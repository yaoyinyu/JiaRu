import assert from "node:assert/strict";
import { cp, mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("batch-verify-nail-detection generates overlay artifacts and report", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-batch-verify-"));
  const imageDir = path.join(root, "images");
  const outputDir = path.join(root, "output");
  await mkdir(imageDir, { recursive: true });
  await cp(
    path.resolve("model/5188.jpg_wh860.jpg"),
    path.join(imageDir, "sample-001.jpg")
  );

  const stdout = await new Promise<string>((resolve, reject) => {
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
        "--prefix",
        "seed-batch-001",
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
      if ((code ?? 0) !== 0) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    ok: boolean;
    totalImages: number;
    successCount: number;
    failureCount: number;
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

  const stdout = await new Promise<string>((resolve, reject) => {
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
        "--prefix",
        "seed-batch-002",
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
      if ((code ?? 0) !== 1) {
        reject(new Error(err || `unexpected exit code: ${code}`));
        return;
      }
      resolve(out);
    });
  });

  const report = JSON.parse(stdout) as {
    totalImages: number;
    failureCount: number;
    results: Array<{ fileName: string; output?: string }>;
  };

  assert.equal(report.totalImages, 2);
  assert.equal(report.failureCount, 1);
  assert.deepEqual(
    report.results.map((item) => item.fileName),
    ["same-name.jpg", "same-name.png"]
  );
  assert.notEqual(report.results[0]?.output, report.results[1]?.output);
});
