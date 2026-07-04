import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import sharp from "sharp";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("phase1 intake pipeline runs manifest preflight through label conversion", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-pipeline-dataset-"));
  const batchRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-pipeline-batch-"));
  const imageDir = path.join(batchRoot, "images");
  await mkdir(imageDir, { recursive: true });

  await sharp({
    create: {
      width: 128,
      height: 128,
      channels: 3,
      background: { r: 240, g: 200, b: 210 },
    },
  })
    .png()
    .toFile(path.join(imageDir, "sample-001.png"));

  const manifestPath = path.join(batchRoot, "batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "reference",
        license: "internal-test-only",
        defaultOriginRef: "generated-test-batch",
        copyImagesToDataset: true,
        items: [
          {
            fileName: "sample-001.png",
            notes: "generated pipeline sample",
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-phase1-intake-pipeline.ts",
      "--manifest",
      manifestPath,
      "--image-dir",
      imageDir,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    sourceGroup: string;
    steps: Array<{ name: string; ok: boolean }>;
    reportPath: string;
    readinessSnapshot: {
      ok: boolean;
      totals: { images: number; validMasks: number };
      gates: {
        imageCount: { ok: boolean; actual: number; required: number };
        validMaskCount: { ok: boolean; actual: number; required: number };
      };
    };
  };

  assert.equal(report.ok, true);
  assert.equal(report.sourceGroup, "seed-batch-001");
  assert.ok(report.steps.some((step) => step.name === "validate-intake-batch" && step.ok));
  assert.ok(
    report.steps.some((step) => step.name === "export-fallback-annotations" && step.ok)
  );
  assert.ok(report.steps.some((step) => step.name === "convert-annotations" && step.ok));
  assert.ok(report.steps.some((step) => step.name === "audit-phase1-readiness" && step.ok));
  assert.equal(report.readinessSnapshot.ok, false);
  assert.equal(report.readinessSnapshot.totals.images, 1);
  assert.equal(report.readinessSnapshot.gates.imageCount.required, 200);
  assert.equal(report.readinessSnapshot.gates.validMaskCount.required, 800);

  const savedReport = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    ok: boolean;
    readinessSnapshot: {
      totals: { images: number };
    };
  };
  assert.equal(savedReport.ok, true);
  assert.equal(savedReport.readinessSnapshot.totals.images, 1);

  const readinessReport = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "phase1-readiness.json"), "utf8")
  ) as { ok: boolean; totals: { images: number } };
  assert.equal(readinessReport.ok, false);
  assert.equal(readinessReport.totals.images, 1);

  const sourcesCsv = await readFile(
    path.join(datasetRoot, "metadata", "sources.csv"),
    "utf8"
  );
  assert.match(sourcesCsv, /sample-001\.png/);

  const splitJson = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "split.json"), "utf8")
  ) as { train: string[]; val: string[]; test: string[] };
  assert.equal(splitJson.train.length + splitJson.val.length + splitJson.test.length, 1);
});

test("phase1 intake pipeline imports negative manifests as empty negative annotations", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-negative-dataset-"));
  const batchRoot = await mkdtemp(path.join(os.tmpdir(), "nail-phase1-negative-batch-"));
  const imageDir = path.join(batchRoot, "images");
  await mkdir(imageDir, { recursive: true });

  await sharp({
    create: {
      width: 96,
      height: 96,
      channels: 3,
      background: { r: 12, g: 15, b: 20 },
    },
  })
    .png()
    .toFile(path.join(imageDir, "plain-background.png"));

  const manifestPath = path.join(batchRoot, "negative-batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "negative-batch-001",
        originType: "negative",
        license: "internal-test-only",
        defaultOriginRef: "generated no-nail negative batch",
        copyImagesToDataset: true,
        items: [
          {
            fileName: "plain-background.png",
            notes: "sample=negative; reason=negative_sample",
          },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-phase1-intake-pipeline.ts",
      "--manifest",
      manifestPath,
      "--image-dir",
      imageDir,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    steps: Array<{ name: string; ok: boolean }>;
  };
  assert.equal(report.ok, true);
  assert.ok(report.steps.some((step) => step.name === "export-fallback-annotations" && step.ok));

  const annotation = JSON.parse(
    await readFile(
      path.join(datasetRoot, "annotations", "raw-json", "plain-background.json"),
      "utf8"
    )
  ) as { image: { negative: boolean }; annotations: unknown[] };
  assert.equal(annotation.image.negative, true);
  assert.deepEqual(annotation.annotations, []);

  const sourcesCsv = await readFile(path.join(datasetRoot, "metadata", "sources.csv"), "utf8");
  assert.match(sourcesCsv, /plain-background\.png/);
  assert.match(sourcesCsv, /negative-batch-001,negative/);
  assert.match(sourcesCsv, /,true,annotations\/raw-json\/plain-background\.json/);
});
