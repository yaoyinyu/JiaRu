import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import {
  buildNailDebugArtifactPaths,
} from "../src/lib/nail-texture-recognition/index.ts";

test("buildNailDebugArtifactPaths keeps default output directory and names", () => {
  const paths = buildNailDebugArtifactPaths({
    inputPath: path.resolve("model/5188.jpg_wh860.jpg"),
  });

  assert.match(paths.output, /nail-5188\.jpg_wh860-detection-debug\.png$/);
  assert.match(paths.debugJsonOutput, /nail-5188\.jpg_wh860-detection-debug\.json$/);
  assert.match(paths.modelOutputDumpPath, /nail-5188\.jpg_wh860-model-output-dump\.json$/);
  assert.match(paths.recognitionMaskOutput, /nail-5188\.jpg_wh860-recognition-mask-overlay\.png$/);
});

test("buildNailDebugArtifactPaths supports custom output directory and prefix", () => {
  const paths = buildNailDebugArtifactPaths({
    inputPath: "C:/images/source image.jpg",
    outputDir: "C:/archives/run-001",
    prefix: "model-v1 session",
  });

  assert.equal(
    paths.output,
    path.resolve("C:/archives/run-001/model-v1-session-source-image-detection-debug.png")
  );
  assert.equal(
    paths.candidateMaskOutput,
    path.resolve("C:/archives/run-001/model-v1-session-source-image-candidate-mask.png")
  );
});
test("buildNailDebugArtifactPaths bounds long and non-ASCII path segments", () => {
  const paths = buildNailDebugArtifactPaths({
    inputPath: `C:/images/${"超长中文美甲素材名称".repeat(12)}.jpg`,
    outputDir: "C:/archives/run-001",
    prefix: "real-reference-2026-07-12-batch-02-128b70cc4121",
  });

  assert.ok(path.basename(paths.output).length < 110);
  assert.match(path.basename(paths.output), /-[a-f0-9]{12}-detection-debug\.png$/);
  assert.ok(paths.output.length < 260);
});
