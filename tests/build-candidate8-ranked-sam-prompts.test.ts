import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-candidate8-ranked-sam-prompts.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("candidate8 ranked prompts keep exact expected count and remain candidate-only", () => {
  const root = mkdtempSync(path.join(tmpdir(), "candidate8-prompts-"));
  const workspace = path.join(root, "workspace.json");
  const annotation = path.join(root, "annotation.json");
  const prelabels = path.join(root, "prelabels.json");
  const output = path.join(root, "prompts.json");
  writeFileSync(workspace, JSON.stringify({
    ok: true,
    decision: "candidate8_annotation_workspace_ready_candidate_only",
    trainingUse: "prohibited",
    items: [{ fileName: "a.jpg", sha256: "a".repeat(64), imageSha256: "a".repeat(64), sourceGroup: "g1", expectedFullyVisibleNails: 1 }],
  }));
  writeFileSync(annotation, JSON.stringify({
    image: { fileName: "a.jpg", sourceGroup: "g1", width: 100, height: 100 },
    annotations: [
      { polygon: [{ x: 10, y: 10 }, { x: 20, y: 10 }, { x: 20, y: 20 }, { x: 10, y: 20 }], attributes: { confidence: 0.9 } },
      { polygon: [{ x: 70, y: 70 }, { x: 80, y: 70 }, { x: 80, y: 80 }, { x: 70, y: 80 }], attributes: { confidence: 0.1 } },
    ],
  }));
  writeFileSync(prelabels, JSON.stringify({
    ok: true,
    decision: "candidate_only_not_training_truth",
    trainingUse: "prohibited",
    originalResolutionReviewRequired: true,
    workspaceManifestSha256: hash(workspace),
    items: [{ fileName: "a.jpg", sha256: "a".repeat(64), sourceGroup: "g1", annotationPath: annotation }],
  }));
  const result = spawnSync("python", [script, "--workspace-manifest", workspace, "--prelabel-report", prelabels, "--output", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.promptCount, 1);
  assert.equal(report.images[0].selectedCandidateIndices[0], 1);
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.policy.originalResolutionReviewRequired, true);
});
