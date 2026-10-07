"""Pipeline entry point. Paid model calls only happen with an explicit --paid flag.

Examples:
  python3 run.py enrich --input data/cost_100.csv --out runs/dev100              # dry run: estimate only
  python3 run.py enrich --input data/cost_100.csv --out runs/dev100 --paid --max-spend 0.05
  python3 run.py snapshot --out runs/dev100 --to runs/dev100/checkpoint_before.json
  python3 run.py status --out runs/dev100
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pipeline.common import load_env, write_json
from pipeline.enrich import latest_records, run_enrich


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enrich", help="classify every row of an input CSV (dry run unless --paid)")
    e.add_argument("--input", required=True, type=Path)
    e.add_argument("--out", required=True, type=Path)
    e.add_argument("--cache", type=Path, help="result cache (default: <out>/cache.jsonl)")
    e.add_argument("--paid", action="store_true", help="actually call the API (costs money)")
    e.add_argument("--max-spend", type=float, default=0.05, help="per-run USD cap (default 0.05)")
    e.add_argument("--workers", type=int, default=1)
    e.add_argument("--batch-size", type=int, default=10, help="reviews per request (max 10)")
    e.add_argument("--phase", choices=["initial", "resume"], default="initial")
    e.add_argument("--max-new-requests", type=int, help="stop after N requests (interruption demo)")

    s = sub.add_parser("snapshot", help="save completed_ids checkpoint")
    s.add_argument("--out", required=True, type=Path)
    s.add_argument("--to", required=True, type=Path)

    st = sub.add_parser("status", help="count statuses/labels in a run folder")
    st.add_argument("--out", required=True, type=Path)

    a = p.parse_args()
    if a.cmd == "enrich":
        load_env()
        summary = run_enrich(a.input, a.out, max_spend=a.max_spend, cache_path=a.cache or a.out / "cache.jsonl",
                             phase=a.phase, workers=a.workers, batch_size=a.batch_size,
                             max_new_requests=a.max_new_requests,
                             dry_run=not a.paid)
        print(json.dumps(summary, indent=2))
        if summary.get("stop_reason"):
            sys.exit(2)
    elif a.cmd == "snapshot":
        recs = latest_records(a.out)
        ids = sorted(r for r, v in recs.items() if v["status"] == "completed")
        write_json(a.to, {"completed_ids": ids, "count": len(ids)})
        print(f"{len(ids)} completed IDs -> {a.to}")
    elif a.cmd == "status":
        recs = latest_records(a.out).values()
        print("status:", dict(Counter(r["status"] for r in recs)))
        done = [r for r in recs if r["status"] == "completed"]
        for f in ("topic", "intent", "severity"):
            print(f"{f}:", dict(Counter(r[f] for r in done).most_common()))
        print("needs_review:", sum(r["needs_review"] for r in done), "| cache reuse:",
              sum("cache_source_id" in r or r.get("cache_hit", False) for r in done))


if __name__ == "__main__":
    main()
