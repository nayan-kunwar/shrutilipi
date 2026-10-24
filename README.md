# ShrutiLipi

Paste a YouTube URL → get a transcript you can copy or download as `.txt` / `.srt` / `.vtt`, plus an optional AI summary generated only when you click the button. The page embeds the video: turn on Timestamps and click any timestamp to seek the player. Transcript extraction is captions-only.

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

The backend's transcript providers are in `apps/api/services/` (chain, rate
limiter, YouTube parsing); the optional summarizer is `services/summarize.py`.

## Local dev

```bash
pnpm install                                # workspace JS deps (once)
pip install -r apps/api/requirements.txt    # backend deps (once)
pnpm dev                                    # web + api in parallel
```

Open the URL Next prints — `http://localhost:3000`, or the next free port if
3000 is taken (every localhost port is CORS-safe). API probe:
`curl http://localhost:8000/api/wake`. No env vars are required locally: the
summary button explains that it isn't configured until the three `SUMMARY_*`
vars below are set.

**Full walkthrough + troubleshooting: [`docs/getting-started.md`](docs/getting-started.md).**

Test the API directly:

```bash
curl "http://localhost:8000/api/transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Optional: AI summary

The transcript is free; a summary calls an LLM, so it only runs when the user
clicks **Generate summary**. The backend talks to any OpenAI-compatible chat
endpoint, selected by env (Gemini Flash, Groq, OpenRouter, a local server, …):

```bash
# apps/api, before `pnpm dev` (or in Render's dashboard)
SUMMARY_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
SUMMARY_API_KEY=<key>
SUMMARY_MODEL=gemini-2.5-flash
```

Missing any of the three ⇒ `POST /api/summary` returns `503 summary_disabled`
and transcripts keep working. The client sends only `{videoId, lang}` — never
transcript text — so the API is not an open LLM proxy. Limits, cache, privacy,
truncation and the cost formula are in
[`docs/operations.md` §9](docs/operations.md#9-on-demand-ai-summary).

## Scripts (repo root)

| Command | What it does |
|---|---|
| `pnpm dev` | Both apps in parallel via Turbo |
| `pnpm build` | Shared + web production build, plus a `py_compile` syntax check for the API |
| `pnpm typecheck` | `tsc --noEmit` across the TS packages |
| `pnpm test` | pytest (58) + `node --test` cases (15), via Turbo |
| `pnpm clean` | Drop build output and `node_modules` |

## Deploy

- **Render (backend):** New Web Service → this repo → Root Directory `apps/api` → Runtime Docker → env `FRONTEND_URL=https://shrutilipi.nayankunwar.com,https://shrutilipi-rho.vercel.app`
- **Vercel (frontend):** Import repo → Root Directory `apps/web` → env `NEXT_PUBLIC_API_URL=https://shrutilipi-backend.onrender.com`

`FRONTEND_URL` is a comma-separated list of allowed frontend origins. The production
origins are also hardcoded in the API (`apps/api/main.py`), so this env var can only
*add* origins — it can no longer lock the site out of its own API.

The summary feature is optional and off unless `SUMMARY_BASE_URL`,
`SUMMARY_API_KEY` and `SUMMARY_MODEL` are set on Render (`render.yaml` declares
them with `sync: false`, so the blueprint prompts for them). See
[`docs/operations.md` §9](docs/operations.md#9-on-demand-ai-summary).

Vercel detects pnpm from the root `pnpm-lock.yaml`; the `packageManager` field in the
root `package.json` pins the version.

## v2 (Whisper fallback)

Add `WhisperProvider` behind `TranscriptProvider` in `apps/api/services/providers.py`.
No frontend change needed — if it also needs to be usable from the CLI, add it to
`packages/shared` at the same time.
