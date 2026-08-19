import { NextResponse } from "next/server";
import { createCaptcha } from "@/lib/auth/captcha";

/**
 * GET /api/auth/captcha
 * 获取人机验证图形验证码。返回 { id, svg }：
 *  - id：后续请求验证码时回传；
 *  - svg：SVG 图片内容，前端以 data URL 渲染（不返回答案）。
 */
export async function GET() {
  const { id, svg } = createCaptcha();
  const dataUrl = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
  return NextResponse.json({ id, dataUrl });
}
