"""Pipeline entry point. Paid model calls only happen with an explicit --paid flag.

Run all six stages on any input CSV (ingest, enrich, verify, group, rank, recommend):
  python3 run.py pipeline --input data/cost_100.csv --out runs/demo               # dry run: plan + estimate
  python3 run.py pipeline --input data/cost_100.csv --out runs/demo --paid --max-spend 0.10

Regenerate the ranking from the committed grading export — no model, no database, no key:
  python3 run.py rank

Single stages and utilities:
  python3 run.py enrich   --input data/cost_100.csv --out runs/dev100 --paid --max-spend 0.05
  python3 run.py export   --run runs/main100k --out results
  python3 run.py snapshot --out runs/dev100 --to runs/dev100/checkpoint_before.json
  python3 run.py status   --out runs/dev100
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

    pl = sub.add_parser("pipeline", help="run all six stages on an input CSV (dry run unless --paid)")
    pl.add_argument("--input", required=True, type=Path)
    pl.add_argument("--out", required=True, type=Path)
    pl.add_argument("--paid", action="store_true", help="actually call the APIs (costs money)")
    pl.add_argument("--max-spend", type=float, default=0.05, help="per-stage USD cap (default 0.05)")
    pl.add_argument("--workers", type=int, default=1)
    pl.add_argument("--batch-size", type=int, default=10, help="reviews per request (max 10)")
    pl.add_argument("--verify-rate", type=float, default=0.01, help="declared verification sample fraction")
    pl.add_argument("--cache-dir", type=Path, help="result caches (default: the output folder)")
    pl.add_argument("--scope-note", help="one-line scope statement passed to the memo role")

    rk = sub.add_parser("rank", help="regenerate the ranking from saved outputs (no model calls)")
    rk.add_argument("--records", type=Path, default=Path("grading/records.jsonl.gz"))
    rk.add_argument("--membership", type=Path, default=Path("grading/membership.csv"))
    rk.add_argument("--saved", type=Path, default=Path("grading/ranking.csv"))
    rk.add_argument("--write", type=Path, help="also write the regenerated ranking to this path")

    ex = sub.add_parser("export", help="write the named result files from a run folder")
    ex.add_argument("--run", required=True, type=Path)
    ex.add_argument("--out", required=True, type=Path)

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
    if a.cmd == "pipeline":
        load_env()
        from pipeline.orchestrator import run_pipeline
        res = run_pipeline(a.input, a.out, paid=a.paid, max_spend=a.max_spend, workers=a.workers,
                           batch_size=a.batch_size, verify_rate=a.verify_rate, cache_dir=a.cache_dir,
                           scope_note=a.scope_note)
        if res.get("stopped"):
            sys.exit(2)
    elif a.cmd == "rank":
        from pipeline.rank import rerank_from_export
        rows, same = rerank_from_export(a.records, a.membership, a.saved if a.saved.exists() else None, a.write)
        print(f"{'rank':>4}  {'issue_id':16} {'complaints':>10} {'sev_sum':>8} {'mean_sev':>10} {'priority':>9}")
        for r in rows:
            print(f"{r['rank']:>4}  {r['issue_id']:16} {r['complaint_count']:>10} {r['severity_sum']:>8} "
                  f"{r['mean_severity']:>10} {r['priority_score']:>9}")
        if same is not None:
            print(f"\nidentical to {a.saved}: {same}")
            if not same:
                sys.exit(1)
    elif a.cmd == "export":
        from pipeline.exports import export_results, run_summary
        print(json.dumps(export_results(a.run, a.out), indent=2))
        run_summary(a.run, a.out / "run_summary.json")
        print(f"wrote {a.out}/")
    elif a.cmd == "enrich":
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
