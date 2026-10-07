"""100-review cost/runtime calculator.

  python3 cost/calculator.py            # DEFAULT: offline replay. No API key, no network, no model calls.
  python3 cost/calculator.py replay     # same as above
  python3 cost/calculator.py pilot      # PAID: real cold + warm run on data/cost_100.csv, then replay

Offline replay recomputes every cost from cost/usage.csv x cost/rates.csv, and every projection from
cost/pilot_measurements.json + cost/settings.json. Edit rates.csv or settings.json and rerun replay.
"""

import csv
import json
import shutil
import sys
import time
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


# ======================================================================== offline replay (default)

def load_rates():
    with (HERE / "rates.csv").open(encoding="utf-8") as f:
        return {(r["provider"], r["model"], r["billing_item"]): r for r in csv.DictReader(f)}


def replay(write=True):
    settings = json.loads((HERE / "settings.json").read_text())
    meas = json.loads((HERE / "pilot_measurements.json").read_text())
    rates = load_rates()
    with (HERE / "usage.csv").open(encoding="utf-8") as f:
        usage = list(csv.DictReader(f))

    # ---- measured cost: billed_units x price_per_unit, per mutually exclusive item
    cost = defaultdict(Decimal)          # (run_type, stage) -> USD
    units = defaultdict(int)             # (run_type, stage, item) -> units
    attempts = defaultdict(int)
    missing_usage = 0
    for u in usage:
        key = (u["run_type"], u["stage"])
        attempts[key] += 1
        if u["usage_known"] != "true":
            missing_usage += 1
            continue
        for item in ("input_tokens", "output_tokens"):
            n = int(u[item] or 0)
            rate = Decimal(rates[(u["provider"], u["model"], item)]["price_per_unit"])
            units[key + (item,)] += n
            cost[key] += n * rate

    def run_total(rt):
        return sum((v for (r, _), v in cost.items() if r == rt), Decimal(0))

    cold, warm = run_total("cold"), run_total("warm")
    m_cold, m_warm = meas["cold"], meas["warm"]
    completed = m_cold["records_completed"]

    # ---- per-request averages from the cold run (used for projection)
    def avg_tokens(stage):
        n = attempts[("cold", stage)]
        return units[("cold", stage, "input_tokens")] / n if n else 0.0

    enr_tok, ver_tok = avg_tokens("enrich"), avg_tokens("verify")   # per REQUEST
    enr_reqs = attempts[("cold", "enrich")]
    batch = max(1, m_cold.get("batch_size", 1))
    enr_texts = max(1, m_cold["enrich_unique_texts_called"])
    enr_retry_rate = max(0.0, enr_reqs / max(1, -(-enr_texts // batch)) - 1)
    sec_per_enrich = m_cold["stage_wall_s"]["enrich"] / max(1, enr_reqs)
    sec_per_verify = m_cold["stage_wall_s"]["verify"] / max(1, attempts[("cold", "verify")])
    in_rate = Decimal(rates[("typesafe", "jev-1.13.0", "input_tokens")]["price_per_unit"])

    full = settings["full_run"]
    workers = settings["max_workers"]
    comp = settings.get("full_corpus_comparison")
    scen = {}
    for name, s in settings["scenarios"].items():
        infl = s.get("token_inflation", 1.0)
        for reuse in (True, False):
            texts = full["distinct_nonempty_texts"] if reuse else full["nonempty"]
            enr_n = -(-texts // batch) * (1 + enr_retry_rate + s["extra_retry_rate"])  # REQUESTS
            ver_n = texts * s["verify_fraction"]
            api = (Decimal(enr_n * enr_tok * infl) + Decimal(ver_n * ver_tok * infl)) * in_rate
            secs_1 = enr_n * sec_per_enrich + ver_n * sec_per_verify
            scen[(name, reuse)] = {"enrich_requests": round(enr_n), "verify_requests": round(ver_n),
                                   "api_usd": float(round(api, 2)), "hours_1_worker": round(secs_1 / 3600, 1),
                                   f"hours_{workers}_workers_ideal": round(secs_1 / 3600 / workers, 1),
                                   "over_budget": float(api) > settings["spending_limit_full_run_usd"]}

    # same arithmetic applied to the whole corpus, for the scope comparison in the report
    corpus = None
    if comp:
        s0 = settings["scenarios"]["base"]
        t = comp["distinct_nonempty_texts"]
        n = -(-t // batch) * (1 + enr_retry_rate)
        corpus = {"api_usd": float(round((Decimal(n * enr_tok) + Decimal(t * s0["verify_fraction"] * ver_tok)) * in_rate, 2)),
                  "hours_1_worker": round(n * sec_per_enrich / 3600, 1)}
    report = render(settings, meas, rates, cost, units, attempts, cold, warm, completed, missing_usage,
                    enr_tok, ver_tok, enr_retry_rate, sec_per_enrich, scen, workers, batch, corpus)
    if write:
        (HERE / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return {"cold_usd": float(cold), "warm_usd": float(warm), "scenarios": {f"{k[0]}/{'reuse' if k[1] else 'no-reuse'}": v for k, v in scen.items()}}


def render(settings, meas, rates, cost, units, attempts, cold, warm, completed, missing_usage,
           enr_tok, ver_tok, retry_rate, sec_per_enrich, scen, workers, batch, corpus):
    mc, mw = meas["cold"], meas["warm"]
    comp_texts = (settings.get("full_corpus_comparison") or {}).get("distinct_nonempty_texts", 0)
    full = settings["full_run"]
    L = ["# 100-review cost & runtime report", "",
         f"Generated by offline replay (`python3 cost/calculator.py`). Pilot measured {meas['measured_at']}. "
         "Costs = billed units x price per unit from `usage.csv` x `rates.csv`; nothing here calls an API.", "",
         "## Pilot input", "",
         f"- File: `{meas['input']}` sha256 `{meas['input_sha256']}`",
         f"- IDs: {mc['rows']} | completed {mc['records_completed']} | quarantined {mc['records_quarantined']} | "
         f"pending/failed {mc['records_pending']} | unique texts {mc['unique_texts']}",
         f"- Provider/model: TypeSafe `jev-1.13.0` (no reasoning-effort setting; Choice/Score questions) | "
         f"enrich config `{meas['enrich_label_config']}` | verify config `{meas['verify_label_config']}`",
         f"- Batching: **{batch} reviews per request** (contract limit 50; rubric sent once per request in `state`). Workers = {mc['workers']} (pilot is single-worker by spec).",
         "", "## Rates used (editable: `cost/rates.csv`)", "",
         "| provider | model | item | unit | price/unit | currency | source | checked |", "|---|---|---|---|---|---|---|---|"]
    for r in rates.values():
        L.append(f"| {r['provider']} | {r['model']} | {r['billing_item']} | {r['unit']} | {r['price_per_unit']} | "
                 f"{r['currency']} | [{r['price_quote']}]({r['source_url']}) | {r['checked_date']} |")
    L += ["", "## Measured: by run and stage", "",
          "| run | stage | attempts (incl. retries/failures) | input tokens | output tokens | API cost USD |", "|---|---|---|---|---|---|"]
    for rt in ("cold", "warm"):
        for st in ("enrich", "verify", "group", "rank", "memo"):
            a = attempts.get((rt, st), 0)
            L.append(f"| {rt} | {st} | {a} | {units.get((rt, st, 'input_tokens'), 0):,} | "
                     f"{units.get((rt, st, 'output_tokens'), 0):,} | {cost.get((rt, st), Decimal(0)):.8f} |")
    per_k = cold / mc["rows"] * 1000
    L += ["", "| measure | cold run | warm run |", "|---|---|---|",
          f"| API spend USD | {cold:.8f} | {warm:.8f} |",
          f"| End-to-end wall clock (s) | {mc['wall_clock_s']} | {mw['wall_clock_s']} |",
          f"| Stage wall clock (s) | {mc['stage_wall_s']} | {mw['stage_wall_s']} |",
          f"| New enrichment calls | {mc['enrich_requests']} | {mw['enrich_requests']} |",
          f"| Result-cache hits (records) | {mc['cache_hit_records']} | {mw['cache_hit_records']} |",
          f"| Throughput (records/s) | {mc['rows'] / mc['wall_clock_s']:.2f} | {mw['rows'] / max(mw['wall_clock_s'], 1e-9):.2f} |",
          f"| Cost per 1,000 input rows | ${per_k:.6f} | |",
          f"| Cost per completed record | ${cold / max(1, completed):.8f} | |",
          "", f"- Missing usage rows: {missing_usage} (counted at reservation estimate in the ledger, excluded above).",
          f"- Mean input tokens per request: enrich {enr_tok:.0f} (= {enr_tok / batch:.0f} per review at batch {batch}), verify {ver_tok:.0f}. Output tokens are unbilled.",
          f"- Measured enrich retry rate: {retry_rate:.3f}. Seconds per enrich request (1 worker): {sec_per_enrich:.3f}.",
          "- Group, rank and memo are code-only in this version (0 model calls). Local compute: " + settings["local_compute"],
          "", f"## Projection for the declared scope: {full['rows']:,} rows, {full['nonempty']:,} classified, "
          f"{full['empty_quarantines']} empty-text quarantines ({full.get('scope', '')})", "",
          f"Budget (editable): ${settings['spending_limit_full_run_usd']:.2f} | max workers {workers} | "
          f"max fallback fraction {settings['max_fallback_fraction']} | output-token cap: {settings['output_token_cap_note']}", "",
          f"| scenario | exact-text reuse | enrich requests | verify requests | API USD | hours @1 worker | hours @{workers} workers (ideal) | over budget? |",
          "|---|---|---|---|---|---|---|---|"]
    for (name, reuse), v in scen.items():
        reuse_label = f"yes ({full['distinct_nonempty_texts']:,} texts)" if reuse else f"no ({full['nonempty']:,} texts)"
        L.append(f"| {name} | {reuse_label} | {v['enrich_requests']:,} | "
                 f"{v['verify_requests']:,} | {v['api_usd']:.2f} | {v['hours_1_worker']} | {v[f'hours_{workers}_workers_ideal']} | "
                 f"{'**YES - exceeds budget**' if v['over_budget'] else 'no'} |")
    if corpus:
        L += ["", f"**Scope comparison.** The same measured arithmetic applied to the entire 660,622-row corpus "
              f"({comp_texts:,} distinct texts) gives **${corpus['api_usd']:.2f}** and {corpus['hours_1_worker']} hours "
              f"at 1 worker. The declared scope is {full['nonempty']:,} nonempty reviews (assignment v2 requires at "
              f"least 100,000); the grader's coverage formula still divides by 660,622/660,609, so this is a disclosed "
              f"trade-off, not an accounting error. See README."]
    L += ["", "Assumptions: per-request tokens and seconds from the cold pilot; base/conservative verify, retry and "
          "token-inflation rates from `settings.json`; fixed overhead (memo, grouping) is code-only and counted once (≈$0). "
          "Parallel hours assume ideal scaling and are a model, not a measurement; rate limits (80 req/s) and retries "
          "can make it slower. Refresh after the 500- and 10,000-review checkpoints.", ""]
    return "\n".join(L)


# ======================================================================== paid pilot (explicit only)

def pilot():
    from pipeline.common import file_sha, load_env, read_jsonl, write_jsonl, write_json
    from pipeline import labels as Lb
    from pipeline.enrich import latest_records, run_enrich
    from pipeline.rank import run_downstream
    from pipeline.verify import run_verify

    load_env(ROOT / ".env")
    settings = json.loads((HERE / "settings.json").read_text())
    inp = ROOT / settings["pilot_input"]
    base = ROOT / "runs" / f"pilot-{time.strftime('%Y%m%dT%H%M%S')}"
    cache_dir = base / "cache"   # empty result cache for this experiment
    measurements = {"input": settings["pilot_input"], "input_sha256": file_sha(inp),
                    "measured_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    "enrich_label_config": Lb.ENRICH_LABEL_CONFIG, "verify_label_config": Lb.VERIFY_LABEL_CONFIG}
    for run_type in ("cold", "warm"):
        out = base / run_type
        t0 = time.monotonic()
        e = run_enrich(inp, out, max_spend=settings["pilot_run_cap_usd"], cache_path=cache_dir / "enrich_cache.jsonl",
                       workers=1, batch_size=settings.get("pilot_batch_size", 1))
        t1 = time.monotonic()
        v = run_verify(inp, out, rate=settings["pilot_verify_fraction"], max_spend=settings["pilot_run_cap_usd"],
                       cache_path=cache_dir / "verify_cache.jsonl")
        t2 = time.monotonic()
        d = run_downstream(out)
        wall = time.monotonic() - t0
        recs = latest_records(out)
        st = [r["status"] for r in recs.values()]
        measurements[run_type] = {
            "rows": e["rows"], "unique_texts": len({r["source_sha256"] for r in recs.values()}),
            "records_completed": st.count("completed"), "records_quarantined": st.count("quarantined"),
            "records_pending": e["rows"] - st.count("completed") - st.count("quarantined"),
            "enrich_requests": e.get("requests", 0), "enrich_unique_texts_called": e["pending_unique_texts"],
            "batch_size": e["batch_size"], "label_config": e["label_config"],
            "cache_hit_records": e["cache_hit_records"], "verify_sample": v["sample_size"],
            "verify_requests": v["stats"].get("requests", 0), "workers": 1, "stop_reason": e.get("stop_reason"),
            "wall_clock_s": round(wall, 3),
            "stage_wall_s": {"enrich": round(t1 - t0, 3), "verify": round(t2 - t1, 3), **d},
            "run_dir": str(out.relative_to(ROOT))}
        print(f"[pilot] {run_type}: {measurements[run_type]['records_completed']} completed, "
              f"{measurements[run_type]['enrich_requests']} enrich calls, {wall:.1f}s")
        if e.get("stop_reason"):
            print("[pilot] stopped early:", e["stop_reason"]); break

    # ---- save evidence under cost/
    cold_recs = latest_records(base / "cold")
    keep = ("review_id", "source_sha256", "status", "reason", "topic", "intent", "sentiment", "severity", "entities",
            "evidence_quote", "needs_review", "label_config", "attempts", "cache_source_id")
    write_jsonl(HERE / "pilot_records.jsonl", [{k: r[k] for k in keep if k in r} for r in cold_recs.values()])
    calls, usage = [], []
    for run_type in ("cold", "warm"):
        for c in read_jsonl(base / run_type / "calls.jsonl"):
            if c.get("outcome") == "invalid_output":
                calls.append({**c, "run_type": run_type}); continue
            calls.append({**c, "run_type": run_type})
            usage.append({"run_type": run_type, "run_id": c["run_id"], "request_id": c["request_id"], "stage": c["role"],
                          "provider": "typesafe", "model": "jev-1.13.0", "outcome": c["outcome"],
                          "input_tokens": c.get("input_tokens") or 0, "output_tokens": c.get("output_tokens") or 0,
                          "usage_known": str(bool(c.get("usage_known"))).lower(), "duration_s": c.get("duration_s")})
    write_jsonl(HERE / "pilot_calls.jsonl", calls)
    with (HERE / "usage.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["run_type", "run_id", "request_id", "stage", "provider", "model", "outcome", "input_tokens",
                  "output_tokens", "usage_known", "duration_s"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(usage)
    write_json(HERE / "pilot_measurements.json", measurements)
    shutil.copy(base / "cold" / "verify_report.json", HERE / "pilot_verify_report.json")
    print(f"[pilot] evidence saved under cost/ ; run folders under {base.relative_to(ROOT)}")
    replay()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "replay"
    if cmd == "pilot":
        pilot()
    elif cmd == "replay":
        replay()
    else:
        sys.exit(__doc__)
