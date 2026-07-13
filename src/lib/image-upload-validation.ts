export const SUPPORTED_IMAGE_MIME_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
] as const;

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
  if (!SUPPORTED_IMAGE_MIME_TYPES.includes(file.type as (typeof SUPPORTED_IMAGE_MIME_TYPES)[number])) {
    return {
      ok: false,
      code: "unsupported_type",
      message: "仅支持 JPG、PNG 与 WebP 图片。",
    };
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
      message: "图片无法解码，请重新选择完整的 JPG、PNG 或 WebP 文件。",
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
      message: "图片无法解码，请重新选择完整的 JPG、PNG 或 WebP 文件。",
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
