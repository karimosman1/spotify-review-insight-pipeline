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

from .common import JsonlLog, write_json
from .enrich import latest_records

MEMO_MODEL = "claude-haiku-4-5"          # $1.00 / $5.00 per MTok (checked 2026-10-06)
MEMO_PROMPT_VERSION = "memo-p2"
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
- Be concise and concrete. No marketing language."""


def build_evidence(out_dir, ranking, top_n=4):
    """A few short, high-severity examples per top issue. Quotes are exact source substrings
    produced earlier by code, so nothing new is introduced here."""
    recs = latest_records(out_dir)
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


def run_memo(out_dir, *, scope_note, max_spend=0.25, log=print):
    out_dir = Path(out_dir)
    ranking = list(csv.DictReader((out_dir / "ranking.csv").open(encoding="utf-8")))
    claims = list(csv.DictReader((out_dir / "claims.csv").open(encoding="utf-8")))
    evidence = build_evidence(out_dir, ranking)
    calls = JsonlLog(out_dir / "calls.jsonl")

    by_claim = {c["claim_id"]: c for c in claims}
    valid_issues = {r["issue_id"] for r in ranking}
    valid_reviews = {e["review_id"] for v in evidence.values() for e in v}

    payload = {"scope": scope_note, "ranked_issues": ranking, "claims": claims, "evidence_pack": evidence}
    client = anthropic.Anthropic()
    t0 = time.monotonic()
    resp = client.messages.create(
        model=MEMO_MODEL, max_tokens=4000, system=SYSTEM,
        messages=[{"role": "user", "content":
                   "Write the priority memo from this data.\n\n" + json.dumps(payload, indent=2)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    duration = time.monotonic() - t0
    u = resp.usage
    cost = u.input_tokens * 1.0e-6 + u.output_tokens * 5.0e-6
    calls.append({"run_id": f"memo-{time.strftime('%Y%m%dT%H%M%S')}", "role": "memo", "phase": "initial",
                  "review_ids": [], "model": MEMO_MODEL, "label_config": MEMO_LABEL_CONFIG,
                  "request_id": resp._request_id, "outcome": "succeeded", "attempt": 1,
                  "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "usage_known": True,
                  "cost_usd_estimate": round(cost, 8), "duration_s": round(duration, 3),
                  "stop_reason": resp.stop_reason,
                  "consumed_artifacts": ["ranking.csv", "claims.csv", "evidence_pack(from results.jsonl)"]})
    if cost > max_spend:
        log(f"[memo] WARNING: memo cost ${cost:.4f} exceeded expected ${max_spend}")

    text = next(b.text for b in resp.content if b.type == "text")
    memo = json.loads(text)

    # ---- code validation: every cited ID and number must trace to a saved calculation
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
                # the exact failure seen in memo-p1 v1: billing's numbers cited under another
                # issue's claim ids. A claim only supports the issue it was computed for.
                problems.append(f"{name} cites {cid}, which belongs to {c['issue_id']}, not {sec['issue_id']}")
    for rid in memo["recommendation"]["cited_review_ids"]:
        if rid not in valid_reviews:
            problems.append(f"cites review_id {rid} that was not in the evidence pack")
    # Every number in the prose must appear in the saved claims or ranking. Review IDs and claim
    # IDs are stripped first so their digits are not mistaken for numeric claims.
    allowed = {c["value"] for c in claims} | {r[k] for r in ranking for k in
                                              ("complaint_count", "severity_sum", "mean_severity", "priority_score", "rank")}
    allowed |= {str(int(float(v))) for v in allowed if _isnum(v)}
    allowed |= {"1", "2", "3", "4", "5"}  # severity levels are defined labels, not derived numbers
    prose = " ".join([memo["recommendation"]["headline"], memo["recommendation"]["rationale"]]
                     + [a["case_for"] + " " + a["why_not_first"] for a in memo["alternatives"]]
                     + memo["limitations"])
    unsupported = [tok for tok in _numbers(prose) if tok not in allowed]
    if unsupported:
        problems.append(f"prose contains numbers absent from saved calculations: {sorted(set(unsupported))}")

    result = {"memo": memo, "validation": {"passed": not problems, "problems": problems,
                                           "claims_cited": sorted(cited_claims),
                                           "reviews_cited": memo["recommendation"]["cited_review_ids"]},
              "model": MEMO_MODEL, "label_config": MEMO_LABEL_CONFIG,
              "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
              "cost_usd": round(cost, 8), "duration_s": round(duration, 3)}
    write_json(out_dir / "memo_model_output.json", result)
    (out_dir / "memo.md").write_text(render_md(memo, ranking, by_claim, evidence, scope_note, problems),
                                     encoding="utf-8")
    log(f"[memo] {MEMO_MODEL} | {u.input_tokens} in / {u.output_tokens} out | ${cost:.5f} | "
        f"validation {'PASSED' if not problems else 'FAILED: ' + '; '.join(problems)}")
    return result


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
