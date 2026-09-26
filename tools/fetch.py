#!/usr/bin/env python3
"""ShrutiLipi CLI — fetch YouTube transcripts via the backend API.

Stdlib only (rich is optional — pretty progress/tables when installed).
Examples:
  python tools/fetch.py HHUsHkYhkcM
  python tools/fetch.py https://youtu.be/HHUsHkYhkcM --lang hi --timestamps
  python tools/fetch.py HHUsHkYhkcM --out transcript.txt
  python tools/fetch.py --batch urls.txt --api https://shrutilipi-backend.onrender.com

Exit codes: 0 = ok, 1 = no captions / not found, 2 = other error.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API = "http://localhost:8000"

try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )
    from rich.table import Table

    RICH = True
except ImportError:
    RICH = False


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


def emit(data: dict, timestamps: bool, out: str | None, pretty: Console | None) -> int:
    text = render(data, timestamps)
    if out:
        where = f"{data['videoId']}.txt" if out == "-" else out
        with open(where, "w", encoding="utf-8") as fh:
            fh.write(text)
        msg = f"{data['videoId']}: {len(data['segments'])} segments ({data['language']}) -> {where}"
    else:
        where = None
        print(text)
        msg = f"{data['videoId']}: {len(data['segments'])} segments ({data['language']})"
    if pretty is not None:
        pretty.print(f"[green]{msg}[/green]")
    else:
        print(msg, file=sys.stderr)
    return 0


def fail_msg(url: str, msg: str, pretty: Console | None) -> None:
    if pretty is not None:
        pretty.print(f"[red]{url}: {msg}[/red]")
    else:
        print(f"{url}: {msg}", file=sys.stderr)


def one(api: str, url: str, lang: str, timestamps: bool, out: str | None,
        pretty: Console | None) -> int:
    try:
        data = fetch(api, url, lang)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("detail", "")
        except Exception:
            detail = ""
        fail_msg(url, f"HTTP {e.code} {detail}", pretty)
        return 1 if detail in ("no_captions", "invalid_url") else 2
    except Exception as e:
        fail_msg(url, str(e), pretty)
        return 2
    return emit(data, timestamps, out, pretty)


def run_batch(args, pretty: Console | None) -> int:
    try:
        lines = open(args.batch, encoding="utf-8").read().splitlines()
    except OSError as e:
        fail_msg(args.batch, f"cannot read batch file: {e}", pretty)
        return 2
    urls = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not urls:
        return 0

    rows: list[tuple[str, str, str]] = []
    worst = 0

    if pretty is not None and RICH:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=pretty,
            transient=True,
        )
        with progress:
            task = progress.add_task("fetching", total=len(urls))
            for u in urls:
                rc = one(args.api, u, args.lang, args.timestamps, "-", None)
                rows.append((u, "", "ok" if rc == 0 else f"exit {rc}"))
                worst = max(worst, rc)
                progress.advance(task)
    else:
        for i, u in enumerate(urls, 1):
            if pretty is None:
                print(f"[{i}/{len(urls)}] {u}", file=sys.stderr)
            rc = one(args.api, u, args.lang, args.timestamps, "-", pretty)
            rows.append((u, "", "ok" if rc == 0 else f"exit {rc}"))
            worst = max(worst, rc)

    if pretty is not None and RICH:
        table = Table(title=f"batch: {args.batch}")
        table.add_column("URL", overflow="fold")
        table.add_column("Status", justify="right")
        for u, _, status in rows:
            style = "green" if status == "ok" else "red"
            table.add_row(u, f"[{style}]{status}[/{style}]")
        pretty.print(table)
    else:
        ok = sum(1 for _, _, s in rows if s == "ok")
        print(f"batch done: {ok}/{len(rows)} ok (exit {worst})", file=sys.stderr)
    return worst


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch a YouTube transcript via ShrutiLipi.")
    p.add_argument("url", nargs="?", help="YouTube URL or 11-char video ID")
    p.add_argument("--lang", default="en", help="caption language (default: en)")
    p.add_argument("--api", default=DEFAULT_API, help=f"backend base URL (default: {DEFAULT_API})")
    p.add_argument("--out", help="write to file instead of stdout ('-' = <videoId>.txt)")
    p.add_argument("--timestamps", action="store_true", help="prefix lines with [m:ss]")
    p.add_argument("--batch", help="file with one URL per line (# comments allowed)")
    p.add_argument("--plain", action="store_true", help="force plain output even if rich is installed")
    args = p.parse_args()

    pretty: Console | None = Console(stderr=True) if (RICH and not args.plain) else None

    if args.batch:
        return run_batch(args, pretty)

    if not args.url:
        p.error("url required (or use --batch)")
    return one(args.api, args.url, args.lang, args.timestamps, args.out, pretty)


if __name__ == "__main__":
    sys.exit(main())
