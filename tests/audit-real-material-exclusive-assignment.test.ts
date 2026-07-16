import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const authorizeScript = path.resolve("model/training/authorize-real-material-candidate-intake.py");
const auditScript = path.resolve("model/training/audit-real-material-exclusive-assignment.py");

function sha256(filePath: string) {
  return createHash("sha256").update(readFileSync(filePath)).digest("hex");
}

function fixture(decision: "A" | "B" | "C" = "A") {
  const root = mkdtempSync(path.join(tmpdir(), "real-material-assignment-"));
  const imageRoot = path.join(root, "images");
  mkdirSync(imageRoot);
  const files = ["nail_00001_note-a_0.jpg", "nail_00002_note-a_1.jpg", "nail_00003_note-b_0.jpg"];
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
      batchId: "assignment-test",
      ok: true,
      root: imageRoot,
      authorization: { status: "pending-user-confirmation", authorizedUses: [], trainingUse: "prohibited" },
      status: "candidate_inventory_pass_authorization_and_visual_review_pending",
      counts: { images: 3, sourceGroups: 2 },
      entries: files.map((fileName, index) => ({
        fileName,
        sha256: sha256(path.join(imageRoot, fileName)),
        sourceGroup: index < 2 ? "group-a" : "group-b",
        decision: "pending-visual-review-and-authorization",
        trainingUse: "prohibited",
      })),
    }),
    "utf8"
  );
  const authorization = path.join(root, "authorization.json");
  execFileSync("python", [
    authorizeScript,
    "--intake", intake,
    "--decision", decision,
    "--confirmed-by", "workspace-user",
    "--confirmation-note", `user selected ${decision}`,
    "--output", authorization,
  ]);
  return { root, authorization, files };
}

function run(item: ReturnType<typeof fixture>, rows?: string[]) {
  const output = path.join(item.root, "assignment-audit.json");
  const args = [auditScript, "--authorization", item.authorization, "--output", output];
  if (rows) {
    const csv = path.join(item.root, "review.csv");
    writeFileSync(csv, ["fileName,reviewStatus,assignedRole,note", ...rows].join("\n") + "\n", "utf8");
    args.push("--review-csv", csv);
  }
  const result = spawnSync("python", args, { encoding: "utf8" });
  return { result, output };
}

test("exclusive assignment accepts final source-group-atomic A assignments", () => {
  const item = fixture("A");
  const { result, output } = run(item, [
    `${item.files[0]},pass,train,complete nail review passed`,
    `${item.files[1]},pass,train,complete nail review passed`,
    `${item.files[2]},pass,independent-release-test,complete nail review passed`,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.decision, "approved_real_material_exclusive_assignment");
  assert.equal(report.counts.leakingSourceGroups, 0);
  assert.equal(report.counts.byRole.train, 2);
  assert.equal(report.counts.byRole["independent-release-test"], 1);
});

test("exclusive assignment rejects source-group leakage and incomplete review", () => {
  const item = fixture("A");
  const { result, output } = run(item, [
    `${item.files[0]},pass,train,passed`,
    `${item.files[1]},pass,val,passed`,
  ]);
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, false);
  assert.equal(report.counts.leakingSourceGroups, 1);
  assert.match(report.errors.join("\n"), /does not cover 1|multiple roles/);
});

test("exclusive assignment rejects unreviewed or unauthorized B roles", () => {
  const item = fixture("B");
  const { result, output } = run(item, [
    `${item.files[0]},rework,unassigned,incomplete nail`,
    `${item.files[1]},pass,train,passed`,
    `${item.files[2]},exclude,archive,cropped nail`,
  ]);
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.match(report.errors.join("\n"), /reviewStatus must be pass or exclude|not authorized by decision B/);
});

test("archive-only C authorization needs no visual review CSV and never assigns training", () => {
  const item = fixture("C");
  const { result, output } = run(item);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(readFileSync(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.counts.byRole.archive, 3);
  assert.ok(report.assignments.every((entry: { assignedRole: string }) => entry.assignedRole === "archive"));
});
