import type { NailMask, NailTextureCandidate } from "./types.ts";
import type { NailMatteInstance, NailMatteResult } from "@/lib/nail-matte-api";
import {
  candidateBounds,
  matchMasksToCandidates,
  type Box,
  type MatchInstance,
} from "./mask-matching.ts";

/**
 * 本机精细抠图（WeVisOne-VL）的前端编排。
 *
 * 该能力是**辅助**：只把更精细的软边蒙版替换到既有候选上，
 * 不改变候选数量、指位推导、置信度等级与「需复核」语义。
 *
 * 数据流：原图压到长边 ≤1600 JPEG → /api/nail-matte → 整图 alpha PNG
 * → 取 R 通道 → 降采样到长边 ≤1024 → NailMask（含软 alpha）。
 */

/** 上传前的最长边上限：与上游 12MB 体积上限和 4096 硬限制留出双重余量。 */
export const MATTE_IMAGE_MAX_EDGE = 1600;
/** 本地持有的 alpha 栅格最长边上限：整图 alpha 原尺寸会到数 MB。 */
export const MATTE_ALPHA_MAX_EDGE = 1024;
/** 软边与二值几何的共享阈值（与上游 `matting.py` 的 solid 阈值一致）。 */
export const MATTE_ALPHA_THRESHOLD = 128;

export interface AlphaGrid {
  width: number;
  height: number;
  /** 0..255 软边权重 */
  alpha: Uint8ClampedArray;
  /** 0/1 二值几何（非零即前景） */
  data: Uint8Array;
}

/** 等比缩放到最长边不超过 `maxEdge` 的比例；已足够小返回 1。 */
export function computeScaleToMaxEdge(width: number, height: number, maxEdge: number): number {
  const longest = Math.max(width, height);
  if (!Number.isFinite(longest) || longest <= 0) return 1;
  if (longest <= maxEdge) return 1;
  return maxEdge / longest;
}

/**
 * 单通道灰度 PNG 在 canvas 中解码为 RGBA 后，灰度落在 **R 通道**，
 * A 通道恒为 255；取 A 会得到全 255，因此这里固定取 R。
 */
export function alphaGridFromRgba(
  rgba: Uint8ClampedArray | Uint8Array,
  width: number,
  height: number,
  threshold: number = MATTE_ALPHA_THRESHOLD
): AlphaGrid {
  const size = Math.max(0, Math.floor(width) * Math.floor(height));
  const alpha = new Uint8ClampedArray(size);
  const data = new Uint8Array(size);
  for (let index = 0; index < size; index += 1) {
    const value = rgba[index * 4] ?? 0;
    alpha[index] = value;
    data[index] = value >= threshold ? 1 : 0;
  }
  return { width: Math.floor(width), height: Math.floor(height), alpha, data };
}

/** 面积平均降采样；同时重算二值几何，避免 alpha 与 data 口径不一致。 */
export function downsampleAlphaGrid(
  grid: AlphaGrid,
  maxEdge: number = MATTE_ALPHA_MAX_EDGE,
  threshold: number = MATTE_ALPHA_THRESHOLD
): AlphaGrid {
  const scale = computeScaleToMaxEdge(grid.width, grid.height, maxEdge);
  if (scale >= 1) return grid;

  const targetWidth = Math.max(1, Math.round(grid.width * scale));
  const targetHeight = Math.max(1, Math.round(grid.height * scale));
  const alpha = new Uint8ClampedArray(targetWidth * targetHeight);
  const data = new Uint8Array(targetWidth * targetHeight);

  for (let y = 0; y < targetHeight; y += 1) {
    const sourceYStart = Math.floor((y * grid.height) / targetHeight);
    const sourceYEnd = Math.max(sourceYStart + 1, Math.floor(((y + 1) * grid.height) / targetHeight));
    for (let x = 0; x < targetWidth; x += 1) {
      const sourceXStart = Math.floor((x * grid.width) / targetWidth);
      const sourceXEnd = Math.max(
        sourceXStart + 1,
        Math.floor(((x + 1) * grid.width) / targetWidth)
      );
      let sum = 0;
      let count = 0;
      for (let sourceY = sourceYStart; sourceY < sourceYEnd; sourceY += 1) {
        if (sourceY >= grid.height) break;
        const rowOffset = sourceY * grid.width;
        for (let sourceX = sourceXStart; sourceX < sourceXEnd; sourceX += 1) {
          if (sourceX >= grid.width) break;
          sum += grid.alpha[rowOffset + sourceX] ?? 0;
          count += 1;
        }
      }
      const index = y * targetWidth + x;
      const value = count > 0 ? Math.round(sum / count) : 0;
      alpha[index] = value;
      data[index] = value >= threshold ? 1 : 0;
    }
  }

  return { width: targetWidth, height: targetHeight, alpha, data };
}

/**
 * 构造 `NailMask`：整图栅格，`origin` 恒 0，`scale` 与 `postprocess.ts` 同口径
 * （宽高两个比例取较大者）。`extractTextureFromMaskDetailed` 实际按
 * `imageWidth / mask.width` 映射，因此整图等比降采样不改变几何位置。
 */
export function nailMaskFromAlphaGrid(
  grid: AlphaGrid,
  imageWidth: number,
  imageHeight: number
): NailMask {
  return {
    width: grid.width,
    height: grid.height,
    data: grid.data,
    originX: 0,
    originY: 0,
    scale: Math.max(imageWidth / grid.width, imageHeight / grid.height),
    alpha: grid.alpha,
  };
}

export type NailMatteOutcome =
  | { status: "ok"; result: NailMatteResult }
  | { status: "degraded"; reason: string; message: string; retryAfterSeconds?: number }
  | { status: "error"; message: string };

export interface NailMatteAvailability {
  enabled: boolean;
  ready: boolean;
  busy: boolean;
}

/**
 * 读取入口可见性（GET 不触发推理）。
 * 未配置、网络异常、响应异常一律按「不可用」处理，绝不因探测失败展示入口。
 */
export async function fetchNailMatteAvailability(
  options: { fetchImpl?: typeof fetch } = {}
): Promise<NailMatteAvailability> {
  const fetchImpl = options.fetchImpl ?? fetch;
  try {
    const response = await fetchImpl("/api/nail-matte", { cache: "no-store" });
    if (!response.ok) return { enabled: false, ready: false, busy: false };
    const body = (await response.json()) as Record<string, unknown>;
    return {
      enabled: body.enabled === true,
      ready: body.ready === true,
      busy: body.busy === true,
    };
  } catch {
    return { enabled: false, ready: false, busy: false };
  }
}

/** 浏览器侧调用 `/api/nail-matte`；降级与错误都以返回值表达，不抛异常。 */
export async function requestNailMatteFromBrowser(
  input: { image: string; task: "matting" | "visual_prompt"; query?: string; boxes?: Box[] },
  options: { signal?: AbortSignal; fetchImpl?: typeof fetch } = {}
): Promise<NailMatteOutcome> {
  const fetchImpl = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl("/api/nail-matte", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return { status: "degraded", reason: "cancelled", message: "已取消精细抠图" };
    }
    return { status: "error", message: "网络异常，未能连接本机抠图服务" };
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (response.ok) {
    if (!body || typeof body !== "object") {
      return { status: "error", message: "抠图服务返回格式异常" };
    }
    return { status: "ok", result: body as NailMatteResult };
  }

  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const message = typeof record.error === "string" ? record.error : "抠图服务暂时不可用";
  if (record.degraded === true) {
    return {
      status: "degraded",
      reason: typeof record.reason === "string" ? record.reason : "upstream_error",
      message,
      retryAfterSeconds:
        typeof record.retryAfterSeconds === "number" ? record.retryAfterSeconds : undefined,
    };
  }
  return { status: "error", message };
}

/** 把原图压到长边 ≤1600 的 JPEG Data URI（仅用于本次请求）。 */
export async function encodeImageForMatte(
  image: CanvasImageSource,
  width: number,
  height: number
): Promise<string> {
  const scale = computeScaleToMaxEdge(width, height, MATTE_IMAGE_MAX_EDGE);
  const targetWidth = Math.max(1, Math.round(width * scale));
  const targetHeight = Math.max(1, Math.round(height * scale));

  const canvas = new OffscreenCanvas(targetWidth, targetHeight);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("offscreen_canvas_2d_unavailable");
  ctx.drawImage(image, 0, 0, targetWidth, targetHeight);

  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.85 });
  const buffer = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let offset = 0; offset < buffer.length; offset += chunk) {
    binary += String.fromCharCode(...buffer.subarray(offset, offset + chunk));
  }
  return `data:image/jpeg;base64,${btoa(binary)}`;
}

/** 解码整图 alpha PNG 并降采样为本地栅格。 */
export async function decodeAlphaPngToGrid(
  alphaPng: string,
  maxEdge: number = MATTE_ALPHA_MAX_EDGE
): Promise<AlphaGrid> {
  const response = await fetch(alphaPng);
  const blob = await response.blob();
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("offscreen_canvas_2d_unavailable");
    ctx.drawImage(bitmap, 0, 0);
    const imageData = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
    const grid = alphaGridFromRgba(imageData.data, bitmap.width, bitmap.height);
    return downsampleAlphaGrid(grid, maxEdge);
  } finally {
    bitmap.close();
  }
}

export type MatteRefinementOutcome =
  | {
      status: "ok";
      masks: Array<{ candidateId: string; mask: NailMask }>;
      matchedCount: number;
      candidateCount: number;
      instanceCount: number;
      omittedInstances: number;
      elapsedMs: number;
      warnings: string[];
    }
  | { status: "degraded"; reason: string; message: string; retryAfterSeconds?: number }
  | { status: "error"; message: string };

export interface MatteRefineInput {
  image: CanvasImageSource;
  imageWidth: number;
  imageHeight: number;
  candidates: NailTextureCandidate[];
  signal?: AbortSignal;
  encode?: typeof encodeImageForMatte;
  decode?: typeof decodeAlphaPngToGrid;
  request?: typeof requestNailMatteFromBrowser;
}

/**
 * refine 主路径：以文本提示 `matting` 请求整图软 alpha，再按几何一一匹配回候选。
 *
 * 不使用 `visual_prompt`：2026-10-28 本机实测该模式对同一原图（像素框/归一化框/
 * 0-1000 网格框/不带框四种写法）恒定返回 0 实例，而 `matting` 正常产出。
 * 匹配用「中心归属优先、IoU≥0.15 兜底」，因为本地候选外接框来自几何推导，比上游更松。
 * 未命中实例直接丢弃；未命中候选由调用方保留原结果。
 */
export async function refineCandidateMasksWithMatte(
  input: MatteRefineInput
): Promise<MatteRefinementOutcome> {
  const candidates = input.candidates.filter((candidate) => candidate);
  if (candidates.length === 0) {
    return { status: "error", message: "当前没有可精细处理的甲面候选" };
  }

  const encode = input.encode ?? encodeImageForMatte;
  const decode = input.decode ?? decodeAlphaPngToGrid;
  const request = input.request ?? requestNailMatteFromBrowser;

  const image = await encode(input.image, input.imageWidth, input.imageHeight);
  const boxes: Box[] = candidates.map((candidate) => candidateBounds(candidate));

  const outcome = await request(
    { image, task: "matting", query: "指甲" },
    { signal: input.signal }
  );
  if (outcome.status !== "ok") return outcome;

  const { result } = outcome;
  const instances: MatchInstance[] = result.instances.map((instance) => ({
    index: instance.index,
    box: instance.box,
  }));
  const matches = matchMasksToCandidates(
    candidates.map((candidate, index) => ({ id: candidate.id, box: boxes[index] })),
    instances
  );

  const instanceByIndex = new Map<number, NailMatteInstance>(
    result.instances.map((instance) => [instance.index, instance])
  );

  const masks: Array<{ candidateId: string; mask: NailMask }> = [];
  for (const match of matches.matches) {
    const instance = instanceByIndex.get(match.instanceIndex);
    if (!instance) continue;
    const grid = await decode(instance.alphaPng);
    masks.push({
      candidateId: match.candidateId,
      mask: nailMaskFromAlphaGrid(grid, input.imageWidth, input.imageHeight),
    });
  }

  const warnings: string[] = [];
  if (result.instances.length === 0) warnings.push("matte_no_instances");
  if (masks.length === 0 && result.instances.length > 0) warnings.push("matte_no_match");
  if (matches.unmatchedCandidateIds.length > 0) warnings.push("matte_partial_match");
  if (matches.unmatchedInstanceIndexes.length > 0) warnings.push("matte_unmatched_instance");
  if (result.omittedInstances > 0) warnings.push("matte_truncated");

  return {
    status: "ok",
    masks,
    matchedCount: masks.length,
    candidateCount: candidates.length,
    instanceCount: result.instances.length,
    omittedInstances: result.omittedInstances,
    elapsedMs: result.elapsedMs,
    warnings,
  };
}

export type MatteDetectOutcome =
  | { status: "ok"; candidates: NailTextureCandidate[]; instanceCount: number; omittedInstances: number }
  | { status: "degraded"; reason: string; message: string; retryAfterSeconds?: number }
  | { status: "error"; message: string };

export interface MatteDetectInput {
  image: CanvasImageSource;
  imageWidth: number;
  imageHeight: number;
  signal?: AbortSignal;
  encode?: typeof encodeImageForMatte;
  decode?: typeof decodeAlphaPngToGrid;
  request?: typeof requestNailMatteFromBrowser;
}

/** 由上游实例构造低置信候选：几何取 alpha 外接框，角度 0，来源标注为 vlm-matte。 */
export function candidateFromMatteInstance(
  instance: NailMatteInstance,
  grid: AlphaGrid,
  imageWidth: number,
  imageHeight: number
): NailTextureCandidate {
  const box = instance.bbox[2] > instance.bbox[0] ? instance.bbox : instance.box;
  const cx = (box[0] + box[2]) / 2;
  const cy = (box[1] + box[3]) / 2;
  const width = Math.max(1, box[2] - box[0]);
  const length = Math.max(1, box[3] - box[1]);
  return {
    id: `vlm-matte-${instance.index}`,
    cx,
    cy,
    length,
    width,
    angle: 0,
    score: 0.2,
    confidence: "low",
    source: "vlm-matte",
    mask: nailMaskFromAlphaGrid(grid, imageWidth, imageHeight),
    warnings: ["needs_review"],
    suggestedFinger: null,
  };
}

/**
 * detect 兜底：本地 0 候选时请求一次纯文本抠图。
 * 返回的候选一律 `confidence: "low"`，必须由用户逐指确认后才能提取。
 */
export async function detectNailsWithMatte(input: MatteDetectInput): Promise<MatteDetectOutcome> {
  const encode = input.encode ?? encodeImageForMatte;
  const decode = input.decode ?? decodeAlphaPngToGrid;
  const request = input.request ?? requestNailMatteFromBrowser;

  const image = await encode(input.image, input.imageWidth, input.imageHeight);
  const outcome = await request({ image, task: "matting", query: "指甲" }, { signal: input.signal });
  if (outcome.status !== "ok") return outcome;

  const { result } = outcome;
  const candidates: NailTextureCandidate[] = [];
  for (const instance of result.instances) {
    const grid = await decode(instance.alphaPng);
    candidates.push(candidateFromMatteInstance(instance, grid, input.imageWidth, input.imageHeight));
  }

  return {
    status: "ok",
    candidates,
    instanceCount: result.instances.length,
    omittedInstances: result.omittedInstances,
  };
}
