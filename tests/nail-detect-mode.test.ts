import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyNailDetectError,
  decideNailDetectRun,
  describeNailCloudBackend,
  hasAnyCloudBackend,
  NAIL_CLOUD_BACKEND_LABELS,
  NAIL_CLOUD_CONSENT_STORAGE_KEY,
  NAIL_DETECT_ERROR_MESSAGES,
  readNailCloudConsent,
  resolveDefaultCloudBackend,
  writeNailCloudConsent,
  type NailCloudAvailability,
} from "../src/lib/nail-detect-mode.ts";

// ── resolveDefaultCloudBackend / hasAnyCloudBackend ──

test("resolveDefaultCloudBackend prefers ark and falls back to cloud matte", () => {
  assert.equal(resolveDefaultCloudBackend({ ark: true, cloudMatte: true }), "ark");
  assert.equal(resolveDefaultCloudBackend({ ark: false, cloudMatte: true }), "cloud-matte");
  assert.equal(resolveDefaultCloudBackend({ ark: false, cloudMatte: false }), null);
  assert.equal(resolveDefaultCloudBackend({ ark: true, cloudMatte: false }), "ark");
});

test("hasAnyCloudBackend is true only when at least one backend is available", () => {
  assert.equal(hasAnyCloudBackend({ ark: false, cloudMatte: false }), false);
  assert.equal(hasAnyCloudBackend({ ark: true, cloudMatte: false }), true);
  assert.equal(hasAnyCloudBackend({ ark: false, cloudMatte: true }), true);
});

// ── decideNailDetectRun ──

const AVAILABLE: NailCloudAvailability = { ark: true, cloudMatte: true };
const NONE: NailCloudAvailability = { ark: false, cloudMatte: false };

test("decideNailDetectRun: local mode always runs without consent or availability", () => {
  assert.deepEqual(decideNailDetectRun({ mode: "local", backend: "ark", availability: NONE, consentGiven: false }), {
    action: "run",
  });
});

test("decideNailDetectRun: cloud without any backend is unavailable with actionable message", () => {
  const decision = decideNailDetectRun({ mode: "cloud", backend: "ark", availability: NONE, consentGiven: true });
  assert.equal(decision.action, "unavailable");
  assert.ok(decision.action === "unavailable" && /ARK_VISION_MODEL|NAIL_CLOUD_MATTE_URL/.test(decision.message));
});

test("decideNailDetectRun: cloud with unavailable selected backend names the backend", () => {
  const decision = decideNailDetectRun({
    mode: "cloud",
    backend: "cloud-matte",
    availability: { ark: true, cloudMatte: false },
    consentGiven: true,
  });
  assert.equal(decision.action, "unavailable");
  assert.ok(decision.action === "unavailable" && decision.message.includes(NAIL_CLOUD_BACKEND_LABELS["cloud-matte"]));
});

test("decideNailDetectRun: cloud without consent asks for consent first", () => {
  const decision = decideNailDetectRun({ mode: "cloud", backend: "ark", availability: AVAILABLE, consentGiven: false });
  assert.equal(decision.action, "need-consent");
  assert.ok(decision.action === "need-consent" && /隐私/.test(decision.message));
});

test("decideNailDetectRun: cloud with availability and consent runs", () => {
  assert.deepEqual(
    decideNailDetectRun({ mode: "cloud", backend: "cloud-matte", availability: AVAILABLE, consentGiven: true }),
    { action: "run" }
  );
});

// ── consent storage helpers ──

test("consent round-trips through a localStorage-like store; failures are silent", () => {
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
  };
  assert.equal(readNailCloudConsent(storage), false);
  writeNailCloudConsent(storage);
  assert.equal(store.get(NAIL_CLOUD_CONSENT_STORAGE_KEY), "1");
  assert.equal(readNailCloudConsent(storage), true);
  // 未提供 storage（SSR / 隐私模式）不抛错。
  assert.equal(readNailCloudConsent(undefined), false);
  assert.doesNotThrow(() => writeNailCloudConsent(undefined));
});

// ── classifyNailDetectError ──

test("classifyNailDetectError maps degraded reasons to stable codes with copy", () => {
  assert.equal(classifyNailDetectError("rate_limited"), "rate_limited");
  assert.equal(classifyNailDetectError("timeout"), "timeout");
  assert.equal(classifyNailDetectError("disabled"), "disabled");
  assert.equal(classifyNailDetectError("busy"), "busy");
  assert.equal(classifyNailDetectError("invalid_image"), "invalid");
  assert.equal(classifyNailDetectError("too_large"), "invalid");
  assert.equal(classifyNailDetectError("cancelled"), "cancelled");
  assert.equal(classifyNailDetectError("network"), "network");
  // 未知一律按 upstream，不给用户裸异常。
  assert.equal(classifyNailDetectError("weird_reason"), "upstream");
  assert.equal(classifyNailDetectError(null), "upstream");
  for (const message of Object.values(NAIL_DETECT_ERROR_MESSAGES)) {
    assert.ok(message.length > 4);
  }
});

test("describeNailCloudBackend returns user-facing labels", () => {
  assert.equal(describeNailCloudBackend("ark"), "方舟视觉");
  assert.equal(describeNailCloudBackend("cloud-matte"), "云端自托管抠图");
});
