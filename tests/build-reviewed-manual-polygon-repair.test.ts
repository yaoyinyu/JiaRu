import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/build-reviewed-manual-polygon-repair.py");

function fixture(overlap = false) {
  const root = mkdtempSync(path.join(tmpdir(), "manual-polygon-repair-"));
  const imageDir = path.join(root, "images");
  const annotationDir = path.join(root, "annotations");
  const overlayDir = path.join(root, "overlays");
  mkdirSync(imageDir);
  execFileSync("python", [
    "-c",
    "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1])",
    path.join(imageDir, "sample.png"),
  ]);
  const sourcePath = path.join(root, "source.json");
  writeFileSync(
    sourcePath,
    JSON.stringify({
      version: "nail-texture-dataset/v1",
      image: { id: "sample", fileName: "sample.png", width: 100, height: 100, sourceGroup: "group-1", negative: false },
      annotations: [{ id: "n1", label: "nail_texture", polygon: [{ x: 10, y: 10 }, { x: 30, y: 10 }, { x: 30, y: 30 }, { x: 10, y: 30 }], attributes: {} }],
    }),
  );
  const manifestPath = path.join(root, "manifest.json");
  writeFileSync(
    manifestPath,
    JSON.stringify({
      images: [{
        fileName: "sample.png",
        sourceAnnotationPath: sourcePath,
        sourceGroup: "group-1",
        nails: [
          { sourceIndex: 1 },
          { polygon: overlap
            ? [{ x: 20, y: 20 }, { x: 40, y: 20 }, { x: 40, y: 40 }, { x: 20, y: 40 }]
            : [{ x: 60, y: 60 }, { x: 90, y: 60 }, { x: 90, y: 90 }, { x: 60, y: 90 }] },
        ],
      }],
    }),
  );
  return { root, imageDir, annotationDir, overlayDir, manifestPath, reportPath: path.join(root, "report.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [script, "--manifest", item.manifestPath, "--image-dir", item.imageDir, "--output-annotations", item.annotationDir, "--overlay-dir", item.overlayDir, "--report", item.reportPath];
}

test("reviewed manual polygon repair retains good masks and validates manual replacements", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.reportPath, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.polygonCount, 2);
  assert.equal(report.retainedPolygonCount, 1);
  assert.equal(report.manualPolygonCount, 1);
  assert.equal(report.pairwiseOverlapCount, 0);
  const annotation = JSON.parse(readFileSync(path.join(item.annotationDir, "sample.json"), "utf8"));
  assert.equal(annotation.annotations.length, 2);
  assert.equal(annotation.annotations[1].attributes.annotationMethod, "codex-original-resolution-manual");
});

test("reviewed manual polygon repair rejects overlapping nail polygons", () => {
  const item = fixture(true);
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.reportPath, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /overlap/);
});
