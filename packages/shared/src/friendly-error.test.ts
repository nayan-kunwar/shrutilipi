import { test } from "node:test";
import assert from "node:assert/strict";

import { friendlyError } from "./errors.ts";

test("summary codes map to actionable sentences", () => {
  assert.match(friendlyError(503, "summary_disabled"), /isn't configured/);
  assert.match(friendlyError(429, "summary_rate_limited"), /wait a minute/);
  assert.match(friendlyError(503, "summary_busy"), /already being generated/);
  assert.match(friendlyError(502, "summary_failed"), /transcript is unaffected/);
});

test("transcript codes keep their existing copy", () => {
  assert.match(friendlyError(400, "invalid_url"), /valid YouTube URL/);
  assert.match(friendlyError(404, "no_captions"), /No captions found/);
  assert.match(friendlyError(429, "rate_limited"), /requesting transcripts/);
});

test("unknown details stay visible instead of being swallowed", () => {
  assert.equal(friendlyError(418, "teapot"), "teapot");
});

test("404 without a known code falls back to a generic sentence", () => {
  assert.equal(friendlyError(404, "something_new"), "Transcript not found for this video.");
});
