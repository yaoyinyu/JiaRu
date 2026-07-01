import assert from "node:assert/strict";
import test from "node:test";
import {
  createLocalNailDebugSample,
  createNailDebugSampleFilename,
  toNailDebugSampleCandidate,
} from "../src/lib/nail-texture-debug-sample.ts";

test("toNailDebugSampleCandidate maps editable region to export shape", () => {
  const candidate = toNailDebugSampleCandidate({
    id: "n1",
    cx: 100,
    cy: 120,
    angle: 0.5,
    nl: 80,
    nw: 40,
    assignedFinger: 2,
    confidence: "high",
    mask: { width: 4, height: 4 },
    warnings: ["highlight_hotspots"],
    extractionDiagnostics: {
      quality: {
        ok: false,
        warnings: ["mask_crop_touches_edge"],
      },
      highlightRepair: {
        highlightPixels: 3,
        repairedPixels: 2,
        highlightRatio: 0.125,
      },
    },
  });

  assert.deepEqual(candidate, {
    id: "n1",
    cx: 100,
    cy: 120,
    angle: 0.5,
    length: 80,
    width: 40,
    assignedFinger: 2,
    confidence: "high",
    hasMask: true,
    warnings: ["highlight_hotspots"],
    extractionDiagnostics: {
      qualityWarnings: ["mask_crop_touches_edge"],
      qualityOk: false,
      highlightPixels: 3,
      repairedPixels: 2,
      highlightRatio: 0.125,
    },
  });
});

test("createLocalNailDebugSample falls back to fallback-v0 and preserves candidates", () => {
  const record = createLocalNailDebugSample({
    imageUrl: "blob:demo",
    imageWidth: 860,
    imageHeight: 573,
    detectionSummary: null,
    originalRegions: [
      {
        id: "a",
        cx: 10,
        cy: 20,
        angle: 0,
        nl: 30,
        nw: 12,
        assignedFinger: null,
      },
    ],
    correctedRegions: [
      {
        id: "a",
        cx: 11,
        cy: 21,
        angle: 0.1,
        nl: 32,
        nw: 13,
        assignedFinger: 1,
        confidence: "low",
      },
    ],
    createdAt: "2026-06-30T12:34:56.000Z",
  });

  assert.equal(record.backend, "fallback");
  assert.equal(record.modelVersion, "fallback-v0");
  assert.equal(record.imageId, "local-debug-2026-06-30T12-34-56.000Z");
  assert.deepEqual(record.image, {
    width: 860,
    height: 573,
  });
  assert.equal(record.originalCandidates.length, 1);
  assert.equal(record.correctedCandidates[0].assignedFinger, 1);
  assert.deepEqual(record.correctedCandidates[0].warnings, []);
  assert.equal(createNailDebugSampleFilename(record), "local-debug-2026-06-30T12-34-56.000Z.json");
});
