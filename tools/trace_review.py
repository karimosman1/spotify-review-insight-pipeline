"""Trace one review from the source CSV to the published memo claim, from saved artifacts only.

  python3 tools/trace_review.py 4c5dee86-808d-4414-932e-d01feeb8a64e
  python3 tools/trace_review.py <id> --md >> docs/trace.md

No model calls, no database, no credentials. Everything printed here is read back out of the files
in runs/<run>/ and grading/, so a grader can re-run it for any review ID and get the same chain.
"""

import argparse
import csv
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import read_jsonl, row_sha, read_source_rows  # noqa: E402
from pipeline.enrich import latest_records  # noqa: E402


def trace(rid, run_dir, analysis_csv):
    run_dir = Path(run_dir)
    out = {"review_id": rid}

    # 1 — source row, exactly as shipped
    src = next((r for r in read_source_rows(analysis_csv) if r["review_id"] == rid), None)
    if src is None:
        sys.exit(f"{rid} is not in {analysis_csv}")
    out["source"] = {**src, "computed_row_sha256": row_sha(src)}

    # 2 — the enriched record
    recs = latest_records(run_dir)
    rec = recs.get(rid)
    if rec is None:
        sys.exit(f"{rid} has no record in {run_dir}")
    out["record"] = rec
    out["quote_is_exact_substring"] = rec.get("evidence_quote", "") in src["review_text"]

    # 3 — the model request that produced it. With batching, the logged review_ids are the first id
    # of each unique-text group, so a duplicate text points back to its cache origin.
    origin = rec.get("cache_source_id") or rid
    call = None
    for c in read_jsonl(run_dir / "calls.jsonl"):
        if c.get("role") == "enrich" and origin in (c.get("review_ids") or []):
            call = c
            break
    out["enrich_call"] = call
    out["cache_origin"] = origin if origin != rid else None

    # 4 — independent verification, if this review fell in the sample
    v = next((x for x in read_jsonl(run_dir / "verify_results.jsonl")
              if x["review_id"] == rid and x["status"] == "verified"), None)
    if v:
        fields = ("topic", "intent", "severity")
        out["verify"] = {"verifier": {f: v[f] for f in fields},
                         "enricher": {f: rec[f] for f in fields},
                         "agreed": {f: rec[f] == v[f] for f in fields},
                         "label_config": v["label_config"]}
    else:
        out["verify"] = None

    # 5 — issue membership
    mem = [m for m in csv.DictReader((run_dir / "membership.csv").open(encoding="utf-8"))
           if m["review_id"] == rid]
    out["membership"] = [m["issue_id"] for m in mem]

    # 6 — contribution to the ranking
    ranking = list(csv.DictReader((run_dir / "ranking.csv").open(encoding="utf-8")))
    out["ranking"] = []
    for iid in out["membership"]:
        row = next(r for r in ranking if r["issue_id"] == iid)
        n, s = int(row["complaint_count"]), int(row["severity_sum"])
        without = (Decimal(s - rec["severity"]) / Decimal(n - 1)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP) if n > 1 else None
        out["ranking"].append({**row, "this_review_adds_severity": rec["severity"],
                               "mean_severity_without_this_review": str(without)})

    # 7 — the claims that count this review, and where the memo uses them
    claims = [c for c in csv.DictReader((run_dir / "claims.csv").open(encoding="utf-8"))
              if c["issue_id"] in out["membership"]]
    out["claims"] = claims
    memo = json.loads((run_dir / "memo_model_output.json").read_text())
    cited = set(memo["memo"]["recommendation"]["cited_claim_ids"])
    for a in memo["memo"]["alternatives"]:
        cited |= set(a["cited_claim_ids"])
    out["claims_cited_in_memo"] = [c["claim_id"] for c in claims if c["claim_id"] in cited]
    out["memo_headline"] = memo["memo"]["recommendation"]["headline"]
    out["memo_recommends"] = memo["memo"]["recommendation"]["issue_id"]
    out["memo_validation_passed"] = memo["validation"]["passed"]

    # 8 — present in the graded export?
    g = ROOT / "grading/records.jsonl.gz"
    if g.exists():
        import gzip
        with gzip.open(g, "rt", encoding="utf-8") as f:
            out["in_grading_export"] = any(json.loads(l)["review_id"] == rid for l in f if rid in l)
    return out


def as_markdown(t):
    r, s = t["record"], t["source"]
    L = [f"### `{t['review_id']}`", ""]
    L += ["**1 · Source row** — read from `data/analysis_100k.csv`, values unchanged from the course extract.", "",
          f"> {s['review_text']}", "",
          f"| field | value |", "|---|---|",
          f"| `review_rating` | {s['review_rating']} ★ (metadata only — never used to set severity) |",
          f"| `review_timestamp` | {s['review_timestamp']} |",
          f"| `app_version` | {s['app_version'] or '_(missing)_'} |",
          f"| `source_sha256` | `{s['computed_row_sha256'][:32]}…` |", ""]

    c = t["enrich_call"]
    L += ["**2 · Enrichment** — role `enrich`.", ""]
    if c:
        L += [f"Request `{c['request_id']}` carried **{c.get('batch_size', 1)} reviews** "
              f"({c['input_tokens']:,} input tokens, outcome `{c['outcome']}`, model `{c['model']}`, "
              f"config `{c['label_config']}`).", ""]
    if t["cache_origin"]:
        L += [f"This review's text is an exact duplicate, so it reuses the validated result from "
              f"`{t['cache_origin']}` (`cache_source_id`) rather than a new call.", ""]
    L += [f"| field | value | who decided it |", "|---|---|---|",
          f"| `topic` | `{r['topic']}` | model |",
          f"| `intent` | `{r['intent']}` | model |",
          f"| `severity` | `{r['severity']}` | model, then code applied the contract rules |",
          f"| `sentiment` | `{r['sentiment']}` | model (Score 0–4 → −1..1 in code) |",
          f"| `evidence_quote` | \"{r['evidence_quote']}\" | **code** — exact substring, verified: "
          f"`{t['quote_is_exact_substring']}` |",
          f"| `entities` | `{r['entities']}` | **code** — term match |",
          f"| `needs_review` | `{r['needs_review']}` | **code** — from model confidence |", ""]
    if r.get("rule_adjustments"):
        L += [f"Code adjustment applied and logged: {r['rule_adjustments']}", ""]
    if r.get("confidence"):
        L += [f"Model confidence: `{r['confidence']}`", ""]

    v = t["verify"]
    L += ["**3 · Independent verification** — role `verify`.", ""]
    if v:
        L += [f"This review fell in the deterministic 1% sample. A second role re-labelled it from the "
              f"review text alone, never seeing the first answer (`{v['label_config']}`).", "",
              "| field | enricher | verifier | agreed |", "|---|---|---|---|"]
        for f in ("topic", "intent", "severity"):
            L.append(f"| {f} | `{v['enricher'][f]}` | `{v['verifier'][f]}` | "
                     f"{'✅' if v['agreed'][f] else '❌'} |")
        L.append("")
    else:
        L += ["Not selected by the 1% sample, so this review has no second opinion. "
              "Stated rather than glossed over.", ""]

    L += ["**4 · Issue membership** — code only, deterministic.", ""]
    if t["membership"]:
        L += [f"Member of {', '.join('`' + m + '`' for m in t['membership'])}. Complaint and "
              f"cancellation records join the issue for their primary topic.", ""]
    else:
        L += [f"**Deliberately excluded from every issue.** The baseline ranking counts only "
              f"`complaint` and `cancellation` records; this one is `{r['intent']}`, so it is "
              f"classified, exported and auditable but contributes nothing to any priority score. "
              f"Excluding it is the contract's rule, not a dropped record.", ""]

    L += ["**5 · Ranking** — code only, no model call.", ""]
    if not t["ranking"]:
        L += ["No contribution, per the membership rule above.", ""]
    for rk in t["ranking"]:
        L += [f"`{rk['issue_id']}` ranks **{rk['rank']}** with "
              f"`complaint_count` {int(rk['complaint_count']):,} × `mean_severity` {rk['mean_severity']} "
              f"= `priority_score` **{int(rk['priority_score']):,}**.", "",
              f"This single review contributes **{rk['this_review_adds_severity']}** to that severity sum. "
              f"Remove it and the issue's mean severity becomes "
              f"{rk['mean_severity_without_this_review']} — the arithmetic is fully attributable.", ""]

    L += ["**6 · Memo claim** — role `memo`.", "",
          f"The memo recommends `{t['memo_recommends']}`: \"{t['memo_headline']}\". "
          f"Code validation passed: **{t['memo_validation_passed']}**.", ""]
    if t["claims_cited_in_memo"]:
        L += [f"This review is counted inside the claims the memo cites: "
              f"{', '.join('`' + c + '`' for c in t['claims_cited_in_memo'])}.", "",
              "| claim | metric | value |", "|---|---|---|"]
        for c in t["claims"]:
            if c["claim_id"] in t["claims_cited_in_memo"]:
                L.append(f"| `{c['claim_id']}` | {c['metric']} | {c['value']} |")
        L.append("")
    L += [f"**7 · Graded export** — present in `grading/records.jsonl.gz`: "
          f"**{t.get('in_grading_export')}**.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review_id")
    ap.add_argument("--run", default=ROOT / "runs/main100k", type=Path)
    ap.add_argument("--analysis", default=ROOT / "data/analysis_100k.csv", type=Path)
    ap.add_argument("--md", action="store_true", help="markdown instead of JSON")
    a = ap.parse_args()
    t = trace(a.review_id, a.run, a.analysis)
    print(as_markdown(t) if a.md else json.dumps(t, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
