# ShrutiLipi — Operations Notes

Everything future-us needs: env, deploy flow, provider chain rules, known traps.

Last verified: 2026-10-24 (includes the on-demand summary feature, §9).

---

## 1. Identity

| Thing | Value |
|---|---|
| Display name | **ShrutiLipi** (camel-case; never `shrutilipi` in UI copy) |
| Code slugs | `shrutilipi`, `shrutilipi-frontend`, `shrutilipi-backend` |
| Repo | `git@github.com-personal:nayan-kunwar/shrutilipi.git`, branch `main` |
| Frontend | https://shrutilipi.nayankunwar.com (custom domain on Vercel) — legacy: https://shrutilipi-rho.vercel.app |
| Backend | https://shrutilipi-backend.onrender.com (Render free, Docker) |
| Commit convention | Conventional commits; user says **"commit and p"** → commit + push. Never commit unasked. |

---

## 2. Architecture

- **Monorepo**: pnpm workspaces + Turborepo. `apps/web` (Next.js) · `apps/api` (FastAPI) · `packages/shared` (API contract) · `packages/tsconfig` (base TS config). Root scripts (`pnpm dev|build|typecheck|test`) run through Turbo; `apps/api/package.json` holds thin delegating scripts so Turbo can drive the Python side too.
- **Frontend**: Next.js 14 App Router, `apps/web/`, built by `pnpm build` (`/` ≈ 5.1 kB first-load JS ≈ 92 kB). Not a static export — default Vercel build, despite what §6 used to claim.
- **Backend**: FastAPI, `apps/api/`, Docker (`python`, 3.11). Dependencies pinned: `youtube-transcript-api==1.2.4`, `httpx==0.28.1` — hosted providers use plain `httpx`, no new deps.
- **Shared package**: `@shrutilipi/shared` ships raw TS (no build step). It holds `TranscriptResponse`/`TranscriptSegment`, `SummaryResponse`, the `TranscriptErrorDetail`/`SummaryErrorDetail` unions, `friendlyError()` (in `src/errors.ts`, re-exported from the index so Node tests can import it directly), and `formatTime()`. Anything touching `process.env` or the network stays in `apps/web/lib/api.ts`. `next.config.js` needs `transpilePackages: ["@shrutilipi/shared"]` and `experimental.outputFileTracingRoot` set to the repo root, or the build resolves the workspace dep but misses it in the trace.
- **API**:
  - `GET /api/wake` → `{"ok": true}` (frontend wake probe; `GET /health` is the ops alias for the same handler)
  - `GET /api/transcript?url=<youtube-url-or-id>&lang=<code>` → `{videoId, title, language, plainText, segments[]}` (`segments[i] = {start, duration, text}` in seconds)
  - `POST /api/summary` with `{videoId, lang?}` → `{summary, model, cached}` — on-demand only; see §9
- **Cache**: in-memory TTL dict, **24h** (`CACHE_TTL` in `apps/api/main.py`), key `videoId:lang`. Restart clears it.
- **Summary cache**: a second 24h dict keyed `videoId:lang:model:prompt_version`; entries are created only when a summary is generated, never by the transcript route (§9).
- **Title**: best-effort via YouTube oEmbed (no key); may be `null` → frontend falls back to showing `videoId`.

---

## 3. Provider chain (the core mechanism)

`build_provider()` in `apps/api/services/providers.py` reads env at process start (not per-request — env changes need a redeploy).

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
| `FRONTEND_URL` | — | comma-separated origins (plain, not secret) | CORS allow-origin, **additive only**. The production origins are hardcoded in `apps/api/main.py` (`PROD_ORIGINS`), so this var can only *add* origins — it can no longer lock the site out of its own API. Localhost ports are covered by the CORS regex, not this var. |
| `WEBSHARE_PROXY_USERNAME/PASSWORD/HOSTS` | — | **leave empty** | Free proxies are dead (`Connection refused` + YouTube blocks datacenter IPs). Kept as legacy only. |
| `WEBSHARE_PROXY_LIST` | — | — | Alternative: comma-separated full proxy URLs |
| `RATE_LIMIT_ENABLED` | `true` | leave unset | Kill switch: `0`/`false`/`no`/`off` disables the limiter |
| `RATE_LIMIT_REQUESTS` | `20` | leave unset | Bucket capacity per client per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `600` | leave unset | Refill window in seconds (20 per 10 min); misses only, `/api/wake` unlimited |

Summary-specific vars (`SUMMARY_*`) are documented in §9. The feature is off
unless `SUMMARY_BASE_URL`, `SUMMARY_API_KEY` and `SUMMARY_MODEL` are all set.

### Chain semantics

- **not-found** (`no_captions`): narrows remaining levels to `handles_missing=True` → **SerpApi is skipped** (it has no AI, calling it would waste a paid-ish call). Result: 404 `no_captions`.
- **block / quota / auth / network**: falls through to next level.
- **Terminal** (`VideoUnavailable`, `VideoUnplayable`, `AgeRestricted`): chain stops immediately, that error surfaces.
- **Exhaustion**: last error surfaces (404 `no_captions` or 502 `provider_unavailable`).
- **Proxy hop**: `_get_proxy_config()` returns `None` when any hosted level is active (saves 10–20s of dead-proxy retries).
- **All keys missing**: `build_provider()` logs warning + falls back to direct captions only (correct for local dev).

### Error mapping (`_map_error` in `apps/api/main.py`)

| Condition | HTTP | `detail` | Frontend copy |
|---|---|---|---|
| `TranscriptsNotFound` / invalid id | 404 | `no_captions` / `invalid_url` | "No captions found for this video. Try another video (Whisper fallback coming in v2)." |
| Quota/auth/exhausted chain | 502 | `provider_unavailable` | "Transcript services are busy or out of quota — retry in a few minutes." |
| Rate limiter (token bucket, misses only) | 429 | `rate_limited` | "You're requesting transcripts a bit too quickly — wait a minute and retry." + `Retry-After` header |
| Legacy YouTube errors (direct level) | 404/400/502 | `youtube_blocked`, etc. | existing switch in `apps/web/lib/api.ts` |

Rate limiter notes (`apps/api/services/ratelimit.py`, wired in `main.py` after
the cache-hit return): 20 requests per 600 s per client by default, via
`RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`, kill switch
`RATE_LIMIT_ENABLED`. Key is leftmost `X-Forwarded-For` (Render proxies, so
`client.host` would bucket the whole world together), falling back to the peer
address locally. Cache hits and invalid URLs consume nothing — the limiter
guards upstream spend, not raw traffic. `/api/wake` (and its `/health` alias) is unlimited. Buckets are
process-local; restart clears them (fail-open). Tests:
`apps/api/tests/test_ratelimit.py` (`pnpm test` from root, `pytest` in
`requirements.txt`).

---

## 4. Render setup

- `render.yaml` (root) drives env; `sync: false` vars = enter manually in **Dashboard → Environment → Secrets**.
- **`rootDir` is `apps/api`.** Any move of the backend must be mirrored here *and* in the Render dashboard.
- **Required manual secret:** `SUPADATA_API_KEY`.
- Optional: `SERPAPI_API_KEY` **plus** `SERPAPI_ENABLED=true` (flag is NOT in render.yaml).
- Optional on-demand summaries: set `SUMMARY_BASE_URL`, `SUMMARY_API_KEY` (secret) and `SUMMARY_MODEL` (§9). Missing any one of the three leaves the feature off — transcripts are unaffected.
- If `CHAIN_ORDER` doesn't auto-appear, add manually: `supadata,serpapi`.
- Plain vars from render.yaml: `FRONTEND_URL`, `DIRECT_ENABLED=false`.
- After env edits: **Save, rebuild, and deploy** (button shows pending-changes state while dirty).
- Watch for unsaved-change indicator — Webshare rows were once cleared pending save; empty values are harmless (proxy hop is skipped when hosted keys exist).

### Cold starts & wake-up UX (free tier)

Render free instances spin down after ~15 min idle; the first request after that pays a ~30 s cold start. The
frontend softens this (`apps/web`):

- `pingHealth()` (`lib/api.ts`) — `GET /api/wake` (`/health` aliases the same handler); its arrival starts a
  boot and it costs nothing upstream (no provider call, no rate-limit tokens, CORS-allowed). The frontend path
  deliberately avoids the word "health": some adblock filter lists block health-style URLs client-side
  (`net::ERR_BLOCKED_BY_CLIENT`), indistinguishable from a dead server in JS.
- `useServerWake()` (`lib/useServerWake.ts`) — pings on page load (boot starts while the user is still pasting),
  on tab-return / first interaction if the last ping is >5 min old, and every 10 min while the tab is visible
  (under Render's 15-min sleep timer). One ping in flight at a time; hidden tabs skip the interval.
- `ServerStatus` pill — silent when warm; amber "Waking up the API…" once a ping runs >2.5 s; green "API awake"
  for 3 s after a slow wake or a retry; a neutral banner with a **Wake up the server** button when unreachable
  (a call to action, deliberately not styled as an error).
- A slow transcript fetch switches the loading copy after 3 s, and the error card has a **Retry** button.

Tradeoff: a visible tab keeps the instance awake — bounded by real visits, unlike a 24/7 cron pinger, which would
burn free instance hours and hide the problem rather than surface it.

### Vercel setup

- Root Directory **`apps/web`**. Install command is left blank — Vercel detects pnpm from the root `pnpm-lock.yaml`, and the root `package.json` `packageManager` field pins the version.
- Only `NEXT_PUBLIC_API_URL` is needed in env.
- If the build fails with a missing `@shrutilipi/shared`, the Root Directory is wrong (it must be `apps/web`, not the repo root, or the workspace links won't resolve).
- `packages/shared` is workspace-linked, so Vercel needs `apps/web/node_modules` to be populated by the root install — it does this automatically, but it is the #1 thing to check when a monorepo deploy breaks.

---

## 5. Deploy flow (backend)

1. `git add <files>` → `git commit -m "<type>: <what>"` → `git push` (only on request: "commit and p").
2. Render → **Save, rebuild, and deploy** (if env changed) or wait for auto-deploy.
3. Smoke test: `GET https://shrutilipi-backend.onrender.com/health`.
4. CORS smoke test (after any origin/domain change):
   ```bash
   curl -s -D - -o /dev/null -X OPTIONS https://shrutilipi-backend.onrender.com/api/transcript \
     -H "Origin: https://shrutilipi.nayankunwar.com" -H "Access-Control-Request-Method: GET"
   ```
   Expect `200` **and** `access-control-allow-origin: https://shrutilipi.nayankunwar.com`.
   A `400 "Disallowed CORS origin"` means the allowlist is stale — see §6.
   Repeat with `Origin: http://localhost:3000` for the dev path.
5. Functional test: request `HHUsHkYhkcM` on the Vercel frontend (or `curl "…/api/transcript?url=HHUsHkYhkcM&lang=en"`).
6. Render logs should show `transcript served by SupadataProvider video_id=… segments=…`.
7. Summary smoke test (only when the feature is configured):
   ```bash
   curl -s -X POST https://shrutilipi-backend.onrender.com/api/summary \
     -H "Content-Type: application/json" -d '{"videoId":"HHUsHkYhkcM"}'
   ```
   Expect `200` with `{summary, model, cached:false}`; a second call returns
   `cached:true`. Run it preflighted from a browser origin too — the route
   needs `POST` in CORS `allow_methods` (§9). Without `SUMMARY_*` env, expect
   `503 {"detail":"summary_disabled"}`, which is the correct degraded state.

Known-good test video: **`HHUsHkYhkcM`** (969 en segments, title via oEmbed).

---

## 6. Known issues / history

- **Production CORS broke on the custom domain (fixed 2026-10-22)** — `https://shrutilipi.nayankunwar.com` was added to the Vercel project without touching the API's allowlist, so the browser sent a new `Origin` the API didn't know. Preflight returned `400 "Disallowed CORS origin"`, and the simple `GET /api/wake` returned 200 **without** `access-control-allow-origin`, so the browser discarded every response. The page looked fine; no API call worked. Root cause: `render.yaml` pinned `FRONTEND_URL` to only the Vercel URL. Fix: the production origins are now hardcoded in `apps/api/main.py` (`PROD_ORIGINS`) **and** the env var is additive-only, so a domain change can never lock the site out of its own API again. Note the frontend needs its own redeploy for the `SITE_URL` change to reach `sitemap.xml`/`robots.txt`.
- **`FRONTEND_URL` was parsed wrong** — the raw env string was added to the allowlist *before* being split on commas, so `"https://a.app,https://b.app"` landed in the set as one bogus origin (the two real ones were also added, so it mostly worked by accident). Now it is split first. Covered by `tests/test_cors.py`.
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
# once, from the repo root
pnpm install

# both apps in parallel (Turbo)
pnpm dev

# or individually
# backend (from apps/api/)
pnpm dev                             # uvicorn --reload --port 8000
curl "http://127.0.0.1:8000/api/transcript?url=HHUsHkYhkcM&lang=en"

# frontend (from apps/web/)
pnpm dev
```

Gate before shipping:

```bash
pnpm typecheck        # tsc --noEmit across shared + web
pnpm build            # shared -> web, plus a py_compile syntax check for the API
```

- **Keyless local env = direct captions only** (correct default; your home IP isn't blocked).
- To test chain behavior locally, export any subset of the §3 vars before starting uvicorn.
- Unit-checks used during development (chain parse, eligibility, terminal, time-unit auto, proxy skip) — re-add as a test file if this grows.
- Test suites: `apps/api/tests/` (**57 pytest** — limiter + 429 wiring, wake-probe contract, CORS contract, summary endpoint contract/cache/locks/accounting, LLM adapter + truncation) via `pnpm test` or `pytest` from `apps/api/`, and `packages/shared/src/` (**15 `node --test` cases** — 11 SRT/VTT formatter cases + 4 `friendlyError` copy cases; Node ≥22.6 runs the TS natively, no test framework). `pnpm test` runs both through Turbo; `pytest` is pinned in `requirements.txt`. The summary suites stub the transcript provider and the LLM, so they need no key and no network.

### Frontend note
- `apiBase()` in `apps/web/lib/api.ts` reads `NEXT_PUBLIC_API_URL` (set to the Render URL in Vercel env); code default is `http://localhost:8000` for local dev.
- `friendlyError()` and the response types live in `@shrutilipi/shared` (`friendlyError` is in `src/errors.ts`, re-exported from the index so Node's test runner can import it directly) — add new `detail` codes to its switch, and extend the `TranscriptErrorDetail`/`SummaryErrorDetail` union at the same time.
- Summary UI: `TranscriptView` has a `Generate summary` button (never runs on page load), a summary card with `Copy summary`, and inline errors. It calls `fetchSummary()` in `lib/api.ts`, which sends `{videoId, lang}` only — never transcript text — and uses a 75 s timeout (30 s transcript + 30 s LLM, with headroom). The label reads `Refresh summary` after a result; within the 24 h cache TTL that re-request is answered from cache (§9).
- Exports: `TranscriptView` has Copy, a segmented `Download [.txt | .srt | .vtt]` group and Share. `toSrt()`/`toVtt()` are pure functions in `packages/shared/src/subtitles.ts` (re-exported from the package index); the Python twins are `render_srt()`/`render_vtt()` in `tools/fetch.py`. `.txt` honors the Timestamps checkbox; the subtitle formats always carry timestamps, so they ignore it.
- Cold-start wake probe: `pingHealth()` in the same file; `useServerWake` + `ServerStatus` drive the pill (§4). No backend change needed — `/api/wake` is already outside the limiter.

---

## 8. Growth tooling (branch `feat/share-cli-seo`)

### Shareable links
- App reads `?url=<video-id-or-url>&lang=<code>` on load → prefills + auto-fetches once.
- After a successful fetch the address bar is rewritten via `history.replaceState` to `?url=<canonical videoId>&lang=<lang>` — the current transcript result **is** the share link.
- Root URL (`/?`) or bare `/` = clean start state (no auto-fetch).

### SEO
- `apps/web/app/layout.tsx`: `metadataBase`, template title, description, keywords (`youtube to text`, `youtube transcript downloader`, …), OG + Twitter cards, canonical `/`.
- `apps/web/app/sitemap.ts` + `robots.ts` → `/sitemap.xml`, `/robots.txt` (single-page app, 1 URL).
- **Fixed:** `SITE_URL` used to be copy-pasted into 3 files (`layout.tsx`, `sitemap.ts`, `robots.ts`), so a domain change could silently update two of three. It now lives once in `@shrutilipi/shared` and is imported by all three.
- `SITE_URL` is now `https://shrutilipi.nayankunwar.com` (the custom domain), with `https://shrutilipi-rho.vercel.app` kept as the legacy URL. It drives `metadataBase`, the canonical link, OG `url`, `sitemap.xml` and `robots.txt` — so a change here needs a **frontend** redeploy to reach the live pages.

### CLI helper — `tools/fetch.py`
- **Full usage guide with examples: [`tools/README.md`](../tools/README.md)** (dummy IDs only).
- Stdlib only, no installs (`rich` optional — pretty progress/table when installed; `--plain` disables). Windows launcher: `tools/shrutilipi.bat`. Talks to any backend (`--api`, default `http://localhost:8000`).
- Transcript goes to **stdout**, stats/progress to **stderr** (pipes cleanly: `python tools/fetch.py … | pbcopy`).
- `--out <file>` writes a file; `--out -` or `--batch` writes `<videoId>.<fmt>` per video (default `txt`). `--srt`/`--vtt` switch the format — mutually exclusive, and incompatible with `--timestamps`.
- `--timestamps` → `[m:ss] text` lines; `--lang <code>`; `--batch <file>` = one URL/line, `#` comments.
- Exit codes for scripting: **0** ok, **1** no captions/bad URL, **2** network/server error or rate-limited (`429` — transient, respect `Retry-After`).
- Verified locally: single/timestamps/out/batch/bad-id/dead-api all behave as specified.
- Fair use: CLI hits the same free-tier quota as the web app (§3) — batch files should stay small. The prod API **is** rate-limited (20 req / 10 min per IP, `429 rate_limited` with `Retry-After`); automation must back off on 429 rather than retrying blindly. Don't build heavy automation on it without discussing limits first.

---

## 9. On-demand AI summary

**What ships:** a `Generate summary` button under the transcript. Nothing runs
until it is clicked — `GET /api/transcript` never calls an LLM, so the transcript
path keeps its old latency and cost. Output is one `TL;DR:` sentence plus 3–5
`•` bullets, asked for in the system prompt and capped at 350 output tokens.

### Contract

`POST /api/summary` with JSON `{"videoId": "<11-char id>", "lang": "en"}`
→ `200 {"summary": string, "model": string, "cached": boolean}`.

| Status | `detail` | Meaning |
|---|---|---|
| 400 | `invalid_url` | Body is not a YouTube id/URL |
| 429 | `summary_rate_limited` | Summary bucket empty; `Retry-After` set |
| 429 | `rate_limited` | The transcript fetch the summary needed is limited |
| 502 | `summary_failed` | LLM failed, timed out, or returned an unusable body |
| 503 | `summary_disabled` | `SUMMARY_*` config incomplete — feature off by design |
| 503 | `summary_busy` | Same video still generating after a 30 s wait |
| 404/502 | transcript codes | The source transcript could not be fetched (§3) |

The browser preflights this route (JSON POST), so `POST` is in CORS
`allow_methods`; the localhost-port regex covers any dev port.

### Request path (order matters)

1. Validate `videoId` → `400 invalid_url`
2. Summary-cache hit → `200 cached:true`
3. Summarizer missing → `503 summary_disabled`
4. Consume one **summary** token → `429 summary_rate_limited`
5. Per-video lock, wait at most 30 s → `503 summary_busy`
6. Re-check the cache (another request may have filled it while waiting)
7. Shared transcript helper: transcript cache → transcript limiter (misses only) → provider
8. LLM call
9. Store the summary (non-empty only) → `200 cached:false`

**Accounting policy:** summary tokens are *attempt*-counted. A request that
passes step 4 pays even if it later hits the transcript limiter, the lock
timeout, or an LLM failure. That is deliberate: the limit caps LLM work per IP,
and checking it *before* the lock stops a hot loop from queuing threads. Cache
hits cost nothing. Transcript tokens are spent only on a real transcript-cache
miss, so summarizing a video whose transcript was already viewed is free on the
transcript side. The trade-off (a failed attempt still consumes budget) is the
reason the error copy says "retry in a moment" rather than promising a fresh
budget.

### Environment

| Var | Default | Set where | Notes |
|---|---|---|---|
| `SUMMARY_BASE_URL` | — | Render | OpenAI-compatible base URL, **without** `/chat/completions`. Gemini: `https://generativelanguage.googleapis.com/v1beta/openai` · Groq: `https://api.groq.com/openai/v1` · OpenRouter: `https://openrouter.ai/api/v1` · local llama.cpp/ollama: its `/v1` |
| `SUMMARY_API_KEY` | — | Render secret (`sync: false`) | Bearer token. Never logged, never sent to clients |
| `SUMMARY_MODEL` | — | Render | e.g. `gemini-2.5-flash`, `llama-3.3-70b-versatile` |
| `SUMMARY_TIMEOUT_SECONDS` | `30` | optional | Per LLM call |
| `SUMMARY_MAX_CHARS` | `15000` | optional | Prompt input cap (see Truncation) |
| `SUMMARY_MAX_OUTPUT_TOKENS` | `350` | optional | Output cap |
| `SUMMARY_RATE_LIMIT_REQUESTS` | `5` | optional | Per IP, misses only |
| `SUMMARY_RATE_LIMIT_WINDOW_SECONDS` | `600` | optional | Refill window |
| `SUMMARY_RATE_LIMIT_ENABLED` | `true` | optional | Break-glass kill switch |

All three of base URL, key and model are required. If any is missing the route
answers `503 summary_disabled` and **transcripts are unaffected** — summary is
an optional capability, not a boot dependency. To swap vendors, change the
three values and restart; the model is part of the cache key, so the new vendor
starts cold instead of serving old text. No code or frontend change.

### Truncation

Deterministic **head** truncation at `SUMMARY_MAX_CHARS` (15,000 chars ≈ 3–4k
English tokens), backed up to the last whitespace so a word is not split, with
a visible marker:

```
[... transcript truncated for summarization ...]
```

Long videos are summarized from their opening ~15k characters only; the tail is
never sent. Unit-tested in `tests/test_summarize.py`. Chunked/recursive
summarization is intentionally not implemented — it multiplies cost and latency
and has no consumer yet.

### Cost

Nothing is billed until the button is clicked; cache hits are free. Upper bound
per **uncached** summary:

- input ≈ `SUMMARY_MAX_CHARS / 4` tokens (English rule of thumb) → ~3,750 at the default
- output ≤ `SUMMARY_MAX_OUTPUT_TOKENS` → ≤ 350 tokens

```
cost ≈ (input_tokens  / 1_000_000 × input_price_per_M)
     + (output_tokens / 1_000_000 × output_price_per_M)
```

At the prices listed for Gemini 2.5 Flash when this was written (about
$0.30/M input and $2.50/M output — **check current prices, they change**):
≈ $0.0011 input + $0.0009 output ≈ **$0.002 per summary**, so roughly 500
summaries per dollar. Provider free tiers (daily/RPM quotas) usually make the
marginal bill $0 until the quota is hit; the summary limiter (5 per 10 min per
IP) is what keeps a public instance inside those quotas.

Honesty caveats: **no live call has been measured against a real key yet**;
token counts vary by language (Devanagari/Tamil cost more per character); and
pricing/quota terms change. The formula and the caps are the durable part. A
summary also needs a transcript: uncached, that spends one Supadata request
(100/month free); already cached, zero.

### Cache, privacy, failure isolation

- **Cache:** separate in-process dict, 24 h TTL, key
  `videoId:lang:model:PROMPT_VERSION`. Expired entries are pruned on each write;
  only non-empty summaries are stored. Restart clears it. `Refresh summary`
  within the TTL re-requests and gets `cached:true` — change the model or bump
  `PROMPT_VERSION` (`services/summarize.py`) to force real regeneration. That
  variable is in the key precisely so a prompt change never serves old text.
- **Privacy:** the client sends only `{videoId, lang}`. The server fetches the
  transcript itself and sends the truncated text to the configured LLM provider.
  Logs contain the video id, model name and error detail — never the transcript,
  prompt, summary, or raw upstream bodies. Once sent, the LLM provider's data
  policy applies to that text.
- **Single-flight:** per-video locks (not one global lock), refcounted so the
  table cannot grow without bound, with a 30 s wait cap. Process-local, same as
  the caches — correct for one Render instance; two instances need Redis.
- **Failure isolation:** LLM failures return `502 summary_failed`; the
  transcript was cached before the LLM call, so the transcript view keeps
  working and no cache entry is poisoned.

### Verifying

```bash
# Disabled state (no SUMMARY_* env) — the correct local default:
curl -s -X POST http://localhost:8000/api/summary \
  -H 'Content-Type: application/json' -d '{"videoId":"HHUsHkYhkcM"}'
# {"detail":"summary_disabled"}

# Enabled: start the API with all three required vars, then:
curl -s -X POST http://localhost:8000/api/summary \
  -H 'Content-Type: application/json' -d '{"videoId":"HHUsHkYhkcM"}'
# {"summary":"TL;DR: …","model":"…","cached":false}
# second identical call -> "cached":true, no LLM call
```

The pytest suites stub both the provider and the LLM
(`tests/test_summary.py`) and cover the adapter/truncation/env factory
(`tests/test_summarize.py`), so the contract is verified without a key or
network. A real-key smoke test is still the only way to confirm the vendor's
endpoint, model name and quota.
