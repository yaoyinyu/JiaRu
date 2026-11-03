import assert from "node:assert/strict";
import test from "node:test";

import {
  getNailMatteConfig,
  NailMatteApiError,
  probeNailMatte,
  requestNailMatte,
  resolveNailMatteConfig,
  type NailMatteEnv,
} from "../src/lib/nail-matte-api.ts";

const LOCAL_ENV: NailMatteEnv = { VLM_MATTE_URL: "http://127.0.0.1:8008", VLM_MATTE_TOKEN: "local-token" };
const CLOUD_ENV: NailMatteEnv = {
  NAIL_CLOUD_MATTE_URL: "https://cloud.example.com:8008/",
  NAIL_CLOUD_MATTE_TOKEN: "cloud-token",
};

// ── resolveNailMatteConfig ──

test("resolveNailMatteConfig keeps local behavior and reads cloud env for cloud target", () => {
  // local 与 getNailMatteConfig 同口径。
  assert.deepEqual(resolveNailMatteConfig("local", LOCAL_ENV), { url: "http://127.0.0.1:8008", token: "local-token" });
  assert.deepEqual(getNailMatteConfig(LOCAL_ENV), resolveNailMatteConfig("local", LOCAL_ENV));
  // cloud 读取新 env，尾斜杠归一。
  assert.deepEqual(resolveNailMatteConfig("cloud", CLOUD_ENV), {
    url: "https://cloud.example.com:8008",
    token: "cloud-token",
  });
  // 未配置 → 关闭；local env 不影响 cloud 解析。
  assert.equal(resolveNailMatteConfig("cloud", LOCAL_ENV), null);
  assert.equal(resolveNailMatteConfig("cloud", {}), null);
  assert.equal(getNailMatteConfig({}), null);
});

// ── requestNailMatte target=cloud ──

function matteResponse(): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({
      width: 800,
      height: 600,
      instances: [],
      omittedInstances: 0,
      model: "wevisone-test",
      quant: "int4",
      elapsedMs: 12,
    }),
  } as unknown as Response;
}

test("requestNailMatte with target=cloud posts to the cloud URL with its token", async () => {
  let capturedUrl = "";
  let capturedAuth: string | null = null;
  let capturedBody: Record<string, unknown> | null = null;
  const result = await requestNailMatte(
    { image: "data:image/jpeg;base64,AAAA", task: "matting", query: "nails" },
    {
      target: "cloud",
      env: CLOUD_ENV,
      fetchImpl: (async (url: string | URL, init?: RequestInit) => {
        capturedUrl = String(url);
        capturedAuth = new Headers(init?.headers).get("Authorization");
        capturedBody = JSON.parse(String(init?.body));
        return matteResponse();
      }) as typeof fetch,
    }
  );
  assert.equal(capturedUrl, "https://cloud.example.com:8008/matte");
  assert.equal(capturedAuth, "Bearer cloud-token");
  assert.equal(capturedBody!.image, "data:image/jpeg;base64,AAAA");
  assert.equal(result.model, "wevisone-test");
});

test("requestNailMatte target=cloud without config throws disabled with cloud wording", async () => {
  await assert.rejects(
    requestNailMatte(
      { image: "data:image/jpeg;base64,AAAA", task: "matting", query: "nails" },
      { target: "cloud", env: {} }
    ),
    (err: unknown) =>
      err instanceof NailMatteApiError && err.reason === "disabled" && /云端抠图服务未启用/.test(err.message)
  );
});

test("requestNailMatte default target stays local (backward compatible)", async () => {
  let capturedUrl = "";
  await requestNailMatte(
    { image: "data:image/jpeg;base64,AAAA", task: "matting", query: "nails" },
    {
      env: LOCAL_ENV,
      fetchImpl: (async (url: string | URL) => {
        capturedUrl = String(url);
        return matteResponse();
      }) as typeof fetch,
    }
  );
  assert.equal(capturedUrl, "http://127.0.0.1:8008/matte");
});

test("probeNailMatte with target=cloud probes the cloud health endpoint", async () => {
  let capturedUrl = "";
  const health = await probeNailMatte({
    target: "cloud",
    env: CLOUD_ENV,
    fetchImpl: (async (url: string | URL) => {
      capturedUrl = String(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({ ready: true, busy: false, model: "wevisone-cloud" }),
      } as unknown as Response;
    }) as typeof fetch,
  });
  assert.equal(capturedUrl, "https://cloud.example.com:8008/health");
  assert.deepEqual(health, { ready: true, busy: false, model: "wevisone-cloud" });
  // 未配置 cloud → null（入口不渲染）。
  assert.equal(await probeNailMatte({ target: "cloud", env: {} }), null);
});
