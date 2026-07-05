import assert from "node:assert/strict";
import test from "node:test";
import { assessDebugSamplePriority } from "../src/lib/nail-texture-debug-priority.ts";
import type { NailDebugSampleRecord } from "../src/lib/nail-texture-debug-sample.ts";

function createRecord(overrides: Partial<NailDebugSampleRecord> = {}): NailDebugSampleRecord {
  return {
    imageId: "local-debug-001",
    imageUrl: "blob:demo",
    image: { width: 320, height: 200 },
    backend: "model",
    modelVersion: "nail-texture-seg-v2",
    modelBackend: "webgpu",
    elapsedMs: 120,
    warnings: [],
    originalCandidates: [],
    correctedCandidates: [],
    createdAt: "2026-07-03T00:00:00.000Z",
    ...overrides,
  };
}

test("assessDebugSamplePriority elevates low-confidence corrections and manual additions", () => {
  const assessment = assessDebugSamplePriority(
    createRecord({
      originalCandidates: [
        {
          id: "n1",
          cx: 100,
          cy: 80,
          angle: 0.1,
          length: 60,
          width: 24,
          assignedFinger: 1,
          confidence: "low",
          source: "model",
          hasMask: false,
          warnings: [],
        },
      ],
      correctedCandidates: [
        {
          id: "n1",
          cx: 112,
          cy: 92,
          angle: 0.1,
          length: 78,
          width: 30,
          assignedFinger: 1,
          confidence: "high",
          source: "model",
          hasMask: true,
          warnings: [],
        },
        {
          id: "n2",
          cx: 200,
          cy: 90,
          angle: 0.2,
          length: 62,
          width: 26,
          assignedFinger: 3,
          confidence: "high",
          source: "manual",
          hasMask: true,
          warnings: [],
        },
      ],
    })
  );

  assert.equal(assessment.priorityTier, "high");
  assert.equal(assessment.modelBackend, "webgpu");
  assert.equal(assessment.elapsedMs, 120);
  assert.ok(assessment.reasons.some((item) => item.code === "low_confidence_corrected"));
  assert.ok(assessment.reasons.some((item) => item.code === "manual_candidate_added"));
  assert.ok(assessment.reasons.some((item) => item.code === "large_geometry_adjustment"));
  assert.equal(assessment.summary.addedCandidates, 1);
  assert.equal(assessment.summary.manualAddedCandidates, 1);
  assert.equal(assessment.summary.lowConfidenceCorrections, 1);
});

test("assessDebugSamplePriority ignores non-manual added candidates for manual-add reason", () => {
  const assessment = assessDebugSamplePriority(
    createRecord({
      correctedCandidates: [
        {
          id: "n1",
          cx: 200,
          cy: 90,
          angle: 0.2,
          length: 62,
          width: 26,
          assignedFinger: 3,
          confidence: "high",
          source: "saliency",
          hasMask: true,
          warnings: [],
        },
      ],
    })
  );

  assert.equal(assessment.summary.addedCandidates, 1);
  assert.equal(assessment.summary.manualAddedCandidates, 0);
  assert.equal(
    assessment.reasons.some((item) => item.code === "manual_candidate_added"),
    false
  );
});

test("assessDebugSamplePriority surfaces fallback runtime and deletion risks", () => {
  const assessment = assessDebugSamplePriority(
    createRecord({
      backend: "fallback",
      modelVersion: "fallback-v0",
      modelBackend: "fallback",
      warnings: ["onnx_session_init_failed:webgpu"],
      originalCandidates: [
        {
          id: "n1",
          cx: 100,
          cy: 80,
          angle: 0.1,
          length: 60,
          width: 24,
          assignedFinger: 1,
          confidence: "high",
          source: "saliency",
          hasMask: true,
          warnings: ["highlight_hotspots"],
          extractionDiagnostics: {
            qualityWarnings: ["dirty_mask_crop"],
            qualityOk: false,
            highlightPixels: 6,
            repairedPixels: 4,
            highlightRatio: 0.2,
          },
        },
      ],
      correctedCandidates: [],
    })
  );

  assert.equal(assessment.priorityTier, "high");
  assert.ok(assessment.reasons.some((item) => item.code === "fallback_backend_used"));
  assert.ok(assessment.reasons.some((item) => item.code === "model_runtime_warning"));
  assert.ok(assessment.reasons.some((item) => item.code === "high_confidence_deleted"));
  assert.equal(assessment.summary.highConfidenceDeletions, 1);
});

test("assessDebugSamplePriority treats model manifest and inference failures as runtime warnings", () => {
  for (const warning of [
    "model_manifest_error:invalid_nail_texture_model_manifest",
    "model_inference_error:simulated_session_run_failure",
    "onnx_session_or_tensor_unavailable",
    "model_outputs_empty_used_fallback",
  ]) {
    const assessment = assessDebugSamplePriority(
      createRecord({
        warnings: [warning],
      })
    );

    assert.equal(assessment.priorityTier, "low");
    assert.equal(assessment.priorityScore, 2);
    assert.ok(assessment.reasons.some((item) => item.code === "model_runtime_warning"));
  }
});
test("assessDebugSamplePriority stays low when user barely changed a clean sample", () => {
  const assessment = assessDebugSamplePriority(
    createRecord({
      originalCandidates: [
        {
          id: "n1",
          cx: 100,
          cy: 80,
          angle: 0.1,
          length: 60,
          width: 24,
          assignedFinger: 1,
          confidence: "high",
          source: "model",
          hasMask: true,
          warnings: [],
        },
      ],
      correctedCandidates: [
        {
          id: "n1",
          cx: 101,
          cy: 81,
          angle: 0.1,
          length: 61,
          width: 24,
          assignedFinger: 1,
          confidence: "high",
          source: "model",
          hasMask: true,
          warnings: [],
        },
      ],
    })
  );

  assert.equal(assessment.priorityTier, "low");
  assert.equal(assessment.priorityScore, 0);
  assert.deepEqual(assessment.reasons, []);
});
