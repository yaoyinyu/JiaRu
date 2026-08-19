import { NextRequest, NextResponse } from "next/server";
import {
  AgnesImageApiError,
  generateAgnesImage,
} from "@/lib/agnes-image-api";
import {
  assembleAiImageEditPrompt,
  assembleAiImagePrompt,
} from "@/lib/ai-hand-anatomy-prompt";

export const maxDuration = 300;

/** 允许的图生图宽高比白名单（Agnes size=1K + ratio）。 */
const ALLOWED_RATIOS = new Set([
  "1:1",
  "3:4",
  "4:3",
  "16:9",
  "9:16",
  "2:3",
  "3:2",
  "21:9",
]);

/** Data URI 图片白名单前缀（PNG/JPEG/WebP）。 */
const IMAGE_DATA_URI_PATTERN = /^data:image\/(png|jpeg|jpg|webp);base64,/i;

/** Base64 Data URI 长度上限（约 6.7MB 原始图片二进制）。 */
const IMAGE_DATA_URI_MAX_LENGTH = 9_000_000;

/**
 * POST /api/generate-ai
 * Body: { prompt: string, image?: string, ratio?: string }
 * Returns: { imageUrl: string } | { error: string }
 *
 * 使用 Agnes Image 2.1 Flash 生成美甲效果图。
 * - 无 image：文生图（text-to-image），行为与历史版本完全一致。
 * - 有 image（Data URI）：图生图（image-to-image），在参考图基础上绘制美甲，
 *   保持原图手部姿势与场景不变。
 * API Key 从服务端环境变量读取，前端永远拿不到。
 */
export async function POST(req: NextRequest) {
  // ── 1. 解析请求 ──
  let body: { prompt?: unknown; image?: unknown; ratio?: unknown };
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
  if (prompt.length > 520) {
    return NextResponse.json(
      { error: "描述文字不能超过 520 字符" },
      { status: 400 }
    );
  }

  const image = typeof body.image === "string" ? body.image.trim() : "";
  if (image) {
    if (image.length > IMAGE_DATA_URI_MAX_LENGTH) {
      return NextResponse.json(
        { error: "参考图过大，请更换更小的图片（不超过 6MB）" },
        { status: 400 }
      );
    }
    if (!IMAGE_DATA_URI_PATTERN.test(image)) {
      return NextResponse.json(
        { error: "参考图格式不支持，请使用 PNG/JPEG/WebP 图片" },
        { status: 400 }
      );
    }
  }

  const ratio = typeof body.ratio === "string" ? body.ratio.trim() : "";
  if (ratio && !ALLOWED_RATIOS.has(ratio)) {
    return NextResponse.json(
      { error: "参考图宽高比参数无效" },
      { status: 400 }
    );
  }

  // ── 3. 构造美甲专用 prompt（用户提示词 → 场景后缀 → 隐藏系统提示词）──
  //    有参考图时走图生图组装（保持原图手部，仅改指甲），否则文生图组装。
  const enhancedPrompt = image
    ? assembleAiImageEditPrompt(prompt)
    : assembleAiImagePrompt(prompt);

  // ── 4. 调用 Agnes Images API ──
  try {
    const { imageUrl } = await generateAgnesImage(enhancedPrompt, {
      imageDataUri: image || undefined,
      ratio: ratio || undefined,
    });
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
