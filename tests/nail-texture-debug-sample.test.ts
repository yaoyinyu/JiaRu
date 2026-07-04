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
    confidence: "medium",
    source: "model",
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
    confidence: "medium",
    source: "model",
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

test("createLocalNailDebugSample preserves source and runtime summary metadata", () => {
  const record = createLocalNailDebugSample({
    imageUrl: "blob:demo",
    imageWidth: 860,
    imageHeight: 573,
    detectionSummary: {
      backend: "model",
      modelVersion: "nail-texture-seg-v2",
      modelBackend: "webgpu",
      elapsedMs: 184.2,
      workerElapsedMs: 150.5,
      warnings: ["candidate_count_capped"],
    },
    originalRegions: [
      {
        id: "a",
        cx: 10,
        cy: 20,
        angle: 0,
        nl: 30,
        nw: 12,
        assignedFinger: null,
        confidence: "low",
        source: "saliency",
      },
    ],
    correctedRegions: [
      {
        id: "b",
        cx: 11,
        cy: 21,
        angle: 0.1,
        nl: 32,
        nw: 13,
        assignedFinger: 1,
        confidence: "medium",
        source: "manual",
      },
    ],
    createdAt: "2026-06-30T12:34:56.000Z",
  });

  assert.equal(record.backend, "model");
  assert.equal(record.modelVersion, "nail-texture-seg-v2");
  assert.equal(record.modelBackend, "webgpu");
  assert.equal(record.elapsedMs, 184.2);
  assert.equal(record.workerElapsedMs, 150.5);
  assert.deepEqual(record.warnings, ["candidate_count_capped"]);
  assert.equal(record.imageId, "local-debug-2026-06-30T12-34-56.000Z");
  assert.deepEqual(record.image, {
    width: 860,
    height: 573,
  });
  assert.equal(record.originalCandidates[0].source, "saliency");
  assert.equal(record.correctedCandidates[0].source, "manual");
  assert.equal(record.correctedCandidates[0].confidence, "medium");
  assert.equal(createNailDebugSampleFilename(record), "local-debug-2026-06-30T12-34-56.000Z.json");
});

test("createLocalNailDebugSample defaults missing region source to manual and fallback metadata", () => {
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
    correctedRegions: [],
    createdAt: "2026-06-30T12:34:56.000Z",
  });

  assert.equal(record.backend, "fallback");
  assert.equal(record.modelVersion, "fallback-v0");
  assert.equal(record.elapsedMs, 0);
  assert.equal(record.originalCandidates[0].source, "manual");
});
