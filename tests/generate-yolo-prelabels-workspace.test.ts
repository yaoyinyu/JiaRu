import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/generate-yolo-prelabels.py");
const hash = (file: string) => createHash("sha256").update(readFileSync(file)).digest("hex");

test("YOLO prelabel dry-run preserves per-image source groups from the workspace", () => {
  const root = mkdtempSync(path.join(tmpdir(), "yolo-workspace-"));
  const imageDir = path.join(root, "images");
  mkdirSync(imageDir);
  const files = ["a.jpg", "b.jpg"];
  files.forEach((file, index) => execFileSync("python", ["-c", `from PIL import Image; Image.new('RGB',(64,96),(${index + 30},40,50)).save(r'${path.join(imageDir, file)}')`]));
  const manifest = path.join(root, "manifest.json");
  writeFileSync(manifest, JSON.stringify({
    ok: true,
    decision: "annotation_workspace_ready_candidate_only",
    imageDir,
    items: files.map((fileName, index) => ({
      fileName,
      sha256: hash(path.join(imageDir, fileName)),
      sourceGroup: `group-${index + 1}`,
      trainingUse: "prohibited",
      annotationTruthStatus: "not-started",
    })),
  }));
  const model = path.join(root, "model.pt");
  writeFileSync(model, "test model only");
  const report = path.join(root, "report.json");
  const result = spawnSync("python", [
    script,
    "--model", model,
    "--image-dir", imageDir,
    "--workspace-manifest", manifest,
    "--annotation-dir", path.join(root, "annotations"),
    "--overlay-dir", path.join(root, "overlays"),
    "--report", report,
    "--dry-run",
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(readFileSync(report, "utf8"));
  assert.equal(output.decision, "prelabel_input_validation_pass_candidate_generation_not_run");
  assert.deepEqual(output.items.map((item: { sourceGroup: string }) => item.sourceGroup), ["group-1", "group-2"]);
  assert.ok(output.items.every((item: { sha256: string }) => item.sha256.length === 64));
});
