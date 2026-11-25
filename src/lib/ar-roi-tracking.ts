import type { NailLandmark } from "./nail-geometry.ts";

/** 全帧归一化手部包围盒。 */
export interface RoiBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 像素裁剪窗（源视频坐标）。 */
export interface RoiCrop {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/** 由关键点求归一化包围盒，外扩 margin 并夹取到 [0,1]。 */
export function bboxFromLandmarks(
  lm: readonly NailLandmark[],
  margin = 0.08,
): RoiBox | null {
  if (!lm.length) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of lm) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  if (!Number.isFinite(minX) || maxX <= minX || maxY <= minY) return null;
  const x = Math.max(0, minX - margin);
  const y = Math.max(0, minY - margin);
  const w = Math.min(1, maxX + margin) - x;
  const h = Math.min(1, maxY + margin) - y;
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}

/** 归一化包围盒 → 像素裁剪窗，外扩 expand 倍并夹取到源尺寸。 */
export function expandRoi(box: RoiBox, vw: number, vh: number, expand = 1.35): RoiCrop | null {
  if (vw <= 0 || vh <= 0) return null;
  const cx = (box.x + box.w / 2) * vw;
  const cy = (box.y + box.h / 2) * vh;
  const sw = Math.min(vw, box.w * vw * expand);
  const sh = Math.min(vh, box.h * vh * expand);
  if (sw < 8 || sh < 8) return null;
  const sx = Math.max(0, Math.min(vw - sw, cx - sw / 2));
  const sy = Math.max(0, Math.min(vh - sh, cy - sh / 2));
  return { sx, sy, sw, sh };
}

/** 裁剪窗内归一化关键点 → 全帧归一化关键点（z 缺省补 0，保持 required 语义）。 */
export function remapLandmarks(
  lm: readonly NailLandmark[],
  crop: RoiCrop,
  vw: number,
  vh: number,
): { x: number; y: number; z: number }[] {
  return lm.map(p => ({
    x: (crop.sx + p.x * crop.sw) / vw,
    y: (crop.sy + p.y * crop.sh) / vh,
    z: p.z ?? 0,
  }));
}

/** 冷启动 bootstrap：掌检测从未回包时，用粗分割甲实例并集外扩估计手部包围盒。 */
export function segBootstrapBox(
  instances: readonly { cx: number; cy: number; w: number; h: number; score: number }[],
  minScore = 0.3,
  margin = 0.12,
): RoiBox | null {
  const hit = instances.filter(i => i.score >= minScore);
  if (!hit.length) return null;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const i of hit) {
    minX = Math.min(minX, i.cx - i.w / 2);
    minY = Math.min(minY, i.cy - i.h / 2);
    maxX = Math.max(maxX, i.cx + i.w / 2);
    maxY = Math.max(maxY, i.cy + i.h / 2);
  }
  const x = Math.max(0, minX - margin);
  const y = Math.max(0, minY - margin);
  const w = Math.min(1, maxX + margin) - x;
  const h = Math.min(1, maxY + margin) - y;
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}

/** 漂移守卫：恢复关键点质心须落在上一帧包围盒外扩域内，且跨度合理。 */
export function roiSanity(remapped: readonly NailLandmark[], prev: RoiBox, pad = 0.25): boolean {
  if (!remapped.length) return false;
  let cx = 0, cy = 0, minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of remapped) {
    cx += p.x; cy += p.y;
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  cx /= remapped.length; cy /= remapped.length;
  const inBox = cx >= prev.x - pad && cx <= prev.x + prev.w + pad
    && cy >= prev.y - pad && cy <= prev.y + prev.h + pad;
  const spread = (maxX - minX) + (maxY - minY);
  return inBox && spread > 0.05 && spread < 1.6;
}