import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/merge-reviewed-region-reports.py");

function sha256(data: Buffer) {
  return createHash("sha256").update(data).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "merge-reviewed-regions-"));
  const baseDir = path.join(root, "base");
  const replacementDir = path.join(root, "replacement");
  const outputDir = path.join(root, "output");
  mkdirSync(baseDir);
  mkdirSync(replacementDir);
  const oldBytes = Buffer.from("old-region");
  const newBytes = Buffer.from("new-region");
  writeFileSync(path.join(baseDir, "old.png"), oldBytes);
  writeFileSync(path.join(replacementDir, "new.png"), newBytes);
  const common = {
    parentFileName: "parent.jpg",
    parentSha256: "a".repeat(64),
    sourceGroup: "stable-parent-group",
  };
  const baseReport = path.join(root, "base.json");
  const replacementReport = path.join(root, "replacement.json");
  const outputReport = path.join(root, "merged.json");
  writeFileSync(
    baseReport,
    JSON.stringify({
      ok: true,
      outputs: [
        {
          ...common,
          regionId: "primary",
          outputFileName: "old.png",
          outputSha256: sha256(oldBytes),
        },
      ],
    }),
  );
  writeFileSync(
    replacementReport,
    JSON.stringify({
      ok: true,
      outputs: [
        {
          ...common,
          regionId: "main-v2",
          outputFileName: "new.png",
          outputSha256: sha256(newBytes),
        },
      ],
    }),
  );
  return { baseDir, replacementDir, outputDir, baseReport, replacementReport, outputReport };
}

function args(item: ReturnType<typeof fixture>) {
  return [
    script,
    "--base-report",
    item.baseReport,
    "--base-dir",
    item.baseDir,
    "--replacement-report",
    item.replacementReport,
    "--replacement-dir",
    item.replacementDir,
    "--output-dir",
    item.outputDir,
    "--output-report",
    item.outputReport,
  ];
}

test("reviewed region replacement preserves one stable parent and materializes the new crop", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.outputReport, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.completedCount, 1);
  assert.equal(report.outputs[0].outputFileName, "new.png");
  assert.equal(report.outputs[0].sourceGroup, "stable-parent-group");
  assert.equal(readFileSync(path.join(item.outputDir, "new.png"), "utf8"), "new-region");
});

test("reviewed region replacement rejects source-group drift", () => {
  const item = fixture();
  const replacement = JSON.parse(readFileSync(item.replacementReport, "utf8"));
  replacement.outputs[0].sourceGroup = "different-group";
  writeFileSync(item.replacementReport, JSON.stringify(replacement));
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.outputReport, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /sourceGroup mismatch/);
});
