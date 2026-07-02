import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("run-reviewed-batch-import-pipeline imports reviewed batch and runs readiness gate", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-import-pipeline-dataset-"));
  const rootDir = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-import-pipeline-root-"));
  await mkdir(path.join(rootDir, "images"), { recursive: true });
  await mkdir(path.join(rootDir, "review"), { recursive: true });
  await mkdir(path.join(rootDir, "selected", "images"), { recursive: true });
  await mkdir(path.join(rootDir, "selected", "annotations", "raw-json"), { recursive: true });

  await writeFile(
    path.join(rootDir, "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [{ fileName: "sample-001.jpg" }, { fileName: "sample-002.png" }],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    path.join(rootDir, "review", "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "sample-001.jpg,true,keep,good_detection,4,true,train,reference,light,red,highlight|gold_line,ok",
      "sample-002.png,false,reserve_for_test,complex_background,3,false,test,negative,dark,black,glitter,ok",
      "",
    ].join("\n"),
    "utf8"
  );
  await writeFile(
    path.join(rootDir, "review", "failure-classification.csv"),
    "fileName,stage,category,subcategory,severity,action,notes\n",
    "utf8"
  );
  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(rootDir, "images", "sample-001.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(rootDir, "images", "sample-002.png"));

  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-seed-batch-prep-pipeline.ts",
      "--root-dir",
      rootDir,
    ],
    { cwd: path.resolve(".") }
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-reviewed-batch-import-pipeline.ts",
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
    reportPath: string;
    steps: Array<{ name: string; ok: boolean; stdout?: { ok?: boolean } }>;
  };
  assert.equal(report.ok, true);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    [
      "audit-seed-batch-workspace",
      "import-reviewed-batch",
      "audit-phase1-readiness",
      "plan-phase1-collection",
      "generate-first-batch-checklist",
      "build-initial-release-trace-draft",
      "build-reviewed-batch-release-handoff",
    ]
  );
  assert.ok(report.steps.every((step) => step.ok));

  const readiness = report.steps.find((step) => step.name === "audit-phase1-readiness");
  assert.equal(readiness?.stdout?.ok, false);

  const saved = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(saved.ok, true);
  const readinessFile = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "phase1-readiness.json"), "utf8")
  ) as { totals: { images: number } };
  assert.equal(readinessFile.totals.images, 2);
  const checklistFile = JSON.parse(
    await readFile(path.join(datasetRoot, "metadata", "first-batch-execution-checklist.json"), "utf8")
  ) as { firstBatchRecommendation: { targetImages: number } };
  assert.equal(checklistFile.firstBatchRecommendation.targetImages, 50);
  const draft = JSON.parse(await readFile(path.join(rootDir, "release-trace-draft.json"), "utf8")) as {
    draft: boolean;
    batch: { sourceGroup: string; importedFileCount: number };
    release: { finalAuditStatus: string | null };
  };
  assert.equal(draft.draft, true);
  assert.equal(draft.batch.sourceGroup, "seed-batch-001");
  assert.equal(draft.batch.importedFileCount, 2);
  assert.equal(draft.release.finalAuditStatus, null);
  const handoff = JSON.parse(
    await readFile(path.join(rootDir, "reviewed-batch-release-handoff.json"), "utf8")
  ) as {
    version: string;
    governanceHints: {
      reviewedBatchRootDir: string;
      reviewedBatchImportPipelineReportPath: string;
      releaseTraceDraftPath: string;
    };
    batch: { sourceGroup: string; importedFileCount: number };
  };
  assert.equal(handoff.version, "reviewed-batch-release-handoff/v1");
  assert.equal(handoff.governanceHints.reviewedBatchRootDir, rootDir);
  assert.equal(handoff.batch.sourceGroup, "seed-batch-001");
  assert.equal(handoff.batch.importedFileCount, 2);
});
