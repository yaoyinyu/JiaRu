import { createHash } from "node:crypto";

/**
 * AI 生图配额与预算熔断（服务端专用，勿在客户端组件引入）。
 *
 * 背景（2026-09-05 评审 P1）：`/api/generate-ai` 与 `/api/generate-seedream`
 * 两个付费供应商路由此前仅做参数校验即转发请求，接口公开可达且服务端配置
 * 有效密钥时，任意调用者都能消耗付费额度。本模块提供进程内防护：
 * 身份识别 → 每日额度 → 全局预算熔断 → 并发上限。
 *
 * 语义约定：
 * - 身份键：登录用户 `user:<id>`；游客 `guest:<ip 哈希前 16 位>`。
 *   游客 IP 取自 x-forwarded-for 首段（隧道/反代场景）或回退 "unknown"，
 *   该头可伪造，游客额度只是软约束；全局熔断是真正的预算上限。
 * - reserve() 是同步预留（单进程 Node 单线程下原子）；供应商调用成功后
 *   commit() 确认消耗；调用失败时 release() 返还该身份当日次数。
 * - 全局日计数在失败时**不返还**：超时/5xx 无法区分供应商是否已实际消耗，
 *   保守不返还可保证「每次请求最多消耗一个全局名额」，即使刻意制造失败
 *   也无法刷穿全局预算（每次失败同样占用名额）。
 * - 计数按本地时区日历日重置（与用户验证码的 daily 口径一致）；
 *   在飞任务计数独立于日期，跨天不丢失。
 * - 进程内存态：适配当前单实例部署（Windows 本地 `next start`）；
 *   重启清零。多实例共享与持久化台账属后续增强，不虚称分布式配额。
 *
 * 环境变量（均可选，非法值回退默认）：
 * - AI_QUOTA_GUEST_DAILY       游客单日生成上限（默认 5）
 * - AI_QUOTA_USER_DAILY        登录用户单日生成上限（默认 20）
 * - AI_QUOTA_GLOBAL_DAILY      全局单日生成上限（默认 200，预算熔断）
 * - AI_QUOTA_GLOBAL_CONCURRENCY 全局同时生成任务上限（默认 3）
 */

export type AiEngine = "agnes" | "seedream";

export interface AiQuotaEnv {
  AI_QUOTA_GUEST_DAILY?: string;
  AI_QUOTA_USER_DAILY?: string;
  AI_QUOTA_GLOBAL_DAILY?: string;
  AI_QUOTA_GLOBAL_CONCURRENCY?: string;
}

export interface ReserveInput {
  /** "user:<id>" 或 "guest:<hash>" */
  identity: string;
  authenticated: boolean;
  engine: AiEngine;
}

export interface Reservation {
  token: symbol;
  identity: string;
  engine: AiEngine;
  /** 预留时的日历日，用于跨天时安全释放 */
  day: string;
}

export type ReserveResult =
  | { ok: true; reservation: Reservation }
  | { ok: false; status: 429; error: string; retryAfterSeconds: number };

export interface QuotaSnapshot {
  day: string;
  globalCount: number;
  globalInFlight: number;
  identityCounts: Record<string, number>;
}

export interface AiQuotaGuard {
  reserve(input: ReserveInput): ReserveResult;
  commit(reservation: Reservation): void;
  release(reservation: Reservation): void;
  snapshot(): QuotaSnapshot;
}

export interface QuotaGuardOptions {
  /** 测试注入时钟；默认 Date.now */
  now?: () => number;
  /** 测试注入环境；默认 process.env */
  env?: AiQuotaEnv;
}

/** 默认限额；env 未配置或非法时使用 */
export const AI_QUOTA_DEFAULTS = {
  guestDaily: 5,
  userDaily: 20,
  globalDaily: 200,
  globalConcurrency: 3,
} as const;

function intFromEnv(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return fallback;
  return parsed;
}

/** 与 sms.ts 的日历日口径一致：本地时区 YYYY-MM-DD */
export function quotaDayString(nowMs: number): string {
  const d = new Date(nowMs);
  const month = `${d.getMonth() + 1}`.padStart(2, "0");
  const date = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${month}-${date}`;
}

/** 到下一个日历日 00:00 的秒数（ Retry-After 用，向上取整） */
function secondsUntilNextDay(nowMs: number): number {
  const d = new Date(nowMs);
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1, 0, 0, 0, 0);
  return Math.max(1, Math.ceil((next.getTime() - nowMs) / 1000));
}

/** 由请求头提取游客身份键（隧道/反代场景读 x-forwarded-for 首段） */
export function guestIdentityFromHeaders(headers: {
  get(name: string): string | null;
}): string {
  const forwarded = headers.get("x-forwarded-for") ?? "";
  const ip = forwarded.split(",")[0]?.trim() || "unknown";
  const hash = createHash("sha256").update(ip).digest("hex").slice(0, 16);
  return `guest:${hash}`;
}

export function createAiQuotaGuard(options: QuotaGuardOptions = {}): AiQuotaGuard {
  const now = options.now ?? (() => Date.now());
  const envOf = (): AiQuotaEnv => options.env ?? (process.env as AiQuotaEnv);

  let day = quotaDayString(now());
  let globalCount = 0;
  const identityCounts = new Map<string, number>();
  /** 在飞计数独立于日期，跨天不重置 */
  let globalInFlight = 0;
  const identityInFlight = new Map<string, number>();

  function limits() {
    const env = envOf();
    return {
      guestDaily: intFromEnv(env.AI_QUOTA_GUEST_DAILY, AI_QUOTA_DEFAULTS.guestDaily),
      userDaily: intFromEnv(env.AI_QUOTA_USER_DAILY, AI_QUOTA_DEFAULTS.userDaily),
      globalDaily: intFromEnv(env.AI_QUOTA_GLOBAL_DAILY, AI_QUOTA_DEFAULTS.globalDaily),
      globalConcurrency: intFromEnv(
        env.AI_QUOTA_GLOBAL_CONCURRENCY,
        AI_QUOTA_DEFAULTS.globalConcurrency
      ),
    };
  }

  function rollDayIfNeeded(): void {
    const current = quotaDayString(now());
    if (current !== day) {
      day = current;
      globalCount = 0;
      identityCounts.clear();
    }
  }

  function deny(error: string, retryAfterSeconds: number): ReserveResult {
    return { ok: false, status: 429, error, retryAfterSeconds };
  }

  return {
    reserve(input) {
      rollDayIfNeeded();
      const { guestDaily, userDaily, globalDaily, globalConcurrency } = limits();

      // 1. 全局预算熔断（今日供应商请求量上限）
      if (globalCount >= globalDaily) {
        return deny(
          `今日服务端生成额度已用完（全局上限 ${globalDaily} 次），请明天再试`,
          secondsUntilNextDay(now())
        );
      }
      // 2. 全局并发上限
      if (globalInFlight >= globalConcurrency) {
        return deny(
          `当前生成任务较多（并发上限 ${globalConcurrency}），请稍后重试`,
          30
        );
      }
      // 3. 同一身份同时只允许一个生成任务
      if ((identityInFlight.get(input.identity) ?? 0) >= 1) {
        return deny("你有一个生成任务正在进行中，请等待完成后再试", 30);
      }
      // 4. 身份当日额度
      const identityLimit = input.authenticated ? userDaily : guestDaily;
      const used = identityCounts.get(input.identity) ?? 0;
      if (used >= identityLimit) {
        return deny(
          `今日生成次数已用完（${identityLimit} 次/天），请明天再试或登录后重试`,
          secondsUntilNextDay(now())
        );
      }

      // 预留（同步执行，天然原子）
      globalCount += 1;
      globalInFlight += 1;
      identityInFlight.set(input.identity, 1);
      identityCounts.set(input.identity, used + 1);
      return {
        ok: true,
        reservation: { token: Symbol("ai-quota"), identity: input.identity, engine: input.engine, day },
      };
    },

    commit(reservation) {
      rollDayIfNeeded();
      // 全局/身份日计数保持已预留值（消耗确认），仅释放在飞名额
      globalInFlight = Math.max(0, globalInFlight - 1);
      identityInFlight.delete(reservation.identity);
    },

    release(reservation) {
      rollDayIfNeeded();
      globalInFlight = Math.max(0, globalInFlight - 1);
      identityInFlight.delete(reservation.identity);
      if (reservation.day !== day) return; // 跨天完成：当日计数已重置，无需返还
      // 身份当日次数与全局日计数：身份返还（真实用户遇 5xx 不被扣次数），
      // 全局保留（保守防刷，见模块注释）。
      const used = identityCounts.get(reservation.identity) ?? 0;
      if (used > 0) identityCounts.set(reservation.identity, used - 1);
    },

    snapshot() {
      rollDayIfNeeded();
      return {
        day,
        globalCount,
        globalInFlight,
        identityCounts: Object.fromEntries(identityCounts),
      };
    },
  };
}

/** Next.js Route Handler 单例（热重载安全：globalThis 兜底） */
declare global {
  var __jiaruAiQuotaGuard: AiQuotaGuard | undefined;
}

export function getAiQuotaGuard(): AiQuotaGuard {
  if (!globalThis.__jiaruAiQuotaGuard) {
    globalThis.__jiaruAiQuotaGuard = createAiQuotaGuard();
  }
  return globalThis.__jiaruAiQuotaGuard;
}
