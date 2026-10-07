"""Stage 2: enrichment (role `enrich`).

Code owns: reading every row, empty-text quarantine, exact-text dedupe, cache lookup, pending queue,
validation, the one-retry rule, evidence quotes/entities, and saving after every request.
The model (Jev) owns: topic, intent, severity and sentiment judgments for one review per request.
"""

import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import labels as L
from .common import JsonlLog, file_sha, read_jsonl, read_source_rows, row_sha, text_sha, write_json
from .jev import BudgetExceeded, FatalAPIError, JevClient, SpendLedger, TransientFailure

MAX_REVIEWS_PER_BATCH = 50  # contract limit; Jev requests carry 1 review each, batches group saves/logs
NEEDS_REVIEW_THRESHOLDS = {"topic": 0.50, "intent": 0.50, "severity": 0.40}  # tune on dev data, not golden
SHORT_QUOTE_CHARS = 200


# ---------------------------------------------------------------- deterministic helpers

def extract_quote(text, topic):
    """Exact source substring. Short reviews: the whole text. Longer: the sentence with most
    topic-term hits (first on ties), falling back to the first sentence."""
    stripped = text.strip()
    if len(stripped) <= SHORT_QUOTE_CHARS:
        return stripped
    spans = [(m.start(), m.end()) for m in re.finditer(r"[^.!?\n]+[.!?]*", text)]
    spans = [(a, b) for a, b in spans if text[a:b].strip()]
    terms = L.TOPIC_TERMS.get(topic, [])
    best, best_hits = None, 0
    for a, b in spans:
        seg = text[a:b].lower()
        hits = sum(seg.count(t) for t in terms)
        if hits > best_hits:
            best, best_hits = (a, b), hits
    a, b = best or spans[0]
    quote = text[a:b].strip()
    return quote if quote else stripped


def extract_entities(text):
    low = text.lower()
    return [t for t in L.ENTITY_TERMS if re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", low)]


def parse_answers(resp, questions):
    """Validate a Jev response against the schema. Returns (labels, confidences) or raises ValueError."""
    answers = resp.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("missing answers")
    out, conf = {}, {}
    topic = answers.get("topic", {}).get("choice")
    intent = answers.get("intent", {}).get("choice")
    sev = answers.get("severity", {}).get("choice")
    if topic not in L.TOPICS:
        raise ValueError(f"invalid topic {topic!r}")
    if intent not in L.INTENTS:
        raise ValueError(f"invalid intent {intent!r}")
    if sev not in ("sev1", "sev2", "sev3", "sev4", "sev5"):
        raise ValueError(f"invalid severity {sev!r}")
    out.update(topic=topic, intent=intent, severity=int(sev[3]))
    for k in ("topic", "intent", "severity"):
        c = answers[k].get("confidence")
        conf[k] = round(float(c), 4) if isinstance(c, (int, float)) else None
    if "sentiment" in questions:
        score = answers.get("sentiment", {}).get("score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 4:
            raise ValueError(f"invalid sentiment score {score!r}")
        out["sentiment"] = round(max(-1.0, min(1.0, score / 2 - 1)), 4)
    return out, conf


def parse_batch_answers(resp, n):
    """Validate a batched response. Returns {index: (labels, confidences)} for every VALID review index;
    missing or invalid indices are simply absent, so one bad answer never discards the whole batch."""
    answers = resp.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("missing answers")
    out = {}
    for i in range(1, n + 1):
        try:
            sub = {k: answers[f"{k}_{i}"] for k in ("topic", "intent", "severity", "sentiment")}
        except KeyError:
            continue  # index absent from the response
        try:
            out[i] = parse_answers({"answers": sub}, L.ENRICH_QUESTIONS)
        except (ValueError, KeyError, TypeError):
            continue  # invalid labels for this index
    return out


def apply_contract_rules(labels):
    """Severity consistency rules taken directly from the shared definitions. Logged, not hidden.

    Note: `cancellation` is deliberately NOT bumped to 2. Per the contract, cancellation intent does not
    raise severity, so a bare boycott/uninstall with no reported product problem stays at 1."""
    adj = []
    if labels["intent"] in ("praise", "request", "unclear") and labels["severity"] != 1:
        adj.append(f"severity {labels['severity']}->1 (intent {labels['intent']} has no reported problem)")
        labels["severity"] = 1
    if labels["intent"] == "complaint" and labels["severity"] == 1:
        adj.append("severity 1->2 (a complaint reports at least a dislike)")
        labels["severity"] = 2
    return adj


# ---------------------------------------------------------------- stage runner

def run_enrich(input_csv, out_dir, *, max_spend, cache_path, phase="initial", workers=1, batch_size=1,
               max_new_requests=None, global_ledger="state/ledger.json", dry_run=False, log=print):
    """batch_size=1 sends one review per request (`enrich-p1`). batch_size>1 sends up to that many
    reviews in one request with the rubric carried once in the state (`enrich-b1`)."""
    if batch_size > L.MAX_BATCH:
        raise ValueError(f"batch_size {batch_size} exceeds MAX_BATCH {L.MAX_BATCH}")
    batched = batch_size > 1
    label_config = L.BATCH_LABEL_CONFIG if batched else L.ENRICH_LABEL_CONFIG
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = JsonlLog(out_dir / "results.jsonl")
    calls = JsonlLog(out_dir / "calls.jsonl")
    cache = JsonlLog(cache_path)
    run_id = f"{phase}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    t_start = time.monotonic()

    rows = list(read_source_rows(input_csv))
    done = {r["review_id"]: r for r in results.read() if r["status"] in ("completed", "quarantined")}
    cached = {(c["text_sha256"], c["label_config"]): c for c in cache.read()}

    # Group pending rows by exact text; the first ID seen for a text is its direct original.
    new_records, groups, n_empty = [], {}, 0
    for row in rows:
        rid = row["review_id"]
        if rid in done:
            continue
        if not row["review_text"].strip():
            n_empty += 1
            new_records.append({"review_id": rid, "source_sha256": row_sha(row), "status": "quarantined",
                                "reason": "empty_review_text", "attempts": 0, "run_id": run_id})
            continue
        groups.setdefault(text_sha(row["review_text"]), []).append(row)
    if new_records:
        results.append(*new_records)

    cache_hits, pending = 0, []
    for tsha, members in groups.items():
        hit = cached.get((tsha, label_config))
        if hit:
            cache_hits += len(members)
            results.append(*[make_record(r, hit["labels"], hit["meta"], run_id, label_config, cache_from=hit)
                             for r in members])
        else:
            pending.append((tsha, members))

    summary = {"run_id": run_id, "phase": phase, "input": str(input_csv), "input_sha256": file_sha(input_csv),
               "label_config": label_config, "batch_size": batch_size, "rows": len(rows), "already_done": len(done),
               "empty_quarantined_now": n_empty, "cache_hit_records": cache_hits,
               "pending_unique_texts": len(pending), "pending_records": sum(len(m) for _, m in pending),
               "workers": workers, "max_spend_usd": max_spend}
    log(f"[enrich] {summary['rows']} rows | {len(done)} already done | {n_empty} empty->quarantine | "
        f"{cache_hits} cache hits | {len(pending)} unique texts need a model call")

    if dry_run:
        per_req_overhead = 5300 if batched else 1500   # rubric+questions, measured; see cost/report.md
        n_req = -(-len(pending) // batch_size)
        est_tokens = n_req * per_req_overhead + sum(len(m[0]["review_text"]) // 3 for _, m in pending)
        summary.update(dry_run=True, requests_planned=n_req, est_input_tokens=est_tokens,
                       est_cost_usd=round(est_tokens * 0.042e-6, 6))
        log(f"[enrich] DRY RUN: ~{est_tokens:,} input tokens ~= ${summary['est_cost_usd']:.4f}. No calls made.")
        return summary

    ledger = SpendLedger(max_spend, global_ledger)
    client = JevClient(ledger, on_attempt=calls.append)
    stop = threading.Event()
    stop_reason = [None]
    counter_lock = threading.Lock()
    stats = {"requests": 0, "completed": 0, "quarantined": 0, "pending_failed": 0}

    def work(chunk):
        """One request covering <=batch_size unique texts. Results are saved per chunk, so a crash or a
        budget stop loses at most one in-flight request."""
        if stop.is_set():
            return
        with counter_lock:
            if max_new_requests is not None and stats["requests"] >= max_new_requests:
                stop.set(); stop_reason[0] = f"max_new_requests={max_new_requests} reached (simulated interruption)"
                return
            stats["requests"] += 1
        firsts = [members[0] for _, members in chunk]
        texts = [r["review_text"] for r in firsts]
        ids = [r["review_id"] for r in firsts]
        chunk_key = text_sha("|".join(t[:12] for t in texts))[:12]
        est = 5500 + sum(len(t) for t in texts) if batched else 3000 + len(texts[0])
        state = L.batch_state(texts) if batched else texts[0]
        questions = L.batch_questions(len(texts)) if batched else L.ENRICH_QUESTIONS

        parsed, attempts_total, error = {}, 0, None
        for validation_try in (1, 2):  # invalid model output: retry once, then quarantine
            ctx = {"run_id": run_id, "role": "enrich", "phase": phase, "review_ids": ids, "batch_size": len(texts),
                   "label_config": label_config, "model": L.JEV_MODEL,
                   "call_id": f"{chunk_key}-v{validation_try}", "validation_try": validation_try}
            resp, n = client.ask(state, questions, L.JEV_MODEL, est_tokens=est, context=ctx)
            attempts_total += n
            if batched:
                parsed = parse_batch_answers(resp, len(texts))
            else:
                try:
                    parsed = {1: parse_answers(resp, questions)}
                except ValueError as e:
                    error, parsed = str(e), {}
            if len(parsed) == len(texts):
                break
            missing = [i for i in range(1, len(texts) + 1) if i not in parsed]
            error = error or f"missing/invalid answers for review index {missing}"
            calls.append({**ctx, "outcome": "invalid_output", "error": error,
                          "request_id": f"validation-{ctx['call_id']}"})

        done_recs, quar_recs, cache_rows = [], [], []
        for i, (tsha, members) in enumerate(chunk, 1):
            if i not in parsed:
                quar_recs += [{"review_id": r["review_id"], "source_sha256": row_sha(r), "status": "quarantined",
                               "reason": f"invalid_model_output: {error}", "attempts": attempts_total,
                               "run_id": run_id} for r in members]
                continue
            lbl, conf = parsed[i]
            meta = {"confidence": conf, "rule_adjustments": apply_contract_rules(lbl), "attempts": attempts_total,
                    "model_reported": resp.get("model"), "origin_review_id": members[0]["review_id"]}
            cache_rows.append({"text_sha256": tsha, "label_config": label_config, "labels": lbl, "meta": meta})
            done_recs += [make_record(r, lbl, meta, run_id, label_config, original=members[0]["review_id"])
                          for r in members]
        if cache_rows:
            cache.append(*cache_rows)
        if done_recs:
            results.append(*done_recs)
        if quar_recs:
            results.append(*quar_recs)
        with counter_lock:
            stats["completed"] += len(done_recs)
            stats["quarantined"] += len(quar_recs)

    # One request per chunk of <=batch_size unique texts (contract limit is 50 reviews/request).
    chunks = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
    snapshot_every = max(1, min(50, len(chunks) // 20 or 1))

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, c): i for i, c in enumerate(chunks, 1)}
            for k, f in enumerate(as_completed(futures), 1):
                try:
                    f.result()
                except BudgetExceeded as e:
                    stop.set(); stop_reason[0] = f"budget: {e}"
                except FatalAPIError as e:
                    stop.set(); stop_reason[0] = f"fatal API error: {e}"
                except TransientFailure as e:
                    with counter_lock:
                        stats["pending_failed"] += 1
                    log(f"[enrich] request failed after retries, left pending: {e}")
                if k % snapshot_every == 0 or k == len(chunks):
                    write_json(out_dir / "progress.json", {"run_id": run_id, "chunks_done": k, "chunks": len(chunks),
                                                           **stats, "run_spent_usd": round(ledger.run_spent, 8)})
                    log(f"[enrich] {k}/{len(chunks)} requests | completed={stats['completed']} "
                        f"quarantined={stats['quarantined']} spent=${ledger.run_spent:.6f}")
    except KeyboardInterrupt:
        stop_reason[0] = "KeyboardInterrupt (saved progress is kept)"
        log("[enrich] interrupted; everything saved so far is kept")

    summary.update(stats, stop_reason=stop_reason[0], run_spent_usd=round(ledger.run_spent, 8),
                   wall_clock_s=round(time.monotonic() - t_start, 3))
    if stop_reason[0]:
        log(f"[enrich] STOPPED: {stop_reason[0]}")
    JsonlLog(out_dir / "run_log.jsonl").append({"stage": "enrich", **summary})
    return summary


def make_record(row, labels, meta, run_id, label_config=None, original=None, cache_from=None):
    text = row["review_text"]
    quote = extract_quote(text, labels["topic"])
    conf = meta.get("confidence", {})
    reasons = [f"low {k} confidence {v}" for k, v in conf.items()
               if v is not None and v < NEEDS_REVIEW_THRESHOLDS.get(k, 0)]
    rec = {"review_id": row["review_id"], "source_sha256": row_sha(row), "status": "completed",
           "topic": labels["topic"], "intent": labels["intent"], "sentiment": labels["sentiment"],
           "severity": labels["severity"], "entities": extract_entities(text), "evidence_quote": quote,
           "needs_review": bool(reasons), "needs_review_reasons": reasons,
           "label_config": label_config or L.ENRICH_LABEL_CONFIG,
           "confidence": conf, "rule_adjustments": meta.get("rule_adjustments", []), "run_id": run_id,
           "attempts": 0 if cache_from else meta.get("attempts", 1),
           # source values kept for analysis (not model inputs)
           "review_rating": row["review_rating"], "review_likes": row["review_likes"],
           "app_version": row["app_version"], "review_timestamp": row["review_timestamp"]}
    if cache_from:
        rec["cache_hit"] = True
        if cache_from["meta"]["origin_review_id"] != row["review_id"]:
            rec["cache_source_id"] = cache_from["meta"]["origin_review_id"]
    elif original and original != row["review_id"]:
        rec["cache_source_id"] = original  # exact duplicate text in this run; direct original
    return rec


def latest_records(out_dir):
    """Final record per review_id (last write wins)."""
    recs = {}
    for r in read_jsonl(Path(out_dir) / "results.jsonl"):
        recs[r["review_id"]] = r
    return recs
