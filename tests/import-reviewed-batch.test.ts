import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, writeFile, access } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("import-reviewed-batch copies selected artifacts into dataset and runs downstream steps", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-import-dataset-"));
  const rootDir = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-import-root-"));
  const reviewDir = path.join(rootDir, "review");
  const selectedImagesDir = path.join(rootDir, "selected", "images");
  const selectedAnnotationDir = path.join(rootDir, "selected", "annotations", "raw-json");
  await mkdir(reviewDir, { recursive: true });
  await mkdir(selectedImagesDir, { recursive: true });
  await mkdir(selectedAnnotationDir, { recursive: true });

  await writeFile(
    path.join(reviewDir, "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "sample-001.jpg,true,keep,good_detection,4,true,train,reference,light,red,highlight|gold_line,ok",
      "sample-002.png,false,reserve_for_test,complex_background,3,false,test,merchant,dark,black,glitter,ok",
      "",
    ].join("\n"),
    "utf8"
  );
  await writeFile(
    path.join(rootDir, "selected", "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [
          { fileName: "sample-001.jpg" },
          { fileName: "sample-002.png" },
        ],
      },
      null,
      2
    ),
    "utf8"
  );
  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(selectedImagesDir, "sample-001.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(selectedImagesDir, "sample-002.png"));

  const prepResult = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/prepare-reviewed-annotations.ts",
      "--root-dir",
      rootDir,
    ],
    {
      cwd: path.resolve("."),
    }
  );
  const prepReport = JSON.parse(prepResult.stdout) as { preparedCount: number };
  assert.equal(prepReport.preparedCount, 2);

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/import-reviewed-batch.ts",
      "--root-dir",
      rootDir,
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
    reportPath: string;
    copiedImages: string[];
    importedDocuments: Array<{ polygonCount: number }>;
    steps: Array<{ name: string; ok: boolean }>;
  };

  assert.equal(report.ok, true);
  assert.equal(report.sourceGroup, "seed-batch-001");
  assert.deepEqual(report.copiedImages, ["sample-001.jpg", "sample-002.png"]);
  assert.ok(report.importedDocuments.every((doc) => doc.polygonCount >= 3));
  assert.ok(report.steps.some((step) => step.name === "sync-sources-csv" && step.ok));
  assert.ok(report.steps.some((step) => step.name === "convert-annotations" && step.ok));
  const sourcesAuditStep = report.steps.find((step) => step.name === "audit-sources-csv");
  assert.equal(sourcesAuditStep?.ok, true);
  const sourcesAuditStdout = sourcesAuditStep?.stdout as
    | { issues?: Array<{ code: string }> }
    | undefined;
  assert.deepEqual(
    (sourcesAuditStdout?.issues ?? []).filter(
      (issue) => issue.code === "missing_origin_ref" || issue.code === "missing_license"
    ),
    []
  );

  const sourcesCsv = await readFile(path.join(datasetRoot, "metadata", "sources.csv"), "utf8");
  assert.match(sourcesCsv, /sample-001\.jpg/);
  assert.match(sourcesCsv, /sample-002\.png/);

  let labelContent = "";
  for (const subset of ["train", "val", "test"] as const) {
    const labelPath = path.join(datasetRoot, "labels-yolo-seg", subset, "sample-001.txt");
    try {
      await access(labelPath);
      labelContent = await readFile(labelPath, "utf8");
      break;
    } catch {
      // continue searching other subsets
    }
  }
  assert.ok(labelContent.length > 0);

  const savedReport = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(savedReport.ok, true);
});
