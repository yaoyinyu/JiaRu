import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

test("init-intake-batch creates a sorted manifest draft from image directory", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-init-intake-"));
  const imageDir = path.join(root, "batch");
  await mkdir(imageDir, { recursive: true });
  await writeFile(path.join(imageDir, "b.png"), "x");
  await writeFile(path.join(imageDir, "a.jpg"), "x");
  await writeFile(path.join(imageDir, "notes.txt"), "ignore");

  const manifestPath = path.join(root, "seed-batch-001.manifest.json");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/init-intake-batch.ts",
        "--image-dir",
        imageDir,
        "--output",
        manifestPath,
        "--source-group",
        "seed-batch-001",
        "--origin-type",
        "web",
        "--license",
        "internal-test-only",
        "--default-origin-ref",
        "manual web sourcing 2026-07-01",
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 0);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as {
    sourceGroup: string;
    originType: string;
    license: string;
    defaultOriginRef: string;
    copyImagesToDataset: boolean;
    items: Array<{ fileName: string; notes: string }>;
  };
  assert.equal(manifest.sourceGroup, "seed-batch-001");
  assert.equal(manifest.originType, "web");
  assert.equal(manifest.license, "internal-test-only");
  assert.equal(manifest.defaultOriginRef, "manual web sourcing 2026-07-01");
  assert.equal(manifest.copyImagesToDataset, true);
  assert.deepEqual(
    manifest.items.map((item) => item.fileName),
    ["a.jpg", "b.png"]
  );
});

test("init-intake-batch fails when image directory does not contain supported images", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-init-intake-empty-"));
  const imageDir = path.join(root, "batch");
  await mkdir(imageDir, { recursive: true });
  await writeFile(path.join(imageDir, "notes.txt"), "ignore");

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/init-intake-batch.ts",
        "--image-dir",
        imageDir,
        "--source-group",
        "seed-batch-001",
        "--origin-type",
        "web",
        "--license",
        "internal-test-only",
        "--default-origin-ref",
        "manual web sourcing 2026-07-01",
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
});
