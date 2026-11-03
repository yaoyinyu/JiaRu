import assert from "node:assert/strict";
import test from "node:test";

import {
  candidateFromArkBox,
  cloudDetectMessageFromReason,
  detectNailsWithArk,
  detectNailsWithCloudMatte,
  mapArkBoxesToCandidates,
  NAIL_CLOUD_MAX_CANDIDATES,
  NAIL_CLOUD_MIN_BOX_PX,
  nailCandidatesToDetectionRegions,
  rectMaskFromBox,
  type ArkDetectInput,
} from "../src/lib/nail-cloud-detect.ts";
import { NAIL_DETECT_ERROR_MESSAGES } from "../src/lib/nail-detect-mode.ts";
import type { AlphaGrid } from "../src/lib/nail-texture-recognition/vlm-refinement.ts";

// ── rectMaskFromBox ──

test("rectMaskFromBox builds a solid full-image grid mask inside the box", () => {
  // 2000x1000 原图 → 栅格最长边 256 → 256x128。
  const mask = rectMaskFromBox({ x1: 100, y1: 50, x2: 300, y2: 250 }, 2000, 1000);
  assert.equal(mask.width, 256);
  assert.equal(mask.height, 128);
  assert.equal(mask.originX, 0);
  assert.equal(mask.originY, 0);
  // scale 取两轴较大比例（2000/256 = 7.8125）。
  assert.ok(Math.abs(mask.scale - 2000 / 256) < 1e-9);
  // 框内实心（换算到栅格：x≈12.8→38.4，y≈6.4→32）。
  const inside = mask.data[20 * mask.width + 20];
  assert.equal(inside, 1);
  // 框外为空。
  assert.equal(mask.data[2 * mask.width + 2], 0);
  assert.equal(mask.data[mask.data.length - 1], 0);
});

// ── candidateFromArkBox ──

test("candidateFromArkBox maps encoded-space boxes to original coordinates", () => {
  // 编码图 1600x800（原图 2000x1000，scale=0.8）。
  const candidate = candidateFromArkBox([200, 100, 400, 300], 2000, 1000, 0);
  assert.ok(candidate);
  // x: 200/0.8=250 → 400/0.8=500；cx=375, width=250。
  assert.ok(Math.abs(candidate!.cx - 375) < 1e-6);
  assert.ok(Math.abs(candidate!.width - 250) < 1e-6);
  // y: 100/0.8=125 → 300/0.8=375；cy=250, length=250。
  assert.ok(Math.abs(candidate!.cy - 250) < 1e-6);
  assert.ok(Math.abs(candidate!.length - 250) < 1e-6);
  assert.equal(candidate!.confidence, "low");
  assert.equal(candidate!.source, "cloud-ark");
  assert.deepEqual(candidate!.warnings, ["needs_review"]);
  assert.equal(candidate!.suggestedFinger, null);
  assert.ok(candidate!.mask, "矩形 mask 必须随候选提供");
});

test("candidateFromArkBox rejects malformed and noise boxes", () => {
  assert.equal(candidateFromArkBox([0, 0, 0, 0], 1000, 1000, 0), null, "零尺寸框");
  assert.equal(candidateFromArkBox([10, 10, 5, 20], 1000, 1000, 0), null, "x2<=x1");
  assert.equal(candidateFromArkBox([10, 10, 20, 5], 1000, 1000, 0), null, "y2<=y1");
  assert.equal(
    candidateFromArkBox([10, 10, 10 + NAIL_CLOUD_MIN_BOX_PX - 1, 100], 1000, 1000, 0),
    null,
    "宽度低于噪声门"
  );
  assert.equal(candidateFromArkBox([1, 2, 3], 1000, 1000, 0), null, "长度不为 4");
  assert.equal(candidateFromArkBox(["a", 1, 2, 3] as unknown as number[], 1000, 1000, 0), null, "非数值");
});

test("candidateFromArkBox clamps boxes to image bounds", () => {
  const candidate = candidateFromArkBox([-50, -50, 5000, 5000], 1000, 1000, 0);
  assert.ok(candidate);
  assert.ok(candidate!.cx - candidate!.width / 2 >= 0);
  assert.ok(candidate!.cx + candidate!.width / 2 <= 1000);
  assert.ok(candidate!.cy + candidate!.length / 2 <= 1000);
});

// ── mapArkBoxesToCandidates ──

test("mapArkBoxesToCandidates dedupes near-identical boxes and caps at the limit", () => {
  const boxes = [
    [100, 100, 200, 200],
    [101, 101, 201, 201], // IoU > 0.9 → 丢弃
    [500, 100, 600, 200], // 保留
  ];
  const candidates = mapArkBoxesToCandidates(boxes, 1000, 1000);
  assert.equal(candidates.length, 2);
  assert.equal(candidates[0]!.id, "cloud-ark-0");
  assert.equal(candidates[1]!.id, "cloud-ark-1");

  const many = Array.from({ length: 20 }, (_, i) => [i * 40, 0, i * 40 + 30, 30]);
  assert.equal(mapArkBoxesToCandidates(many, 2000, 2000).length, NAIL_CLOUD_MAX_CANDIDATES);
  // 非数组输入安全返回空。
  assert.equal(mapArkBoxesToCandidates(null, 1000, 1000).length, 0);
  assert.equal(mapArkBoxesToCandidates("boxes", 1000, 1000).length, 0);
});

// ── detectNailsWithArk（mock fetch / encode）──

function makeArkInput(
  fetchImpl: typeof fetch,
  overrides: Partial<ArkDetectInput> = {}
): ArkDetectInput {
  return {
    image: { width: 800, height: 600 } as unknown as CanvasImageSource,
    imageWidth: 800,
    imageHeight: 600,
    encode: async () => "data:image/jpeg;base64,AAAA",
    fetchImpl,
    ...overrides,
  };
}

function arkFetchResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

test("detectNailsWithArk posts encoded image with geometry and maps boxes", async () => {
  let capturedUrl = "";
  let capturedBody: Record<string, unknown> | null = null;
  const fetchImpl = (async (url: string | URL, init?: RequestInit) => {
    capturedUrl = String(url);
    capturedBody = JSON.parse(String(init?.body));
    return arkFetchResponse({
      ok: true,
      boxes: [
        [100, 100, 200, 220],
        [400, 100, 500, 220],
      ],
      model: "doubao-vision-test",
      elapsedMs: 1234,
    });
  }) as typeof fetch;

  const outcome = await detectNailsWithArk(makeArkInput(fetchImpl));
  assert.equal(outcome.status, "ok");
  assert.equal(capturedUrl, "/api/nail-detect-ark");
  // 编码几何：800x600 → 长边 1600 不缩放 → width 800 height 600。
  assert.equal(capturedBody!.width, 800);
  assert.equal(capturedBody!.height, 600);
  assert.ok(String(capturedBody!.image).startsWith("data:image/jpeg;base64,"));
  if (outcome.status !== "ok") throw new Error("unreachable");
  assert.equal(outcome.candidates.length, 2);
  assert.equal(outcome.model, "doubao-vision-test");
  assert.equal(outcome.elapsedMs, 1234);
});

test("detectNailsWithArk maps degraded and error responses without throwing", async () => {
  const degraded = await detectNailsWithArk(
    makeArkInput((async () =>
      arkFetchResponse({ degraded: true, reason: "rate_limited", error: "过于频繁", retryAfterSeconds: 42 }, 429)) as typeof fetch)
  );
  assert.equal(degraded.status, "degraded");
  if (degraded.status === "degraded") {
    assert.equal(degraded.reason, "rate_limited");
    assert.equal(degraded.retryAfterSeconds, 42);
  }

  const networkError = await detectNailsWithArk(
    makeArkInput((async () => {
      throw new Error("ECONNREFUSED");
    }) as typeof fetch)
  );
  assert.equal(networkError.status, "error");
  assert.ok(networkError.status === "error" && /网络异常/.test(networkError.message));
});

test("detectNailsWithArk reports abort as degraded/cancelled", async () => {
  const controller = new AbortController();
  controller.abort();
  const outcome = await detectNailsWithArk(
    makeArkInput((async () => {
      throw Object.assign(new Error("aborted"), { name: "AbortError" });
    }) as typeof fetch, { signal: controller.signal })
  );
  assert.equal(outcome.status, "degraded");
  assert.ok(outcome.status === "degraded" && outcome.reason === "cancelled");
});

// ── detectNailsWithCloudMatte ──

function makeAlphaGrid(): AlphaGrid {
  const width = 4;
  const height = 4;
  const alpha = new Uint8ClampedArray(width * height);
  const data = new Uint8Array(width * height);
  for (let y = 1; y < 3; y += 1) {
    for (let x = 1; x < 3; x += 1) {
      alpha[y * width + x] = 255;
      data[y * width + x] = 1;
    }
  }
  return { width, height, alpha, data };
}

test("detectNailsWithCloudMatte posts to the cloud endpoint and labels candidates cloud-matte", async () => {
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    calls.push({ url: String(url), body: JSON.parse(String(init?.body)) });
    return arkFetchResponse({
      width: 800,
      height: 600,
      instances: [
        { index: 0, box: [100, 100, 200, 200], bbox: [100, 100, 200, 200], area: 100, alphaPng: "data:image/png;base64,AAAA", width: 100, height: 100 },
      ],
      omittedInstances: 0,
    });
  }) as typeof fetch;
  try {
    const outcome = await detectNailsWithCloudMatte({
      image: { width: 800, height: 600 } as unknown as CanvasImageSource,
      imageWidth: 800,
      imageHeight: 600,
      encode: async () => "data:image/jpeg;base64,AAAA",
      decode: async () => makeAlphaGrid(),
    });
    assert.equal(outcome.status, "ok");
    assert.equal(calls.length, 1);
    assert.equal(calls[0]!.url, "/api/nail-matte-cloud");
    assert.equal(calls[0]!.body.task, "matting");
    assert.equal(calls[0]!.body.query, "nails");
    if (outcome.status !== "ok") throw new Error("unreachable");
    assert.equal(outcome.candidates.length, 1);
    assert.equal(outcome.candidates[0]!.source, "cloud-matte");
    assert.equal(outcome.candidates[0]!.confidence, "low");
    assert.match(outcome.candidates[0]!.id, /^cloud-matte-/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

// ── 共享换算 ──

test("nailCandidatesToDetectionRegions maps candidate fields onto frame inputs", () => {
  const candidate = candidateFromArkBox([100, 100, 200, 200], 1000, 1000, 0);
  assert.ok(candidate);
  const [region] = nailCandidatesToDetectionRegions([candidate!]);
  assert.equal(region!.id, candidate!.id);
  assert.equal(region!.nl, candidate!.length);
  assert.equal(region!.nw, candidate!.width);
  assert.equal(region!.confidence, "low");
  assert.equal(region!.source, "cloud-ark");
  assert.deepEqual(region!.warnings, ["needs_review"]);
});

test("cloudDetectMessageFromReason maps reasons to user-facing copy", () => {
  assert.equal(cloudDetectMessageFromReason("rate_limited", "fallback"), NAIL_DETECT_ERROR_MESSAGES.rate_limited);
  assert.equal(cloudDetectMessageFromReason("mystery", "fallback"), NAIL_DETECT_ERROR_MESSAGES.upstream);
});
