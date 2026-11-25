export const SUPPORTED_IMAGE_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

const SUPPORTED_MIME_SET: ReadonlySet<string> = new Set(SUPPORTED_IMAGE_MIME_TYPES);

/** 常见但不规范的 MIME 别名（部分相册、旧版 Android 文件选择器会给出）。 */
const MIME_ALIASES: Readonly<Record<string, string>> = {
  "image/jpg": "image/jpeg",
  "image/pjpeg": "image/jpeg",
  "image/x-png": "image/png",
  "image/x-webp": "image/webp",
};

/** 浏览器普遍无法解码、需要用户先转码的格式。 */
const TRANSCODE_REQUIRED_MIME_TYPES: ReadonlySet<string> = new Set([
  "image/heic",
  "image/heif",
  "image/heic-sequence",
  "image/heif-sequence",
]);

/**
 * 缺少 MIME（部分微信/安卓来源给空字符串）或只给通用二进制类型时，
 * 以「能否解码」作为格式判据，避免把有效 JPG/PNG 误判为不支持。
 */
function shouldAttemptDecodeWithoutMime(mime: string): boolean {
  if (!mime) return true;
  return mime === "application/octet-stream" || mime === "binary/octet-stream";
}

function normalizeMime(type: string | null | undefined): string {
  const normalized = (type ?? "").trim().toLowerCase();
  return MIME_ALIASES[normalized] ?? normalized;
}

export const MAX_IMAGE_FILE_BYTES = 10 * 1024 * 1024;
export const MIN_IMAGE_DIMENSION = 320;
export const MAX_IMAGE_DIMENSION = 4096;

export type ImageUploadValidationCode =
  | "unsupported_type"
  | "file_too_large"
  | "decode_failed"
  | "resolution_too_small"
  | "resolution_too_large";

export type ImageUploadValidationResult =
  | { ok: true; width: number; height: number }
  | { ok: false; code: ImageUploadValidationCode; message: string };

interface ImageFileLike extends Blob {
  type: string;
  size: number;
}

interface DecodedImageInfo {
  width: number;
  height: number;
}

type ImageDecoder = (file: Blob) => Promise<DecodedImageInfo>;

async function decodeImageInBrowser(file: Blob): Promise<DecodedImageInfo> {
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    try {
      return { width: bitmap.width, height: bitmap.height };
    } finally {
      bitmap.close();
    }
  }

  return await new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("image decode failed"));
    };
    image.src = url;
  });
}

export async function validateImageUpload(
  file: ImageFileLike,
  decode: ImageDecoder = decodeImageInBrowser
): Promise<ImageUploadValidationResult> {
  const mime = normalizeMime(file.type);
  if (!SUPPORTED_MIME_SET.has(mime)) {
    if (TRANSCODE_REQUIRED_MIME_TYPES.has(mime)) {
      return {
        ok: false,
        code: "unsupported_type",
        message: "暂不支持 HEIC/HEIF 照片，请在相册中导出为 JPG 后重试。",
      };
    }
    if (!shouldAttemptDecodeWithoutMime(mime)) {
      return {
        ok: false,
        code: "unsupported_type",
        message: "仅支持 JPG、PNG 与 WebP 图片。",
      };
    }
    // 无 MIME / 通用二进制：继续走解码与尺寸校验，能解码即视为可用图片。
  }

  if (file.size > MAX_IMAGE_FILE_BYTES) {
    return {
      ok: false,
      code: "file_too_large",
      message: "图片大小不能超过 10 MB。",
    };
  }

  let decoded: DecodedImageInfo;
  try {
    decoded = await decode(file);
  } catch {
    return {
      ok: false,
      code: "decode_failed",
      message: "图片无法解码，请换一张 JPG、PNG 或 WebP。",
    };
  }

  if (
    !Number.isFinite(decoded.width) ||
    !Number.isFinite(decoded.height) ||
    decoded.width <= 0 ||
    decoded.height <= 0
  ) {
    return {
      ok: false,
      code: "decode_failed",
      message: "图片无法解码，请换一张 JPG、PNG 或 WebP。",
    };
  }

  if (decoded.width < MIN_IMAGE_DIMENSION || decoded.height < MIN_IMAGE_DIMENSION) {
    return {
      ok: false,
      code: "resolution_too_small",
      message: `图片分辨率不能低于 ${MIN_IMAGE_DIMENSION}×${MIN_IMAGE_DIMENSION} 像素。`,
    };
  }

  if (decoded.width > MAX_IMAGE_DIMENSION || decoded.height > MAX_IMAGE_DIMENSION) {
    return {
      ok: false,
      code: "resolution_too_large",
      message: `图片长边不能超过 ${MAX_IMAGE_DIMENSION} 像素。`,
    };
  }

  return { ok: true, width: decoded.width, height: decoded.height };
}
