/**
 * 头像图片处理（浏览器端）：把用户选择的图片居中裁切、压缩为
 * PROFILE_LIMITS.avatarSize 的正方形 JPEG Data URL，再交给档案接口存档。
 * 在调用时依赖 DOM，因此只能从客户端组件引用。
 */

import { PROFILE_LIMITS } from "./profile";

export const AVATAR_ACCEPT = "image/png,image/jpeg,image/webp";

const ALLOWED_MIME = new Set(["image/png", "image/jpeg", "image/webp"]);

type DecodedImage = { source: CanvasImageSource; width: number; height: number; release: () => void };

async function decodeImage(file: File): Promise<DecodedImage> {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      return { source: bitmap, width: bitmap.width, height: bitmap.height, release: () => bitmap.close() };
    } catch {
      // 部分浏览器不支持 imageOrientation 选项或该格式，退回 <img> 解码
    }
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.decoding = "async";
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("图片无法解码，请换一张试试"));
      image.src = objectUrl;
    });
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    if (!width || !height) throw new Error("图片无法解码，请换一张试试");
    return { source: image, width, height, release: () => URL.revokeObjectURL(objectUrl) };
  } catch (err) {
    URL.revokeObjectURL(objectUrl);
    throw err;
  }
}

/** 选择图片 → 正方形压缩头像 Data URL；失败时抛出可直接展示的中文错误 */
export async function createAvatarDataUrl(file: File): Promise<string> {
  if (!file.size) throw new Error("图片内容为空，请重新选择");
  if (file.size > PROFILE_LIMITS.avatarMaxFileBytes) {
    throw new Error(`图片不能超过 ${Math.round(PROFILE_LIMITS.avatarMaxFileBytes / 1024 / 1024)}MB，请压缩后再试`);
  }
  if (!ALLOWED_MIME.has(file.type)) throw new Error("仅支持 PNG、JPEG 或 WebP 图片");

  const decoded = await decodeImage(file);
  try {
    const size = PROFILE_LIMITS.avatarSize;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("当前浏览器不支持图片处理，请更换浏览器");

    // 居中裁切为正方形（同一比例缩放后取中心区域）
    const scale = Math.max(size / decoded.width, size / decoded.height);
    const drawWidth = decoded.width * scale;
    const drawHeight = decoded.height * scale;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(decoded.source, (size - drawWidth) / 2, (size - drawHeight) / 2, drawWidth, drawHeight);

    const dataUrl = canvas.toDataURL("image/jpeg", 0.86);
    if (!dataUrl.startsWith("data:image/jpeg;base64,")) {
      throw new Error("头像生成失败，请重新选择图片");
    }
    return dataUrl;
  } finally {
    decoded.release();
  }
}
