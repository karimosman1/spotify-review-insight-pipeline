# Priority memo: Address usability and ad experience as top priority

_Scope: 100,013 reviews sampled from 660,622 Spotify Google Play reviews (May 2022 - Nov 2023); 100,000 classified, 13 empty texts quarantined._

**Recommendation: ISS-usability**

Usability ranks first by priority score with C3: 32340, driven by C1: 12408 complaints at C2: 2.606383 mean severity. Volume dominates here: this catches the most users. Evidence shows ad frequency complaints (review 5e8201f3-0f71-44be-8eab-b8d9414496be, 08a1f178-3e7a-4d65-9da3-dee293dd0061) and app state loss (30b1d1c0-e1a1-437f-a5cd-e1327467bda4, 365c0fe6-e618-4c4a-9176-fbd48eb76d30) are recurring friction points affecting daily user engagement.

## Supporting numbers

| claim | issue | metric | value |
|---|---|---|---|
| C1 | ISS-usability | complaint_count | 12408 |
| C2 | ISS-usability | mean_severity | 2.606383 |
| C3 | ISS-usability | priority_score | 32340 |

## Representative reviews

- `5e8201f3-0f71-44be-8eab-b8d9414496be` (severity 5, complaint): "Startìng to irritate me when i see "enjoy 30 mins of uniterrupted listening after the video" then theres 3 ads after i counted 3 i came here im a daily almost hourly listener of spotify so whys it give me 3 to 5 ads afte"
- `08a1f178-3e7a-4d65-9da3-dee293dd0061` (severity 5, cancellation): "That wasn't the trigger me to give this a one star; it is ads."
- `30b1d1c0-e1a1-437f-a5cd-e1327467bda4` (severity 5, complaint): "Recent update lost everything, even my Play list is deleted"
- `365c0fe6-e618-4c4a-9176-fbd48eb76d30` (severity 5, complaint): "Isse bekaar app maine aaj tak nhi dekha jitni baar back kro utni Baar add aate hai . If you download this app you would lost your mb 🤣"

## Alternatives considered

**ISS-playback** — Playback issues have the highest mean severity at C8: 3.644176, signaling acute user frustration. C7: 6121 complaints yield C9: 22306 priority score. Evidence shows complete playback failures (0834a740-a550-4e67-b4ef-128a78940f6b) and app glitches (15d478e6-07df-436c-8c31-a0ab7a6b4e77) directly block core functionality. _Why not first:_ Lower complaint volume than usability and other. A high-severity, low-volume issue trades off against broader user impact: playback affects fewer reviewers but hits harder per incident. [C7, C8, C9]
**ISS-billing** — Billing issues have C11: 2.946708 mean severity and C10: 7412 complaints, yielding C12: 21841 priority score. Evidence shows charged accounts (01bc38c1-0d0b-4716-a3ed-a7fc3a0aa362, 0327424f-5ab1-42d7-aefa-b021dc049420) and account state mismatches (01fe8e61-0f32-4a8c-b6ae-a542cfa33975) erode trust in payment systems. _Why not first:_ Usability and other issues rank higher by priority score. Billing volume is meaningful but lower than top two; playback severity is higher despite fewer complaints. [C10, C11, C12]
**ISS-access** — Access issues have the second-highest mean severity at C17: 3.969859. Though C16: 1493 complaints yield low C18: 5927 priority score, the intensity suggests access barriers significantly impair affected users. _Why not first:_ Complaint volume is lowest among top tiers. Playback and billing address more reviewers despite lower severity per incident. [C16, C17, C18]

## Limitations

- Data reflects self-selected public reviews only; does not represent full user population, paying customers, or observed churn. No causal inference about retention or revenue impact possible.
- Complaint intent (cancellation vs. complaint) is stated intent, not confirmed account closure.
- ISS-other (C4: 14389 complaints, C6: 29099 priority score) contains unclassified issues; actionability requires sub-categorization.
- Severity and count are inferred from review text; no direct user telemetry on feature usage or failure rates available.
- Evidence pack is illustrative only; patterns may not be fully representative of classified corpus.

## Full ranking (recomputed from saved records, no model call)

| rank | issue | complaints | mean severity | priority |
|---|---|---|---|---|
| 1 | ISS-usability | 12408 | 2.606383 | 32340 |
| 2 | ISS-other | 14389 | 2.022309 | 29099 |
| 3 | ISS-playback | 6121 | 3.644176 | 22306 |
| 4 | ISS-billing | 7412 | 2.946708 | 21841 |
| 5 | ISS-catalog | 2332 | 2.841767 | 6627 |
| 6 | ISS-access | 1493 | 3.969859 | 5927 |
| 7 | ISS-downloads | 1026 | 3.548733 | 3641 |
| 8 | ISS-support | 101 | 2.960396 | 299 |

---
_Written by `claude-haiku-4-5` from saved aggregates and a bounded evidence pack. Code checked every cited claim ID, review ID and number against the saved calculations: all checks passed._
