/**
 * 编辑器笔画纯逻辑（2026-09-05 评审 #8 修复配套模块）。
 *
 * 设计：显示尺寸与输出尺寸分离——预览画布最长边 400/600，笔画以预览坐标
 * 记录；导出时按原图尺寸离屏重放（坐标与笔刷半径等比放大），4096×4096
 * 上传图不再被压成 400×400（评审复现：像素仅保留约 0.95%）。
 * 撤销/重置共用「重放 strokes」一条路径：重置 = 空 strokes = 原图基线，
 * 不再依赖历史快照队列（评审复现：20 份快照淘汰后重置回到第 6 笔）。
 */

export const PREVIEW_MAX_W = 400;
export const PREVIEW_MAX_H = 600;
/** 实时绘制与重放共用的插值步长（预览坐标系，像素） */
export const STROKE_STEP = 5;

export interface StrokePoint {
  x: number;
  y: number;
}

/** 一条完整笔画：落笔到抬笔的全部采样点（预览坐标）+ 笔刷颜色与半径 */
export interface Stroke {
  color: string;
  size: number;
  points: StrokePoint[];
}

/** 预览缩放：显示不超过 400×600 且从不放大 */
export function previewScale(width: number, height: number): number {
  if (width <= 0 || height <= 0) return 1;
  return Math.min(PREVIEW_MAX_W / width, PREVIEW_MAX_H / height, 1);
}

/** 把笔画整体缩放到目标坐标系（点坐标与笔刷半径等比） */
export function scaleStroke(stroke: Stroke, s: number): Stroke {
  return {
    color: stroke.color,
    size: stroke.size * s,
    points: stroke.points.map((p) => ({ x: p.x * s, y: p.y * s })),
  };
}

/**
 * 两点间插值点列（含两端点）：steps = max(floor(dist / step), 1)。
 * 与组件内实时绘制的分段插值语义逐点一致。
 */
export function interpolateStrokePoints(a: StrokePoint, b: StrokePoint, step: number): StrokePoint[] {
  const dist = Math.hypot(b.x - a.x, b.y - a.y);
  const steps = Math.max(Math.floor(dist / step), 1);
  const pts: StrokePoint[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    pts.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
  }
  return pts;
}

/**
 * 重放一条笔画生成的落点序列：相邻采样点逐段插值，段间端点重复——
 * 与实时绘制（每次 move 事件画上一位置到当前位置的插值段）的点集语义一致。
 * scale 用于把预览坐标映射到输出坐标系；step 随坐标系等比传入。
 */
export function strokeDots(stroke: Stroke, scale: number, step: number): StrokePoint[] {
  const scaled = scaleStroke(stroke, scale);
  if (scaled.points.length === 0) return [];
  const dots: StrokePoint[] = [scaled.points[0]];
  for (let i = 1; i < scaled.points.length; i++) {
    dots.push(...interpolateStrokePoints(scaled.points[i - 1], scaled.points[i], step));
  }
  return dots;
}
