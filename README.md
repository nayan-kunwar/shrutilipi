# ShrutiLipi

Paste a YouTube URL → get a transcript you can copy or download as `.txt` / `.srt` / `.vtt`. v1 = captions-only.

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

## Local dev

```bash
pnpm install                                # workspace JS deps (once)
pip install -r apps/api/requirements.txt    # backend deps (once)
pnpm dev                                    # web + api in parallel
```

Open the URL Next prints — `http://localhost:3000`, or the next free port if
3000 is taken (every localhost port is CORS-safe). API probe:
`curl http://localhost:8000/api/wake`. No env vars needed locally.

**Full walkthrough + troubleshooting: [`docs/getting-started.md`](docs/getting-started.md).**

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
| `pnpm test` | pytest (29) + `node --test` formatter tests (11), via Turbo |
| `pnpm clean` | Drop build output and `node_modules` |

## Deploy

- **Render (backend):** New Web Service → this repo → Root Directory `apps/api` → Runtime Docker → env `FRONTEND_URL=https://shrutilipi.nayankunwar.com,https://shrutilipi-rho.vercel.app`
- **Vercel (frontend):** Import repo → Root Directory `apps/web` → env `NEXT_PUBLIC_API_URL=https://shrutilipi-backend.onrender.com`

`FRONTEND_URL` is a comma-separated list of allowed frontend origins. The production
origins are also hardcoded in the API (`apps/api/main.py`), so this env var can only
*add* origins — it can no longer lock the site out of its own API.

Vercel detects pnpm from the root `pnpm-lock.yaml`; the `packageManager` field in the
root `package.json` pins the version.

## v2 (Whisper fallback)

Add `WhisperProvider` behind `TranscriptProvider` in `apps/api/services/providers.py`.
No frontend change needed — if it also needs to be usable from the CLI, add it to
`packages/shared` at the same time.
