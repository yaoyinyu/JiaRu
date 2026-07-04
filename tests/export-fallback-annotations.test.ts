import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import sharp from "sharp";
import {
  auditAnnotationDocument,
  parseSourceRecords,
} from "../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);
const REFERENCE_IMAGE = path.resolve("model/5188.jpg_wh860.jpg");

test("export fallback annotations script produces valid initial annotation json", async (t) => {
  if (!existsSync(REFERENCE_IMAGE)) {
    t.skip("reference image is not available");
    return;
  }

  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-fallback-export-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/export-fallback-annotations.ts",
      "--copy-image",
      "--source-group",
      "reference-image-seeds",
      REFERENCE_IMAGE,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const summary = JSON.parse(stdout) as {
    exported: number;
    sourcesCsvPath: string;
    outputs: Array<{
      outputJson: string;
      copiedImage?: string;
      polygonCount: number;
      sourceGroup: string;
      originType: string;
    }>;
  };
  assert.equal(summary.exported, 1);
  assert.equal(summary.outputs.length, 1);
  assert.ok(summary.outputs[0].polygonCount >= 4);
  assert.ok(summary.outputs[0].copiedImage);
  assert.equal(summary.outputs[0].sourceGroup, "reference-image-seeds");
  assert.equal(summary.outputs[0].originType, "reference");

  const annotation = JSON.parse(
    await readFile(summary.outputs[0].outputJson, "utf8")
  ) as Parameters<typeof auditAnnotationDocument>[0];
  const audit = auditAnnotationDocument(annotation);
  assert.equal(audit.ok, true);
  assert.equal(annotation.image.sourceGroup, "reference-image-seeds");
  assert.equal(annotation.image.negative, false);

  const sources = parseSourceRecords(
    await readFile(summary.sourcesCsvPath, "utf8")
  );
  assert.equal(sources.length, 1);
  assert.equal(sources[0].fileName, "5188.jpg_wh860.jpg");
  assert.equal(sources[0].originType, "reference");
  assert.equal(sources[0].annotationCount, annotation.annotations.length);
});

test("export fallback annotations can create reviewed negative samples without polygons", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-negative-export-"));
  const imageRoot = await mkdtemp(path.join(os.tmpdir(), "nail-negative-image-"));
  await mkdir(path.join(datasetRoot, "annotations", "raw-json"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });

  const imagePath = path.join(imageRoot, "plain-background.png");
  await sharp({
    create: {
      width: 96,
      height: 96,
      channels: 3,
      background: { r: 25, g: 28, b: 32 },
    },
  })
    .png()
    .toFile(imagePath);

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/export-fallback-annotations.ts",
      "--copy-image",
      "--negative",
      "--source-group",
      "negative-batch",
      "--origin-type",
      "negative",
      "--origin-ref",
      "generated no-nail test image",
      "--license",
      "internal-test",
      "--notes",
      "sample=negative; reason=negative_sample",
      imagePath,
    ],
    {
      cwd: path.resolve("."),
      env: {
        ...process.env,
        DATASET_ROOT: datasetRoot,
      },
    }
  );

  const summary = JSON.parse(stdout) as {
    sourcesCsvPath: string;
    outputs: Array<{
      outputJson: string;
      polygonCount: number;
      originType: string;
    }>;
  };
  assert.equal(summary.outputs[0].polygonCount, 0);
  assert.equal(summary.outputs[0].originType, "negative");

  const annotation = JSON.parse(
    await readFile(summary.outputs[0].outputJson, "utf8")
  ) as Parameters<typeof auditAnnotationDocument>[0];
  const audit = auditAnnotationDocument(annotation);
  assert.equal(audit.ok, true);
  assert.equal(annotation.image.negative, true);
  assert.deepEqual(annotation.annotations, []);

  const sources = parseSourceRecords(
    await readFile(summary.sourcesCsvPath, "utf8")
  );
  assert.equal(sources[0].negative, true);
  assert.equal(sources[0].originType, "negative");
  assert.equal(sources[0].annotationCount, 0);
});
