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

const script = path.resolve("model/training/audit-validation-role-isolation.py");
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

type Fixture = ReturnType<typeof fixture>;

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "val-role-isolation-"));
  const valRoot = path.join(root, "val-dataset");
  mkdirSync(path.join(valRoot, "images", "val"), { recursive: true });
  const valRecords = Array.from({ length: 30 }, (_, index) => {
    const id = String(index + 1).padStart(3, "0");
    const fileName = `val-${id}.jpg`;
    const image = path.join(valRoot, "images", "val", fileName);
    writeFileSync(image, `validation-image-${id}`);
    const imageSha256 = shaFile(image);
    return {
      fileName,
      sourceGroup: `val-group-${id}`,
      sourceImageSha256: imageSha256,
      materializedRawImageSha256: imageSha256,
      materializedValidationImageSha256: imageSha256,
    };
  });
  const datasetFiles = valRecords.map((record) => ({
    path: `images/val/${record.fileName}`,
    sha256: record.sourceImageSha256,
  }));
  const valReport = path.join(root, "val-materialization.json");
  const valDocument = {
    ok: true,
    decision:
      "canonical_validation_dataset_materialized_pending_role_isolation_audit",
    trainingUse: "prohibited",
    validationUse: "prohibited-until-role-isolation-audit",
    outputDir: valRoot,
    counts: {
      validationImages: 30,
      orphanFiles: 0,
      trainImages: 0,
      testImages: 0,
    },
    invariants: {
      canonicalTruthsAreSoleAllowList: true,
      fixedValidationOnlySplit: true,
      noOrphans: true,
    },
    recordsSha256: shaCanonical(valRecords),
    datasetFilesSha256: shaCanonical(datasetFiles),
    datasetFiles,
    records: valRecords,
  };
  writeFileSync(valReport, `${JSON.stringify(valDocument, null, 2)}\n`);

  const trainRoot = path.join(root, "train");
  mkdirSync(trainRoot);
  const trainTruths = ["a", "b"].map((id, index) => {
    const fileName = `train-${id}.jpg`;
    const image = path.join(trainRoot, fileName);
    writeFileSync(image, `train-image-${id}`);
    const imageSha256 = shaFile(image);
    const report = path.join(trainRoot, `training-truth-${index + 1}-final.json`);
    writeFileSync(
      report,
      `${JSON.stringify({
        ok: true,
        decision:
          "approved_as_training_truth_candidate_pending_dataset_materialization",
        inputs: { truthRole: "train", image, imageSha256 },
        item: {
          fileName,
          sha256: imageSha256,
          sourceGroup: `train-group-${id}`,
        },
      })}\n`,
    );
    return {
      fileName,
      imageSha256,
      sourceGroup: `train-group-${id}`,
      reportPath: report,
      reportSha256: shaFile(report),
    };
  });
  const trainIndex = path.join(root, "training-truth-index.json");
  const trainDocument = {
    ok: true,
    decision: "approved_unique_training_truth_index",
    inputs: { truthRole: "train" },
    summary: { uniqueImageCount: trainTruths.length },
    canonicalTruths: trainTruths,
    conflicts: [],
    errors: [],
  };
  writeFileSync(trainIndex, `${JSON.stringify(trainDocument, null, 2)}\n`);

  const frozenRoot = path.join(root, "frozen");
  mkdirSync(path.join(frozenRoot, "images", "core"), { recursive: true });
  const frozenItems = ["a", "b"].map((id) => {
    const fileName = `test-${id}.jpg`;
    const image = path.join(frozenRoot, "images", "core", fileName);
    writeFileSync(image, `frozen-image-${id}`);
    return {
      lane: "core",
      fileName,
      sourceGroup: `test-region-${id}`,
      parentSourceGroup: `test-parent-${id}`,
      imageSha256: shaFile(image),
      trainingUse: "prohibited",
    };
  });
  const frozenManifest = path.join(frozenRoot, "manifest.json");
  const frozenDocument = {
    decision: "frozen_reviewed_candidate_not_release_ready",
    trainingUse: "prohibited",
    counts: { images: frozenItems.length },
    itemsSha256: shaCanonical(frozenItems),
    items: frozenItems,
  };
  writeFileSync(frozenManifest, `${JSON.stringify(frozenDocument, null, 2)}\n`);

  const hardRoot = path.join(root, "hard-negatives");
  mkdirSync(hardRoot);
  const hardImage = path.join(hardRoot, "negative-a.jpg");
  writeFileSync(hardImage, "negative-image-a");
  const hardItems = [
    {
      fileName: "negative-a.jpg",
      sourceGroup: "negative-group-a",
      imageSha256: shaFile(hardImage),
      imagePath: hardImage,
    },
  ];
  const hardManifest = path.join(hardRoot, "manifest.json");
  const hardDocument = {
    ok: true,
    decision: "approved_hard_negative_manifest",
    trainingUse: "permitted",
    itemsSha256: shaCanonical(hardItems),
    items: hardItems,
  };
  writeFileSync(hardManifest, `${JSON.stringify(hardDocument, null, 2)}\n`);

  return {
    root,
    valReport,
    valDocument,
    trainIndex,
    trainDocument,
    frozenManifest,
    frozenDocument,
    hardManifest,
    hardDocument,
  };
}

function save(item: Fixture) {
  item.valDocument.recordsSha256 = shaCanonical(item.valDocument.records);
  item.valDocument.datasetFilesSha256 = shaCanonical(
    item.valDocument.datasetFiles,
  );
  writeFileSync(item.valReport, `${JSON.stringify(item.valDocument, null, 2)}\n`);
  writeFileSync(
    item.trainIndex,
    `${JSON.stringify(item.trainDocument, null, 2)}\n`,
  );
  item.frozenDocument.itemsSha256 = shaCanonical(item.frozenDocument.items);
  writeFileSync(
    item.frozenManifest,
    `${JSON.stringify(item.frozenDocument, null, 2)}\n`,
  );
  item.hardDocument.itemsSha256 = shaCanonical(item.hardDocument.items);
  writeFileSync(
    item.hardManifest,
    `${JSON.stringify(item.hardDocument, null, 2)}\n`,
  );
}

function run(item: Fixture, withHardNegatives = true) {
  const output = path.join(item.root, "isolation-report.json");
  const args = [
    script,
    "--val-materialization-report",
    item.valReport,
    "--train-truth-index",
    item.trainIndex,
    "--frozen-test-manifest",
    item.frozenManifest,
    "--output",
    output,
  ];
  if (withHardNegatives) {
    args.push("--hard-negative-manifest", item.hardManifest);
  }
  const result = spawnSync("python", args, { encoding: "utf8" });
  return {
    ...result,
    output,
    report: JSON.parse(readFileSync(output, "utf8")),
  };
}

test("approves deterministic hash-bound isolation across all four roles", () => {
  const item = fixture();
  const first = run(item);
  assert.equal(first.status, 0, first.stderr || first.stdout);
  assert.equal(first.report.status, "PASS");
  assert.equal(first.report.decision, "approved_validation_role_isolation");
  assert.deepEqual(first.report.overlaps, {
    fileName: [],
    imageSha256: [],
    sourceGroup: [],
  });
  assert.equal(first.report.roles.val.images, 30);
  assert.equal(first.report.roles["hard-negative"].images, 1);
  for (const input of Object.values(first.report.inputs) as Array<{
    sha256: string;
  }>) {
    assert.match(input.sha256, /^[a-f0-9]{64}$/);
  }
  const second = run(item);
  assert.equal(second.status, 0, second.stderr || second.stdout);
  assert.equal(second.report.allRolesSha256, first.report.allRolesSha256);
});

test("places cross-role fileName, image hash, or source group overlap on HOLD", async (t) => {
  await t.test("fileName", () => {
    const item = fixture();
    item.frozenDocument.items[0].fileName =
      item.valDocument.records[0].fileName;
    const oldImage = path.join(
      path.dirname(item.frozenManifest),
      "images",
      "core",
      "test-a.jpg",
    );
    const renamedImage = path.join(
      path.dirname(item.frozenManifest),
      "images",
      "core",
      item.frozenDocument.items[0].fileName,
    );
    writeFileSync(renamedImage, readFileSync(oldImage));
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(result.report.status, "HOLD");
    assert.equal(result.report.overlaps.fileName.length, 1);
  });
  await t.test("image SHA-256", () => {
    const item = fixture();
    const val = item.valDocument.records[0];
    const frozen = item.frozenDocument.items[0];
    const frozenImage = path.join(
      path.dirname(item.frozenManifest),
      "images",
      "core",
      frozen.fileName,
    );
    const valImage = path.join(
      item.valDocument.outputDir,
      "images",
      "val",
      val.fileName,
    );
    writeFileSync(frozenImage, readFileSync(valImage));
    frozen.imageSha256 = val.sourceImageSha256;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(result.report.overlaps.imageSha256.length, 1);
  });
  await t.test("sourceGroup including frozen parent group", () => {
    const item = fixture();
    item.frozenDocument.items[0].parentSourceGroup =
      item.trainDocument.canonicalTruths[0].sourceGroup;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(result.report.overlaps.sourceGroup.length, 1);
  });
});

test("rejects missing fields, duplicate identities, weak val evidence, and hash drift", async (t) => {
  await t.test("missing source group", () => {
    const item = fixture();
    delete item.hardDocument.items[0].sourceGroup;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /sourceGroup is missing/);
    assert.equal(
      result.report.inputs.hardNegativeManifest.sha256,
      shaFile(item.hardManifest),
    );
  });
  await t.test("duplicate identity within a role", () => {
    const item = fixture();
    item.valDocument.records[1].fileName =
      item.valDocument.records[0].fileName;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /duplicate fileName/);
  });
  await t.test("validation below 30", () => {
    const item = fixture();
    item.valDocument.counts.validationImages = 29;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /only 29 images/);
  });
  await t.test("validation orphan", () => {
    const item = fixture();
    item.valDocument.counts.orphanFiles = 1;
    save(item);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /orphan files/);
  });
  await t.test("val dataset file drift", () => {
    const item = fixture();
    const target = path.join(
      item.valDocument.outputDir,
      item.valDocument.datasetFiles[0].path,
    );
    writeFileSync(target, "changed");
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /dataset file hash drift/);
  });
  await t.test("train final report drift", () => {
    const item = fixture();
    const report = item.trainDocument.canonicalTruths[0].reportPath;
    writeFileSync(report, `${readFileSync(report, "utf8")} `);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /final report hash drift/);
  });
  await t.test("frozen manifest aggregate drift", () => {
    const item = fixture();
    item.frozenDocument.items[0].sourceGroup = "changed-without-rehash";
    writeFileSync(
      item.frozenManifest,
      `${JSON.stringify(item.frozenDocument, null, 2)}\n`,
    );
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /items SHA-256 drift/);
  });
});
