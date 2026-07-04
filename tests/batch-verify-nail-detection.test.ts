import assert from "node:assert/strict";
import { cp, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

function runBatchVerify(args: string[], expectedExitCode: number = 0): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/batch-verify-nail-detection.ts",
        ...args,
      ],
      { cwd: process.cwd(), stdio: ["ignore", "pipe", "pipe"] }
    );

    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => {
      out += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      err += String(chunk);
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if ((code ?? 0) !== expectedExitCode) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });
}

test("batch-verify-nail-detection generates overlay artifacts and report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  await mkdir(imageDir, { recursive: true });
  await cp(
    path.resolve("model/5188.jpg_wh860.jpg"),
    path.join(imageDir, "sample-001.jpg")
  );

  const stdout = await runBatchVerify([
    "--image-dir",
    imageDir,
    "--output-dir",
    outputDir,
    "--prefix",
    "seed-batch-001",
  ]);

  const report = JSON.parse(stdout) as {
    ok: boolean;
    totalImages: number;
    successCount: number;
    failureCount: number;
    skippedAnnotationCount: number;
    reportPath: string;
    results: Array<{
      ok: boolean;
      count?: number;
      output?: string;
      candidateMaskOutput?: string;
      skinMaskOutput?: string;
      debugJsonOutput?: string;
    }>;
  };

  assert.equal(report.ok, true);
  assert.equal(report.totalImages, 1);
  assert.equal(report.successCount, 1);
  assert.equal(report.failureCount, 0);
  assert.equal(report.skippedAnnotationCount, 0);
  assert.equal(report.results[0]?.ok, true);
  assert.ok((report.results[0]?.count ?? 0) >= 4);

  const persisted = JSON.parse(await readFile(report.reportPath, "utf8")) as {
    ok: boolean;
    results: Array<{
      output?: string;
      candidateMaskOutput?: string;
      skinMaskOutput?: string;
      debugJsonOutput?: string;
    }>;
  };
  assert.equal(persisted.ok, true);

  for (const artifactPath of [
    persisted.results[0]?.output,
    persisted.results[0]?.candidateMaskOutput,
    persisted.results[0]?.skinMaskOutput,
    persisted.results[0]?.debugJsonOutput,
  ]) {
    assert.ok(artifactPath, "artifact path should exist in report");
    const content = await readFile(artifactPath!, artifactPath!.endsWith(".json") ? "utf8" : undefined);
    assert.ok(content);
  }
});

test("batch-verify-nail-detection matches fixtures from fixture directory by image stem", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-fixture-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  const fixtureDir = path.join(root, "fixtures");
  await mkdir(imageDir, { recursive: true });
  await mkdir(fixtureDir, { recursive: true });
  await cp(
    path.resolve("model/5188.jpg_wh860.jpg"),
    path.join(imageDir, "5188.jpg_wh860.jpg")
  );
  await cp(
    path.resolve("model/fixtures/nail-detection-reference-5188.json"),
    path.join(fixtureDir, "custom-5188-fixture.json")
  );

  const stdout = await runBatchVerify([
    "--image-dir",
    imageDir,
    "--output-dir",
    outputDir,
    "--prefix",
    "seed-batch-fixture",
    "--fixture-dir",
    fixtureDir,
  ]);

  const report = JSON.parse(stdout) as {
    ok: boolean;
    fixtureDir: string | null;
    matchedFixtureCount: number;
    skippedAnnotationCount: number;
    results: Array<{
      ok: boolean;
      fixturePath?: string | null;
      debugJsonOutput?: string;
    }>;
  };

  assert.equal(report.ok, true);
  assert.equal(report.fixtureDir, fixtureDir);
  assert.equal(report.matchedFixtureCount, 1);
  assert.equal(report.skippedAnnotationCount, 0);
  assert.equal(report.results[0]?.ok, true);
  assert.equal(
    report.results[0]?.fixturePath,
    path.join(fixtureDir, "custom-5188-fixture.json")
  );

  const debugPayload = JSON.parse(
    await readFile(report.results[0]!.debugJsonOutput!, "utf8")
  ) as { fixturePath?: string | null };
  assert.equal(
    debugPayload.fixturePath,
    path.join(fixtureDir, "custom-5188-fixture.json")
  );
});

test("batch-verify-nail-detection skips annotation images referenced by fixtures", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-annotation-skip-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  const fixtureDir = path.join(root, "fixtures");
  await mkdir(imageDir, { recursive: true });
  await mkdir(fixtureDir, { recursive: true });
  await cp(
    path.resolve("model/5188.jpg_wh860.jpg"),
    path.join(imageDir, "5188.jpg_wh860.jpg")
  );
  await cp(
    path.resolve("model/5188.jpg_wh860.png"),
    path.join(imageDir, "5188.jpg_wh860.png")
  );
  await cp(
    path.resolve("model/fixtures/nail-detection-reference-5188.json"),
    path.join(fixtureDir, "nail-detection-reference-5188.json")
  );

  const stdout = await runBatchVerify([
    "--image-dir",
    imageDir,
    "--output-dir",
    outputDir,
    "--prefix",
    "seed-batch-annotation-skip",
    "--fixture-dir",
    fixtureDir,
  ]);

  const report = JSON.parse(stdout) as {
    ok: boolean;
    totalImages: number;
    successCount: number;
    failureCount: number;
    matchedFixtureCount: number;
    skippedAnnotationCount: number;
    skippedAnnotationFiles: string[];
    results: Array<{ fileName: string; ok: boolean }>;
  };

  assert.equal(report.ok, true);
  assert.equal(report.totalImages, 1);
  assert.equal(report.successCount, 1);
  assert.equal(report.failureCount, 0);
  assert.equal(report.matchedFixtureCount, 1);
  assert.equal(report.skippedAnnotationCount, 1);
  assert.deepEqual(report.skippedAnnotationFiles, ["5188.jpg_wh860.png"]);
  assert.deepEqual(report.results.map((item) => item.fileName), ["5188.jpg_wh860.jpg"]);
  assert.equal(report.results[0]?.ok, true);
});

test("batch-verify-nail-detection fails when directory has no supported images", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-empty-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  await mkdir(imageDir, { recursive: true });
  await writeFile(path.join(imageDir, "notes.txt"), "ignore");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/batch-verify-nail-detection.ts",
        "--image-dir",
        imageDir,
        "--output-dir",
        outputDir,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
});

test("batch-verify-nail-detection skips generated debug artifacts and keeps unique outputs per extension", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-skip-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  await mkdir(imageDir, { recursive: true });
  await cp(
    path.resolve("model/5188.jpg_wh860.jpg"),
    path.join(imageDir, "same-name.jpg")
  );
  await cp(
    path.resolve("model/5188.jpg_wh860.png"),
    path.join(imageDir, "same-name.png")
  );
  await cp(
    path.resolve("model/nail-detection-debug.png"),
    path.join(imageDir, "ignore-detection-debug.png")
  );

  const stdout = await runBatchVerify(
    [
      "--image-dir",
      imageDir,
      "--output-dir",
      outputDir,
      "--prefix",
      "seed-batch-002",
    ],
    1
  );

  const report = JSON.parse(stdout) as {
    totalImages: number;
    failureCount: number;
    skippedAnnotationCount: number;
    results: Array<{ fileName: string; output?: string }>;
  };

  assert.equal(report.totalImages, 2);
  assert.equal(report.failureCount, 1);
  assert.equal(report.skippedAnnotationCount, 0);
  assert.deepEqual(
    report.results.map((item) => item.fileName),
    ["same-name.jpg", "same-name.png"]
  );
  assert.notEqual(report.results[0]?.output, report.results[1]?.output);
});
