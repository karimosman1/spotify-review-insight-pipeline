import {
  getRun, getRanking, getClaims, getMemo, getAlternatives, getEvals, getTrends,
  getSeverityMix, getIntentMix, getReviewsByIds,
} from "@/lib/db";
import { RankedBars, TrendLines, SeverityBar } from "@/components/charts";

export const dynamic = "force-dynamic";

const pct = (v: string) => `${(Number(v) * 100).toFixed(1)}%`;

export default async function Page() {
  const [run, ranking, claims, memo, evals, trends, sevMix, intentMix] = await Promise.all([
    getRun(), getRanking(), getClaims(), getMemo(), getEvals(), getTrends(), getSeverityMix(), getIntentMix(),
  ]);
  const alternatives = memo ? await getAlternatives(memo.id) : [];
  const citedReviews = memo ? await getReviewsByIds(memo.cited_review_ids) : [];
  const claimById = Object.fromEntries(claims.map((c) => [c.claim_id, c]));
  const top = ranking[0];
  const complaints = intentMix.filter((i) => i.intent === "complaint" || i.intent === "cancellation")
    .reduce((a, b) => a + b.n, 0);
  const topTopics = ranking.slice(0, 4).map((r) => r.issue_id.replace("ISS-", ""));
  const evalBy = Object.fromEntries(evals.map((e) => [e.name, e]));

  return (
    <main>
      {/* ---------- overall metrics ---------- */}
      <section>
        <h2>Overall metrics</h2>
        <p className="note">
          Run <span className="mono">{run.run_id}</span> · scope <span className="mono">{run.scope}</span> ·
          labels <span className="mono">{run.label_config}</span>
        </p>
        <div className="tiles">
          <div className="card tile">
            <div className="k">Reviews classified</div>
            <div className="v">{run.completed.toLocaleString()}</div>
            <div className="d">of {run.analysis_rows.toLocaleString()} in scope · {run.quarantined} quarantined</div>
          </div>
          <div className="card tile">
            <div className="k">Complaints &amp; cancellations</div>
            <div className="v">{complaints.toLocaleString()}</div>
            <div className="d">{((complaints / run.completed) * 100).toFixed(1)}% of classified reviews</div>
          </div>
          <div className="card tile">
            <div className="k">Top priority</div>
            <div className="v" style={{ fontSize: 20 }}>{top.label}</div>
            <div className="d">score {top.priority_score.toLocaleString()} · rank 1 of {ranking.length}</div>
          </div>
          <div className="card tile">
            <div className="k">Model cost</div>
            <div className="v">${Number(run.api_cost_usd).toFixed(2)}</div>
            <div className="d">{run.enrich_requests.toLocaleString()} requests · {(Number(run.wall_clock_s) / 60).toFixed(0)} min · {run.workers} workers</div>
          </div>
          <div className="card tile">
            <div className="k">Exact-text reuse</div>
            <div className="v">{run.cache_reuse_records.toLocaleString()}</div>
            <div className="d">{run.distinct_texts.toLocaleString()} distinct texts classified</div>
          </div>
        </div>
        <div className="card" style={{ marginTop: 12 }}>
          <h3>Severity mix across classified reviews</h3>
          <SeverityBar mix={sevMix} />
        </div>
      </section>

      {/* ---------- ranking ---------- */}
      <section>
        <h2>Issue ranking</h2>
        <p className="note">
          priority score = complaint count × mean severity (= severity sum). Ties break on issue ID.
          Recomputed deterministically from saved records; no model is involved in this number.
        </p>
        <div className="card"><RankedBars rows={ranking} /></div>
      </section>

      {/* ---------- AI recommendation ---------- */}
      <section>
        <h2>AI-generated recommendation</h2>
        {!memo ? <p className="note">No memo loaded.</p> : (
          <>
            <p className="note">
              Written by <span className="mono">{memo.model}</span> from the ranked table and a bounded
              evidence pack only — it never saw the raw corpus.{" "}
              {memo.validation_passed
                ? <span className="chip ok">code validation passed: every claim ID, review ID and number traced to a saved calculation</span>
                : <span className="chip warn">validation problems: {memo.validation_problems.join("; ")}</span>}
            </p>
            <div className="card">
              <h3 style={{ fontSize: 17 }}>{memo.headline}</h3>
              <p style={{ marginTop: 0 }}>
                <span className="chip">recommends {memo.issue_id}</span>
              </p>
              <p>{memo.rationale}</p>
              <h3 style={{ marginTop: 18 }}>Supporting numbers</h3>
              <table>
                <thead><tr><th>Claim</th><th>Issue</th><th>Metric</th><th className="num">Value</th></tr></thead>
                <tbody>
                  {memo.cited_claim_ids.map((cid) => {
                    const c = claimById[cid];
                    return c ? (
                      <tr key={cid}>
                        <td className="mono">{cid}</td>
                        <td><a href={`/issue/${c.issue_id}`}>{c.issue_id}</a></td>
                        <td>{c.metric}</td>
                        <td className="num">{c.value}</td>
                      </tr>
                    ) : null;
                  })}
                </tbody>
              </table>
              {citedReviews.length > 0 && (
                <>
                  <h3 style={{ marginTop: 18 }}>Cited review evidence</h3>
                  {citedReviews.map((r) => (
                    <div key={r.review_id} style={{ marginBottom: 10 }}>
                      <span className="mono">{r.review_id}</span>{" "}
                      <span className="chip">severity {r.severity}</span>{" "}
                      <span className="chip">{r.intent}</span>
                      <div className="quote">{r.evidence_quote}</div>
                    </div>
                  ))}
                </>
              )}
              <h3 style={{ marginTop: 18 }}>Alternatives considered</h3>
              {alternatives.map((a) => (
                <div key={a.issue_id} style={{ marginBottom: 12 }}>
                  <strong>{a.label}</strong>{" "}
                  <a className="mono" href={`/issue/${a.issue_id}`}>{a.issue_id}</a>
                  <div>{a.case_for}</div>
                  <div style={{ color: "var(--text-secondary)" }}><em>Why not first:</em> {a.why_not_first}</div>
                  <div style={{ marginTop: 4 }}>
                    {a.cited_claim_ids.map((cid) => (
                      <span key={cid} className="chip" style={{ marginRight: 5 }}>
                        {cid}: {claimById[cid]?.value ?? "?"}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              <h3 style={{ marginTop: 18 }}>Limitations</h3>
              <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text-secondary)" }}>
                {memo.limitations.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </div>
          </>
        )}
      </section>

      {/* ---------- trend ---------- */}
      <section>
        <h2>Complaint share over time</h2>
        <p className="note">Top four issues by priority. Compare months of comparable length only.</p>
        <div className="card"><TrendLines points={trends} topics={topTopics} /></div>
      </section>

      {/* ---------- evaluation ---------- */}
      <section>
        <h2>How far to trust these labels</h2>
        <p className="note">
          Measured, not asserted. Golden-set figures compare the model against 50 reviews hand-labeled by
          the author; verifier figures compare two independent model roles on a random 1% sample.
        </p>
        <div className="grid2">
          <div className="card">
            <h3>Golden set (50 hand labels)</h3>
            <table>
              <tbody>
                <tr><td>Topic agreement</td><td className="num">{pct(evalBy.golden_topic_agreement?.value ?? "0")}</td></tr>
                <tr><td>Intent agreement</td><td className="num">{pct(evalBy.golden_intent_agreement?.value ?? "0")}</td></tr>
                <tr><td>Severity exact match</td><td className="num">{pct(evalBy.golden_severity_agreement?.value ?? "0")}</td></tr>
                <tr><td>Severity mean absolute error</td><td className="num">{Number(evalBy.golden_severity_mae?.value ?? 0).toFixed(2)}</td></tr>
              </tbody>
            </table>
            <p className="note" style={{ marginTop: 10, marginBottom: 0 }}>
              50 cases is a small diagnostic sample, not a population accuracy estimate.
            </p>
          </div>
          <div className="card">
            <h3>Independent verifier ({evalBy.verifier_topic_agreement?.sample_size?.toLocaleString()} reviews)</h3>
            <table>
              <tbody>
                <tr><td>Topic agreement</td><td className="num">{pct(evalBy.verifier_topic_agreement?.value ?? "0")}</td></tr>
                <tr><td>Intent agreement</td><td className="num">{pct(evalBy.verifier_intent_agreement?.value ?? "0")}</td></tr>
                <tr><td>Severity agreement</td><td className="num">{pct(evalBy.verifier_severity_agreement?.value ?? "0")}</td></tr>
                <tr><td>Flagged for human review</td><td className="num">{Number(evalBy.needs_review_flagged?.value ?? 0).toLocaleString()}</td></tr>
              </tbody>
            </table>
            <p className="note" style={{ marginTop: 10, marginBottom: 0 }}>
              A second model role re-labels from the original text alone, without seeing the first answer.
            </p>
          </div>
        </div>
      </section>

      <p className="foot">
        Scope: {run.analysis_rows.toLocaleString()} reviews sampled deterministically from the{" "}
        {run.source_rows.toLocaleString()}-row course extract (May 2022 – Nov 2023).
        Source SHA-256 <span className="mono">{run.source_sha256.slice(0, 16)}…</span> ·
        analysis SHA-256 <span className="mono">{run.analysis_sha256.slice(0, 16)}…</span>.
        These are self-selected public app reviews: no revenue, plan tier, confirmed cancellations, or
        complete customer population. Cancellation language is stated intent, not observed churn.
      </p>
    </main>
  );
}
