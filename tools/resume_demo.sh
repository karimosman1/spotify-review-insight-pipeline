#!/usr/bin/env bash
# Interruption and resume demonstration (GRADING_CONTRACT.md "Execution").
#
#   bash tools/resume_demo.sh
#
# The input is a 500-row slice of data/analysis_100k.csv, so every logged review ID is inside the
# declared analysis scope that the grading checker validates against.
#
# Phase 1 runs with --max-new-requests so the run stops mid-way after saving completed batches.
# A checkpoint of completed IDs is snapshotted. Phase 2 resumes against the SAME output folder and
# cache: already-completed IDs are skipped with no new enrichment calls for them, and only the
# remaining work is paid for. The second checkpoint is a strict superset of the first.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=runs/resume_demo
INPUT=data/resume_slice_500.csv
rm -rf "$OUT"

echo "=== PHASE 1: initial run, interrupted after 20 requests ==="
python3 run.py enrich --input "$INPUT" --out "$OUT" --paid --max-spend 0.05 \
  --workers 4 --batch-size 10 --phase initial --max-new-requests 20 || true
python3 run.py snapshot --out "$OUT" --to "$OUT/checkpoint_before.json"

echo
echo "=== PHASE 2: resume, same output folder and cache ==="
python3 run.py enrich --input "$INPUT" --out "$OUT" --paid --max-spend 0.05 \
  --workers 4 --batch-size 10 --phase resume
python3 run.py snapshot --out "$OUT" --to "$OUT/checkpoint_after.json"

echo
echo "=== VERIFY ==="
python3 - <<'PY'
import json, sys
sys.path.insert(0, ".")
from pipeline.common import read_jsonl

before = set(json.load(open("runs/resume_demo/checkpoint_before.json"))["completed_ids"])
after = set(json.load(open("runs/resume_demo/checkpoint_after.json"))["completed_ids"])
calls = read_jsonl("runs/resume_demo/calls.jsonl")
initial = [c for c in calls if c.get("phase") == "initial" and c.get("outcome") == "succeeded"]
resume = [c for c in calls if c.get("phase") == "resume" and c.get("outcome") == "succeeded"]
resent = {r for c in resume for r in c.get("review_ids", [])} & before

print(f"completed before interruption : {len(before)}")
print(f"completed after resume        : {len(after)}")
print(f"new records completed on resume: {len(after - before)}")
print(f"successful calls  initial/resume: {len(initial)}/{len(resume)}")
print(f"already-completed IDs re-sent to the model on resume: {len(resent)}  <- must be 0")
assert before and before < after, "checkpoint_after must be a strict superset of checkpoint_before"
assert not resent, "resume must not pay to relabel completed IDs"
print("\nPASS: work was saved, interrupted, and resumed without repaying for completed IDs.")
PY
