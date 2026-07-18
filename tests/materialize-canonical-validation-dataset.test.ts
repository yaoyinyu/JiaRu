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
import sharp from "sharp";

const script = path.resolve(
  "model/training/materialize-canonical-validation-dataset.py",
);
const sha = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

type Fixture = {
  root: string;
  indexPath: string;
  index: Record<string, any>;
};

async function fixture(): Promise<Fixture> {
  const root = path.join(
    mkdtempSync(path.join(tmpdir(), "canonical-val-")),
    "中文验证工作区",
  );
  const images = path.join(root, "sources", "images");
  const annotations = path.join(root, "sources", "annotations");
  const reports = path.join(root, "truth-final");
  mkdirSync(images, { recursive: true });
  mkdirSync(annotations, { recursive: true });
  mkdirSync(reports, { recursive: true });
  const basePng = await sharp({
    create: {
      width: 20,
      height: 20,
      channels: 3,
      background: { r: 240, g: 240, b: 240 },
    },
  })
    .png()
    .toBuffer();

  const canonicalTruths = [];
  for (let index = 1; index <= 30; index++) {
    const id = String(index).padStart(3, "0");
    const fileName = `val-${id}.png`;
    const sourceGroup = `validation-group-${id}`;
    const image = path.join(images, fileName);
    writeFileSync(image, Buffer.concat([basePng, Buffer.from(`image-${id}`)]));
    const annotation = path.join(annotations, `val-${id}.json`);
    writeFileSync(
      annotation,
      `${JSON.stringify({
        version: "nail-texture-dataset/v1",
        image: {
          id: `val-${id}`,
          fileName,
          sourceGroup,
          width: 20,
          height: 20,
        },
        annotations: [
          {
            id: `nail-${id}`,
            label: "nail_texture",
            polygon: [
              { x: 2, y: 2 },
              { x: 8, y: 2 },
              { x: 8, y: 8 },
              { x: 2, y: 8 },
            ],
          },
        ],
      })}\n`,
    );
    const report = path.join(
      reports,
      `validation-truth-${id}-val-${id}-final.json`,
    );
    const reportDocument = {
      schemaVersion: 1,
      ok: true,
      decision:
        "approved_as_validation_truth_candidate_pending_dataset_materialization",
      inputs: {
        truthRole: "val",
        image,
        imageSha256: sha(image),
        annotation,
        annotationSha256: sha(annotation),
      },
      policy: {
        trainingUse: "prohibited",
        validationUse: "prohibited-until-materialization-audit",
      },
      item: {
        fileName,
        sha256: sha(image),
        sourceGroup,
        completeMaskCount: 1,
        trainingUse: "prohibited",
      },
      errors: [],
    };
    writeFileSync(report, `${JSON.stringify(reportDocument, null, 2)}\n`);
    canonicalTruths.push({
      reportPath: report,
      reportName: path.basename(report),
      reportSha256: sha(report),
      sequence: index,
      fileName,
      imageSha256: sha(image),
      sourceGroup,
      completeMaskCount: 1,
      annotationPath: annotation,
      annotationSha256: sha(annotation),
    });
  }
  const index = {
    schemaVersion: 1,
    ok: true,
    decision: "approved_unique_validation_truth_index",
    inputs: { truthRole: "val", truthDir: reports },
    policy: {
      trainingUse: "prohibited",
      validationUse: "prohibited-until-materialization-audit",
    },
    summary: {
      approvedReportCount: 30,
      rejectedReportCount: 1,
      uniqueImageCount: 30,
      completeMaskCount: 30,
      redundantReportCount: 0,
      redundantImageCount: 0,
      conflictingImageCount: 0,
    },
    canonicalTruths,
    rejectedReports: [
      {
        reportName: "validation-truth-999-excluded-final.json",
        decision: "reject_val_truth_candidate",
        errors: ["cropped required nail"],
      },
    ],
    redundantReports: [],
    conflicts: [],
    errors: [],
  };
  const indexPath = path.join(root, "validation-truth-index.json");
  writeFileSync(indexPath, `${JSON.stringify(index, null, 2)}\n`);
  return { root, indexPath, index };
}

function saveIndex(item: Fixture) {
  writeFileSync(item.indexPath, `${JSON.stringify(item.index, null, 2)}\n`);
}

function run(item: Fixture, outputName = "materialized") {
  const output = path.join(item.root, outputName);
  const result = spawnSync(
    "python",
    [script, "--truth-index", item.indexPath, "--output-dir", output],
    { encoding: "utf8" },
  );
  return { ...result, output };
}

function refreshAnnotationEvidence(item: Fixture, truthIndex = 0) {
  const truth = item.index.canonicalTruths[truthIndex];
  const report = JSON.parse(readFileSync(truth.reportPath, "utf8"));
  const annotationHash = sha(truth.annotationPath);
  truth.annotationSha256 = annotationHash;
  report.inputs.annotationSha256 = annotationHash;
  writeFileSync(truth.reportPath, `${JSON.stringify(report, null, 2)}\n`);
  truth.reportSha256 = sha(truth.reportPath);
  saveIndex(item);
}

function assertTransactionalFailure(
  item: Fixture,
  expected: RegExp,
  outputName = "failed-output",
) {
  const result = run(item, outputName);
  assert.notEqual(result.status, 0, result.stdout);
  assert.match(result.stderr, expected);
  assert.equal(existsSync(result.output), false);
  assert.deepEqual(
    readdirSync(item.root).filter((name) =>
      name.startsWith(`.${outputName}.tmp-`),
    ),
    [],
  );
}

test("materializes only canonical truths deterministically on a Chinese Windows-safe path", async () => {
  const item = await fixture();
  const first = run(item, "物化结果一");
  assert.equal(first.status, 0, first.stderr || first.stdout);
  const report = JSON.parse(
    readFileSync(
      path.join(first.output, "metadata", "materialization-report.json"),
      "utf8",
    ),
  );
  assert.equal(report.counts.validationImages, 30);
  assert.equal(report.counts.validationMasks, 30);
  assert.equal(report.counts.orphanFiles, 0);
  assert.equal(report.trainingUse, "prohibited");
  assert.equal(report.records.length, 30);
  assert.equal(
    report.records.some(
      (record: { fileName: string }) =>
        record.fileName === "validation-truth-999-excluded-final.json",
    ),
    false,
  );
  const split = JSON.parse(
    readFileSync(path.join(first.output, "metadata", "split.json"), "utf8"),
  );
  assert.deepEqual(split.train, []);
  assert.deepEqual(split.test, []);
  assert.equal(split.val.length, 30);
  assert.equal(
    readdirSync(path.join(first.output, "images", "val")).length,
    30,
  );
  assert.equal(
    readdirSync(path.join(first.output, "labels", "val")).length,
    30,
  );
  assert.match(
    readFileSync(
      path.join(first.output, "metadata", "sources-isolation.csv"),
      "utf8",
    ),
    /^fileName,sourceGroup,imageSha256\n/,
  );

  const second = run(item, "物化结果二");
  assert.equal(second.status, 0, second.stderr || second.stdout);
  const secondReport = JSON.parse(
    readFileSync(
      path.join(second.output, "metadata", "materialization-report.json"),
      "utf8",
    ),
  );
  assert.equal(secondReport.recordsSha256, report.recordsSha256);
  assert.equal(secondReport.datasetFilesSha256, report.datasetFilesSha256);
});

test("rejects insufficient, conflicting, duplicate-name, and duplicate-hash indexes", async (t) => {
  await t.test("fewer than 30", async () => {
    const item = await fixture();
    item.index.canonicalTruths.pop();
    item.index.summary.uniqueImageCount = 29;
    saveIndex(item);
    assertTransactionalFailure(item, /below 30/);
  });
  await t.test("conflict", async () => {
    const item = await fixture();
    item.index.conflicts = [{ fileName: "val-001.png" }];
    item.index.summary.conflictingImageCount = 1;
    saveIndex(item);
    assertTransactionalFailure(item, /conflicting truths/);
  });
  await t.test("duplicate fileName", async () => {
    const item = await fixture();
    item.index.canonicalTruths[1].fileName =
      item.index.canonicalTruths[0].fileName;
    saveIndex(item);
    assertTransactionalFailure(item, /duplicate canonical fileName/);
  });
  await t.test("duplicate image SHA", async () => {
    const item = await fixture();
    item.index.canonicalTruths[1].imageSha256 =
      item.index.canonicalTruths[0].imageSha256;
    saveIndex(item);
    assertTransactionalFailure(item, /duplicate canonical image SHA-256/);
  });
});

test("rejects final-report, source-image, and annotation SHA drift transactionally", async (t) => {
  await t.test("final report drift", async () => {
    const item = await fixture();
    writeFileSync(
      item.index.canonicalTruths[0].reportPath,
      `${readFileSync(item.index.canonicalTruths[0].reportPath, "utf8")} `,
    );
    assertTransactionalFailure(item, /final report SHA-256 drift/);
  });
  await t.test("source image drift", async () => {
    const item = await fixture();
    const report = JSON.parse(
      readFileSync(item.index.canonicalTruths[0].reportPath, "utf8"),
    );
    writeFileSync(
      report.inputs.image,
      Buffer.concat([readFileSync(report.inputs.image), Buffer.from("drift")]),
    );
    assertTransactionalFailure(item, /source image SHA-256 drift/);
  });
  await t.test("annotation drift", async () => {
    const item = await fixture();
    writeFileSync(
      item.index.canonicalTruths[0].annotationPath,
      `${readFileSync(item.index.canonicalTruths[0].annotationPath, "utf8")} `,
    );
    assertTransactionalFailure(item, /annotation SHA-256 drift/);
  });
});

test("rejects invalid polygons and same-image overlap before publishing output", async (t) => {
  await t.test("invalid polygon", async () => {
    const item = await fixture();
    const annotationPath = item.index.canonicalTruths[0].annotationPath;
    const annotation = JSON.parse(readFileSync(annotationPath, "utf8"));
    annotation.annotations[0].polygon = [
      { x: 2, y: 2 },
      { x: 8, y: 8 },
      { x: 2, y: 8 },
      { x: 8, y: 2 },
    ];
    writeFileSync(annotationPath, `${JSON.stringify(annotation)}\n`);
    refreshAnnotationEvidence(item);
    assertTransactionalFailure(item, /invalid topology/);
  });
  await t.test("pairwise overlap", async () => {
    const item = await fixture();
    const truth = item.index.canonicalTruths[0];
    const annotation = JSON.parse(readFileSync(truth.annotationPath, "utf8"));
    annotation.annotations.push({
      label: "nail_texture",
      polygon: [
        { x: 7.99999999, y: 5 },
        { x: 12, y: 5 },
        { x: 12, y: 12 },
        { x: 7.99999999, y: 12 },
      ],
    });
    writeFileSync(truth.annotationPath, `${JSON.stringify(annotation)}\n`);
    truth.completeMaskCount = 2;
    const report = JSON.parse(readFileSync(truth.reportPath, "utf8"));
    report.item.completeMaskCount = 2;
    report.inputs.annotationSha256 = sha(truth.annotationPath);
    writeFileSync(truth.reportPath, `${JSON.stringify(report, null, 2)}\n`);
    truth.annotationSha256 = sha(truth.annotationPath);
    truth.reportSha256 = sha(truth.reportPath);
    item.index.summary.completeMaskCount = 31;
    saveIndex(item);
    assertTransactionalFailure(item, /overlap/);
  });
});
