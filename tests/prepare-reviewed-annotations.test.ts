import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile, cp } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

async function createReviewedBatch(options?: { firstCandidateCount?: number }) {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-prepare-reviewed-"));
  const reviewDir = path.join(root, "review");
  const selectedImagesDir = path.join(root, "selected", "images");
  await mkdir(reviewDir, { recursive: true });
  await mkdir(selectedImagesDir, { recursive: true });

  await writeFile(
    path.join(reviewDir, "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      `sample-001.jpg,true,keep,good_detection,${options?.firstCandidateCount ?? 4},true,train,reference,light,red,highlight|gold_line,ok`,
      "sample-002.png,false,reserve_for_test,complex_background,3,false,test,merchant,dark,black,glitter,ok",
      "",
    ].join("\n"),
    "utf8"
  );

  await writeFile(
    path.join(root, "selected", "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [
          { fileName: "sample-001.jpg", notes: "keep" },
          { fileName: "sample-002.png", notes: "test" },
        ],
      },
      null,
      2
    ),
    "utf8"
  );

  await cp(path.resolve("model/5188.jpg_wh860.jpg"), path.join(selectedImagesDir, "sample-001.jpg"));
  await cp(path.resolve("model/5188.jpg_wh860.png"), path.join(selectedImagesDir, "sample-002.png"));

  return root;
}

async function runPrepareReviewedAnnotations(root: string, args: string[] = []) {
  return await new Promise<{ code: number; stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/prepare-reviewed-annotations.ts",
        "--root-dir",
        root,
        ...args,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += String(chunk)));
    child.stderr.on("data", (chunk) => (stderr += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => resolve({ code: code ?? 0, stdout, stderr }));
  });
}

test("prepare-reviewed-annotations writes initial annotation jsons and prep report", async () => {
  const root = await createReviewedBatch();
  const result = await runPrepareReviewedAnnotations(root);
  assert.equal(result.code, 0, result.stderr);

  const report = JSON.parse(result.stdout) as {
    preparedCount: number;
    totalPolygons: number;
    manualFixCount: number;
    reportPath: string;
    qualityGate: {
      ok: boolean;
      infoCount: number;
      issueCount: number;
      manualReviewQueue: Array<{ fileName: string; issues: Array<{ code: string }> }>;
    };
    outputs: Array<{ annotationPath: string; polygonCount: number; targetSplitHint: string }>;
  };

  assert.equal(report.preparedCount, 2);
  assert.ok(report.totalPolygons >= 7);
  assert.equal(report.manualFixCount, 1);
  assert.equal(report.outputs[0]?.targetSplitHint, "train");
  assert.equal(report.outputs[1]?.targetSplitHint, "test");
  assert.equal(report.qualityGate.ok, true);
  assert.ok(report.qualityGate.infoCount >= 1);
  assert.ok(
    report.qualityGate.manualReviewQueue.some(
      (item) =>
        item.fileName === "sample-001.jpg" &&
        item.issues.some((issue) => issue.code === "manual_fix_required")
    )
  );

  const annotation = JSON.parse(
    await readFile(report.outputs[0]!.annotationPath, "utf8")
  ) as { annotations: unknown[] };
  assert.ok(annotation.annotations.length >= 4);

  const persisted = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    preparedCount: number;
    qualityGate: { issueCount: number };
  };
  assert.equal(persisted.preparedCount, 2);
  assert.equal(persisted.qualityGate.issueCount, report.qualityGate.issueCount);
});

test("prepare-reviewed-annotations strict mode fails when reviewer counts need inspection", async () => {
  const root = await createReviewedBatch({ firstCandidateCount: 999 });
  const result = await runPrepareReviewedAnnotations(root, ["--fail-on-issues"]);
  assert.notEqual(result.code, 0);

  const report = JSON.parse(result.stdout) as {
    ok: boolean;
    qualityGate: { warningCount: number; failOnIssues: boolean };
    issues: Array<{ code: string; expected?: number }>;
  };
  assert.equal(report.ok, true);
  assert.equal(report.qualityGate.failOnIssues, true);
  assert.ok(report.qualityGate.warningCount >= 1);
  assert.ok(
    report.issues.some(
      (issue) => issue.code === "candidate_count_mismatch" && issue.expected === 999
    )
  );
});
