"""Build the declared analysis subset (assignment v2 allows "at least 100,000").

  python3 tools/make_analysis_set.py --full <path to spotify_reviews_18months.csv>

Rule (deterministic, documented, reproducible):
  * rank every NONEMPTY review by SHA-256(SEED + ':' + review_id) and take the lowest 100,000;
  * additionally include ALL empty-text rows from the full file, so the quarantine path is exercised
    and every empty text in the corpus is accounted for.

A uniform hash sample keeps the monthly and rating mix close to the full corpus, so complaint-share
trends stay meaningful. Source field values are written back unchanged, so each row's SHA-256 still
matches the full file (the grader's `reference --full ... --analysis ...` check depends on this).
"""

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.common import FIELDS, file_sha, write_json  # noqa: E402

SEED = "karim-a5-100k-v1"
TARGET_NONEMPTY = 100_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "data/analysis_100k.csv")
    ap.add_argument("--target", type=int, default=TARGET_NONEMPTY)
    a = ap.parse_args()

    csv.field_size_limit(10 ** 9)
    rows = []
    with a.full.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        for r in reader:
            rows.append({k: r[k] for k in FIELDS})
    print(f"read {len(rows):,} source rows")

    empty = [r for r in rows if not r["review_text"].strip()]
    nonempty = [r for r in rows if r["review_text"].strip()]
    nonempty.sort(key=lambda r: hashlib.sha256(f"{SEED}:{r['review_id']}".encode()).hexdigest())
    picked = nonempty[:a.target]
    chosen_ids = {r["review_id"] for r in picked} | {r["review_id"] for r in empty}
    selected = [r for r in rows if r["review_id"] in chosen_ids]  # keep original source order

    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(FIELDS), lineterminator="\n")
        w.writeheader()
        w.writerows(selected)

    texts = [r["review_text"] for r in picked]
    months = Counter(r["review_timestamp"][:7] for r in selected)
    full_months = Counter(r["review_timestamp"][:7] for r in rows)
    dev = max(abs(months[m] / len(selected) - full_months[m] / len(rows)) for m in full_months)
    ratings = Counter(r["review_rating"] for r in selected)
    meta = {
        "seed": SEED, "rule": "lowest SHA-256(seed:review_id) among nonempty rows, plus all empty-text rows",
        "source_file": str(a.full), "source_sha256": file_sha(a.full), "source_rows": len(rows),
        "analysis_file": a.out.name, "analysis_sha256": file_sha(a.out), "analysis_rows": len(selected),
        "nonempty_to_classify": len(picked), "empty_quarantines": len(empty),
        "distinct_nonempty_texts": len(set(texts)),
        "exact_text_reuse_fraction": round(1 - len(set(texts)) / len(texts), 6),
        "monthly_share_max_deviation_pp": round(dev * 100, 4),
        "reviews_by_month": dict(sorted(months.items())), "reviews_by_rating": dict(sorted(ratings.items())),
        "coverage_note": ("Assignment v2 requires at least 100,000 reviews. The grader's coverage formula still "
                          "divides by 660,622/660,609, so this declared scope earns a proportional coverage score; "
                          "this is disclosed in the README."),
    }
    write_json(ROOT / "data/analysis_manifest.json", meta)
    print(f"wrote {a.out}: {len(selected):,} rows ({len(picked):,} nonempty + {len(empty)} empty)")
    print(f"distinct nonempty texts {meta['distinct_nonempty_texts']:,} "
          f"(reuse {meta['exact_text_reuse_fraction'] * 100:.1f}%) | monthly deviation {meta['monthly_share_max_deviation_pp']} pp")
    print(f"analysis_sha256 {meta['analysis_sha256']}")


if __name__ == "__main__":
    main()
