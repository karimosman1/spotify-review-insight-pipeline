# Golden-50 evaluation

```json
{
  "label_config": "jev-1.13.0+enrich-p1+schema-v1",
  "predictions_from": "runs/golden50",
  "human_labeled": 50,
  "of_total": 50,
  "missing_or_quarantined_predictions": 0,
  "agreement": {
    "topic": 0.9,
    "intent": 0.92,
    "severity": 0.86,
    "joint": 0.8
  },
  "severity_mae": 0.2,
  "sentiment_mae": 0.107,
  "sentiment_within_0.5": 0.94,
  "quote_exact_substring_rate": 1.0,
  "ambiguous_cases": 5,
  "needs_review_as_predictor": {
    "flagged": 7,
    "flagged_and_wrong": 3,
    "wrong_total": 10
  },
  "note": "50 cases is a small diagnostic sample, not a population accuracy estimate. Ambiguous cases accept the recorded alternative label."
}
```

## Topic confusion (rows = human, cols = model)

| human \ model | access | usability | playback | downloads | catalog | billing | support | other |
|---|---|---|---|---|---|---|---|---|
| access |  |  |  |  |  |  |  |  |
| usability |  | 10 |  |  |  |  |  |  |
| playback |  |  | 4 |  |  |  |  |  |
| downloads |  |  |  |  |  | 1 |  |  |
| catalog |  |  |  |  | 4 |  |  | 2 |
| billing |  |  |  |  |  | 1 |  |  |
| support |  |  | 1 |  |  |  |  |  |
| other |  |  |  |  | 1 | 1 |  | 25 |

## Disagreements (fill in the 'why' column during error analysis)

| review_id | text | human topic/intent/sev | model topic/intent/sev | why |
|---|---|---|---|---|
| 292ce26a | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks  | catalog/complaint/2 | other/complaint/2 | |
| 991b6b3a | Ads were okay, but limited functionality..it's just too much | usability/complaint/3 | usability/complaint/2 | |
| 947821dc | Very good but wen I play my song it o ly plays a little bit then it stops I updated my pho | playback/complaint/4 | playback/complaint/3 | |
| 723f07de | Update: I reached out to Spotify Support and with some help from Sarah I was able to get t | support/praise/1 | playback/complaint/4 | |
| fc344263 | Great... | other/praise/1 | other/unclear/1 | |
| ac6cd66d | Lhat ng song nasa spotify | other/unclear/1 | catalog/complaint/2 | |
| 16d640e9 | It's my best music app but now it's not...everything basic features is premium.... | billing/complaint/2 | billing/complaint/3 | |
| 8cc4fad4 | I hate this app and sweden .I love islam | other/unclear/1 | other/complaint/2 | |
| 283b5843 | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/1 | billing/unclear/1 | |
| ac4e860a | paying for subscribing but unable to play in offline mode really? | downloads/complaint/2 | billing/complaint/4 | |
