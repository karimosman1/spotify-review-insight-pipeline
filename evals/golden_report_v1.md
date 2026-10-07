# Golden-50 evaluation

```json
{
  "label_config": "jev-1.13.0+enrich-p1+schema-v1",
  "human_labeled": 50,
  "of_total": 50,
  "missing_or_quarantined_predictions": 0,
  "agreement": {
    "topic": 0.82,
    "intent": 0.82,
    "severity": 0.76,
    "joint": 0.6
  },
  "severity_mae": 0.32,
  "sentiment_mae": 0.107,
  "sentiment_within_0.5": 0.94,
  "quote_exact_substring_rate": 1.0,
  "ambiguous_cases": 0,
  "needs_review_as_predictor": {
    "flagged": 7,
    "flagged_and_wrong": 5,
    "wrong_total": 20
  },
  "note": "50 cases is a small diagnostic sample, not a population accuracy estimate. Ambiguous cases accept the recorded alternative label."
}
```

## Topic confusion (rows = human, cols = model)

| human \ model | access | usability | playback | downloads | catalog | billing | support | other |
|---|---|---|---|---|---|---|---|---|
| access |  |  |  |  |  |  |  |  |
| usability |  | 9 |  |  |  | 1 |  |  |
| playback |  |  | 4 |  | 1 |  |  |  |
| downloads |  |  |  |  |  | 1 |  |  |
| catalog |  |  |  |  | 3 |  |  | 2 |
| billing |  |  |  |  |  |  |  |  |
| support |  |  | 1 |  |  |  |  |  |
| other |  | 1 |  |  | 1 | 1 |  | 25 |

## Disagreements (fill in the 'why' column during error analysis)

| review_id | text | human topic/intent/sev | model topic/intent/sev | why |
|---|---|---|---|---|
| 292ce26a | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks  | catalog/complaint/2 | other/complaint/2 | |
| 991b6b3a | Ads were okay, but limited functionality..it's just too much | usability/cancellation/3 | usability/complaint/2 | |
| b5ee7834 | Spotify is awesome and and very diverse :) | catalog/praise/1 | other/praise/1 | |
| 1fc8b08f | Duo Premium .... No ads at all! | other/unclear/1 | usability/praise/1 | |
| 947821dc | Very good but wen I play my song it o ly plays a little bit then it stops I updated my pho | playback/complaint/4 | playback/complaint/3 | |
| 723f07de | Update: I reached out to Spotify Support and with some help from Sarah I was able to get t | support/praise/1 | playback/complaint/4 | |
| 47428620 | This app is bad work | other/complaint/1 | other/complaint/2 | |
| fc344263 | Great... | other/praise/1 | other/unclear/1 | |
| ac6cd66d | Lhat ng song nasa spotify | other/unclear/1 | catalog/complaint/2 | |
| 46842184 | asem, lirik nya kdang gaada kek mana?? | catalog/complaint/2 | catalog/complaint/3 | |
| 47f1406d | Very poor updates as we cannot playback the songs and most bad updates are happening it is | playback/complaint/2 | playback/complaint/4 | |
| f4c8146a | Unconditional love, Stoli Canales | other/praise/1 | other/unclear/1 | |
| 3ddb3f4e | Deleting this App. The new update suck, we can't choose our fvrt songs after some clicks,  | usability/cancellation/2 | usability/cancellation/3 | |
| 16d640e9 | It's my best music app but now it's not...everything basic features is premium.... | usability/complaint/2 | billing/complaint/3 | |
| 8cc4fad4 | I hate this app and sweden .I love islam | other/unclear/2 | other/complaint/2 | |
| 283b5843 | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/1 | billing/unclear/1 | |
| 2aa566c6 | Nice app, very less advertising | usability/complaint/1 | usability/praise/1 | |
| 8c0546b0 | 1-Lyrics not getting loaded, 2-can't go back to or start song where to wanted. Pathetic up | playback/complaint/2 | catalog/complaint/3 | |
| ac4e860a | paying for subscribing but unable to play in offline mode really? | downloads/complaint/2 | billing/complaint/4 | |
| d2f3874f | Too expensive and the free version is pretty much unusable with constant ads... Every two  | usability/cancellation/2 | usability/complaint/3 | |
