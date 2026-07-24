import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { writeTestPng } from "./helpers/hard-negative-evidence.ts";

const builder = path.resolve(
  "model/training/build-independent-hard-negative-review-workspace.py",
);
const finalizer = path.resolve(
  "model/training/finalize-independent-hard-negative-review.py",
);
const python = process.env.PYTHON ?? "python";

const shaFile = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeFixture() {
  const root = mkdtempSync(path.join(tmpdir(), "independent-hard-negative-review-"));
  const images = path.join(root, "images");
  const workspace = path.join(root, "workspace");
  const protectedRoles = {
    train: path.join(root, "train.json"),
    val: path.join(root, "val.json"),
    frozenTest: path.join(root, "frozen-test.json"),
  };
  Object.values(protectedRoles).forEach((file) => writeJson(file, {}));

  const entries = Array.from({ length: 4 }, (_, index) => {
    const sequence = String(index + 1).padStart(3, "0");
    const variant = String(index + 1).padStart(2, "0");
    const fileName =
      `hard_negative_independent_20260724_${sequence}_test_family_${variant}.png`;
    const sourcePath = path.join(images, fileName);
    writeTestPng(sourcePath, index + 1);
    return {
      fileName,
      sourcePath,
      sha256: shaFile(sourcePath),
      width: 320,
      height: 320,
      authorizedUses: [
        "commercial-model-training",
        "long-term-regression",
      ],
      trainingEligibility:
        "permitted-only-after-original-resolution-review-and-source-role-isolation",
    };
  });
  const authorization = path.join(root, "authorization.json");
  writeJson(authorization, {
    ok: true,
    decision: "A",
    status: "confirmed",
    currentTrainingUse: "prohibited",
    authorizedUses: [
      "commercial-model-training",
      "long-term-regression",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
    roleConstraint:
      "authorization-does-not-assign-train-validation-or-holdout-role",
    entriesSha256: createHash("sha256")
      .update(canonical(entries))
      .digest("hex"),
    entries,
  });
  const machineAudit = path.join(root, "machine-audit.json");
  writeJson(machineAudit, {
    decodedCount: entries.length,
    decodeFailures: [],
    records: entries.map((entry) => ({
      fileName: entry.fileName,
      sha256: entry.sha256,
      width: entry.width,
      height: entry.height,
    })),
  });
  return {
    root,
    workspace,
    authorization,
    machineAudit,
    protectedRoles,
    entries,
  };
}

function buildFixture(item: ReturnType<typeof makeFixture>) {
  return spawnSync(
    python,
    [
      builder,
      "--authorization",
      item.authorization,
      "--machine-audit",
      item.machineAudit,
      "--train-index",
      item.protectedRoles.train,
      "--val-index",
      item.protectedRoles.val,
      "--frozen-test-manifest",
      item.protectedRoles.frozenTest,
      "--output-dir",
      item.workspace,
    ],
    { encoding: "utf8" },
  );
}

function completeDecisions(item: ReturnType<typeof makeFixture>) {
  const source = path.join(item.workspace, "review-decisions-v1.csv");
  const target = path.join(item.root, "review-decisions-completed-v1.csv");
  const lines = readFileSync(source, "utf8").replace(/^\uFEFF/, "").trimEnd().split(/\r?\n/);
  const completed = lines.map((line, index) => {
    if (index === 0) return line;
    const fields = line.split(",");
    assert.equal(fields.length, 9);
    if (index === 2) {
      fields[6] = "exclude";
      fields[7] = "impossible-hand-topology";
      fields[8] = "Original-resolution review found an impossible four-digit topology.";
    } else {
      fields[6] = "pass";
      fields[7] = "";
      fields[8] =
        "Original-resolution review found a clear complete deployment hard negative.";
    }
    return fields.join(",");
  });
  writeFileSync(target, `\uFEFF${completed.join("\n")}\n`);
  return target;
}

test("builds and finalizes hash-bound independent hard-negative decisions", () => {
  const item = makeFixture();
  const built = buildFixture(item);
  assert.equal(built.status, 0, built.stderr);

  const workspaceFile = path.join(item.workspace, "review-workspace-v1.json");
  const workspace = JSON.parse(readFileSync(workspaceFile, "utf8"));
  assert.equal(workspace.summary.authorizedImages, 4);
  assert.equal(workspace.summary.reviewSheets, 1);
  assert.equal(workspace.policy.reviewSheetsUseSourcePixelsWithoutResampling, true);
  assert.equal(workspace.summary.protectedRoleIdentityMatches, 0);

  const decisions = completeDecisions(item);
  const output = path.join(item.root, "finalized");
  const finalized = spawnSync(
    python,
    [
      finalizer,
      "--workspace",
      workspaceFile,
      "--decisions",
      decisions,
      "--output-dir",
      output,
    ],
    { encoding: "utf8" },
  );
  assert.equal(finalized.status, 0, finalized.stderr);

  const review = JSON.parse(
    readFileSync(path.join(output, "hard-negative-review-decisions-v1.json"), "utf8"),
  );
  assert.equal(review.summary.originalResolutionReviewed, 4);
  assert.equal(review.summary.passedCandidates, 3);
  assert.equal(review.summary.failedSelectedCandidates, 1);
  assert.equal(review.exclusions[0].defectCodes[0], "impossible-hand-topology");

  const manifest = JSON.parse(
    readFileSync(path.join(output, "hard-negative-candidate-manifest-v1.json"), "utf8"),
  );
  assert.equal(manifest.summary.safeHardNegativeCount, 3);
  assert.equal(manifest.gates.trainingStillProhibited, true);
  assert.ok(
    manifest.candidates.every(
      (candidate: { trainingUse: string }) => candidate.trainingUse === "prohibited",
    ),
  );
});

test("rejects source-image byte drift after the review workspace is built", () => {
  const item = makeFixture();
  const built = buildFixture(item);
  assert.equal(built.status, 0, built.stderr);
  const decisions = completeDecisions(item);
  writeFileSync(item.entries[0].sourcePath, "tampered-image-bytes\n");

  const finalized = spawnSync(
    python,
    [
      finalizer,
      "--workspace",
      path.join(item.workspace, "review-workspace-v1.json"),
      "--decisions",
      decisions,
      "--output-dir",
      path.join(item.root, "rejected"),
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(finalized.status, 0);
  assert.match(finalized.stderr, /source image SHA-256 drift|current image SHA-256 drift/);
});
