/**
 * WorkItem 跨页参数桥（方案 §9.4/§9.5）：把分散的 gallery / collect / preset
 * 参数统一为 ?work=<workId>，同时兼容全部旧参数。
 *
 * 优先级：work > gallery > collect > preset（gallery 优先于 preset 沿用
 * 编辑器现行口径，见白皮书 §4.6）。
 *
 * 边界：本模块只做参数解析与作品装载；页面消费后的一切行为（是否自动
 * 贴合等）由各页既有合同决定，本模块不改变任何产品能力边界。
 */

import { getWorkItem } from "./work-items.ts";
import type { WorkItem } from "./work-items.ts";

export type WorkRef =
  | { kind: "work"; id: string }
  | { kind: "gallery"; id: string }
  | { kind: "collect"; id: string }
  | { kind: "preset"; id: string };

export type WorkRefParams = {
  work?: string | null;
  gallery?: string | null;
  collect?: string | null;
  preset?: string | null;
};

/** 按优先级解析跨页参数；全部缺失/为空时返回 null。 */
export function resolveWorkRef(params: WorkRefParams): WorkRef | null {
  if (params.work) return { kind: "work", id: params.work };
  if (params.gallery) return { kind: "gallery", id: params.gallery };
  if (params.collect) return { kind: "collect", id: params.collect };
  if (params.preset) return { kind: "preset", id: params.preset };
  return null;
}

/** WorkItem 预览 Blob → File（沿用旧收录带入上传管线的 File 形态）。 */
function workItemToFile(item: WorkItem): File {
  const extension = item.previewBlob.type.includes("png")
    ? "png"
    : item.previewBlob.type.includes("webp")
      ? "webp"
      : "jpg";
  return new File([item.previewBlob], `jiaru-work-${item.id.slice(0, 8)}.${extension}`, {
    type: item.previewBlob.type || "image/jpeg",
  });
}

/**
 * 读取 ?work= 指向的本地作品并转为 File（供编辑器/AI/AR 既有上传校验
 * 管线复用）。作品缺失、读取失败或 blob 缺失时返回 null（静默降级，
 * 不阻塞手动上传主流程——与 gallery-bridge 同一口径）。
 */
export async function loadWorkItemReference(id: string): Promise<File | null> {
  try {
    const item = await getWorkItem(id);
    if (!item || !(item.previewBlob instanceof Blob)) return null;
    return workItemToFile(item);
  } catch {
    return null;
  }
}
