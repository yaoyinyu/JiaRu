import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  createProtectedRoleEvidence,
  writePatternTestPng,
} from "./helpers/hard-negative-evidence.ts";
import { createFormalThresholdEvidence } from "./helpers/formal-threshold-evidence.ts";

const builder = path.resolve(
  "model/training/build-independent-hard-negative-review-workspace.py",
);
const recorder = path.resolve(
  "model/training/record-training-hard-negative-authorization.py",
);
const independentRecorder = path.resolve(
  "model/training/record-independent-hard-negative-authorization.py",
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

const canonicalSha = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");

function writeJson(file: string, value: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function makeFixture() {
  const root = mkdtempSync(path.join(tmpdir(), "independent-hard-negative-review-"));
  const images = path.join(root, "images");
  const workspace = path.join(root, "workspace");
  const protectedRoles = createProtectedRoleEvidence(root);

  const relativePaths = Array.from({ length: 4 }, (_, index) => {
    const sequence = String(index + 1).padStart(3, "0");
    const variant = String(index + 1).padStart(2, "0");
    const fileName =
      `hard_negative_training_20260724_${sequence}_test_family_${variant}.png`;
    const relativePath = path.join("batch", fileName);
    const sourcePath = path.join(images, relativePath);
    writePatternTestPng(sourcePath, index + 1, 768, 768);
    return relativePath.replaceAll("\\", "/");
  });
  const userAuthorization = path.join(root, "user-authorization.json");
  const confirmationNote =
    "用户明确允许该精确批次用于商业模型训练和长期回归。";
  writeJson(userAuthorization, {
    schemaVersion: 1,
    ok: true,
    decision: "authorized_for_training_hard_negative_review",
    confirmedBy: "workspace-user",
    confirmationNote,
    authorizationEvidence: {
      kind: "codex-user-message",
      threadId: "019f4ca0-a894-7b63-8ec9-c286885a5a22",
      decisionId:
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/training-review-fixture",
      userMessageText: confirmationNote,
      userMessageSha256: createHash("sha256")
        .update(confirmationNote)
        .digest("hex"),
    },
    sourceRoot: images,
    scopeIncludesDescendants: false,
    authorizedUses: [
      "commercial-model-training",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
    roleConstraint:
      "authorization-does-not-assign-train-validation-or-holdout-role",
    authorizedRelativePaths: relativePaths,
    authorizedRelativePathsSha256: canonicalSha(relativePaths),
  });
  const createProtectedManifest = (
    role: "training" | "independent",
    seed: number,
  ) => {
    const decision =
      role === "training"
        ? "approved_hard_negative_manifest"
        : "approved_independent_hard_negative_holdout";
    const trainingUse = role === "training" ? "permitted" : "prohibited";
    const fileName =
      `hard_negative_${role}_20260723_${role === "training" ? "101" : "201"}_` +
      `protected_${role}_01.png`;
    const imagePath = path.join(root, "protected", role, fileName);
    writePatternTestPng(imagePath, seed, 768, 768);
    const items = [
      {
        fileName,
        sourceFileName: fileName,
        sourceGroup: `ai-hard-negative-${role}-2026-07-23:protected_${role}`,
        imageSha256: shaFile(imagePath),
        imagePath,
        width: 768,
        height: 768,
        imageFormat: "PNG",
        role: role === "training" ? "hard-negative" : "independent-holdout",
        originalResolutionVisualReview: true,
        trainingUse,
      },
    ];
    const manifestPath = path.join(root, `protected-${role}.json`);
    writeJson(manifestPath, {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision,
      trainingUse,
      itemsSha256: canonicalSha(items),
      items,
    });
    return manifestPath;
  };
  const protectedManifests = [
    createProtectedManifest("training", 5001),
    createProtectedManifest("independent", 5002),
  ];
  const protectedRegistry = path.join(root, "protected-registry.json");
  const registryEntries = protectedManifests.map((manifestPath, index) => ({
    path: path.resolve(manifestPath),
    sha256: shaFile(manifestPath),
    role: index === 0 ? "training" : "holdout",
  }));
  writeJson(protectedRegistry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: 2,
      trainingManifestCount: 1,
      holdoutManifestCount: 1,
    },
    entriesSha256: canonicalSha(registryEntries),
    entries: registryEntries,
  });
  const evidence = path.join(root, "training-authorization-evidence");
  const frozen = spawnSync(
    python,
    [
      recorder,
      "--source-root",
      images,
      "--user-authorization",
      userAuthorization,
      "--output-dir",
      evidence,
      "--protected-hard-negative-registry",
      protectedRegistry,
      "--batch-date",
      "20260724",
      "--sequence-start",
      "1",
      "--sequence-end",
      "4",
    ],
    { encoding: "utf8" },
  );
  assert.equal(frozen.status, 0, frozen.stderr);
  const authorization = path.join(evidence, "authorization-record-A-v1.json");
  const machineAudit = path.join(evidence, "machine-audit-v1.json");
  const entries = JSON.parse(readFileSync(authorization, "utf8")).entries;
  return {
    root,
    workspace,
    authorization,
    machineAudit,
    protectedRoles,
    protectedRegistry,
    protectedManifests,
    entries,
  };
}

function makeIndependentFixture() {
  const base = makeFixture();
  const images = path.join(base.root, "independent-images");
  for (let index = 0; index < 100; index++) {
    const sequence = 161 + index;
    const fileName =
      `hard_negative_independent_20260725_${String(sequence).padStart(3, "0")}_` +
      `new_holdout_family_${String((index % 99) + 1).padStart(2, "0")}.png`;
    writePatternTestPng(
      path.join(images, `shard-${index % 4}`, fileName),
      10001 + index,
      320,
      320,
    );
  }
  const userAuthorization = path.join(
    base.root,
    "independent-user-authorization.json",
  );
  const confirmationNote = "用户明确允许该精确批次用于独立发布测试。";
  writeJson(userAuthorization, {
    schemaVersion: 1,
    ok: true,
    decision: "authorized_for_independent_holdout_evaluation",
    confirmedBy: "workspace-user",
    confirmationNote,
    authorizationEvidence: {
      kind: "codex-user-message",
      threadId: "019f4ca0-a894-7b63-8ec9-c286885a5a22",
      decisionId:
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/independent-review-fixture",
      userMessageText: confirmationNote,
      userMessageSha256: createHash("sha256")
        .update(confirmationNote)
        .digest("hex"),
    },
    sourceRoot: images,
    scopeIncludesDescendants: false,
    authorizedUses: [
      "independent-release-test",
      "long-term-regression",
      "model-diagnostic-evaluation",
      "data-quality-review",
    ],
    qualityConstraint: "authorization-does-not-relax-quality-gates",
  });
  const { weights, thresholdReport } = createFormalThresholdEvidence(0.45);
  const frozen = spawnSync(
    python,
    [
      independentRecorder,
      "--source-root",
      images,
      "--user-authorization",
      userAuthorization,
      "--candidate-weights",
      weights,
      "--candidate-threshold-report",
      thresholdReport,
      "--protected-hard-negative-registry",
      base.protectedRegistry,
      "--batch-date",
      "20260725",
      "--sequence-start",
      "161",
      "--sequence-end",
      "260",
    ],
    { encoding: "utf8" },
  );
  assert.equal(frozen.status, 0, frozen.stderr);
  const evidence = path.join(images, "_independent_holdout_freeze_v1");
  return {
    ...base,
    workspace: path.join(base.root, "independent-workspace"),
    authorization: path.join(evidence, "authorization-record-A-v1.json"),
    machineAudit: path.join(evidence, "machine-audit-v1.json"),
    freezeManifest: path.join(evidence, "freeze-manifest-v1.json"),
  };
}

function buildFixture(item: ReturnType<typeof makeFixture>, extra: string[] = []) {
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
      ...extra,
    ],
    { encoding: "utf8" },
  );
}

function buildIndependentFixture(
  item: ReturnType<typeof makeIndependentFixture>,
  extra: string[] = [],
) {
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
      "--freeze-manifest",
      item.freezeManifest,
      "--output-dir",
      item.workspace,
      ...extra,
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

test("builds and finalizes hash-bound training hard-negative decisions", () => {
  const item = makeFixture();
  const built = buildFixture(item);
  assert.equal(built.status, 0, built.stderr);

  const workspaceFile = path.join(item.workspace, "review-workspace-v1.json");
  const workspace = JSON.parse(readFileSync(workspaceFile, "utf8"));
  assert.equal(workspace.summary.authorizedImages, 4);
  assert.equal(workspace.summary.reviewSheets, 1);
  assert.equal(workspace.policy.reviewSheetsUseSourcePixelsWithoutResampling, true);
  assert.equal(workspace.summary.protectedRoleIdentityMatches, 0);
  assert.equal(
    workspace.inputs.authorization.deepReplay.mode,
    "training-authorization-deep-replay",
  );
  assert.equal(
    workspace.inputs.authorization.deepReplay.authorizationRecordSha256,
    shaFile(item.authorization),
  );

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

test("rejects empty or wrong protected-role evidence", () => {
  const item = makeFixture();
  writeJson(item.protectedRoles.train, {});
  const built = buildFixture(item);
  assert.notEqual(built.status, 0);
  assert.match(
    built.stderr,
    /train truth index does not satisfy the formal role contract/,
  );
});

test("rejects authorization-record drift through training deep replay", () => {
  const item = makeFixture();
  const authorization = JSON.parse(readFileSync(item.authorization, "utf8"));
  authorization.inputs.machineAudit.sha256 = "0".repeat(64);
  writeJson(item.authorization, authorization);
  const built = buildFixture(item);
  assert.notEqual(built.status, 0);
  assert.match(
    built.stderr,
    /machine audit SHA-256 drift/,
  );
});

test("independent review deeply replays the registry bound by its freeze", () => {
  const item = makeIndependentFixture();
  const built = buildIndependentFixture(item);
  assert.equal(built.status, 0, built.stderr);
  const workspace = JSON.parse(
    readFileSync(path.join(item.workspace, "review-workspace-v1.json"), "utf8"),
  );
  const replay = workspace.inputs.authorization.deepReplay;
  const frozenRegistry = workspace.inputs.freezeManifest.protectedHardNegativeRegistry;
  assert.equal(replay.mode, "independent-freeze-deep-replay");
  assert.equal(replay.protectedHardNegativeRegistry.path, item.protectedRegistry);
  assert.equal(replay.protectedHardNegativeRegistry.sha256, shaFile(item.protectedRegistry));
  assert.deepEqual(frozenRegistry, replay.protectedHardNegativeRegistry);
  assert.equal(
    replay.protectedHardNegativeCrossCheck.decision,
    "pass_no_protected_hard_negative_overlap",
  );
  assert.equal(replay.protectedHardNegativeCrossCheck.candidateRecordCount, 100);
  assert.equal(replay.protectedHardNegativeCrossCheck.exactSha256Matches, 0);
  assert.equal(replay.protectedHardNegativeCrossCheck.sourceIdentityMatches, 0);
  assert.equal(
    replay.protectedHardNegativeCrossCheck.perceptualMatchesAtOrBelowThreshold,
    0,
  );
});

test("independent review rejects drift in the freeze-bound registry", () => {
  const item = makeIndependentFixture();
  writeFileSync(item.protectedRegistry, "{}\n");
  const built = buildIndependentFixture(item);
  assert.notEqual(built.status, 0);
  assert.match(built.stderr, /registry.*SHA-256.*drift|registry binding drift/is);
  assert.equal(existsSync(item.workspace), false);
});

test("overwrite keeps the old workspace on failure and atomically replaces it on success", () => {
  const item = makeFixture();
  const built = buildFixture(item);
  assert.equal(built.status, 0, built.stderr);
  const reportPath = path.join(item.workspace, "review-workspace-v1.json");
  const oldReportHash = shaFile(reportPath);
  const sentinel = path.join(item.workspace, "old-workspace-sentinel.txt");
  writeFileSync(sentinel, "old-workspace\n");

  const sourcePath = item.entries[0].sourcePath as string;
  const sourceBytes = readFileSync(sourcePath);
  writeFileSync(sourcePath, "drifted-before-overwrite\n");
  const failed = buildFixture(item, ["--overwrite"]);
  assert.notEqual(failed.status, 0);
  assert.equal(existsSync(sentinel), true);
  assert.equal(shaFile(reportPath), oldReportHash);

  writeFileSync(sourcePath, sourceBytes);
  const replaced = buildFixture(item, ["--overwrite"]);
  assert.equal(replaced.status, 0, replaced.stderr);
  assert.equal(existsSync(sentinel), false);
  assert.equal(existsSync(reportPath), true);
  assert.deepEqual(
    readdirSync(item.root).filter(
      (name) =>
        name.startsWith(".workspace.staging-") ||
        name.startsWith(".workspace.backup-"),
    ),
    [],
  );
});
