import { normalizeHalfTurnAngle } from "./nail-texture-recognition/mask-orientation.ts";

interface NailAxis {
  cx: number; cy: number; length: number; width: number; angle: number;
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
