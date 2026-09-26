# ShrutiLipi CLI

Fetch YouTube transcripts from the terminal — stdlib only, nothing to install.

## Prerequisites

- Python 3
- A running backend:
  - **Local:** `python -m uvicorn main:app --port 8000` (from `backend/`)
  - **Production:** pass `--api https://shrutilipi-backend.onrender.com`

> Dummy IDs below (`abc123XYZ_-`, `Xyz987AbC12`) are examples only — replace with real video IDs or URLs.

## Quick start

```bash
# transcript to terminal (backend at localhost:8000 by default)
python tools/fetch.py abc123XYZ_-

# full URL works the same
python tools/fetch.py "https://www.youtube.com/watch?v=abc123XYZ_-"

# against production backend
python tools/fetch.py abc123XYZ_- --api https://shrutilipi-backend.onrender.com
```

## Flags

| Flag | Meaning | Example |
|---|---|---|
| `--lang <code>` | caption language (default `en`) | `python tools/fetch.py abc123XYZ_- --lang hi` |
| `--timestamps` | prefix each line with `[m:ss]` | `python tools/fetch.py abc123XYZ_- --timestamps` |
| `--out <file>` | write to a file (`-` → `<videoId>.txt`) | `python tools/fetch.py abc123XYZ_- --out transcript.txt` |
| `--api <url>` | backend base URL (default `http://localhost:8000`) | `python tools/fetch.py abc123XYZ_- --api https://shrutilipi-backend.onrender.com` |
| `--batch <file>` | fetch every URL in a file | `python tools/fetch.py --batch urls.txt` |

## Batch mode

`urls.txt` — one URL per line, `#` lines are comments, blank lines skipped.
Each video saves as its own `<videoId>.txt`:

```
# my list
abc123XYZ_-
https://www.youtube.com/watch?v=Xyz987AbC12
```

```bash
python tools/fetch.py --batch urls.txt
```

**Full batch guide** — file format, output behavior, partial-failure exit
codes, gotchas, scripting examples: [BATCH.md](BATCH.md).

## stdout vs stderr

- **stdout** = transcript text only → pipes cleanly
- **stderr** = stats (`<videoId>: 969 segments (en)`) and errors

```powershell
# PowerShell: transcript straight to clipboard
python tools/fetch.py abc123XYZ_- 2>$null | Set-Clipboard
```

```bash
# bash: transcript to a file, stats stay visible in terminal
python tools/fetch.py abc123XYZ_- > notes.txt
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | no captions / invalid URL or video ID |
| `2` | network or server error |

```powershell
# PowerShell: branch on the result
python tools/fetch.py abc123XYZ_-
switch ($LASTEXITCODE) {
  0 { "ok" }
  1 { "no captions found" }
  2 { "server/network problem" }
}
```

## Fair use

The CLI spends the same free-tier quota as the web app (100 req/mo per
provider — see `docs/operations.md` §3). Keep batch files small; don't build
heavy automation on the public API without reviewing limits first.
