import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const authorizeScript = path.resolve("model/training/authorize-real-material-candidate-intake.py");
const script = path.resolve("model/training/build-real-material-review-workspace.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "real-material-review-workspace-"));
  const imageRoot = path.join(root, "images");
  mkdirSync(imageRoot);
  const files = Array.from({ length: 5 }, (_, index) => `nail_${String(index + 1).padStart(5, "0")}_note-${index < 3 ? "a" : "b"}_${index}.jpg`);
  for (const [index, fileName] of files.entries()) {
    execFileSync("python", [
      "-c",
      `from PIL import Image; Image.new('RGB', (64, 96), (${100 + index}, 120, 140)).save(r'${path.join(imageRoot, fileName)}')`,
    ]);
  }
  const intake = path.join(root, "intake.json");
  writeFileSync(
    intake,
    JSON.stringify({
      schemaVersion: 1,
      batchId: "review-workspace-test",
      ok: true,
      root: imageRoot,
      authorization: { status: "pending-user-confirmation", authorizedUses: [], trainingUse: "prohibited" },
      status: "candidate_inventory_pass_authorization_and_visual_review_pending",
      counts: { images: 5, sourceGroups: 2 },
      entries: files.map((fileName, index) => ({
        fileName,
        sha256: sha256(path.join(imageRoot, fileName)),
        width: 64,
        height: 96,
        sourceGroup: index < 3 ? "group-a" : "group-b",
        trainingUse: "prohibited",
      })),
    }),
    "utf8"
  );
  const authorization = path.join(root, "authorization.json");
  execFileSync("python", [
    authorizeScript,
    "--intake", intake,
    "--decision", "A",
    "--confirmed-by", "workspace-user",
    "--confirmation-note", "fixture A",
    "--output", authorization,
  ]);
  return { root, imageRoot, files, authorization, outputDir: path.join(root, "workspace") };
}

test("review workspace keeps source groups intact and covers every authorized image", () => {
  const item = fixture();
  const result = spawnSync("python", [
    script,
    "--authorization", item.authorization,
    "--output-dir", item.outputDir,
    "--target-shard-size", "2",
  ], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(path.join(item.outputDir, "review-workspace-report.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.images, 5);
  assert.equal(report.counts.sourceGroups, 2);
  assert.equal(report.counts.shards, 2);
  assert.deepEqual(report.shards.map((shard: { images: number }) => shard.images), [3, 2]);
  const groups = report.shards.flatMap((shard: { sourceGroups: string[] }) => shard.sourceGroups);
  assert.deepEqual(groups, ["group-a", "group-b"]);
  const combined = readFileSync(report.combinedReviewCsv, "utf8");
  assert.equal(item.files.filter((fileName) => combined.includes(fileName)).length, 5);
  assert.equal(report.policy.blankFieldsAreNotApproval, true);
});

test("review workspace rejects image drift before writing review shards", () => {
  const item = fixture();
  writeFileSync(path.join(item.imageRoot, item.files[0]), "changed", "utf8");
  const result = spawnSync("python", [
    script,
    "--authorization", item.authorization,
    "--output-dir", item.outputDir,
  ], { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(path.join(item.outputDir, "review-workspace-report.json"), "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /missing or changed/);
});
