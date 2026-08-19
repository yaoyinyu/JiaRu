import { NextResponse } from "next/server";
import { getWechatConfig } from "@/lib/auth/wechat";

/**
 * GET /api/auth/oauth/wechat/status
 * 返回微信登录是否已配置（前端据此显示按钮可用/禁用）。
 */
export async function GET() {
  return NextResponse.json({ configured: getWechatConfig() !== null });
}
