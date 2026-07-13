import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-reviewed-sam-repair-prompts.py");

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "sam-repair-prompts-"));
  const source = path.join(root, "source.json");
  const manifest = path.join(root, "manifest.json");
  const output = path.join(root, "output.json");
  writeFileSync(
    source,
    JSON.stringify({
      images: [
        {
          fileName: "sample.jpg",
          sourceGroup: "source-group-1",
          boxes: [
            [0.1, 0.1, 0.2, 0.2],
            [0.3, 0.3, 0.4, 0.4],
          ],
        },
      ],
    }),
  );
  writeFileSync(
    manifest,
    JSON.stringify({
      schemaVersion: 1,
      decision: "human_reviewed_prompt_repair_candidate_only",
      images: [
        {
          fileName: "sample.jpg",
          keepPromptIndices: [2],
          addBoxes: [[0.5, 0.5, 0.6, 0.6]],
          reviewReason: "drop false positive and add missed nail",
        },
      ],
    }),
  );
  return { source, manifest, output };
}

test("reviewed SAM repair prompts preserve provenance and apply keep/drop/add decisions", () => {
  const item = fixture();
  execFileSync("python", [
    script,
    "--source-prompts",
    item.source,
    "--repair-manifest",
    item.manifest,
    "--output",
    item.output,
  ]);
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.decision, "sam_repair_candidate_only_not_test_truth");
  assert.equal(document.imageCount, 1);
  assert.equal(document.promptCount, 2);
  assert.deepEqual(document.images[0].boxes, [
    [0.3, 0.3, 0.4, 0.4],
    [0.5, 0.5, 0.6, 0.6],
  ]);
  assert.equal(document.images[0].sourceGroup, "source-group-1");
  assert.match(document.sourcePromptSha256, /^[a-f0-9]{64}$/);
});

test("reviewed SAM repair prompts reject an out-of-range source index", () => {
  const item = fixture();
  const manifest = JSON.parse(readFileSync(item.manifest, "utf8"));
  manifest.images[0].keepPromptIndices = [3];
  writeFileSync(item.manifest, JSON.stringify(manifest));
  const result = spawnSync(
    "python",
    [
      script,
      "--source-prompts",
      item.source,
      "--repair-manifest",
      item.manifest,
      "--output",
      item.output,
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(result.status, 0);
  const document = JSON.parse(readFileSync(item.output, "utf8"));
  assert.equal(document.ok, false);
  assert.match(document.errors.join("\n"), /out of range/);
});
