import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("SAM assisted annotation requires vision prompts and emits reviewed polygons", async () => {
  const source = await readFile("model/training/sam-assisted-nail-annotation.py", "utf8");
  assert.match(source, /vision-guided-box-center-positive-corner-negative-prompts-plus-sam2/);
  assert.match(source, /labels\.append\(\[1, 0, 0, 0, 0\]\)/);
  assert.match(source, /annotationMethod.*vision-guided-sam2/);
  assert.match(source, /pointPolygonTest/);
  assert.match(source, /sam-reviewed-overlay/);
  assert.match(source, /box-only fallback returned/);
  assert.match(source, /boxOnlyFallbackPromptCount/);
  assert.match(source, /zip\(boxes, points, labels, strict=True\)/);
});
