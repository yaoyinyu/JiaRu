/**
 * WeVisOne-VL 本机抠图服务的转发封装（服务端专用，勿在客户端组件引入）。
 *
 * 上游事实（`model/VlM_Model/server.py` / `matting.py`）：
 * - `POST /matte` 接受 `{ image | imagePath, task, query, boxes }`；
 *   `imagePath` 会直接打开本机文件，因此**本模块只允许 `image`**，
 *   payload 一律按白名单重建，绝不透传调用方 JSON。
 * - `GET /health` 返回 `{ ready, busy, model, quant, ... }`，不触发推理。
 * - 返回体含 VLM 文本 `response` 与 `metrics`，本模块只保留结构化字段。
 * - 单实例并发 1，忙时立即 503；单任务超时 120s。
 *
 * 边界：该能力为第三方通用模型辅助，不计正式识别成功率、不进训练真值、
 * 不写生产 manifest，也不改变 PRODUCT HOLD 状态。
 */

export type NailMatteTask = "matting" | "segmentation" | "visual_prompt";

export type NailMatteErrorReason =
  | "disabled"
  | "invalid_request"
  | "invalid_image"
  | "too_large"
  | "auth_misconfigured"
  | "busy"
  | "timeout"
  | "upstream_error";

/** 上游错误归一化：`statusCode` 为下游 HTTP 状态码，`reason` 为稳定机器标识。 */
export class NailMatteApiError extends Error {
  readonly statusCode: number;
  readonly reason: NailMatteErrorReason;
  readonly retryAfterSeconds: number | null;

  constructor(
    statusCode: number,
    reason: NailMatteErrorReason,
    message: string,
    retryAfterSeconds: number | null = null
  ) {
    super(message);
    this.name = "NailMatteApiError";
    this.statusCode = statusCode;
    this.reason = reason;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export type NailMatteBox = [number, number, number, number];

export interface NailMatteInstance {
  index: number;
  /** 原图像素坐标，来自上游 `box`（`box01 × 原图宽高`）。 */
  box: NailMatteBox;
  /** alpha>127 的外接框，用于二次裁剪。 */
  bbox: NailMatteBox;
  area: number;
  /** 整图尺寸的 mode L 灰度 PNG（data URI）。 */
  alphaPng: string;
  width: number;
  height: number;
}

export interface NailMatteResult {
  width: number;
  height: number;
  instances: NailMatteInstance[];
  /** 超过实例上限被截断的数量，不静默丢弃。 */
  omittedInstances: number;
  model: string;
  quant: "int4" | "none";
  elapsedMs: number;
}

export interface NailMatteRequest {
  image: string;
  task: NailMatteTask;
  query: string;
  boxes?: NailMatteBox[];
}

export interface NailMatteConfig {
  url: string;
  token: string;
}

export interface NailMatteEnv {
  VLM_MATTE_URL?: string;
  VLM_MATTE_TOKEN?: string;
}

/** 单次响应最多保留的实例数；超出部分只计数，不补齐、不按分数截断。 */
export const NAIL_MATTE_MAX_INSTANCES = 10;

const DEFAULT_TIMEOUT_MS = 150_000;
const HEALTH_TIMEOUT_MS = 1_500;
const ALPHA_DATA_URI_PATTERN = /^data:image\/png;base64,/i;

/** 读取配置；未配置 URL 视为能力关闭（入口不渲染）。 */
export function getNailMatteConfig(
  env: NailMatteEnv = process.env as NailMatteEnv
): NailMatteConfig | null {
  const url = (env.VLM_MATTE_URL ?? "").trim().replace(/\/+$/, "");
  if (!url) return null;
  return { url, token: (env.VLM_MATTE_TOKEN ?? "").trim() };
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asBox(value: unknown): NailMatteBox | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const numbers = value.map(asFiniteNumber);
  if (numbers.some((item) => item === null)) return null;
  return numbers as NailMatteBox;
}

/** 只接受 PNG data URI，避免把任意 URL 回传给前端。 */
function asAlphaPng(value: unknown): string | null {
  return typeof value === "string" && ALPHA_DATA_URI_PATTERN.test(value) ? value : null;
}

function normalizeInstances(raw: unknown): {
  instances: NailMatteInstance[];
  omittedInstances: number;
} {
  if (!Array.isArray(raw)) return { instances: [], omittedInstances: 0 };
  const parsed: NailMatteInstance[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const box = asBox(record.box);
    const bbox = asBox(record.bbox);
    const alphaPng = asAlphaPng(record.alphaPng);
    const width = asFiniteNumber(record.width);
    const height = asFiniteNumber(record.height);
    if (!box || !alphaPng || width === null || height === null) continue;
    parsed.push({
      index: asFiniteNumber(record.index) ?? parsed.length,
      box,
      bbox: bbox ?? box,
      area: asFiniteNumber(record.area) ?? 0,
      alphaPng,
      width: Math.round(width),
      height: Math.round(height),
    });
  }
  const instances = parsed.slice(0, NAIL_MATTE_MAX_INSTANCES);
  return { instances, omittedInstances: Math.max(0, parsed.length - instances.length) };
}

function mapStatusToError(status: number, body: unknown): NailMatteApiError {
  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const upstreamBusy = record.busy === true;
  const retryAfter = asFiniteNumber(record.retryAfterSeconds);

  if (status === 401 || status === 403) {
    return new NailMatteApiError(503, "auth_misconfigured", "抠图服务鉴权配置异常", null);
  }
  if (status === 400) {
    return new NailMatteApiError(400, "invalid_image", "图片无法处理，请更换更清晰的图片", null);
  }
  if (status === 413) {
    return new NailMatteApiError(413, "too_large", "图片体积超过服务上限，请压缩后重试", null);
  }
  if (status === 504) {
    return new NailMatteApiError(504, "timeout", "抠图服务处理超时", null);
  }
  if (status === 503) {
    return new NailMatteApiError(
      503,
      upstreamBusy || !record.error ? "busy" : "upstream_error",
      "抠图服务正在处理其他图片",
      retryAfter === null ? 3 : Math.min(30, Math.max(1, Math.round(retryAfter)))
    );
  }
  return new NailMatteApiError(502, "upstream_error", "抠图服务暂时不可用", null);
}

export interface NailMatteCallOptions {
  env?: NailMatteEnv;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

/**
 * 调用上游 `/matte`。
 * 请求体只由 `{ image, task, query, boxes }` 重建，`imagePath` 等字段不可达。
 */
export async function requestNailMatte(
  request: NailMatteRequest,
  options: NailMatteCallOptions = {}
): Promise<NailMatteResult> {
  const config = getNailMatteConfig(options.env);
  if (!config) {
    throw new NailMatteApiError(503, "disabled", "本机抠图服务未启用", null);
  }

  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const startedAt = Date.now();

  // 白名单重建：即使调用方传入 imagePath / 其他字段，也不会进入上游。
  const payload: Record<string, unknown> = {
    image: request.image,
    task: request.task,
    query: request.query,
  };
  if (request.boxes && request.boxes.length > 0) {
    payload.boxes = request.boxes.map((box) => [box[0], box[1], box[2], box[3]]);
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  let response: Response;
  try {
    response = await fetchImpl(`${config.url}/matte`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (err) {
    const aborted = timedOut || (err instanceof Error && err.name === "AbortError");
    if (aborted) {
      throw new NailMatteApiError(504, "timeout", "抠图服务处理超时", null);
    }
    throw new NailMatteApiError(502, "upstream_error", "抠图服务暂时不可用", null);
  } finally {
    clearTimeout(timer);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw mapStatusToError(response.status, body);
  }

  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const width = asFiniteNumber(record.width);
  const height = asFiniteNumber(record.height);
  if (width === null || height === null) {
    throw new NailMatteApiError(502, "upstream_error", "抠图服务返回格式异常", null);
  }

  const { instances, omittedInstances } = normalizeInstances(record.instances);
  const quant = record.quant === "none" ? "none" : "int4";

  return {
    width: Math.round(width),
    height: Math.round(height),
    instances,
    omittedInstances,
    model: typeof record.model === "string" ? record.model : "unknown",
    quant,
    elapsedMs: Date.now() - startedAt,
  };
}

export interface NailMatteHealth {
  ready: boolean;
  busy: boolean;
  model: string | null;
}

/**
 * 探测上游 `/health`（不触发推理）。
 * 未配置返回 null；不可达或超时返回 `{ ready:false, busy:false }`。
 */
export async function probeNailMatte(
  options: NailMatteCallOptions = {}
): Promise<NailMatteHealth | null> {
  const config = getNailMatteConfig(options.env);
  if (!config) return null;

  const fetchImpl = options.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? HEALTH_TIMEOUT_MS);

  try {
    const response = await fetchImpl(`${config.url}/health`, {
      method: "GET",
      headers: config.token ? { Authorization: `Bearer ${config.token}` } : {},
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) return { ready: false, busy: false, model: null };
    const body = (await response.json()) as Record<string, unknown>;
    return {
      ready: body.ready === true,
      busy: body.busy === true,
      model: typeof body.model === "string" ? body.model : null,
    };
  } catch {
    return { ready: false, busy: false, model: null };
  } finally {
    clearTimeout(timer);
  }
}
