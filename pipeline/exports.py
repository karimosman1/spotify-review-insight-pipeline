"""Stage 1 ingestion report, and the named result files (assignment "Save Your Results").

Code only. Everything here is derived from saved artifacts, so it can be regenerated offline.
"""

import csv
import gzip
import json
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .common import file_sha, read_jsonl, read_source_rows, text_sha, write_json, write_jsonl


def ingestion_report(input_csv, out_path):
    """Full-file profile of whatever CSV the pipeline was given: identity, counts, missingness,
    duplicates, date and rating mix. Filters may organise work but never remove required rows."""
    rows = list(read_source_rows(input_csv))
    ids = Counter(r["review_id"] for r in rows)
    texts = [r["review_text"] for r in rows if r["review_text"].strip()]
    ts = sorted(r["review_timestamp"] for r in rows if r["review_timestamp"])
    rep = {
        "input": str(input_csv), "input_sha256": file_sha(input_csv), "rows": len(rows),
        "duplicate_review_ids": sum(n - 1 for n in ids.values() if n > 1),
        "empty_review_text": len(rows) - len(texts),
        "missing_app_version": sum(1 for r in rows if not r["app_version"]),
        "nonempty_to_classify": len(texts),
        "distinct_nonempty_texts": len({text_sha(t) for t in texts}),
        "first_review": ts[0] if ts else None, "last_review": ts[-1] if ts else None,
        "reviews_by_month": dict(sorted(Counter(t[:7] for t in ts).items())),
        "reviews_by_rating": dict(sorted(Counter(r["review_rating"] for r in rows).items())),
        "note": ("Every row is carried forward: nonempty rows are classified, empty rows are quarantined "
                 "with reason empty_review_text. Missing app_version alone does not block classification."),
    }
    write_json(out_path, rep)
    return rep


def mean6(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def export_results(run_dir, out_dir, records=None):
    """Write the named result files. `records` defaults to the run's results.jsonl."""
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if records is None:
        from .enrich import latest_records
        records = latest_records(run_dir)

    # enriched: predictions joined with the preserved source values, one row per completed ID
    cols = ["review_id", "status", "topic", "intent", "severity", "sentiment", "needs_review",
            "evidence_quote", "entities", "cache_source_id", "label_config", "source_sha256",
            "review_rating", "review_likes", "app_version", "review_timestamp"]
    with gzip.open(out_dir / "enriched.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in sorted(records.values(), key=lambda r: r["review_id"]):
            if r["status"] == "completed":
                w.writerow({**r, "entities": ";".join(r.get("entities", []))})

    # quarantine log: unresolved records with reason and attempts
    q = [{"review_id": r["review_id"], "source_sha256": r["source_sha256"], "reason": r.get("reason"),
          "attempts": r.get("attempts", 0), "run_id": r.get("run_id")}
         for r in records.values() if r["status"] == "quarantined"]
    write_jsonl(out_dir / "quarantine.jsonl", sorted(q, key=lambda r: r["review_id"]))

    # issues: stable ids, accepted names, member counts
    names = {}
    if (run_dir / "issues.json").exists():
        names = json.loads((run_dir / "issues.json").read_text())["issues"]
    membership = list(csv.DictReader((run_dir / "membership.csv").open(encoding="utf-8")))
    members = Counter(m["issue_id"] for m in membership)
    with (out_dir / "issues.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "topic", "label", "description", "member_count"])
        for iid in sorted(members):
            n = names.get(iid, {})
            w.writerow([iid, iid.replace("ISS-", ""), n.get("label", ""), n.get("description", ""), members[iid]])

    # aggregates: per issue, the counts behind the score plus the intent and review-flag split
    by = {}
    for m in membership:
        r = records[m["review_id"]]
        a = by.setdefault(m["issue_id"], Counter())
        a["complaint_count"] += 1
        a["severity_sum"] += r["severity"]
        a[f"intent_{r['intent']}"] += 1
        a["needs_review"] += bool(r.get("needs_review"))
        a[f"severity_{r['severity']}"] += 1
    with (out_dir / "aggregates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["issue_id", "complaint_count", "severity_sum", "mean_severity", "complaint_records",
                    "cancellation_records", "severity_4_or_5", "needs_review"])
        for iid in sorted(by):
            a = by[iid]
            w.writerow([iid, a["complaint_count"], a["severity_sum"], mean6(a["severity_sum"], a["complaint_count"]),
                        a["intent_complaint"], a["intent_cancellation"], a["severity_4"] + a["severity_5"],
                        a["needs_review"]])
    return {"enriched": sum(r["status"] == "completed" for r in records.values()), "quarantined": len(q),
            "issues": len(members)}


def run_summary(run_dir, out_path, extra=None):
    """Stage timing, statuses, attempts, failures, usage and charges for one run, from its logs."""
    run_dir = Path(run_dir)
    calls = read_jsonl(run_dir / "calls.jsonl")
    by_role = {}
    for c in calls:
        r = by_role.setdefault(c.get("role", "?"), Counter())
        r["attempts"] += 1
        r[f"outcome_{c.get('outcome')}"] += 1
        r["input_tokens"] += c.get("input_tokens") or 0
        r["output_tokens"] += c.get("output_tokens") or 0
        r["cost_usd_estimate_x1e9"] += int(round((c.get("cost_usd_estimate") or 0) * 1e9))
        r["usage_unknown"] += c.get("usage_known") is False
    roles = {k: {**{kk: vv for kk, vv in v.items() if kk != "cost_usd_estimate_x1e9"},
                 "cost_usd_estimate": v["cost_usd_estimate_x1e9"] / 1e9} for k, v in by_role.items()}
    logs = read_jsonl(run_dir / "run_log.jsonl")
    summary = {"run_dir": str(run_dir), "stages": logs, "calls_by_role": roles,
               "total_cost_usd_estimate": round(sum(v["cost_usd_estimate"] for v in roles.values()), 8),
               "cost_basis": "logged provider usage x rates in cost/rates.csv; provider billing is authoritative",
               **(extra or {})}
    for name in ("verify_report.json", "downstream_summary.json", "issues.json", "memo_model_output.json"):
        p = run_dir / name
        if p.exists():
            d = json.loads(p.read_text())
            summary[name.replace(".json", "")] = (
                {k: d[k] for k in ("compared", "agreement", "sample_rate", "stats") if k in d}
                if name == "verify_report.json" else
                {k: d[k] for k in ("validation", "usage", "cost_usd", "cache_hit", "label_config") if k in d}
                if name in ("issues.json", "memo_model_output.json") else d)
    write_json(out_path, summary)
    return summary
