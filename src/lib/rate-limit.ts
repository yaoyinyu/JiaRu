import { createHash } from "node:crypto";

/**
 * 简易进程内 IP 限流（2026-09-24 安全审计修复）。
 *
 * 背景：应用层此前完全没有按 IP 的速率限制——图形验证码可无限签发、
 * 短信验证码只按手机号节流（60 秒 / 单日 10 条），攻击者可轮换手机号轰炸。
 * 本模块提供按来源 IP 的固定窗口计数，补足 Web 应用层的第一道闸。
 *
 * 语义与局限（与 `ai-quota.ts` 一致，不虚称分布式能力）：
 *  - 进程内存态，单实例部署下有效；重启清零，多实例需换共享存储；
 *  - 计数窗口到期由 `sweep()` 惰性回收；
 *  - 反向代理场景必须设置 `JIARU_TRUST_PROXY=1` 并由 Nginx 注入
 *    `X-Real-IP: $remote_addr`，否则一律回退 "unknown"（共享计数，偏保守）。
 */

export type RateLimitName =
  | "captcha"
  | "requestCode"
  | "verifyCode"
  | "bindPhone"
  | "oauthStart";

interface RateLimitRule {
  limit: number;
  windowMs: number;
}

/** 各端点的每 IP 窗口限额；可用环境变量覆盖（非法值回退默认）。 */
const DEFAULT_RULES: Record<RateLimitName, RateLimitRule> = {
  captcha: { limit: 30, windowMs: 5 * 60 * 1000 },
  requestCode: { limit: 5, windowMs: 10 * 60 * 1000 },
  verifyCode: { limit: 20, windowMs: 10 * 60 * 1000 },
  bindPhone: { limit: 10, windowMs: 10 * 60 * 1000 },
  oauthStart: { limit: 20, windowMs: 10 * 60 * 1000 },
};

const ENV_OVERRIDES: Record<RateLimitName, string> = {
  captcha: "JIARU_RL_CAPTCHA",
  requestCode: "JIARU_RL_REQUEST_CODE",
  verifyCode: "JIARU_RL_VERIFY_CODE",
  bindPhone: "JIARU_RL_BIND_PHONE",
  oauthStart: "JIARU_RL_OAUTH_START",
};

interface Bucket {
  count: number;
  resetAt: number;
}

export interface RateLimitResult {
  ok: boolean;
  limit: number;
  remaining: number;
  retryAfterSeconds: number;
}

export interface RateLimitOptions {
  now?: () => number;
  env?: Record<string, string | undefined>;
  buckets?: Map<string, Bucket>;
}

function intFromEnv(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return fallback;
  return parsed;
}

/**
 * 由请求头解析客户端 IP。
 * 仅在 `JIARU_TRUST_PROXY=1` 时信任代理头，避免 X-Forwarded-For 被伪造以绕过限流；
 * 单级可信代理时真实客户端位于 XFF 最右侧（左侧条目可由客户端任意伪造），
 * 更可靠的是直接使用 Nginx 注入的 `X-Real-IP`。
 */
export function resolveClientIp(
  headers: { get(name: string): string | null },
  env: Record<string, string | undefined> = process.env
): string {
  if (env.JIARU_TRUST_PROXY !== "1") return "unknown";
  const real = headers.get("x-real-ip");
  if (real && real.trim()) return real.trim();
  const forwarded = headers.get("x-forwarded-for") ?? "";
  const parts = forwarded
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length > 0) return parts[parts.length - 1];
  return "unknown";
}

const globalBuckets = new Map<string, Bucket>();

export function createRateLimiter(options: RateLimitOptions = {}) {
  const now = options.now ?? (() => Date.now());
  const envOf = () => options.env ?? (process.env as Record<string, string | undefined>);
  const buckets = options.buckets ?? globalBuckets;

  function ruleFor(name: RateLimitName): RateLimitRule {
    const fallback = DEFAULT_RULES[name];
    return {
      limit: intFromEnv(envOf()[ENV_OVERRIDES[name]], fallback.limit),
      windowMs: fallback.windowMs,
    };
  }

  function sweep(current: number): void {
    for (const [key, bucket] of buckets) {
      if (current >= bucket.resetAt) buckets.delete(key);
    }
  }

  return {
    /** 占用一次配额；超限返回 ok=false 与建议重试秒数 */
    consume(name: RateLimitName, identity: string): RateLimitResult {
      const current = now();
      // 惰性清理：仅在 Map 规模较大时执行，避免每次请求全量遍历
      if (buckets.size > 512) sweep(current);
      const { limit, windowMs } = ruleFor(name);
      const key = `${name}:${createHash("sha256").update(identity).digest("hex").slice(0, 16)}`;
      const existing = buckets.get(key);
      if (!existing || current >= existing.resetAt) {
        buckets.set(key, { count: 1, resetAt: current + windowMs });
        return { ok: true, limit, remaining: limit - 1, retryAfterSeconds: 0 };
      }
      if (existing.count >= limit) {
        return {
          ok: false,
          limit,
          remaining: 0,
          retryAfterSeconds: Math.max(1, Math.ceil((existing.resetAt - current) / 1000)),
        };
      }
      existing.count += 1;
      return { ok: true, limit, remaining: limit - existing.count, retryAfterSeconds: 0 };
    },
  };
}

declare global {
  var __jiaruRateLimiter: ReturnType<typeof createRateLimiter> | undefined;
}

/** Next.js Route Handler 单例（热重载安全） */
export function getRateLimiter() {
  if (!globalThis.__jiaruRateLimiter) {
    globalThis.__jiaruRateLimiter = createRateLimiter();
  }
  return globalThis.__jiaruRateLimiter;
}
