/**
 * /editor 会话内编辑草稿（§5.7.3 阶段一）。
 *
 * 只保存甲面框、贴合实例、纹理选择与原图尺寸，不保存原图文件；
 * 恢复时由调用方把草稿尺寸与当前画布原图尺寸比对，不一致即丢弃。
 * storage 由调用方注入（浏览器传 sessionStorage，node 测试传内存实现），
 * 本模块不直接触碰 window，可在 node:test 中验证。
 *
 * 识别候选的 mask（Uint8Array 栅格）不是 JSON 安全数据且体积大，
 * 写入时统一剥离；恢复后的甲面框保留几何与指位，足够重建贴合与再次精细抠图。
 */

import type { NailDetectionRegion } from "./nail-detection-cascade.ts";
import type { NailPlacement } from "./canvas/placements.ts";

export const EDITOR_DRAFT_STORAGE_KEY = "jiaru-editor-draft-v1";

/** 编辑草稿：恢复编辑态所需的全部轻量数据（无原图）。 */
export interface EditorDraft {
  frames: NailDetectionRegion[];
  placements: NailPlacement[];
  activeSetId: string | null;
  pinnedTextureKey: string | null;
  /** 草稿对应的原图尺寸；恢复时与画布尺寸比对，不一致丢弃 */
  imageWidth: number;
  imageHeight: number;
  savedAt: number;
}

/** sessionStorage / 内存实现共用的最小存储接口。 */
export interface EditorDraftStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isValidFrame(value: unknown): boolean {
  if (typeof value !== "object" || value === null) return false;
  const frame = value as Record<string, unknown>;
  return (
    typeof frame.id === "string" &&
    frame.id.length > 0 &&
    isFiniteNumber(frame.cx) &&
    isFiniteNumber(frame.cy) &&
    isFiniteNumber(frame.angle) &&
    isFiniteNumber(frame.nl) &&
    isFiniteNumber(frame.nw) &&
    (frame.assignedFinger === null || typeof frame.assignedFinger === "number")
  );
}

function isValidPlacement(value: unknown): boolean {
  if (typeof value !== "object" || value === null) return false;
  const placement = value as Record<string, unknown>;
  return (
    typeof placement.id === "string" &&
    placement.id.length > 0 &&
    typeof placement.textureKey === "string" &&
    typeof placement.textureSrc === "string" &&
    isFiniteNumber(placement.cx) &&
    isFiniteNumber(placement.cy)
  );
}

function isEditorDraftShape(value: unknown): value is EditorDraft {
  if (typeof value !== "object" || value === null) return false;
  const draft = value as Record<string, unknown>;
  if (!Array.isArray(draft.frames) || !draft.frames.every(isValidFrame)) return false;
  if (!Array.isArray(draft.placements) || !draft.placements.every(isValidPlacement)) {
    return false;
  }
  if (
    draft.activeSetId !== null &&
    typeof draft.activeSetId !== "string"
  ) {
    return false;
  }
  if (
    draft.pinnedTextureKey !== null &&
    typeof draft.pinnedTextureKey !== "string"
  ) {
    return false;
  }
  if (
    !isFiniteNumber(draft.imageWidth) ||
    draft.imageWidth <= 0 ||
    !isFiniteNumber(draft.imageHeight) ||
    draft.imageHeight <= 0 ||
    !isFiniteNumber(draft.savedAt)
  ) {
    return false;
  }
  return true;
}

/** 写入草稿；mask 字段（Uint8Array）剥离后再序列化。存储异常（配额/隐私模式）返回 false。 */
export function saveEditorDraft(
  storage: EditorDraftStorage | null | undefined,
  draft: EditorDraft
): boolean {
  if (!storage) return false;
  try {
    const payload = {
      ...draft,
      // mask 字段（Uint8Array）剥离后再序列化；JSON.stringify 会省略 undefined。
      frames: draft.frames.map((frame) => ({ ...frame, mask: undefined })),
    };
    storage.setItem(EDITOR_DRAFT_STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

/** 读取草稿；缺失、存储异常、JSON 损坏或结构校验失败一律返回 null。 */
export function loadEditorDraft(
  storage: EditorDraftStorage | null | undefined
): EditorDraft | null {
  if (!storage) return null;
  let raw: string | null = null;
  try {
    raw = storage.getItem(EDITOR_DRAFT_STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isEditorDraftShape(parsed)) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** 清除草稿；存储异常静默忽略（无草稿即目标状态）。 */
export function clearEditorDraft(
  storage: EditorDraftStorage | null | undefined
): void {
  if (!storage) return;
  try {
    storage.removeItem(EDITOR_DRAFT_STORAGE_KEY);
  } catch {
    // 隐私模式下 removeItem 可能抛错；无草稿即目标状态。
  }
}

/** 恢复判决：草稿尺寸与当前原图尺寸是否一致（不一致由调用方丢弃并提示）。 */
export function draftMatchesImageSize(
  draft: EditorDraft,
  imageWidth: number,
  imageHeight: number
): boolean {
  return draft.imageWidth === imageWidth && draft.imageHeight === imageHeight;
}
