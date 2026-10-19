"""The orchestrator: runs all six stages on one input CSV, in order, under code control.

Code decides what runs next at every step. A model is consulted inside four stages (enrich, verify,
group naming, recommend) but never chooses the control flow, never sees another role's answer, and
never produces a number that reaches the memo. Each stage reads the previous stage's saved artifact
and writes its own, so any stage can be inspected or rerun on its own.

Stop conditions: a dry run stops after planning; a spend cap, fatal API error or interruption in
enrichment stops the run before any downstream stage, with all completed work saved.
"""

import time
from pathlib import Path

from .common import JsonlLog, write_json
from .enrich import run_enrich
from .exports import export_results, ingestion_report, run_summary
from . import rank as R


def run_pipeline(input_csv, out_dir, *, paid=False, max_spend=0.05, workers=1, batch_size=10,
                 verify_rate=0.01, cache_dir=None, scope_note=None, log=print):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir) if cache_dir else out_dir
    timing, t_all = {}, time.monotonic()
    scope_note = scope_note or f"{Path(input_csv).name}"

    def stage(name, fn):
        t0 = time.monotonic()
        res = fn()
        timing[name] = round(time.monotonic() - t0, 3)
        log(f"[pipeline] {name} done in {timing[name]}s")
        return res

    # 1 · ingest (code)
    ing = stage("ingest", lambda: ingestion_report(input_csv, out_dir / "ingestion_report.json"))

    # 2 · enrich (Jev + code)
    enr = stage("enrich", lambda: run_enrich(input_csv, out_dir, max_spend=max_spend,
                                             cache_path=cache_dir / "enrich_cache.jsonl",
                                             workers=workers, batch_size=batch_size, dry_run=not paid, log=log))
    if enr.get("dry_run"):
        log("[pipeline] dry run: stopping after planning. Add --paid to execute.")
        return {"dry_run": True, "ingest": ing, "enrich": enr}
    if enr.get("stop_reason"):
        log(f"[pipeline] STOPPED in enrich ({enr['stop_reason']}); completed work is saved. "
            f"Rerun the same command to resume.")
        return {"stopped": enr["stop_reason"], "ingest": ing, "enrich": enr, "timing": timing}

    # 3 · verify (Jev, separately worded, blind to the first answer + code comparison)
    from .verify import run_verify
    ver = stage("verify", lambda: run_verify(input_csv, out_dir, rate=verify_rate, max_spend=max_spend,
                                             cache_path=cache_dir / "verify_cache.jsonl", log=log))

    # 4-6 use the text model. A model/auth/network failure there stops the run cleanly: everything
    # upstream is already saved, and rerunning the same command resumes from the caches.
    import anthropic
    try:
        # 4 · group: membership in code, issue naming by Haiku from bounded examples
        from .group import run_group
        stage("group", lambda: (R.group(out_dir), run_group(out_dir, cache_path=cache_dir / "group_cache.jsonl", log=log)))

        # 5 · rank (code only) — also writes claims.csv for every ranked issue
        stage("rank", lambda: (R.rank(out_dir), R.memo(out_dir)))

        # 6 · recommend (Haiku reads only the ranked table + a bounded evidence pack; code validates)
        from .memo import run_memo
        memo = stage("recommend", lambda: run_memo(out_dir, scope_note=scope_note,
                                                    cache_path=cache_dir / "memo_cache.jsonl", log=log))
    except anthropic.APIError as e:
        reason = f"text-model stage failed: {type(e).__name__}: {getattr(e, 'message', e)}"
        log(f"[pipeline] STOPPED — {reason}. Enrichment and verification are saved; fix the cause and "
            f"rerun the same command to resume.")
        JsonlLog(out_dir / "run_log.jsonl").append({"stage": "pipeline", "stopped": reason, "timing": timing})
        return {"stopped": reason, "ingest": ing, "enrich": enr, "verify": ver, "timing": timing}

    # named result files + run summary
    stage("export", lambda: export_results(out_dir, out_dir / "results"))
    timing["end_to_end"] = round(time.monotonic() - t_all, 3)
    summ = run_summary(out_dir, out_dir / "run_summary.json",
                       extra={"stage_wall_clock_s": timing, "input": str(input_csv),
                              "memo_validation_passed": memo["validation"]["passed"]})
    JsonlLog(out_dir / "run_log.jsonl").append({"stage": "pipeline", "timing": timing,
                                                "memo_validation_passed": memo["validation"]["passed"]})
    log(f"[pipeline] complete in {timing['end_to_end']}s | cost ≈ ${summ['total_cost_usd_estimate']:.6f} | "
        f"memo validation {'passed' if memo['validation']['passed'] else 'FAILED'}")
    return {"ingest": ing, "enrich": enr, "verify": ver, "memo": memo, "timing": timing, "summary": summ}
