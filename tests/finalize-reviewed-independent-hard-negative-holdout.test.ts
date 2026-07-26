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
import {
  createApprovedHardNegativeEvidence,
  createProtectedRoleEvidence,
  writePatternTestPng,
} from "./helpers/hard-negative-evidence.ts";
import { createFormalThresholdEvidence } from "./helpers/formal-threshold-evidence.ts";

const python = process.env.PYTHON ?? "python";
const recorder = path.resolve(
  "model/training/record-independent-hard-negative-authorization.py",
);
const workspaceBuilder = path.resolve(
  "model/training/build-independent-hard-negative-review-workspace.py",
);
const reviewFinalizer = path.resolve(
  "model/training/finalize-independent-hard-negative-review.py",
);
const holdoutFinalizer = path.resolve(
  "model/training/finalize-reviewed-independent-hard-negative-holdout.py",
);
const audit = path.resolve(
  "model/training/audit-hard-negative-watermark-shortcut.py",
);

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

function run(args: string[]) {
  return spawnSync(python, args, { encoding: "utf8" });
}

function runWithEnv(args: string[], environment: NodeJS.ProcessEnv) {
  return spawnSync(python, args, {
    encoding: "utf8",
    env: { ...process.env, ...environment },
  });
}

function makeFakeUltralytics(root: string) {
  const packageRoot = path.join(root, "fake-python", "ultralytics");
  mkdirSync(packageRoot, { recursive: true });
  writeFileSync(
    path.join(packageRoot, "__init__.py"),
    [
      "import os",
      "",
      "class _Tensor:",
      "    def __init__(self, values): self.values = values",
      "    def detach(self): return self",
      "    def cpu(self): return self",
      "    def tolist(self): return self.values",
      "",
      "class _Boxes:",
      "    def __init__(self, count):",
      "        self.count = count",
      "        self.conf = _Tensor([0.9] * count)",
      "    def __len__(self): return self.count",
      "",
      "class _Result:",
      "    def __init__(self, count): self.boxes = _Boxes(count)",
      "",
      "class YOLO:",
      "    def __init__(self, weights): self.weights = weights",
      "    def predict(self, source, **kwargs):",
      "        count = int(os.environ.get('FAKE_YOLO_DETECTIONS', '0'))",
      "        return [_Result(count) for _ in source]",
      "",
    ].join("\n"),
  );
  return path.dirname(packageRoot);
}

function completeAllPassDecisions(template: string, output: string) {
  const lines = readFileSync(template, "utf8")
    .replace(/^\uFEFF/, "")
    .trimEnd()
    .split(/\r?\n/);
  const completed = lines.map((line, index) => {
    if (index === 0) return line;
    const fields = line.split(",");
    assert.equal(fields.length, 9);
    fields[6] = "pass";
    fields[7] = "";
    fields[8] =
      "Original-resolution review confirms a clear complete non-human deployment hard negative.";
    return fields.join(",");
  });
  writeFileSync(output, `\uFEFF${completed.join("\n")}\n`);
}

function buildHoldoutFixture() {
  const root = mkdtempSync(path.join(tmpdir(), "reviewed-independent-holdout-"));
  const images = path.join(root, "images");
  const threshold = createFormalThresholdEvidence(0.45);
  const userAuthorization = path.join(root, "user-authorization.json");
  const confirmationNote =
    "用户明确允许该精确批次用于独立发布测试和长期回归。";
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
        "goal-thread/019f4ca0-a894-7b63-8ec9-c286885a5a22/holdout-test",
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
    trainingUse: "prohibited-for-independent-holdout",
  });

  const sources: Array<{
    fileName: string;
    sourceGroup: string;
    imageSha256: string;
    imagePath: string;
  }> = [];
  for (let index = 0; index < 100; index += 1) {
    const sequence = 161 + index;
    const variant = String((index % 99) + 1).padStart(2, "0");
    const family = `holdout_family_${String(index % 20).padStart(2, "0")}`;
    const fileName =
      `hard_negative_independent_20260724_${String(sequence).padStart(3, "0")}_` +
      `${family}_${variant}.png`;
    const imagePath = path.join(images, `shard-${index % 3}`, fileName);
    writePatternTestPng(imagePath, sequence);
    sources.push({
      fileName,
      sourceGroup: `fixture:${family}`,
      imageSha256: shaFile(imagePath),
      imagePath,
    });
  }

  const protectedEntries: Array<{
    path: string;
    sha256: string;
    role: "training" | "holdout";
  }> = [];
  for (const [role, sequence] of [
    ["training", 901],
    ["holdout", 902],
  ] as const) {
    const protectedImage = path.join(
      root,
      "protected",
      `hard_negative_independent_20260720_${sequence}_protected_${role}_01.png`,
    );
    writePatternTestPng(protectedImage, sequence);
    const protectedItems = [
      {
        fileName: path.basename(protectedImage),
        sourceFileName: path.basename(protectedImage),
        sourceGroup: `protected:${role}`,
        imageSha256: shaFile(protectedImage),
        imagePath: protectedImage,
        width: 320,
        height: 320,
        imageFormat: "PNG",
        role: role === "training" ? "hard-negative" : "independent-holdout",
        originalResolutionVisualReview: true,
        trainingUse: role === "training" ? "permitted" : "prohibited",
      },
    ];
    const protectedManifest = path.join(root, `protected-${role}.json`);
    writeJson(protectedManifest, {
      schemaVersion: 2,
      ok: true,
      status: "PASS",
      decision:
        role === "training"
          ? "approved_hard_negative_manifest"
          : "approved_independent_hard_negative_holdout",
      trainingUse: role === "training" ? "permitted" : "prohibited",
      itemsSha256: canonicalSha(protectedItems),
      items: protectedItems,
    });
    protectedEntries.push({
      path: path.resolve(protectedManifest),
      sha256: shaFile(protectedManifest),
      role,
    });
  }
  const protectedRegistry = path.join(root, "protected-registry.json");
  writeJson(protectedRegistry, {
    schemaVersion: 1,
    ok: true,
    decision: "protected_hard_negative_registry",
    summary: {
      manifestCount: 2,
      trainingManifestCount: 1,
      holdoutManifestCount: 1,
    },
    entriesSha256: canonicalSha(protectedEntries),
    entries: protectedEntries,
  });

  const frozen = run([
    recorder,
    "--source-root",
    images,
    "--user-authorization",
    userAuthorization,
    "--candidate-weights",
    threshold.weights,
    "--candidate-threshold-report",
    threshold.thresholdReport,
    "--protected-hard-negative-registry",
    protectedRegistry,
    "--batch-date",
    "20260724",
    "--sequence-start",
    "161",
    "--sequence-end",
    "260",
  ]);
  assert.equal(frozen.status, 0, frozen.stderr);
  const freezeRoot = path.join(images, "_independent_holdout_freeze_v1");
  const freezeManifest = path.join(freezeRoot, "freeze-manifest-v1.json");
  const authorization = path.join(freezeRoot, "authorization-record-A-v1.json");
  const machineAudit = path.join(freezeRoot, "machine-audit-v1.json");

  const protectedRoles = createProtectedRoleEvidence(root);
  const workspace = path.join(root, "workspace");
  const built = run([
    workspaceBuilder,
    "--authorization",
    authorization,
    "--machine-audit",
    machineAudit,
    "--freeze-manifest",
    freezeManifest,
    "--train-index",
    protectedRoles.train,
    "--val-index",
    protectedRoles.val,
    "--frozen-test-manifest",
    protectedRoles.frozenTest,
    "--output-dir",
    workspace,
  ]);
  assert.equal(built.status, 0, built.stderr);

  const completedDecisions = path.join(root, "review-decisions-completed.csv");
  completeAllPassDecisions(
    path.join(workspace, "review-decisions-v1.csv"),
    completedDecisions,
  );
  const reviewed = path.join(root, "reviewed");
  const finalizedReview = run([
    reviewFinalizer,
    "--workspace",
    path.join(workspace, "review-workspace-v1.json"),
    "--decisions",
    completedDecisions,
    "--output-dir",
    reviewed,
  ]);
  assert.equal(finalizedReview.status, 0, finalizedReview.stderr);
  const candidateManifest = path.join(
    reviewed,
    "hard-negative-candidate-manifest-v1.json",
  );
  const approvedHoldout = path.join(
    reviewed,
    "approved-independent-hard-negative-holdout-v2.json",
  );
  const finalizedHoldout = run([
    holdoutFinalizer,
    "--candidate-manifest",
    candidateManifest,
    "--output",
    approvedHoldout,
  ]);
  assert.equal(finalizedHoldout.status, 0, finalizedHoldout.stderr);
  return {
    root,
    images,
    sources,
    threshold,
    approvedHoldout,
    candidateManifest,
    freezeManifest,
  };
}

test(
  "finalizes and deeply replays 100 frozen reviewed holdout images without training permission",
  { timeout: 120_000 },
  () => {
    const item = buildHoldoutFixture();
    const report = JSON.parse(readFileSync(item.approvedHoldout, "utf8"));
    assert.equal(report.ok, true);
    assert.equal(
      report.decision,
      "approved_independent_hard_negative_holdout",
    );
    assert.equal(report.datasetRole, "independent-holdout");
    assert.equal(report.trainingUse, "prohibited");
    assert.equal(report.releaseEvaluationUse, "permitted");
    assert.equal(report.candidateScoreThreshold, 0.45);
    assert.equal(report.summary.reviewedIndependentHoldoutImages, 100);
    assert.ok(
      report.items.every(
        (entry: {
          trainingUse: string;
          datasetRole: string;
          releaseEvaluationUse: string;
        }) =>
          entry.trainingUse === "prohibited" &&
          entry.datasetRole === "independent-holdout" &&
          entry.releaseEvaluationUse === "permitted",
      ),
    );

    const verified = run([
      holdoutFinalizer,
      "--verify-report",
      item.approvedHoldout,
    ]);
    assert.equal(verified.status, 0, verified.stderr);
    assert.equal(
      JSON.parse(verified.stdout).reviewedIndependentHoldoutImages,
      100,
    );

    const relaxedAudit = run([
      audit,
      "--weights",
      item.threshold.weights,
      "--hard-negative-manifest",
      item.approvedHoldout,
      "--output",
      path.join(item.root, "relaxed-audit.json"),
      "--artifacts-dir",
      path.join(item.root, "relaxed-artifacts"),
      "--dataset-role",
      "independent-holdout",
      "--deployment-confidence",
      "0.45",
      "--max-false-positive-images",
      "1",
    ]);
    assert.notEqual(relaxedAudit.status, 0);
    assert.match(relaxedAudit.stderr, /fixes both error limits at zero/);

    const wrongImageSize = run([
      audit,
      "--weights",
      item.threshold.weights,
      "--hard-negative-manifest",
      item.approvedHoldout,
      "--output",
      path.join(item.root, "wrong-imgsz-audit.json"),
      "--artifacts-dir",
      path.join(item.root, "wrong-imgsz-artifacts"),
      "--dataset-role",
      "independent-holdout",
      "--deployment-confidence",
      "0.45",
      "--imgsz",
      "32",
    ]);
    assert.notEqual(wrongImageSize.status, 0);
    assert.match(wrongImageSize.stderr, /fixes deployment imgsz at 512/);

    const thresholdDrift = run([
      audit,
      "--weights",
      item.threshold.weights,
      "--hard-negative-manifest",
      item.approvedHoldout,
      "--output",
      path.join(item.root, "threshold-drift-audit.json"),
      "--artifacts-dir",
      path.join(item.root, "threshold-drift-artifacts"),
      "--dataset-role",
      "independent-holdout",
      "--deployment-confidence",
      "0.44",
    ]);
    assert.notEqual(thresholdDrift.status, 0);
    assert.match(thresholdDrift.stderr, /pre-frozen candidate threshold/);

    const wrongRole = run([
      audit,
      "--weights",
      item.threshold.weights,
      "--hard-negative-manifest",
      item.approvedHoldout,
      "--output",
      path.join(item.root, "wrong-role-audit.json"),
      "--artifacts-dir",
      path.join(item.root, "wrong-role-artifacts"),
      "--dataset-role",
      "training",
    ]);
    assert.notEqual(wrongRole.status, 0);
    assert.match(
      wrongRole.stderr,
      /not an approved schema v2 report|training audit requires/,
    );

    const fakePython = makeFakeUltralytics(item.root);
    const fakeEnvironment = {
      PYTHONPATH: [fakePython, process.env.PYTHONPATH]
        .filter(Boolean)
        .join(path.delimiter),
      FAKE_YOLO_DETECTIONS: "0",
    };
    const auditReport = path.join(item.root, "deep-audit.json");
    const auditArtifacts = path.join(item.root, "deep-audit-artifacts");
    const audited = runWithEnv(
      [
        audit,
        "--weights",
        item.threshold.weights,
        "--hard-negative-manifest",
        item.approvedHoldout,
        "--output",
        auditReport,
        "--artifacts-dir",
        auditArtifacts,
        "--dataset-role",
        "independent-holdout",
        "--deployment-confidence",
        "0.45",
      ],
      fakeEnvironment,
    );
    assert.equal(audited.status, 0, audited.stderr);

    const forgedCounts = runWithEnv(
      [audit, "--verify-report", auditReport],
      { ...fakeEnvironment, FAKE_YOLO_DETECTIONS: "1" },
    );
    assert.notEqual(forgedCounts.status, 0);
    assert.match(
      forgedCounts.stderr,
      /prediction counts differ from replay/,
    );

    const auditDocument = JSON.parse(readFileSync(auditReport, "utf8"));
    const originalVariant = auditDocument.records[0].variants.original.path as string;
    writePatternTestPng(originalVariant, 9999);
    auditDocument.records[0].variants.original.sha256 = shaFile(originalVariant);
    const canonical = (value: unknown): string => {
      if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
      if (value && typeof value === "object") {
        return `{${Object.entries(value as Record<string, unknown>)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, value]) => `${JSON.stringify(key)}:${canonical(value)}`)
          .join(",")}}`;
      }
      return JSON.stringify(value) ?? "null";
    };
    auditDocument.recordsSha256 = createHash("sha256")
      .update(canonical(auditDocument.records))
      .digest("hex");
    writeJson(auditReport, auditDocument);
    const replacedVariant = runWithEnv(
      [audit, "--verify-report", auditReport],
      fakeEnvironment,
    );
    assert.notEqual(replacedVariant.status, 0);
    assert.match(
      replacedVariant.stderr,
      /variants differ from deterministic rebuild/,
    );
  },
);

test(
  "independent audit rejects a training-approved hard-negative manifest",
  { timeout: 120_000 },
  () => {
    const root = mkdtempSync(path.join(tmpdir(), "holdout-role-rejection-"));
    const threshold = createFormalThresholdEvidence(0.45);
    const sources = Array.from({ length: 100 }, (_, index) => {
      const fileName = `training-negative-${String(index).padStart(3, "0")}.png`;
      const imagePath = path.join(root, "images", fileName);
      writePatternTestPng(imagePath, index + 1);
      return {
        fileName,
        sourceGroup: `training-group-${index}`,
        imageSha256: shaFile(imagePath),
        imagePath,
      };
    });
    const training = createApprovedHardNegativeEvidence(root, sources);
    const result = run([
      audit,
      "--weights",
      threshold.weights,
      "--hard-negative-manifest",
      training.approvedManifest,
      "--output",
      path.join(root, "audit.json"),
      "--artifacts-dir",
      path.join(root, "artifacts"),
      "--dataset-role",
      "independent-holdout",
      "--deployment-confidence",
      "0.45",
    ]);
    assert.notEqual(result.status, 0);
    assert.match(
      result.stderr,
      /not an approved schema v2 report|independent audit requires/,
    );
  },
);
