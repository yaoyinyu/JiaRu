import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ARK_DETECT_MAX_BOXES,
  ARK_DETECT_SYSTEM_PROMPT,
  ArkDetectApiError,
  buildArkDetectUserPrompt,
  detectNailsWithArkModel,
  getArkDetectConfig,
  isArkDetectEnabled,
  parseArkDetectBoxes,
} from "../src/lib/nail-detect-ark-api.ts";

const GOOD_ENV = {
  VOLCENGINE_ARK_API_KEY: "test-key",
  ARK_VISION_MODEL: "doubao-vision-test",
};

// ── 配置 ──

test("isArkDetectEnabled requires both key and model", () => {
  assert.equal(isArkDetectEnabled(GOOD_ENV), true);
  assert.equal(isArkDetectEnabled({ VOLCENGINE_ARK_API_KEY: "test-key" }), false);
  assert.equal(isArkDetectEnabled({ ARK_VISION_MODEL: "m" }), false);
  assert.equal(isArkDetectEnabled({ VOLCENGINE_ARK_API_KEY: "your-key-here", ARK_VISION_MODEL: "m" }), false);
});

test("getArkDetectConfig validates base URL like the Seedream client", () => {
  const config = getArkDetectConfig(GOOD_ENV);
  assert.equal(config.apiKey, "test-key");
  assert.equal(config.model, "doubao-vision-test");
  assert.ok(config.baseUrl.startsWith("https://ark."));

  assert.throws(
    () => getArkDetectConfig({ ...GOOD_ENV, ARK_BASE_URL: "http://insecure.example.com" }),
    (err: unknown) => err instanceof ArkDetectApiError && err.reason === "disabled"
  );
  assert.throws(
    () => getArkDetectConfig({ VOLCENGINE_ARK_API_KEY: "test-key" }),
    /ARK_VISION_MODEL/
  );
});

// ── 提示词与解析 ──

test("buildArkDetectUserPrompt declares image size, format and the 10-box cap", () => {
  const prompt = buildArkDetectUserPrompt(1600, 800);
  assert.ok(prompt.includes("1600x800"));
  assert.ok(prompt.includes("[x1,y1,x2,y2]"));
  assert.ok(prompt.includes("10 个框"));
  assert.ok(prompt.includes('{"nails":[{"box":[x1,y1,x2,y2]}]}'));
  assert.ok(ARK_DETECT_SYSTEM_PROMPT.includes("JSON"));
});

test("parseArkDetectBoxes strips fences and validates each box", () => {
  const fenced = '```json\n{"nails":[{"box":[1,2,30,40]},{"box":[5,5,6,6]}]}\n```';
  // 解析层只做形状校验（x2>x1、y2>y1）；噪声尺寸门在客户端映射层。
  assert.deepEqual(parseArkDetectBoxes(fenced), [
    [1, 2, 30, 40],
    [5, 5, 6, 6],
  ]);

  const plain = '前缀 {"nails":[{"box":[10,20,30,40]},{"box":[40,30,20,10]}]} 后缀';
  assert.deepEqual(parseArkDetectBoxes(plain), [[10, 20, 30, 40]]);

  assert.deepEqual(parseArkDetectBoxes('{"nails":[{"box":[1,2,3]}]}'), [], "长度不为 4 剔除");
  assert.deepEqual(parseArkDetectBoxes('{"nails":[{"box":["a",1,2,3]}]}'), [], "非数值剔除");
  assert.deepEqual(parseArkDetectBoxes('{"nails":[]}'), [], "空结果合法");
  // 超限截断到 ARK_DETECT_MAX_BOXES。
  const many = `{"nails":[${Array.from({ length: 15 }, (_, i) => `{"box":[${i},0,${i + 10},10]}`).join(",")}]}`;
  assert.equal(parseArkDetectBoxes(many).length, ARK_DETECT_MAX_BOXES);
  // 非法 JSON 由调用方（模型层）转 upstream，解析层抛错。
  assert.throws(() => parseArkDetectBoxes("not json at all"));
});

// ── detectNailsWithArkModel（mock fetchImpl）──

function arkResponse(body: unknown, status = 200, headers?: Record<string, string>): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(headers),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function chatContent(content: string) {
  return { choices: [{ message: { content } }] };
}

test("detectNailsWithArkModel posts chat/completions with data URI and returns boxes", async () => {
  let capturedUrl = "";
  let capturedAuth = "";
  let capturedBody: Record<string, unknown> | null = null;
  const result = await detectNailsWithArkModel({
    imageDataUri: "data:image/jpeg;base64,AAAA",
    imageWidth: 1600,
    imageHeight: 800,
    env: GOOD_ENV,
    fetchImpl: (async (url: string | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedAuth = String(new Headers(init?.headers).get("Authorization"));
      capturedBody = JSON.parse(String(init?.body));
      return arkResponse(chatContent('{"nails":[{"box":[10,20,30,40]}]}'));
    }) as typeof fetch,
  });
  assert.ok(capturedUrl.endsWith("/chat/completions"));
  assert.equal(capturedAuth, "Bearer test-key");
  assert.equal((capturedBody as unknown as { model: string }).model, "doubao-vision-test");
  const messages = (capturedBody as unknown as { messages: Array<{ role: string; content: unknown }> }).messages;
  assert.equal(messages[0]!.role, "system");
  const userContent = messages[1]!.content as Array<{ type: string }>;
  assert.ok(userContent.some((part) => part.type === "image_url"));
  assert.deepEqual(result.boxes, [[10, 20, 30, 40]]);
  assert.equal(result.model, "doubao-vision-test");
  assert.ok(result.elapsedMs >= 0);
});

test("detectNailsWithArkModel retries 500 then succeeds", async () => {
  let calls = 0;
  const result = await detectNailsWithArkModel({
    imageDataUri: "data:image/jpeg;base64,AAAA",
    imageWidth: 800,
    imageHeight: 600,
    env: GOOD_ENV,
    fetchImpl: (async () => {
      calls += 1;
      if (calls === 1) return arkResponse({ error: { message: "internal" } }, 500);
      return arkResponse(chatContent('{"nails":[{"box":[0,0,9,9]}]}'));
    }) as typeof fetch,
    retryDelayMs: 1,
  });
  assert.equal(calls, 2);
  assert.deepEqual(result.boxes, [[0, 0, 9, 9]]);
});

test("detectNailsWithArkModel maps 429 to rate_limited with Retry-After", async () => {
  await assert.rejects(
    detectNailsWithArkModel({
      imageDataUri: "data:image/jpeg;base64,AAAA",
      imageWidth: 800,
      imageHeight: 600,
      env: GOOD_ENV,
      fetchImpl: (async () => arkResponse({ error: { message: "quota" } }, 429, { "Retry-After": "30" })) as typeof fetch,
      maxAttempts: 1,
    }),
    (err: unknown) =>
      err instanceof ArkDetectApiError &&
      err.statusCode === 429 &&
      err.reason === "rate_limited" &&
      err.retryAfterSeconds === 30
  );
});

test("detectNailsWithArkModel maps 401 to auth_misconfigured without leaking the key", async () => {
  try {
    await detectNailsWithArkModel({
      imageDataUri: "data:image/jpeg;base64,AAAA",
      imageWidth: 800,
      imageHeight: 600,
      env: GOOD_ENV,
      fetchImpl: (async () => arkResponse({ error: { message: "invalid key test-key" } }, 401)) as typeof fetch,
      maxAttempts: 1,
    });
    assert.fail("should throw");
  } catch (err) {
    assert.ok(err instanceof ArkDetectApiError);
    assert.equal(err.reason, "auth_misconfigured");
    assert.equal(err.statusCode, 503);
    // 错误文案不得包含密钥原文。
    assert.ok(!err.message.includes("test-key"));
  }
});

test("detectNailsWithArkModel treats unparseable model content as upstream error", async () => {
  await assert.rejects(
    detectNailsWithArkModel({
      imageDataUri: "data:image/jpeg;base64,AAAA",
      imageWidth: 800,
      imageHeight: 600,
      env: GOOD_ENV,
      fetchImpl: (async () => arkResponse(chatContent("这不是 JSON"))) as typeof fetch,
      maxAttempts: 1,
    }),
    (err: unknown) => err instanceof ArkDetectApiError && err.reason === "upstream"
  );
});

// ── 路由源码合同（node:test 无请求环境，按源码断言接线） ──

test("ark route keeps the whitelist, size gate and rate-limit bucket contract", () => {
  const source = readFileSync(new URL("../src/app/api/nail-detect-ark/route.ts", import.meta.url), "utf8");
  assert.match(source, /IMAGE_DATA_URI_PATTERN = \/\^data:image\\\/\(png\|jpeg\|jpg\|webp\);base64,\/i/);
  assert.match(source, /MAX_BODY_BYTES = 8 \* 1024 \* 1024/);
  assert.match(source, /consume\("nailDetectArk", identity\)/);
  assert.match(source, /isArkDetectEnabled\(\)/);
  assert.match(source, /requireUserWithRenewal\(req\)/);
  assert.match(source, /guestIdentityFromHeaders\(req\.headers\)/);
  // 降级响应格式与 matte 路由同构。
  assert.match(source, /degraded: true/);
  // 响应只含白名单字段。
  assert.match(source, /boxes: result\.boxes\.slice\(0, MAX_BOXES\)/);
});

test("cloud matte route mirrors the local contract with its own bucket and target", () => {
  const source = readFileSync(new URL("../src/app/api/nail-matte-cloud/route.ts", import.meta.url), "utf8");
  assert.match(source, /consume\("nailMatteCloud", identity\)/);
  assert.match(source, /target: "cloud"/);
  assert.match(source, /NAIL_CLOUD_MATTE_URL/);
  assert.match(source, /MAX_BODY_BYTES = 8 \* 1024 \* 1024/);
  // imagePath 不可达上游（白名单重建）。
  assert.match(source, /只读四个白名单字段/);
  assert.match(source, /degraded: true/);
  assert.match(source, /requireUserWithRenewal\(req\)/);
});

test("nail-matte-api stays backward compatible and parameterizes the target", () => {
  const source = readFileSync(new URL("../src/lib/nail-matte-api.ts", import.meta.url), "utf8");
  assert.match(source, /export function resolveNailMatteConfig\(/);
  assert.match(source, /target\?: NailMatteTarget/);
  // 本地默认路径行为不变：requestNailMatte 仍按 target 解析，默认 local。
  assert.match(source, /options\.target \?\? "local"/);
});
