"""Golden-50 evaluation: model predictions vs. your hand labels.

  python3 evals/golden_eval.py --labels data/golden_50_labeled.csv            # compare (uses saved predictions)
  python3 evals/golden_eval.py --labels data/golden_50_labeled.csv --paid     # first time: also run the enricher

Predictions are produced from data/golden_50_to_label.csv (the unlabeled file), and the enricher only
reads the six source columns, so human labels can never reach the model. The labels file is read here,
after predictions exist, purely for comparison.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import labels as L  # noqa: E402
from pipeline.common import load_env, write_json  # noqa: E402
from pipeline.enrich import latest_records, run_enrich  # noqa: E402

UNLABELED = ROOT / "data/golden_50_to_label.csv"
RUN_DIR = ROOT / "runs/golden50"
OUT = ROOT / "evals"


def accepted(h, field):
    vals = [h[field]]
    if h.get("ambiguous") == "true" and h.get("alt_" + field):
        vals.append(h["alt_" + field])
    return [int(v) for v in vals] if field == "severity" else vals


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--labels", required=True, type=Path)
    p.add_argument("--paid", action="store_true")
    p.add_argument("--max-spend", type=float, default=0.02)
    p.add_argument("--run-dir", type=Path, default=RUN_DIR, help="where predictions live")
    a = p.parse_args()

    if a.paid:
        load_env()
        run_enrich(UNLABELED, a.run_dir, max_spend=a.max_spend, cache_path=a.run_dir / "cache.jsonl")
    preds = latest_records(a.run_dir)
    if not preds:
        sys.exit("No predictions yet: rerun with --paid (about $0.004).")

    human = list(csv.DictReader(a.labels.open(encoding="utf-8")))
    labeled = [h for h in human if h["topic"] and h["intent"] and h["severity"]]
    tot, cases = Counter(), []
    conf = {f: Counter() for f in ("topic", "intent")}
    sev_err, sent_err = [], []
    for h in labeled:
        rid = h["review_id"]
        pr = preds.get(rid, {})
        ok_pred = pr.get("status") == "completed"
        res = {"review_id": rid, "text": h["review_text"][:160], "ambiguous": h.get("ambiguous") == "true",
               "notes": h.get("notes", "")}
        for f in ("topic", "intent", "severity"):
            acc = accepted(h, f)
            got = pr.get(f) if ok_pred else None
            res[f"human_{f}"], res[f"model_{f}"] = "|".join(map(str, acc)), got
            res[f"{f}_ok"] = got in acc
            tot[f] += res[f"{f}_ok"]
        for f in ("topic", "intent"):
            conf[f][(h[f], pr.get(f, "<none>"))] += 1
        if ok_pred:
            sev_err.append(min(abs(pr["severity"] - s) for s in accepted(h, "severity")))
            if h.get("sentiment") not in (None, ""):
                sent_err.append(abs(pr["sentiment"] - float(h["sentiment"])))
            res["quote_is_substring"] = pr["evidence_quote"] in h["review_text"]
            res["model_needs_review"] = pr["needs_review"]
            tot["quote_ok"] += res["quote_is_substring"]
        else:
            tot["missing"] += 1
        res["all_ok"] = all(res[f"{f}_ok"] for f in ("topic", "intent", "severity"))
        tot["joint"] += res["all_ok"]
        cases.append(res)

    n = len(labeled)
    amb = [c for c in cases if c["ambiguous"]]
    flagged = [c for c in cases if c.get("model_needs_review")]
    configs = sorted({p["label_config"] for p in preds.values() if p.get("label_config")})
    summary = {
        # read back from the predictions themselves, so this can never claim a config that did not
        # produce these numbers
        "label_config": configs[0] if len(configs) == 1 else configs,
        "predictions_from": str(a.run_dir), "human_labeled": n, "of_total": len(human),
        "missing_or_quarantined_predictions": tot["missing"],
        "agreement": {f: round(tot[f] / n, 4) for f in ("topic", "intent", "severity", "joint")} if n else {},
        "severity_mae": round(sum(sev_err) / len(sev_err), 4) if sev_err else None,
        "sentiment_mae": round(sum(sent_err) / len(sent_err), 4) if sent_err else None,
        "sentiment_within_0.5": round(sum(e <= 0.5 for e in sent_err) / len(sent_err), 4) if sent_err else None,
        "quote_exact_substring_rate": round(tot["quote_ok"] / max(1, n - tot["missing"]), 4),
        "ambiguous_cases": len(amb),
        "needs_review_as_predictor": {
            "flagged": len(flagged),
            "flagged_and_wrong": sum(not c["all_ok"] for c in flagged),
            "wrong_total": sum(not c["all_ok"] for c in cases)},
        "note": "50 cases is a small diagnostic sample, not a population accuracy estimate. Ambiguous cases accept the recorded alternative label.",
    }
    write_json(OUT / "golden_results.json", {"summary": summary, "cases": cases,
                                             "confusion": {f: [[k[0], k[1], v] for k, v in sorted(c.items())] for f, c in conf.items()}})
    with (OUT / "golden_cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0]) if cases else ["review_id"])
        w.writeheader(); w.writerows(cases)

    md = ["# Golden-50 evaluation", "", "```json", json.dumps(summary, indent=2), "```", "",
          "## Topic confusion (rows = human, cols = model)", ""]
    labs = list(L.TOPICS)
    md.append("| human \\ model | " + " | ".join(labs) + " |")
    md.append("|---" * (len(labs) + 1) + "|")
    for t in labs:
        md.append(f"| {t} | " + " | ".join(str(conf['topic'].get((t, m), 0) or "") for m in labs) + " |")
    md += ["", "## Disagreements (fill in the 'why' column during error analysis)", "",
           "| review_id | text | human topic/intent/sev | model topic/intent/sev | why |", "|---|---|---|---|---|"]
    for c in cases:
        if not c["all_ok"]:
            md.append(f"| {c['review_id'][:8]} | {c['text'].replace('|', '/').replace(chr(10), ' ')[:90]} | "
                      f"{c['human_topic']}/{c['human_intent']}/{c['human_severity']} | "
                      f"{c['model_topic']}/{c['model_intent']}/{c['model_severity']} | |")
    (OUT / "golden_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote evals/golden_report.md, golden_results.json, golden_cases.csv")


if __name__ == "__main__":
    main()
