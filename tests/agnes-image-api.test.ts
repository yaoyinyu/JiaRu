import assert from "node:assert/strict";
import test from "node:test";

import {
  AgnesImageApiError,
  generateAgnesImage,
  getAgnesImageConfig,
} from "../src/lib/agnes-image-api.ts";

test("Agnes 配置拒绝缺失密钥", () => {
  assert.throws(
    () => getAgnesImageConfig({}),
    (error: unknown) =>
      error instanceof AgnesImageApiError && error.statusCode === 503
  );
});

test("Agnes 图像请求遵循 Image 2.1 Flash 协议", async () => {
  let requestedUrl = "";
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (input: string | URL | Request, init?: RequestInit) => {
    requestedUrl = String(input);
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/design.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const result = await generateAgnesImage("pink chrome manicure", {
    env: {
      AGNES_API_KEY: "test-secret",
      AGNES_API_BASE_URL: "https://apihub.agnes-ai.cn/v1/",
      AGNES_IMAGE_MODEL: "agnes-image-2.1-flash",
    },
    fetchImpl: fetchImpl as typeof fetch,
  });

  assert.equal(
    requestedUrl,
    "https://apihub.agnes-ai.cn/v1/images/generations"
  );
  assert.equal(
    new Headers(requestedInit?.headers).get("Authorization"),
    "Bearer test-secret"
  );
  const body = JSON.parse(String(requestedInit?.body));
  assert.deepEqual(body, {
    model: "agnes-image-2.1-flash",
    prompt: "pink chrome manicure",
    size: "1024x1024",
    extra_body: { response_format: "url" },
  });
  assert.equal("image" in body, false);
  assert.equal("response_format" in body, false);
  assert.deepEqual(result, {
    imageUrl: "https://images.example/design.png",
    model: "agnes-image-2.1-flash",
  });
});

test("Agnes 503 响应按指数退避重试", async () => {
  let attempts = 0;
  const fetchImpl = async () => {
    attempts += 1;
    if (attempts < 3) {
      return new Response("busy", { status: 503 });
    }
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/retry.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const result = await generateAgnesImage("retry manicure", {
    env: { AGNES_API_KEY: "test-secret" },
    fetchImpl: fetchImpl as typeof fetch,
    retryDelayMs: 0,
  });

  assert.equal(attempts, 3);
  assert.equal(result.imageUrl, "https://images.example/retry.png");
});

test("Agnes 401 响应不会泄露供应商正文", async () => {
  const fetchImpl = async () =>
    new Response(JSON.stringify({ error: { message: "secret detail" } }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });

  await assert.rejects(
    () =>
      generateAgnesImage("unauthorized manicure", {
        env: { AGNES_API_KEY: "bad-secret" },
        fetchImpl: fetchImpl as typeof fetch,
      }),
    (error: unknown) =>
      error instanceof AgnesImageApiError &&
      error.statusCode === 401 &&
      error.message === "Agnes API Key 无效"
  );
});

test("Agnes 图生图请求携带 Data URI 图片与 ratio", async () => {
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (_input: string | URL | Request, init?: RequestInit) => {
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/hand.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const dataUri = "data:image/jpeg;base64,/9j/4AAQSkZJRg==";
  const result = await generateAgnesImage("银色亮片美甲", {
    env: { AGNES_API_KEY: "test-secret" },
    fetchImpl: fetchImpl as typeof fetch,
    imageDataUri: dataUri,
    ratio: "3:4",
  });

  const body = JSON.parse(String(requestedInit?.body));
  assert.deepEqual(body, {
    model: "agnes-image-2.1-flash",
    prompt: "银色亮片美甲",
    size: "1K",
    ratio: "3:4",
    extra_body: {
      image: [dataUri],
      response_format: "url",
    },
  });
  assert.equal(result.imageUrl, "https://images.example/hand.png");
});

test("Agnes 图生图不传 ratio 时保持旧尺寸格式", async () => {
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (_input: string | URL | Request, init?: RequestInit) => {
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/hand2.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  await generateAgnesImage("简约美甲", {
    env: { AGNES_API_KEY: "test-secret" },
    fetchImpl: fetchImpl as typeof fetch,
    imageDataUri: "data:image/png;base64,AAAA",
  });

  const body = JSON.parse(String(requestedInit?.body));
  assert.equal(body.size, "1024x1024");
  assert.equal("ratio" in body, false);
  assert.deepEqual(body.extra_body, {
    image: ["data:image/png;base64,AAAA"],
    response_format: "url",
  });
});

test("Agnes 支持用户指定的尺寸档位与画面比例（文生图）", async () => {
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (_input: string | URL | Request, init?: RequestInit) => {
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/wide.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  const result = await generateAgnesImage("银河渐变长甲", {
    env: { AGNES_API_KEY: "test-secret" },
    fetchImpl: fetchImpl as typeof fetch,
    size: "2K",
    ratio: "16:9",
  });

  const body = JSON.parse(String(requestedInit?.body));
  assert.deepEqual(body, {
    model: "agnes-image-2.1-flash",
    prompt: "银河渐变长甲",
    size: "2K",
    ratio: "16:9",
    extra_body: { response_format: "url" },
  });
  assert.equal(result.imageUrl, "https://images.example/wide.png");
});

test("Agnes 提供尺寸档位但未提供比例时保持档位式 size", async () => {
  let requestedInit: RequestInit | undefined;
  const fetchImpl = async (_input: string | URL | Request, init?: RequestInit) => {
    requestedInit = init;
    return new Response(
      JSON.stringify({ data: [{ url: "https://images.example/hi.png" }] }),
      { status: 200, headers: { "Content-Type": "application/json" } }
    );
  };

  await generateAgnesImage("高清美甲", {
    env: { AGNES_API_KEY: "test-secret" },
    fetchImpl: fetchImpl as typeof fetch,
    size: "4K",
  });

  const body = JSON.parse(String(requestedInit?.body));
  assert.equal(body.size, "4K");
  assert.equal("ratio" in body, false);
});
