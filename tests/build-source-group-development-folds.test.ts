import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-source-group-development-folds.py");

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha(value: string | Buffer | unknown): string {
  const payload = typeof value === "string" || Buffer.isBuffer(value) ? value : canonical(value);
  return createHash("sha256").update(payload).digest("hex");
}

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "source-group-folds-"));
  const indexPath = path.join(root, "index.json");
  const materializationPath = path.join(root, "materialization.json");
  const auditPath = path.join(root, "audit.json");
  const yamlPath = path.join(root, "dataset.yaml");
  const outputPath = path.join(root, "folds.json");
  writeFileSync(yamlPath, "path: .\ntrain: images/train\nval: images/val\ntest: images/test\ntask: segment\n");

  const positiveGroups = Array.from({ length: 112 }, (_, index) => `positive-${String(index).padStart(3, "0")}`);
  const truths = Array.from({ length: 328 }, (_, index) => {
    const fileName = `positive-${String(index).padStart(3, "0")}.jpg`;
    const maskCount = index < 13 ? 7 : 6;
    return {
      fileName,
      imageSha256: sha(`positive-image-${index}`),
      sourceGroup: positiveGroups[index % positiveGroups.length],
      completeMaskCount: maskCount,
    };
  });
  assert.equal(truths.reduce((total, item) => total + item.completeMaskCount, 0), 1981);
  const index = {
    ok: true,
    decision: "approved_unique_training_truth_index",
    summary: { uniqueImageCount: 328, completeMaskCount: 1981, sourceGroupCount: 112 },
    canonicalTruthsSha256: sha(truths),
    canonicalTruths: truths,
    conflicts: [],
    errors: [],
  };
  writeFileSync(indexPath, JSON.stringify(index));

  const positiveRecords = truths.map((item) => ({
    fileName: item.fileName,
    role: "train-positive",
    split: "train",
    sourceGroup: item.sourceGroup,
    sourceGroups: [item.sourceGroup],
    imageSha256: item.imageSha256,
    maskCount: item.completeMaskCount,
  }));
  const negativeRecords = Array.from({ length: 160 }, (_, index) => {
    const sourceGroup = `negative-${String(index % 16).padStart(2, "0")}`;
    return {
      fileName: `negative-${String(index).padStart(3, "0")}.jpg`,
      role: "hard-negative",
      split: "train",
      sourceGroup,
      sourceGroups: [sourceGroup],
      imageSha256: sha(`negative-image-${index}`),
      maskCount: 0,
    };
  });
  const valRecords = Array.from({ length: 30 }, (_, index) => {
    const sourceGroup = `old-val-${String(index % 14).padStart(2, "0")}`;
    return {
      fileName: `val-${String(index).padStart(3, "0")}.jpg`,
      role: "val",
      split: "val",
      sourceGroup,
      sourceGroups: [sourceGroup],
      imageSha256: sha(`val-image-${index}`),
      maskCount: index < 24 ? 5 : 4,
    };
  });
  const records = [...positiveRecords, ...negativeRecords, ...valRecords];
  const materialization = {
    ok: true,
    status: "PASS",
    decision: "approved_canonical_candidate_dataset_materialization",
    candidateTrainingEligible: true,
    trainingUse: "permitted-for-candidate-training-only",
    outputDir: root,
    inputs: { trainingTruthIndex: { path: indexPath, sha256: sha(readFileSync(indexPath)) } },
    counts: {
      trainImages: 488,
      trainPositiveImages: 328,
      hardNegativeImages: 160,
      validationImages: 30,
      testImages: 0,
      positiveMasks: 1981,
      validationMasks: 144,
      emptyHardNegativeLabels: 160,
      orphanFiles: 0,
    },
    roles: {
      "train-positive": { images: 328, masks: 1981, sourceGroups: 112 },
      "hard-negative": { images: 160, masks: 0, sourceGroups: 16 },
      val: { images: 30, masks: 144, sourceGroups: 14 },
    },
    recordsSha256: sha(records),
    records,
    datasetFilesSha256: "a".repeat(64),
    allRolesSha256: "b".repeat(64),
    errors: [],
  };
  writeFileSync(materializationPath, JSON.stringify(materialization));
  const audit = {
    ok: true,
    status: "PASS",
    decision: "approved_candidate_training_input",
    candidateTrainingEligible: true,
    trainingUse: "approved-for-candidate-training-only",
    outputDir: root,
    inputs: {
      materializationReport: {
        path: materializationPath,
        sha256: sha(readFileSync(materializationPath)),
      },
    },
    counts: materialization.counts,
    roles: materialization.roles,
    datasetFilesSha256: materialization.datasetFilesSha256,
    allRolesSha256: materialization.allRolesSha256,
    errors: [],
  };
  writeFileSync(auditPath, JSON.stringify(audit));
  return { root, indexPath, materializationPath, auditPath, yamlPath, outputPath };
}

function build(value: ReturnType<typeof fixture>) {
  execFileSync("python", [
    script,
    "--combined-training-truth-index", value.indexPath,
    "--materialization-report", value.materializationPath,
    "--candidate-input-audit", value.auditPath,
    "--dataset-yaml", value.yamlPath,
    "--output", value.outputPath,
  ]);
  return JSON.parse(readFileSync(value.outputPath, "utf8"));
}

test("确定性构建五个sourceGroup互斥开发折并排除旧val", () => {
  const value = fixture();
  const report = build(value);
  assert.equal(report.ok, true);
  assert.equal(report.summary.trainPositiveImages, 328);
  assert.equal(report.summary.positiveMasks, 1981);
  assert.equal(report.summary.hardNegativeImages, 160);
  assert.equal(report.summary.sourceGroups, 128);
  assert.equal(report.summary.excludedValidationSourceGroups, 14);
  assert.equal(report.summary.testOrHoldoutRecords, 0);
  assert.equal(report.records.length, 488);
  assert.equal(report.records.some((item: { role: string }) => item.role === "val"), false);
  const groupFolds = new Map<string, number>();
  for (const item of report.records) {
    const prior = groupFolds.get(item.sourceGroup);
    if (prior !== undefined) assert.equal(item.fold, prior);
    groupFolds.set(item.sourceGroup, item.fold);
  }
  assert.equal(groupFolds.size, 128);
  for (const fold of report.folds) {
    assert.ok(fold.roles["train-positive"].images > 0);
    assert.ok(fold.roles["hard-negative"].images > 0);
  }
  execFileSync("python", [script, "--verify-plan", value.outputPath]);
});

test("同一冻结输入可确定性重建同一开发折", () => {
  const left = fixture();
  const rightOutput = path.join(left.root, "folds-second.json");
  const first = build(left);
  execFileSync("python", [
    script,
    "--combined-training-truth-index", left.indexPath,
    "--materialization-report", left.materializationPath,
    "--candidate-input-audit", left.auditPath,
    "--dataset-yaml", left.yamlPath,
    "--output", rightOutput,
  ]);
  const second = JSON.parse(readFileSync(rightOutput, "utf8"));
  assert.equal(second.contentSha256, first.contentSha256);
  assert.deepEqual(second.sourceGroupAssignments, first.sourceGroupAssignments);
  assert.deepEqual(second.records, first.records);
});

test("上游报告漂移后重放必须失败", () => {
  const value = fixture();
  build(value);
  const audit = JSON.parse(readFileSync(value.auditPath, "utf8"));
  audit.trainingUse = "drifted";
  writeFileSync(value.auditPath, JSON.stringify(audit));
  const result = spawnSync("python", [script, "--verify-plan", value.outputPath]);
  assert.notEqual(result.status, 0);
});

test("train与旧val来源组交叠必须拒绝", () => {
  const value = fixture();
  const materialization = JSON.parse(readFileSync(value.materializationPath, "utf8"));
  materialization.records.at(-1).sourceGroup = materialization.records[0].sourceGroup;
  materialization.records.at(-1).sourceGroups = [materialization.records[0].sourceGroup];
  materialization.recordsSha256 = sha(materialization.records);
  writeFileSync(value.materializationPath, JSON.stringify(materialization));
  const audit = JSON.parse(readFileSync(value.auditPath, "utf8"));
  audit.inputs.materializationReport.sha256 = sha(readFileSync(value.materializationPath));
  writeFileSync(value.auditPath, JSON.stringify(audit));
  const result = spawnSync("python", [
    script,
    "--combined-training-truth-index", value.indexPath,
    "--materialization-report", value.materializationPath,
    "--candidate-input-audit", value.auditPath,
    "--dataset-yaml", value.yamlPath,
    "--output", value.outputPath,
  ]);
  assert.notEqual(result.status, 0);
});
