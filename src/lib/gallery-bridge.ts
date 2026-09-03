import { GALLERY_IMAGES } from "./utils.ts";
import {
  getCollectStore,
  type GalleryCollectRecord,
} from "./gallery-collection.ts";

export type GalleryLook = (typeof GALLERY_IMAGES)[number];

/** 图库引用加载结果：File 供 AR 纹理管线与 AI 参考图压缩链路共用。 */
export type GalleryReference = {
  file: File;
  /** 展示名：静态款式名或「我的收录」。 */
  name: string;
  /** 关联的图库款式（收录图无静态款式时为 null）。 */
  look: GalleryLook | null;
  /** 收录记录（仅 ?collect= 路径返回）。 */
  collect: GalleryCollectRecord | null;
};

/** 按 id 字符串查找静态图库款式；非法或未知 id 返回 null。 */
export function findGalleryLook(id: string | null | undefined): GalleryLook | null {
  if (!id) return null;
  const parsed = Number(id);
  if (!Number.isInteger(parsed) || parsed <= 0) return null;
  return GALLERY_IMAGES.find((item) => item.id === parsed) ?? null;
}

/** 从静态资源路径推导下载文件名（如 /nail-gallery/ai-look-1.jpg → ai-look-1.jpg）。 */
export function fileNameFromSrc(src: string): string {
  const last = src.split("/").pop() ?? "";
  return last || "gallery-image.jpg";
}

/**
 * 加载静态图库款式图为 File。
 * 任何失败（id 非法、网络错误、非 2xx、非图片类型）都返回 null，绝不抛错，
 * 保证调用方可以无阻塞降级到原有主流程。
 */
export async function loadGalleryReference(
  id: string | null | undefined,
  fetchImpl: typeof fetch = fetch
): Promise<GalleryReference | null> {
  const look = findGalleryLook(id);
  if (!look) return null;
  const file = await fetchImageAsFile(look.src, fetchImpl);
  if (!file) return null;
  return { file, name: look.name, look, collect: null };
}

/**
 * 加载 IndexedDB 收录图为 File。
 * 任何失败（id 非法、记录不存在、读取失败）返回 null，绝不抛错。
 */
export async function loadCollectReference(
  collectId: string | null | undefined
): Promise<GalleryReference | null> {
  if (!collectId) return null;
  const store = getCollectStore();
  let record: GalleryCollectRecord | null = null;
  try {
    record = await store.get(collectId);
  } catch {
    return null;
  }
  if (!record) return null;
  const file = blobToFile(record.blob, `collect-${record.id}.jpg`);
  if (!file) return null;
  return { file, name: "我的收录", look: null, collect: record };
}

/**
 * 统一入口：优先消费 ?gallery=（静态款式），其次 ?collect=（IndexedDB 收录）。
 * 两类参数都缺失或加载失败时返回 null。
 */
export async function loadReferenceFromParams(
  params: { gallery?: string | null; collect?: string | null },
  fetchImpl: typeof fetch = fetch
): Promise<GalleryReference | null> {
  if (params.gallery) {
    const fromGallery = await loadGalleryReference(params.gallery, fetchImpl);
    if (fromGallery) return fromGallery;
  }
  if (params.collect) {
    return await loadCollectReference(params.collect);
  }
  return null;
}

/** fetch 静态图并包装为 File；失败返回 null。fetchImpl 可注入便于单测。 */
async function fetchImageAsFile(
  src: string,
  fetchImpl: typeof fetch
): Promise<File | null> {
  let blob: Blob;
  try {
    const resp = await fetchImpl(src);
    if (!resp.ok) return null;
    blob = await resp.blob();
  } catch {
    return null;
  }
  return blobToFile(blob, fileNameFromSrc(src));
}

/** 把 Blob 包装为图片 File；类型不是图片时返回 null。 */
function blobToFile(blob: Blob, fileName: string): File | null {
  const type = blob.type || "image/jpeg";
  if (!type.startsWith("image/")) return null;
  return new File([blob], fileName, { type });
}
