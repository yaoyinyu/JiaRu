/**
 * /editor 纹理试色页的纯逻辑状态模块（不依赖 DOM 与并行代理文件，可被 node:test 直接测试）。
 *
 * 覆盖四类可测逻辑：
 * 1) activeTexture 解析（钉选纹理优先 → 套装指位匹配 → 缺失分支提示）；
 * 2) placement 替换（同一甲面框重贴时先移除旧贴合）；
 * 3) history 撤销栈（变更前 push、undo 弹栈、空栈不动）；
 * 4) 手动甲面框创建（尺寸钳制与空闲指位推断）。
 *
 * placement / frame 相关类型按结构化最小接口编码，兼容
 * `@/lib/canvas/placements` 的 NailPlacement 与
 * `@/lib/nail-detection-cascade` 的 NailDetectionRegion。
 */

import {
  textureSrcFor,
  type NailTextureSet,
} from "./nail-texture-sets.ts";
import type { NailTextureCandidate } from "./nail-texture-recognition/types.ts";

/** 指位数量（0=拇指 … 4=小指）。 */
export const FINGER_COUNT = 5;

/** 钉选纹理键格式："<套装id>/<指位>"。 */
export function textureKeyFor(setId: string, finger: number): string {
  return `${setId}/${finger}`;
}

export function parsePinnedTextureKey(
  key: string | null | undefined
): { setId: string; finger: number } | null {
  if (!key) return null;
  const separator = key.lastIndexOf("/");
  if (separator <= 0 || separator >= key.length - 1) return null;
  const setId = key.slice(0, separator);
  const finger = Number.parseInt(key.slice(separator + 1), 10);
  if (!Number.isInteger(finger) || finger < 0 || finger >= FINGER_COUNT) return null;
  return { setId, finger };
}

export interface ResolvedTexture {
  /** 纹理键（与钉选键同格式） */
  key: string;
  /** 纹理 PNG 的 public 路径 */
  src: string;
  setId: string;
  finger: number;
}

export type ActiveTextureResolution =
  | { status: "pinned"; texture: ResolvedTexture }
  | { status: "set"; texture: ResolvedTexture }
  | { status: "missing"; texture: null; message: string };

/** 指位缺失或该指无纹理时的固定提示（不得贴合，引导用户确认指位或钉选）。 */
export const MISSING_FINGER_HINT = "请先在套装中确认指位或钉选单张纹理，再点击甲面框贴合。";
/** 未选择任何套装/钉选时的提示。 */
export const NO_SELECTION_HINT = "请先在下方选择纹理套装，或在展开的套装卡中钉选一张纹理。";

/**
 * 解析当前点击应使用的纹理：
 * 1) 钉选纹理优先；钉选指向的套装/纹理不存在时视为失效，回落到套装匹配；
 * 2) 有激活套装时按甲面框指位取纹理；指位缺失或该指无纹理 → missing 分支；
 * 3) 两者皆无 → missing 分支（未选择）。
 */
export function resolveActiveTexture(params: {
  sets: readonly NailTextureSet[];
  pinnedTextureKey: string | null;
  activeSetId: string | null;
  /** 甲面框的指位（可能为 null） */
  finger: number | null;
}): ActiveTextureResolution {
  const { sets, pinnedTextureKey, activeSetId, finger } = params;

  const pinned = parsePinnedTextureKey(pinnedTextureKey);
  if (pinned) {
    const set = sets.find((item) => item.id === pinned.setId);
    const texture = set?.textures.find((item) => item.finger === pinned.finger);
    if (set && texture) {
      return {
        status: "pinned",
        texture: { key: textureKeyFor(set.id, pinned.finger), src: texture.src, setId: set.id, finger: pinned.finger },
      };
    }
  }

  if (activeSetId) {
    const set = sets.find((item) => item.id === activeSetId);
    if (set) {
      if (finger === null) {
        return { status: "missing", texture: null, message: MISSING_FINGER_HINT };
      }
      const texture = textureSrcFor(set, finger);
      if (!texture) {
        return { status: "missing", texture: null, message: MISSING_FINGER_HINT };
      }
      return {
        status: "set",
        texture: { key: textureKeyFor(set.id, finger), src: texture.src, setId: set.id, finger },
      };
    }
  }

  return { status: "missing", texture: null, message: NO_SELECTION_HINT };
}

/** 第一个未被占用的指位；全部占用返回 null。 */
export function firstUnoccupiedFinger(
  occupied: readonly (number | null)[]
): number | null {
  const taken = new Set<number>();
  for (const finger of occupied) {
    if (finger !== null) taken.add(finger);
  }
  for (let finger = 0; finger < FINGER_COUNT; finger += 1) {
    if (!taken.has(finger)) return finger;
  }
  return null;
}

export interface PlacementLike {
  id: string;
  /** 所属甲面框 id（NailPlacement 允许 null）；同一框重贴时旧贴合被替换 */
  frameId: string | null;
}

/** 同一甲面框重贴：先移除该框旧贴合，再追加新贴合。 */
export function replacePlacementForFrame<T extends PlacementLike>(
  placements: readonly T[],
  next: T
): T[] {
  return [...placements.filter((item) => item.frameId !== next.frameId), next];
}

/** 变更前把当前贴合列表压入撤销栈（浅拷贝快照）。 */
export function pushPlacementHistory<T>(
  history: readonly (readonly T[])[],
  snapshot: readonly T[]
): T[][] {
  return [...history.map((entry) => [...entry]), [...snapshot]];
}

/** 撤销：弹栈恢复上一次快照；空栈返回 null（调用方保持现状）。 */
export function undoPlacementHistory<T>(
  history: readonly (readonly T[])[]
): { placements: T[]; history: T[][] } | null {
  if (history.length === 0) return null;
  return {
    placements: [...history[history.length - 1]],
    history: history.slice(0, -1).map((entry) => [...entry]),
  };
}

export interface ManualFrame {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
}

/** 手动甲面框长度比例（原图最长边的 10%）。 */
export const MANUAL_FRAME_LENGTH_RATIO = 0.1;
/** 手动甲面框宽长比（长度的 58%）。 */
export const MANUAL_FRAME_WIDTH_RATIO = 0.58;
export const MANUAL_FRAME_LENGTH_MIN = 42;
export const MANUAL_FRAME_LENGTH_MAX = 120;
export const MANUAL_FRAME_WIDTH_MIN = 28;
export const MANUAL_FRAME_WIDTH_MAX = 72;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * 在空白处新建手动甲面框：
 * 尺寸按原图最长边 10% / 58% 推导并钳制到 42–120 / 28–72，
 * 指位取第一个空闲指位（全部占用为 null），坐标钳制在图内。
 */
export function buildManualFrame(params: {
  id: string;
  x: number;
  y: number;
  imageWidth: number;
  imageHeight: number;
  occupiedFingers: readonly (number | null)[];
}): ManualFrame {
  const { id, x, y, imageWidth, imageHeight, occupiedFingers } = params;
  const maxDimension = Math.max(imageWidth, imageHeight);
  const nl = clamp(
    Math.round(maxDimension * MANUAL_FRAME_LENGTH_RATIO),
    MANUAL_FRAME_LENGTH_MIN,
    MANUAL_FRAME_LENGTH_MAX
  );
  const nw = clamp(
    Math.round(nl * MANUAL_FRAME_WIDTH_RATIO),
    MANUAL_FRAME_WIDTH_MIN,
    MANUAL_FRAME_WIDTH_MAX
  );
  const halfWidth = nw / 2;
  const halfLength = nl / 2;
  return {
    id,
    cx: clamp(x, halfWidth, Math.max(halfWidth, imageWidth - halfWidth)),
    cy: clamp(y, halfLength, Math.max(halfLength, imageHeight - halfLength)),
    angle: 0,
    nl,
    nw,
    assignedFinger: firstUnoccupiedFinger(occupiedFingers),
  };
}

/** 甲面框的最小结构接口（兼容 NailDetectionRegion）。 */
export interface FrameLike {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
  confidence?: "high" | "medium" | "low";
  source?: NailTextureCandidate["source"];
  mask?: NailTextureCandidate["mask"];
  warnings?: string[];
}

/** 甲面框 → 精细抠图候选（只换算字段名，几何保持原图坐标域）。 */
export function frameToMatteCandidate(frame: FrameLike): NailTextureCandidate {
  return {
    id: frame.id,
    cx: frame.cx,
    cy: frame.cy,
    length: frame.nl,
    width: frame.nw,
    angle: frame.angle,
    score: 1,
    confidence: frame.confidence ?? "low",
    source: frame.source ?? "manual",
    mask: frame.mask,
    suggestedFinger: frame.assignedFinger,
    warnings: frame.warnings ? [...frame.warnings] : undefined,
  };
}

export interface FrameGeometry {
  cx: number;
  cy: number;
  length: number;
  width: number;
}

/**
 * 精细抠图结果回填：按 candidateId 替换 mask，并用几何解析器重算该帧
 * cx/cy/nl/nw；mask 有值但几何为 null 时保留原几何。未命中的帧原样保留。
 */
export function applyRefinedFrameMasks<
  F extends { id: string; cx: number; cy: number; nl: number; nw: number; mask?: M },
  M,
>(
  frames: readonly F[],
  masksById: ReadonlyMap<string, M>,
  geometryFromMask: (frame: F) => FrameGeometry | null
): F[] {
  return frames.map((frame) => {
    if (!masksById.has(frame.id)) return frame;
    const withMask: F = { ...frame, mask: masksById.get(frame.id) };
    const geometry = geometryFromMask(withMask);
    if (!geometry) return withMask;
    return {
      ...withMask,
      cx: geometry.cx,
      cy: geometry.cy,
      nl: geometry.length,
      nw: geometry.width,
    };
  });
}
