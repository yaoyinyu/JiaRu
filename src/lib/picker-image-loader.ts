/**
 * 选择器图片解码（带备用通道）。
 *
 * 甲面选择器此前只用一个 `<img>` 解码 `imageUrl`：部分移动浏览器/来源（相册、
 * 微信转发、超大照片）会让 `<img>` 解码失败，即使同一份字节已被 `createImageBitmap`
 * 成功解码过，界面就停在黑屏与「图片加载失败」上。
 *
 * 这里按「`<img>` → fetch + createImageBitmap 画到 canvas」两级解码，
 * 调用方拿到统一的 `HTMLImageElement | HTMLCanvasElement`（两者都有 width/height，
 * 也都是 MediaPipe Hands 的合法输入），失败时抛出带 code 的错误供界面给出可恢复提示。
 */

export type PickerImageSource = HTMLImageElement | HTMLCanvasElement;

export interface LoadedPickerImage {
  source: PickerImageSource;
  width: number;
  height: number;
}

export type PickerImageLoadErrorCode = "cancelled" | "decode_error" | "network_error";

export class PickerImageLoadError extends Error {
  readonly code: PickerImageLoadErrorCode;

  constructor(code: PickerImageLoadErrorCode, message: string) {
    super(message);
    this.name = "PickerImageLoadError";
    this.code = code;
  }
}

function createAbortError(): PickerImageLoadError {
  return new PickerImageLoadError("cancelled", "图片载入已取消");
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw createAbortError();
}

function decodeWithImageElement(
  url: string,
  signal?: AbortSignal
): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    // 同源 blob:/data: 不需要 CORS；远程地址保持 anonymous 以配合跨域画布。
    if (!url.startsWith("blob:") && !url.startsWith("data:")) {
      image.crossOrigin = "anonymous";
    }
    image.decoding = "async";
    let settled = false;
    const cleanup = () => {
      image.onload = null;
      image.onerror = null;
      signal?.removeEventListener("abort", onAbort);
    };
    const finish = (callback: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      callback();
    };
    const onAbort = () => finish(() => reject(createAbortError()));
    image.onload = () => finish(() => resolve(image));
    image.onerror = () =>
      finish(() => reject(new PickerImageLoadError("decode_error", "图片解码失败")));
    signal?.addEventListener("abort", onAbort, { once: true });
    image.src = url;
  });
}

/**
 * 超过该像素数时按长边上限生成位图：移动端同时持有页面预览与选择器副本时，
 * 全尺寸 `<img>` 位图加同尺寸画布会把内存压力推到解码失败。
 */
const MAX_DECODE_PIXELS = 24_000_000;
const MAX_DECODE_LONG_SIDE = 3072;

/** 从 Blob 解码并画到画布，作为 `<img>` 失败后的备用通道。 */
async function decodeBlobToCanvas(
  blob: Blob,
  signal?: AbortSignal
): Promise<LoadedPickerImage> {
  if (typeof createImageBitmap !== "function") {
    throw new PickerImageLoadError("decode_error", "当前浏览器不支持备用图片解码");
  }
  throwIfAborted(signal);
  if (blob.size === 0) throw new PickerImageLoadError("decode_error", "图片内容为空");

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(blob);
  } catch {
    throw new PickerImageLoadError("decode_error", "图片无法解码");
  }
  try {
    throwIfAborted(signal);
    let width = bitmap.width;
    let height = bitmap.height;
    if (width * height > MAX_DECODE_PIXELS) {
      const scale = MAX_DECODE_LONG_SIDE / Math.max(width, height);
      width = Math.max(1, Math.round(width * scale));
      height = Math.max(1, Math.round(height * scale));
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new PickerImageLoadError("decode_error", "画布不可用");
    context.drawImage(bitmap, 0, 0, width, height);
    return { source: canvas, width, height };
  } finally {
    bitmap.close();
  }
}

async function fetchBlobUrl(url: string, signal?: AbortSignal): Promise<Blob> {
  if (typeof fetch !== "function") {
    throw new PickerImageLoadError("decode_error", "当前浏览器不支持备用图片解码");
  }
  try {
    const response = await fetch(url, { signal });
    if (!response.ok && !url.startsWith("blob:")) {
      throw new PickerImageLoadError("network_error", `图片请求失败（${response.status}）`);
    }
    return await response.blob();
  } catch (error) {
    if (error instanceof PickerImageLoadError) throw error;
    if (signal?.aborted) throw createAbortError();
    throw new PickerImageLoadError("network_error", "图片读取失败");
  }
}

/**
 * 依次尝试 `<img>` → 原始 Blob → `fetch` 字节，全部失败时抛出 `PickerImageLoadError`。
 *
 * 原始 Blob 通道优先于 fetch：安卓相册返回的 `content://` 流在部分浏览器只可成功读取
 * 一次，交给调用方传入已经读进内存的 Blob 才能稳定重复解码。
 */
export async function loadPickerImage(
  url: string,
  options: { signal?: AbortSignal; blob?: Blob | null } = {}
): Promise<LoadedPickerImage> {
  throwIfAborted(options.signal);
  try {
    const image = await decodeWithImageElement(url, options.signal);
    const width = image.naturalWidth || image.width;
    const height = image.naturalHeight || image.height;
    if (width > 0 && height > 0) return { source: image, width, height };
  } catch (error) {
    if (error instanceof PickerImageLoadError && error.code === "cancelled") throw error;
  }
  if (options.blob && options.blob.size > 0) {
    return decodeBlobToCanvas(options.blob, options.signal);
  }
  const blob = await fetchBlobUrl(url, options.signal);
  return decodeBlobToCanvas(blob, options.signal);
}
