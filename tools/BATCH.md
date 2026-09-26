# Batch mode — fetch many transcripts at once

Instead of running `python tools/fetch.py` once per video, put your URLs in a
text file and fetch them all with one command.

```bash
python tools/fetch.py --batch urls.txt
```

## The input file

Plain text, one video per line. **`#` lines and blank lines are skipped.**
Both raw video IDs and full YouTube URLs work, mixed freely:

```
# my list
abc123XYZ_-
https://www.youtube.com/watch?v=Xyz987AbC12
https://youtu.be/QwErTyUiOp9
```

> Dummy IDs above (`abc123XYZ_-`, `Xyz987AbC12`, `QwErTyUiOp9`) are examples
> only — replace with real ones.

## What happens

- Each video is fetched through the backend, one after another
- Each transcript is saved as its own file named **`<videoId>.txt`** in the
  current directory (raw IDs and full URLs both resolve to the ID)
- Progress/stats go to **stderr**, so you can watch it while files accumulate:

  ```
  abc123XYZ_-: 969 segments (en) -> abc123XYZ_-.txt
  Xyz987AbC12: 412 segments (en) -> Xyz987AbC12.txt
  ```

- A failing video prints an error and **the run continues** with the rest

## Options that work with `--batch`

```bash
# Hindi captions, timestamped lines
python tools/fetch.py --batch urls.txt --lang hi --timestamps

# against production instead of localhost
python tools/fetch.py --batch urls.txt --api https://shrutilipi-backend.onrender.com
```

(`--out` is ignored in batch mode — every video already gets its own
`<videoId>.txt`.)

## Exit codes (good for scripting)

| Code | Meaning |
|---|---|
| `0` | every video fetched |
| `1` | at least one had no captions / invalid URL (others may have succeeded) |
| `2` | a network or server error occurred |

```powershell
# PowerShell: run the batch, report the result
python tools/fetch.py --batch urls.txt
switch ($LASTEXITCODE) {
  0 { "all ok" }
  1 { "some videos had no captions" }
  2 { "network/server problem — rerun later" }
}
```

Exit code is the **worst** result across the run, so `0` genuinely means
"everything landed".

## Gotchas

- **Duplicate IDs overwrite** — if the same video appears twice, the second
  fetch rewrites the first file (harmless, but you get one file per unique ID)
- **Files land in your current directory** — `cd` where you want them first
- **Repeated runs are cheap** — successful results are cached 24h on the
  backend, so re-running the same list hits the cache, not the quota
- **Quota**: every *uncached* video spends free-tier quota (100 req/mo per
  provider — see `docs/operations.md` §3). Keep lists small until you know
  your headroom.

## See also

- [tools/README.md](README.md) — all CLI flags, quick start, exit codes
- [docs/operations.md](../docs/operations.md) §3 — provider chain & quota rules
