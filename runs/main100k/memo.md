# Priority memo: Prioritize usability issues: highest priority score driven by volume

_Scope: 100,013 reviews sampled from 660,622 Spotify Google Play reviews (May 2022 - Nov 2023); 100,000 classified, 13 empty texts quarantined._

**Recommendation: ISS-usability**

ISS-usability ranks 1 of 8 by priority_score with 32340 (C3). It has the second-highest complaint count at 12408 (C1) but ranks 7 of 8 by mean_severity at 2.606383 (C2). This is a high-volume, moderate-severity trade-off: the sheer number of complaints makes it the most urgent. Evidence shows recurring friction: ads interrupting free tier use (08a1f178-3e7a-4d65-9da3-dee293dd0061), playlist loss after updates (30b1d1c0-e1a1-437f-a5cd-e1327467bda4), and data consumption concerns (365c0fe6-e618-4c4a-9176-fbd48eb76d30, 5e8201f3-0f71-44be-8eab-b8d9414496be).

## Supporting numbers

| claim | issue | metric | value |
|---|---|---|---|
| C3 | ISS-usability | priority_score | 32340 |
| C1 | ISS-usability | complaint_count | 12408 |
| C2 | ISS-usability | mean_severity | 2.606383 |

## Representative reviews

- `08a1f178-3e7a-4d65-9da3-dee293dd0061` (severity 5, cancellation): "That wasn't the trigger me to give this a one star; it is ads."
- `30b1d1c0-e1a1-437f-a5cd-e1327467bda4` (severity 5, complaint): "Recent update lost everything, even my Play list is deleted"
- `365c0fe6-e618-4c4a-9176-fbd48eb76d30` (severity 5, complaint): "Isse bekaar app maine aaj tak nhi dekha jitni baar back kro utni Baar add aate hai . If you download this app you would lost your mb 🤣"
- `5e8201f3-0f71-44be-8eab-b8d9414496be` (severity 5, complaint): "Startìng to irritate me when i see "enjoy 30 mins of uniterrupted listening after the video" then theres 3 ads after i counted 3 i came here im a daily almost hourly listener of spotify so whys it give me 3 to 5 ads afte"

## Alternatives considered

**ISS-playback** — Playback ranks 2 of 8 by mean_severity at 3.644176 (C8), indicating acute user frustration when the core product fails. With 6121 complaints (C7), it ranks 4 of 8 by complaint count and 3 of 8 by priority_score (C9). Evidence shows critical failures: nothing playing (0834a740-a550-4e67-b4ef-128a78940f6b) and persistent glitching (15d478e6-07df-436c-8c31-a0ab7a6b4e77). _Why not first:_ Priority score 22306 (C9) is lower than usability's 32340 (C3). Playback complaints are fewer and more acute; usability complaints are both more numerous and materially severe. [C8, C7, C9]
**ISS-billing** — ISS-billing has 7412 complaints (C10), ranking 3 of 8 by complaint count, with mean_severity 2.946708 (C11) and priority_score 21841 (C12). Evidence indicates financial harm concerns: unexpected charges after cancellation (01bc38c1-0d0b-4716-a3ed-a7fc3a0aa362), charges without permission (0327424f-5ab1-42d7-aefa-b021dc049420), and payment-to-service mismatch (01fe8e61-0f32-4a8c-b6ae-a542cfa33975). _Why not first:_ Priority score 21841 (C12) trails usability's 32340 (C3). Billing ranks below both usability and playback in priority impact. [C10, C11, C12]
**ISS-access** — ISS-access ranks 1 of 8 by mean_severity at 3.969859 (C17), the highest acute severity in the dataset. Though only 1493 complaints (C16), it reflects severe barriers to app use. _Why not first:_ Priority score 5927 (C18) is far below usability's 32340 (C3). Complaint volume is substantially lower. High severity does not compensate when occurrence is rare. [C17, C16, C18]

## Limitations

- Data reflects self-selected public reviews only; does not represent the full user population or paying subscribers. No revenue, churn, plan tier, or retention data available. Cancellation language indicates stated intent, not confirmed churn. Issue classification depends on review text quality and model accuracy. Severity scores are review-level ratings and do not measure business impact. Claims with ISS-other (14389 complaints, C4) remain unspecified and warrant investigation—this issue ranks 2 of 8 by priority_score (C6) with the lowest mean severity (C5), suggesting numerous but mild complaints of heterogeneous nature.

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
