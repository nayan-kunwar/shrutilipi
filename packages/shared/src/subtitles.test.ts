import { test } from "node:test";
import assert from "node:assert/strict";

import { toSrt, toVtt } from "./subtitles.ts";

test("srt: two cues, exact document shape", () => {
  const out = toSrt([
    { start: 0, duration: 3.25, text: "hello" },
    { start: 4, duration: 2, text: "world" },
  ]);
  assert.equal(
    out,
    "1\n00:00:00,000 --> 00:00:03,250\nhello\n\n" +
      "2\n00:00:04,000 --> 00:00:06,000\nworld\n"
  );
});

test("vtt: same cues with WEBVTT header and dot decimals", () => {
  const out = toVtt([
    { start: 0, duration: 3.25, text: "hello" },
    { start: 4, duration: 2, text: "world" },
  ]);
  assert.equal(
    out,
    "WEBVTT\n\n" +
      "1\n00:00:00.000 --> 00:00:03.250\nhello\n\n" +
      "2\n00:00:04.000 --> 00:00:06.000\nworld\n"
  );
});

test("hours always render two digits past the hour mark", () => {
  const out = toSrt([{ start: 3661.5, duration: 1, text: "x" }]);
  assert.ok(out.includes("01:01:01,500 --> 01:01:02,500"));
});

test("milliseconds round to nearest, padded to three digits", () => {
  assert.ok(toSrt([{ start: 0.0014, duration: 1, text: "r" }]).includes("00:00:00,001 -->"));
  assert.ok(toSrt([{ start: 0.005, duration: 1, text: "p" }]).includes("00:00:00,005 -->"));
});

test("zero-length cue clamps to at least 1 ms", () => {
  const out = toSrt([{ start: 5, duration: 0, text: "z" }]);
  assert.ok(out.includes("00:00:05,000 --> 00:00:05,001"));
});

test("negative duration clamps the same way", () => {
  const out = toSrt([{ start: 5, duration: -2, text: "n" }]);
  assert.ok(out.includes("00:00:05,000 --> 00:00:05,001"));
});

test("negative start clamps to zero", () => {
  const out = toSrt([{ start: -1, duration: 2, text: "neg" }]);
  assert.ok(out.includes("00:00:00,000 --> 00:00:01,000"));
});

test("empty-text segments are skipped and numbering stays contiguous", () => {
  const out = toSrt([
    { start: 0, duration: 1, text: "first" },
    { start: 1, duration: 1, text: "   " },
    { start: 2, duration: 1, text: "third" },
  ]);
  assert.ok(out.includes("1\n00:00:00,000 --> 00:00:01,000\nfirst"));
  assert.ok(out.includes("2\n00:00:02,000 --> 00:00:03,000\nthird"));
  assert.ok(!out.includes("00:00:01,000 -->")); // the blank segment produced no cue
  assert.ok(!out.includes("\n3\n")); // no gap left behind by the skip
});

test("exactly one trailing newline", () => {
  const out = toSrt([{ start: 0, duration: 1, text: "t" }]);
  assert.ok(out.endsWith("\n"));
  assert.ok(!out.endsWith("\n\n"));
});

test("empty segment list: srt is empty, vtt is header-only", () => {
  assert.equal(toSrt([]), "");
  assert.equal(toVtt([]), "WEBVTT\n");
});

test("multi-line caption text passes through untouched", () => {
  const out = toSrt([{ start: 0, duration: 1, text: "line A\nline B" }]);
  assert.ok(out.endsWith("1\n00:00:00,000 --> 00:00:01,000\nline A\nline B\n"));
});
