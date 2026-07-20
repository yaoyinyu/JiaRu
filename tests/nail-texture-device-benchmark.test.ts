import assert from "node:assert/strict";
import test from "node:test";
import {
  buildNailTextureDeviceSession,
  type NailTextureDeviceBenchmarkSample,
} from "../src/lib/nail-texture-device-benchmark.ts";

function samples(count = 20, overrides: Partial<NailTextureDeviceBenchmarkSample> = {}) {
  return Array.from({ length: count }, (_, index): NailTextureDeviceBenchmarkSample => ({
    iteration: index + 1,
    recordedAt: new Date(1_700_000_000_000 + index * 1000).toISOString(),
    sessionId: "session-1",
    deviceFamily: "android",
    elapsedMs: 600 + index,
    workerElapsedMs: 550 + index,
    backend: "model",
    backendName: "wasm",
    modelVersion: "candidate-v1",
    inputSize: 512,
    candidateCount: 5,
    warnings: [],
    usedJSHeapBytes: null,
    ...overrides,
  }));
}

function build(inputSamples = samples()) {
  return buildNailTextureDeviceSession({
    sessionId: "session-1",
    deviceFamily: "android",
    warmupRuns: 3,
    samples: inputSamples,
    image: { name: "hand.jpg", type: "image/jpeg", sizeBytes: 100, width: 1000, height: 1200, benchmarkWidth: 667, benchmarkHeight: 800 },
    environment: { userAgent: "test", platform: "test", hardwareConcurrency: 8, deviceMemoryGiB: 8, viewportWidth: 400, viewportHeight: 800, screenWidth: 400, screenHeight: 800, devicePixelRatio: 2 },
  });
}

test("device benchmark session accepts one model/backend/input across 20 measured runs", () => {
  const report = build();
  assert.equal(report.eligibleForPerformanceVerification, true);
  assert.equal(report.eligibleForMemoryAcceptance, false);
  assert.equal(report.measuredRuns, 20);
  assert.equal(report.backend, "wasm");
});

test("device benchmark session rejects fallback, mixed identity, and undersized runs", () => {
  const fallback = build(samples(20, { backend: "fallback", backendName: "fallback", modelVersion: "fallback-v0", inputSize: 0 }));
  assert.equal(fallback.eligibleForPerformanceVerification, false);
  assert.match(fallback.errors.join(" "), /fallback/);

  const mixed = samples();
  mixed[19] = { ...mixed[19]!, modelVersion: "candidate-v2" };
  const mixedReport = build(mixed);
  assert.match(mixedReport.errors.join(" "), /one model version/);

  const short = build(samples(19));
  assert.match(short.errors.join(" "), /below 20/);
});
