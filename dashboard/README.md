# Dashboard, backend and database

**Live: https://dashboard-seven-gamma-14.vercel.app** (public, no login)

Three required pieces, kept deliberately separate:

| Piece | What it is | Where it lives |
|---|---|---|
| **Database** | Postgres holding the processed records, membership, ranking, claims, the AI memo and the evaluation metrics | any Postgres provider |
| **Backend** | Next.js server components + `/api/*` routes. The only thing that talks to Postgres | `lib/db.ts`, `app/api/*` |
| **Dashboard** | Server-rendered pages: overall metrics, issue ranking, AI recommendation, per-issue review evidence | `app/page.tsx`, `app/issue/[id]/page.tsx` |

The database is a **serving layer, not the source of truth**. Every row is derived from the saved
pipeline artifacts in `runs/<run>/` and can be rebuilt with `python3 db/load_db.py`. Nothing on the
dashboard is computed in the browser or hard-coded in the UI.

## 1. Create a Postgres database

Any provider works — `DATABASE_URL` alone decides which driver `lib/db.ts` uses (Neon's HTTP driver
for a `*.neon.tech` host, node-postgres for everything else).

- **Neon via Vercel** (fewest steps): in the Vercel project → **Storage** → **Create Database** →
  Neon. Vercel sets `DATABASE_URL` on the deployment automatically.
- **Neon directly**: console.neon.tech → new project → copy the connection string.
- **Supabase / Railway / Render**: create a Postgres instance and copy its connection string.

## 2. Load the processed data

From the repository root, with the connection string in the root `.env` as `DATABASE_URL=...`:

```bash
python3 db/load_db.py --run runs/main100k
```

This creates the schema (`db/schema.sql`) and bulk-loads every table with `COPY`. It is idempotent —
rerunning drops and reloads from the same saved artifacts. Use `--dry-run` to regenerate
`db/seed/*.csv` without connecting.

## 3. Run locally

```bash
cd dashboard && npm install && echo "DATABASE_URL=<same connection string>" > .env.local && npm run dev
```

Then open http://localhost:3100.

## 4. Deploy

```bash
cd dashboard && npx vercel --prod
```

Set `DATABASE_URL` in the Vercel project's environment variables (skip this if Vercel created the
database for you, which sets it automatically). Put the resulting URL in the root `README.md`.

## API routes (the backend the dashboard reads)

| Route | Returns |
|---|---|
| `GET /api/overview` | run metadata, severity mix, intent mix |
| `GET /api/ranking` | the ranked issue table and every claim |
| `GET /api/memo` | the AI recommendation, alternatives, cited claims and cited reviews |
| `GET /api/trends` | monthly complaint counts with denominators |
| `GET /api/evals` | golden-set and verifier agreement metrics |
| `GET /api/issue/[id]` | one issue plus its member reviews and evidence quotes |

## Design notes

Charts are inline SVG with no charting dependency. Colors come from a validated categorical palette
(six checks passed in light and dark mode, including colorblind separation). Because two light-mode
slots fall below 3:1 contrast against the surface, **every chart ships direct labels and a table
view**, so identity is never carried by color alone. Dark mode is a selected set of steps for the
dark surface, not an automatic inversion.
