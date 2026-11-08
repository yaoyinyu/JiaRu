import type { NailGeometry } from "./nail-geometry.ts";

export type FitHandle = "root" | "tip" | "width";
export interface FitValues {
  lengthScale: number; widthScale: number; rootOffset: number;
  sideOffset?: number; rotationOffset?: number;
}

/** 指针坐标先撤销显示镜像与CSS缩放，再进入画布几何坐标。 */
export function mirroredCanvasPoint(clientX: number, clientY: number,
  rect: { left: number; top: number; width: number; height: number }, width: number, height: number) {
  return { x: (1 - (clientX - rect.left) / rect.width) * width,
    y: (clientY - rect.top) / rect.height * height };
}

export function fitHandlePoints(g: NailGeometry) {
  const root = { x: g.cx - Math.sin(g.angle) * g.length / 2,
    y: g.cy + Math.cos(g.angle) * g.length / 2 };
  const cross = g.transverseAngle ?? g.angle;
  return { root, tip: { x: g.cx + Math.sin(g.angle) * g.length / 2,
    y: g.cy - Math.cos(g.angle) * g.length / 2 },
    width: { x: g.cx + Math.cos(cross) * g.width / 2,
      y: g.cy + Math.sin(cross) * g.width / 2 } };
}

/** 撤销双轴剪切；拖动起点固定，避免每帧累计偏移和透视串轴。 */
export function dragNailFit(handle: FitHandle, dx: number, dy: number,
  raw: NailGeometry, rendered: NailGeometry, fit: FitValues): FitValues {
  const cross = rendered.transverseAngle ?? rendered.angle;
  const a = Math.cos(cross), b = Math.sin(cross);
  const c = -Math.sin(rendered.angle), d = Math.cos(rendered.angle);
  const determinant = a * d - b * c;
  if (![dx, dy, determinant, raw.length, raw.width, rendered.length].every(Number.isFinite)
    || Math.abs(determinant) < .2 || raw.length <= 0 || raw.width <= 0 || rendered.length <= 0) return { ...fit };
  const across = (d * dx - c * dy) / determinant;
  const rootward = (-b * dx + a * dy) / determinant;
  const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
  if (handle === "tip") return { ...fit,
    lengthScale: clamp(fit.lengthScale * (1 - rootward / rendered.length), .75, 1.4) };
  if (handle === "width") return { ...fit,
    widthScale: clamp(fit.widthScale + 2 * across / raw.width, .7, 1.45) };
  // 根部位移的滑杆坐标沿未旋转手指轴定义，保持与adjustNailGeometry一致。
  const rawCross = raw.transverseAngle ?? raw.angle;
  const ra = Math.cos(rawCross), rb = Math.sin(rawCross), rc = -Math.sin(raw.angle), rd = Math.cos(raw.angle);
  const det = ra * rd - rb * rc;
  if (Math.abs(det) < .2) return { ...fit };
  return { ...fit,
    sideOffset: clamp((fit.sideOffset ?? 0) + (rd * dx - rc * dy) / det / raw.width, -.4, .4),
    rootOffset: clamp(fit.rootOffset + (-rb * dx + ra * dy) / det / raw.length, -.2, .2) };
}
