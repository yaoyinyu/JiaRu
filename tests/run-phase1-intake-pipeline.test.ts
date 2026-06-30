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
  };

  assert.equal(report.ok, true);
  assert.equal(report.sourceGroup, "seed-batch-001");
  assert.ok(report.steps.some((step) => step.name === "validate-intake-batch" && step.ok));
  assert.ok(
    report.steps.some((step) => step.name === "export-fallback-annotations" && step.ok)
  );
  assert.ok(report.steps.some((step) => step.name === "convert-annotations" && step.ok));

  const savedReport = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    ok: boolean;
  };
  assert.equal(savedReport.ok, true);

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
