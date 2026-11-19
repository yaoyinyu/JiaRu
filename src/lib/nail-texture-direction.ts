import { normalizeHalfTurnAngle } from "./nail-texture-recognition/mask-orientation.ts";

interface NailAxis {
  cx: number; cy: number; length: number; width: number; angle: number;
}

/** 手部几何候选 id 形如 `mediapipe-hand-0-finger-3`，尾码即指位（0 拇—4 小指）。 */
const REFERENCE_FINGER_PATTERN = /finger-(\d)(?!\d)/;

/** 从手部几何候选 id 解析指位；无法解析时返回 null。 */
export function fingerIndexFromReferenceId(id: string | undefined): number | null {
  if (!id) return null;
  const match = REFERENCE_FINGER_PATTERN.exec(id);
  if (!match) return null;
  const finger = Number(match[1]);
  return Number.isInteger(finger) && finger >= 0 && finger <= 4 ? finger : null;
}

/**
 * 按指位直接取手指方向：同一根手指的关键点方向就是该甲面的甲尖方向。
 *
 * 与几何配对（`matchNailDirectionReferences`）相比，这条路径不受候选框重叠、
 * 角度门限和双向唯一性限制，只要手部关键点可见、指位已知即可定向。
 * 仍保留一道宽松的一致性门：参考甲面与待定向甲面的中心距离超过两者尺寸的
 * 1.2 倍时视为指位不一致，返回 null 交由几何配对或轮廓判据处理。
 */
export function matchNailDirectionsByFinger(
  nails: readonly (NailAxis & { finger: number | null })[],
  references: readonly (NailAxis & { id?: string })[],
): Array<number | null> {
  const byFinger = new Map<number, Array<NailAxis>>();
  for (const reference of references) {
    const finger = fingerIndexFromReferenceId(reference.id);
    if (finger == null) continue;
    if (![reference.cx, reference.cy, reference.length, reference.width, reference.angle].every(Number.isFinite)) continue;
    if (reference.length <= 0 || reference.width <= 0) continue;
    const bucket = byFinger.get(finger);
    if (bucket) bucket.push(reference);
    else byFinger.set(finger, [reference]);
  }

  return nails.map((nail) => {
    if (nail.finger == null) return null;
    const bucket = byFinger.get(nail.finger);
    if (!bucket || bucket.length === 0) return null;
    let best: NailAxis | null = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const reference of bucket) {
      if (![nail.cx, nail.cy, nail.length, nail.width].every(Number.isFinite)) continue;
      const dx = nail.cx - reference.cx;
      const dy = nail.cy - reference.cy;
      const across = Math.abs(dx * Math.cos(reference.angle) + dy * Math.sin(reference.angle));
      const along = Math.abs(-dx * Math.sin(reference.angle) + dy * Math.cos(reference.angle));
      const halfWidth = Math.max(nail.width, reference.width) * 0.6;
      const halfLength = Math.max(nail.length, reference.length) * 0.6;
      const distance = (across / halfWidth) ** 2 + (along / halfLength) ** 2;
      if (distance > 4) continue;
      if (distance < bestDistance) { bestDistance = distance; best = reference; }
    }
    return best ? best.angle : null;
  });
}

/** 双向唯一几何配对，仅补充甲尖方向；保留模型轮廓和手工指位。 */
export function matchNailDirectionReferences(
  nails: readonly NailAxis[], references: readonly NailAxis[],
): Array<number | null> {
  const costs = nails.map(nail => references.map(reference => {
    if (![nail.cx, nail.cy, nail.length, nail.width, nail.angle,
      reference.cx, reference.cy, reference.length, reference.width, reference.angle].every(Number.isFinite)
      || nail.length <= 0 || nail.width <= 0 || reference.length <= 0 || reference.width <= 0) return Infinity;
    if (Math.abs(normalizeHalfTurnAngle(nail.angle - reference.angle)) > Math.PI * 25 / 180) return Infinity;
    const dx = nail.cx - reference.cx, dy = nail.cy - reference.cy;
    const across = Math.abs(dx * Math.cos(reference.angle) + dy * Math.sin(reference.angle));
    const along = Math.abs(-dx * Math.sin(reference.angle) + dy * Math.cos(reference.angle));
    const width = Math.max(nail.width, reference.width), length = Math.max(nail.length, reference.length);
    if (across > width * .65 || along > length * .8) return Infinity;
    return (across / width) ** 2 + (along / length) ** 2;
  }));
  const uniqueBest = (values: number[]) => {
    const ranked = values.map((cost, index) => ({ cost, index })).sort((a, b) => a.cost - b.cost);
    if (!Number.isFinite(ranked[0]?.cost) || (ranked[1]?.cost ?? Infinity) - ranked[0].cost < .12) return null;
    return ranked[0].index;
  };
  return costs.map((row, i) => {
    const j = uniqueBest(row);
    return j != null && uniqueBest(costs.map(other => other[j])) === i ? references[j].angle : null;
  });
}
