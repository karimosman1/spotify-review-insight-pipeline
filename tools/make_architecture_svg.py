"""Generate docs/architecture-light.svg and docs/architecture-dark.svg.

  python3 tools/make_architecture_svg.py

Two files from one source of truth so the README can pair them with <picture> and have the diagram
stay legible in both GitHub themes. `currentColor` is not usable here: GitHub serves README images
as isolated documents, so the SVG cannot inherit the page's foreground colour.
"""

from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent

THEMES = {
    "light": dict(bg="#ffffff", box="#fcfcfb", band="#f4f4f1", border="#d6d5d0",
                  ink="#0b0b0b", mid="#52514e", mute="#76756f",
                  model="#2a78d6", code="#1f6f5c", warn="#b3472f"),
    "dark": dict(bg="#0d1117", box="#1a1a19", band="#17171a", border="#3a3a36",
                 ink="#ffffff", mid="#c3c2b7", mute="#a09f98",
                 model="#6da7ec", code="#5fbfa4", warn="#e08a6a"),
}

W, H = 980, 1114
BX, BW = 20, 598          # stage column
AX, AW = 648, 312         # artifact column
TOP = 128                 # first stage y
PITCH, BH = 126, 96

STAGES = [
    dict(n="1", name="PREPARE", owner="code",
         code="read every row · SHA-256 per row · empty text → quarantine · group exact duplicates · build pending queue",
         model=None,
         retry="malformed CSV aborts before any spend",
         art=["grading/ingestion.json", "data/analysis_manifest.json"],
         flow="77,991 distinct texts queued"),
    dict(n="2", name="ENRICH", owner="both",
         code="validate schema · evidence quote = exact substring · entity match · cache lookup · atomic save per request",
         model="Jev jev-1.13.0 · topic, intent, severity, sentiment · 10 reviews per request, rubric sent once",
         retry="invalid output → 1 retry → quarantine   ·   429/5xx → 3 tries, backoff+jitter   ·   spend cap → stop and save",
         art=["results.jsonl", "cache.jsonl  (exact-text reuse)", "calls.jsonl  (every attempt)"],
         flow="100,000 completed records"),
    dict(n="3", name="VERIFY", owner="both",
         code="deterministic 1% sample · compares the two answers · records every disagreement",
         model="Jev verify-p1 · separately worded · sees the review text only, never the first answer",
         retry="failed call is logged and skipped; the run continues",
         art=["verify_report.json", "verify_results.jsonl"],
         flow="completed complaint + cancellation records"),
    dict(n="4", name="GROUP", owner="both",
         code="membership is deterministic: one issue per primary topic · model output cannot change it",
         model="Claude Haiku group-p1 · names and describes issues from bounded example quotes",
         retry="invented issue id → rejected, falls back to the topic name",
         art=["membership.csv", "issues.json"],
         flow="issue membership"),
    dict(n="5", name="RANK", owner="code",
         code="priority_score = complaint_count × mean_severity = severity_sum · ties by issue_id · no model call",
         model=None,
         retry="pure function of saved records — regenerates identically, offline",
         art=["ranking.csv", "claims.csv"],
         flow="ranked aggregates + claim ids"),
    dict(n="6", name="RECOMMEND", owner="both",
         code="checks every claim id, review id and number against saved calculations · rejects derived figures",
         model="Claude Haiku memo-p2 · reads ONLY the ranked table and a bounded evidence pack",
         retry="validation failure is published as failed, never silently accepted",
         art=["memo.md", "memo_model_output.json"],
         flow="validated recommendation"),
]


def esc(s):
    return escape(str(s))


def svg(t):
    o = []
    a = o.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'role="img" aria-label="Six-stage pipeline: code owns record accounting, caching, validation '
      f'and arithmetic while models read language only; each stage saves an inspectable artifact, and '
      f'the saved results load into Postgres, served by a Next.js backend to a public dashboard.">')
    a(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    a(f'<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
      f'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{t["mid"]}"/></marker>'
      f'<marker id="arm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
      f'orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9 z" fill="{t["mute"]}"/></marker></defs>')
    a(f'<g font-family="ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,sans-serif">')

    # ---- source
    a(f'<rect x="{BX}" y="24" width="{BW}" height="70" rx="8" fill="{t["band"]}" stroke="{t["border"]}"/>')
    a(f'<text x="{BX+16}" y="48" font-size="13" font-weight="600" fill="{t["ink"]}">'
      f'spotify_reviews_18months.csv — 660,622 rows, SHA-256 verified</text>')
    a(f'<text x="{BX+16}" y="68" font-size="11.5" fill="{t["mid"]}">'
      f'full file profiled and accounted for; declared scope sampled by lowest SHA-256(seed + review_id)</text>')
    a(f'<text x="{BX+16}" y="85" font-size="11.5" fill="{t["mid"]}">'
      f'→ data/analysis_100k.csv — 100,013 rows (100,000 nonempty + all 13 empty)</text>')

    # ---- stages
    for i, s in enumerate(STAGES):
        y = TOP + i * PITCH
        a(f'<rect x="{BX}" y="{y}" width="{BW}" height="{BH}" rx="8" fill="{t["box"]}" stroke="{t["border"]}"/>')
        a(f'<text x="{BX+16}" y="{y+23}" font-size="13.5" font-weight="700" fill="{t["ink"]}">'
          f'{s["n"]} · {esc(s["name"])}</text>')
        badge = {"code": ("CODE ONLY", t["code"]), "both": ("CODE + MODEL", t["model"]),
                 }[s["owner"]]
        a(f'<text x="{BX+BW-14}" y="{y+23}" font-size="10.5" font-weight="700" text-anchor="end" '
          f'fill="{badge[1]}">{badge[0]}</text>')
        ty = y + 44
        if s["model"]:
            a(f'<circle cx="{BX+21}" cy="{ty-4}" r="3.5" fill="{t["model"]}"/>')
            a(f'<text x="{BX+32}" y="{ty}" font-size="11" fill="{t["mid"]}">'
              f'<tspan fill="{t["model"]}" font-weight="600">model </tspan>{esc(s["model"])}</text>')
            ty += 18
        a(f'<circle cx="{BX+21}" cy="{ty-4}" r="3.5" fill="{t["code"]}"/>')
        a(f'<text x="{BX+32}" y="{ty}" font-size="11" fill="{t["mid"]}">'
          f'<tspan fill="{t["code"]}" font-weight="600">code </tspan>{esc(s["code"])}</text>')
        a(f'<text x="{BX+32}" y="{y+BH-12}" font-size="10" fill="{t["warn"]}">'
          f'stop / retry: {esc(s["retry"])}</text>')

        # artifact card
        ah = 30 + 16 * len(s["art"])
        ay = y + (BH - ah) / 2
        a(f'<rect x="{AX}" y="{ay}" width="{AW}" height="{ah}" rx="7" fill="none" '
          f'stroke="{t["border"]}" stroke-dasharray="4 3"/>')
        a(f'<text x="{AX+13}" y="{ay+19}" font-size="10" font-weight="600" fill="{t["mute"]}" '
          f'letter-spacing="0.5">SAVED, INSPECTABLE</text>')
        for j, f in enumerate(s["art"]):
            a(f'<text x="{AX+13}" y="{ay+36+j*16}" font-size="11" font-family="ui-monospace,Menlo,monospace" '
              f'fill="{t["mid"]}">{esc(f)}</text>')
        a(f'<line x1="{BX+BW}" y1="{y+BH/2}" x2="{AX-6}" y2="{ay+ah/2}" stroke="{t["mute"]}" '
          f'stroke-width="1.2" marker-end="url(#arm)"/>')

        # flow arrow to next stage
        if i < len(STAGES) - 1:
            a(f'<line x1="{BX+150}" y1="{y+BH}" x2="{BX+150}" y2="{y+PITCH-2}" stroke="{t["mid"]}" '
              f'stroke-width="1.6" marker-end="url(#ar)"/>')
            a(f'<text x="{BX+162}" y="{y+BH+19}" font-size="10.5" fill="{t["mute"]}">{esc(s["flow"])}</text>')

    # ---- serving band
    sy = TOP + len(STAGES) * PITCH + 4
    a(f'<line x1="{BX+150}" y1="{sy-28}" x2="{BX+150}" y2="{sy-4}" stroke="{t["mid"]}" '
      f'stroke-width="1.6" marker-end="url(#ar)"/>')
    a(f'<text x="{BX+162}" y="{sy-10}" font-size="10.5" fill="{t["mute"]}">'
      f'db/load_db.py — COPY from saved artifacts</text>')
    a(f'<rect x="{BX}" y="{sy}" width="{W-2*BX}" height="124" rx="8" fill="{t["band"]}" stroke="{t["border"]}"/>')
    bw, gap = 282, 26
    boxes = [
        ("Postgres (Supabase)", ["10 tables · 100,013 records", "RLS on, no policies → anon key",
                                 "cannot read it"]),
        ("Next.js backend (Vercel)", ["server-side only · privileged role", "lib/db.ts + 6 /api/* routes",
                                      "queries on every request"]),
        ("Public dashboard", ["metrics · ranking · AI memo", "per-issue review evidence",
                              "no login required"]),
    ]
    for k, (title, lines) in enumerate(boxes):
        x = BX + 18 + k * (bw + gap)
        a(f'<rect x="{x}" y="{sy+18}" width="{bw}" height="88" rx="7" fill="{t["box"]}" stroke="{t["border"]}"/>')
        a(f'<text x="{x+13}" y="{sy+39}" font-size="12" font-weight="700" fill="{t["ink"]}">{esc(title)}</text>')
        for j, ln in enumerate(lines):
            a(f'<text x="{x+13}" y="{sy+57+j*15}" font-size="10.5" fill="{t["mid"]}">{esc(ln)}</text>')
        if k < 2:
            a(f'<line x1="{x+bw+4}" y1="{sy+62}" x2="{x+bw+gap-6}" y2="{sy+62}" stroke="{t["mid"]}" '
              f'stroke-width="1.6" marker-end="url(#ar)"/>')
    a(f'<text x="{BX+18}" y="{sy+122}" font-size="10.5" fill="{t["mute"]}">'
      f'the database is a serving layer, never the source of truth — every row is rebuildable from the saved artifacts above</text>')

    # ---- footer claim
    a(f'<text x="{BX}" y="{H-14}" font-size="11" fill="{t["mid"]}">'
      f'<tspan font-weight="700" fill="{t["code"]}">Code</tspan> owns record accounting, caching, validation, '
      f'arithmetic and control flow.  '
      f'<tspan font-weight="700" fill="{t["model"]}">Models</tspan> only read messy language — '
      f'they never choose what runs next, and never produce a number the memo cites.</text>')
    a("</g></svg>")
    return "\n".join(o)


def main():
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        p = out / f"architecture-{name}.svg"
        p.write_text(svg(theme), encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
