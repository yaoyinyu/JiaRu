import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("run-seed-batch-prep-pipeline advances a seed batch through reviewed annotation prep", async () => {
  const rootDir = await mkdtemp(path.join(os.tmpdir(), "nail-seed-prep-pipeline-"));
  await mkdir(path.join(rootDir, "images"), { recursive: true });
  await mkdir(path.join(rootDir, "review"), { recursive: true });

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
  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(rootDir, "images", "sample-001.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(rootDir, "images", "sample-002.png"));
  await writeFile(
    path.join(rootDir, "review", "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "sample-001.jpg,true,keep,good_detection,4,true,train,reference,light,red,highlight|gold_line,ok",
      "sample-002.png,false,reserve_for_test,complex_background,3,false,test,merchant,dark,black,glitter,ok",
      "",
    ].join("\n"),
    "utf8"
  );
  await writeFile(
    path.join(rootDir, "review", "failure-classification.csv"),
    "fileName,stage,category,subcategory,severity,action,notes\n",
    "utf8"
  );

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/run-seed-batch-prep-pipeline.ts",
      "--root-dir",
      rootDir,
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const report = JSON.parse(stdout) as {
    ok: boolean;
    reportPath: string;
    steps: Array<{ name: string; ok: boolean }>;
  };
  assert.equal(report.ok, true);
  assert.deepEqual(
    report.steps.map((step) => step.name),
    [
      "audit-seed-batch-workspace",
      "audit-screening-review",
      "build-reviewed-intake-batch",
      "prepare-reviewed-annotations",
    ]
  );
  assert.ok(report.steps.every((step) => step.ok));

  const prepReport = JSON.parse(
    await readFile(path.join(rootDir, "selected", "reviewed-annotation-prep-report.json"), "utf8")
  ) as { preparedCount: number };
  assert.equal(prepReport.preparedCount, 2);

  const persisted = JSON.parse(await readFile(report.reportPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});
