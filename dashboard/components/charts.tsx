// Inline-SVG charts. Thin marks, 4px rounded data-ends anchored to the baseline, recessive
// axes, direct labels on every bar (the light-mode contrast relief rule), and a table view
// beside each chart so identity is never carried by color alone.
import type { RankRow, TrendPoint } from "@/lib/db";

const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export function RankedBars({ rows }: { rows: RankRow[] }) {
  const w = 980, rowH = 34, padL = 168, padR = 128, padT = 10;
  const h = padT + rows.length * rowH + 6;
  const max = Math.max(...rows.map((r) => r.priority_score), 1);
  const scale = (v: number) => Math.max(3, (v / max) * (w - padL - padR));
  return (
    <>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img"
           aria-label="Issues ranked by priority score, which is complaint count times mean severity">
        {rows.map((r, i) => {
          const y = padT + i * rowH;
          const bw = scale(r.priority_score);
          return (
            <g key={r.issue_id}>
              <text x={padL - 12} y={y + 15} textAnchor="end" fontSize="13" fill="var(--text-primary)">
                {r.label}
              </text>
              <text x={padL - 12} y={y + 28} textAnchor="end" fontSize="11" fill="var(--text-muted)">
                {r.issue_id}
              </text>
              {/* 2px surface gap between adjacent bars comes from the row pitch vs bar height */}
              <rect x={padL} y={y + 5} width={bw} height={20} rx="4"
                    fill={i === 0 ? "var(--seq-500)" : "var(--seq-300)"} />
              <text x={padL + bw + 10} y={y + 19} fontSize="12.5" fill="var(--text-primary)"
                    fontVariant="tabular-nums">
                {r.priority_score.toLocaleString()}
              </text>
              <text x={padL + bw + 10} y={y + 19} dx={String(r.priority_score).length * 7.6 + 14}
                    fontSize="11.5" fill="var(--text-muted)">
                {r.complaint_count.toLocaleString()} × {Number(r.mean_severity).toFixed(2)}
              </text>
            </g>
          );
        })}
      </svg>
      <details className="table-view">
        <summary>Table view</summary>
        <table>
          <thead><tr><th>Rank</th><th>Issue</th><th className="num">Complaints</th>
            <th className="num">Mean severity</th><th className="num">Priority</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.issue_id}>
                <td className="num">{r.rank}</td>
                <td><a href={`/issue/${r.issue_id}`}>{r.label}</a> <span className="mono">{r.issue_id}</span></td>
                <td className="num">{r.complaint_count.toLocaleString()}</td>
                <td className="num">{r.mean_severity}</td>
                <td className="num">{r.priority_score.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}

export function TrendLines({ points, topics }: { points: TrendPoint[]; topics: string[] }) {
  const months = [...new Set(points.map((p) => p.month))].sort();
  const w = 980, h = 260, padL = 46, padR = 104, padT = 14, padB = 34;
  const byTopic = topics.map((t) => ({
    topic: t,
    values: months.map((m) => {
      const p = points.find((x) => x.month === m && x.topic === t);
      return { month: m, share: p && p.reviews ? (p.complaints / p.reviews) * 100 : 0, partial: p?.partial ?? false };
    }),
  }));
  const max = Math.max(...byTopic.flatMap((s) => s.values.map((v) => v.share)), 1);
  const x = (i: number) => padL + (i * (w - padL - padR)) / Math.max(1, months.length - 1);
  const y = (v: number) => padT + (1 - v / max) * (h - padT - padB);
  const ticks = [0, max / 2, max];
  return (
    <>
      <div className="legend">
        {byTopic.map((s, i) => (
          <span key={s.topic}>
            <i className="swatch" style={{ background: SERIES[i % SERIES.length] }} />{s.topic}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img"
           aria-label="Complaint share by topic for each month, with partial first and last months">
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={w - padR} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth="1" />
            <text x={padL - 8} y={y(t) + 4} textAnchor="end" fontSize="11" fill="var(--text-muted)">
              {t.toFixed(0)}%
            </text>
          </g>
        ))}
        {months.map((m, i) =>
          i % 3 === 0 || i === months.length - 1 ? (
            <text key={m} x={x(i)} y={h - 12} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
              {m}
            </text>
          ) : null
        )}
        {byTopic.map((s, si) => {
          const d = s.values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v.share)}`).join(" ");
          const last = s.values[s.values.length - 1];
          return (
            <g key={s.topic}>
              <path d={d} fill="none" stroke={SERIES[si % SERIES.length]} strokeWidth="2"
                    strokeLinejoin="round" strokeLinecap="round" />
              {s.values.map((v, i) =>
                v.partial ? (
                  <circle key={i} cx={x(i)} cy={y(v.share)} r="4"
                          fill="var(--surface-1)" stroke={SERIES[si % SERIES.length]} strokeWidth="2" />
                ) : null
              )}
              {/* direct label: identity never depends on color alone */}
              <text x={w - padR + 8} y={y(last.share) + 4} fontSize="12" fill="var(--text-primary)">
                {s.topic} <tspan fill="var(--text-muted)">{last.share.toFixed(1)}%</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <p className="note">
        Hollow markers mark the first and last calendar months, which are partial in the source window
        (2022-05-17 to 2023-11-15). Share = complaint and cancellation records ÷ all classified reviews
        that month; denominators are in the table view.
      </p>
      <details className="table-view">
        <summary>Table view (with denominators)</summary>
        <table>
          <thead><tr><th>Month</th>{topics.map((t) => <th key={t} className="num">{t}</th>)}
            <th className="num">Reviews</th></tr></thead>
          <tbody>
            {months.map((m) => {
              const reviews = points.find((p) => p.month === m)?.reviews ?? 0;
              const partial = points.find((p) => p.month === m)?.partial;
              return (
                <tr key={m}>
                  <td>{m}{partial ? " (partial)" : ""}</td>
                  {topics.map((t) => {
                    const p = points.find((x) => x.month === m && x.topic === t);
                    return <td key={t} className="num">{p ? p.complaints.toLocaleString() : "0"}</td>;
                  })}
                  <td className="num">{reviews.toLocaleString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </details>
    </>
  );
}

export function SeverityBar({ mix }: { mix: { severity: number; n: number }[] }) {
  const total = mix.reduce((a, b) => a + b.n, 0) || 1;
  const steps = ["var(--seq-150)", "var(--seq-300)", "var(--series-4)", "var(--series-2)", "var(--critical)"];
  return (
    <>
      <div style={{ display: "flex", gap: 2, marginTop: 6 }}>
        {mix.map((m) => (
          <div key={m.severity}
               style={{ width: `${(m.n / total) * 100}%`, height: 22, background: steps[m.severity - 1],
                        borderRadius: m.severity === 1 ? "4px 0 0 4px" : m.severity === 5 ? "0 4px 4px 0" : 0 }}
               title={`Severity ${m.severity}: ${m.n.toLocaleString()}`} />
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 8, flexWrap: "wrap", fontSize: 12.5,
                    color: "var(--text-secondary)" }}>
        {mix.map((m) => (
          <span key={m.severity} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <i className="swatch" style={{ background: steps[m.severity - 1] }} />
            sev {m.severity}: {m.n.toLocaleString()} ({((m.n / total) * 100).toFixed(1)}%)
          </span>
        ))}
      </div>
    </>
  );
}
