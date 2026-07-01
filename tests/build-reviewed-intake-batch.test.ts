import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("build-reviewed-intake-batch copies kept images and writes reviewed manifest", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-batch-"));
  const batchRoot = path.join(root, "seed-batch-001");
  const imagesDir = path.join(batchRoot, "images");
  const reviewDir = path.join(batchRoot, "review");
  await mkdir(imagesDir, { recursive: true });
  await mkdir(reviewDir, { recursive: true });

  await writeFile(path.join(imagesDir, "keep.jpg"), "a");
  await writeFile(path.join(imagesDir, "test.jpg"), "b");
  await writeFile(path.join(imagesDir, "drop.jpg"), "c");

  await writeFile(
    path.join(batchRoot, "seed-batch-001.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-001",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [],
      },
      null,
      2
    ),
    "utf8"
  );

  await writeFile(
    path.join(reviewDir, "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "keep.jpg,true,keep,good_detection,4,true,train,reference,light,red,highlight|gold_line,ready for fix",
      "test.jpg,false,reserve_for_test,complex_background,3,false,test,reference,dark,black,glitter,hold for eval",
      "drop.jpg,false,drop,low_resolution,1,false,,reference,light,nude,,bad image",
      "",
    ].join("\n"),
    "utf8"
  );

  const outputDir = path.join(batchRoot, "selected");
  const stdout = await new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/build-reviewed-intake-batch.ts",
        "--root-dir",
        batchRoot,
        "--output-dir",
        outputDir,
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
    ok: boolean;
    copiedCount: number;
    droppedCount: number;
    outputManifestPath: string;
  };
  assert.equal(report.ok, true);
  assert.equal(report.copiedCount, 2);
  assert.equal(report.droppedCount, 1);

  const manifest = JSON.parse(await readFile(report.outputManifestPath, "utf8")) as {
    items: Array<{ fileName: string; notes: string }>;
  };
  assert.deepEqual(
    manifest.items.map((item) => item.fileName),
    ["keep.jpg", "test.jpg"]
  );
  assert.match(manifest.items[0]?.notes ?? "", /decision=keep/);
  assert.match(manifest.items[1]?.notes ?? "", /split=test/);
});

test("build-reviewed-intake-batch fails when selected file is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-reviewed-batch-missing-"));
  const batchRoot = path.join(root, "seed-batch-002");
  const imagesDir = path.join(batchRoot, "images");
  const reviewDir = path.join(batchRoot, "review");
  await mkdir(imagesDir, { recursive: true });
  await mkdir(reviewDir, { recursive: true });

  await writeFile(
    path.join(batchRoot, "seed-batch-002.manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-intake-batch/v1",
        sourceGroup: "seed-batch-002",
        originType: "web",
        license: "internal-test-only",
        defaultOriginRef: "manual web sourcing 2026-07-01",
        copyImagesToDataset: true,
        items: [],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(
    path.join(reviewDir, "screening-review.csv"),
    [
      "fileName,keepForTraining,decision,reasonCode,candidateCount,needsManualFix,targetSplitHint,sampleKind,backgroundTone,colorFamily,effectTags,notes",
      "missing.jpg,true,keep,good_detection,4,false,train,reference,light,red,highlight,missing file",
      "",
    ].join("\n"),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/build-reviewed-intake-batch.ts",
        "--root-dir",
        batchRoot,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
});
