// Backend data access. Every dashboard number is read from Postgres here; nothing is
// recomputed in the browser and nothing is hard-coded in the UI.
//
// Provider-agnostic on purpose: any Postgres works. A Neon host uses Neon's HTTP driver (no
// connection pool, which suits serverless functions); anything else (Supabase, Railway, Render,
// local Postgres) uses node-postgres. DATABASE_URL alone decides, so the hosting choice is not
// baked into the app.
import { neon } from "@neondatabase/serverless";
import { Pool } from "pg";

type Rows = Record<string, any>[];
type SqlFn = (strings: TemplateStringsArray, ...values: unknown[]) => Promise<Rows>;

// Resolved on first query, not at import: `next build` must succeed without a database, and the
// deployed app reads DATABASE_URL from its hosting environment at runtime.
let _sql: SqlFn | null = null;
let _pool: Pool | null = null;

const client = (): SqlFn => {
  if (_sql) return _sql;
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is not set. Put the Postgres connection string in dashboard/.env.local for " +
      "local development, or in the hosting project's environment variables for the deployment."
    );
  }
  if (/\.neon\.tech|neon\.build/.test(url)) {
    const tag = neon(url);
    _sql = ((s, ...v) => (tag as unknown as SqlFn)(s, ...v)) as SqlFn;
  } else {
    // node-postgres takes $1-style placeholders, so convert the tagged template to a parameterized
    // query. Values are never interpolated into SQL text.
    _pool = _pool ?? new Pool({
      connectionString: url,
      ssl: url.includes("sslmode=disable") ? undefined : { rejectUnauthorized: false },
      max: 3,
    });
    _sql = (async (strings: TemplateStringsArray, ...values: unknown[]) => {
      const text = strings.reduce((acc, s, i) => acc + s + (i < values.length ? `$${i + 1}` : ""), "");
      const res = await _pool!.query(text, values as unknown[]);
      return res.rows as Rows;
    }) as SqlFn;
  }
  return _sql;
};

export const sql: SqlFn = (strings, ...values) => client()(strings, ...values);

export type Run = {
  run_id: string; scope: string; source_file: string; source_sha256: string; analysis_sha256: string;
  source_rows: number; analysis_rows: number; completed: number; quarantined: number;
  distinct_texts: number; cache_reuse_records: number; enrich_requests: number; batch_size: number;
  workers: number; label_config: string; api_cost_usd: string; wall_clock_s: string;
};
export type RankRow = {
  rank: number; issue_id: string; label: string; description: string;
  complaint_count: number; severity_sum: number; mean_severity: string; priority_score: number;
};
export type Claim = { claim_id: string; issue_id: string; metric: string; value: string };
export type Memo = {
  id: number; model: string; label_config: string; headline: string; issue_id: string; rationale: string;
  cited_claim_ids: string[]; cited_review_ids: string[]; limitations: string[];
  validation_passed: boolean; validation_problems: string[]; input_tokens: number; output_tokens: number;
};
export type Alternative = {
  issue_id: string; label: string; case_for: string; why_not_first: string; cited_claim_ids: string[];
};
export type EvalMetric = { name: string; value: string; sample_size: number | null; detail: string | null };
export type TrendPoint = { month: string; topic: string; complaints: number; reviews: number; partial: boolean };
export type ReviewRow = {
  review_id: string; topic: string; intent: string; severity: number; sentiment: number;
  evidence_quote: string; needs_review: boolean; review_rating: number | null;
  review_ts: string | null; cache_source_id: string | null;
};

export const getRun = async () =>
  (await sql`SELECT * FROM pipeline_run ORDER BY created_at DESC LIMIT 1`)[0] as unknown as Run;

export const getRanking = async () =>
  (await sql`SELECT r.rank, r.issue_id, i.label, i.description, r.complaint_count,
                    r.severity_sum, r.mean_severity, r.priority_score
             FROM ranking r JOIN issue i USING (issue_id)
             ORDER BY r.priority_score DESC, r.issue_id ASC`) as unknown as RankRow[];

export const getClaims = async () =>
  (await sql`SELECT claim_id, issue_id, metric, value FROM claim ORDER BY claim_id`) as unknown as Claim[];

export const getMemo = async () =>
  (await sql`SELECT * FROM memo ORDER BY created_at DESC LIMIT 1`)[0] as unknown as Memo | undefined;

export const getAlternatives = async (memoId: number) =>
  (await sql`SELECT a.issue_id, i.label, a.case_for, a.why_not_first, a.cited_claim_ids
             FROM memo_alternative a JOIN issue i USING (issue_id)
             WHERE a.memo_id = ${memoId} ORDER BY a.id`) as unknown as Alternative[];

export const getEvals = async () =>
  (await sql`SELECT name, value, sample_size, detail FROM eval_metric ORDER BY name`) as unknown as EvalMetric[];

export const getTrends = async () =>
  (await sql`SELECT month, topic, complaints, reviews, partial FROM monthly_topic ORDER BY month, topic`) as unknown as TrendPoint[];

/** Severity histogram across completed records, for the overview tiles. */
export const getSeverityMix = async () =>
  (await sql`SELECT severity, count(*)::int AS n FROM review_record
             WHERE status = 'completed' GROUP BY severity ORDER BY severity`) as unknown as { severity: number; n: number }[];

export const getIntentMix = async () =>
  (await sql`SELECT intent, count(*)::int AS n FROM review_record
             WHERE status = 'completed' GROUP BY intent ORDER BY n DESC`) as unknown as { intent: string; n: number }[];

/** Evidence for one issue: highest severity first, the exact saved quotes. */
export const getIssueReviews = async (issueId: string, limit = 50) =>
  (await sql`SELECT rr.review_id, rr.topic, rr.intent, rr.severity, rr.sentiment, rr.evidence_quote,
                    rr.needs_review, rr.review_rating, rr.review_ts, rr.cache_source_id
             FROM membership m JOIN review_record rr USING (review_id)
             WHERE m.issue_id = ${issueId}
             ORDER BY rr.severity DESC, rr.review_id ASC
             LIMIT ${limit}`) as unknown as ReviewRow[];

export const getIssue = async (issueId: string) =>
  (await sql`SELECT r.rank, r.issue_id, i.label, i.description, r.complaint_count, r.severity_sum,
                    r.mean_severity, r.priority_score
             FROM ranking r JOIN issue i USING (issue_id) WHERE r.issue_id = ${issueId}`)[0] as unknown as RankRow | undefined;

/** Named reviews the memo cited, so every citation on the page is clickable. */
export const getReviewsByIds = async (ids: string[]) =>
  ids.length === 0 ? [] :
  (await sql`SELECT review_id, topic, intent, severity, sentiment, evidence_quote, needs_review,
                    review_rating, review_ts, cache_source_id
             FROM review_record WHERE review_id = ANY(${ids})`) as unknown as ReviewRow[];
