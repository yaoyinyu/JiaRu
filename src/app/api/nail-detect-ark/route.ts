import { NextRequest, NextResponse } from "next/server";
import {
  ArkDetectApiError,
  detectNailsWithArkModel,
  isArkDetectEnabled,
} from "@/lib/nail-detect-ark-api";
import { applyRenewedCookies, requireUserWithRenewal } from "@/lib/auth/http";
import { getRateLimiter } from "@/lib/rate-limit";
import { guestIdentityFromHeaders } from "@/lib/ai-quota";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

/** Data URI 图片白名单前缀（PNG/JPEG/WebP），与 matte 路由同口径。 */
const IMAGE_DATA_URI_PATTERN = /^data:image\/(png|jpeg|jpg|webp);base64,/i;
/** 请求体上限 8MB（含 base64 膨胀），超过即在解析前拒绝。 */
const MAX_BODY_BYTES = 8 * 1024 * 1024;
/** 单图甲面框上限（服务端截断；坐标映射与去重在浏览器共享库）。 */
const MAX_BOXES = 10;

/**
 * GET /api/nail-detect-ark
 * 返回方舟视觉识别是否已配置（env 判定，不发起上游请求）。
 * - 未配置 `ARK_VISION_MODEL` 或密钥：`{ enabled:false }`，前端云端选项禁用。
 */
export async function GET() {
  return NextResponse.json({ enabled: isArkDetectEnabled() });
}

/**
 * POST /api/nail-detect-ark
 * 请求体 `{ image: DataURI, width, height }`（图片由浏览器 encodeImageForMatte 同源
 * 链路编码至长边 ≤1600，width/height 为编码图坐标域尺寸）。
 * 响应 `{ ok:true, boxes:[ [x1,y1,x2,y2] ... ], model, elapsedMs }`（编码图坐标域像素框），
 * 降级响应 `{ degraded:true, reason, error, retryAfterSeconds? }`。
 * 身份与限流复用现有体系（桶 `nailDetectArk`，默认每人每 10 分钟 3 次）。
 */
export async function POST(req: NextRequest) {
  if (!isArkDetectEnabled()) {
    return NextResponse.json(
      { degraded: true, reason: "disabled", error: "云端识别未启用" },
      { status: 503 }
    );
  }

  // ── 1. 体积预检：先看头，再读体 ──
  const declaredLength = Number.parseInt(req.headers.get("content-length") ?? "", 10);
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
    return NextResponse.json(
      { error: `图片过大，请压缩到 ${Math.floor(MAX_BODY_BYTES / (1024 * 1024))}MB 以内` },
      { status: 413 }
    );
  }

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = await req.json();
    if (!parsed || typeof parsed !== "object") throw new Error("body must be object");
    body = parsed as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "请求体不是合法 JSON" }, { status: 400 });
  }

  // ── 2. 参数校验：只接受白名单字段 image / width / height（编码图坐标域）──
  const image = typeof body.image === "string" ? body.image : "";
  if (!image) {
    return NextResponse.json({ error: "缺少图片数据" }, { status: 400 });
  }
  if (image.length > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "图片过大，请压缩后重试" }, { status: 413 });
  }
  if (!IMAGE_DATA_URI_PATTERN.test(image)) {
    return NextResponse.json(
      { error: "图片格式不支持，请使用 PNG/JPEG/WebP" },
      { status: 400 }
    );
  }
  const width = typeof body.width === "number" ? body.width : Number.NaN;
  const height = typeof body.height === "number" ? body.height : Number.NaN;
  if (!Number.isFinite(width) || !Number.isFinite(height) || width < 1 || height < 1 || width > 4096 || height > 4096) {
    return NextResponse.json({ error: "缺少有效的图片宽高（编码图坐标域）" }, { status: 400 });
  }

  // ── 3. 身份与限流（复用现有配额体系，不新建鉴权）──
  const session = requireUserWithRenewal(req);
  const user = session?.user ?? null;
  const identity = user ? `user:${user.id}` : guestIdentityFromHeaders(req.headers);
  const limit = getRateLimiter().consume("nailDetectArk", identity);
  if (!limit.ok) {
    return NextResponse.json(
      {
        degraded: true,
        reason: "rate_limited",
        error: "云端识别请求过于频繁，请稍后再试",
        retryAfterSeconds: limit.retryAfterSeconds,
      },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } }
    );
  }

  // ── 4. 调用方舟视觉理解模型（框在编码图坐标域，映射在浏览器共享库）──
  try {
    const result = await detectNailsWithArkModel({
      imageDataUri: image,
      imageWidth: Math.round(width),
      imageHeight: Math.round(height),
    });
    return applyRenewedCookies(
      NextResponse.json({
        ok: true,
        boxes: result.boxes.slice(0, MAX_BOXES),
        model: result.model,
        elapsedMs: result.elapsedMs,
      }),
      session
    );
  } catch (err) {
    if (err instanceof ArkDetectApiError) {
      if (err.statusCode === 400 || err.statusCode === 413) {
        return applyRenewedCookies(
          NextResponse.json({ error: err.message }, { status: err.statusCode }),
          session
        );
      }
      const headers: Record<string, string> = {};
      const responseBody: Record<string, unknown> = {
        degraded: true,
        reason: err.reason,
        error: err.message,
      };
      if (err.retryAfterSeconds !== null) {
        responseBody.retryAfterSeconds = err.retryAfterSeconds;
        headers["Retry-After"] = String(err.retryAfterSeconds);
      }
      return applyRenewedCookies(NextResponse.json(responseBody, { status: err.statusCode, headers }), session);
    }
    // 内部异常原文不外泄，只写服务端日志。
    console.error("[nail-detect-ark] unexpected error:", err);
    return NextResponse.json(
      { degraded: true, reason: "upstream", error: "云端识别服务暂时不可用" },
      { status: 502 }
    );
  }
}
