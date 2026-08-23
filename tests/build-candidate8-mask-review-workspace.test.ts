import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-candidate8-mask-review-workspace.py");

test("candidate8 mask review workspace rejects an unsafe source workspace", () => {
  const root = mkdtempSync(path.join(tmpdir(), "candidate8-mask-review-"));
  const workspace = path.join(root, "workspace.json");
  const placeholder = path.join(root, "placeholder.json");
  writeFileSync(workspace, JSON.stringify({ ok: true, decision: "candidate8_annotation_workspace_ready_candidate_only", trainingUse: "permitted" }));
  writeFileSync(placeholder, "{}");
  const result = spawnSync("python", [
    script,
    "--workspace-manifest", workspace,
    "--prompts", placeholder,
    "--sam-report", placeholder,
    "--geometry-audit", placeholder,
    "--visual-evidence", placeholder,
    "--output-dir", path.join(root, "output"),
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  assert.ok(result.stderr.length > 0);
});
