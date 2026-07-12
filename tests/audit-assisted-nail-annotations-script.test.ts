import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("assisted annotation audit keeps machine candidates out of training truth", async () => {
  const source = await readFile("model/training/audit-assisted-nail-annotations.py", "utf8");
  assert.match(source, /candidate_only_not_training_truth/);
  assert.match(source, /prompt_center_outside_polygon/);
  assert.match(source, /polygon_extends_beyond_prompt/);
  assert.match(source, /polygon_too_large/);
  assert.match(source, /minimumBoundsContainment/);
  assert.match(source, /candidate_overlaps_peer/);
  assert.match(source, /maximumPeerBoundsIou/);
  assert.match(source, /utf-8-sig/);
});
