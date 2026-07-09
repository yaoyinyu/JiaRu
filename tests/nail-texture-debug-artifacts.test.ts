import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import {
  buildNailDebugArtifactPaths,
  buildNailRecognitionMaskOverlay,
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
test("buildNailRecognitionMaskOverlay maps candidate masks back to original pixels", () => {
  const overlay = buildNailRecognitionMaskOverlay({
    width: 8,
    height: 8,
    candidates: [
      {
        mask: {
          width: 4,
          height: 4,
          data: new Uint8Array([
            0, 0, 0, 0,
            0, 1, 1, 0,
            0, 1, 0, 0,
            0, 0, 0, 0,
          ]),
          originX: 0,
          originY: 0,
          scale: 2,
        },
      },
      {},
    ],
    preprocess: {
      inputSize: 8,
      originalWidth: 8,
      originalHeight: 8,
      scaleX: 1,
      scaleY: 1,
    },
  });

  assert.equal(overlay.width, 8);
  assert.equal(overlay.height, 8);
  assert.equal(overlay.maskCandidateCount, 1);
  assert.equal(overlay.coveredPixels, 3);
  assert.equal(overlay.data[(3 * 8 + 3) * 4 + 3], 150);
  assert.equal(overlay.data[(5 * 8 + 3) * 4 + 3], 150);
  assert.equal(overlay.data[(0 * 8 + 0) * 4 + 3], 0);
});
