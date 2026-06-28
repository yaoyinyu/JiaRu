import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/generate-ai
 * Body: { prompt: string }
 * Returns: { imageUrl: string } | { error: string }
 *
 * 使用 OpenAI DALL-E 3 生成美甲效果图。
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

  // ── 3. 检查 API Key ──
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey || apiKey === "your-key-here") {
    return NextResponse.json(
      { error: "服务器未配置 OPENAI_API_KEY，请联系管理员" },
      { status: 503 }
    );
  }

  // ── 4. 构造美甲专用 prompt ──
  const enhancedPrompt = `${prompt}, nail art design on fingernails, manicure, close-up hand photo, beautiful, high detail`;

  // ── 5. 调用 OpenAI Images API (DALL-E 3) ──
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);

    const resp = await fetch("https://api.openai.com/v1/images/generations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "dall-e-3",
        prompt: enhancedPrompt,
        n: 1,
        size: "1024x1024",
        quality: "standard",
      }),
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!resp.ok) {
      const errText = await resp.text();
      let errMsg: string;
      try {
        const errJson = JSON.parse(errText);
        errMsg = errJson?.error?.message || errText;
      } catch {
        errMsg = errText;
      }

      if (resp.status === 401) {
        return NextResponse.json(
          { error: "OpenAI API Key 无效" },
          { status: 401 }
        );
      }
      if (resp.status === 429) {
        return NextResponse.json(
          { error: "API 调用频率过高，请稍后再试" },
          { status: 429 }
        );
      }
      return NextResponse.json(
        { error: `OpenAI API 错误: ${errMsg}` },
        { status: 502 }
      );
    }

    const data = await resp.json();
    const imageUrl: string | undefined = data?.data?.[0]?.url;

    if (!imageUrl) {
      return NextResponse.json(
        { error: "API 返回数据格式异常" },
        { status: 502 }
      );
    }

    return NextResponse.json({ imageUrl });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      return NextResponse.json(
        { error: "请求超时（30s），请重试" },
        { status: 504 }
      );
    }
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `服务器错误: ${msg}` },
      { status: 500 }
    );
  }
}
