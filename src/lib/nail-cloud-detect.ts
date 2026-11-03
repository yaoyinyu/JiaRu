/**
 * 云端识别（v1.2.216）：把云端后端返回的甲面元素统一映射为既有候选结构。
 *
 * - `detectNailsWithArk`：方舟视觉理解模型返回像素框 → 轴对齐低置信候选（矩形 mask）。
 * - `detectNailsWithCloudMatte`：云端自托管 /matte 契约 → 复用 `detectNailsWithMatte`
 *   全部换算逻辑（仅替换端点与来源标注）。
 *
 * 云端候选一律 `confidence:"low"` + `warnings:["needs_review"]`，只作辅助定位：
 * 编辑器须逐指核对，AR 复核门按低置信进复核态，正式识别口径不受影响。
 * 降级 / 错误 / 中止一律由调用方保留本地结果。
 */
import {
  computeMatteEncodeGeometry,
  detectNailsWithMatte,
  encodeImageForMatte,
  requestNailMatteFromBrowser,
  type MatteDetectOutcome,
  type MatteDetectInput,
} from "./nail-texture-recognition/vlm-refinement.ts";
import type {
  NailMask,
  NailTextureCandidate,
  NailTextureCandidateSource,
} from "./nail-texture-recognition/types.ts";
import { classifyNailDetectError, NAIL_DETECT_ERROR_MESSAGES } from "./nail-detect-mode.ts";

/** 云端 matte 契约路由（与 /api/nail-matte 同构，配置指向云端自托管服务）。 */
export const NAIL_CLOUD_MATTE_ENDPOINT = "/api/nail-matte-cloud";

/** 方舟视觉识别路由。 */
export const NAIL_DETECT_ARK_ENDPOINT = "/api/nail-detect-ark";

/** 矩形 mask 栅格的最长边（矩形无细节需求，取小栅格控制内存）。 */
const RECT_MASK_MAX_EDGE = 256;

/** 单图云端候选上限（与 matte 实例上限同口径）。 */
export const NAIL_CLOUD_MAX_CANDIDATES = 10;

/** 小于该边长（原图像素）的框视为噪声剔除。 */
export const NAIL_CLOUD_MIN_BOX_PX = 8;

export type ArkDetectOutcome =
  | { status: "ok"; candidates: NailTextureCandidate[]; model: string; elapsedMs: number }
  | { status: "degraded"; reason: string; message: string; retryAfterSeconds?: number }
  | { status: "error"; message: string };

export interface ArkDetectInput {
  image: CanvasImageSource;
  imageWidth: number;
  imageHeight: number;
  signal?: AbortSignal;
  encode?: typeof encodeImageForMatte;
  fetchImpl?: typeof fetch;
}

/** 两轴IoU（同坐标域）；任一面积为 0 时按 0 处理。 */
function boxIoU(
  a: { x1: number; y1: number; x2: number; y2: number },
  b: { x1: number; y1: number; x2: number; y2: number }
): number {
  const interX = Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1);
  const interY = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1);
  if (interX <= 0 || interY <= 0) return 0;
  const inter = interX * interY;
  const areaA = (a.x2 - a.x1) * (a.y2 - a.y1);
  const areaB = (b.x2 - b.x1) * (b.y2 - b.y1);
  const union = areaA + areaB - inter;
  return union > 0 ? inter / union : 0;
}

/**
 * 由矩形框构造整图栅格 mask：实心区域即框内（用于提取矩形纹理，
 * 后续可用本机「精细处理」按 matting 整图软 alpha 精化）。
 */
export function rectMaskFromBox(
  box: { x1: number; y1: number; x2: number; y2: number },
  imageWidth: number,
  imageHeight: number
): NailMask {
  const scale = Math.min(1, RECT_MASK_MAX_EDGE / Math.max(imageWidth, imageHeight));
  const gridWidth = Math.max(1, Math.round(imageWidth * scale));
  const gridHeight = Math.max(1, Math.round(imageHeight * scale));
  const data = new Uint8Array(gridWidth * gridHeight);
  const alpha = new Uint8ClampedArray(gridWidth * gridHeight);
  const minX = Math.max(0, Math.floor(box.x1 * scale));
  const minY = Math.max(0, Math.floor(box.y1 * scale));
  const maxX = Math.min(gridWidth - 1, Math.ceil(box.x2 * scale) - 1);
  const maxY = Math.min(gridHeight - 1, Math.ceil(box.y2 * scale) - 1);
  for (let y = minY; y <= maxY; y += 1) {
    const rowOffset = y * gridWidth;
    for (let x = minX; x <= maxX; x += 1) {
      data[rowOffset + x] = 1;
      alpha[rowOffset + x] = 255;
    }
  }
  // 与 nailMaskFromAlphaGrid 同口径：整图栅格、origin 0、scale 取两轴较大比例。
  return {
    width: gridWidth,
    height: gridHeight,
    data,
    originX: 0,
    originY: 0,
    scale: Math.max(imageWidth / gridWidth, imageHeight / gridHeight),
    alpha,
  };
}

/**
 * 编码图坐标域的框 → 原图坐标域的低置信候选（轴对齐、矩形 mask）。
 * 编码几何必须与 encodeImageForMatte 同源（computeMatteEncodeGeometry），
 * 否则长边 >1600 图片的候选会整体缩聚在左上角。
 */
export function candidateFromArkBox(
  box: readonly number[],
  imageWidth: number,
  imageHeight: number,
  index: number
): NailTextureCandidate | null {
  if (box.length !== 4 || box.some((v) => typeof v !== "number" || !Number.isFinite(v))) return null;
  const geometry = computeMatteEncodeGeometry(imageWidth, imageHeight);
  const scaleX = imageWidth / geometry.width;
  const scaleY = imageHeight / geometry.height;
  const x1 = Math.max(0, Math.min(box[0] * scaleX, imageWidth));
  const y1 = Math.max(0, Math.min(box[1] * scaleY, imageHeight));
  const x2 = Math.max(0, Math.min(box[2] * scaleX, imageWidth));
  const y2 = Math.max(0, Math.min(box[3] * scaleY, imageHeight));
  const width = Math.max(1, x2 - x1);
  const length = Math.max(1, y2 - y1);
  if (width < NAIL_CLOUD_MIN_BOX_PX || length < NAIL_CLOUD_MIN_BOX_PX) return null;
  return {
    id: `cloud-ark-${index}`,
    cx: (x1 + x2) / 2,
    cy: (y1 + y2) / 2,
    length,
    width,
    // 框不带旋转信息：轴对齐候选，方向由用户旋转或复核阶段纠正。
    angle: 0,
    score: 0.2,
    confidence: "low",
    source: "cloud-ark",
    mask: rectMaskFromBox({ x1, y1, x2, y2 }, imageWidth, imageHeight),
    warnings: ["needs_review"],
    suggestedFinger: null,
  };
}

/** 服务端返回的框列表 → 去重（IoU>0.9）、剔噪、封顶后的候选列表。 */
export function mapArkBoxesToCandidates(
  boxes: unknown,
  imageWidth: number,
  imageHeight: number
): NailTextureCandidate[] {
  if (!Array.isArray(boxes)) return [];
  const candidates: NailTextureCandidate[] = [];
  const accepted: Array<{ x1: number; y1: number; x2: number; y2: number }> = [];
  for (const raw of boxes) {
    if (candidates.length >= NAIL_CLOUD_MAX_CANDIDATES) break;
    if (!Array.isArray(raw)) continue;
    const candidate = candidateFromArkBox(raw as readonly number[], imageWidth, imageHeight, candidates.length);
    if (!candidate) continue;
    const box = { x1: candidate.cx - candidate.width / 2, y1: candidate.cy - candidate.length / 2, x2: candidate.cx + candidate.width / 2, y2: candidate.cy + candidate.length / 2 };
    if (accepted.some((existing) => boxIoU(existing, box) > 0.9)) continue;
    accepted.push(box);
    candidate.id = `cloud-ark-${candidates.length}`;
    candidates.push(candidate);
  }
  return candidates;
}

/**
 * 方舟视觉识别：编码（与 matte 同一 ≤1600 JPEG 链路）→ /api/nail-detect-ark → 候选。
 * 降级 / 错误以返回值表达，不抛异常；中止返回 degraded/cancelled。
 */
export async function detectNailsWithArk(input: ArkDetectInput): Promise<ArkDetectOutcome> {
  const encode = input.encode ?? encodeImageForMatte;
  const fetchImpl = input.fetchImpl ?? fetch;
  let image: string;
  try {
    image = await encode(input.image, input.imageWidth, input.imageHeight);
  } catch {
    return { status: "error", message: "照片编码失败，无法进行云端识别。" };
  }

  let response: Response;
  try {
    // 编码图坐标域尺寸随请求声明（与 encodeImageForMatte 同源几何），
    // 服务端用它构造提示词坐标域；框映射回原图在本模块完成。
    const geometry = computeMatteEncodeGeometry(input.imageWidth, input.imageHeight);
    response = await fetchImpl(NAIL_DETECT_ARK_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image, width: geometry.width, height: geometry.height }),
      signal: input.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return {
        status: "degraded",
        reason: "cancelled",
        message: NAIL_DETECT_ERROR_MESSAGES.cancelled,
      };
    }
    return { status: "error", message: NAIL_DETECT_ERROR_MESSAGES.network };
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;

  if (!response.ok) {
    const message = typeof record.error === "string" ? record.error : NAIL_DETECT_ERROR_MESSAGES.upstream;
    if (record.degraded === true) {
      return {
        status: "degraded",
        reason: typeof record.reason === "string" ? record.reason : "upstream",
        message,
        retryAfterSeconds:
          typeof record.retryAfterSeconds === "number" ? record.retryAfterSeconds : undefined,
      };
    }
    return { status: "error", message };
  }

  const boxes = record.boxes;
  const candidates = mapArkBoxesToCandidates(boxes, input.imageWidth, input.imageHeight);
  return {
    status: "ok",
    candidates,
    model: typeof record.model === "string" ? record.model : "unknown",
    elapsedMs: typeof record.elapsedMs === "number" ? record.elapsedMs : 0,
  };
}

/** 云端 matte 识别输入：与本地 detect 相同，但端点与来源固定为云端口径。 */
export type CloudMatteDetectInput = Omit<MatteDetectInput, "request" | "source">;

/**
 * 云端自托管 matte 识别：完整复用 `detectNailsWithMatte` 的编码、实例换算、
 * 低置信标注逻辑，仅把请求端点替换为 /api/nail-matte-cloud、来源标注 cloud-matte。
 */
export async function detectNailsWithCloudMatte(input: CloudMatteDetectInput): Promise<MatteDetectOutcome> {
  return detectNailsWithMatte({
    ...input,
    source: "cloud-matte" satisfies NailTextureCandidateSource,
    request: (req, options) =>
      requestNailMatteFromBrowser(req, { ...options, endpoint: NAIL_CLOUD_MATTE_ENDPOINT }),
  });
}

/** 把候选统一换算为编辑器甲面框（与页面内联换算同构，供云端路径复用）。 */
export function nailCandidatesToDetectionRegions(
  candidates: NailTextureCandidate[]
): Array<{
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
  confidence: "low";
  source: NailTextureCandidateSource;
  mask?: NailMask;
  warnings: string[];
}> {
  return candidates.map((candidate) => ({
    id: candidate.id,
    cx: candidate.cx,
    cy: candidate.cy,
    angle: candidate.angle,
    nl: candidate.length,
    nw: candidate.width,
    assignedFinger: candidate.suggestedFinger,
    confidence: "low" as const,
    source: candidate.source,
    mask: candidate.mask,
    warnings: [...(candidate.warnings ?? [])],
  }));
}

/** 云端降级 / 错误 → 用户可见文案（与 nail-detect-mode 的错误分类对齐）。 */
export function cloudDetectMessageFromReason(reason: string | null | undefined, fallback: string): string {
  return NAIL_DETECT_ERROR_MESSAGES[classifyNailDetectError(reason)] ?? fallback;
}
