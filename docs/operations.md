# ShrutiLipi — Operations Notes

Everything future-us needs: env, deploy flow, provider chain rules, known traps.

Last verified: commit `2fdeaf5` (2026-09-26).

---

## 1. Identity

| Thing | Value |
|---|---|
| Display name | **ShrutiLipi** (camel-case; never `shrutilipi` in UI copy) |
| Code slugs | `shrutilipi`, `shrutilipi-frontend`, `shrutilipi-backend` |
| Repo | `git@github.com-personal:nayan-kunwar/shrutilipi.git`, branch `main` |
| Frontend | https://frontend-six-woad-540yl4bn2c.vercel.app (Vercel, **keep this domain**) |
| Backend | https://shrutilipi-backend.onrender.com (Render free, Docker) |
| Commit convention | Conventional commits; user says **"commit and p"** → commit + push. Never commit unasked. |

---

## 2. Architecture

- **Frontend**: Next.js 14 App Router, `frontend/`, static export (`npm run build` → `/` ≈ 3.4 kB).
- **Backend**: FastAPI, `backend/`, Docker (`python`, 3.11). Dependencies pinned: `youtube-transcript-api==1.2.4`, `httpx==0.28.1` — hosted providers use plain `httpx`, no new deps.
- **API**:
  - `GET /health` → `{"ok": true}`
  - `GET /api/transcript?url=<youtube-url-or-id>&lang=<code>` → `{videoId, title, language, plainText, segments[]}` (`segments[i] = {start, duration, text}` in seconds)
- **Cache**: in-memory TTL dict, **24h** (`CACHE_TTL` in `backend/main.py`), key `videoId:lang`. Restart clears it.
- **Title**: best-effort via YouTube oEmbed (no key); may be `null` → frontend falls back to showing `videoId`.

---

## 3. Provider chain (the core mechanism)

`build_provider()` in `backend/services/providers.py` reads env at process start (not per-request — env changes need a redeploy).

### Levels

| Level | Source | Handles not-found? | Notes |
|---|---|---|---|
| `direct` | `youtube-transcript-api` via Webshare proxies (legacy) | yes | **Blocked on Render's datacenter IP.** Skipped when `DIRECT_ENABLED=false`. |
| `supadata` | `GET https://api.supadata.ai/v1/transcript?url=...&lang=...`, header `x-api-key` | **yes** (AI retranscribes missing captions) | Primary. Free tier, no card, 100 req/mo. Response: `{lang, content:[{text, offset(ms), duration(ms)}]}` → normalized to seconds. |
| `serpapi` | `GET https://serpapi.com/search?engine=youtube_video_transcript&v=<id>&language_code=...&api_key=...` | **no** | Last resort. Free tier 100 req/mo, cardless. Default **OFF** (`SERPAPI_ENABLED` defaults false). Units unknown → see `SERPAPI_TIME_UNIT`. |

### Env vars (all read in code, no secrets in repo)

| Var | Default | Render value | Meaning |
|---|---|---|---|
| `CHAIN_ORDER` | `direct,supadata,serpapi` | `supadata,serpapi` | Comma-separated try-order; unknowns/dupes ignored; empty → warn + fallback direct-only |
| `DIRECT_ENABLED` | `true` | **`false`** | Render IP is YouTube-blocked; flip to `true` later via env only |
| `SUPADATA_API_KEY` | — | **secret, required** | Supadata dashboard key |
| `SUPADATA_ENABLED` | `true` | leave unset | |
| `SERPAPI_API_KEY` | — | secret, optional backup | |
| `SERPAPI_ENABLED` | **`false`** | `true` only if key set | **Gotcha:** key alone does nothing without this flag |
| `SERPAPI_TIME_UNIT` | `auto` | leave unset | `auto` = ms iff `max(start)>50000` **or** `max(duration)>100`; override `seconds`/`ms` if wrong |
| `FRONTEND_URL` | — | Vercel URL (plain, not secret) | CORS allow-origin. **Must** match Vercel domain exactly or requests fail. |
| `WEBSHARE_PROXY_USERNAME/PASSWORD/HOSTS` | — | **leave empty** | Free proxies are dead (`Connection refused` + YouTube blocks datacenter IPs). Kept as legacy only. |
| `WEBSHARE_PROXY_LIST` | — | — | Alternative: comma-separated full proxy URLs |

### Chain semantics

- **not-found** (`no_captions`): narrows remaining levels to `handles_missing=True` → **SerpApi is skipped** (it has no AI, calling it would waste a paid-ish call). Result: 404 `no_captions`.
- **block / quota / auth / network**: falls through to next level.
- **Terminal** (`VideoUnavailable`, `VideoUnplayable`, `AgeRestricted`): chain stops immediately, that error surfaces.
- **Exhaustion**: last error surfaces (404 `no_captions` or 502 `provider_unavailable`).
- **Proxy hop**: `_get_proxy_config()` returns `None` when any hosted level is active (saves 10–20s of dead-proxy retries).
- **All keys missing**: `build_provider()` logs warning + falls back to direct captions only (correct for local dev).

### Error mapping (`_map_error` in `backend/main.py`)

| Condition | HTTP | `detail` | Frontend copy |
|---|---|---|---|
| `TranscriptsNotFound` / invalid id | 404 | `no_captions` / `invalid_url` | "No captions found for this video. Try another video (Whisper fallback coming in v2)." |
| Quota/auth/exhausted chain | 502 | `provider_unavailable` | "Transcript services are busy or out of quota — retry in a few minutes." |
| Legacy YouTube errors (direct level) | 404/400/502 | `youtube_blocked`, etc. | existing switch in `frontend/lib/api.ts` |

---

## 4. Render setup

- `render.yaml` (root) drives env; `sync: false` vars = enter manually in **Dashboard → Environment → Secrets**.
- **Required manual secret:** `SUPADATA_API_KEY`.
- Optional: `SERPAPI_API_KEY` **plus** `SERPAPI_ENABLED=true` (flag is NOT in render.yaml).
- If `CHAIN_ORDER` doesn't auto-appear, add manually: `supadata,serpapi`.
- Plain vars from render.yaml: `FRONTEND_URL`, `DIRECT_ENABLED=false`.
- After env edits: **Save, rebuild, and deploy** (button shows pending-changes state while dirty).
- Watch for unsaved-change indicator — Webshare rows were once cleared pending save; empty values are harmless (proxy hop is skipped when hosted keys exist).

---

## 5. Deploy flow (backend)

1. `git add <files>` → `git commit -m "<type>: <what>"` → `git push` (only on request: "commit and p").
2. Render → **Save, rebuild, and deploy** (if env changed) or wait for auto-deploy.
3. Smoke test: `GET https://shrutilipi-backend.onrender.com/health`.
4. Functional test: request `HHUsHkYhkcM` on the Vercel frontend (or `curl "…/api/transcript?url=HHUsHkYhkcM&lang=en"`).
5. Render logs should show `transcript served by SupadataProvider video_id=… segments=…`.

Known-good test video: **`HHUsHkYhkcM`** (969 en segments, title via oEmbed).

---

## 6. Known issues / history

- **Render IP is YouTube-blocked** — root cause of the original 502 `youtube_blocked` (`RequestBlocked` in `_assert_playability`). Direct level stays off on Render; `DIRECT_ENABLED=true` is the env-only re-enable path if ever needed (e.g., residential egress).
- **Webshare free proxies are dead** — 10 datacenter IPs, all `Connection refused` or YouTube-blocked. Code kept (`b31ff24`) as legacy; harmless because hosted-active skips the proxy hop. Don't bother debugging them.
- **Hosted API shapes verified** (2026-09-26, dummy keys → 401 on both):
  - Supadata: `https://api.supadata.ai/v1/transcript?url=<id-or-url>&text=false&lang=en` + `x-api-key` header → `{error:"unauthorized", …}` for bad key.
  - SerpApi: `https://serpapi.com/search?engine=youtube_video_transcript&v=<id>&language_code=en&api_key=…` → `{error:"Invalid API key."}`.
- **Rebrand**: repo was `yt-transcriptor`; history amended + force-pushed to purge it (`git log -S "yt-transcriptor"` empty local+remote). Old SHA `7677d08` unrecoverable (local reflog wipe declined). Commits: `f26b075` v1 → `5fbf502` FRONTEND_URL → `b31ff24` Webshare → `2fdeaf5` fallback chain.
- **`python`, not `python3`** on this Windows dev box. SQLite queries (opencode sessions) via `python -c`.

---

## 7. Local dev & verification

```bash
# backend (from backend/)
python -m py_compile main.py services/*.py
python -m uvicorn main:app --port 8000     # .env.example sets PORT=8000
curl "http://127.0.0.1:8000/api/transcript?url=HHUsHkYhkcM&lang=en"

# frontend (from frontend/)
npm run dev
npm run build                              # must pass before shipping
```

- **Keyless local env = direct captions only** (correct default; your home IP isn't blocked).
- To test chain behavior locally, export any subset of the §3 vars before starting uvicorn.
- Unit-checks used during development (chain parse, eligibility, terminal, time-unit auto, proxy skip) — re-add as a test file if this grows.

### Frontend note
- `apiBase()` in `frontend/lib/api.ts` reads `NEXT_PUBLIC_API_URL` (set to the Render URL in Vercel env); code default is `http://localhost:8000` for local dev.
- Friendly error strings live in `friendlyError()` there — add new `detail` codes to its switch.

---

## 8. Growth tooling (branch `feat/share-cli-seo`)

### Shareable links
- App reads `?url=<video-id-or-url>&lang=<code>` on load → prefills + auto-fetches once.
- After a successful fetch the address bar is rewritten via `history.replaceState` to `?url=<canonical videoId>&lang=<lang>` — the current transcript result **is** the share link.
- Root URL (`/?`) or bare `/` = clean start state (no auto-fetch).

### SEO
- `frontend/app/layout.tsx`: `metadataBase`, template title, description, keywords (`youtube to text`, `youtube transcript downloader`, …), OG + Twitter cards, canonical `/`.
- `frontend/app/sitemap.ts` + `robots.ts` → `/sitemap.xml`, `/robots.txt` (single-page app, 1 URL).
- **Gotcha:** `SITE_URL` constant (Vercel domain) now appears in **3 files** (`layout.tsx`, `sitemap.ts`, `robots.ts`). If the Vercel domain ever changes, update all three — or refactor to one shared constant first.

### CLI helper — `tools/fetch.py`
- Stdlib only, no installs. Talks to any backend (`--api`, default `http://localhost:8000`).
- Transcript goes to **stdout**, stats/progress to **stderr** (pipes cleanly: `python tools/fetch.py … | pbcopy`).
- `--out <file>` writes a file; `--out -` or `--batch` writes `<videoId>.txt` per video.
- `--timestamps` → `[m:ss] text` lines; `--lang <code>`; `--batch <file>` = one URL/line, `#` comments.
- Exit codes for scripting: **0** ok, **1** no captions/bad URL, **2** network/server error.
- Verified locally: single/timestamps/out/batch/bad-id/dead-api all behave as specified.
- Fair use: CLI hits the same free-tier quota as the web app (§3) — batch files should stay small; the prod API is not rate-limited yet, don't build heavy automation on it without discussing limits first.
