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
import sharp from "sharp";

const materializeScript = path.resolve(
  "model/training/materialize-canonical-validation-dataset.py",
);
const finalizeScript = path.resolve(
  "model/training/finalize-validation-materialization-audit.py",
);
const sha = (file: string) =>
  createHash("sha256").update(readFileSync(file)).digest("hex");

type Fixture = Awaited<ReturnType<typeof fixture>>;

async function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "finalize-val-materialization-"));
  const sourceRoot = path.join(root, "source");
  const images = path.join(sourceRoot, "images");
  const annotations = path.join(sourceRoot, "annotations");
  const reports = path.join(sourceRoot, "reports");
  mkdirSync(images, { recursive: true });
  mkdirSync(annotations, { recursive: true });
  mkdirSync(reports, { recursive: true });
  const basePng = await sharp({
    create: {
      width: 20,
      height: 20,
      channels: 3,
      background: { r: 230, g: 230, b: 230 },
    },
  })
    .png()
    .toBuffer();
  const truths = [];
  for (let index = 1; index <= 30; index++) {
    const id = String(index).padStart(3, "0");
    const fileName = `val-${id}.png`;
    const sourceGroup = `val-group-${id}`;
    const image = path.join(images, fileName);
    writeFileSync(image, Buffer.concat([basePng, Buffer.from(id)]));
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
    writeFileSync(
      report,
      `${JSON.stringify({
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
        item: {
          fileName,
          sha256: sha(image),
          sourceGroup,
          completeMaskCount: 1,
          trainingUse: "prohibited",
        },
      })}\n`,
    );
    truths.push({
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
  const truthIndex = path.join(root, "validation-truth-index.json");
  const truthDocument = {
    ok: true,
    decision: "approved_unique_validation_truth_index",
    inputs: { truthRole: "val" },
    summary: {
      uniqueImageCount: 30,
      completeMaskCount: 30,
      conflictingImageCount: 0,
    },
    canonicalTruths: truths,
    conflicts: [],
    errors: [],
  };
  writeFileSync(truthIndex, `${JSON.stringify(truthDocument, null, 2)}\n`);
  const datasetRoot = path.join(root, "dataset");
  const materialized = spawnSync(
    "python",
    [
      materializeScript,
      "--truth-index",
      truthIndex,
      "--output-dir",
      datasetRoot,
    ],
    { encoding: "utf8" },
  );
  assert.equal(materialized.status, 0, materialized.stderr || materialized.stdout);
  const dataset = path.join(datasetRoot, "dataset.yaml");
  const materializationReport = path.join(
    datasetRoot,
    "metadata",
    "materialization-report.json",
  );
  const roleIsolation = path.join(root, "role-isolation.json");
  const roleIsolationDocument = {
    ok: true,
    status: "PASS",
    decision: "approved_validation_role_isolation",
    inputs: {
      valMaterializationReport: {
        path: materializationReport,
        sha256: sha(materializationReport),
      },
    },
    roles: {
      val: { images: 30, imageSha256: 30, sourceGroups: 30 },
      train: { images: 100 },
      "frozen-test": { images: 67 },
    },
    overlaps: { fileName: [], imageSha256: [], sourceGroup: [] },
    invariants: {
      validationHasNoOrphans: true,
      fileNamesDisjointAcrossRoles: true,
      imageSha256DisjointAcrossRoles: true,
      sourceGroupsDisjointAcrossRoles: true,
    },
    errors: [],
  };
  writeFileSync(
    roleIsolation,
    `${JSON.stringify(roleIsolationDocument, null, 2)}\n`,
  );
  return {
    root,
    truthIndex,
    truthDocument,
    datasetRoot,
    dataset,
    materializationReport,
    roleIsolation,
    roleIsolationDocument,
  };
}

function run(item: Fixture) {
  const output = path.join(item.root, "truth-audit.json");
  const result = spawnSync(
    "python",
    [
      finalizeScript,
      "--dataset",
      item.dataset,
      "--truth-index",
      item.truthIndex,
      "--materialization-report",
      item.materializationReport,
      "--role-isolation-report",
      item.roleIsolation,
      "--output",
      output,
    ],
    { encoding: "utf8" },
  );
  return {
    ...result,
    output,
    report: JSON.parse(readFileSync(output, "utf8")),
  };
}

test("emits the exact downstream approved_as_calibration_truth contract", async () => {
  const item = await fixture();
  const result = run(item);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(result.report.status, "PASS");
  assert.equal(result.report.decision, "approved_as_calibration_truth");
  assert.equal(result.report.calibrationTruthEligible, true);
  assert.equal(result.report.trainingUse, "prohibited");
  assert.deepEqual(
    {
      expectedImages: result.report.counts.expectedImages,
      reviewedImages: result.report.counts.reviewedImages,
      pass: result.report.counts.pass,
      rework: result.report.counts.rework,
      exclude: result.report.counts.exclude,
    },
    {
      expectedImages: 30,
      reviewedImages: 30,
      pass: 30,
      rework: 0,
      exclude: 0,
    },
  );
  assert.equal(Object.keys(result.report.labelSha256).length, 30);
  assert.equal(result.report.inputs.split, "val");
  assert.equal(result.report.inputs.datasetYaml, item.dataset);
  assert.equal(result.report.inputs.datasetYamlSha256, sha(item.dataset));
  assert.equal(result.report.counts.invalidPolygons, 0);
  assert.equal(result.report.counts.overlapPairs, 0);
});

test("holds on isolation failure or any upstream/data hash drift", async (t) => {
  await t.test("role isolation is not PASS", async () => {
    const item = await fixture();
    item.roleIsolationDocument.ok = false;
    item.roleIsolationDocument.status = "HOLD";
    item.roleIsolationDocument.decision = "hold_validation_role_isolation";
    writeFileSync(
      item.roleIsolation,
      `${JSON.stringify(item.roleIsolationDocument, null, 2)}\n`,
    );
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.equal(result.report.status, "HOLD");
    assert.equal(result.report.decision, "rejected_as_calibration_truth");
    assert.equal(result.report.calibrationTruthEligible, false);
    assert.match(result.report.errors.join("\n"), /not PASS/);
  });
  await t.test("dataset hash drift", async () => {
    const item = await fixture();
    writeFileSync(item.dataset, `${readFileSync(item.dataset, "utf8")}# drift\n`);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /dataset binding drift/);
  });
  await t.test("materialized label hash drift", async () => {
    const item = await fixture();
    const label = path.join(item.datasetRoot, "labels", "val", "val-001.txt");
    writeFileSync(label, `${readFileSync(label, "utf8")} `);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.report.errors.join("\n"),
      /labels\/val\/val-001\.txt SHA-256 drift/,
    );
  });
  await t.test("materialized annotation hash drift", async () => {
    const item = await fixture();
    const annotation = path.join(
      item.datasetRoot,
      "annotations",
      "raw-json",
      "val-001.json",
    );
    writeFileSync(annotation, `${readFileSync(annotation, "utf8")} `);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.report.errors.join("\n"),
      /annotations\/raw-json\/val-001\.json SHA-256 drift/,
    );
  });
  await t.test("unlisted materialization orphan", async () => {
    const item = await fixture();
    writeFileSync(
      path.join(item.datasetRoot, "images", "val", "orphan.png"),
      "orphan",
    );
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.report.errors.join("\n"),
      /current output tree.*orphan=.*images\/val\/orphan\.png/,
    );
  });
  await t.test("canonical coverage mismatch", async () => {
    const item = await fixture();
    item.truthDocument.canonicalTruths.pop();
    item.truthDocument.summary.uniqueImageCount = 29;
    item.truthDocument.summary.completeMaskCount = 29;
    writeFileSync(
      item.truthIndex,
      `${JSON.stringify(item.truthDocument, null, 2)}\n`,
    );
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(result.report.errors.join("\n"), /fewer than 30/);
  });
});

test("independently rejects invalid or overlapping YOLO polygons even when hashes are rebound", async (t) => {
  async function rebindLabel(
    item: Fixture,
    content: string,
  ) {
    const label = path.join(item.datasetRoot, "labels", "val", "val-001.txt");
    const converted = path.join(
      item.datasetRoot,
      "labels-yolo-seg",
      "val",
      "val-001.txt",
    );
    writeFileSync(label, content);
    writeFileSync(converted, content);
    const materialization = JSON.parse(
      readFileSync(item.materializationReport, "utf8"),
    );
    const record = materialization.records.find(
      (candidate: { fileName: string }) => candidate.fileName === "val-001.png",
    );
    record.materializedValidationLabelSha256 = sha(label);
    record.materializedYoloLabelSha256 = sha(converted);
    materialization.recordsSha256 = createHash("sha256")
      .update(
        JSON.stringify(materialization.records, Object.keys(materialization.records[0]).sort()),
      )
      .digest("hex");
    // Use Python's canonical JSON for the aggregate to avoid JS replacer behavior.
    // Write once, calculate from the updated in-memory records with a small helper file.
    const scratch = path.join(item.root, "records.json");
    writeFileSync(scratch, JSON.stringify({ records: materialization.records }));
    const corrected = spawnSync(
      "python",
      [
        "-c",
        "import hashlib,json,sys; v=json.load(open(sys.argv[1],encoding='utf-8')); print(hashlib.sha256(json.dumps(v['records'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())",
        scratch,
      ],
      { encoding: "utf8" },
    );
    assert.equal(corrected.status, 0, corrected.stderr);
    materialization.recordsSha256 = corrected.stdout.trim();
    for (const artifact of materialization.datasetFiles) {
      if (
        artifact.path === "labels/val/val-001.txt" ||
        artifact.path === "labels-yolo-seg/val/val-001.txt"
      ) {
        artifact.sha256 = artifact.path.startsWith("labels/val")
          ? sha(label)
          : sha(converted);
      }
    }
    const filesScratch = path.join(item.root, "dataset-files.json");
    writeFileSync(
      filesScratch,
      JSON.stringify({ records: materialization.datasetFiles }),
    );
    const filesAggregate = spawnSync(
      "python",
      [
        "-c",
        "import hashlib,json,sys; v=json.load(open(sys.argv[1],encoding='utf-8')); print(hashlib.sha256(json.dumps(v['records'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())",
        filesScratch,
      ],
      { encoding: "utf8" },
    );
    materialization.datasetFilesSha256 = filesAggregate.stdout.trim();
    writeFileSync(
      item.materializationReport,
      `${JSON.stringify(materialization, null, 2)}\n`,
    );
    item.roleIsolationDocument.inputs.valMaterializationReport.sha256 = sha(
      item.materializationReport,
    );
    writeFileSync(
      item.roleIsolation,
      `${JSON.stringify(item.roleIsolationDocument, null, 2)}\n`,
    );
  }

  await t.test("invalid topology", async () => {
    const item = await fixture();
    await rebindLabel(
      item,
      "0 0.10000000 0.10000000 0.40000000 0.40000000 0.10000000 0.40000000 0.40000000 0.10000000\n",
    );
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.report.errors.join("\n"),
      /differs from canonical annotation|invalid polygon topology/,
    );
  });
  await t.test("pairwise overlap", async () => {
    const item = await fixture();
    const polygon =
      "0 0.10000000 0.10000000 0.40000000 0.10000000 0.40000000 0.40000000 0.10000000 0.40000000";
    await rebindLabel(item, `${polygon}\n${polygon}\n`);
    const result = run(item);
    assert.notEqual(result.status, 0);
    assert.match(
      result.report.errors.join("\n"),
      /differs from canonical annotation|overlap/,
    );
  });
});
