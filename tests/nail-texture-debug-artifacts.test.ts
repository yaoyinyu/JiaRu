import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { buildNailDebugArtifactPaths } from "../src/lib/nail-texture-recognition/index.ts";

test("buildNailDebugArtifactPaths keeps default output directory and names", () => {
  const paths = buildNailDebugArtifactPaths({
    inputPath: path.resolve("model/5188.jpg_wh860.jpg"),
  });

  assert.match(paths.output, /nail-5188\.jpg_wh860-detection-debug\.png$/);
  assert.match(paths.debugJsonOutput, /nail-5188\.jpg_wh860-detection-debug\.json$/);
  assert.match(paths.modelOutputDumpPath, /nail-5188\.jpg_wh860-model-output-dump\.json$/);
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
