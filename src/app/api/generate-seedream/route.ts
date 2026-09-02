import { NextRequest, NextResponse } from "next/server";
import {
  SeedreamImageApiError,
  generateSeedreamImage,
} from "@/lib/seedream-image-api";
import {
  assembleSeedreamEditPrompt,
  assembleSeedreamPrompt,
} from "@/lib/seedream-prompt";
import { AI_IMAGE_RATIOS } from "@/lib/ai-image-size";
import {
  DEFAULT_SEEDREAM_SIZE,
  isSeedreamModel,
  isSeedreamSize,
  resolveSeedreamDimension,
  type SeedreamModel,
} from "@/lib/seedream-image-size";

export const maxDuration = 300;

/** Data URI 图片白名单前缀（PNG/JPEG/WebP），与 Agnes 路由保持同一口径。 */
const IMAGE_DATA_URI_PATTERN = /^data:image\/(png|jpeg|jpg|webp);base64,/i;

/** Base64 Data URI 长度上限（约 6.7MB 原始图片二进制）。 */
const IMAGE_DATA_URI_MAX_LENGTH = 9_000_000;

/** Seedream 用户提示词上限（火山方舟建议中文提示词不超过 300 字）。 */
const SEEDREAM_PROMPT_MAX_LENGTH = 300;

/**
 * POST /api/generate-seedream
 * Body: { prompt: string, model: "pro" | "lite", image?: string, ratio?: string, size?: string }
 * Returns: { imageUrl: string } | { error: string }
 *
 * 使用火山方舟 Seedream 5.0 pro / lite 生成美甲效果图，与 Agnes 链路完全独立。
 * - 无 image：文生图；有 image（Data URI）：图生图（仅修改指甲区域）。
 * - ratio：画面比例白名单与 Agnes 相同；Ark 无 ratio 参数，服务端用
 *   「档位 × 比例 → 显式宽高像素」换算后以 size: "WxH" 传递。
 * - size：档位随模型不同——pro 仅 1K/1.5K/2K，lite 仅 2K/3K/4K。
 * - 密钥与 Model ID 从服务端环境变量读取，前端永远拿不到。
 */
export async function POST(req: NextRequest) {
  // ── 1. 解析请求 ──
  let body: {
    prompt?: unknown;
    model?: unknown;
    image?: unknown;
    ratio?: unknown;
    size?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
  }

  const prompt = typeof body.prompt === "string" ? body.prompt.trim() : "";
  if (!prompt) {
    return NextResponse.json({ error: "请输入描述文字" }, { status: 400 });
  }
  if (prompt.length > SEEDREAM_PROMPT_MAX_LENGTH) {
    return NextResponse.json(
      { error: `描述文字不能超过 ${SEEDREAM_PROMPT_MAX_LENGTH} 字符` },
      { status: 400 }
    );
  }

  // ── 2. 模型类别（pro / lite）──
  const model: SeedreamModel = isSeedreamModel(body.model) ? body.model : "pro";

  // ── 3. 参考图（可选，单张）──
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

  // ── 4. 比例与档位（档位随模型校验）──
  const ratio =
    typeof body.ratio === "string" && (AI_IMAGE_RATIOS as readonly string[]).includes(body.ratio.trim())
      ? body.ratio.trim()
      : "1:1";

  const size =
    typeof body.size === "string" && isSeedreamSize(model, body.size.trim())
      ? body.size.trim()
      : DEFAULT_SEEDREAM_SIZE[model];

  const pixelSize = resolveSeedreamDimension(model, size, ratio);
  if (!pixelSize) {
    return NextResponse.json(
      { error: "尺寸档位与画面比例组合无效，请重新选择" },
      { status: 400 }
    );
  }

  // ── 5. 组装 Seedream 专用精简提示词（与 Agnes 长提示词完全独立）──
  const enhancedPrompt = image
    ? assembleSeedreamEditPrompt(prompt)
    : assembleSeedreamPrompt(prompt);

  // ── 6. 调用火山方舟 Images API ──
  try {
    const { imageUrl } = await generateSeedreamImage(enhancedPrompt, {
      model,
      imageDataUri: image || undefined,
      pixelSize,
    });
    return NextResponse.json({ imageUrl });
  } catch (err) {
    if (err instanceof SeedreamImageApiError) {
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
