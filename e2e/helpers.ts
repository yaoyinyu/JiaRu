import type { BrowserContext } from "@playwright/test";

/** 在浏览器 Canvas 上生成纯色 PNG 测试夹具（内存内完成，不经磁盘模板）。 */
export async function pngBuffer(
  context: BrowserContext,
  width: number,
  height: number,
  color: string
): Promise<Buffer> {
  const page = await context.newPage();
  try {
    const dataUrl = await page.evaluate(
      ({ width, height, color }) => {
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("canvas 2d context unavailable");
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, width, height);
        return canvas.toDataURL("image/png");
      },
      { width, height, color }
    );
    return Buffer.from(dataUrl.slice(dataUrl.indexOf(",") + 1), "base64");
  } finally {
    await page.close();
  }
}

/** 1×1 像素 PNG data URL（简单占位用）。 */
export const TINY_PNG_DATA_URL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

/**
 * 生成真实尺寸的 PNG data URL（mock 生图响应用）。
 * 注意：必须 ≥320px——收录进图库的图在 AR 侧要过 validateImageUpload 的
 * 320–4096 像素校验门，1×1 占位图会让「收录→AR」链路静默降级。
 */
export async function pngDataUrl(
  context: BrowserContext,
  width: number,
  height: number,
  color: string
): Promise<string> {
  const buffer = await pngBuffer(context, width, height, color);
  return `data:image/png;base64,${buffer.toString("base64")}`;
}
