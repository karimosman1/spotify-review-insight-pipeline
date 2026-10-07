# Golden-50 evaluation

```json
{
  "label_config": "jev-1.13.0+enrich-b1+schema-v1",
  "predictions_from": "runs/golden50_b10",
  "human_labeled": 50,
  "of_total": 50,
  "missing_or_quarantined_predictions": 0,
  "agreement": {
    "topic": 0.9,
    "intent": 0.92,
    "severity": 0.82,
    "joint": 0.76
  },
  "severity_mae": 0.26,
  "sentiment_mae": 0.1369,
  "sentiment_within_0.5": 0.92,
  "quote_exact_substring_rate": 1.0,
  "ambiguous_cases": 5,
  "needs_review_as_predictor": {
    "flagged": 6,
    "flagged_and_wrong": 3,
    "wrong_total": 12
  },
  "note": "50 cases is a small diagnostic sample, not a population accuracy estimate. Ambiguous cases accept the recorded alternative label."
}
```

## Topic confusion (rows = human, cols = model)

| human \ model | access | usability | playback | downloads | catalog | billing | support | other |
|---|---|---|---|---|---|---|---|---|
| access |  |  |  |  |  |  |  |  |
| usability |  | 8 |  |  |  | 2 |  |  |
| playback |  |  | 4 |  |  |  |  |  |
| downloads |  |  |  | 1 |  |  |  |  |
| catalog |  |  |  |  | 5 |  |  | 1 |
| billing |  |  |  |  |  | 1 |  |  |
| support |  |  | 1 |  |  |  |  |  |
| other |  |  |  |  | 1 | 1 |  | 25 |

## Disagreements (fill in the 'why' column during error analysis)

| review_id | text | human topic/intent/sev | model topic/intent/sev | why |
|---|---|---|---|---|
| 1fc8b08f | Duo Premium .... No ads at all! | usability|other/praise|unclear/1 | billing/praise/1 | |
| 947821dc | Very good but wen I play my song it o ly plays a little bit then it stops I updated my pho | playback/complaint/4 | playback/complaint/3 | |
| 723f07de | Update: I reached out to Spotify Support and with some help from Sarah I was able to get t | support/praise/1 | playback/complaint/4 | |
| ac6cd66d | Lhat ng song nasa spotify | other/unclear/1 | catalog/complaint/3 | |
| 5de7f95b | We are boycotting Swedish app in our protest against Sweden for their desrecpect & descera | other/cancellation/2 | other/unclear/1 | |
| 372d4e67 | Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | usability/complaint/2 | usability/request/1 | |
| 16d640e9 | It's my best music app but now it's not...everything basic features is premium.... | billing/complaint/2 | billing/complaint/3 | |
| 46c0b49f | Are you out of your mind? This is dangerous! Listening to music in a normal volume and sud | usability/complaint/2 | usability/complaint/3 | |
| 283b5843 | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like | other/unclear/1 | billing/unclear/1 | |
| dceb14e7 | I gave one star because I can't give any less than that. the new update is sooooooo annoyi | playback/complaint/3 | playback/complaint/4 | |
| ac4e860a | paying for subscribing but unable to play in offline mode really? | downloads/complaint/2 | downloads/complaint/4 | |
| d2f3874f | Too expensive and the free version is pretty much unusable with constant ads... Every two  | usability/complaint|cancellation/3|2 | billing/complaint/3 | |
