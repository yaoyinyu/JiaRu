/**
 * 火山方舟（Volcengine Ark）Seedream 图片生成 API 客户端。
 *
 * 与 Agnes 客户端（agnes-image-api.ts）完全独立，协议差异：
 * - 端点：POST {baseUrl}/images/generations，Bearer 鉴权。
 * - Body 为扁平结构（无 extra_body 包装），字段全在顶层。
 * - 无独立 ratio 参数：宽高比通过显式宽高像素值（size: "WxH"）表达。
 * - 错误为顶层 error{code,message}；429/500/503 可退避重试。
 * - watermark 默认关闭（美甲设计导出场景），可用 ARK_IMAGE_WATERMARK 开启。
 */

export const DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";

const DEFAULT_TIMEOUT_MS = 240_000;
const DEFAULT_MAX_ATTEMPTS = 4;
const DEFAULT_RETRY_DELAY_MS = 1_000;

/** 可退避重试的响应状态码（限流 / 供应商内部错误 / 暂不可用）。 */
const RETRYABLE_STATUS_CODES = new Set([429, 500, 503]);

type Environment = Record<string, string | undefined>;

export type SeedreamModelKind = "pro" | "lite";

type GenerateSeedreamImageOptions = {
  env?: Environment;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxAttempts?: number;
  retryDelayMs?: number;
  /** 模型类别：pro / lite（决定读取哪个 Model ID 环境变量）。 */
  model: SeedreamModelKind;
  /** 可选图生图输入：Data URI（data:image/...;base64,...）。提供后走图生图。 */
  imageDataUri?: string;
  /** 显式宽高像素值（如 "2048x2048"），由 seedream-image-size 换算得出。 */
  pixelSize: string;
  /** 是否添加"AI 生成"水印，默认 false。 */
  watermark?: boolean;
};

type SeedreamImageConfig = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export class SeedreamImageApiError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "SeedreamImageApiError";
    this.statusCode = statusCode;
  }
}

/** 各模型类别对应的 Model ID 环境变量名（文档：Model ID 需在控制台查询）。 */
const MODEL_ENV_KEYS: Record<SeedreamModelKind, string> = {
  pro: "ARK_SEEDREAM_PRO_MODEL",
  lite: "ARK_SEEDREAM_LITE_MODEL",
};

export function getSeedreamImageConfig(
  kind: SeedreamModelKind,
  env: Environment = process.env
): SeedreamImageConfig {
  const apiKey = env.VOLCENGINE_ARK_API_KEY?.trim();
  if (!apiKey || apiKey === "your-key-here") {
    throw new SeedreamImageApiError(
      "服务器未配置 VOLCENGINE_ARK_API_KEY，请联系管理员",
      503
    );
  }

  const model = env[MODEL_ENV_KEYS[kind]]?.trim();
  if (!model) {
    throw new SeedreamImageApiError(
      `服务器未配置 ${MODEL_ENV_KEYS[kind]}，请联系管理员`,
      503
    );
  }

  const configuredBaseUrl = env.ARK_BASE_URL?.trim() || DEFAULT_ARK_BASE_URL;
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(configuredBaseUrl);
  } catch {
    throw new SeedreamImageApiError("ARK_BASE_URL 配置无效", 503);
  }

  if (parsedBaseUrl.protocol !== "https:") {
    throw new SeedreamImageApiError("ARK_BASE_URL 必须使用 HTTPS", 503);
  }
  if (parsedBaseUrl.username || parsedBaseUrl.password) {
    throw new SeedreamImageApiError("ARK_BASE_URL 不得包含认证信息", 503);
  }

  return {
    apiKey,
    baseUrl: parsedBaseUrl.toString().replace(/\/+$/, ""),
    model,
  };
}

async function readProviderError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;

  try {
    const parsed = JSON.parse(text);
    // Ark 错误体为顶层 error{code, message}。
    const message = parsed?.error?.message ?? parsed?.message;
    if (typeof message === "string" && message.trim()) {
      return message.trim().slice(0, 500);
    }
  } catch {
    // 非 JSON 响应继续使用截断后的纯文本。
  }

  return text.trim().slice(0, 500) || `HTTP ${response.status}`;
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, milliseconds));
}

/** 水印取值优先级：调用方显式指定 > ARK_IMAGE_WATERMARK 环境变量 > 默认关闭。 */
function resolveWatermark(env: Environment, override?: boolean): boolean {
  if (override !== undefined) return override;
  return env.ARK_IMAGE_WATERMARK?.trim().toLowerCase() === "true";
}

export async function generateSeedreamImage(
  prompt: string,
  options: GenerateSeedreamImageOptions
) {
  const config = getSeedreamImageConfig(options.model, options.env);
  const endpoint = `${config.baseUrl}/images/generations`;
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  const retryDelayMs = options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  const watermark = resolveWatermark(options.env, options.watermark);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  // Ark 扁平 body：所有字段位于顶层，禁止沿用 Agnes 的 extra_body 包装。
  const requestBody: Record<string, unknown> = {
    model: config.model,
    prompt,
    size: options.pixelSize,
    response_format: "url",
    watermark,
  };
  if (options.imageDataUri) {
    requestBody.image = options.imageDataUri;
  }

  try {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const response = await fetchImpl(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${config.apiKey}`,
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (RETRYABLE_STATUS_CODES.has(response.status) && attempt + 1 < maxAttempts) {
        await response.arrayBuffer();
        await wait(retryDelayMs * 2 ** attempt);
        continue;
      }

      if (!response.ok) {
        const providerMessage = await readProviderError(response);
        if (response.status === 401) {
          throw new SeedreamImageApiError("火山方舟 API Key 无效", 401);
        }
        if (response.status === 429) {
          throw new SeedreamImageApiError(
            "火山方舟 API 调用频率过高，请稍后再试",
            429
          );
        }
        throw new SeedreamImageApiError(
          `火山方舟 API 错误: ${providerMessage}`,
          502
        );
      }

      const data = await response.json();
      // 单图场景防御：若首项返回 error 则视为失败。
      const firstItem = data?.data?.[0];
      if (firstItem?.error) {
        throw new SeedreamImageApiError(
          `火山方舟 API 错误: ${String(firstItem.error.message ?? "生成失败")}`,
          502
        );
      }
      const imageUrl = firstItem?.url;
      if (typeof imageUrl !== "string" || !imageUrl.startsWith("https://")) {
        throw new SeedreamImageApiError("火山方舟 API 返回数据格式异常", 502);
      }

      return {
        imageUrl,
        model: config.model,
      };
    }

    throw new SeedreamImageApiError("火山方舟 API 暂时不可用，请稍后再试", 502);
  } catch (error) {
    if (error instanceof SeedreamImageApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new SeedreamImageApiError(
        `火山方舟 API 请求超时（${Math.round(timeoutMs / 1000)}s），请重试`,
        504
      );
    }
    const message = error instanceof Error ? error.message : String(error);
    throw new SeedreamImageApiError(`服务器错误: ${message}`, 500);
  } finally {
    clearTimeout(timeout);
  }
}
