import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import sharp from "sharp";
import {
  validateIntakeBatchManifest,
  type NailTextureIntakeBatchManifest,
} from "../src/lib/nail-texture-dataset.ts";

function sampleManifest(
  overrides: Partial<NailTextureIntakeBatchManifest> = {}
): NailTextureIntakeBatchManifest {
  return {
    version: "nail-texture-intake-batch/v1",
    sourceGroup: "seed-batch-001",
    originType: "reference",
    license: "internal-test-only",
    defaultOriginRef: "desktop export",
    copyImagesToDataset: true,
    items: [
      { fileName: "sample-001.jpg" },
      { fileName: "sample-002.jpg", notes: "dark background" },
    ],
    ...overrides,
  };
}

test("validateIntakeBatchManifest accepts a valid batch manifest", () => {
  const result = validateIntakeBatchManifest(sampleManifest());
  assert.equal(result.ok, true);
  assert.deepEqual(result.issues, []);
});

test("validateIntakeBatchManifest rejects duplicate and missing file names", () => {
  const result = validateIntakeBatchManifest(
    sampleManifest({
      sourceGroup: "",
      items: [
        { fileName: "" },
        { fileName: "dup.jpg" },
        { fileName: "dup.jpg" },
      ],
    })
  );
  assert.equal(result.ok, false);
  assert.ok(result.issues.some((issue) => issue.code === "missing_source_group"));
  assert.ok(result.issues.some((issue) => issue.code === "missing_file_name"));
  assert.ok(result.issues.some((issue) => issue.code === "duplicate_file_name"));
});

test("validateIntakeBatchManifest accepts per-item groups and rejects blank overrides", () => {
  assert.equal(
    validateIntakeBatchManifest(
      sampleManifest({ items: [{ fileName: "derived.png", sourceGroup: "parent-stable:one" }] })
    ).ok,
    true
  );
  const rejected = validateIntakeBatchManifest(
    sampleManifest({ items: [{ fileName: "derived.png", sourceGroup: "  " }] })
  );
  assert.equal(rejected.ok, false);
  assert.ok(rejected.issues.some((issue) => issue.code === "invalid_item_source_group"));
});

test("validate-intake-batch script reports missing and unlisted files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-intake-batch-"));
  const imageDir = path.join(root, "images");
  await mkdir(imageDir, { recursive: true });
  await sharp({ create: { width: 16, height: 16, channels: 3, background: { r: 240, g: 210, b: 220 } } })
    .jpeg()
    .toFile(path.join(imageDir, "sample-001.jpg"));
  await writeFile(path.join(imageDir, "extra.jpg"), "x");

  const manifestPath = path.join(root, "batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      sampleManifest({
        items: [{ fileName: "sample-001.jpg" }, { fileName: "missing.jpg" }],
      }),
      null,
      2
    ),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/validate-intake-batch.ts",
        "--manifest",
        manifestPath,
        "--image-dir",
        imageDir,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(root, "batch.report.json"), "utf8")
  ) as {
    ok: boolean;
    missingFiles: string[];
    unlistedFiles: string[];
    issues: Array<{ code: string }>;
  };
  assert.equal(report.ok, false);
  assert.deepEqual(report.missingFiles, ["missing.jpg"]);
  assert.deepEqual(report.unlistedFiles, ["extra.jpg"]);
  assert.ok(report.issues.some((issue) => issue.code === "missing_image_file"));
  assert.ok(report.issues.some((issue) => issue.code === "unlisted_image_file"));
});

test("validate-intake-batch script accepts recursive relative manifest paths", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-intake-batch-recursive-"));
  const imageDir = path.join(root, "images");
  await mkdir(path.join(imageDir, "claude", "2026_7_4"), { recursive: true });
  await mkdir(path.join(imageDir, "worker", "2026_7_4"), { recursive: true });
  await sharp({ create: { width: 16, height: 16, channels: 3, background: { r: 240, g: 210, b: 220 } } })
    .png()
    .toFile(path.join(imageDir, "claude", "2026_7_4", "nail-001.png"));
  await sharp({ create: { width: 20, height: 18, channels: 3, background: { r: 80, g: 30, b: 70 } } })
    .jpeg()
    .toFile(path.join(imageDir, "worker", "2026_7_4", "nail-002.jpg"));

  const manifestPath = path.join(root, "batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      sampleManifest({
        items: [
          { fileName: "claude/2026_7_4/nail-001.png" },
          { fileName: "worker/2026_7_4/nail-002.jpg" },
        ],
      }),
      null,
      2
    ),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/validate-intake-batch.ts",
        "--manifest",
        manifestPath,
        "--image-dir",
        imageDir,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 0);
  const report = JSON.parse(
    await readFile(path.join(root, "batch.report.json"), "utf8")
  ) as {
    ok: boolean;
    missingFiles: string[];
    imageChecks: Array<{ fileName: string; ok: boolean }>;
  };
  assert.equal(report.ok, true);
  assert.deepEqual(report.missingFiles, []);
  assert.deepEqual(
    report.imageChecks.map((check) => check.fileName).sort(),
    ["claude/2026_7_4/nail-001.png", "worker/2026_7_4/nail-002.jpg"]
  );
});

test("validate-intake-batch script rejects unsafe manifest paths", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-intake-batch-unsafe-"));
  const imageDir = path.join(root, "images");
  await mkdir(imageDir, { recursive: true });

  const manifestPath = path.join(root, "batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      sampleManifest({
        items: [{ fileName: "../outside.jpg" }],
      }),
      null,
      2
    ),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/validate-intake-batch.ts",
        "--manifest",
        manifestPath,
        "--image-dir",
        imageDir,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(root, "batch.report.json"), "utf8")
  ) as { ok: boolean; unsafeFiles: string[]; issues: Array<{ code: string }> };
  assert.equal(report.ok, false);
  assert.deepEqual(report.unsafeFiles, ["../outside.jpg"]);
  assert.ok(report.issues.some((issue) => issue.code === "unsafe_image_path"));
});

test("validate-intake-batch script rejects undecodable image files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-intake-batch-invalid-image-"));
  const imageDir = path.join(root, "images");
  await mkdir(imageDir, { recursive: true });
  await writeFile(path.join(imageDir, "broken.jpg"), "not an image", "utf8");

  const manifestPath = path.join(root, "batch.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      sampleManifest({
        items: [{ fileName: "broken.jpg" }],
      }),
      null,
      2
    ),
    "utf8"
  );

  const exitCode = await new Promise<number>((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/validate-intake-batch.ts",
        "--manifest",
        manifestPath,
        "--image-dir",
        imageDir,
      ],
      { cwd: process.cwd(), stdio: "ignore" }
    );
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 0));
  });

  assert.equal(exitCode, 1);
  const report = JSON.parse(
    await readFile(path.join(root, "batch.report.json"), "utf8")
  ) as {
    ok: boolean;
    invalidImageFiles: string[];
    imageChecks: Array<{ fileName: string; ok: boolean; error?: string }>;
    issues: Array<{ code: string; fileName?: string }>;
  };
  assert.equal(report.ok, false);
  assert.deepEqual(report.invalidImageFiles, ["broken.jpg"]);
  assert.equal(report.imageChecks[0]?.fileName, "broken.jpg");
  assert.equal(report.imageChecks[0]?.ok, false);
  assert.ok(report.imageChecks[0]?.error);
  assert.ok(report.issues.some((issue) => issue.code === "invalid_image_file"));
});
