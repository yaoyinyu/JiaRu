import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

test("reviewed region audit accepts parent-stable groups and rejects mismatches", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-region-review-"));
  const imagesDir = path.join(root, "images");
  const annotationsDir = path.join(root, "annotations");
  await mkdir(imagesDir);
  await mkdir(annotationsDir);
  const imageBytes = Buffer.from("derived-image-fixture");
  await writeFile(path.join(imagesDir, "crop.png"), imageBytes);
  const imageSha = createHash("sha256").update(imageBytes).digest("hex");
  await writeFile(
    path.join(root, "regions.json"),
    JSON.stringify({
      version: "nail-texture-region-extraction/v1",
      outputDir: imagesDir,
      outputs: [{
        outputFileName: "crop.png",
        outputSha256: imageSha,
        outputSize: { width: 100, height: 80 },
        sourceGroup: "parent-stable:one",
        reviewRequired: true,
      }],
    }),
    "utf8"
  );
  const annotationPath = path.join(annotationsDir, "crop.json");
  const annotation = {
    version: "nail-texture-dataset/v1",
    image: {
      fileName: "crop.png",
      width: 100,
      height: 80,
      sourceGroup: "parent-stable:one",
      negative: false,
    },
    annotations: [{
      id: "n1",
      label: "nail_texture",
      polygon: [{ x: 10, y: 10 }, { x: 30, y: 10 }, { x: 30, y: 30 }, { x: 10, y: 30 }],
    }],
  };
  await writeFile(annotationPath, JSON.stringify(annotation), "utf8");
  const manifestPath = path.join(root, "review.json");
  await writeFile(
    manifestPath,
    JSON.stringify({
      version: "nail-texture-region-annotation-review/v1",
      regionReport: "regions.json",
      reviewer: "fixture-reviewer",
      items: [{
        fileName: "crop.png",
        status: "pass",
        annotationPath: "annotations/crop.json",
        acceptedMaskCount: 1,
        reason: "original_resolution_overlay_pass",
      }],
    }),
    "utf8"
  );

  const run = async () => execFileAsync(process.execPath, [
    "--no-warnings",
    "--experimental-strip-types",
    "model/training/verify-reviewed-region-annotations.ts",
    "--manifest",
    manifestPath,
  ], { cwd: path.resolve(".") });

  const accepted = JSON.parse((await run()).stdout) as { ok: boolean; totals: { acceptedMasks: number } };
  assert.equal(accepted.ok, true);
  assert.equal(accepted.totals.acceptedMasks, 1);

  annotation.image.sourceGroup = "wrong-parent";
  await writeFile(annotationPath, JSON.stringify(annotation), "utf8");
  await assert.rejects(run, (error: Error & { stdout?: string }) => {
    const report = JSON.parse(error.stdout ?? "{}") as { errors?: string[] };
    assert.ok(report.errors?.some((message) => message.includes("sourceGroup")));
    return true;
  });

  assert.ok((await readFile(manifestPath, "utf8")).includes("original_resolution_overlay_pass"));
});
