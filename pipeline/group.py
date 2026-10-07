"""Stage 4b: the grouping role (role `group`).

Membership stays deterministic in code (pipeline/rank.py): every complaint/cancellation record joins
the issue for its topic, so ranking never needs a model. This role does the one part that genuinely
needs language judgment: naming and describing each issue from a bounded pack of example quotes.

Code validates that the model returns exactly the issue IDs it was given, invents no new ones, and
changes no membership. The accepted mapping is saved to issues.json.
"""

import json
import time
from pathlib import Path

import anthropic

from .common import JsonlLog, write_json
from .enrich import latest_records

GROUP_MODEL = "claude-haiku-4-5"
GROUP_PROMPT_VERSION = "group-p1"
GROUP_LABEL_CONFIG = f"{GROUP_MODEL}+{GROUP_PROMPT_VERSION}"
EXAMPLES_PER_ISSUE = 6
MAX_QUOTE = 160

SYSTEM = """You name product issues for a review-analysis dashboard.

For each issue_id you are given, write:
  - label: a short noun phrase, 2-4 words, in plain product language (e.g. "Playback reliability")
  - description: one sentence describing what reviewers in this group actually complain about,
    grounded only in the example quotes shown.

Rules:
- Return exactly the issue_ids you were given. Never invent, merge, split or drop one.
- Do not restate the topic name alone; describe the observed complaints.
- Claim no counts, numbers, causes or customer facts. Descriptions are qualitative only."""


def run_group(out_dir, log=print):
    out_dir = Path(out_dir)
    recs = latest_records(out_dir)
    calls = JsonlLog(out_dir / "calls.jsonl")

    issues = {}
    for r in recs.values():
        if r["status"] == "completed" and r["intent"] in ("complaint", "cancellation"):
            issues.setdefault(f"ISS-{r['topic']}", []).append(r)
    pack = {}
    for iid, members in sorted(issues.items()):
        members.sort(key=lambda r: (-r["severity"], r["review_id"]))
        step = max(1, len(members) // EXAMPLES_PER_ISSUE)
        sampled = members[::step][:EXAMPLES_PER_ISSUE]      # spread across the severity range
        pack[iid] = {"topic": iid.replace("ISS-", ""), "member_count": len(members),
                     "example_quotes": [m["evidence_quote"][:MAX_QUOTE] for m in sampled]}

    schema = {
        "type": "object",
        "properties": {"issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"issue_id": {"type": "string"}, "label": {"type": "string"},
                           "description": {"type": "string"}},
            "required": ["issue_id", "label", "description"], "additionalProperties": False}}},
        "required": ["issues"], "additionalProperties": False,
    }

    client = anthropic.Anthropic()
    t0 = time.monotonic()
    resp = client.messages.create(
        model=GROUP_MODEL, max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content":
                   "Name and describe these issues.\n\n" + json.dumps(pack, indent=2)}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    duration = time.monotonic() - t0
    u = resp.usage
    cost = u.input_tokens * 1.0e-6 + u.output_tokens * 5.0e-6
    calls.append({"run_id": f"group-{time.strftime('%Y%m%dT%H%M%S')}", "role": "group", "phase": "initial",
                  "review_ids": [], "model": GROUP_MODEL, "label_config": GROUP_LABEL_CONFIG,
                  "request_id": resp._request_id, "outcome": "succeeded", "attempt": 1,
                  "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "usage_known": True,
                  "cost_usd_estimate": round(cost, 8), "duration_s": round(duration, 3),
                  "consumed_artifacts": ["results.jsonl (bounded example quotes only)"]})

    proposed = json.loads(next(b.text for b in resp.content if b.type == "text"))["issues"]
    got = {p["issue_id"] for p in proposed}
    problems = []
    if got != set(pack):
        problems.append(f"model returned issue ids {sorted(got)} but was given {sorted(pack)}")
    accepted = {}
    for p in proposed:
        if p["issue_id"] not in pack:
            problems.append(f"invented issue id {p['issue_id']} (rejected)")
            continue
        accepted[p["issue_id"]] = {"label": p["label"].strip(), "description": p["description"].strip(),
                                   "topic": pack[p["issue_id"]]["topic"],
                                   "member_count": pack[p["issue_id"]]["member_count"]}
    for iid in pack:                                   # never leave an issue unnamed
        if iid not in accepted:
            accepted[iid] = {"label": pack[iid]["topic"].title(), "description": "",
                             "topic": pack[iid]["topic"], "member_count": pack[iid]["member_count"]}
            problems.append(f"{iid} missing from model output; fell back to the topic name")

    write_json(out_dir / "issues.json", {
        "grouping_rule": "one issue per primary topic; membership assigned in code, never by the model",
        "naming_model": GROUP_MODEL, "label_config": GROUP_LABEL_CONFIG,
        "validation": {"passed": not problems, "problems": problems},
        "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
        "cost_usd": round(cost, 8), "issues": accepted})
    log(f"[group] named {len(accepted)} issues with {GROUP_MODEL} | ${cost:.5f} | "
        f"{'validated' if not problems else 'PROBLEMS: ' + '; '.join(problems)}")
    return accepted
