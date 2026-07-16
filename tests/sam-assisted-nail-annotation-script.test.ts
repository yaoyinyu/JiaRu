import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("SAM assisted annotation requires vision prompts and emits reviewed polygons", async () => {
  const source = await readFile("model/training/sam-assisted-nail-annotation.py", "utf8");
  assert.match(source, /vision-guided-box-center-positive-corner-negative-prompts-plus-sam2/);
  assert.match(source, /labels\.append\(\(\[1\] \* len\(positive_set\)\) \+ \(\[0\] \* len\(negative_set\)\)\)/);
  assert.match(source, /annotationMethod.*vision-guided-\{args\.engine\}/);
  assert.match(source, /pointPolygonTest/);
  assert.match(source, /sam-reviewed-overlay/);
  assert.match(source, /box-only fallback returned/);
  assert.match(source, /boxOnlyFallbackPromptCount/);
  assert.match(source, /boxOnlyFallbackPrompts/);
  assert.match(source, /"promptIndex": prompt_index/);
  assert.match(source, /"promptMode": prompt_mode/);
  assert.match(source, /"initialMaskCount": initial_mask_count/);
  assert.match(source, /def select_prompt_mask/);
  assert.match(source, /positiveHits/);
  assert.match(source, /negativeHits/);
  assert.match(source, /boxContainment/);
  assert.match(source, /multiMaskSelections/);
  assert.match(source, /source_width_span = max\(1, width - 1\)/);
  assert.match(source, /source_height_span = max\(1, height - 1\)/);
  assert.match(source, /data-exclusions\.json/);
  assert.match(source, /excludedFiles/);
  assert.match(source, /positivePoints count must match boxes count/);
  assert.match(source, /negativePoints count must match boxes count/);
  assert.match(source, /normalized_points_to_pixels/);
  assert.match(source, /promptModes count must match boxes count/);
  assert.match(source, /has invalid promptModes/);
  assert.match(source, /prompt \{prompt_index\} \(\{prompt_mode\}\)/);
  assert.match(source, /prompt \{index\} polygon conversion failed/);
  assert.match(source, /prompt_modes, strict=True/);
  assert.match(source, /occludedIndices must contain 1-based box indices/);
  assert.match(source, /"occluded": index in occluded_indices/);
  assert.match(source, /positive_set/);
  assert.match(source, /center-negative-corners/);
  assert.match(source, /box-center/);
  assert.match(source, /Tight reviewed boxes should normally use box mode/);
  assert.match(source, /item\.get\("sourceGroup", document\.get\("sourceGroup"\)\)/);
  assert.match(source, /sourceGroup must be a non-empty string on the image or prompt document/);
  assert.match(source, /"sourceGroup": source_group/);
  assert.match(source, /vision-guided-unprompted-mask-pool-plus-per-box-fastsam/);
  assert.match(source, /model\.predictor\.prompt\(base_results, bboxes=\[box\]\)/);
  assert.match(source, /zip\([\s\S]*boxes, points, positive_points, labels, prompt_modes, strict=True/);
  assert.match(source, /if mask_outputs[\s\S]*np\.empty\(\(0, height, width\), dtype=np\.float32\)/);
  assert.match(source, /candidate_only_not_training_truth/);
  assert.match(source, /sam_candidate_only_not_training_truth/);
  assert.match(source, /originalResolutionReviewRequired/);
});

test("SAM multimask selection prefers positive coverage without negative leakage", () => {
  const python = String.raw`
import importlib.util
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location("sam_assisted", Path("model/training/sam-assisted-nail-annotation.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FakeTensor:
    def __init__(self, value):
        self.value = value
    def cpu(self):
        return self
    def numpy(self):
        return self.value

leaky = np.zeros((10, 10), dtype=np.float32)
leaky[5, 5] = 1
leaky[1, 1] = 1
clean = np.zeros((10, 10), dtype=np.float32)
clean[5, 5] = 1
clean[5, 6] = 1
mask, diagnostics = module.select_prompt_mask(
    FakeTensor(np.stack([leaky, clean])),
    [[5.0, 5.0]],
    [[1.0, 1.0]],
    [0.0, 0.0, 9.0, 9.0],
    10,
    10,
)
assert diagnostics["candidateIndex"] == 2, diagnostics
assert diagnostics["positiveHits"] == 1, diagnostics
assert diagnostics["negativeHits"] == 0, diagnostics
assert int(mask.sum()) == 2
print(diagnostics)
`;
  const result = spawnSync("python", ["-c", python], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /candidateIndex.*2/);
});
