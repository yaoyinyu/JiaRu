import assert from "node:assert/strict";
import test from "node:test";
import { getNailMatteConfig, resolveNailMatteConfig, requestNailMatte } from "../src/lib/nail-matte-api.ts";

const token = "candidate-test-token-32-characters-long";
test("本机候选接管本机链路，原服务配置保留供回退，云端目标独立", () => {
  const env = { NAIL_CANDIDATE_URL: "http://127.0.0.1:8011/", NAIL_CANDIDATE_TOKEN: token,
    VLM_MATTE_URL: "http://127.0.0.1:8008", VLM_MATTE_TOKEN: "old" };
  assert.deepEqual(getNailMatteConfig(env), { url: "http://127.0.0.1:8011", token });
  assert.equal(resolveNailMatteConfig("cloud", env), null);
  assert.deepEqual(getNailMatteConfig({ VLM_MATTE_URL: env.VLM_MATTE_URL, VLM_MATTE_TOKEN: "old" }),
    { url: env.VLM_MATTE_URL, token: "old" });
});
test("候选配置拒绝公网目标、凭证URL和缺少长令牌", () => {
  for (const url of ["https://remote.example", "http://user@127.0.0.1:8011", "http://127.0.0.1:8011/other"]) {
    assert.throws(() => getNailMatteConfig({ NAIL_CANDIDATE_URL: url, NAIL_CANDIDATE_TOKEN: token }));
  }
  assert.throws(() => getNailMatteConfig({ NAIL_CANDIDATE_URL: "http://127.0.0.1:8011" }));
});
test("候选使用既有matte协议，只转发图像白名单，保留真实模型版本", async () => {
  const result = await requestNailMatte({ image: "data:image/png;base64,AAAA", task: "matting", query: "nails" }, {
    env: { NAIL_CANDIDATE_URL: "http://127.0.0.1:8011", NAIL_CANDIDATE_TOKEN: token },
    fetchImpl: (async (url, init) => {
      assert.equal(url, "http://127.0.0.1:8011/matte");
      assert.equal(new Headers(init?.headers).get("Authorization"), `Bearer ${token}`);
      assert.deepEqual(Object.keys(JSON.parse(String(init?.body))).sort(), ["image", "query", "task"]);
      return Response.json({ width: 100, height: 80, instances: [], model: "jiaru-geometry64-trial", quant: "none" });
    }) as typeof fetch,
  });
  assert.equal(result.model, "jiaru-geometry64-trial");
  assert.equal(result.quant, "none");
});
