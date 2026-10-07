"""Build the required grading/ folder from saved artifacts (no model calls).

  python3 tools/export_grading.py --run runs/main100k

Produces run.json, records.jsonl, membership.csv, ranking.csv, claims.csv, calls.jsonl and the two
checkpoint snapshots in the exact shapes GRADING_CONTRACT.md specifies. ingestion.json is produced
separately by the official helper (see README).
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import read_jsonl, write_json, write_jsonl  # noqa: E402
from pipeline.enrich import latest_records  # noqa: E402

VERSION = "a5-audit-v1"
RECORD_KEYS = ("review_id", "source_sha256", "status", "topic", "intent", "sentiment", "severity",
               "entities", "evidence_quote", "needs_review", "label_config", "cache_source_id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=ROOT / "runs/main100k", type=Path)
    ap.add_argument("--out", default=ROOT / "grading", type=Path)
    a = ap.parse_args()
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "data/analysis_manifest.json").read_text())

    # ---- run.json: declared scope. analysis_* describe the file we actually classified.
    write_json(out / "run.json", {
        "version": VERSION,
        "analysis_count": manifest["analysis_rows"],
        "analysis_sha256": manifest["analysis_sha256"],
        "classification_input_fields": ["review_text"],
        "allow_multi_issue": False,
    })

    # ---- records.jsonl: exactly one final record per source ID in the analysis file
    recs = latest_records(a.run)
    rows = []
    for rid in sorted(recs):
        r = recs[rid]
        if r["status"] == "quarantined":
            rows.append({"review_id": rid, "source_sha256": r["source_sha256"],
                         "status": "quarantined", "reason": r["reason"]})
        else:
            rows.append({k: r[k] for k in RECORD_KEYS if k in r})
    write_jsonl(out / "records.jsonl", rows)

    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copy(a.run / name, out / name)

    # ---- calls.jsonl: contract fields only, every attempt from every stage
    keep = ("request_id", "role", "review_ids", "model", "phase", "outcome", "label_config",
            "input_tokens", "output_tokens")
    calls = []
    for src in (a.run / "calls.jsonl", ROOT / "runs/resume_demo/calls.jsonl"):
        if not src.exists():
            continue
        for c in read_jsonl(src):
            if c.get("outcome") == "invalid_output":
                c = {**c, "outcome": "failed"}
            row = {k: c.get(k) for k in keep}
            row["phase"] = row["phase"] or "initial"
            row["review_ids"] = row["review_ids"] or []
            # Request ids must be unique across the whole export. Locally synthesized ids are keyed
            # by text chunk, so the same chunk seen in two runs would collide: qualify them by run.
            rid = row.get("request_id") or ""
            if rid.startswith(("local-", "validation-")) and c.get("run_id") and c["run_id"] not in rid:
                row["request_id"] = f"{c['run_id']}:{rid}"
            # The contract's schema requires integer usage. A call that never returned (timeout or
            # transport error) has no provider usage, so it exports 0 with usage_known:false rather
            # than an invented number; the project's own calls.jsonl keeps the raw null.
            for f in ("input_tokens", "output_tokens"):
                if not isinstance(row[f], int) or row[f] < 0:
                    row[f] = 0
                    row["usage_known"] = False
            calls.append(row)
    write_jsonl(out / "calls.jsonl", calls)

    # ---- checkpoints: copied from the interruption/resume demonstration
    for src, dst in (("checkpoint_before.json", "checkpoint_before.json"),
                     ("checkpoint_after.json", "checkpoint_after.json")):
        p = ROOT / "runs/resume_demo" / src
        if p.exists():
            shutil.copy(p, out / dst)
        else:
            print(f"  ! {dst} missing: run the interruption/resume demo first (tools/resume_demo.sh)")

    counts = {"records": len(rows),
              "completed": sum(r["status"] == "completed" for r in rows),
              "quarantined": sum(r["status"] == "quarantined" for r in rows),
              "calls": len(calls),
              "failed_calls": sum(c["outcome"] == "failed" for c in calls)}
    print(json.dumps(counts, indent=2))
    print(f"wrote {out}/")


if __name__ == "__main__":
    main()
