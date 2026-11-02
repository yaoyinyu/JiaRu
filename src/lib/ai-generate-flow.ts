/**
 * AI 生图流程纯逻辑（方案 §6）：请求快照、任务状态、错误分类与引擎独立设置。
 *
 * 边界：
 * - 取消只指前端中断请求（AbortController），不宣称服务端任务终止；
 * - 取消不算失败；失败不自动重试；
 * - 本模块不改变任何请求契约（/api/generate-ai、/api/generate-seedream）。
 */

import type { AiImageRatio } from "./ai-image-size.ts";

export type AiEngine = "agnes" | "seedream-pro" | "seedream-lite";

/** 一次生成请求的不可变快照：请求只用快照，结果与收录元数据绑定回快照。 */
export interface AiGenerationRequestSnapshot {
  requestId: string;
  engine: AiEngine;
  prompt: string;
  ratio: AiImageRatio;
  size: string;
  referenceImage: string | null;
  createdAt: number;
}

/** 生成任务状态：取消是独立终态，不算失败。 */
export type AiTaskStatus = "idle" | "running" | "cancelled" | "error" | "success";

/** 每引擎独立设置（方案 §6.4）：尺寸档位与提示词草稿互不串扰。 */
export interface AiEngineSettings {
  size: string;
  lastPromptDraft: string;
}

export type AiEngineSettingsMap = Record<AiEngine, AiEngineSettings>;

/** 创建请求快照（requestId 在 crypto.randomUUID 不可用时退化生成）。 */
export function createRequestSnapshot(input: {
  engine: AiEngine;
  prompt: string;
  ratio: AiImageRatio;
  size: string;
  referenceImage: string | null;
  now?: number;
  requestId?: string;
}): AiGenerationRequestSnapshot {
  const requestId =
    input.requestId ??
    (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
  return {
    requestId,
    engine: input.engine,
    prompt: input.prompt,
    ratio: input.ratio,
    size: input.size,
    referenceImage: input.referenceImage,
    createdAt: input.now ?? Date.now(),
  };
}

/** 引擎请求路径：Agnes 与 Seedream 分属两条路由（契约不变）。 */
export function resolveGenerateEndpoint(engine: AiEngine): string {
  return engine === "agnes" ? "/api/generate-ai" : "/api/generate-seedream";
}

/** 组装请求体（模型字段仅 Seedream 需要，契约与现有路由一致）。 */
export function buildAiRequestBody(snapshot: AiGenerationRequestSnapshot): Record<string, unknown> {
  const isSeedream = snapshot.engine !== "agnes";
  return isSeedream
    ? {
        prompt: snapshot.prompt,
        image: snapshot.referenceImage ?? undefined,
        model: snapshot.engine === "seedream-pro" ? "pro" : "lite",
        ratio: snapshot.ratio,
        size: snapshot.size,
      }
    : {
        prompt: snapshot.prompt,
        image: snapshot.referenceImage ?? undefined,
        ratio: snapshot.ratio,
        size: snapshot.size,
      };
}

/** AI 生成错误分类（方案 §6.6 错误表）。 */
export type AiErrorKind =
  | "empty_prompt"
  | "prompt_over_limit"
  | "service_unconfigured"
  | "quota_exceeded"
  | "network_failed"
  | "upstream_timeout"
  | "invalid_result"
  | "unknown";

export const AI_ERROR_MESSAGES: Record<AiErrorKind, string> = {
  empty_prompt: "请先描述想要的美甲",
  prompt_over_limit: "当前引擎的提示词字数已超上限，请缩短后重试",
  service_unconfigured: "AI 服务暂未配置或暂时不可用，请稍后再试",
  quota_exceeded: "今日生成次数已用完，明天再试",
  network_failed: "生成请求失败，请重试",
  upstream_timeout: "生成超时，请重试或更换引擎",
  invalid_result: "AI 服务返回异常，请重试",
  unknown: "生成失败，请重试",
};

/** AbortError 判定（Node 与浏览器 DOMException 双口径）。 */
export function isAbortError(err: unknown): boolean {
  return (
    (err instanceof Error && err.name === "AbortError") ||
    (typeof DOMException !== "undefined" && err instanceof DOMException && err.name === "AbortError")
  );
}

/** 按异常与 HTTP 状态归类错误；调用方用 AI_ERROR_MESSAGES 取用户文案。 */
export function classifyAiGenerationError(err: unknown, respStatus?: number): AiErrorKind {
  const name = (err as { name?: string } | null)?.name ?? "";
  const message = err instanceof Error ? err.message : String(err ?? "");
  if (respStatus === 429) return "quota_exceeded";
  if (respStatus === 401 || respStatus === 403 || respStatus === 503) {
    return "service_unconfigured";
  }
  if (respStatus === 504) return "upstream_timeout";
  if (name === "TypeError" || /failed to fetch|network/i.test(message)) {
    return "network_failed";
  }
  if (/timeout|timed out|超时/i.test(message)) return "upstream_timeout";
  return "unknown";
}

/** 引擎切换目标设置：恢复该引擎上次尺寸与草稿（首次为引擎默认值）。 */
export function nextEngineSettings(
  settings: AiEngineSettingsMap,
  from: AiEngine,
  to: AiEngine
): { engine: AiEngine; size: string; promptDraft: string; settings: AiEngineSettingsMap } {
  return {
    engine: to,
    size: settings[to].size,
    promptDraft: settings[to].lastPromptDraft,
    settings,
  };
}
