import { getIssue, getIssueReviews } from "@/lib/db";
import { notFound } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function IssuePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const issue = await getIssue(id);
  if (!issue) notFound();
  const reviews = await getIssueReviews(id, 60);

  return (
    <main>
      <section>
        <p className="note"><a href="/">← Back to dashboard</a></p>
        <h2>{issue.label} <span className="mono" style={{ color: "var(--text-muted)" }}>{issue.issue_id}</span></h2>
        <p className="note">{issue.description}</p>
        <div className="tiles">
          <div className="card tile"><div className="k">Rank</div><div className="v">{issue.rank}</div></div>
          <div className="card tile">
            <div className="k">Complaints</div>
            <div className="v">{issue.complaint_count.toLocaleString()}</div>
            <div className="d">complaint + cancellation records</div>
          </div>
          <div className="card tile">
            <div className="k">Mean severity</div>
            <div className="v">{Number(issue.mean_severity).toFixed(2)}</div>
            <div className="d">severity sum {issue.severity_sum.toLocaleString()}</div>
          </div>
          <div className="card tile">
            <div className="k">Priority score</div>
            <div className="v">{issue.priority_score.toLocaleString()}</div>
            <div className="d">count × mean severity</div>
          </div>
        </div>
      </section>

      <section>
        <h2>Member reviews</h2>
        <p className="note">
          Highest severity first, {reviews.length} of {issue.complaint_count.toLocaleString()} shown. Each quote is an
          exact substring of the original review text, extracted by code rather than written by a model.
        </p>
        <div className="card">
          <table>
            <thead>
              <tr><th>Review ID</th><th className="num">Sev</th><th>Intent</th><th className="num">Stars</th>
                <th>Evidence quote</th><th>Flags</th></tr>
            </thead>
            <tbody>
              {reviews.map((r) => (
                <tr key={r.review_id}>
                  <td className="mono">{r.review_id.slice(0, 8)}…</td>
                  <td className="num">{r.severity}</td>
                  <td>{r.intent}</td>
                  <td className="num">{r.review_rating ?? "—"}</td>
                  <td style={{ maxWidth: 480, color: "var(--text-secondary)" }}>{r.evidence_quote}</td>
                  <td>
                    {r.needs_review && <span className="chip warn">needs review</span>}
                    {r.cache_source_id && <span className="chip" title={`exact-text reuse of ${r.cache_source_id}`}>cached</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
