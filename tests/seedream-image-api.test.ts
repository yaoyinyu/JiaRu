import assert from "node:assert/strict";
import test from "node:test";

import {
  SeedreamImageApiError,
  generateSeedreamImage,
  getSeedreamImageConfig,
} from "../src/lib/seedream-image-api.ts";

const PRO_ENV = {
  VOLCENGINE_ARK_API_KEY: "test-secret",
  ARK_SEEDREAM_PRO_MODEL: "doubao-seedream-5-0-pro-test",
  ARK_SEEDREAM_LITE_MODEL: "doubao-seedream-5-0-lite-test",
};

test("Seedream 配置拒绝缺失密钥或 Model ID", () => {
  assert.throws(
    () => getSeedreamImageConfig("pro", {}),
    (error: unknown) =>
      error instanceof SeedreamImageApiError && error.statusCode === 503
  );
  assert.throws(
    () => getSeedreamImageConfig("lite", { VOLCENGINE_ARK_API_KEY: "k" }),
    (error: unknown) =>
      error instanceof SeedreamImageApiError &&
      error.statusCode === 503 &&
      error.message.includes("ARK_SEEDREAM_LITE_MODEL")
  );
});

test("Seedream 请求遵循 Ark 扁平协议（无 extra_body、显式 WxH、watermark 关闭）", async () => {
  let requestedUrl = "";
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (input: string | URL | Request, init?: RequestInit) => {
    requestedUrl = String(input);
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://ark.example/design.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const result = await generateSeedreamImage("银色亮片美甲", {
    env: PRO_ENV,
    model: "pro",
    pixelSize: "2048x2048",
    fetchImpl: fetchImpl as typeof fetch,
  });

  assert.equal(
    requestedUrl,
    "https://ark.cn-beijing.volces.com/api/v3/images/generations"
  );
  assert.equal(
    new Headers(requestedInit?.headers).get("Authorization"),
    "Bearer test-secret"
  );
  const body = JSON.parse(String(requestedInit?.body));
  assert.deepEqual(body, {
    model: "doubao-seedream-5-0-pro-test",
    prompt: "银色亮片美甲",
    size: "2048x2048",
    response_format: "url",
    watermark: false,
  });
  assert.equal("extra_body" in body, false);
  assert.equal("ratio" in body, false);
  assert.equal("sequential_image_generation" in body, false);
  assert.equal("image" in body, false);
  assert.equal(result.imageUrl, "https://ark.example/design.png");
  assert.equal(result.model, "doubao-seedream-5-0-pro-test");
});

test("Seedream lite 使用 lite Model ID，图生图携带顶层 image 字段", async () => {
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (_input: string | URL | Request, init?: RequestInit) => {
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://ark.example/hand.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const dataUri = "data:image/jpeg;base64,/9j/4AAQSkZJRg==";
  await generateSeedreamImage("法式美甲", {
    env: PRO_ENV,
    model: "lite",
    pixelSize: "1600x2848",
    imageDataUri: dataUri,
    fetchImpl: fetchImpl as typeof fetch,
  });

  const body = JSON.parse(String(requestedInit?.body));
  assert.equal(body.model, "doubao-seedream-5-0-lite-test");
  assert.equal(body.size, "1600x2848");
  assert.equal(body.image, dataUri);
});

test("Seedream 429/500/503 按指数退避重试", async () => {
  const statusSequence = [429, 500, 503];
  let attempts = 0;
  const fetchImpl = async () => {
    const status = statusSequence[attempts] ?? 200;
    attempts += 1;
    if (status === 200) {
      return new Response(
        JSON.stringify({ data: [{ url: "https://ark.example/retry.png" }] }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response("busy", { status });
  };

  const result = await generateSeedreamImage("重试美甲", {
    env: PRO_ENV,
    model: "pro",
    pixelSize: "2048x2048",
    fetchImpl: fetchImpl as typeof fetch,
    retryDelayMs: 0,
  });

  assert.equal(attempts, 4);
  assert.equal(result.imageUrl, "https://ark.example/retry.png");
});

test("Seedream 401 响应不会泄露供应商正文", async () => {
  const fetchImpl = async () =>
    new Response(JSON.stringify({ error: { message: "secret detail" } }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

  await assert.rejects(
    () =>
      generateSeedreamImage("未授权美甲", {
        env: PRO_ENV,
        model: "pro",
        pixelSize: "2048x2048",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    (error: unknown) =>
      error instanceof SeedreamImageApiError &&
      error.statusCode === 401 &&
      error.message === "火山方舟 API Key 无效"
  );
});

test("Seedream 顶层 error{code,message} 被归一化为 502 中文错误", async () => {
  const fetchImpl = async () =>
    new Response(
      JSON.stringify({ error: { code: "InternalServiceError", message: "生成失败" } }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );

  await assert.rejects(
    () =>
      generateSeedreamImage("审核拒绝美甲", {
        env: PRO_ENV,
        model: "pro",
        pixelSize: "2048x2048",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    (error: unknown) =>
      error instanceof SeedreamImageApiError &&
      error.statusCode === 502 &&
      error.message.includes("生成失败")
  );
});

test("Seedream 单图场景返回 data[0].error 时视为失败", async () => {
  const fetchImpl = async () =>
    new Response(
      JSON.stringify({
        data: [{ error: { code: "OutputImageSensitiveContentDetected", message: "内容审核未通过" } }],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );

  await assert.rejects(
    () =>
      generateSeedreamImage("敏感美甲", {
        env: PRO_ENV,
        model: "pro",
        pixelSize: "2048x2048",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    (error: unknown) =>
      error instanceof SeedreamImageApiError &&
      error.statusCode === 502 &&
      error.message.includes("内容审核未通过")
  );
});

test("Seedream 返回非 HTTPS 链接视为数据异常", async () => {
  const fetchImpl = async () =>
    new Response(JSON.stringify({ data: [{ url: "http://ark.example/x.png" }] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });

  await assert.rejects(
    () =>
      generateSeedreamImage("异常美甲", {
        env: PRO_ENV,
        model: "pro",
        pixelSize: "2048x2048",
        fetchImpl: fetchImpl as typeof fetch,
      }),
    (error: unknown) =>
      error instanceof SeedreamImageApiError && error.statusCode === 502
  );
});

test("Seedream 自定义 Base URL 生效且去掉尾部斜杠", async () => {
  let requestedUrl = "";
  const fetchImpl = async (input: string | URL | Request) => {
    requestedUrl = String(input);
    return new Response(
      JSON.stringify({ data: [{ url: "https://ark.example/ok.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  await generateSeedreamImage("自定义端点美甲", {
    env: { ...PRO_ENV, ARK_BASE_URL: "https://ark.cn-shanghai.volces.com/api/v3/" },
    model: "pro",
    pixelSize: "2048x2048",
    fetchImpl: fetchImpl as typeof fetch,
  });

  assert.equal(
    requestedUrl,
    "https://ark.cn-shanghai.volces.com/api/v3/images/generations"
  );
});

test(
  "Seedream 路由层不传 env 时不崩溃（回归 2026-09-03 浏览器实测报 " +
    "'Cannot read properties of undefined (reading ARK_IMAGE_WATERMARK)'）",
  async () => {
    // 模拟真实路由调用形态：仅传 model / pixelSize，不显式注入 env。
    // 若 generateSeedreamImage 内部没有 env ?? process.env 回退，watermark
    // 解析路径会读 undefined.ARK_IMAGE_WATERMARK 抛出。
    const prevArk = process.env.VOLCENGINE_ARK_API_KEY;
    const prevPro = process.env.ARK_SEEDREAM_PRO_MODEL;
    process.env.VOLCENGINE_ARK_API_KEY = "test-secret";
    process.env.ARK_SEEDREAM_PRO_MODEL = "doubao-seedream-5-0-pro-test";
    try {
      const fetchImpl = async () =>
        new Response(
          JSON.stringify({ data: [{ url: "https://ark.example/design.png" }] }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      const result = await generateSeedreamImage("银色亮片美甲", {
        model: "pro",
        pixelSize: "2048x2048",
        fetchImpl: fetchImpl as typeof fetch,
      });
      assert.equal(result.imageUrl, "https://ark.example/design.png");
      assert.equal(result.model, "doubao-seedream-5-0-pro-test");
    } finally {
      if (prevArk === undefined) delete process.env.VOLCENGINE_ARK_API_KEY;
      else process.env.VOLCENGINE_ARK_API_KEY = prevArk;
      if (prevPro === undefined) delete process.env.ARK_SEEDREAM_PRO_MODEL;
      else process.env.ARK_SEEDREAM_PRO_MODEL = prevPro;
    }
  }
);
