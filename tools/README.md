# ShrutiLipi CLI

Fetch YouTube transcripts from the terminal — stdlib only, nothing to install.

## Prerequisites

- Python 3
- A running backend:
  - **Local:** `python -m uvicorn main:app --port 8000` (from `backend/`)
  - **Production:** pass `--api https://shrutilipi-backend.onrender.com`
- **Optional:** `pip install rich` — unlocks colored output, batch progress bar
  and summary table. Without it the CLI still works, just plain (and `--plain`
  forces plain even when installed).

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

## Accepted input — video ID or any URL form

All of these are equivalent; the backend extracts the video ID itself:

| Form | Dummy example |
|---|---|
| Raw 11-char video ID | `abc123XYZ_-` |
| Full watch URL | `https://www.youtube.com/watch?v=abc123XYZ_-` |
| Short URL | `https://youtu.be/abc123XYZ_-` |
| Shorts / embed / live / `/v/` | `https://www.youtube.com/shorts/abc123XYZ_-` |

```bash
python tools/fetch.py abc123XYZ_-
python tools/fetch.py "https://www.youtube.com/watch?v=abc123XYZ_-"
python tools/fetch.py "https://youtu.be/abc123XYZ_-"
```

- **Quote full URLs** — shells treat `?` and `&` specially
- Works the same in `--batch` files; mix IDs and URLs freely
- Output filenames (`--out -`, batch mode) always use the **resolved video
  ID**, never the raw URL you typed

## Flags

| Flag | Meaning | Example |
|---|---|---|
| `--lang <code>` | caption language (default `en`) | `python tools/fetch.py abc123XYZ_- --lang hi` |
| `--timestamps` | prefix each line with `[m:ss]` | `python tools/fetch.py abc123XYZ_- --timestamps` |
| `--out <file>` | write to a file (`-` → `<videoId>.txt`) | `python tools/fetch.py abc123XYZ_- --out transcript.txt` |
| `--api <url>` | backend base URL (default `http://localhost:8000`) | `python tools/fetch.py abc123XYZ_- --api https://shrutilipi-backend.onrender.com` |
| `--batch <file>` | fetch every URL in a file | `python tools/fetch.py --batch urls.txt` |
| `--plain` | force plain output even if rich is installed | `python tools/fetch.py abc123XYZ_- --plain` |

## Windows launcher — `shrutilipi.bat`

A 3-line wrapper so you don't have to type `python tools/fetch.py` every time:

```bat
tools\shrutilipi.bat abc123XYZ_-
tools\shrutilipi.bat --batch urls.txt --timestamps
```

What it contains (see [`shrutilipi.bat`](shrutilipi.bat)):

```bat
@echo off                          REM silence cmd's own command echo
python "%~dp0fetch.py" %*          REM run fetch.py next to this .bat, pass all args through
exit /b %errorlevel%               REM propagate exit code (0/1/2) back to cmd
```

- `%~dp0` = the folder the `.bat` itself lives in (`tools\`) — works from any
  working directory, quoted so spacey paths are safe
- `%*` = every argument you typed after `shrutilipi`, forwarded untouched:
  `shrutilipi.bat abc123XYZ_- --timestamps --lang hi` runs exactly
  `python tools\fetch.py abc123XYZ_- --timestamps --lang hi`
- `exit /b %errorlevel%` keeps scripting honest — `%errorlevel%` reports the
  real 0/1/2 result, not a fake success

### Add to PATH (optional, one-time)

1. Windows Settings → **System → About → Advanced system settings →
   Environment Variables**
2. Under **Path** (user or system), **New** → add the full `...\shrutilipi\tools`
   folder
3. Open a new terminal → run from anywhere:

```bat
shrutilipi abc123XYZ_-
shrutilipi --batch urls.txt
```

### Limitations

- **Windows/`cmd` only** (PowerShell runs it too) — on Linux/macOS call
  `python tools/fetch.py` directly or make a shell alias
- **Needs Python installed** — it's a launcher, not a bundled `.exe`
- **No logic of its own** — all flags, output, colors, and errors come from
  [`fetch.py`](fetch.py); edit that file, not this one

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
