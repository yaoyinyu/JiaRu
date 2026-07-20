import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/audit-candidate-training-input.py");
const polygon = "0 0.1 0.1 0.4 0.1 0.4 0.4 0.1 0.4\n";
const sha = (file: string) =>
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
const shaCanonical = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");
const writeJson = (file: string, value: unknown) =>
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);

type Json = Record<string, any>;
type Fixture = ReturnType<typeof fixture>;

function datasetYaml(root: string, version: string) {
  const file = path.join(root, "dataset.yaml");
  writeFileSync(
    file,
    [
      "path: .",
      "train: images/train",
      "val: images/val",
      "test: images/test",
      "",
      "names:",
      "  0: nail_texture",
      "",
      "task: segment",
      "class_count: 1",
      "image_size: 640",
      "",
      "metadata:",
      `  dataset_version: ${version}`,
      "",
    ].join("\n"),
  );
  return file;
}

function filesBelow(root: string, excluded: Set<string>) {
  const result: Array<{ path: string; sha256: string }> = [];
  const visit = (directory: string) => {
    for (const name of readdirSync(directory)) {
      const item = path.join(directory, name);
      if (statSync(item).isDirectory()) visit(item);
      else if (!excluded.has(path.resolve(item))) {
        result.push({
          path: path.relative(root, item).split(path.sep).join("/"),
          sha256: sha(item),
        });
      }
    }
  };
  visit(root);
  return result.sort((left, right) => left.path.localeCompare(right.path));
}

function identity(record: Json) {
  return {
    fileName: record.fileName,
    imageSha256: record.imageSha256,
    sourceGroups: [...record.sourceGroups].sort(),
  };
}

function roleEvidence(records: Json[]) {
  const roles: Json = {};
  const roleIdentities: Json = {};
  for (const role of ["train-positive", "hard-negative", "val"]) {
    const selected = records.filter((item) => item.role === role);
    const identities = selected
      .map(identity)
      .sort((left, right) =>
        `${left.fileName}\0${left.imageSha256}\0${left.sourceGroups.join("\0")}`.localeCompare(
          `${right.fileName}\0${right.imageSha256}\0${right.sourceGroups.join("\0")}`,
        ),
      );
    roleIdentities[role] = identities;
    roles[role] = {
      images: selected.length,
      masks: selected.reduce((sum, item) => sum + item.maskCount, 0),
      sourceGroups: new Set(selected.flatMap((item) => item.sourceGroups)).size,
      identitiesSha256: shaCanonical(identities),
    };
  }
  return { roles, allRolesSha256: shaCanonical(roleIdentities) };
}

function fixture(hardNegativeCount = 100) {
  const root = mkdtempSync(path.join(tmpdir(), "candidate-input-audit-"));
  const upstream = path.join(root, "upstream");
  const trainRoot = path.join(upstream, "train");
  const hardRoot = path.join(upstream, "hard");
  const valRoot = path.join(upstream, "val");
  const frozenRoot = path.join(upstream, "frozen");
  for (const directory of [trainRoot, hardRoot, valRoot, frozenRoot]) {
    mkdirSync(directory, { recursive: true });
  }

  const trainTruths: Json[] = [];
  const trainSources: Json[] = [];
  for (let index = 1; index <= 100; index++) {
    const id = String(index).padStart(3, "0");
    const fileName = `positive-${id}.jpg`;
    const image = path.join(trainRoot, fileName);
    const label = path.join(trainRoot, `positive-${id}.txt`);
    writeFileSync(image, `approved-positive-image-${id}`);
    writeFileSync(label, polygon);
    const report = path.join(trainRoot, `training-truth-${id}-final.json`);
    writeJson(report, {
      ok: true,
      decision: "approved_as_training_truth_candidate_pending_dataset_materialization",
      inputs: { truthRole: "train", image, imageSha256: sha(image) },
      item: {
        fileName,
        sha256: sha(image),
        sourceGroup: `positive-group-${id}`,
      },
    });
    trainTruths.push({
      fileName,
      imageSha256: sha(image),
      sourceGroup: `positive-group-${id}`,
      reportPath: report,
      reportSha256: sha(report),
    });
    trainSources.push({ fileName, image, label });
  }
  const trainIndex = path.join(trainRoot, "training-truth-index.json");
  writeJson(trainIndex, {
    ok: true,
    decision: "approved_unique_training_truth_index",
    inputs: { truthRole: "train" },
    summary: { uniqueImageCount: trainTruths.length },
    canonicalTruths: trainTruths,
    conflicts: [],
    errors: [],
  });

  const hardItems: Json[] = [];
  for (let index = 1; index <= hardNegativeCount; index++) {
    const id = String(index).padStart(3, "0");
    const fileName = `negative-${id}.jpg`;
    const imagePath = path.join(hardRoot, fileName);
    writeFileSync(imagePath, `formal-hard-negative-image-${id}`);
    hardItems.push({
      fileName,
      sourceGroup: `hard-group-${id}`,
      imageSha256: sha(imagePath),
      imagePath,
    });
  }
  const hardManifest = path.join(hardRoot, "manifest.json");
  const hardDocument = {
    ok: true,
    decision: "approved_hard_negative_manifest",
    trainingUse: "permitted",
    itemsSha256: shaCanonical(hardItems),
    items: hardItems,
  };
  writeJson(hardManifest, hardDocument);

  mkdirSync(path.join(valRoot, "images", "val"), { recursive: true });
  mkdirSync(path.join(valRoot, "labels", "val"), { recursive: true });
  mkdirSync(path.join(valRoot, "images", "train"), { recursive: true });
  mkdirSync(path.join(valRoot, "images", "test"), { recursive: true });
  mkdirSync(path.join(valRoot, "labels", "train"), { recursive: true });
  mkdirSync(path.join(valRoot, "labels", "test"), { recursive: true });
  const validationDataset = datasetYaml(valRoot, "canonical-validation-dataset/v1");
  const valItems: Json[] = [];
  const valLabelHashes: Json = {};
  for (let index = 1; index <= 30; index++) {
    const id = String(index).padStart(3, "0");
    const fileName = `validation-${id}.jpg`;
    const image = path.join(valRoot, "images", "val", fileName);
    const label = path.join(valRoot, "labels", "val", `validation-${id}.txt`);
    writeFileSync(image, `approved-validation-image-${id}`);
    writeFileSync(label, polygon);
    valLabelHashes[path.basename(label)] = sha(label);
    valItems.push({
      fileName,
      sourceGroup: `validation-group-${id}`,
      imageSha256: sha(image),
      annotationSha256: sha(label),
      labelSha256: sha(label),
      completeMaskCount: 1,
    });
  }
  const validationAudit = path.join(valRoot, "validation-final-audit.json");
  writeJson(validationAudit, {
    schemaVersion: 1,
    ok: true,
    status: "PASS",
    decision: "approved_as_calibration_truth",
    calibrationTruthEligible: true,
    trainingUse: "prohibited",
    inputs: {
      datasetYaml: validationDataset,
      datasetYamlSha256: sha(validationDataset),
      datasetRoot: valRoot,
      split: "val",
    },
    counts: {
      expectedImages: 30,
      reviewedImages: 30,
      pass: 30,
      rework: 0,
      exclude: 0,
      validationMasks: 30,
      invalidPolygons: 0,
      overlapPairs: 0,
      orphanFiles: 0,
    },
    labelSha256: valLabelHashes,
    itemsSha256: shaCanonical(valItems),
    items: valItems,
    errors: [],
  });

  mkdirSync(path.join(frozenRoot, "images", "core"), { recursive: true });
  const frozenImage = path.join(frozenRoot, "images", "core", "frozen-a.jpg");
  writeFileSync(frozenImage, "frozen-test-image-a");
  const frozenItems = [
    {
      lane: "core",
      fileName: "frozen-a.jpg",
      sourceGroup: "frozen-group-a",
      parentSourceGroup: "frozen-parent-a",
      imageSha256: sha(frozenImage),
      trainingUse: "prohibited",
    },
  ];
  const frozenManifest = path.join(frozenRoot, "manifest.json");
  writeJson(frozenManifest, {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: frozenItems.length },
    itemsSha256: shaCanonical(frozenItems),
    items: frozenItems,
  });

  const datasetRoot = path.join(root, "candidate-dataset");
  for (const split of ["train", "val", "test"]) {
    mkdirSync(path.join(datasetRoot, "images", split), { recursive: true });
    mkdirSync(path.join(datasetRoot, "labels", split), { recursive: true });
  }
  mkdirSync(path.join(datasetRoot, "metadata"), { recursive: true });
  const candidateDataset = datasetYaml(datasetRoot, "canonical-candidate-training/v1");
  const records: Json[] = [];
  for (let index = 0; index < trainSources.length; index++) {
    const source = trainSources[index];
    const truth = trainTruths[index];
    const image = path.join(datasetRoot, "images", "train", source.fileName);
    const label = path.join(
      datasetRoot,
      "labels",
      "train",
      `${path.parse(source.fileName).name}.txt`,
    );
    writeFileSync(image, readFileSync(source.image));
    writeFileSync(label, readFileSync(source.label));
    records.push({
      fileName: source.fileName,
      role: "train-positive",
      split: "train",
      sourceGroup: truth.sourceGroup,
      sourceGroups: [truth.sourceGroup],
      imageSha256: sha(source.image),
      maskCount: 1,
      sourceImage: source.image,
      sourceImageSha256: sha(source.image),
      sourceLabel: source.label,
      sourceLabelSha256: sha(source.label),
      materializedImageSha256: sha(image),
      materializedLabelSha256: sha(label),
    });
  }
  for (const item of hardItems) {
    const image = path.join(datasetRoot, "images", "train", item.fileName);
    const label = path.join(
      datasetRoot,
      "labels",
      "train",
      `${path.parse(item.fileName).name}.txt`,
    );
    writeFileSync(image, readFileSync(item.imagePath));
    writeFileSync(label, "");
    records.push({
      fileName: item.fileName,
      role: "hard-negative",
      split: "train",
      sourceGroup: item.sourceGroup,
      sourceGroups: [item.sourceGroup],
      imageSha256: item.imageSha256,
      maskCount: 0,
      sourceImage: item.imagePath,
      sourceImageSha256: item.imageSha256,
      sourceLabel: null,
      sourceLabelSha256: null,
      materializedImageSha256: sha(image),
      materializedLabelSha256: sha(label),
    });
  }
  for (const item of valItems) {
    const sourceImage = path.join(valRoot, "images", "val", item.fileName);
    const sourceLabel = path.join(
      valRoot,
      "labels",
      "val",
      `${path.parse(item.fileName).name}.txt`,
    );
    const image = path.join(datasetRoot, "images", "val", item.fileName);
    const label = path.join(
      datasetRoot,
      "labels",
      "val",
      `${path.parse(item.fileName).name}.txt`,
    );
    writeFileSync(image, readFileSync(sourceImage));
    writeFileSync(label, readFileSync(sourceLabel));
    records.push({
      fileName: item.fileName,
      role: "val",
      split: "val",
      sourceGroup: item.sourceGroup,
      sourceGroups: [item.sourceGroup],
      imageSha256: item.imageSha256,
      maskCount: item.completeMaskCount,
      sourceImage,
      sourceImageSha256: item.imageSha256,
      sourceLabel,
      sourceLabelSha256: item.labelSha256,
      materializedImageSha256: sha(image),
      materializedLabelSha256: sha(label),
    });
  }
  records.sort((left, right) =>
    `${left.role}\0${left.fileName}`.localeCompare(`${right.role}\0${right.fileName}`),
  );
  const splitJson = path.join(datasetRoot, "metadata", "split.json");
  writeJson(splitJson, {
    train: records.filter((item) => item.split === "train").map((item) => item.fileName),
    val: records.filter((item) => item.split === "val").map((item) => item.fileName),
    test: [],
  });
  const sourcesCsv = path.join(datasetRoot, "metadata", "sources-isolation.csv");
  writeFileSync(
    sourcesCsv,
    [
      "fileName,role,split,sourceGroup,imageSha256",
      ...records.map((item) =>
        [
          item.fileName,
          item.role,
          item.split,
          item.sourceGroup,
          item.imageSha256,
        ].join(","),
      ),
    ].join("\n") + "\n",
  );
  const materializationReport = path.join(
    datasetRoot,
    "metadata",
    "materialization-report.json",
  );
  const { roles, allRolesSha256 } = roleEvidence(records);
  const report: Json = {
    schemaVersion: 1,
    ok: true,
    status: "PASS",
    decision: "approved_canonical_candidate_dataset_materialization",
    candidateTrainingEligible: true,
    trainingUse: "permitted-for-candidate-training-only",
    inputs: {
      trainingTruthIndex: { path: trainIndex, sha256: sha(trainIndex) },
      hardNegativeManifest: { path: hardManifest, sha256: sha(hardManifest) },
      validationDatasetYaml: {
        path: validationDataset,
        sha256: sha(validationDataset),
      },
      validationFinalAudit: {
        path: validationAudit,
        sha256: sha(validationAudit),
      },
      frozenTestManifest: { path: frozenManifest, sha256: sha(frozenManifest) },
    },
    outputDir: datasetRoot,
    datasetYaml: candidateDataset,
    counts: {
      trainImages: 100 + hardNegativeCount,
      trainPositiveImages: 100,
      hardNegativeImages: hardNegativeCount,
      validationImages: 30,
      testImages: 0,
      positiveMasks: 100,
      validationMasks: 30,
      emptyHardNegativeLabels: hardNegativeCount,
      orphanFiles: 0,
    },
    recordsSha256: shaCanonical(records),
    records,
    roles,
    overlaps: { fileName: [], imageSha256: [], sourceGroup: [] },
    allRolesSha256,
    artifacts: {
      datasetYaml: { path: candidateDataset, sha256: sha(candidateDataset) },
      splitJson: { path: splitJson, sha256: sha(splitJson) },
      sourcesIsolationCsv: { path: sourcesCsv, sha256: sha(sourcesCsv) },
    },
    datasetFiles: [],
    datasetFilesSha256: "",
    errors: [],
  };
  report.datasetFiles = filesBelow(
    datasetRoot,
    new Set([path.resolve(materializationReport)]),
  );
  report.datasetFilesSha256 = shaCanonical(report.datasetFiles);
  writeJson(materializationReport, report);
  return {
    root,
    datasetRoot,
    candidateDataset,
    materializationReport,
    report,
    trainIndex,
    hardManifest,
    hardDocument,
    validationAudit,
    frozenManifest,
    splitJson,
    sourcesCsv,
  };
}

function refresh(item: Fixture) {
  item.report.inputs.trainingTruthIndex.sha256 = sha(item.trainIndex);
  item.report.inputs.hardNegativeManifest.sha256 = sha(item.hardManifest);
  item.report.inputs.validationFinalAudit.sha256 = sha(item.validationAudit);
  item.report.inputs.frozenTestManifest.sha256 = sha(item.frozenManifest);
  item.report.artifacts.datasetYaml.sha256 = sha(item.candidateDataset);
  item.report.artifacts.splitJson.sha256 = sha(item.splitJson);
  item.report.artifacts.sourcesIsolationCsv.sha256 = sha(item.sourcesCsv);
  item.report.recordsSha256 = shaCanonical(item.report.records);
  const roleData = roleEvidence(item.report.records);
  item.report.roles = roleData.roles;
  item.report.allRolesSha256 = roleData.allRolesSha256;
  item.report.datasetFiles = filesBelow(
    item.datasetRoot,
    new Set([path.resolve(item.materializationReport)]),
  );
  item.report.datasetFilesSha256 = shaCanonical(item.report.datasetFiles);
  writeJson(item.materializationReport, item.report);
}

function run(
  item: Fixture,
  output = path.join(item.root, "candidate-input-audit.json"),
  extra: string[] = [],
) {
  const result = spawnSync(
    "python",
    [
      script,
      "--materialization-report",
      item.materializationReport,
      "--output",
      output,
      ...extra,
    ],
    { encoding: "utf8" },
  );
  return {
    ...result,
    output,
    report: existsSync(output)
      ? JSON.parse(readFileSync(output, "utf8"))
      : undefined,
  };
}

test("approves a complete hash-bound 100/100/30 candidate input", () => {
  const item = fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(result.report.status, "PASS");
  assert.equal(result.report.decision, "approved_candidate_training_input");
  assert.equal(result.report.validationBridgeEligible, true);
  assert.equal(result.report.candidateTrainingEligible, true);
  assert.deepEqual(result.report.counts, item.report.counts);
  assert.deepEqual(result.report.overlaps, {
    fileName: [],
    imageSha256: [],
    sourceGroup: [],
  });
});

test("does not allow CLI flags to lower the formal 100/100/30 gates", () => {
  const item = fixture(99);
  const result = run(item, undefined, [
    "--minimum-positive-images",
    "1",
    "--minimum-hard-negative-images",
    "1",
    "--minimum-validation-images",
    "1",
  ]);
  assert.equal(result.status, 1);
  assert.equal(result.report.status, "HOLD");
  assert.equal(result.report.validationBridgeEligible, true);
  assert.equal(result.report.candidateTrainingEligible, false);
  assert.match(result.report.errors[0], /below 100/);
});

test("rejects a forged PASS whose hard-negative label is non-empty", () => {
  const item = fixture();
  const record = item.report.records.find((entry: Json) => entry.role === "hard-negative");
  const label = path.join(
    item.datasetRoot,
    "labels",
    "train",
    `${path.parse(record.fileName).name}.txt`,
  );
  writeFileSync(label, polygon);
  record.materializedLabelSha256 = sha(label);
  refresh(item);
  const result = run(item);
  assert.equal(result.status, 1);
  assert.equal(result.report.status, "HOLD");
  assert.match(result.report.errors[0], /not byte-empty/);
});

test("rejects positive polygon overlap even after all report hashes are forged", () => {
  const item = fixture();
  const record = item.report.records.find((entry: Json) => entry.role === "train-positive");
  const sourceLabel = record.sourceLabel;
  const label = path.join(
    item.datasetRoot,
    "labels",
    "train",
    `${path.parse(record.fileName).name}.txt`,
  );
  writeFileSync(sourceLabel, polygon + polygon);
  writeFileSync(label, polygon + polygon);
  record.maskCount = 2;
  record.sourceLabelSha256 = sha(sourceLabel);
  record.materializedLabelSha256 = sha(label);
  item.report.counts.positiveMasks += 1;
  refresh(item);
  const result = run(item);
  assert.equal(result.status, 1);
  assert.match(result.report.errors[0], /overlap/);
});

test("rejects cross-role source-group leakage after independent recomputation", () => {
  const item = fixture();
  const hard = item.hardDocument.items[0];
  hard.sourceGroup = "validation-group-001";
  item.hardDocument.itemsSha256 = shaCanonical(item.hardDocument.items);
  writeJson(item.hardManifest, item.hardDocument);
  const record = item.report.records.find(
    (entry: Json) => entry.role === "hard-negative" && entry.fileName === hard.fileName,
  );
  record.sourceGroup = hard.sourceGroup;
  record.sourceGroups = [hard.sourceGroup];
  writeFileSync(
    item.sourcesCsv,
    [
      "fileName,role,split,sourceGroup,imageSha256",
      ...item.report.records.map((entry: Json) =>
        [
          entry.fileName,
          entry.role,
          entry.split,
          entry.sourceGroup,
          entry.imageSha256,
        ].join(","),
      ),
    ].join("\n") + "\n",
  );
  refresh(item);
  const result = run(item);
  assert.equal(result.status, 1);
  assert.match(result.report.errors[0], /not source-isolated/);
});

test("rejects path traversal in the materialized file allow-list", () => {
  const item = fixture();
  item.report.datasetFiles[0].path = "../outside.txt";
  item.report.datasetFilesSha256 = shaCanonical(item.report.datasetFiles);
  writeJson(item.materializationReport, item.report);
  const result = run(item);
  assert.equal(result.status, 1);
  assert.match(result.report.errors[0], /invalid relative path/);
});

test("detects an unlisted file as a write-after-audit orphan", () => {
  const item = fixture();
  writeFileSync(path.join(item.datasetRoot, "metadata", "late-orphan.txt"), "late");
  const result = run(item);
  assert.equal(result.status, 1);
  assert.match(result.report.errors[0], /orphan=.*late-orphan/);
});

test("refuses output overwrite and output inside the dataset without writing", () => {
  const item = fixture();
  const original = readFileSync(item.materializationReport);
  const overwrite = run(item, item.materializationReport);
  assert.equal(overwrite.status, 1);
  assert.deepEqual(readFileSync(item.materializationReport), original);

  const inside = path.join(item.datasetRoot, "metadata", "candidate-audit.json");
  const nested = run(item, inside);
  assert.equal(nested.status, 1);
  assert.equal(existsSync(inside), false);
});

test("deep replay rejects a stored PASS after dataset drift", () => {
  const item = fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const label = path.join(item.datasetRoot, "labels", "train", "positive-001.txt");
  writeFileSync(label, `${polygon}\n`);
  const replay = spawnSync(
    "python",
    [
      "-c",
      [
        "import importlib.util, pathlib, sys",
        `p=pathlib.Path(${JSON.stringify(script)})`,
        "sys.path.insert(0, str(p.parent))",
        "s=importlib.util.spec_from_file_location('candidate_input_audit', p)",
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)",
        `m.verify_approved_report(${JSON.stringify(result.output)}, ${JSON.stringify(item.candidateDataset)})`,
      ].join(";"),
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(replay.status, 0);
  assert.match(replay.stderr, /hash-drifted|differ/i);
});
