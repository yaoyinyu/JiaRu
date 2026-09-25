import { NextRequest, NextResponse } from "next/server";
import { createCaptcha } from "@/lib/auth/captcha";
import { getRateLimiter, resolveClientIp } from "@/lib/rate-limit";

/**
 * GET /api/auth/captcha
 * 获取人机验证图形验证码。返回 { id, svg }：
 *  - id：后续请求验证码时回传；
 *  - svg：SVG 图片内容，前端以 data URL 渲染（不返回答案）。
 *
 * 2026-09-24 安全审计修复：按来源 IP 限流（默认 30 次 / 5 分钟），
 * 防止机器人无限签发验证码后批量尝试。
 */
export async function GET(req: NextRequest) {
  const ip = resolveClientIp(req.headers);
  const limited = getRateLimiter().consume("captcha", ip);
  if (!limited.ok) {
    return NextResponse.json(
      { error: "操作过于频繁，请稍后再试" },
      { status: 429, headers: { "Retry-After": String(limited.retryAfterSeconds) } }
    );
  }
  const { id, svg } = createCaptcha();
  const dataUrl = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
  return NextResponse.json({ id, dataUrl });
}
