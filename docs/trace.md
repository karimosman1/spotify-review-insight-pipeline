# One review, end to end — and one that went wrong

Both traces below are **generated from saved artifacts**, not written by hand:

```bash
python3 tools/trace_review.py <review_id> --md
```

No model call, no database, no credentials. Re-run it on any of the 100,013 review IDs and you get
the same chain, because every step reads back out of the files in `runs/main100k/` and `grading/`.

---

## Case A — a clean record, source text to published claim

This review is a member of the top-ranked issue and fell inside the 1% verification sample, so the
chain runs unbroken through all six stages.

### `4c5dee86-808d-4414-932e-d01feeb8a64e`

**1 · Source row** — read from `data/analysis_100k.csv`, values unchanged from the course extract.

> Not able to select previous song. Not able to slide to skip music.

| field | value |
|---|---|
| `review_rating` | 1 ★ (metadata only — never used to set severity) |
| `review_timestamp` | 2023-10-10 20:44:32 |
| `app_version` | 8.8.76.667 |
| `source_sha256` | `cf0583b9f2d9733d53863c804c2ece97…` |

**2 · Enrichment** — role `enrich`.

Request `local-8759eec34f86-v1-a1` carried **10 reviews** (6,990 input tokens, outcome `succeeded`, model `jev-1.13.0`, config `jev-1.13.0+enrich-b1+schema-v1`).

| field | value | who decided it |
|---|---|---|
| `topic` | `usability` | model |
| `intent` | `complaint` | model |
| `severity` | `4` | model, then code applied the contract rules |
| `sentiment` | `-0.715` | model (Score 0–4 → −1..1 in code) |
| `evidence_quote` | "Not able to select previous song. Not able to slide to skip music." | **code** — exact substring, verified: `True` |
| `entities` | `['skip']` | **code** — term match |
| `needs_review` | `False` | **code** — from model confidence |

Model confidence: `{'intent': 1.0, 'severity': 0.76, 'topic': 0.91}`

**3 · Independent verification** — role `verify`.

This review fell in the deterministic 1% sample. A second role re-labelled it from the review text alone, never seeing the first answer (`jev-1.13.0+verify-p1+schema-v1`).

| field | enricher | verifier | agreed |
|---|---|---|---|
| topic | `usability` | `usability` | ✅ |
| intent | `complaint` | `complaint` | ✅ |
| severity | `4` | `4` | ✅ |

**4 · Issue membership** — code only, deterministic.

Member of `ISS-usability`. Complaint and cancellation records join the issue for their primary topic.

**5 · Ranking** — code only, no model call.

`ISS-usability` ranks **1** with `complaint_count` 12,408 × `mean_severity` 2.606383 = `priority_score` **32,340**.

This single review contributes **4** to that severity sum. Remove it and the issue's mean severity becomes 2.606271 — the arithmetic is fully attributable.

**6 · Memo claim** — role `memo`.

The memo recommends `ISS-usability`: "Address usability and ad experience as top priority". Code validation passed: **True**.

This review is counted inside the claims the memo cites: `C1`, `C2`, `C3`.

| claim | metric | value |
|---|---|---|
| `C1` | complaint_count | 12408 |
| `C2` | mean_severity | 2.606383 |
| `C3` | priority_score | 32340 |

**7 · Graded export** — present in `grading/records.jsonl.gz`: **True**.

**What this demonstrates.** The star rating is 1, but severity 4 comes from the reported impact —
two core playback controls unusable — not from the stars, exactly as the shared definitions require.
The quote was cut by code and machine-checked as an exact substring. An independent second role
reached the same three labels without seeing the first answer. The contribution to the ranking is
arithmetic anyone can redo: remove this one review and the issue's mean severity moves from
2.606383 to 2.606271.

---

## Case B — an ambiguous record the system flagged itself

### `02bbd57e-a230-43b6-8fc8-4855a7ee2ae2`

**1 · Source row** — read from `data/analysis_100k.csv`, values unchanged from the course extract.

> Please ban this app bycottswedon

| field | value |
|---|---|
| `review_rating` | 1 ★ (metadata only — never used to set severity) |
| `review_timestamp` | 2023-07-08 07:47:19 |
| `app_version` | _(missing)_ |
| `source_sha256` | `f6c8800e4061c1aa33915a1cbebfb141…` |

**2 · Enrichment** — role `enrich`.

Request `local-a8aee5d3c6be-v1-a1` carried **10 reviews** (6,700 input tokens, outcome `succeeded`, model `jev-1.13.0`, config `jev-1.13.0+enrich-b1+schema-v1`).

| field | value | who decided it |
|---|---|---|
| `topic` | `other` | model |
| `intent` | `unclear` | model |
| `severity` | `1` | model, then code applied the contract rules |
| `sentiment` | `-0.985` | model (Score 0–4 → −1..1 in code) |
| `evidence_quote` | "Please ban this app bycottswedon" | **code** — exact substring, verified: `True` |
| `entities` | `[]` | **code** — term match |
| `needs_review` | `True` | **code** — from model confidence |

Model confidence: `{'intent': 0.44, 'severity': 0.87, 'topic': 1.0}`

**3 · Independent verification** — role `verify`.

This review fell in the deterministic 1% sample. A second role re-labelled it from the review text alone, never seeing the first answer (`jev-1.13.0+verify-p1+schema-v1`).

| field | enricher | verifier | agreed |
|---|---|---|---|
| topic | `other` | `other` | ✅ |
| intent | `unclear` | `request` | ❌ |
| severity | `1` | `2` | ❌ |

**4 · Issue membership** — code only, deterministic.

**Deliberately excluded from every issue.** The baseline ranking counts only `complaint` and `cancellation` records; this one is `unclear`, so it is classified, exported and auditable but contributes nothing to any priority score. Excluding it is the contract's rule, not a dropped record.

**5 · Ranking** — code only, no model call.

No contribution, per the membership rule above.

**6 · Memo claim** — role `memo`.

The memo recommends `ISS-usability`: "Address usability and ad experience as top priority". Code validation passed: **True**.

**7 · Graded export** — present in `grading/records.jsonl.gz`: **True**.

### What went wrong here, and the handling decision

The text is a boycott slogan with a misspelling (`bycottswedon` for "boycott Sweden"). The contract
is explicit: *"Bare boycott slogans and unrelated/meaningless text are `unclear`, unless there is a
product complaint or explicit personal departure."* There is no product complaint here and the writer
never says they are leaving, so **`unclear` / severity 1 is correct** and both disagreeing answers are
wrong — the verifier's `request` (reading "Please ban this app" as a feature request) and its
severity 2.

Three independent signals converged on this record:

1. **The enricher's own confidence was low** — intent 0.44, under the 0.50 threshold — so code set
   `needs_review: true` without anyone looking at it.
2. **The verifier disagreed** on two of three fields.
3. **The same failure mode appeared in the golden set** on `8cc4fad4` ("I hate this app and sweden"),
   where the first prompt version also mishandled a boycott slogan.

**Decision: keep the label, keep the flag, change nothing silently.** The record stays `unclear`,
stays flagged, and is excluded from the ranking by the membership rule — so a wrong intent here could
not have moved any priority score. It is one of 10,575 records (10.6%) carrying `needs_review: true`,
which is the queue a human would work through next.

**What this cost in accuracy.** Boycott-slogan reviews are the clearest known weakness of
`enrich-b1`. They cluster in `topic: other`, which is already the mixed bucket, and they are
`unclear`, so they never enter the ranking. The exposure is therefore to the *descriptive* counts,
not to the priority ordering.

### Why the flag is worth having

Across the golden 50, `needs_review` was set on 6 records and 3 of those were wrong, against 12
wrong overall. So the flag concentrates errors — a flagged record is far more likely to be wrong
than an unflagged one — but it does not catch most of them. It is a triage signal for human review,
not a correctness guarantee, and the evaluation reports it as a prediction to be measured rather
than trusted.
