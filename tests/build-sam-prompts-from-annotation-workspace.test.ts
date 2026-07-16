import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = path.resolve("model/training/build-sam-prompts-from-annotation-workspace.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("workspace SAM prompt builder binds evidence and preserves each source group", () => {
  const root = mkdtempSync(path.join(tmpdir(), "workspace-sam-prompts-"));
  const annotations = path.join(root, "annotations");
  mkdirSync(annotations);
  const workspace = path.join(root, "workspace.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "annotation_workspace_ready_candidate_only", items: [{ fileName: "a.jpg", sha256: "a", sourceGroup: "g1", expectedFullyVisibleNails: 2 }] }));
  const annotation = path.join(annotations, "a.json");
  writeFileSync(annotation, JSON.stringify({ image: { width: 100, height: 200 }, annotations: [{ polygon: [{ x: 10, y: 20 }, { x: 30, y: 20 }, { x: 30, y: 60 }, { x: 10, y: 60 }] }] }));
  const prelabel = path.join(root, "prelabel.json");
  writeFileSync(prelabel, JSON.stringify({ ok: true, decision: "candidate_only_not_training_truth", items: [{ fileName: "a.jpg", annotationPath: annotation }] }));
  const audit = path.join(root, "audit.json");
  writeFileSync(audit, JSON.stringify({ ok: true, decision: "prelabel_candidate_audit_pass_original_resolution_review_required", inputs: { workspaceManifestSha256: hash(workspace), prelabelReportSha256: hash(prelabel) } }));
  const output = path.join(root, "prompts.json");
  const result = spawnSync("python", [script, "--workspace-manifest", workspace, "--prelabel-report", prelabel, "--prelabel-audit", audit, "--output", output], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const prompts = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(prompts.promptCount, 1);
  assert.equal(prompts.images[0].sourceGroup, "g1");
  assert.equal(prompts.images[0].promptModes[0], "box-center");
  assert.equal(prompts.policy.trainingUse, "prohibited");
});
