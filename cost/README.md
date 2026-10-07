# Cost & runtime calculator (100-review pilot)

| command | what it does | needs API key? | costs money? |
|---|---|---|---|
| `python3 cost/calculator.py` | **Offline replay (default).** Recomputes every cost from `usage.csv` × `rates.csv`, rebuilds projections from `pilot_measurements.json` + `settings.json`, and rewrites `report.md` | no | no |
| `python3 cost/calculator.py pilot` | **Paid pilot.** Runs the real pipeline on `data/cost_100.csv` with an empty result cache and 1 worker (cold), then again with the saved cache (warm), then replays | yes | yes (≈ $0.01, capped by `pilot_run_cap_usd`) |

To change prices or assumptions, edit `rates.csv` or `settings.json` and rerun replay. Settings include the spending limit, max workers, fallback fraction and the scenario rates.

## Files

- `report.md`: the measured cold/warm tables and the full-run projection, with budget warnings.
- `pilot_records.jsonl`: one final status per pilot ID, with row hash and labels.
- `pilot_calls.jsonl`: every attempt from both runs, including failures and retries, with tokens and timing.
- `usage.csv`: billed units per attempt; this is what replay multiplies by the rates.
- `rates.csv`: dated, editable prices with source links.
- `pilot_measurements.json`: wall-clock times, counts, cache hits and the input checksum.
- `pilot_verify_report.json`: the verifier's sample and its disagreements.

## Spending controls (code: `pipeline/jev.py`)

- **Per-run cap (`--max-spend`).** Before each request the code reserves a worst-case cost. The request is refused if spent + reserved + the next reservation exceeds the cap. The run then saves its work and stops.
- **Project-wide cap.** `state/ledger.json` (default $4.00) persists across runs and protects the $5 prepaid credit.
- **Provider-side cap.** The TypeSafe account is prepaid with auto-recharge off.
- **Bounded retries.**
  - Transport and 429/5xx errors: at most 3 attempts, with backoff and jitter.
  - Invalid model output: 1 retry, then quarantine.
  - 401/402/403/422: stop immediately.
- **Unknown outcomes.** If a call times out, its full reservation is counted as spent.
