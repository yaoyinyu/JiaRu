import { NextRequest, NextResponse } from "next/server";
import {
  AgnesImageApiError,
  generateAgnesImage,
} from "@/lib/agnes-image-api";

export const maxDuration = 300;

/**
 * POST /api/generate-ai
 * Body: { prompt: string }
 * Returns: { imageUrl: string } | { error: string }
 *
 * 使用 Agnes Image 2.1 Flash 生成美甲效果图。
 * API Key 从服务端环境变量读取，前端永远拿不到。
 */
export async function POST(req: NextRequest) {
  // ── 1. 解析请求 ──
  let body: { prompt?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
  }

  const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";

  // ── 2. 参数校验 ──
  if (!prompt) {
    return NextResponse.json({ error: "请输入描述文字" }, { status: 400 });
  }
  if (prompt.length > 500) {
    return NextResponse.json(
      { error: "描述文字不能超过 500 字符" },
      { status: 400 }
    );
  }

  // ── 3. 构造美甲专用 prompt ──
  const enhancedPrompt = `${prompt}, nail art design on fingernails, manicure, close-up hand photo, beautiful, high detail`;

  // ── 4. 调用 Agnes Images API ──
  try {
    const { imageUrl } = await generateAgnesImage(enhancedPrompt);
    return NextResponse.json({ imageUrl });
  } catch (err) {
    if (err instanceof AgnesImageApiError) {
      return NextResponse.json(
        { error: err.message },
        { status: err.statusCode }
      );
    }
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `服务器错误: ${msg}` },
      { status: 500 }
    );
  }
}
