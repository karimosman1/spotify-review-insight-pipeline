# Shared labels: definitions and worked examples

Definitions follow `reference/GRADING_CONTRACT.md` exactly. The model-facing wording lives in
[`pipeline/labels.py`](../pipeline/labels.py) (`enrich-p1` for the enricher, `verify-p1` for the verifier).
All examples come from **development data** (`checkpoint_500.csv`). None comes from the golden 50.
Quotes are shortened.

## Topic (exactly one)

| topic | covers | not this |
|---|---|---|
| access | login, signup, password, account access | "no internet" errors while already logged in (that's playback) |
| usability | navigation, controls, layout, queue/playlist management, ad interruptions | controls the review explicitly says are premium-only (that's billing) |
| playback | playback failure, crashes, lag, connection errors, audio quality, battery/data use | |
| downloads | downloading, saved music, offline listening, disappearing downloads | |
| catalog | missing songs/artists, search/discovery, recommendations, lyrics availability | lyrics that exist but are paywalled (that's billing) |
| billing | price, charges, subscriptions, paywalls, premium entitlement, premium-only controls | a paid plan merely being mentioned |
| support | contacting support and its response | |
| other | general praise/criticism, unrelated content, nothing specific | |

**Selection rule:**
- If several problems are mentioned, pick the one with the highest supported severity.
- On a tie, pick the first specific problem mentioned.
- For praise, pick the first specific praised feature. General praise is `other`.

## Intent (precedence order)

The first label that applies wins:

1. `cancellation`: the reviewer explicitly leaves, uninstalls or cancels, or threatens to.
2. `complaint`: a negative experience, including mixed praise and criticism. A bare "bad app" counts.
3. `request`: a desired change with no failure reported.
4. `praise`
5. `unclear`: bare boycott slogans and unrelated or meaningless text. A boycott becomes `cancellation` when the reviewer states they personally are leaving.

## Severity (1–5)

| level | meaning | applied example |
|---|---|---|
| 1 | no problem: praise, neutral/unclear, pure request | "I love sportify. This is number one music app" |
| 2 | dislike, generic criticism, minor annoyance | "great app… but too many ads" |
| 3 | degraded or restricted function; some use remains | "only 6 skips… can't pick the song you want" (free tier) |
| 4 | a core task clearly blocked | "I can't login to the app, it keeps saying no internet" |
| 5 | explicit serious financial, privacy or data harm | "moving storage failed and deleted everything" |

Stars, angry language and cancellation threats never raise severity by themselves.

## Worked examples (my applied labels)

| review_id | gist | topic | intent | sev | reasoning |
|---|---|---|---|---|---|
| 12efd15d-4d4f-4a71-8e71-69d03b6f983a | can't log in; says no internet but phone is online | access | complaint | 4 | login blocked; the "no internet" message is the symptom of the login failure |
| 4a806587-0dde-4fb4-b4f1-f5c7d197c927 | app crashing since latest update | playback | complaint | 4 | can't play music |
| f1abd13b-2391-4b04-8109-efa7f3cfed0b | random pauses; offline mode still needs data; repeated ads | playback | complaint | 3 | first and most severe problem is random pauses; degraded, not blocked |
| 3df77a78-ad9a-4456-8be8-8178ffd43d67 | "always say no internet connection"; Bollywood songs missing | playback | complaint | 4 | connection failure blocks playback; it outranks the catalog gap |
| 16929558-ce1e-4b87-8738-a1de3f557f66 | paid subscription, still sees "pause subscription", can't access music | billing | complaint | 4 | premium entitlement failure blocks the core task |
| d635d6c8-460e-452f-8d53-6cd1ea804e98 | "Why are lyrics premium!?" | billing | complaint | 3 | paywalled lyrics = restricted function (**the model said 2**) |
| 11ad400f-4487-4dfa-a9da-c8d624f4f107 | 6 skips, can't pick songs unless premium | billing | complaint | 3 | premium-only controls go to billing; restricted, still usable |
| 5e42046c-b29b-4035-ba83-a8e222789e98 | great app, but too many ads | usability | complaint | 2 | mixed review = complaint; ads are an annoyance |
| dd89d3d3-e4c1-446e-b899-fc038cfbcf95 | premium user; heart → plus icon broke how they track liked songs | usability | complaint | 3 | paid plan mentioned but not the problem; workflow degraded |
| b03d6dc9-449a-4647-b112-559186656759 | offline mode useless; moving storage deleted everything | downloads | complaint | 5 | explicit data loss |
| a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12 | signed up for premium, it stopped playing; cancelled | billing | cancellation | 4 | cancellation takes precedence over complaint; paid entitlement blocked playback |
| a06df5ff-01c8-4aff-a89c-a0c2ddc88f76 | premium updates ruin basic listening; "I might uninstall soon" | billing | cancellation | 2 | a threat to leave counts; impact stated only generically |
| 7fd63051-28ec-4e51-a06e-97f7010eae40 | uninstalled as a political boycott | other | cancellation | 1 | personal departure stated, but no product problem; cancellation doesn't raise severity (**the code rule bumped this to 2, see below**) |
| 0d361ea6-3089-41c2-9e0f-4cd6a04f0dd8 | random characters | other | unclear | 1 | meaningless text |
| 7a8b5434-66b4-4b13-aa91-5ad62a86ec04 | "number one music app" | other | praise | 1 | general praise, no specific feature |
| d26566f7-a898-4298-a06a-50bd3f7319c1 | wants hi-res audio; recommendations appear when turned off | catalog | complaint | 3 | **ambiguous**: setting ignored → recommendations (catalog) vs. a setting/control (usability). The model said playback, which I consider wrong |

## Known issues found while writing these examples

These will be fixed in `enrich-p2` after the golden-50 evaluation, which means a new `label_config` and a re-run:

- **Code rule for cancellations.** `apply_contract_rules` raises a severity-1 cancellation to 2. Per the contract, a departure with no product problem should stay at 1, so the rule should apply to `complaint` only.
- **Paywall severity.** Paywalled features (lyrics, skips) are sometimes rated 2 instead of 3. The severity examples need a paywall case.
