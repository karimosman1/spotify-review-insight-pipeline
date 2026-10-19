"""Stage 6: the memo role (role `memo`), the only stage that uses a text model.

Input is deliberately narrow: the saved ranking table plus a bounded evidence pack of a few example
reviews per top issue. The raw corpus never reaches this model. Output is a fixed JSON schema, and
code then checks every issue ID, review ID and number it cites against the saved calculations;
anything unsupported is rejected rather than published.
"""

import csv
import json
import time
from pathlib import Path

import anthropic

from .common import JsonlLog, canonical, text_sha, write_json
from .enrich import latest_records

MEMO_MODEL = "claude-haiku-4-5"          # $1.00 / $5.00 per MTok (checked 2026-10-06)
MEMO_PROMPT_VERSION = "memo-p4"
MEMO_LABEL_CONFIG = f"{MEMO_MODEL}+{MEMO_PROMPT_VERSION}"
EVIDENCE_PER_ISSUE = 4
MAX_QUOTE_CHARS = 220

SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "headline": {"type": "string"},
                "rationale": {"type": "string"},
                "cited_claim_ids": {"type": "array", "items": {"type": "string"}},
                "cited_review_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["issue_id", "headline", "rationale", "cited_claim_ids", "cited_review_ids"],
            "additionalProperties": False,
        },
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "case_for": {"type": "string"},
                    "why_not_first": {"type": "string"},
                    "cited_claim_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["issue_id", "case_for", "why_not_first", "cited_claim_ids"],
                "additionalProperties": False,
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["recommendation", "alternatives", "limitations"],
    "additionalProperties": False,
}

SYSTEM = """You are a product analyst writing a short priority memo for Spotify.

You receive ONLY: (1) a ranked issue table computed from classified app reviews, and (2) a small
evidence pack of example reviews. You have no other data.

Hard rules:
- Use only numbers that appear in the ranked table. Never compute, estimate or invent a number.
- Cite every material number by its claim_id. Each claim belongs to ONE issue_id: only cite claims
  whose issue_id matches the issue that section is about. Check the claim's issue_id before citing it.
- Write the number itself next to the claim id that supports it.
- Do NOT compute ratios, percentages, differences, multiples or growth between numbers
  ("40% higher", "twice as many", "3x the severity"). Those are derived values that exist in no
  saved calculation. Compare qualitatively instead: "higher mean severity but fewer complaints".
- Cite review IDs only from the evidence pack, exactly as written.
- The data is self-selected public app reviews. It contains NO revenue, plan tier, confirmed
  cancellations, or the full customer population. Never state revenue at risk, churn, or a causal
  claim about retention. Cancellation language is stated intent, not observed churn.
- priority_score = complaint_count x mean_severity. A high-volume, low-severity issue and a
  low-volume, high-severity issue are a genuine trade-off: say so plainly.
- ORDER WORDS COME FROM CODE, NOT FROM YOU. The `comparisons` field gives every issue's rank by
  priority_score, by mean_severity and by complaint_count (1 = highest), computed by code. Any
  "highest", "second-highest", "lowest", "most", "largest" or "tied" statement must match those
  ranks exactly. Never work out an ordering yourself by comparing numbers. Prefer the explicit
  form "ranks 3 of 8 by mean severity" so the claim can be checked.
- Note which issue has the MOST complaints: it is the one with rank_by_complaint_count 1, which may
  not be the issue you recommend.
- Never state a share of the total ("majority", "most of the complaints", "half", "dominates").
  No share was calculated, so any such statement is unsupported.
- Be concise and concrete. No marketing language."""


def comparative_facts(ranking):
    """Code-computed orderings, so the model never has to infer which number is larger.
    Dense ranks: equal values share a rank, and the next distinct value takes the next rank."""
    from decimal import Decimal

    def dense(key):
        vals = sorted({Decimal(r[key]) for r in ranking}, reverse=True)
        pos = {v: i + 1 for i, v in enumerate(vals)}
        return {r["issue_id"]: pos[Decimal(r[key])] for r in ranking}, len(vals)

    by_p, _ = dense("priority_score")
    by_s, n_s = dense("mean_severity")
    by_c, n_c = dense("complaint_count")
    score = {r["issue_id"]: Decimal(r["priority_score"]) for r in ranking}
    out = {}
    for r in ranking:
        iid = r["issue_id"]
        out[iid] = {"rank_by_priority_score": by_p[iid], "rank_by_mean_severity": by_s[iid],
                    "rank_by_complaint_count": by_c[iid],
                    "lowest_mean_severity": by_s[iid] == n_s, "lowest_complaint_count": by_c[iid] == n_c,
                    "tied_on_priority_with": sorted(o for o in score if o != iid and score[o] == score[iid])}
    return out


def build_evidence(out_dir, ranking, top_n=4):
    """A few short, high-severity examples per top issue. Quotes are exact source substrings
    produced earlier by code, so nothing new is introduced here."""
    from .common import load_run_records
    recs = load_run_records(out_dir)       # falls back to the committed export on a fresh clone
    pack = {}
    for row in ranking[:top_n]:
        members = [r for r in recs.values()
                   if r["status"] == "completed" and f"ISS-{r['topic']}" == row["issue_id"]
                   and r["intent"] in ("complaint", "cancellation")]
        members.sort(key=lambda r: (-r["severity"], r["review_id"]))
        pack[row["issue_id"]] = [
            {"review_id": r["review_id"], "severity": r["severity"], "intent": r["intent"],
             "quote": r["evidence_quote"][:MAX_QUOTE_CHARS]}
            for r in members[:EVIDENCE_PER_ISSUE]]
    return pack


def run_memo(out_dir, *, scope_note, max_spend=0.25, cache_path=None, log=print):
    out_dir = Path(out_dir)
    ranking = list(csv.DictReader((out_dir / "ranking.csv").open(encoding="utf-8")))
    claims = list(csv.DictReader((out_dir / "claims.csv").open(encoding="utf-8")))
    evidence = build_evidence(out_dir, ranking)
    calls = JsonlLog(out_dir / "calls.jsonl")

    by_claim = {c["claim_id"]: c for c in claims}
    valid_issues = {r["issue_id"] for r in ranking}
    valid_reviews = {e["review_id"] for v in evidence.values() for e in v}

    facts = comparative_facts(ranking)
    payload = {"scope": scope_note, "ranked_issues": ranking, "comparisons": facts, "claims": claims,
               "evidence_pack": evidence}
    user_msg = "Write the priority memo from this data.\n\n" + json.dumps(payload, indent=2)
    # Result cache keyed by the exact input + config: an unchanged rerun makes no model call.
    key = text_sha(canonical({"config": MEMO_LABEL_CONFIG, "system": SYSTEM, "user": user_msg}))
    cache = JsonlLog(cache_path or out_dir / "memo_cache.jsonl")
    # last entry wins: after a repair the cache holds the rejected first answer AND the repaired one
    hit = ([c for c in cache.read() if c["key"] == key] or [None])[-1]
    if hit:
        text, in_tok, out_tok, cost, duration, request_id = hit["text"], 0, 0, 0.0, 0.0, hit.get("request_id")
        log("[memo] cache hit — no model call")
    else:
        client = anthropic.Anthropic()
        t0 = time.monotonic()
        resp = client.messages.create(
            model=MEMO_MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        duration = time.monotonic() - t0
        in_tok, out_tok, request_id = resp.usage.input_tokens, resp.usage.output_tokens, resp._request_id
        cost = in_tok * 1.0e-6 + out_tok * 5.0e-6
        calls.append({"run_id": f"memo-{time.strftime('%Y%m%dT%H%M%S')}", "role": "memo", "phase": "initial",
                      "review_ids": [], "model": MEMO_MODEL, "label_config": MEMO_LABEL_CONFIG,
                      "request_id": request_id, "outcome": "succeeded", "attempt": 1,
                      "input_tokens": in_tok, "output_tokens": out_tok, "usage_known": True,
                      "cost_usd_estimate": round(cost, 8), "duration_s": round(duration, 3),
                      "stop_reason": resp.stop_reason,
                      "consumed_artifacts": ["ranking.csv", "claims.csv", "evidence_pack(from results.jsonl)"]})
        if resp.stop_reason not in ("end_turn", "stop_sequence"):
            raise RuntimeError(f"memo call stopped with {resp.stop_reason}; output not trusted")
        text = next(b.text for b in resp.content if b.type == "text")
        cache.append({"key": key, "label_config": MEMO_LABEL_CONFIG, "text": text, "request_id": request_id})
        if cost > max_spend:
            log(f"[memo] WARNING: memo cost ${cost:.4f} exceeded expected ${max_spend}")

    memo = json.loads(text)
    problems, cited_claims = validate_memo(memo, ranking, claims, evidence, scope_note)
    attempts = 1

    # One bounded repair attempt, the same rule enrichment uses for invalid output: send the code's
    # objections back once. If the second answer still fails, it is published as FAILED, never
    # silently accepted, and nothing loops.
    if problems and not hit:
        attempts = 2
        feedback = ("Your memo failed these code checks against the saved calculations. Rewrite it so "
                    "none of them apply, changing only what is wrong:\n- " + "\n- ".join(problems))
        t0 = time.monotonic()
        resp2 = anthropic.Anthropic().messages.create(
            model=MEMO_MODEL, max_tokens=4000, system=SYSTEM,
            messages=[{"role": "user", "content": user_msg},
                      {"role": "assistant", "content": text},
                      {"role": "user", "content": feedback}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        d2 = time.monotonic() - t0
        i2, o2 = resp2.usage.input_tokens, resp2.usage.output_tokens
        c2 = i2 * 1.0e-6 + o2 * 5.0e-6
        calls.append({"run_id": f"memo-repair-{time.strftime('%Y%m%dT%H%M%S')}", "role": "memo",
                      "phase": "initial", "review_ids": [], "model": MEMO_MODEL,
                      "label_config": MEMO_LABEL_CONFIG, "request_id": resp2._request_id,
                      "outcome": "succeeded", "attempt": 2, "input_tokens": i2, "output_tokens": o2,
                      "usage_known": True, "cost_usd_estimate": round(c2, 8), "duration_s": round(d2, 3),
                      "stop_reason": resp2.stop_reason, "repair_of_problems": problems})
        first_problems = problems
        text = next(b.text for b in resp2.content if b.type == "text")
        memo = json.loads(text)
        problems, cited_claims = validate_memo(memo, ranking, claims, evidence, scope_note)
        in_tok, out_tok, cost, duration = in_tok + i2, out_tok + o2, cost + c2, duration + d2
        log(f"[memo] repair attempt: {len(first_problems)} problems -> {len(problems)}")
        # cache the final answer so a warm rerun reproduces it with no call
        cache.append({"key": key, "label_config": MEMO_LABEL_CONFIG, "text": text,
                      "request_id": resp2._request_id, "repaired": True})

    result = {"memo": memo, "validation": {"passed": not problems, "problems": problems,
                                           "validator": VALIDATOR_VERSION,
                                           "claims_cited": sorted(cited_claims),
                                           "reviews_cited": memo["recommendation"]["cited_review_ids"]},
              "model": MEMO_MODEL, "label_config": MEMO_LABEL_CONFIG,
              "usage": {"input_tokens": in_tok, "output_tokens": out_tok}, "cache_hit": bool(hit),
              "attempts": attempts,
              "cost_usd": round(cost, 8), "duration_s": round(duration, 3)}
    write_json(out_dir / "memo_model_output.json", result)
    (out_dir / "memo.md").write_text(render_md(memo, ranking, by_claim, evidence, scope_note, problems),
                                     encoding="utf-8")
    log(f"[memo] {MEMO_MODEL} | {in_tok} in / {out_tok} out | ${cost:.5f} | "
        f"validation {'PASSED' if not problems else 'FAILED: ' + '; '.join(problems)}")
    return result


TOPIC_WORDS = {"usability": "ISS-usability", "playback": "ISS-playback", "billing": "ISS-billing",
               "access": "ISS-access", "catalog": "ISS-catalog", "download": "ISS-downloads",
               "support": "ISS-support", "other": "ISS-other"}

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
            "eighth": 8, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6, "7th": 7, "8th": 8}
UP_WORDS = r"highest|largest|most|biggest|greatest|top|leading"
DOWN_WORDS = r"lowest|smallest|fewest|least"
# Proportion words assert a share of a total. No saved calculation holds a share, so these are
# unsupported by construction (memo-p3 claimed "the majority of complainants" for a 27% issue).
PROPORTION_WORDS = r"\bmajority\b|\bmost of (?:the )?(?:complaints|complainants|reviewers|users)\b|\bhalf of\b|\bdominat\w*"


METRIC_WORDS = [("rank_by_mean_severity", ("sever",)),
                ("rank_by_complaint_count", ("complaint", "volume", "count", "cohort", "reviewers", "complainants")),
                ("rank_by_priority_score", ("priority", "score", "overall", "urgen", "pressing"))]
VALIDATOR_VERSION = "memo-validator-v3"


def _metric_for(fragment, last=False):
    """The metric named nearest the superlative: first occurrence after it, or last occurrence
    before it (last=True). "highest complaint volume with moderate severity" is about volume."""
    f = fragment.lower()
    hits = [(f.rfind(w) if last else f.find(w), metric) for metric, words in METRIC_WORDS for w in words]
    hits = [h for h in hits if h[0] >= 0]
    if not hits:
        return None
    return (max(hits) if last else min(hits))[1]


def validate_memo(memo, ranking, claims, evidence, scope_note):
    """Code-only checks on the memo role's output. Returns (problems, cited_claim_ids)."""
    import re
    from decimal import Decimal, InvalidOperation

    by_claim = {c["claim_id"]: c for c in claims}
    valid_issues = {r["issue_id"] for r in ranking}
    valid_reviews = {e["review_id"] for v in evidence.values() for e in v}
    facts = comparative_facts(ranking)
    problems = []
    sections = [("recommendation", memo["recommendation"])] + \
               [(f"alternative {a['issue_id']}", a) for a in memo["alternatives"]]
    cited_claims = set()
    for name, sec in sections:
        cited_claims |= set(sec["cited_claim_ids"])
        if sec["issue_id"] not in valid_issues:
            problems.append(f"{name} cites unknown issue_id {sec['issue_id']}")
        for cid in sec["cited_claim_ids"]:
            c = by_claim.get(cid)
            if c is None:
                problems.append(f"{name} cites unknown claim_id {cid}")
            elif c["issue_id"] != sec["issue_id"]:
                # memo-p1: billing's numbers cited under another issue's claim ids
                problems.append(f"{name} cites {cid}, which belongs to {c['issue_id']}, not {sec['issue_id']}")
    for rid in memo["recommendation"]["cited_review_ids"]:
        if rid not in valid_reviews:
            problems.append(f"cites review_id {rid} that was not in the evidence pack")

    # Numbers: every figure in the prose must equal (by value, not spelling) a saved claim, a ranking
    # field, a severity level, or a figure stated in the scope note the pipeline gave the model.
    def dec(v):
        try:
            return Decimal(str(v).replace(",", ""))
        except InvalidOperation:
            return None
    allowed = {dec(c["value"]) for c in claims}
    allowed |= {dec(r[k]) for r in ranking for k in
                ("complaint_count", "severity_sum", "mean_severity", "priority_score", "rank")}
    allowed |= {Decimal(n) for n in range(1, 6)}
    allowed |= {dec(t) for t in _numbers(scope_note or "")}
    allowed.discard(None)
    prose_parts = [("recommendation", memo["recommendation"]["issue_id"],
                    memo["recommendation"]["headline"] + ". " + memo["recommendation"]["rationale"])]
    prose_parts += [(f"alternative {a['issue_id']}", a["issue_id"], a["case_for"] + " " + a["why_not_first"])
                    for a in memo["alternatives"]]
    all_prose = " ".join(p[2] for p in prose_parts) + " " + " ".join(memo["limitations"])
    unsupported = sorted({t for t in _numbers(all_prose) if dec(t) not in allowed})
    if unsupported:
        problems.append(f"prose contains numbers absent from saved calculations: {unsupported}")

    # Order words must match the ranks code computed. memo-p2 swapped access and playback while every
    # number was correct; memo-p3 called access "second-lowest" by volume when it is third-lowest.
    # So this parses the general shape — [ordinal] + up/down word + metric — not a list of phrases.
    n_distinct = {m: len({v[m] for v in facts.values()})
                  for m in ("rank_by_mean_severity", "rank_by_complaint_count", "rank_by_priority_score")}
    ordinal_re = re.compile(
        rf"\b(?:(first|second|third|fourth|fifth|sixth|seventh|eighth|[1-8](?:st|nd|rd|th))[- ])?"
        rf"({UP_WORDS}|{DOWN_WORDS})\b([^.;:]{{0,40}})", re.I)
    rank_re = re.compile(r"\branks?\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|[1-8](?:st|nd|rd|th)?)"
                         r"\b([^.;:]{0,40})", re.I)
    for name, sec_issue, text in prose_parts:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            low = sentence.lower()
            mentions = [(m.start(), m.group(0)) for m in re.finditer(r"ISS-[a-z]+", sentence)]
            mentions += [(m.start(), iid) for w, iid in TOPIC_WORDS.items() for m in re.finditer(rf"\b{w}", low)]
            mentions.sort()

            def subject_at(pos):
                before = [iid for at, iid in mentions if at < pos]
                return before[-1] if before else sec_issue

            subject = subject_at(len(sentence))
            if subject not in facts:
                continue
            if re.search(PROPORTION_WORDS, low):
                problems.append(f"{name}: '{sentence.strip()[:90]}' — asserts a share of the total, "
                                f"which no saved calculation contains")
            for m in ordinal_re.finditer(sentence):
                ordw, direction, tail = (m.group(1) or "first").lower(), m.group(2).lower(), m.group(3)
                if re.match(r"\s*(?:among|within|of the top|in the top|of the \w+ (?:largest|highest))", tail, re.I):
                    continue          # a comparison within an unstated subset cannot be checked
                metric = _metric_for(tail.split(",")[0])
                # Look back for the metric only when the superlative ends its clause ("…count is the
                # highest."). If a non-metric word follows ("the most urgent", "most users"), the
                # claim is about that word, so borrowing a metric from an earlier clause would test
                # the wrong thing.
                if metric is None and re.match(r"\s*(?:$|[,.;:)])", tail):
                    metric = _metric_for(sentence[max(0, m.start() - 30):m.start()], last=True)
                if metric is None:
                    continue          # e.g. "most users", "highest-impact" with no measurable metric
                n = ORDINALS.get(ordw, 1)
                want = n if re.fullmatch(UP_WORDS, direction) else n_distinct[metric] - n + 1
                subject = subject_at(m.start())
                got = facts[subject][metric]
                if got != want:
                    problems.append(f"{name}: '{sentence.strip()[:90]}' — {subject} is rank {got} by "
                                    f"{metric.replace('rank_by_', '')}, not {want}")
            for m in rank_re.finditer(sentence):
                n = ORDINALS.get(m.group(1).lower(), int(m.group(1)[0]) if m.group(1)[0].isdigit() else None)
                metric = _metric_for(m.group(2)) or "rank_by_priority_score"
                subject = subject_at(m.start())
                if n and facts[subject][metric] != n:
                    problems.append(f"{name}: '{sentence.strip()[:90]}' — {subject} ranks "
                                    f"{facts[subject][metric]} by {metric.replace('rank_by_', '')}, not {n}")
            if re.search(r"\btied?\b", low) and not facts[subject]["tied_on_priority_with"]:
                problems.append(f"{name}: says 'tied' but {subject} shares its priority_score with no issue")
    return problems, cited_claims


def revalidate(out_dir, scope_note, log=print):
    """Re-run the code checks on a saved memo answer. Deterministic, no model call. Used when the
    validator itself is corrected, so the published verdict always comes from the current rules."""
    out_dir = Path(out_dir)
    saved = json.loads((out_dir / "memo_model_output.json").read_text())
    ranking = list(csv.DictReader((out_dir / "ranking.csv").open(encoding="utf-8")))
    claims = list(csv.DictReader((out_dir / "claims.csv").open(encoding="utf-8")))
    evidence = build_evidence(out_dir, ranking)
    problems, cited = validate_memo(saved["memo"], ranking, claims, evidence, scope_note)
    before = saved["validation"]
    saved["validation"] = {"passed": not problems, "problems": problems, "claims_cited": sorted(cited),
                           "reviews_cited": saved["memo"]["recommendation"]["cited_review_ids"],
                           "validator": VALIDATOR_VERSION,
                           "previous_verdict": {k: before.get(k) for k in ("passed", "problems")}}
    write_json(out_dir / "memo_model_output.json", saved)
    by_claim = {c["claim_id"]: c for c in claims}
    (out_dir / "memo.md").write_text(render_md(saved["memo"], ranking, by_claim, evidence, scope_note, problems),
                                     encoding="utf-8")
    log(f"[memo] re-validated with {VALIDATOR_VERSION}: {'PASSED' if not problems else problems}")
    return saved


def _isnum(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _numbers(text):
    """Numeric tokens in prose, excluding digits inside review UUIDs and claim ids."""
    import re
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{20,}\b", " ", text)   # review IDs
    text = re.sub(r"\bC\d+\b", " ", text)                          # claim ids
    out = []
    for t in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        out.append(t.replace(",", "").rstrip("."))
    return out


def render_md(memo, ranking, by_claim, evidence, scope_note, problems):
    r = memo["recommendation"]
    L = [f"# Priority memo: {r['headline']}", "", f"_Scope: {scope_note}_", "",
         f"**Recommendation: {r['issue_id']}**", "", r["rationale"], "",
         "## Supporting numbers", "",
         "| claim | issue | metric | value |", "|---|---|---|---|"]
    for cid in r["cited_claim_ids"]:
        c = by_claim.get(cid)
        if c:
            L.append(f"| {cid} | {c['issue_id']} | {c['metric']} | {c['value']} |")
    L += ["", "## Representative reviews", ""]
    for rid in r["cited_review_ids"]:
        ev = next((e for v in evidence.values() for e in v if e["review_id"] == rid), None)
        if ev:
            L.append(f"- `{rid}` (severity {ev['severity']}, {ev['intent']}): \"{ev['quote']}\"")
    L += ["", "## Alternatives considered", ""]
    for a in memo["alternatives"]:
        L.append(f"**{a['issue_id']}** — {a['case_for']} _Why not first:_ {a['why_not_first']} "
                 f"[{', '.join(a['cited_claim_ids'])}]")
    L += ["", "## Limitations", ""] + [f"- {x}" for x in memo["limitations"]]
    L += ["", "## Full ranking (recomputed from saved records, no model call)", "",
          "| rank | issue | complaints | mean severity | priority |", "|---|---|---|---|---|"]
    for row in ranking:
        L.append(f"| {row['rank']} | {row['issue_id']} | {row['complaint_count']} | "
                 f"{row['mean_severity']} | {row['priority_score']} |")
    L += ["", "---", f"_Written by `{MEMO_MODEL}` from saved aggregates and a bounded evidence pack. "
          f"Code checked every cited claim ID, review ID and number against the saved calculations: "
          f"{'all checks passed' if not problems else 'ISSUES: ' + '; '.join(problems)}._"]
    return "\n".join(L) + "\n"
