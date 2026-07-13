import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

test("reviewed region intake inherits authorization and preserves parent-stable groups", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-region-intake-"));
  const imagesDir = path.join(root, "regions");
  const annotationsDir = path.join(root, "annotations");
  const outputRoot = path.join(root, "output");
  await mkdir(imagesDir);
  await mkdir(annotationsDir);
  await writeFile(path.join(imagesDir, "crop.png"), "image", "utf8");
  await writeFile(path.join(annotationsDir, "crop.json"), "{}", "utf8");
  await writeFile(
    path.join(root, "regions.json"),
    JSON.stringify({
      version: "nail-texture-region-extraction/v1",
      outputDir: imagesDir,
      outputs: [{
        parentFileName: "parent.jpg",
        parentSha256: "abc123",
        regionId: "main-hand",
        normalizedBox: [0.1, 0.2, 0.8, 0.9],
        outputFileName: "crop.png",
        sourceGroup: "parent-stable:abc",
      }],
    }),
    "utf8"
  );
  const reviewPath = path.join(root, "review.json");
  await writeFile(
    reviewPath,
    JSON.stringify({
      version: "nail-texture-region-annotation-review/v1",
      regionReport: "regions.json",
      items: [{
        fileName: "crop.png",
        status: "pass",
        annotationPath: "annotations/crop.json",
        acceptedMaskCount: 4,
        reason: "overlay_pass",
      }],
    }),
    "utf8"
  );
  const sourceManifestPath = path.join(root, "source.manifest.json");
  await writeFile(
    sourceManifestPath,
    JSON.stringify({
      version: "nail-texture-intake-batch/v1",
      sourceGroup: "authorized-source",
      originType: "reference",
      license: "user-authorized-commercial-training-and-long-term-regression",
      defaultOriginRef: "user folder",
      copyImagesToDataset: true,
      items: [{ fileName: "parent.jpg" }],
    }),
    "utf8"
  );

  const { stdout } = await execFileAsync(process.execPath, [
    "--no-warnings",
    "--experimental-strip-types",
    "model/training/build-reviewed-region-intake-batch.ts",
    "--review-manifest",
    reviewPath,
    "--source-manifest",
    sourceManifestPath,
    "--output-root",
    outputRoot,
  ], { cwd: path.resolve(".") });
  const report = JSON.parse(stdout) as {
    acceptedCount: number;
    acceptedMaskCount: number;
    manifestPath: string;
    inheritedLicense: string;
  };
  assert.equal(report.acceptedCount, 1);
  assert.equal(report.acceptedMaskCount, 4);
  assert.equal(report.inheritedLicense, "user-authorized-commercial-training-and-long-term-regression");
  const manifest = JSON.parse(await readFile(report.manifestPath, "utf8")) as {
    license: string;
    items: Array<{ fileName: string; sourceGroup: string; originRef: string; notes: string }>;
  };
  assert.equal(manifest.items[0].sourceGroup, "parent-stable:abc");
  assert.match(manifest.items[0].originRef, /parentSha256=abc123/);
  assert.match(manifest.items[0].notes, /authorizationInheritedFrom=source\.manifest\.json/);
  await access(path.join(outputRoot, "selected", "images", "crop.png"));
  await access(path.join(outputRoot, "selected", "annotations", "raw-json", "crop.json"));
});
