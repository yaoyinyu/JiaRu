import { createHash, randomInt } from "node:crypto";

/**
 * 手机验证码模块（文档 §5.1：验证码 5 分钟有效、同号码 60 秒节流、
 * 单日上限 10 条防轰炸）。
 *
 * 验证码不存明文，只存 SHA-256 哈希。短信发送依赖外部服务商
 * （阿里云/腾讯云短信，文档 §10.1），在未配置服务商时进入
 * "开发模式"：验证码直接返回给调用方并在控制台输出，便于本地联调；
 * 生产环境必须配置短信服务商，否则 request-code 返回 503。
 */

export const CODE_TTL_MS = 5 * 60 * 1000; // 5 分钟有效
export const CODE_RESEND_INTERVAL_MS = 60 * 1000; // 60 秒节流
export const CODE_DAILY_LIMIT = 10; // 单日上限 10 条
export const CODE_MAX_ATTEMPTS = 5; // 单条验证码最多尝试 5 次

export function generateCode(): string {
  // 6 位数字
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}

export function hashCode(code: string): string {
  return createHash("sha256").update(code).digest("hex");
}

export function isCodeExpired(expiresAt: number, now: number): boolean {
  return now > expiresAt;
}

export function todayString(now: number): string {
  const d = new Date(now);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 发送验证码。返回 true 表示已成功投递（发送或开发模式）。
 * 短信服务商未配置时抛错（生产环境禁止把验证码写入日志）。
 */
export async function deliverSmsCode(phone: string, code: string): Promise<{ mode: "dev" | "provider" }> {
  const provider = process.env.SMS_PROVIDER;
  if (!provider) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("SMS_PROVIDER 未配置：生产环境禁止开发模式发送验证码");
    }
    // 开发模式：验证码由路由层返回给前端（仅本地联调），此处不落日志以外的敏感信息
    console.log(`[dev-sms] ${phone} 验证码: ${code}`);
    return { mode: "dev" };
  }
  // TODO(Phase 1): 接入阿里云/腾讯云短信服务商（需 AccessKey/签名模板配置）
  // 当前占位：标记为未实现，避免静默失败。
  throw new Error(`短信服务商 ${provider} 尚未接入，请配置 SMS_ACCESS_KEY 与 SMS_SIGN_NAME`);
}
