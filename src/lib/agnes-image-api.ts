export const DEFAULT_AGNES_API_BASE_URL = "https://apihub.agnes-ai.com/v1";
export const DEFAULT_AGNES_IMAGE_MODEL = "agnes-image-2.1-flash";
export const DEFAULT_AGNES_IMAGE_SIZE = "1024x1024";

const DEFAULT_TIMEOUT_MS = 180_000;
const DEFAULT_MAX_ATTEMPTS = 4;
const DEFAULT_RETRY_DELAY_MS = 1_000;

type Environment = Record<string, string | undefined>;

type GenerateAgnesImageOptions = {
  env?: Environment;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  maxAttempts?: number;
  retryDelayMs?: number;
  /** 可选图生图输入：Data URI（data:image/...;base64,...）。提供后走 image-to-image。 */
  imageDataUri?: string;
  /** 可选输出宽高比（1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9），与 size "1K" 搭配。 */
  ratio?: string;
};

type AgnesImageConfig = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export class AgnesImageApiError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "AgnesImageApiError";
    this.statusCode = statusCode;
  }
}

export function getAgnesImageConfig(
  env: Environment = process.env
): AgnesImageConfig {
  const apiKey = env.AGNES_API_KEY?.trim();
  if (!apiKey || apiKey === "your-key-here") {
    throw new AgnesImageApiError(
      "服务器未配置 AGNES_API_KEY，请联系管理员",
      503
    );
  }

  const configuredBaseUrl =
    env.AGNES_API_BASE_URL?.trim() || DEFAULT_AGNES_API_BASE_URL;
  let parsedBaseUrl: URL;
  try {
    parsedBaseUrl = new URL(configuredBaseUrl);
  } catch {
    throw new AgnesImageApiError("AGNES_API_BASE_URL 配置无效", 503);
  }

  if (parsedBaseUrl.protocol !== "https:") {
    throw new AgnesImageApiError("AGNES_API_BASE_URL 必须使用 HTTPS", 503);
  }
  if (parsedBaseUrl.username || parsedBaseUrl.password) {
    throw new AgnesImageApiError("AGNES_API_BASE_URL 不得包含认证信息", 503);
  }

  return {
    apiKey,
    baseUrl: parsedBaseUrl.toString().replace(/\/+$/, ""),
    model: env.AGNES_IMAGE_MODEL?.trim() || DEFAULT_AGNES_IMAGE_MODEL,
  };
}

async function readProviderError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;

  try {
    const parsed = JSON.parse(text);
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

export async function generateAgnesImage(
  prompt: string,
  options: GenerateAgnesImageOptions = {}
) {
  const config = getAgnesImageConfig(options.env);
  const endpoint = `${config.baseUrl}/images/generations`;
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxAttempts = options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;
  const retryDelayMs = options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const extraBody: Record<string, unknown> = { response_format: "url" };
  if (options.imageDataUri) {
    extraBody.image = [options.imageDataUri];
  }
  const requestBody: Record<string, unknown> = {
    model: config.model,
    prompt,
    size: options.imageDataUri && options.ratio ? "1K" : DEFAULT_AGNES_IMAGE_SIZE,
    extra_body: extraBody,
  };
  if (options.imageDataUri && options.ratio) {
    requestBody.ratio = options.ratio;
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

      if (response.status === 503 && attempt + 1 < maxAttempts) {
        await response.arrayBuffer();
        await wait(retryDelayMs * 2 ** attempt);
        continue;
      }

      if (!response.ok) {
        const providerMessage = await readProviderError(response);
        if (response.status === 401) {
          throw new AgnesImageApiError("Agnes API Key 无效", 401);
        }
        if (response.status === 429) {
          throw new AgnesImageApiError(
            "Agnes API 调用频率过高，请稍后再试",
            429
          );
        }
        throw new AgnesImageApiError(
          `Agnes API 错误: ${providerMessage}`,
          502
        );
      }

      const data = await response.json();
      const imageUrl = data?.data?.[0]?.url;
      if (typeof imageUrl !== "string" || !imageUrl.startsWith("https://")) {
        throw new AgnesImageApiError("Agnes API 返回数据格式异常", 502);
      }

      return {
        imageUrl,
        model: config.model,
      };
    }

    throw new AgnesImageApiError("Agnes API 暂时不可用，请稍后再试", 502);
  } catch (error) {
    if (error instanceof AgnesImageApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new AgnesImageApiError(
        `Agnes API 请求超时（${Math.round(timeoutMs / 1000)}s），请重试`,
        504
      );
    }
    const message = error instanceof Error ? error.message : String(error);
    throw new AgnesImageApiError(`服务器错误: ${message}`, 500);
  } finally {
    clearTimeout(timeout);
  }
}
