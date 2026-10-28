import { NextRequest, NextResponse } from "next/server";
import {
  NailMatteApiError,
  getNailMatteConfig,
  probeNailMatte,
  requestNailMatte,
  type NailMatteBox,
  type NailMatteTask,
} from "@/lib/nail-matte-api";
import { applyRenewedCookies, requireUserWithRenewal } from "@/lib/auth/http";
import { getRateLimiter } from "@/lib/rate-limit";
import { guestIdentityFromHeaders } from "@/lib/ai-quota";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 180;

/** Data URI 图片白名单前缀（PNG/JPEG/WebP）。 */
const IMAGE_DATA_URI_PATTERN = /^data:image\/(png|jpeg|jpg|webp);base64,/i;
/** 请求体上限 8MB（含 base64 膨胀），超过即在解析前拒绝。 */
const MAX_BODY_BYTES = 8 * 1024 * 1024;
/** 上游单图并发固定 1，候选框数量与上游实例上限保持一致。 */
const MAX_BOXES = 10;
const MAX_QUERY_LENGTH = 32;
const DEFAULT_QUERY = "指甲";
const ALLOWED_TASKS = new Set<NailMatteTask>(["matting", "segmentation", "visual_prompt"]);

function parseBoxes(value: unknown): NailMatteBox[] | null {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > MAX_BOXES) return null;
  const boxes: NailMatteBox[] = [];
  for (const item of value) {
    if (!Array.isArray(item) || item.length !== 4) return null;
    const numbers = item.map((entry) => (typeof entry === "number" ? entry : Number.NaN));
    if (numbers.some((entry) => !Number.isFinite(entry))) return null;
    const [x1, y1, x2, y2] = numbers;
    if (x2 <= x1 || y2 <= y1) return null;
    boxes.push([x1, y1, x2, y2]);
  }
  return boxes;
}

function degradedResponse(error: NailMatteApiError): NextResponse {
  const body: Record<string, unknown> = {
    degraded: true,
    reason: error.reason,
    error: error.message,
  };
  const headers: Record<string, string> = {};
  if (error.retryAfterSeconds !== null) {
    body.retryAfterSeconds = error.retryAfterSeconds;
    headers["Retry-After"] = String(error.retryAfterSeconds);
  }
  return NextResponse.json(body, { status: error.statusCode, headers });
}

/**
 * GET /api/nail-matte
 * 返回入口可见性与就绪状态，不触发推理。
 * - 未配置 `VLM_MATTE_URL`：`{ enabled:false }`，前端整块不渲染。
 * - 已配置但上游不可达：`{ enabled:true, ready:false }`，前端显示不可用。
 */
export async function GET() {
  const config = getNailMatteConfig();
  if (!config) {
    return NextResponse.json({ enabled: false, ready: false, busy: false });
  }
  const health = await probeNailMatte();
  return NextResponse.json({
    enabled: true,
    ready: health?.ready ?? false,
    busy: health?.busy ?? false,
  });
}

/**
 * POST /api/nail-matte
 * Body: { image: string, task?: "matting"|"segmentation"|"visual_prompt", query?: string, boxes?: number[][] }
 *
 * 转发到本机 WeVisOne-VL 服务并只回传结构化字段：
 * 上游的 VLM 文本 `response`、`metrics` 与任何鉴权信息都不外泄。
 * 请求体按白名单重建，调用方无法通过本路由触发上游的 `imagePath` 分支。
 */
export async function POST(req: NextRequest) {
  const config = getNailMatteConfig();
  if (!config) {
    return NextResponse.json(
      { degraded: true, reason: "disabled", error: "本机抠图服务未启用" },
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

  // ── 2. 参数校验（只读四个白名单字段，其余忽略）──
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

  const task: NailMatteTask =
    typeof body.task === "string" && ALLOWED_TASKS.has(body.task as NailMatteTask)
      ? (body.task as NailMatteTask)
      : "matting";

  const rawQuery = typeof body.query === "string" ? body.query.trim() : "";
  if (rawQuery.length > MAX_QUERY_LENGTH) {
    return NextResponse.json({ error: "提示词过长" }, { status: 400 });
  }
  const query = rawQuery || DEFAULT_QUERY;

  const boxes = parseBoxes(body.boxes);
  if (boxes === null) {
    return NextResponse.json(
      { error: `候选框不合法：最多 ${MAX_BOXES} 组，每组 [x1,y1,x2,y2] 且需满足 x1<x2、y1<y2` },
      { status: 400 }
    );
  }
  if (boxes.length > 0 && task !== "visual_prompt") {
    return NextResponse.json(
      { error: "仅在 visual_prompt 模式下可以传候选框" },
      { status: 400 }
    );
  }

  // ── 3. 身份与限流（复用现有配额体系，不新建鉴权）──
  const session = requireUserWithRenewal(req);
  const user = session?.user ?? null;
  const identity = user ? `user:${user.id}` : guestIdentityFromHeaders(req.headers);
  const limit = getRateLimiter().consume("nailMatte", identity);
  if (!limit.ok) {
    return NextResponse.json(
      {
        degraded: true,
        reason: "rate_limited",
        error: "精细抠图请求过于频繁，请稍后再试",
        retryAfterSeconds: limit.retryAfterSeconds,
      },
      { status: 429, headers: { "Retry-After": String(limit.retryAfterSeconds) } }
    );
  }

  // ── 4. 转发 ──
  try {
    const result = await requestNailMatte({ image, task, query, boxes });
    return applyRenewedCookies(NextResponse.json(result), session);
  } catch (err) {
    if (err instanceof NailMatteApiError) {
      if (err.statusCode === 400 || err.statusCode === 413) {
        return applyRenewedCookies(
          NextResponse.json({ error: err.message }, { status: err.statusCode }),
          session
        );
      }
      return applyRenewedCookies(degradedResponse(err), session);
    }
    // 内部异常原文不外泄，只写服务端日志。
    console.error("[nail-matte] unexpected error:", err);
    return NextResponse.json(
      { degraded: true, reason: "upstream_error", error: "抠图服务暂时不可用" },
      { status: 502 }
    );
  }
}
