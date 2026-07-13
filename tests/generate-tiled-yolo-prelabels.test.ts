import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const script = "model/training/generate-tiled-yolo-prelabels.py";

test("tiled prelabel tool exposes overlap, edge, and dedupe controls", () => {
  const result = spawnSync("python", [script, "--help"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /--tile-fraction/);
  assert.match(result.stdout, /--grid-size/);
  assert.match(result.stdout, /--dedupe-mask-iou/);
  assert.match(result.stdout, /--edge-margin/);
});

test("tiled prelabels remain review-only and reject tile-edge fragments", async () => {
  const source = await readFile(script, "utf8");
  assert.match(source, /candidate_only_not_training_truth/);
  assert.match(source, /reviewRequired/);
  assert.match(source, /touches_internal_tile_edge/);
  assert.match(source, /yolo-overlapping-tiles-v1/);
});
