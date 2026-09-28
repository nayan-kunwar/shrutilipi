# ShrutiLipi

Paste a YouTube URL → get a copyable transcript. v1 = captions-only.

Monorepo: **pnpm workspaces + Turborepo.** `apps/web` (Next.js, Vercel) + `apps/api`
(FastAPI, Render) + `packages/shared` (the API contract every client depends on).

```
apps/
  web/      Next.js 14 App Router
  api/      FastAPI backend (Python)
packages/
  shared/   @shrutilipi/shared — types, friendlyError, formatTime
  tsconfig/ @shrutilipi/tsconfig — shared TS config
tools/      stdlib-only CLI (fetch.py)
```

## Local dev (2 terminals)

Install once from the repo root:

```bash
pnpm install
```

Terminal 1 — backend (from `apps/api`):

```powershell
pip install -r requirements.txt
$env:FRONTEND_URL="http://localhost:3000"
pnpm dev
# health: http://localhost:8000/health
```

Terminal 2 — frontend (from `apps/web`):

```powershell
copy .env.example .env.local
pnpm dev
# app: http://localhost:3000
```

Or run both from the repo root with `pnpm dev` (Turborepo runs them in parallel).

Test the API directly:

```bash
curl "http://localhost:8000/api/transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Scripts (repo root)

| Command | What it does |
|---|---|
| `pnpm dev` | Both apps in parallel via Turbo |
| `pnpm build` | Builds the shared package, then the web app |
| `pnpm typecheck` | `tsc --noEmit` across the TS packages |
| `pnpm test` | Test pipeline (nothing wired up yet) |
| `pnpm clean` | Drop build output and `node_modules` |

## Deploy

- **Render (backend):** New Web Service → this repo → Root Directory `apps/api` → Runtime Docker → env `FRONTEND_URL=https://YOUR-APP.vercel.app`
- **Vercel (frontend):** Import repo → Root Directory `apps/web` → env `NEXT_PUBLIC_API_URL=https://YOUR-API.onrender.com`

Vercel detects pnpm from the root `pnpm-lock.yaml`; the `packageManager` field in the
root `package.json` pins the version.

## v2 (Whisper fallback)

Add `WhisperProvider` behind `TranscriptProvider` in `apps/api/services/providers.py`.
No frontend change needed — if it also needs to be usable from the CLI, add it to
`packages/shared` at the same time.
