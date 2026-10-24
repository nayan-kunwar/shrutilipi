# Getting started

Run ShrutiLipi locally from a fresh clone. The "it looks broken" cases at the
bottom are all real ones — check there before debugging anything.

## Prerequisites

- **Node.js ≥ 20** — 22.6+ recommended: `node --test` then runs the TypeScript
  tests natively, no framework needed
- **pnpm** — the repo pins the version (`packageManager` in the root
  `package.json`); enable it with `corepack enable`
- **Python 3.11+** — for the FastAPI backend and the CLI
- A YouTube URL to test with. Known-good: **`HHUsHkYhkcM`** (English captions,
  ~969 segments — documented in `docs/operations.md` §7)

## 1. Install (once)

```bash
git clone <repo-url> && cd shrutilipi
pnpm install                                # workspace JS deps
pip install -r apps/api/requirements.txt    # fastapi, uvicorn, ... (venv optional)
```

`pnpm dev` runs `python -m uvicorn` with whatever interpreter is active —
`pip install` goes wherever `python` points.

## 2. Start

```bash
pnpm dev
```

Turborepo starts both halves in parallel:

| | URL | Notes |
|---|---|---|
| Web | http://localhost:3000 | If 3000 is taken, Next takes the next free port (3001, 3002, …) and **prints the one it chose** |
| API | http://localhost:8000 | Probe: `curl http://localhost:8000/api/wake` → `{"ok":true}`; interactive docs at `/docs` |

No env vars are needed locally. Keyless mode fetches YouTube captions directly
(Supadata's key is only for the deployed fallback chain), and rate limiting is
on by default (20 requests / 10 min / IP — misses only). AI summaries are off
until you set `SUMMARY_BASE_URL`, `SUMMARY_API_KEY` and `SUMMARY_MODEL` (see
[Optional: AI summary](#optional-ai-summary)); without them the button shows a
clear "isn't configured" message and transcripts are unaffected.

## 3. Use it

Open the web URL, paste any YouTube link or video ID, **Get transcript** →
copy it, download `.txt` / `.srt` / `.vtt`, or share. Timestamps toggle adds
`[m:ss]` prefixes to the text copy/download **and** turns each timestamp into a
seek button for the embedded player. **Generate summary** (optional) produces a
`TL;DR:` plus bullets on demand; nothing is generated on page load.

## Optional: AI summary

Set all three before `pnpm dev` (PowerShell syntax: `$env:SUMMARY_BASE_URL = "…"`):

```bash
SUMMARY_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \
SUMMARY_API_KEY=<your key> \
SUMMARY_MODEL=gemini-2.5-flash \
pnpm dev
```

Any OpenAI-compatible endpoint works (Groq, OpenRouter, a local server). Missing
any of the three is a supported state: `POST /api/summary` returns
`503 summary_disabled`. Details, limits and cost:
[`operations.md` §9](operations.md#9-on-demand-ai-summary).

PowerShell equivalent (this dev box's default shell):

```powershell
$env:SUMMARY_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
$env:SUMMARY_API_KEY  = "<your key>"
$env:SUMMARY_MODEL    = "gemini-2.5-flash"
pnpm dev
```

## Variants

```bash
# Frontend against the deployed Render API instead of a local one
NEXT_PUBLIC_API_URL=https://shrutilipi-backend.onrender.com pnpm dev
# (first call sleeps ~30-50 s: the UI shows a wake-up card, then retries)

# Separate terminals, if you prefer
cd apps/web && pnpm dev     # frontend only
cd apps/api && pnpm dev     # backend only (uvicorn --reload)

# CLI — same API, no browser (defaults to http://localhost:8000; --api to point elsewhere)
python tools/fetch.py HHUsHkYhkcM --srt --out subs.srt
```

## Checks

| Command | What runs |
|---|---|
| `pnpm test` | 58 pytest (limiter, wake probe, CORS, summary contract/cache/locks, LLM adapter) + 15 `node --test` cases (SRT/VTT + `friendlyError`) |
| `pnpm typecheck` | `tsc --noEmit` across web + shared |
| `pnpm build` | production Next build (stop `next dev` first — they share `.next`) |

## Troubleshooting — the ways it actually breaks

| Symptom | Cause | Fix |
|---|---|---|
| Site loads but every API call fails in the browser console with "Disallowed CORS origin" (and `OPTIONS /api/transcript` returns 400) | The API's CORS allowlist doesn't include the origin the browser is sending — usually after adding a custom domain to Vercel | The production origins are hardcoded in `apps/api/main.py` (`PROD_ORIGINS`), so this means the API hasn't been redeployed with the current code. Redeploy the API on Render. Check: `curl -s -D - -o /dev/null -X OPTIONS https://shrutilipi-backend.onrender.com/api/transcript -H "Origin: https://shrutilipi.nayankunwar.com" -H "Access-Control-Request-Method: GET"` must return `200` with `access-control-allow-origin: https://shrutilipi.nayankunwar.com` |
| Page on 3001/3002 shows "Failed to fetch" + "The API is asleep" while the API logs healthy 200s | CORS: the browser blocked the response (server logs prove it answered) | Should not happen anymore — any localhost port is allowed via `allow_origin_regex` in `apps/api/main.py`. Verify: `curl -s -D - -H "Origin: http://localhost:3001" http://localhost:8000/api/wake \| grep -i access-control` echoes the origin |
| Loads once, then chunks 404 (`main-app.js`, `app-pages-internals.js`) | Corrupted `.next` — usually two `next dev` processes shared the folder | Stop every `next dev`, `rm -rf apps/web/.next`, restart |
| "The API is asleep" card, locally | The API really is down or on another port — the probe fetch failed | `curl http://localhost:8000/api/wake` → must return 200. If not, restart `pnpm dev` |
| Weird double-stack behavior, flaky ports | A second `pnpm dev` while the first still runs (Windows lets two processes bind one port) | `netstat -ano \| findstr ":8000"` → `taskkill /F /T /PID <pid>` on the extra one; keep a single stack |
| uvicorn didn't reload your edit | You're editing files the reloader isn't watching, or the terminal died | The terminal running `pnpm dev` must stay alive; watch for `WatchFiles detected changes` |
| `Generate summary` says summary generation isn't configured | No `SUMMARY_*` env — this is the intended default, not a bug | Set all three vars and restart the API ([§9](operations.md#9-on-demand-ai-summary)) |
| Summary says "already being generated" / "generated a lot of summaries" | `summary_busy` = same video is mid-generation; `summary_rate_limited` = 5 per 10 min per IP, attempt-counted | Wait for the lock (≤30 s) or the window; the transcript still works either way |

## Stop

Ctrl+C in the terminal running `pnpm dev`. If a server ever outlives its
terminal (orphaned dev process):

```powershell
netstat -ano | findstr ":3001 :8000"     # find the PIDs
taskkill /F /T /PID <pid>
```

Ports free = project fully stopped. Start again with `pnpm dev`.
