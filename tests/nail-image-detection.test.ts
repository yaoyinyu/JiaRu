import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { recognizeNailTexturesWithFallback } from "../src/lib/nail-texture-recognition/index.ts";
import type { NailDetectionGroundTruthFixture } from "../src/lib/nail-detection-fixture.ts";
import { compareDetectedRegionsToFixture } from "../src/lib/nail-detection-fixture.ts";

const FIXTURE_PATH = path.resolve("model/fixtures/nail-detection-reference-5188.json");

test("reference nail-art image detection matches reusable fixture", async () => {
  const fixture = JSON.parse(
    await readFile(FIXTURE_PATH, "utf8")
  ) as NailDetectionGroundTruthFixture;

  const { default: sharp } = await import("sharp");
  const reference = await sharp(path.resolve(fixture.imagePath))
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const result = recognizeNailTexturesWithFallback({
    width: reference.info.width,
    height: reference.info.height,
    data: reference.data,
  });

  assert.equal(result.backend, "fallback");
  assert.equal(result.candidates.length, fixture.expected.candidateCount);

  const comparison = compareDetectedRegionsToFixture(result.candidates, fixture.truthRegions);
  assert.equal(comparison.matchedTruthCount, fixture.truthRegions.length);
  assert.ok(
    comparison.maxCenterError <= fixture.expected.maxCenterError,
    `max center error ${comparison.maxCenterError.toFixed(2)}px exceeded ${fixture.expected.maxCenterError}px`
  );
});
