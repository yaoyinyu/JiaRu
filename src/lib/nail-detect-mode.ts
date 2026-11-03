/**
 * 指甲识别「本地 / 云端」双模式共享逻辑（v1.2.216，node 可测纯函数）。
 *
 * 模式是会话级状态：每个识别站点（编辑器 / AR 选择器 / 个性化分析）默认本地，
 * 不持久化模式选择；云端涉及图片离开本机，需一次性隐私确认（localStorage 记忆，
 * 键 `jiaru.nail-detect-cloud-consent.v1`），确认后本会话内切换云端不再重复询问。
 *
 * 云端候选与 `vlm-matte` 兜底同口径：固定低置信 + `needs_review`，仅作辅助定位，
 * 不计入正式识别成功率（正式模型 PRODUCT HOLD 不变）。
 */

/** 识别模式：本地（浏览器级联 + 本机 matte 兜底）或云端（用户显式选择）。 */
export type NailDetectMode = "local" | "cloud";

/** 云端识别后端：方舟视觉理解模型，或兼容 /matte 契约的云端自托管服务。 */
export type NailCloudBackend = "ark" | "cloud-matte";

/** 云端识别一次性隐私确认的 localStorage 键。 */
export const NAIL_CLOUD_CONSENT_STORAGE_KEY = "jiaru.nail-detect-cloud-consent.v1";

/** 云端后端可用性（由两条路由的 GET 探测汇聚；false = 未配置或服务不可达）。 */
export interface NailCloudAvailability {
  ark: boolean;
  cloudMatte: boolean;
}

/** 云端后端的用户可见名称。 */
export const NAIL_CLOUD_BACKEND_LABELS: Record<NailCloudBackend, string> = {
  ark: "方舟视觉",
  "cloud-matte": "云端自托管抠图",
};

/** 按可用性解析默认云端后端：方舟视觉优先（无需自建服务）。 */
export function resolveDefaultCloudBackend(availability: NailCloudAvailability): NailCloudBackend | null {
  if (availability.ark) return "ark";
  if (availability.cloudMatte) return "cloud-matte";
  return null;
}

/** 是否配置了至少一个云端后端。 */
export function hasAnyCloudBackend(availability: NailCloudAvailability): boolean {
  return availability.ark || availability.cloudMatte;
}

export type NailDetectRunDecision =
  | { action: "run" }
  | { action: "need-consent"; message: string }
  | { action: "unavailable"; message: string };

/**
 * 发起一次识别前的判决：
 * - local 恒可运行（本地路径不需要任何网络与确认）；
 * - cloud 需要所选后端可用 + 已有一次性隐私确认；
 * - 未确认 → `need-consent`（页面弹确认，同意后重判）；后端不可用 → `unavailable`。
 */
export function decideNailDetectRun(input: {
  mode: NailDetectMode;
  backend: NailCloudBackend;
  availability: NailCloudAvailability;
  consentGiven: boolean;
}): NailDetectRunDecision {
  if (input.mode === "local") return { action: "run" };
  if (!hasAnyCloudBackend(input.availability)) {
    return {
      action: "unavailable",
      message: "云端识别未配置（需在服务端设置 ARK_VISION_MODEL 或 NAIL_CLOUD_MATTE_URL），已保留本地模式。",
    };
  }
  if (!input.availability[input.backend === "ark" ? "ark" : "cloudMatte"]) {
    return {
      action: "unavailable",
      message: `云端识别后端「${NAIL_CLOUD_BACKEND_LABELS[input.backend]}」当前不可用，请切换后端或使用本地模式。`,
    };
  }
  if (!input.consentGiven) {
    return {
      action: "need-consent",
      message: "使用云端识别前需要确认隐私说明（当前照片将上传至云端视觉服务，仅用于本次甲面定位）。",
    };
  }
  return { action: "run" };
}

/** 读取一次性隐私确认（SSR / 读取异常一律按未确认处理）。 */
export function readNailCloudConsent(storage: Pick<Storage, "getItem"> | undefined): boolean {
  try {
    return storage?.getItem(NAIL_CLOUD_CONSENT_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** 写入一次性隐私确认；写入失败静默（下次仍会询问，不阻塞识别）。 */
export function writeNailCloudConsent(storage: Pick<Storage, "setItem"> | undefined): void {
  try {
    storage?.setItem(NAIL_CLOUD_CONSENT_STORAGE_KEY, "1");
  } catch {
    // 存储不可用（隐私模式等）：保持未确认状态即可。
  }
}

/** 云端识别错误的稳定分类（与降级响应 reason 对齐）。 */
export type NailDetectErrorCode =
  | "rate_limited"
  | "timeout"
  | "disabled"
  | "busy"
  | "network"
  | "invalid"
  | "upstream"
  | "cancelled";

/** 各错误的用户可见文案；调用方在错误后一律保留本地结果。 */
export const NAIL_DETECT_ERROR_MESSAGES: Record<NailDetectErrorCode, string> = {
  rate_limited: "云端识别请求过于频繁，请稍后再试。",
  timeout: "云端识别超时，请重试或改用本地模式。",
  disabled: "云端识别未启用，请检查服务端配置。",
  busy: "云端识别服务繁忙，请稍后再试。",
  network: "网络异常，未能连接云端识别服务。",
  invalid: "照片格式不支持云端识别，请使用 JPG/PNG/WebP。",
  upstream: "云端识别服务暂时不可用，已保留本地结果。",
  cancelled: "已取消云端识别。",
};

/** 把降级 reason / 异常归一为稳定错误码（未知一律 upstream）。 */
export function classifyNailDetectError(reason: string | null | undefined): NailDetectErrorCode {
  switch (reason) {
    case "rate_limited":
      return "rate_limited";
    case "timeout":
      return "timeout";
    case "disabled":
      return "disabled";
    case "busy":
      return "busy";
    case "invalid_image":
    case "too_large":
      return "invalid";
    case "cancelled":
      return "cancelled";
    case "network":
      return "network";
    default:
      return "upstream";
  }
}

/** 云端识别一次的用户可见描述（隐私确认弹层复用）。 */
export function describeNailCloudBackend(backend: NailCloudBackend): string {
  return NAIL_CLOUD_BACKEND_LABELS[backend];
}
