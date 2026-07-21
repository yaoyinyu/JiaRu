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
  createApprovedHardNegativeEvidence,
  writeTestPng,
} from "./helpers/hard-negative-evidence.ts";

const script = path.resolve(
  "model/training/materialize-canonical-candidate-training-dataset.py",
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
const shaCanonical = (value: unknown) =>
  createHash("sha256").update(canonical(value)).digest("hex");

function writeImage(file: string, index: number) {
  mkdirSync(path.dirname(file), { recursive: true });
  const pixel = Buffer.from([index & 255, (index >> 8) & 255, (index * 17) & 255]);
  writeFileSync(file, Buffer.concat([Buffer.from("P6\n16 16\n255\n"), ...Array(256).fill(pixel)]));
}

function files(root: string, excluded: string[] = []) {
  const excludedSet = new Set(excluded.map((item) => path.resolve(item)));
  const result: Array<{ path: string; sha256: string }> = [];
  const walk = (folder: string) => {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const target = path.join(folder, entry.name);
      if (entry.isDirectory()) walk(target);
      else if (!excludedSet.has(path.resolve(target))) {
        result.push({
          path: path.relative(root, target).split(path.sep).join("/"),
          sha256: shaFile(target),
        });
      }
    }
  };
  walk(root);
  return result.sort((left, right) => left.path.localeCompare(right.path));
}

type Fixture = ReturnType<typeof fixture>;

function fixture(hardCount = 100) {
  const root = mkdtempSync(path.join(tmpdir(), "candidate-dataset-"));
  const trainRoot = path.join(root, "train");
  const finalRoot = path.join(trainRoot, "final");
  mkdirSync(finalRoot, { recursive: true });
  const truths = Array.from({ length: 100 }, (_, index) => {
    const id = String(index + 1).padStart(3, "0");
    const fileName = `positive-${id}.jpg`;
    const image = path.join(trainRoot, "images", fileName);
    const annotation = path.join(trainRoot, "annotations", `${path.parse(fileName).name}.json`);
    writeImage(image, index);
    mkdirSync(path.dirname(annotation), { recursive: true });
    const sourceGroup = `train-group-${id}`;
    writeFileSync(
      annotation,
      `${JSON.stringify({
        image: { fileName, sourceGroup, width: 16, height: 16 },
        annotations: [
          {
            label: "nail_texture",
            polygon: [
              { x: 2, y: 2 },
              { x: 12, y: 2 },
              { x: 12, y: 12 },
              { x: 2, y: 12 },
            ],
          },
        ],
      })}\n`,
    );
    const imageSha256 = shaFile(image);
    const annotationSha256 = shaFile(annotation);
    const report = path.join(finalRoot, `training-truth-${index + 1}-final.json`);
    writeFileSync(
      report,
      `${JSON.stringify({
        ok: true,
        decision: "approved_as_training_truth_candidate_pending_dataset_materialization",
        inputs: {
          truthRole: "train",
          image,
          imageSha256,
          annotation,
          annotationSha256,
        },
        item: {
          fileName,
          sha256: imageSha256,
          sourceGroup,
          completeMaskCount: 1,
          trainingUse: "prohibited-until-materialization-audit",
        },
      })}\n`,
    );
    return {
      reportPath: report,
      reportName: path.basename(report),
      reportSha256: shaFile(report),
      sequence: index + 1,
      fileName,
      imageSha256,
      sourceGroup,
      completeMaskCount: 1,
      annotationPath: annotation,
      annotationSha256,
    };
  });
  const trainingTruthIndex = path.join(trainRoot, "training-truth-index.json");
  const trainingDocument = {
    schemaVersion: 1,
    ok: true,
    decision: "approved_unique_training_truth_index",
    inputs: { truthRole: "train", truthDir: finalRoot, reportPattern: "training-truth-*-final.json" },
    summary: {
      approvedReportCount: truths.length,
      rejectedReportCount: 0,
      uniqueImageCount: truths.length,
      completeMaskCount: truths.length,
      redundantReportCount: 0,
      redundantImageCount: 0,
      conflictingImageCount: 0,
    },
    canonicalTruths: truths,
    conflicts: [],
    errors: [],
  };
  writeFileSync(trainingTruthIndex, `${JSON.stringify(trainingDocument, null, 2)}\n`);

  const hardRoot = path.join(root, "hard");
  mkdirSync(path.join(hardRoot, "images"), { recursive: true });
  const hardItems = Array.from({ length: hardCount }, (_, index) => {
    const id = String(index + 1).padStart(3, "0");
    const fileName = `negative-${id}.png`;
    const imagePath = path.join(hardRoot, "images", fileName);
    writeTestPng(imagePath, 100 + index);
    return {
      fileName,
      sourceGroup: `hard-group-${id}`,
      imageSha256: shaFile(imagePath),
      imagePath,
      trainingUse: "permitted",
    };
  });
  const hardEvidence = createApprovedHardNegativeEvidence(hardRoot, hardItems);
  const hardNegativeManifest = hardEvidence.approvedManifest;
  const hardDocument = hardEvidence.approvedDocument;

  const valRoot = path.join(root, "validation");
  for (const split of ["train", "val", "test"]) {
    mkdirSync(path.join(valRoot, "images", split), { recursive: true });
    mkdirSync(path.join(valRoot, "labels", split), { recursive: true });
  }
  mkdirSync(path.join(valRoot, "annotations", "raw-json"), { recursive: true });
  mkdirSync(path.join(valRoot, "metadata"), { recursive: true });
  const valItems = Array.from({ length: 30 }, (_, index) => {
    const id = String(index + 1).padStart(3, "0");
    const fileName = `validation-${id}.jpg`;
    const image = path.join(valRoot, "images", "val", fileName);
    const label = path.join(valRoot, "labels", "val", `validation-${id}.txt`);
    const annotation = path.join(valRoot, "annotations", "raw-json", `validation-${id}.json`);
    writeImage(image, 200 + index);
    writeFileSync(label, "0 0.125 0.125 0.75 0.125 0.75 0.75 0.125 0.75\n");
    writeFileSync(annotation, `${JSON.stringify({ val: id })}\n`);
    return {
      fileName,
      sourceGroup: `val-group-${id}`,
      imageSha256: shaFile(image),
      annotationSha256: shaFile(annotation),
      labelSha256: shaFile(label),
      completeMaskCount: 1,
    };
  });
  const datasetYaml = path.join(valRoot, "dataset.yaml");
  writeFileSync(
    datasetYaml,
    "path: .\ntrain: images/train\nval: images/val\ntest: images/test\n\nnames:\n  0: nail_texture\n",
  );
  writeFileSync(
    path.join(valRoot, "metadata", "split.json"),
    `${JSON.stringify({ train: [], val: valItems.map((item) => item.fileName), test: [] }, null, 2)}\n`,
  );
  writeFileSync(path.join(valRoot, "metadata", "sources-isolation.csv"), "fixture\n");
  const truthIndex = path.join(root, "validation-truth-index.json");
  const roleIsolation = path.join(root, "validation-role-isolation.json");
  writeFileSync(truthIndex, "{\"ok\":true}\n");
  writeFileSync(roleIsolation, "{\"ok\":true}\n");
  const valMaterialization = path.join(valRoot, "metadata", "materialization-report.json");
  const datasetFiles = files(valRoot, [valMaterialization]);
  const valMaterializationDocument = {
    ok: true,
    decision: "canonical_validation_dataset_materialized_pending_role_isolation_audit",
    trainingUse: "prohibited",
    outputDir: valRoot,
    datasetFilesSha256: shaCanonical(datasetFiles),
    datasetFiles,
  };
  writeFileSync(valMaterialization, `${JSON.stringify(valMaterializationDocument, null, 2)}\n`);
  const validationFinalAudit = path.join(root, "validation-final-audit.json");
  const validationAuditDocument = {
    schemaVersion: 1,
    ok: true,
    status: "PASS",
    decision: "approved_as_calibration_truth",
    calibrationTruthEligible: true,
    trainingUse: "prohibited",
    inputs: {
      datasetYaml,
      datasetYamlSha256: shaFile(datasetYaml),
      datasetRoot: valRoot,
      truthIndex,
      truthIndexSha256: shaFile(truthIndex),
      materializationReport: valMaterialization,
      materializationReportSha256: shaFile(valMaterialization),
      roleIsolationReport: roleIsolation,
      roleIsolationReportSha256: shaFile(roleIsolation),
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
    invariants: {
      canonicalTruthCoverageComplete: true,
      allInputsHashBound: true,
      allImagesAnnotationsAndLabelsHashBound: true,
      polygonTopologyValid: true,
      pairwisePolygonOverlapZero: true,
      roleIsolationPassed: true,
      trainingUseProhibited: true,
    },
    itemsSha256: shaCanonical(valItems),
    items: valItems,
  };
  writeFileSync(validationFinalAudit, `${JSON.stringify(validationAuditDocument, null, 2)}\n`);

  const frozenRoot = path.join(root, "frozen");
  const frozenImage = path.join(frozenRoot, "images", "core", "frozen-a.jpg");
  writeImage(frozenImage, 230);
  const frozenItems = [
    {
      lane: "core",
      fileName: "frozen-a.jpg",
      sourceGroup: "frozen-region-a",
      parentSourceGroup: "frozen-parent-a",
      imageSha256: shaFile(frozenImage),
      trainingUse: "prohibited",
    },
  ];
  const frozenTestManifest = path.join(frozenRoot, "manifest.json");
  const frozenDocument = {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: frozenItems.length },
    itemsSha256: shaCanonical(frozenItems),
    items: frozenItems,
  };
  writeFileSync(frozenTestManifest, `${JSON.stringify(frozenDocument, null, 2)}\n`);

  return {
    root,
    trainingTruthIndex,
    trainingDocument,
    hardNegativeManifest,
    hardDocument,
    datasetYaml,
    validationFinalAudit,
    validationAuditDocument,
    roleIsolation,
    frozenTestManifest,
    frozenDocument,
  };
}

function saveHard(item: Fixture) {
  item.hardDocument.itemsSha256 = shaCanonical(item.hardDocument.items);
  writeFileSync(item.hardNegativeManifest, `${JSON.stringify(item.hardDocument, null, 2)}\n`);
}

function saveFrozen(item: Fixture) {
  item.frozenDocument.itemsSha256 = shaCanonical(item.frozenDocument.items);
  writeFileSync(item.frozenTestManifest, `${JSON.stringify(item.frozenDocument, null, 2)}\n`);
}

function run(item: Fixture, options: { output?: string; report?: string; frozen?: boolean } = {}) {
  const output = options.output ?? path.join(item.root, "candidate-output");
  const args = [
    script,
    "--training-truth-index",
    item.trainingTruthIndex,
    "--hard-negative-manifest",
    item.hardNegativeManifest,
    "--validation-dataset",
    item.datasetYaml,
    "--validation-final-audit",
    item.validationFinalAudit,
    "--output-dir",
    output,
  ];
  if (options.frozen !== false) args.push("--frozen-test-manifest", item.frozenTestManifest);
  if (options.report) args.push("--report-output", options.report);
  const result = spawnSync("python", args, { encoding: "utf8" });
  return { ...result, output };
}

test("materializes the exact 100 positive + 100 hard-negative + 30 val candidate dataset", () => {
  const item = fixture();
  const externalReport = path.join(item.root, "candidate-materialization-pass.json");
  const result = run(item, { report: externalReport });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(
    readFileSync(path.join(result.output, "metadata", "materialization-report.json"), "utf8"),
  );
  assert.equal(report.decision, "approved_canonical_candidate_dataset_materialization");
  assert.equal(report.status, "PASS");
  assert.deepEqual(report.counts, {
    trainImages: 200,
    trainPositiveImages: 100,
    hardNegativeImages: 100,
    validationImages: 30,
    testImages: 0,
    positiveMasks: 100,
    validationMasks: 30,
    emptyHardNegativeLabels: 100,
    orphanFiles: 0,
  });
  assert.equal(report.records.length, 230);
  assert.equal(report.datasetFilesSha256, shaCanonical(report.datasetFiles));
  assert.equal(report.recordsSha256, shaCanonical(report.records));
  assert.equal(report.overlaps.fileName.length, 0);
  assert.equal(report.invariants.frozenTestIsolationChecked, true);
  assert.equal(readFileSync(path.join(result.output, "labels", "train", "negative-001.txt"), "utf8"), "");
  assert.equal(readdirSync(path.join(result.output, "images", "test")).length, 0);
  assert.equal(JSON.parse(readFileSync(externalReport, "utf8")).recordsSha256, report.recordsSha256);
  const currentFiles = files(result.output, [path.join(result.output, "metadata", "materialization-report.json")]);
  assert.deepEqual(currentFiles, report.datasetFiles);
});

test("HOLDs 99 hard negatives before creating the dataset and writes only external evidence", () => {
  const item = fixture(99);
  const reportOutput = path.join(item.root, "hold.json");
  const result = run(item, { report: reportOutput });
  assert.notEqual(result.status, 0);
  assert.equal(existsSync(result.output), false);
  const hold = JSON.parse(readFileSync(reportOutput, "utf8"));
  assert.equal(hold.status, "HOLD");
  assert.equal(hold.candidateTrainingEligible, false);
  assert.deepEqual(hold.observedCounts, {
    trainPositiveImages: 100,
    hardNegativeImages: 99,
    validationImages: 30,
  });
  assert.deepEqual(hold.requiredCounts, {
    trainPositiveImages: 100,
    hardNegativeImages: 100,
    validationImages: 30,
  });
  assert.equal(
    hold.inputs.hardNegativeManifest.sha256,
    shaFile(item.hardNegativeManifest),
  );
  assert.match(hold.errors.join("\n"), /only 99 images.*at least 100/);
});

test("rejects formal-manifest drift and role identity overlap before output", async (t) => {
  await t.test("hard-negative image drift", () => {
    const item = fixture();
    writeFileSync(item.hardDocument.items[0].imagePath, "changed");
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(result.output), false);
    assert.match(result.stdout, /hard-negative image hash drift/);
  });
  await t.test("hard-negative source group overlaps train", () => {
    const item = fixture();
    item.hardDocument.items[0].sourceGroup = item.trainingDocument.canonicalTruths[0].sourceGroup;
    saveHard(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(result.output), false);
    assert.match(result.stdout, /cross-role sourceGroup overlap/);
  });
  await t.test("frozen test overlaps validation", () => {
    const item = fixture();
    item.frozenDocument.items[0].parentSourceGroup =
      item.validationAuditDocument.items[0].sourceGroup;
    saveFrozen(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(result.output), false);
    assert.match(result.stdout, /cross-role sourceGroup overlap/);
  });
});

test("rejects validation evidence drift and output/report path hazards", async (t) => {
  await t.test("hash-bound validation role-isolation evidence drift", () => {
    const item = fixture();
    writeFileSync(item.roleIsolation, "{\"ok\":false}\n");
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(result.output), false);
    assert.match(result.stdout, /validation audit input roleIsolationReport SHA-256 drift/);
  });
  await t.test("existing output is preserved", () => {
    const item = fixture();
    const output = path.join(item.root, "existing-output");
    mkdirSync(output);
    writeFileSync(path.join(output, "sentinel.txt"), "preserve");
    const result = run(item, { output });
    assert.notEqual(result.status, 0);
    assert.equal(readFileSync(path.join(output, "sentinel.txt"), "utf8"), "preserve");
  });
  await t.test("report cannot overwrite an input", () => {
    const item = fixture();
    const original = readFileSync(item.trainingTruthIndex);
    const result = run(item, { report: item.trainingTruthIndex });
    assert.notEqual(result.status, 0);
    assert.deepEqual(readFileSync(item.trainingTruthIndex), original);
    assert.equal(existsSync(result.output), false);
    assert.match(result.stdout, /report-output must not overwrite any input/);
  });
  await t.test("report cannot be inside the dataset output", () => {
    const item = fixture();
    const output = path.join(item.root, "candidate-output");
    const result = run(item, {
      output,
      report: path.join(output, "metadata", "hold.json"),
    });
    assert.notEqual(result.status, 0);
    assert.equal(existsSync(output), false);
    assert.match(result.stdout, /report-output must not be located inside/);
  });
});

test("formal quantity CLI flags cannot weaken the documented gates", () => {
  const item = fixture(1);
  const output = path.join(item.root, "candidate-output");
  const result = spawnSync(
    "python",
    [
      script,
      "--training-truth-index",
      item.trainingTruthIndex,
      "--hard-negative-manifest",
      item.hardNegativeManifest,
      "--validation-dataset",
      item.datasetYaml,
      "--validation-final-audit",
      item.validationFinalAudit,
      "--output-dir",
      output,
      "--minimum-hard-negative-images",
      "1",
    ],
    { encoding: "utf8" },
  );
  assert.notEqual(result.status, 0);
  assert.equal(existsSync(output), false);
  assert.match(result.stderr, /cannot weaken the formal 100-image gate/);
});
