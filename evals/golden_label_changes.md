# Golden-50 label changes: v1 → v2

v1 (`data/golden_50_labeled_v1.csv`) is the original hand labeling, kept unchanged.
v2 corrects labels that contradicted a written rule in GRADING_CONTRACT.md. These were identified **after** seeing model predictions (disclosed per the assignment). Only rule violations were changed; disagreements that were judgment calls were left as they were, or will be marked ambiguous.

| review_id | text | change | rule applied |
|---|---|---|---|
| 991b6b3a-f511-458a-a5b7-234f78048fb5 | Ads were okay, but limited functionality..it's just too much | intent: cancellation → complaint | Cancellation requires explicitly leaving/uninstalling/cancelling or threatening to; 'it's just too much' does not state departure. |
| 47428620-ec21-424d-a515-0b0b0012a5cf | This app is bad work | severity: 1 → 2 | Severity 2 = 'generic criticism'; contract: 'General "bad app" is a complaint'. A complaint cannot be severity 1 (no reported problem). |
| 47f1406d-4918-4d60-9647-5ca8e610caca | Very poor updates as we cannot playback the songs and most bad updates are happe | severity: 2 → 4 | Severity 4 = 'a clearly blocked core task, such as inability to ... play music'; text says 'we cannot playback the songs'. |
| 3ddb3f4e-f7b9-430b-b335-eadc6d321f46 | Deleting this App. The new update suck, we can't choose our fvrt songs after som | severity: 2 → 3 | Song choice/shuffle restricted but app still usable = 'degraded or restricted function; some use remains'. |
| 16d640e9-b281-4746-9562-c7dbcf7126b6 | It's my best music app but now it's not...everything basic features is premium.. | topic: usability → billing | Text is about basic features moved to premium; contract: billing covers paywalls/premium entitlement and 'explicitly premium-only controls go here'. |
| 8cc4fad4-26ec-47b7-96e8-49c7da714eca | I hate this app and sweden .I love islam | severity: 2 → 1 | Severity 1 covers 'neutral/unclear content'; intent kept as unclear (boycott slogan). |
| 2aa566c6-b98d-4513-b900-83702a8db8eb | Nice app, very less advertising | intent: complaint → praise | 'very less advertising' means very few ads: positive about ads, no negative experience reported. |
| 8c0546b0-ce43-4a36-9d33-9f979e98d522 | 1-Lyrics not getting loaded, 2-can't go back to or start song where to wanted. P | topic: playback → catalog; severity: 2 → 3 | Tie rule: first specific problem mentioned is lyrics not loading (catalog: lyrics availability); features failing but app usable = 3. |

## Ambiguous cases (both labels accepted)

Marked `ambiguous=true` with an accepted alternative. Also identified after seeing predictions (disclosed).

| review_id | text | primary (change from v1) | accepted alternative | reason |
|---|---|---|---|---|
| b5ee7834-a0eb-4c15-9c7b-935831021922 | Spotify is awesome and and very diverse :) | unchanged | topic=other | 'very diverse' may be catalog variety (specific feature) or general praise. |
| 1fc8b08f-7d6a-472f-b317-8ceb28d00f22 | Duo Premium .... No ads at all! | topic: other → usability; intent: unclear → praise | topic=other, intent=unclear | 'No ads at all!' reads as praise of the ad-free experience; could also be an unclear fragment. Premium mention alone is not billing. |
| 46842184-32f8-4088-ac15-2a700a7e94ed | asem, lirik nya kdang gaada kek mana?? | unchanged | severity=3 | Lyrics missing 'sometimes' (kadang): minor annoyance (2) or degraded function with use remaining (3). |
| f4c8146a-d5c8-4168-b00e-21af666afc6a | Unconditional love, Stoli Canales | unchanged | intent=unclear | 'Unconditional love' may praise the app or be an unrelated name/song reference. |
| d2f3874f-d15d-4a2f-bb97-4f1213defa46 | Too expensive and the free version is pretty much unusable with consta | intent: cancellation → complaint; severity: 2 → 3 | intent=cancellation, severity=2 | 'Forget it' implies giving up but is not an explicit departure; 'pretty much unusable' with music still playing is degraded (3) rather than mere annoyance (2). |

Reviewed and kept: 947821dc stays severity 4, not ambiguous. Playback stops again after the temporary workaround (a phone update) stopped working, so the core task is blocked.
