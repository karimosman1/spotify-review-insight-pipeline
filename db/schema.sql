-- Schema for the processed review data served to the dashboard.
-- Everything here is DERIVED from the saved pipeline artifacts in runs/<run>/ and is reloadable
-- with `python3 db/load_db.py`. The database is a serving layer, never the source of truth.

DROP TABLE IF EXISTS memo_alternative, memo, claim, ranking, membership, issue,
                     monthly_topic, eval_metric, review_record, pipeline_run CASCADE;

CREATE TABLE pipeline_run (
  run_id              TEXT PRIMARY KEY,
  scope               TEXT        NOT NULL,
  source_file         TEXT        NOT NULL,
  source_sha256       TEXT        NOT NULL,
  analysis_sha256     TEXT        NOT NULL,
  source_rows         INTEGER     NOT NULL,   -- 660,622 full corpus
  analysis_rows       INTEGER     NOT NULL,   -- rows in the declared scope
  completed           INTEGER     NOT NULL,
  quarantined         INTEGER     NOT NULL,
  distinct_texts      INTEGER     NOT NULL,
  cache_reuse_records INTEGER     NOT NULL,
  enrich_requests     INTEGER     NOT NULL,
  batch_size          INTEGER     NOT NULL,
  workers             INTEGER     NOT NULL,
  label_config        TEXT        NOT NULL,
  api_cost_usd        NUMERIC(12,6) NOT NULL,
  wall_clock_s        NUMERIC(12,3) NOT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE review_record (
  review_id       TEXT PRIMARY KEY,
  run_id          TEXT REFERENCES pipeline_run(run_id),
  status          TEXT NOT NULL,              -- completed | quarantined
  reason          TEXT,                       -- quarantine reason
  topic           TEXT,
  intent          TEXT,
  severity        SMALLINT,
  sentiment       REAL,
  evidence_quote  TEXT,                       -- exact substring of the source review
  needs_review    BOOLEAN,
  cache_source_id TEXT,                       -- direct original when text was reused
  review_rating   SMALLINT,
  app_version     TEXT,
  review_ts       TIMESTAMP,
  label_config    TEXT
);
CREATE INDEX review_topic_intent_idx ON review_record (topic, intent);
CREATE INDEX review_severity_idx     ON review_record (severity DESC);
CREATE INDEX review_needs_review_idx ON review_record (needs_review) WHERE needs_review;

CREATE TABLE issue (
  issue_id    TEXT PRIMARY KEY,
  topic       TEXT NOT NULL,
  label       TEXT NOT NULL,
  description TEXT
);

CREATE TABLE membership (
  issue_id  TEXT REFERENCES issue(issue_id),
  review_id TEXT REFERENCES review_record(review_id),
  PRIMARY KEY (issue_id, review_id)
);
CREATE INDEX membership_issue_idx ON membership (issue_id);

CREATE TABLE ranking (
  rank            SMALLINT NOT NULL,
  issue_id        TEXT PRIMARY KEY REFERENCES issue(issue_id),
  complaint_count INTEGER  NOT NULL,
  severity_sum    INTEGER  NOT NULL,
  mean_severity   NUMERIC(12,6) NOT NULL,
  priority_score  INTEGER  NOT NULL
);

CREATE TABLE claim (
  claim_id TEXT PRIMARY KEY,
  issue_id TEXT REFERENCES issue(issue_id),
  metric   TEXT NOT NULL,
  value    TEXT NOT NULL
);

CREATE TABLE memo (
  id              SERIAL PRIMARY KEY,
  run_id          TEXT REFERENCES pipeline_run(run_id),
  model           TEXT NOT NULL,
  label_config    TEXT NOT NULL,
  headline        TEXT NOT NULL,
  issue_id        TEXT REFERENCES issue(issue_id),
  rationale       TEXT NOT NULL,
  cited_claim_ids TEXT[] NOT NULL,
  cited_review_ids TEXT[] NOT NULL,
  limitations     TEXT[] NOT NULL,
  validation_passed BOOLEAN NOT NULL,
  validation_problems TEXT[] NOT NULL,
  input_tokens    INTEGER,
  output_tokens   INTEGER,
  cost_usd        NUMERIC(12,6),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE memo_alternative (
  id            SERIAL PRIMARY KEY,
  memo_id       INTEGER REFERENCES memo(id) ON DELETE CASCADE,
  issue_id      TEXT REFERENCES issue(issue_id),
  case_for      TEXT NOT NULL,
  why_not_first TEXT NOT NULL,
  cited_claim_ids TEXT[] NOT NULL
);

-- Complaint share by month, with denominators, for trend display. First and last calendar
-- months of the window are partial; the dashboard labels them.
CREATE TABLE monthly_topic (
  month      TEXT NOT NULL,
  topic      TEXT NOT NULL,
  complaints INTEGER NOT NULL,
  reviews    INTEGER NOT NULL,
  partial    BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (month, topic)
);

-- Evaluation evidence shown on the dashboard so the numbers are inspectable.
CREATE TABLE eval_metric (
  name        TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  sample_size INTEGER,
  detail      TEXT
);

-- Supabase exposes tables in `public` through PostgREST using the anon key. This dashboard reads
-- the database server-side with a privileged role over DATABASE_URL and never ships an anon key to
-- the browser, so enable RLS with NO policies: anonymous REST access is denied outright while the
-- backend's role (which bypasses RLS) keeps working. On a non-Supabase Postgres this is harmless.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['pipeline_run','review_record','issue','membership','ranking','claim',
                           'memo','memo_alternative','monthly_topic','eval_metric']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
