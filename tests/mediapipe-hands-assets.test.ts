import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import {
  MEDIAPIPE_HANDS_ASSET_BASE_PATH,
  resolveMediaPipeHandsAsset,
} from "../src/lib/mediapipe-hands-assets.ts";

const requiredAssets = [
  "hands.js",
  "hands.binarypb",
  "hand_landmark_full.tflite",
  "hand_landmark_lite.tflite",
  "hands_solution_packed_assets_loader.js",
  "hands_solution_packed_assets.data",
  "hands_solution_simd_wasm_bin.js",
  "hands_solution_simd_wasm_bin.wasm",
  "hands_solution_wasm_bin.js",
  "hands_solution_wasm_bin.wasm",
] as const;

test("MediaPipe Hands browser runtime is self-hosted under public", async () => {
  assert.equal(MEDIAPIPE_HANDS_ASSET_BASE_PATH, "/vendor/mediapipe/hands");

  for (const fileName of requiredAssets) {
    assert.equal(
      resolveMediaPipeHandsAsset(fileName),
      `/vendor/mediapipe/hands/${fileName}`
    );
    const asset = await stat(path.resolve("public/vendor/mediapipe/hands", fileName));
    assert.ok(asset.isFile(), `${fileName} must be a file`);
    assert.ok(asset.size > 0, `${fileName} must not be empty`);
  }
});

test("static image detection and live AR do not depend on a MediaPipe CDN", async () => {
  const [detectorSource, arSource] = await Promise.all([
    readFile(path.resolve("src/lib/nail-hand-geometry-detection.ts"), "utf8"),
    readFile(path.resolve("src/components/ArView.tsx"), "utf8"),
  ]);

  for (const source of [detectorSource, arSource]) {
    assert.doesNotMatch(source, /cdn\.jsdelivr\.net.*mediapipe\/hands/);
    assert.match(source, /resolveMediaPipeHandsAsset/);
  }
});
