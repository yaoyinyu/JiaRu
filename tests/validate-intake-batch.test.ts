import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";
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

test("validate-intake-batch script reports missing and unlisted files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-intake-batch-"));
  const imageDir = path.join(root, "images");
  await mkdir(imageDir, { recursive: true });
  await writeFile(path.join(imageDir, "sample-001.jpg"), "x");
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
