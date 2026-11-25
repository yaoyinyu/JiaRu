const PALM_ANCHORS = [0, 5, 9, 13, 17];

interface Point {
  x: number;
  y: number;
}

/** 平移一致时，把手掌位移与指节局部运动分开。输入是画布像素。 */
export function getCoherentPalmTranslation(previous: readonly Point[], current: readonly Point[]) {
  const movements = PALM_ANCHORS.map(index => ({
    x: current[index].x - previous[index].x,
    y: current[index].y - previous[index].y,
  }));
  const median = (axis: "x" | "y") => movements.map(point => point[axis]).sort((a, b) => a - b)[2];
  const x = median("x");
  const y = median("y");
  const span = Math.hypot(current[5].x - current[17].x, current[5].y - current[17].y);
  const distance = Math.hypot(x, y);
  if (!(span > 0 && distance >= span * 0.055 && distance <= span * 0.65)) return;
  const coherent = movements.filter(point => Math.hypot(point.x - x, point.y - y) <= span * 0.06);
  if (coherent.length >= 4) return { x, y };
}
