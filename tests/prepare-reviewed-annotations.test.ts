import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile, cp } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("prepare-reviewed-annotations writes initial annotation jsons and prep report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-prepare-reviewed-"));
  const reviewDir = path.join(root, "review");
  const selectedImagesDir = path.join(root, "selected", "images");
  await mkdir(reviewDir, { recursive: true });
  await mkdir(selectedImagesDir, { recursive: true });

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

  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/prepare-reviewed-annotations.ts",
        "--root-dir",
        root,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => (out += String(chunk)));
    child.stderr.on("data", (chunk) => (err += String(chunk)));
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== 0) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    preparedCount: number;
    totalPolygons: number;
    manualFixCount: number;
    reportPath: string;
    outputs: Array<{ annotationPath: string; polygonCount: number; targetSplitHint: string }>;
  };

  assert.equal(report.preparedCount, 2);
  assert.ok(report.totalPolygons >= 7);
  assert.equal(report.manualFixCount, 1);
  assert.equal(report.outputs[0]?.targetSplitHint, "train");
  assert.equal(report.outputs[1]?.targetSplitHint, "test");

  const annotation = JSON.parse(
    await readFile(report.outputs[0]!.annotationPath, "utf8")
  ) as { annotations: unknown[] };
  assert.ok(annotation.annotations.length >= 4);

  const persisted = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    preparedCount: number;
  };
  assert.equal(persisted.preparedCount, 2);
});
