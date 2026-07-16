import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

const script = path.resolve("model/training/repair-reviewed-annotation-topology.py");

function fixture(maximumOverlapPixels = 1000) {
  const root = mkdtempSync(path.join(tmpdir(), "repair-reviewed-topology-"));
  const coreImages = path.join(root, "core-images");
  const stressImages = path.join(root, "stress-images");
  const coreAnnotations = path.join(root, "core-annotations");
  const stressAnnotations = path.join(root, "stress-annotations");
  const outputAnnotations = path.join(root, "output-annotations");
  const overlays = path.join(root, "overlays");
  const crops = path.join(root, "crops");
  for (const dir of [coreImages, stressImages, coreAnnotations, stressAnnotations]) mkdirSync(dir);
  execFileSync("python", ["-c", "from PIL import Image; import sys; Image.new('RGB',(100,100),'white').save(sys.argv[1])", path.join(coreImages, "sample.png")]);
  writeFileSync(path.join(coreAnnotations, "sample.json"), JSON.stringify({
    version: "nail-texture-dataset/v1",
    image: { id: "sample", fileName: "sample.png", width: 100, height: 100, sourceGroup: "group", negative: false },
    annotations: [
      { id: "n1", label: "nail_texture", polygon: [{ x: 10, y: 10 }, { x: 50, y: 10 }, { x: 50, y: 50 }, { x: 10, y: 50 }, { x: 10, y: 10 }, { x: 20, y: 20 }, { x: 10, y: 10 }], attributes: {} },
      { id: "n2", label: "nail_texture", polygon: [{ x: 30, y: 20 }, { x: 70, y: 20 }, { x: 70, y: 60 }, { x: 30, y: 60 }], attributes: {} },
    ],
  }));
  const manifest = path.join(root, "manifest.json");
  writeFileSync(manifest, JSON.stringify({ images: [{
    lane: "core",
    fileName: "sample.png",
    repairTopologyIndices: [1],
    maximumDiscardedAreaRatio: 0.51,
    overlapRepairs: [{ backgroundIndex: 1, foregroundIndex: 2, maximumOverlapPixels, maximumAreaLossRatio: 0.8, marginPixels: 0.25 }],
  }] }));
  return { root, coreImages, stressImages, coreAnnotations, stressAnnotations, outputAnnotations, overlays, crops, manifest, report: path.join(root, "report.json") };
}

function args(item: ReturnType<typeof fixture>) {
  return [script, "--manifest", item.manifest, "--core-image-dir", item.coreImages, "--stress-image-dir", item.stressImages, "--core-annotations", item.coreAnnotations, "--stress-annotations", item.stressAnnotations, "--output-annotations", item.outputAnnotations, "--overlay-dir", item.overlays, "--crop-dir", item.crops, "--report", item.report];
}

test("repairs only declared invalid topology and foreground overlap", () => {
  const item = fixture();
  execFileSync("python", args(item));
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  const annotation = JSON.parse(readFileSync(path.join(item.outputAnnotations, "sample.json"), "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.repairCount, 2);
  assert.equal(report.outputs[0].pairwiseOverlapCount, 0);
  assert.equal(annotation.annotations.length, 2);
});

test("rejects an overlap larger than the reviewed manifest limit", () => {
  const item = fixture(1);
  const result = spawnSync("python", args(item), { encoding: "utf8" });
  assert.notEqual(result.status, 0);
  const report = JSON.parse(readFileSync(item.report, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join("\n"), /outside/);
});
