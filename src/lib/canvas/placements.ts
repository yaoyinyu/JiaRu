/**
 * 编辑器「甲面框 + 纹理贴合实例」纯逻辑模块。
 *
 * 职责：由识别甲面框与纹理资产构建贴合实例（placement）、应用用户微调、
 * 命中测试与导出重放；除纹理加载辅助外不依赖 DOM，可在 node 测试中直接验证。
 *
 * 坐标与角度约定（与 ar-nail-shape / nail-geometry 一致）：
 *  - 全部几何均在原图像素域；angle 为甲面横轴方向角，局部 −Y 为甲尖方向；
 *  - 甲根方向为 (−sin(angle), cos(angle))，rootOffset 正值向指根移动；
 *  - 渲染长度由 computeTextureRenderPlan 保证 = 宽×纹理长宽比（钳内）：
 *    不短于甲面框长度、上限 3×估算长；任何绘制路径不得把纹理拉伸到
 *    与长宽比不符的矩形（用户经 adjust 显式改宽/改长除外）。
 */

import { computeTextureRenderPlan } from "../ar-nail-shape.ts";
import { adjustNailGeometry } from "../nail-geometry.ts";

export const PREVIEW_MAX_W = 400;
export const PREVIEW_MAX_H = 600;

/** 预览缩放：显示不超过 400×600 且从不放大（沿用旧笔刷画布口径） */
export function previewScale(width: number, height: number): number {
  if (width <= 0 || height <= 0) return 1;
  return Math.min(PREVIEW_MAX_W / width, PREVIEW_MAX_H / height, 1);
}

/** 用户贴合微调；字段值会被 adjustNailGeometry 钳制（0.75–1.4 / 0.7–1.45 / ±0.2） */
export interface PlacementAdjust {
  lengthScale: number;
  widthScale: number;
  rootOffset: number;
}

export const DEFAULT_PLACEMENT_ADJUST: PlacementAdjust = {
  lengthScale: 1,
  widthScale: 1,
  rootOffset: 0,
};

/** 一个纹理贴合实例（原图像素域；数组序即绘制层序，末尾在最上） */
export interface NailPlacement {
  id: string;
  /** 来源甲面框 id；由 buildPlacementFromFrame 构建时恒为 frame.id */
  frameId: string | null;
  /** 纹理标识 "<setId>/<finger>" */
  textureKey: string;
  textureSrc: string;
  /** 纹理长宽比（naturalHeight / naturalWidth） */
  aspect: number;
  /** 甲面横轴方向角（原图像素域） */
  angle: number;
  /** renderPlan 前的甲面框几何（重算 adjust 的基准） */
  baseCx: number;
  baseCy: number;
  baseLength: number;
  baseWidth: number;
  /** 当前渲染几何（原图像素域） */
  cx: number;
  cy: number;
  length: number;
  width: number;
  adjust: PlacementAdjust;
}

/**
 * 甲面框输入。字段与识别级联的甲面框结构（NailDetectionRegion）对齐，
 * 这里用本地结构类型解耦，不直接依赖该模块。
 */
export interface PlacementFrameInput {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  /** 甲面长（沿局部 −Y 甲尖方向） */
  nl: number;
  /** 甲面宽（沿局部 +X 横轴） */
  nw: number;
  /** 分配手指 0–4；未分配为 null */
  assignedFinger: number | null;
}

/** 由 base 甲面框几何 + 纹理长宽比 + 微调计算当前渲染几何（纯函数） */
function computePlacementGeometry(
  base: { cx: number; cy: number; length: number; width: number; angle: number },
  aspect: number,
  adjust: PlacementAdjust,
): { cx: number; cy: number; length: number; width: number } {
  // 长宽比保真：渲染长 = 宽×纹理长宽比（甲根锚定、钳内），再叠加用户微调
  const plan = computeTextureRenderPlan(base, aspect);
  const adjusted = adjustNailGeometry(
    { cx: plan.cx, cy: plan.cy, length: plan.length, width: base.width, angle: base.angle },
    adjust.lengthScale,
    adjust.rootOffset,
    adjust.widthScale,
  );
  return {
    cx: adjusted.cx,
    cy: adjusted.cy,
    length: adjusted.length,
    width: adjusted.width,
  };
}

/**
 * 由甲面框 + 纹理构建贴合实例。
 * id 确定性派生为 `placement-<frameId>`：同一框重复贴合时天然按 id 替换，
 * 也便于调用方按 frameId 去重。
 */
export function buildPlacementFromFrame(
  frame: PlacementFrameInput,
  texture: { key: string; src: string; aspect: number },
  adjust: PlacementAdjust = DEFAULT_PLACEMENT_ADJUST,
): NailPlacement {
  const base = {
    cx: frame.cx,
    cy: frame.cy,
    length: frame.nl,
    width: frame.nw,
    angle: frame.angle,
  };
  const geometry = computePlacementGeometry(base, texture.aspect, adjust);
  return {
    id: `placement-${frame.id}`,
    frameId: frame.id,
    textureKey: texture.key,
    textureSrc: texture.src,
    aspect: texture.aspect,
    angle: frame.angle,
    baseCx: base.cx,
    baseCy: base.cy,
    baseLength: base.length,
    baseWidth: base.width,
    cx: geometry.cx,
    cy: geometry.cy,
    length: geometry.length,
    width: geometry.width,
    adjust,
  };
}

/** 微调变化时从 base 几何整体重算渲染几何（返回新对象，不改入参） */
export function applyPlacementAdjust(
  placement: NailPlacement,
  adjust: PlacementAdjust,
): NailPlacement {
  const geometry = computePlacementGeometry(
    {
      cx: placement.baseCx,
      cy: placement.baseCy,
      length: placement.baseLength,
      width: placement.baseWidth,
      angle: placement.angle,
    },
    placement.aspect,
    adjust,
  );
  return {
    ...placement,
    adjust,
    cx: geometry.cx,
    cy: geometry.cy,
    length: geometry.length,
    width: geometry.width,
  };
}

/** 世界坐标点是否落在旋转椭圆内（canvas rotate(angle) 语义，逆旋转到局部域） */
function pointInRotatedEllipse(
  x: number,
  y: number,
  cx: number,
  cy: number,
  angle: number,
  radiusX: number,
  radiusY: number,
): boolean {
  if (!(radiusX > 0) || !(radiusY > 0)) return false;
  const dx = x - cx;
  const dy = y - cy;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  // 世界 → 局部：局部 +X 为甲面横轴，局部 −Y 为甲尖方向
  const lx = dx * cos + dy * sin;
  const ly = -dx * sin + dy * cos;
  return (lx * lx) / (radiusX * radiusX) + (ly * ly) / (radiusY * radiusY) <= 1;
}

/**
 * 贴合命中测试：从数组末尾向前找（顶层优先），返回命中的数组索引或 -1。
 * 命中域为贴合当前渲染几何的旋转椭圆（半轴 width/2, length/2）。
 */
export function placementHitTest(
  placements: readonly NailPlacement[],
  x: number,
  y: number,
): number {
  for (let i = placements.length - 1; i >= 0; i--) {
    const p = placements[i];
    if (
      pointInRotatedEllipse(x, y, p.cx, p.cy, p.angle, p.width / 2, p.length / 2)
    ) {
      return i;
    }
  }
  return -1;
}

/**
 * 甲面框命中测试：从数组末尾向前找（顶层优先），返回命中的数组索引或 -1。
 * 命中域为框的旋转椭圆（半轴 nw/2, nl/2）。
 */
export function frameHitTest(
  frames: readonly PlacementFrameInput[],
  x: number,
  y: number,
): number {
  for (let i = frames.length - 1; i >= 0; i--) {
    const f = frames[i];
    if (
      pointInRotatedEllipse(x, y, f.cx, f.cy, f.angle, f.nw / 2, f.nl / 2)
    ) {
      return i;
    }
  }
  return -1;
}

/** 导出重放的单个绘制参数（cx,cy,length,width 按 factor 等比缩放，angle 不变） */
export interface PlacementDraw {
  textureSrc: string;
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
}

/** 导出重放清单：按 factor 把贴合几何缩放到目标画布坐标系 */
export function placementDrawList(
  placements: readonly NailPlacement[],
  factor: number,
): PlacementDraw[] {
  return placements.map((p) => ({
    textureSrc: p.textureSrc,
    cx: p.cx * factor,
    cy: p.cy * factor,
    length: p.length * factor,
    width: p.width * factor,
    angle: p.angle,
  }));
}

/** 导出前的纹理装载分区：可导出与纹理加载失败两组。 */
export interface ExportTexturePartition {
  /** 纹理已就绪、可直接导出的贴合 */
  ok: NailPlacement[];
  /** 纹理加载失败、导出须跳过的贴合 */
  failed: NailPlacement[];
  /** 失败涉及的去重纹理 src */
  failedSources: string[];
}

/**
 * 按纹理装载状态把贴合分成可导出/失败两组（§5.8 导出失败治理）。
 * isLoaded 由调用方传入（如画布的已装载纹理缓存 has），保持纯函数可测。
 */
export function partitionExportTextures(
  placements: readonly NailPlacement[],
  isLoaded: (src: string) => boolean,
): ExportTexturePartition {
  const ok: NailPlacement[] = [];
  const failed: NailPlacement[] = [];
  const failedSourceSet = new Set<string>();
  for (const placement of placements) {
    if (isLoaded(placement.textureSrc)) {
      ok.push(placement);
    } else {
      failed.push(placement);
      failedSourceSet.add(placement.textureSrc);
    }
  }
  return { ok, failed, failedSources: [...failedSourceSet] };
}

/** 键盘微调步长（原图像素域）：方向键 2px，Shift + 方向键 8px。 */
export const NUDGE_STEP_PX = 2;
export const NUDGE_STEP_LARGE_PX = 8;

/** 把坐标钳制到原图范围内（拖动与键盘微调共用；空图原样返回 0 下界）。 */
export function clampToImageBounds(
  x: number,
  y: number,
  imageWidth: number,
  imageHeight: number,
): { x: number; y: number } {
  return {
    x: Math.min(Math.max(x, 0), Math.max(0, imageWidth)),
    y: Math.min(Math.max(y, 0), Math.max(0, imageHeight)),
  };
}

/** 纹理图缓存：同一 src 的并发/重复加载复用同一 Image（失败不缓存，可重试） */
const textureImageCache = new Map<string, Promise<HTMLImageElement>>();

export function loadTextureImage(src: string): Promise<HTMLImageElement> {
  const cached = textureImageCache.get(src);
  if (cached) return cached;
  const promise = new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => {
      textureImageCache.delete(src);
      reject(new Error(`纹理加载失败：${src}`));
    };
    img.src = src;
  });
  textureImageCache.set(src, promise);
  return promise;
}

/** 纹理长宽比 = naturalHeight / naturalWidth；加载失败或尺寸非法回退 1 */
export async function loadTextureAspect(src: string): Promise<number> {
  let img: HTMLImageElement;
  try {
    img = await loadTextureImage(src);
  } catch {
    return 1;
  }
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return 1;
  return h / w;
}
