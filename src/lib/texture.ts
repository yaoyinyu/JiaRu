/**
 * 纹理工具函数 — 美甲纹理的提取、缩放和资源管理
 *
 * 所有处理在浏览器本地完成，不发送任何数据到服务器。
 */

const MAX_TEXTURE_SIZE = 256;

/**
 * 从图片 URL 和裁剪区域提取 ImageBitmap
 *
 * @param imageUrl - 上传图片的本地 blob URL
 * @param crop - 裁剪区域（原图像素坐标）
 * @returns 提取的 ImageBitmap，宽度 ≤ MAX_TEXTURE_SIZE
 */
export async function extractTexture(
  imageUrl: string,
  crop: { x: number; y: number; w: number; h: number }
): Promise<ImageBitmap> {
  // 1. 加载原图
  const img = await loadImage(imageUrl);

  // 2. 边界保护：裁剪区域不能超出原图
  const sx = Math.max(0, Math.floor(crop.x));
  const sy = Math.max(0, Math.floor(crop.y));
  const sw = Math.min(img.naturalWidth - sx, Math.ceil(crop.w));
  const sh = Math.min(img.naturalHeight - sy, Math.ceil(crop.h));

  if (sw <= 0 || sh <= 0) {
    throw new Error(`无效的裁剪区域: ${JSON.stringify({ sx, sy, sw, sh })}`);
  }

  // 3. 如果裁剪区域超过最大尺寸，需要先缩小再提取
  if (sw <= MAX_TEXTURE_SIZE && sh <= MAX_TEXTURE_SIZE) {
    // 直接裁剪
    return createImageBitmap(img, sx, sy, sw, sh);
  }

  // 裁剪区域过大，先缩放到离屏 canvas 再生成 bitmap
  const scale = Math.min(MAX_TEXTURE_SIZE / sw, MAX_TEXTURE_SIZE / sh);
  const dw = Math.round(sw * scale);
  const dh = Math.round(sh * scale);

  const canvas = new OffscreenCanvas(dw, dh);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("无法创建 OffscreenCanvas 2D 上下文");
  }
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, dw, dh);
  return createImageBitmap(canvas);
}

/**
 * 限制纹理最大尺寸（用于已有 ImageBitmap 的二次处理）
 */
export async function clampTextureSize(
  bitmap: ImageBitmap,
  maxSize: number = MAX_TEXTURE_SIZE
): Promise<ImageBitmap> {
  if (bitmap.width <= maxSize && bitmap.height <= maxSize) {
    return bitmap;
  }

  const scale = Math.min(maxSize / bitmap.width, maxSize / bitmap.height);
  const dw = Math.round(bitmap.width * scale);
  const dh = Math.round(bitmap.height * scale);

  const canvas = new OffscreenCanvas(dw, dh);
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("无法创建 OffscreenCanvas 2D 上下文");
  }
  ctx.drawImage(bitmap, 0, 0, dw, dh);
  return createImageBitmap(canvas);
}

/**
 * 释放 ImageBitmap 占用的 GPU 内存
 */
export function disposeTexture(bitmap: ImageBitmap | null | undefined): void {
  if (bitmap && typeof bitmap.close === "function") {
    bitmap.close();
  }
}

/**
 * 释放所有纹理
 */
export function disposeAllTextures(
  textures: (ImageBitmap | null | undefined)[]
): void {
  for (const tex of textures) {
    disposeTexture(tex);
  }
}

// ─── 内部辅助 ────────────────────────────────────────────

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`图片加载失败: ${url}`));
    img.src = url;
  });
}
