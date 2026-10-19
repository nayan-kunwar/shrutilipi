#!/usr/bin/env python3
"""ShrutiLipi CLI — fetch YouTube transcripts via the backend API.

Stdlib only (rich is optional — pretty progress/tables when installed).
Examples:
  python tools/fetch.py HHUsHkYhkcM
  python tools/fetch.py https://youtu.be/HHUsHkYhkcM --lang hi --timestamps
  python tools/fetch.py HHUsHkYhkcM --out transcript.txt
  python tools/fetch.py HHUsHkYhkcM --srt --out subs.srt
  python tools/fetch.py --batch urls.txt --api https://shrutilipi-backend.onrender.com

Exit codes: 0 = ok, 1 = no captions / not found, 2 = other error.
"""

from __future__ import annotations

import argparse
import json
import math
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


def _round_ms(value: float) -> int:
    # Math.round parity with the TS twin: nearest, ties away from zero
    # (Python's round() is banker's rounding and would drift at .5 ms).
    return math.floor(value + 0.5)


def cue_time(ms: int, sep: str) -> str:
    """Twin of cueTime() in packages/shared/src/subtitles.ts (HH:MM:SS,mmm)."""
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{msec:03d}"


def render_cues(segments: list[dict], sep: str) -> str:
    """Twin of cues() in packages/shared/src/subtitles.ts — same edge-case rules."""
    blocks: list[str] = []
    n = 0
    for seg in segments:
        text = seg.get("text", "")
        if not text.strip():  # no stray empty cue boxes
            continue
        n += 1
        start_ms = max(0, _round_ms(seg["start"] * 1000))
        # Some players drop zero-length cues; clamp every cue to at least 1 ms.
        end_ms = max(_round_ms((seg["start"] + seg["duration"]) * 1000), start_ms + 1)
        blocks.append(f"{n}\n{cue_time(start_ms, sep)} --> {cue_time(end_ms, sep)}\n{text}")
    return "\n\n".join(blocks)


def render_srt(segments: list[dict]) -> str:
    body = render_cues(segments, ",")
    return body + "\n" if body else ""


def render_vtt(segments: list[dict]) -> str:
    body = render_cues(segments, ".")
    return f"WEBVTT\n\n{body}\n" if body else "WEBVTT\n"


def fetch(api: str, url: str, lang: str, timeout: float = 60.0) -> dict:
    qs = urllib.parse.urlencode({"url": url, "lang": lang})
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/transcript?{qs}",
        headers={"User-Agent": "shrutilipi-cli/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def render(data: dict, timestamps: bool, fmt: str = "txt") -> str:
    if fmt == "srt":
        return render_srt(data["segments"])
    if fmt == "vtt":
        return render_vtt(data["segments"])
    if not timestamps:
        return data["plainText"]
    return "\n".join(
        f"[{format_time(seg['start'])}] {seg['text']}" for seg in data["segments"]
    )


def emit(data: dict, timestamps: bool, out: str | None, pretty: Console | None,
         fmt: str = "txt") -> int:
    text = render(data, timestamps, fmt)
    if out:
        where = f"{data['videoId']}.{fmt}" if out == "-" else out
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
        pretty: Console | None, fmt: str = "txt") -> int:
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
    return emit(data, timestamps, out, pretty, fmt)


def run_batch(args, pretty: Console | None) -> int:
    fmt = "srt" if args.srt else "vtt" if args.vtt else "txt"
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
                rc = one(args.api, u, args.lang, args.timestamps, "-", None, fmt)
                rows.append((u, "", "ok" if rc == 0 else f"exit {rc}"))
                worst = max(worst, rc)
                progress.advance(task)
    else:
        for i, u in enumerate(urls, 1):
            if pretty is None:
                print(f"[{i}/{len(urls)}] {u}", file=sys.stderr)
            rc = one(args.api, u, args.lang, args.timestamps, "-", pretty, fmt)
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
    p.add_argument("--out", help="write to file instead of stdout ('-' = <videoId>.<fmt>)")
    p.add_argument("--timestamps", action="store_true", help="prefix lines with [m:ss]")
    p.add_argument("--srt", action="store_true", help="emit SubRip subtitles instead of text")
    p.add_argument("--vtt", action="store_true", help="emit WebVTT subtitles instead of text")
    p.add_argument("--batch", help="file with one URL per line (# comments allowed)")
    p.add_argument("--plain", action="store_true", help="force plain output even if rich is installed")
    args = p.parse_args()

    if args.srt and args.vtt:
        p.error("--srt and --vtt are mutually exclusive")
    if (args.srt or args.vtt) and args.timestamps:
        p.error("--timestamps only applies to text output")
    fmt = "srt" if args.srt else "vtt" if args.vtt else "txt"

    pretty: Console | None = Console(stderr=True) if (RICH and not args.plain) else None

    if args.batch:
        return run_batch(args, pretty)

    if not args.url:
        p.error("url required (or use --batch)")
    return one(args.api, args.url, args.lang, args.timestamps, args.out, pretty, fmt)


if __name__ == "__main__":
    sys.exit(main())
