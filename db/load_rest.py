"""Load the seed CSVs into Supabase over HTTPS (PostgREST), for networks that block port 5432.

  python3 db/load_rest.py                 # needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY in .env
  python3 db/load_rest.py --truncate      # clear the tables first (safe: all rows are rebuildable)

Identical result to db/load_db.py, which uses COPY over a direct Postgres connection. Use that one
where port 5432 is reachable; this is the fallback. Standard library only.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import load_env  # noqa: E402

BATCH = 1000

# column -> converter. Anything unlisted stays a string; "" becomes null everywhere.
INT = lambda v: int(v)                                     # noqa: E731
FLT = lambda v: float(v)                                   # noqa: E731
BOOL = lambda v: v.lower() == "true"                       # noqa: E731
ARR = lambda v: _pg_array_to_list(v)                       # noqa: E731

TYPES = {
    "pipeline_run": {"source_rows": INT, "analysis_rows": INT, "completed": INT, "quarantined": INT,
                     "distinct_texts": INT, "cache_reuse_records": INT, "enrich_requests": INT,
                     "batch_size": INT, "workers": INT, "api_cost_usd": FLT, "wall_clock_s": FLT},
    "review_record": {"severity": INT, "sentiment": FLT, "needs_review": BOOL, "review_rating": INT},
    "membership": {},
    "issue": {},
    "ranking": {"rank": INT, "complaint_count": INT, "severity_sum": INT, "mean_severity": FLT,
                "priority_score": INT},
    "claim": {},
    "monthly_topic": {"complaints": INT, "reviews": INT, "partial": BOOL},
    "eval_metric": {"sample_size": INT},
    "memo": {"cited_claim_ids": ARR, "cited_review_ids": ARR, "limitations": ARR,
             "validation_problems": ARR, "validation_passed": BOOL, "input_tokens": INT,
             "output_tokens": INT, "cost_usd": FLT},
    "memo_alternative": {"cited_claim_ids": ARR, "memo_id": INT},
}
ORDER = ["pipeline_run", "review_record", "issue", "membership", "ranking", "claim",
         "monthly_topic", "eval_metric", "memo", "memo_alternative"]


def _pg_array_to_list(v):
    """Parse the {"a","b"} literal written by load_db.build_seed back into a JSON list."""
    if not v or v == "{}":
        return []
    out, cur, in_q, esc = [], "", False, False
    for ch in v[1:-1]:
        if esc:
            cur += ch; esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            in_q = not in_q
        elif ch == "," and not in_q:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x for x in out if x != ""]


def request(method, url, key, body=None, extra_headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
        **(extra_headers or {})})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"\n{method} {url.split('?')[0]} failed: HTTP {e.code}\n{detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"\nnetwork error on {url.split('?')[0]}: {e}")


def rows_of(table, seed_dir):
    path = seed_dir / f"{table}.csv"
    conv = TYPES[table]
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out = {}
            for k, v in row.items():
                if v == "":
                    out[k] = [] if conv.get(k) is ARR else None
                else:
                    out[k] = conv[k](v) if k in conv else v
            yield out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-dir", default=ROOT / "db/seed", type=Path)
    ap.add_argument("--truncate", action="store_true")
    a = ap.parse_args()
    load_env()
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env "
                 "(Supabase: Project Settings -> API Keys -> service_role).")
    rest = f"{base}/rest/v1"

    if a.truncate:
        for table in reversed(ORDER):
            request("DELETE", f"{rest}/{table}?{primary_filter(table)}", key)
            print(f"  cleared {table}")

    for table in ORDER:
        if table == "memo_alternative":
            memo = request("GET", f"{rest}/memo?select=id&order=id.desc&limit=1", key)
            memo_id = memo[0]["id"] if memo else None
            if memo_id is None:
                print("  ! no memo row; skipping memo_alternative")
                continue
        batch, sent, t0 = [], 0, time.monotonic()
        for row in rows_of(table, a.seed_dir):
            if table == "memo_alternative":
                row["memo_id"] = memo_id
            batch.append(row)
            if len(batch) >= BATCH:
                request("POST", f"{rest}/{table}", key, batch, {"Prefer": "return=minimal"})
                sent += len(batch); batch = []
                print(f"\r  {table}: {sent:,} rows", end="", flush=True)
        if batch:
            request("POST", f"{rest}/{table}", key, batch, {"Prefer": "return=minimal"})
            sent += len(batch)
        print(f"\r  {table}: {sent:,} rows in {time.monotonic() - t0:.1f}s")
    print("done")


def primary_filter(table):
    """PostgREST requires a filter on DELETE; match every row via its primary key column."""
    col = {"pipeline_run": "run_id", "review_record": "review_id", "issue": "issue_id",
           "membership": "issue_id", "ranking": "issue_id", "claim": "claim_id",
           "monthly_topic": "month", "eval_metric": "name", "memo": "id",
           "memo_alternative": "id"}[table]
    return f"{col}=not.is.null"


if __name__ == "__main__":
    main()
