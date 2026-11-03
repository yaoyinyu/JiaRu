/**
 * 火山方舟（Volcengine Ark）视觉理解模型甲面检测 API 客户端（v1.2.216）。
 *
 * 与 Seedream 生图客户端（seedream-image-api.ts）共用方舟接入约定：
 * - 端点：POST {baseUrl}/chat/completions，Bearer 鉴权，HTTPS 强制。
 * - 密钥复用 `VOLCENGINE_ARK_API_KEY`；模型经 `ARK_VISION_MODEL` 配置
 *   （如 doubao-1.6-vision-pro-<版本后缀>，须在方舟控制台开通）。
 * - 输出：**编码图坐标域**的像素框列表（客户端编码长边 ≤1600，服务端只做
 *   形状校验与上限截断，坐标→原图映射在浏览器 `nail-cloud-detect.ts`）。
 * - 429/500/503 指数退避；错误归一为 `ArkDetectApiError`，正文不含密钥与堆栈。
 *
 * 用途边界：仅作甲面辅助定位候选来源（固定低置信、须人工复核），
 * 不参与正式识别质量口径（PRODUCT HOLD 不变）。
 */
import { DEFAULT_ARK_BASE_URL } from "./seedream-image-api.ts";

const DEFAULT_TIMEOUT_MS = 120_000;
const DEFAULT_MAX_ATTEMPTS = 4;
const DEFAULT_RETRY_DELAY_MS = 1_000;
const RETRYABLE_STATUS_CODES = new Set([429, 500, 503]);
/** 单图甲面框上限（与 matte 实例上限同口径）。 */
export const ARK_DETECT_MAX_BOXES = 10;

type Environment = Record<string, string | undefined>;

export class ArkDetectApiError extends Error {
  readonly statusCode: number;
  readonly reason: string;
  readonly retryAfterSeconds: number | null;

  constructor(
    message: string,
    statusCode: number,
    reason: string,
    retryAfterSeconds: number | null = null
  ) {
    super(message);
    this.name = "ArkDetectApiError";
    this.statusCode = statusCode;
    this.reason = reason;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export interface ArkDetectConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
}

/** 配置是否齐备（GET enabled 探测用；不校验 HTTPS 等运行时细节）。 */
export function isArkDetectEnabled(env: Environment = process.env): boolean {
  const apiKey = env.VOLCENGINE_ARK_API_KEY?.trim();
  const model = env.ARK_VISION_MODEL?.trim();
  return Boolean(apiKey && apiKey !== "your-key-here" && model);
}

export function getArkDetectConfig(env: Environment = process.env): ArkDetectConfig {
  const apiKey = env.VOLCENGINE_ARK_API_KEY?.trim();
  if (!apiKey || apiKey === "your-key-here") {
    throw new ArkDetectApiError("服务器未配置 VOLCENGINE_ARK_API_KEY，请联系管理员", 503, "disabled");
  }
  const model = env.ARK_VISION_MODEL?.trim();
  if (!model) {
    throw new ArkDetectApiError("服务器未配置 ARK_VISION_MODEL，请联系管理员", 503, "disabled");
  }

  const configuredBaseUrl = env.ARK_BASE_URL?.trim() || DEFAULT_ARK_BASE_URL;
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(configuredBaseUrl);
  } catch {
    throw new ArkDetectApiError("ARK_BASE_URL 配置无效", 503, "disabled");
  }
  if (parsedBaseUrl.protocol !== "https:") {
    throw new ArkDetectApiError("ARK_BASE_URL 必须使用 HTTPS", 503, "disabled");
  }
  if (parsedBaseUrl.username || parsedBaseUrl.password) {
    throw new ArkDetectApiError("ARK_BASE_URL 不得包含认证信息", 503, "disabled");
  }

  return { apiKey, baseUrl: parsedBaseUrl.toString().replace(/\/+$/, ""), model };
}

/** 系统提示词：只输出 JSON，角色为甲面定位。 */
export const ARK_DETECT_SYSTEM_PROMPT =
  "你是美甲图像分析助手，任务是定位图片中所有清晰可见的指甲甲面。" +
  "只输出一个 JSON 对象，不要输出任何解释、注释或 Markdown 代码块以外的文字。";

/** 构造用户提示词：像素坐标框 + 数量上限 + 输出格式约定。 */
export function buildArkDetectUserPrompt(imageWidth: number, imageHeight: number): string {
  return (
    `图片尺寸为 ${imageWidth}x${imageHeight} 像素。` +
    "请定位图中所有清晰可见的指甲甲面（含美甲款式与裸甲），为每个甲面输出一个紧贴甲面边缘的矩形框 " +
    "[x1,y1,x2,y2]，使用像素坐标且 x2>x1、y2>y1。" +
    "忽略手指皮肤、饰品、背景与模糊不可辨认的区域；最多输出 10 个框，按可见置信度从高到低排列。" +
    '输出格式：{"nails":[{"box":[x1,y1,x2,y2]}]}'
  );
}

/** 剥离 Markdown 围栏并截取最外层 JSON 对象。 */
function extractJsonText(content: string): string {
  let text = content.trim();
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced && fenced[1]) text = fenced[1].trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) text = text.slice(start, end + 1);
  return text;
}

/** 解析模型输出为像素框列表；形状不合法的框剔除，超限截断。 */
export function parseArkDetectBoxes(content: string): number[][] {
  const parsed: unknown = JSON.parse(extractJsonText(content));
  const nails = (parsed as { nails?: unknown })?.nails;
  if (!Array.isArray(nails)) return [];
  const boxes: number[][] = [];
  for (const entry of nails) {
    if (boxes.length >= ARK_DETECT_MAX_BOXES) break;
    if (!entry || typeof entry !== "object") continue;
    const box = (entry as { box?: unknown }).box;
    if (!Array.isArray(box) || box.length !== 4) continue;
    const numbers = box.map((v) => (typeof v === "number" ? v : Number.NaN));
    if (numbers.some((v) => !Number.isFinite(v))) continue;
    const [x1, y1, x2, y2] = numbers;
    if (x2 <= x1 || y2 <= y1) continue;
    boxes.push([x1, y1, x2, y2]);
  }
  return boxes;
}

async function readProviderError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;
  try {
    const parsed = JSON.parse(text);
    const message = parsed?.error?.message ?? parsed?.message;
    if (typeof message === "string" && message.trim()) return message.trim().slice(0, 500);
  } catch {
    // 非 JSON 错误体继续使用截断文本。
  }
  return text.trim().slice(0, 500) || `HTTP ${response.status}`;
}

function wait(milliseconds: number): Promise<void> {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

export interface ArkDetectRequest {
  /** 编码图 Data URI（data:image/jpeg;base64,...，长边 ≤1600，客户端编码）。 */
  imageDataUri: string;
  /** 编码图宽高（提示词声明尺寸用）。 */
  imageWidth: number;
  imageHeight: number;
  env?: Environment;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxAttempts?: number;
  retryDelayMs?: number;
}

export interface ArkDetectSuccess {
  boxes: number[][];
  model: string;
  elapsedMs: number;
}

/** 调用方舟视觉理解模型识别甲面框；失败抛 ArkDetectApiError（正文脱敏）。 */
export async function detectNailsWithArkModel(request: ArkDetectRequest): Promise<ArkDetectSuccess> {
  const config = getArkDetectConfig(request.env ?? process.env);
  const fetchImpl = request.fetchImpl ?? fetch;
  const timeoutMs = request.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxAttempts = request.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  const retryDelayMs = request.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;

  const body = {
    model: config.model,
    messages: [
      { role: "system", content: ARK_DETECT_SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: buildArkDetectUserPrompt(request.imageWidth, request.imageHeight) },
          { type: "image_url", image_url: { url: request.imageDataUri } },
        ],
      },
    ],
    temperature: 0,
    max_tokens: 1000,
  };

  const startedAt = Date.now();
  let lastError: ArkDetectApiError = new ArkDetectApiError(
    "云端识别服务暂时不可用",
    502,
    "upstream"
  );

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetchImpl(`${config.baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${config.apiKey}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      clearTimeout(timer);
      lastError = new ArkDetectApiError("云端识别服务连接失败", 504, "timeout");
      if (attempt < maxAttempts) {
        await wait(retryDelayMs * 2 ** (attempt - 1));
        continue;
      }
      throw lastError;
    }
    clearTimeout(timer);

    if (response.ok) {
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        throw new ArkDetectApiError("云端识别返回格式异常", 502, "upstream");
      }
      const content = (payload as { choices?: Array<{ message?: { content?: unknown } }> })
        ?.choices?.[0]?.message?.content;
      const contentText = typeof content === "string" ? content : "";
      let boxes: number[][];
      try {
        boxes = parseArkDetectBoxes(contentText);
      } catch {
        throw new ArkDetectApiError("云端识别返回内容无法解析", 502, "upstream");
      }
      return {
        boxes,
        model: config.model,
        elapsedMs: Date.now() - startedAt,
      };
    }

    const providerMessage = await readProviderError(response);
    if (RETRYABLE_STATUS_CODES.has(response.status) && attempt < maxAttempts) {
      const retryAfterHeader = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
      const backoff = Number.isFinite(retryAfterHeader)
        ? retryAfterHeader * 1000
        : retryDelayMs * 2 ** (attempt - 1);
      await wait(backoff);
      continue;
    }

    if (response.status === 429) {
      const retryAfterHeader = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
      throw new ArkDetectApiError(
        "云端识别请求过于频繁，请稍后再试",
        429,
        "rate_limited",
        Number.isFinite(retryAfterHeader) ? retryAfterHeader : null
      );
    }
    if (response.status === 401 || response.status === 403) {
      throw new ArkDetectApiError("云端识别鉴权未通过，请检查服务端配置", 503, "auth_misconfigured");
    }
    throw new ArkDetectApiError(providerMessage, response.status === 400 ? 400 : 502, "upstream");
  }

  throw lastError;
}
