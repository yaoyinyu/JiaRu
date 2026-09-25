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
 * 2026-09-24 安全审计修复：开发模式验证码是否允许。
 *
 * 原实现只看 `NODE_ENV !== "production"`，一旦以 `next dev` 经隧道对外暴露，
 * 任何人请求任意手机号即可从响应 `devCode` 字段拿到明文验证码并登录任意账号。
 * 现在收紧为：
 *  - production 一律禁止；
 *  - 非 production 时，仅当调用方来自回环/私网地址才允许（保障本地联调）；
 *  - 需要强制开启（如局域网联调被误判）时显式设置 `JIARU_DEV_SMS=1`。
 *
 * @param clientIp 客户端 IP（来自 getClientIp，可为 null）
 */
export function isDevSmsAllowed(clientIp?: string | null): boolean {
  if (process.env.NODE_ENV === "production") return false;
  if (process.env.JIARU_DEV_SMS === "1") return true;
  // 没有任何代理头 = 直连（本地 `next dev` 场景），保留本地联调能力。
  // 经隧道/反代对外暴露时必然带 X-Forwarded-For，此时按来源地址判定。
  if (!clientIp) return true;
  return isLoopbackOrPrivateIp(clientIp);
}

function isLoopbackOrPrivateIp(ip: string): boolean {
  const value = ip.trim().toLowerCase();
  if (value === "::1" || value === "localhost" || value === "unknown") return false;
  if (value.startsWith("127.")) return true;
  if (value.startsWith("10.")) return true;
  if (value.startsWith("192.168.")) return true;
  const m = /^172\.(\d{1,3})\./.exec(value);
  if (m) {
    const second = Number(m[1]);
    if (second >= 16 && second <= 31) return true;
  }
  return false;
}

/**
 * 发送验证码。返回 true 表示已成功投递（发送或开发模式）。
 * 短信服务商未配置时，仅在本机/私网联调场景允许开发模式（验证码写入日志），
 * 公网来源一律拒绝，避免明文验证码外泄。
 */
export async function deliverSmsCode(
  phone: string,
  code: string,
  clientIp?: string | null
): Promise<{ mode: "dev" | "provider" }> {
  const provider = process.env.SMS_PROVIDER;
  if (!provider) {
    if (!isDevSmsAllowed(clientIp)) {
      throw new Error(
        "SMS_PROVIDER 未配置：不允许以开发模式发送验证码（需本机/私网访问，或显式设置 JIARU_DEV_SMS=1）"
      );
    }
    // 开发模式：验证码由路由层返回给前端（仅本地联调），此处不落日志以外的敏感信息
    console.log(`[dev-sms] ${phone} 验证码: ${code}`);
    return { mode: "dev" };
  }
  // TODO(Phase 1): 接入阿里云/腾讯云短信服务商（需 AccessKey/签名模板配置）
  // 当前占位：标记为未实现，避免静默失败。
  throw new Error(`短信服务商 ${provider} 尚未接入，请配置 SMS_ACCESS_KEY 与 SMS_SIGN_NAME`);
}
