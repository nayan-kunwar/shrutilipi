#!/usr/bin/env python3
"""ShrutiLipi CLI — fetch YouTube transcripts via the backend API.

Stdlib only. Examples:
  python tools/fetch.py HHUsHkYhkcM
  python tools/fetch.py https://youtu.be/HHUsHkYhkcM --lang hi --timestamps
  python tools/fetch.py HHUsHkYhkcM --out transcript.txt
  python tools/fetch.py --batch urls.txt --api https://shrutilipi-backend.onrender.com

Exit codes: 0 = ok, 1 = no captions / not found, 2 = other error.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API = "http://localhost:8000"


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch(api: str, url: str, lang: str, timeout: float = 60.0) -> dict:
    qs = urllib.parse.urlencode({"url": url, "lang": lang})
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/transcript?{qs}",
        headers={"User-Agent": "shrutilipi-cli/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def render(data: dict, timestamps: bool) -> str:
    if not timestamps:
        return data["plainText"]
    return "\n".join(
        f"[{format_time(seg['start'])}] {seg['text']}" for seg in data["segments"]
    )


def emit(data: dict, timestamps: bool, out: str | None) -> int:
    text = render(data, timestamps)
    where = f"{data['videoId']}.txt" if out == "-" else out
    if out:
        with open(where, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(
            f"{data['videoId']}: {len(data['segments'])} segments "
            f"({data['language']}) -> {where}",
            file=sys.stderr,
        )
    else:
        print(text)
        print(
            f"\n{data['videoId']}: {len(data['segments'])} segments "
            f"({data['language']})",
            file=sys.stderr,
        )
    return 0


def one(api: str, url: str, lang: str, timestamps: bool, out: str | None) -> int:
    try:
        data = fetch(api, url, lang)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("detail", "")
        except Exception:
            detail = ""
        print(f"{url}: HTTP {e.code} {detail}", file=sys.stderr)
        return 1 if detail in ("no_captions", "invalid_url") else 2
    except Exception as e:
        print(f"{url}: {e}", file=sys.stderr)
        return 2
    return emit(data, timestamps, out)


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch a YouTube transcript via ShrutiLipi.")
    p.add_argument("url", nargs="?", help="YouTube URL or 11-char video ID")
    p.add_argument("--lang", default="en", help="caption language (default: en)")
    p.add_argument("--api", default=DEFAULT_API, help=f"backend base URL (default: {DEFAULT_API})")
    p.add_argument("--out", help="write to file instead of stdout ('-' = <videoId>.txt)")
    p.add_argument("--timestamps", action="store_true", help="prefix lines with [m:ss]")
    p.add_argument("--batch", help="file with one URL per line (# comments allowed)")
    args = p.parse_args()

    if args.batch:
        try:
            lines = open(args.batch, encoding="utf-8").read().splitlines()
        except OSError as e:
            print(f"cannot read batch file: {e}", file=sys.stderr)
            return 2
        worst = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rc = one(args.api, line, args.lang, args.timestamps, "-")
            worst = max(worst, rc)
        return worst

    if not args.url:
        p.error("url required (or use --batch)")
    return one(args.api, args.url, args.lang, args.timestamps, args.out)


if __name__ == "__main__":
    sys.exit(main())
