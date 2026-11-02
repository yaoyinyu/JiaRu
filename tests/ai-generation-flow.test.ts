import assert from "node:assert/strict";
import test from "node:test";

import {
  AI_ERROR_MESSAGES,
  buildAiRequestBody,
  classifyAiGenerationError,
  createRequestSnapshot,
  isAbortError,
  nextEngineSettings,
  resolveGenerateEndpoint,
  type AiEngineSettingsMap,
} from "../src/lib/ai-generate-flow.ts";

test("createRequestSnapshot 冻结请求参数并生成 requestId", () => {
  const snapshot = createRequestSnapshot({
    engine: "agnes",
    prompt: "银色亮片",
    ratio: "1:1",
    size: "1K",
    referenceImage: null,
    now: 1234,
    requestId: "req-fixed",
  });
  assert.deepEqual(snapshot, {
    requestId: "req-fixed",
    engine: "agnes",
    prompt: "银色亮片",
    ratio: "1:1",
    size: "1K",
    referenceImage: null,
    createdAt: 1234,
  });
});

test("resolveGenerateEndpoint 与 buildAiRequestBody 保持既有路由契约", () => {
  assert.equal(resolveGenerateEndpoint("agnes"), "/api/generate-ai");
  assert.equal(resolveGenerateEndpoint("seedream-pro"), "/api/generate-seedream");
  assert.equal(resolveGenerateEndpoint("seedream-lite"), "/api/generate-seedream");

  const agnes = createRequestSnapshot({
    engine: "agnes",
    prompt: "p",
    ratio: "1:1",
    size: "1K",
    referenceImage: "data:image/jpeg;base64,xx",
  });
  assert.deepEqual(buildAiRequestBody(agnes), {
    prompt: "p",
    image: "data:image/jpeg;base64,xx",
    ratio: "1:1",
    size: "1K",
  });

  const seedream = createRequestSnapshot({
    engine: "seedream-pro",
    prompt: "p",
    ratio: "16:9",
    size: "2K",
    referenceImage: null,
  });
  assert.deepEqual(buildAiRequestBody(seedream), {
    prompt: "p",
    image: undefined,
    model: "pro",
    ratio: "16:9",
    size: "2K",
  });
});

test("classifyAiGenerationError 覆盖方案 §6.6 错误表", () => {
  assert.equal(classifyAiGenerationError(new Error("x"), 429), "quota_exceeded");
  assert.equal(classifyAiGenerationError(new Error("x"), 401), "service_unconfigured");
  assert.equal(classifyAiGenerationError(new Error("x"), 503), "service_unconfigured");
  assert.equal(classifyAiGenerationError(new Error("x"), 504), "upstream_timeout");
  assert.equal(classifyAiGenerationError(new TypeError("Failed to fetch")), "network_failed");
  assert.equal(classifyAiGenerationError(new Error("request timeout")), "upstream_timeout");
  assert.equal(classifyAiGenerationError(new Error("weird")), "unknown");
  assert.match(AI_ERROR_MESSAGES.quota_exceeded, /明天再试/);
  assert.match(AI_ERROR_MESSAGES.service_unconfigured, /暂未配置/);
});

test("isAbortError 覆盖 Error 与 DOMException 两种口径", () => {
  const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
  assert.equal(isAbortError(abort), true);
  assert.equal(isAbortError(new Error("x")), false);
});

test("nextEngineSettings 恢复目标引擎的上次尺寸与草稿", () => {
  const settings: AiEngineSettingsMap = {
    agnes: { size: "1K", lastPromptDraft: "agnes 草稿" },
    "seedream-pro": { size: "2K", lastPromptDraft: "pro 草稿" },
    "seedream-lite": { size: "3K", lastPromptDraft: "" },
  };
  const next = nextEngineSettings(settings, "agnes", "seedream-pro");
  assert.equal(next.size, "2K");
  assert.equal(next.promptDraft, "pro 草稿");
});
