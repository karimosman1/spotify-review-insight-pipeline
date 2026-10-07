"""Shared label definitions (from reference/GRADING_CONTRACT.md) and the Jev question sets.

The enricher and verifier are separate roles with separately worded instructions. Neither ever
receives a previous prediction or a golden human label. Examples below are paraphrased from
development files (cost_100 / checkpoint_500), never from the golden 50.

Bump the version strings whenever wording changes: cached results are keyed by them.
"""

TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")  # precedence order
SEVERITIES = (1, 2, 3, 4, 5)

JEV_MODEL = "jev-1.13.0"  # pinned (jev-latest is an alias that may move)
ENRICH_PROMPT_VERSION = "enrich-p1"
VERIFY_PROMPT_VERSION = "verify-p1"
SCHEMA_VERSION = "schema-v1"
ENRICH_LABEL_CONFIG = f"{JEV_MODEL}+{ENRICH_PROMPT_VERSION}+{SCHEMA_VERSION}"
VERIFY_LABEL_CONFIG = f"{JEV_MODEL}+{VERIFY_PROMPT_VERSION}+{SCHEMA_VERSION}"

# ---------------------------------------------------------------- enricher (role: enrich)

ENRICH_TOPIC = {
    "type": "choice",
    "instructions": (
        "Which product area is this app review mainly about? If several problems are mentioned, pick the "
        "one with the most serious impact; on a tie, the first specific problem mentioned. For a positive "
        "review pick the first specific praised feature; general praise with no specific feature is 'other'. "
        "Mentioning a paid/premium plan alone does not make it billing."
    ),
    "criteria": {
        "access": {
            "what": "Login, signup, password, or account access problems",
            "examples": ["I can't log in, it says there's no internet but everything else works",
                         "my account got logged out and won't accept my password"],
        },
        "usability": {
            "what": "Navigation, controls, layout, queue/playlist management, UI changes, ad interruptions",
            "not_for": "Controls that the review explicitly says are locked behind premium (that is billing)",
            "examples": ["too many ads, five in a row", "the new drop-down only lets me shuffle my playlist",
                         "replacing the heart with a plus was a bad design change"],
        },
        "playback": {
            "what": "Playback failure, crashes, lag, songs stopping, connection errors, audio quality, battery/data use",
            "examples": ["app crashes since the latest update", "music randomly stops even with full bars",
                         "keeps saying no internet connection when my internet works"],
        },
        "downloads": {
            "what": "Downloading songs, saved music, offline listening, downloads disappearing",
            "examples": ["offline mode still needs wifi to open downloaded songs", "my downloads got deleted"],
        },
        "catalog": {
            "what": "Missing songs or artists, search and discovery, recommendations, lyrics availability, podcasts content",
            "not_for": "Lyrics that are available but locked behind premium (that is billing)",
            "examples": ["my favourite Bollywood songs are not on the app", "keeps recommending songs I hate",
                         "lyrics won't load for songs in my playlist"],
        },
        "billing": {
            "what": "Price, charges, subscriptions, paywalls, premium entitlement, features restricted to premium",
            "examples": ["I paid for premium and still can't access my music", "why are lyrics premium now",
                         "only 6 skips unless you pay, every basic feature is paid now"],
        },
        "support": {
            "what": "Contacting customer support and the quality of the support response",
            "examples": ["support never answered my emails", "the chat agent just told me to reinstall"],
        },
        "other": {
            "what": "General praise or criticism with no specific feature, unrelated content, politics, gibberish",
            "examples": ["great app", "worst app ever", "boycott because of a government decision", "random letters"],
        },
    },
}

ENRICH_INTENT = {
    "type": "choice",
    "instructions": (
        "What is the reviewer's main intent? Apply this precedence: if they explicitly say they are leaving, "
        "uninstalling, cancelling, or threaten to, it is cancellation even if they also complain. Otherwise a "
        "negative experience (including mixed praise and criticism) is complaint. A desired change with no "
        "reported failure is request. Purely positive is praise. Slogans, unrelated or meaningless text is unclear."
    ),
    "criteria": {
        "cancellation": {"what": "Explicitly leaving, uninstalling, cancelling, or threatening to",
                         "examples": ["I'm uninstalling", "time to cancel my subscription", "I might uninstall soon"],
                         "not_for": "Bare boycott slogans with no product complaint or personal departure"},
        "complaint": {"what": "A negative experience or criticism of the product, including mixed reviews",
                      "examples": ["great app but too many ads", "bad app", "lyrics won't load"]},
        "request": {"what": "Asks for a feature or change without reporting a failure",
                    "examples": ["please add hi-res audio", "would love a sleep timer on the widget"]},
        "praise": {"what": "Purely positive feedback", "examples": ["love this app", "easy to use"]},
        "unclear": {"what": "Unrelated, meaningless, or slogan-only text; intent cannot be determined",
                    "examples": ["random characters", "a political slogan with no product content"]},
    },
}

ENRICH_SEVERITY = {
    "type": "choice",
    "instructions": (
        "How severe is the problem the reviewer actually describes? Judge reported impact only. Star ratings, "
        "angry language, insults, or threats to cancel do not by themselves raise severity. Do not invent impact."
    ),
    "criteria": {
        "sev1": {"what": "No reported problem: praise, neutral or unclear content, or a pure feature request"},
        "sev2": {"what": "Dislike, generic criticism, minor annoyance or cosmetic issue; no specific loss of function",
                 "examples": ["worst app", "too many ads", "I don't like the new design"]},
        "sev3": {"what": "A function is degraded or restricted but some use or workaround remains",
                 "examples": ["lyrics sometimes don't load", "only 6 skips per hour on free", "random pauses"]},
        "sev4": {"what": "A core task is clearly blocked, such as cannot log in or cannot play any music",
                 "examples": ["can't log in at all", "app crashes every time I open it", "I paid and can't play anything"]},
        "sev5": {"what": "Explicit serious financial, privacy or data harm",
                 "examples": ["charged twice and refused a refund", "my account was hacked and my data exposed"],
                 "not_for": "Merely an expensive price, a crash, or angry language"},
    },
}

ENRICH_SENTIMENT = {
    "type": "score",
    "instructions": "Overall sentiment the reviewer expresses toward the app.",
    "criteria": ["Very negative", "Somewhat negative", "Neutral or mixed", "Somewhat positive", "Very positive"],
}

ENRICH_QUESTIONS = {"topic": ENRICH_TOPIC, "intent": ENRICH_INTENT,
                    "severity": ENRICH_SEVERITY, "sentiment": ENRICH_SENTIMENT}

# ---------------------------------------------------------------- verifier (role: verify)
# Written independently and more tersely; it only sees the original review text.

VERIFY_QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": ("Classify the main subject of this Spotify review. Choose the most serious specific "
                         "problem (first one if tied); for praise, the first specific feature praised; general "
                         "comments go to other. A paid plan being mentioned is not by itself a billing topic."),
        "criteria": {
            "access": "Signing in, signing up, passwords, locked or lost account access",
            "usability": "Interface, navigation, controls, queue and playlist handling, advertisements",
            "playback": "Audio not playing, stopping, crashing, lagging, connection errors, sound quality",
            "downloads": "Downloaded or saved music, offline mode",
            "catalog": "Song/artist availability, search, recommendations, lyrics availability",
            "billing": "Prices, payments, subscriptions, paywalls, features limited to paying users",
            "support": "Customer service contact and responses",
            "other": "Nothing specific: general opinion, off-topic, or meaningless text",
        },
    },
    "intent": {
        "type": "choice",
        "instructions": ("Pick the first label that applies, in this order: cancellation, complaint, request, "
                         "praise, unclear."),
        "criteria": {
            "cancellation": "The writer says they are quitting, uninstalling, cancelling, or threatens to",
            "complaint": "The writer reports something bad or criticizes the app",
            "request": "The writer asks for something new without reporting anything broken",
            "praise": "The writer is only positive",
            "unclear": "Cannot tell, off-topic, or slogan only",
        },
    },
    "severity": {
        "type": "choice",
        "instructions": "Rate the reported impact on the user. Ignore tone and star rating.",
        "criteria": {
            "sev1": "Nothing wrong reported",
            "sev2": "Annoyed or generally critical, nothing actually stops working",
            "sev3": "Something works worse or is limited, but the app is still usable",
            "sev4": "Cannot do a core thing at all (sign in, play music)",
            "sev5": "Real money lost, privacy breach, or data harm explicitly stated",
        },
    },
}

# ---------------------------------------------------------------- deterministic extraction (code, no model)

TOPIC_TERMS = {
    "access": ["log in", "login", "logged out", "sign in", "sign up", "signup", "password", "account"],
    "usability": ["ads", "advert", "ad ", "interface", "ui", "layout", "navigation", "queue", "playlist",
                  "shuffle", "button", "update", "design", "menu", "widget"],
    "playback": ["crash", "stop", "pause", "lag", "internet", "connection", "play", "freez", "glitch",
                 "buffer", "audio", "sound", "battery", "bluetooth", "cast"],
    "downloads": ["download", "offline", "storage", "saved"],
    "catalog": ["song", "artist", "lyrics", "search", "recommend", "podcast", "album", "missing"],
    "billing": ["premium", "pay", "paid", "price", "subscription", "charge", "money", "refund", "free"],
    "support": ["support", "customer service", "help", "contact", "response"],
    "other": [],
}

ENTITY_TERMS = ["premium", "free", "ads", "shuffle", "skip", "lyrics", "playlist", "queue", "podcast",
                "download", "offline", "login", "password", "dj", "widget", "bluetooth", "car", "android auto",
                "smart shuffle", "family plan", "student", "update", "search", "recommendations", "repeat",
                "liked songs", "wear os", "chromecast", "audiobook"]


# ---------------------------------------------------------------- batched enricher (role: enrich, enrich-b1)
# Jev bills input tokens only, and a per-review request spends ~1,750 of them re-sending the rubric.
# Batched design: the full rubric travels ONCE in `state` alongside N reviews; the N*4 questions carry
# only short option labels that point back into that rubric. Validated against the golden 50 before use.

BATCH_PROMPT_VERSION = "enrich-b1"
BATCH_LABEL_CONFIG = f"{JEV_MODEL}+{BATCH_PROMPT_VERSION}+{SCHEMA_VERSION}"
MAX_BATCH = 10

BATCH_RUBRIC = {
    "task": "Classify each Spotify app review in `reviews` independently. Answer only about the review named in each question.",
    "topic": {
        "selection_rule": "Pick the problem with the highest supported severity; on a tie the first specific problem mentioned. For a positive review pick the first specific praised feature; general praise is 'other'. Mentioning a paid/premium plan alone is NOT billing.",
        "access": "Login, signup, password, account access.",
        "usability": "Navigation, controls, layout, queue/playlist management, ad interruptions. NOT controls the review says are premium-only.",
        "playback": "Playback failure, crashes, lag, songs stopping, connection errors, audio quality, battery/data use.",
        "downloads": "Downloading, saved music, offline listening, downloads disappearing.",
        "catalog": "Missing songs/artists, search, discovery, recommendations, lyrics availability. NOT lyrics that exist but are paywalled.",
        "billing": "Price, charges, subscriptions, paywalls, premium entitlement, features restricted to premium.",
        "support": "Contacting customer support and the support response.",
        "other": "General praise or criticism with no specific feature, unrelated content, politics, gibberish.",
    },
    "intent": {
        "precedence": "First match wins: cancellation > complaint > request > praise > unclear.",
        "cancellation": "Explicitly leaving, uninstalling, cancelling, or threatening to. A bare boycott slogan with no product complaint and no personal departure is NOT cancellation.",
        "complaint": "Negative experience or criticism, including mixed praise/criticism. 'Bad app' counts.",
        "request": "Asks for a change with no reported failure.",
        "praise": "Only positive.",
        "unclear": "Slogans, unrelated, or meaningless text.",
    },
    "severity": {
        "rule": "Judge only the impact the reviewer actually describes. Star ratings, angry language, insults and threats to cancel do NOT raise severity. Do not invent impact.",
        "sev1": "No reported problem: praise, neutral or unclear content, or a pure feature request.",
        "sev2": "Dislike, generic criticism, minor annoyance or cosmetic issue; nothing stops working.",
        "sev3": "A function is degraded or restricted but some use or workaround remains (includes features locked behind a paywall).",
        "sev4": "A core task is clearly blocked: cannot log in, cannot play music, app crashes on open.",
        "sev5": "Explicit serious financial, privacy or data harm (lost money, hacked account, deleted data). An expensive price or a crash alone is NOT enough.",
    },
    "sentiment": "Overall feeling toward the app, from very negative to very positive.",
}

_T = {k: v for k, v in BATCH_RUBRIC["topic"].items() if k != "selection_rule"}
_I = {k: v for k, v in BATCH_RUBRIC["intent"].items() if k != "precedence"}
_S = {k: v for k, v in BATCH_RUBRIC["severity"].items() if k != "rule"}
_SHORT_T = {k: v.split(".")[0][:60] for k, v in _T.items()}
_SHORT_I = {k: v.split(".")[0][:60] for k, v in _I.items()}
_SHORT_S = {k: v.split(";")[0].split(":")[0][:60] for k, v in _S.items()}


def batch_state(reviews):
    """reviews: list of review texts. Rubric travels once per request."""
    return {"rubric": BATCH_RUBRIC, "reviews": [{"n": i + 1, "text": t} for i, t in enumerate(reviews)]}


def batch_questions(n):
    """4 questions per review; option descriptions are short because the rubric is in the state."""
    q = {}
    for i in range(1, n + 1):
        q[f"topic_{i}"] = {"type": "choice", "criteria": _SHORT_T,
                           "instructions": f"Review {i} only: product area, using rubric.topic and its selection_rule."}
        q[f"intent_{i}"] = {"type": "choice", "criteria": _SHORT_I,
                            "instructions": f"Review {i} only: intent, using rubric.intent precedence order."}
        q[f"severity_{i}"] = {"type": "choice", "criteria": _SHORT_S,
                              "instructions": f"Review {i} only: severity of the reported impact, using rubric.severity."}
        q[f"sentiment_{i}"] = {"type": "score", "criteria": ["Very negative", "Somewhat negative",
                                                            "Neutral or mixed", "Somewhat positive", "Very positive"],
                               "instructions": f"Review {i} only: overall sentiment toward the app."}
    return q
