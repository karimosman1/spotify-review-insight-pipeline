"""Load the saved pipeline artifacts into Postgres for the dashboard.

  python3 db/load_db.py --run runs/main100k            # needs DATABASE_URL in .env
  python3 db/load_db.py --run runs/main100k --dry-run  # write db/seed/*.csv only, no connection

Every row comes from a saved artifact; nothing is recomputed differently here. Running it again is
idempotent: it recreates the schema and reloads from the same files.
"""

import argparse
import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import load_env, read_jsonl  # noqa: E402
from pipeline.enrich import latest_records  # noqa: E402

TOPIC_LABELS = {
    "access": ("Account access", "Login, signup, password and account access failures"),
    "usability": ("Usability and ads", "Navigation, controls, queue/playlist handling, ad interruptions"),
    "playback": ("Playback reliability", "Playback failures, crashes, lag, connection errors, audio quality"),
    "downloads": ("Downloads and offline", "Downloading, saved music, offline listening"),
    "catalog": ("Catalog and discovery", "Missing songs/artists, search, recommendations, lyrics availability"),
    "billing": ("Billing and entitlement", "Price, charges, subscriptions, paywalls, premium entitlement"),
    "support": ("Customer support", "Contacting support and the support response"),
    "other": ("Unspecified / general", "General praise or criticism with no specific feature; mixed bucket"),
}


def build_seed(run_dir, out_dir):
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    recs = latest_records(run_dir)
    manifest = json.loads((ROOT / "data/analysis_manifest.json").read_text())
    summary = [json.loads(l) for l in (run_dir / "run_log.jsonl").open()][-1]
    memo_out = json.loads((run_dir / "memo_model_output.json").read_text())

    def w(name, header, rows):
        with (out_dir / name).open("w", newline="", encoding="utf-8") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            cw.writerows(rows)
        return len(rows)

    run_id = summary["run_id"]
    completed = [r for r in recs.values() if r["status"] == "completed"]
    quarantined = [r for r in recs.values() if r["status"] == "quarantined"]

    w("pipeline_run.csv",
      ["run_id", "scope", "source_file", "source_sha256", "analysis_sha256", "source_rows", "analysis_rows",
       "completed", "quarantined", "distinct_texts", "cache_reuse_records", "enrich_requests", "batch_size",
       "workers", "label_config", "api_cost_usd", "wall_clock_s"],
      [[run_id, "analysis_100k", Path(manifest["source_file"]).name, manifest["source_sha256"],
        manifest["analysis_sha256"], manifest["source_rows"], manifest["analysis_rows"],
        len(completed), len(quarantined), manifest["distinct_nonempty_texts"],
        summary["cache_hit_records"] + sum(1 for r in completed if r.get("cache_source_id")),
        summary["requests"], summary["batch_size"], summary["workers"], summary["label_config"],
        f"{summary['run_spent_usd']:.6f}", f"{summary['wall_clock_s']:.3f}"]])

    w("review_record.csv",
      ["review_id", "run_id", "status", "reason", "topic", "intent", "severity", "sentiment",
       "evidence_quote", "needs_review", "cache_source_id", "review_rating", "app_version", "review_ts",
       "label_config"],
      [[r["review_id"], run_id, r["status"], r.get("reason", ""), r.get("topic", ""), r.get("intent", ""),
        r.get("severity", ""), r.get("sentiment", ""), r.get("evidence_quote", ""),
        "true" if r.get("needs_review") else "false", r.get("cache_source_id", ""),
        r.get("review_rating", ""), r.get("app_version", ""), r.get("review_timestamp", ""),
        r.get("label_config", "")] for r in recs.values()])

    topics_used = sorted({r["topic"] for r in completed})
    w("issue.csv", ["issue_id", "topic", "label", "description"],
      [[f"ISS-{t}", t, TOPIC_LABELS[t][0], TOPIC_LABELS[t][1]] for t in topics_used])

    membership = list(csv.DictReader((run_dir / "membership.csv").open(encoding="utf-8")))
    w("membership.csv", ["issue_id", "review_id"], [[m["issue_id"], m["review_id"]] for m in membership])

    ranking = list(csv.DictReader((run_dir / "ranking.csv").open(encoding="utf-8")))
    w("ranking.csv", ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"],
      [[r["rank"], r["issue_id"], r["complaint_count"], r["severity_sum"], r["mean_severity"],
        r["priority_score"]] for r in ranking])

    claims = list(csv.DictReader((run_dir / "claims.csv").open(encoding="utf-8")))
    w("claim.csv", ["claim_id", "issue_id", "metric", "value"],
      [[c["claim_id"], c["issue_id"], c["metric"], c["value"]] for c in claims])

    # monthly complaint share with denominators; edge months are partial
    months = sorted({r["review_timestamp"][:7] for r in completed if r.get("review_timestamp")})
    per = defaultdict(Counter)
    totals = Counter()
    for r in completed:
        m = r.get("review_timestamp", "")[:7]
        if not m:
            continue
        totals[m] += 1
        if r["intent"] in ("complaint", "cancellation"):
            per[m][r["topic"]] += 1
    edge = {months[0], months[-1]} if months else set()
    w("monthly_topic.csv", ["month", "topic", "complaints", "reviews", "partial"],
      [[m, t, per[m][t], totals[m], "true" if m in edge else "false"]
       for m in months for t in topics_used])

    # memo + alternatives
    mm = memo_out["memo"]
    v = memo_out["validation"]
    w("memo.csv",
      ["run_id", "model", "label_config", "headline", "issue_id", "rationale", "cited_claim_ids",
       "cited_review_ids", "limitations", "validation_passed", "validation_problems",
       "input_tokens", "output_tokens", "cost_usd"],
      [[run_id, memo_out["model"], memo_out["label_config"], mm["recommendation"]["headline"],
        mm["recommendation"]["issue_id"], mm["recommendation"]["rationale"],
        pg_array(mm["recommendation"]["cited_claim_ids"]), pg_array(mm["recommendation"]["cited_review_ids"]),
        pg_array(mm["limitations"]), "true" if v["passed"] else "false", pg_array(v["problems"]),
        memo_out["usage"]["input_tokens"], memo_out["usage"]["output_tokens"], memo_out["cost_usd"]]])
    w("memo_alternative.csv", ["issue_id", "case_for", "why_not_first", "cited_claim_ids"],
      [[a["issue_id"], a["case_for"], a["why_not_first"], pg_array(a["cited_claim_ids"])]
       for a in mm["alternatives"]])

    # evaluation evidence
    metrics = []
    ev = ROOT / "evals/golden_results.json"
    if ev.exists():
        g = json.loads(ev.read_text())["summary"]
        metrics += [
            ("golden_topic_agreement", f"{g['agreement']['topic']:.4f}", g["human_labeled"], "vs 50 hand labels (v2)"),
            ("golden_intent_agreement", f"{g['agreement']['intent']:.4f}", g["human_labeled"], "vs 50 hand labels (v2)"),
            ("golden_severity_agreement", f"{g['agreement']['severity']:.4f}", g["human_labeled"], "exact match"),
            ("golden_severity_mae", f"{g['severity_mae']:.4f}", g["human_labeled"], "mean absolute error"),
        ]
    vr = run_dir / "verify_report.json"
    if vr.exists():
        j = json.loads(vr.read_text())
        for f in ("topic", "intent", "severity"):
            metrics.append((f"verifier_{f}_agreement", f"{j['agreement'][f]:.4f}", j["compared"],
                            "independent second model role, random 1% sample"))
    metrics.append(("needs_review_flagged", str(sum(1 for r in completed if r.get("needs_review"))),
                    len(completed), "low-confidence records flagged for human review"))
    w("eval_metric.csv", ["name", "value", "sample_size", "detail"], [list(m) for m in metrics])
    return out_dir


def pg_array(values):
    """Postgres array literal for COPY: {"a","b"}"""
    return "{" + ",".join('"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"' for v in values) + "}"


def load(seed_dir, database_url):
    import psycopg
    seed_dir = Path(seed_dir)
    order = [("pipeline_run", None), ("review_record", None), ("issue", None), ("membership", None),
             ("ranking", None), ("claim", None), ("monthly_topic", None), ("eval_metric", None)]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Hosted Postgres (Supabase) caps statement duration, which cancels a multi-minute COPY
            # part-way through. Lift it for this session only; it reverts when the connection closes.
            cur.execute("SET statement_timeout = 0")
            cur.execute("SET idle_in_transaction_session_timeout = 0")
            cur.execute((ROOT / "db/schema.sql").read_text())
            conn.commit()
            for table, _ in order:
                path = seed_dir / f"{table}.csv"
                with path.open(encoding="utf-8") as f:
                    header = f.readline().strip()
                    cols = ",".join(header.split(","))
                    with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
                        for chunk in iter(lambda: f.read(1 << 20), ""):
                            cp.write(chunk)
                conn.commit()   # per table, so a later failure keeps the work already done
                print(f"  loaded {table}")
            # memo needs its serial id for alternatives
            with (seed_dir / "memo.csv").open(encoding="utf-8") as f:
                header = f.readline().strip()
                with cur.copy(f"COPY memo ({header}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
                    cp.write(f.read())
            cur.execute("SELECT id FROM memo ORDER BY id DESC LIMIT 1")
            memo_id = cur.fetchone()[0]
            alts = list(csv.DictReader((seed_dir / "memo_alternative.csv").open(encoding="utf-8")))
            buf = io.StringIO()
            cw = csv.writer(buf)
            for a in alts:
                cw.writerow([memo_id, a["issue_id"], a["case_for"], a["why_not_first"], a["cited_claim_ids"]])
            with cur.copy("COPY memo_alternative (memo_id, issue_id, case_for, why_not_first, cited_claim_ids) "
                          "FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
                cp.write(buf.getvalue())
            print(f"  loaded memo (+{len(alts)} alternatives)")
            cur.execute("ANALYZE")
        conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="runs/main100k", type=Path)
    ap.add_argument("--seed-dir", default=ROOT / "db/seed", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="write seed CSVs only")
    a = ap.parse_args()
    load_env()
    out = build_seed(a.run, a.seed_dir)
    sizes = {p.name: p.stat().st_size for p in sorted(out.glob("*.csv"))}
    print(f"seed written to {out}:")
    for k, v in sizes.items():
        print(f"  {k:26} {v / 1024:9.1f} KB")
    if a.dry_run:
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set in .env (add the Neon connection string), or use --dry-run")
    print("loading into Postgres...")
    load(out, url)
    print("done")


if __name__ == "__main__":
    main()
