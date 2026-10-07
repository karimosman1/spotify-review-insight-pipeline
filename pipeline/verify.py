"""Stage 3: independent verification (role `verify`).

A declared, deterministic random sample is re-labelled from the original text only, using the
separately worded VERIFY_QUESTIONS. The verifier never sees the enricher's answer; code compares.
"""

import hashlib
import time
from collections import Counter
from pathlib import Path

from . import labels as L
from .common import JsonlLog, read_source_rows, text_sha, write_json
from .enrich import latest_records, parse_answers
from .jev import BudgetExceeded, FatalAPIError, JevClient, SpendLedger, TransientFailure

VERIFY_SEED = "verify-v1"


def in_sample(review_id, rate):
    h = int(hashlib.sha256(f"{VERIFY_SEED}:{review_id}".encode()).hexdigest()[:8], 16)
    return h / 0xFFFFFFFF < rate


def run_verify(input_csv, out_dir, *, rate, max_spend, phase="initial", global_ledger="state/ledger.json",
               cache_path=None, log=print):
    out_dir = Path(out_dir)
    t0 = time.monotonic()
    enriched = latest_records(out_dir)
    rows = {r["review_id"]: r for r in read_source_rows(input_csv)}
    sample = sorted(rid for rid, rec in enriched.items() if rec["status"] == "completed" and in_sample(rid, rate))
    vlog = JsonlLog(out_dir / "verify_results.jsonl")
    calls = JsonlLog(out_dir / "calls.jsonl")
    vcache = JsonlLog(cache_path or out_dir / "verify_cache.jsonl")
    cached = {(c["text_sha256"], c["label_config"]): c["labels"] for c in vcache.read()}
    have = {v["review_id"]: v for v in vlog.read()}
    run_id = f"verify-{phase}-{time.strftime('%Y%m%dT%H%M%S')}"
    client, ledger = None, SpendLedger(max_spend, global_ledger)
    stats = Counter()
    stop_reason = None
    for rid in sample:
        if rid in have:
            stats["already_verified"] += 1
            continue
        text = rows[rid]["review_text"]
        key = (text_sha(text), L.VERIFY_LABEL_CONFIG)
        if key in cached:
            labels = cached[key]; stats["cache_hits"] += 1
        else:
            client = client or JevClient(ledger, on_attempt=calls.append)
            ctx = {"run_id": run_id, "role": "verify", "phase": phase, "review_ids": [rid],
                   "label_config": L.VERIFY_LABEL_CONFIG, "model": L.JEV_MODEL, "call_id": f"verify-{rid[:12]}"}
            try:
                resp, _ = client.ask(text, L.VERIFY_QUESTIONS, L.JEV_MODEL, est_tokens=2500 + len(text), context=ctx)
                labels, _conf = parse_answers(resp, L.VERIFY_QUESTIONS)
                stats["requests"] += 1
            except (BudgetExceeded, FatalAPIError) as e:
                stop_reason = str(e); break
            except (TransientFailure, ValueError) as e:
                vlog.append({"review_id": rid, "status": "failed", "error": str(e)}); stats["failed"] += 1
                continue
            vcache.append({"text_sha256": key[0], "label_config": key[1], "labels": labels})
        vlog.append({"review_id": rid, "status": "verified", "label_config": L.VERIFY_LABEL_CONFIG, **labels})
    report = compare(out_dir, enriched)
    report.update(sample_rate=rate, sample_seed=VERIFY_SEED, sample_size=len(sample), stats=dict(stats),
                  stop_reason=stop_reason, run_spent_usd=round(ledger.run_spent, 8),
                  wall_clock_s=round(time.monotonic() - t0, 3))
    write_json(out_dir / "verify_report.json", report)
    log(f"[verify] sample {len(sample)} | new requests {stats['requests']} | cache hits {stats['cache_hits']} | "
        f"topic agree {report['agreement'].get('topic')} | disagreements {len(report['disagreements'])}")
    return report


def compare(out_dir, enriched):
    """Code-only comparison of verifier vs enricher labels."""
    ver = {v["review_id"]: v for v in JsonlLog(Path(out_dir) / "verify_results.jsonl").read() if v["status"] == "verified"}
    agree, dis = Counter(), []
    for rid, v in sorted(ver.items()):
        e = enriched[rid]
        diffs = {f: {"enricher": e[f], "verifier": v[f]} for f in ("topic", "intent", "severity") if e[f] != v[f]}
        for f in ("topic", "intent", "severity"):
            agree[f] += e[f] == v[f]
        if diffs:
            dis.append({"review_id": rid, "evidence_quote": e["evidence_quote"], "diffs": diffs})
    n = len(ver)
    return {"compared": n, "agreement": {f: round(agree[f] / n, 4) if n else None for f in ("topic", "intent", "severity")},
            "disagreements": dis}
