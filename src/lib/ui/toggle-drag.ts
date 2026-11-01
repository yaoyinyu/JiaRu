/**
 * 新拟态拨动开关的拖拽几何（node 可测纯函数）。
 *
 * 交互模型（与 design/consumer-v1 开关动效同口径）：
 * - 滑块拖拽位置 = 起点基准位（选中=travel，未选=0）+ 指针位移，钳制在 [0, travel]；
 * - 磁吸：越过中点后滑块向吸引极倾斜 pull 像素（松手由弹簧缓动完成吸附）；
 * - 松手：越过中点则翻转状态，否则回弹到原状态位。
 */

export const NEU_TOGGLE_TRACK_WIDTH = 52;
export const NEU_TOGGLE_KNOB_SIZE = 24;
export const NEU_TOGGLE_TRACK_PAD = 3;
/** 滑块行程：52 轨道 - 24 滑块 - 两侧 3px 内边距 */
export const NEU_TOGGLE_TRAVEL = NEU_TOGGLE_TRACK_WIDTH - NEU_TOGGLE_KNOB_SIZE - NEU_TOGGLE_TRACK_PAD * 2;
/** 磁吸倾斜幅度（px）：越过中点后向吸引极的额外偏置 */
export const NEU_TOGGLE_MAGNET_PULL_PX = 5;

export interface DragFrameInput {
  /** 拖拽起点时滑块所在状态位：选中 = travel，未选 = 0 */
  baseX: number;
  /** 指针按下时的 clientX */
  startX: number;
  /** 当前指针 clientX */
  x: number;
  /** 行程（默认 NEU_TOGGLE_TRAVEL） */
  travel?: number;
  /** 判定「发生拖拽」的位移阈值（默认 4px；低于阈值视为点击） */
  dragThreshold?: number;
}

export interface DragFrameOutcome {
  /** 滑块拖拽位置（px，不含磁吸偏置），钳制在 [0, travel] */
  x: number;
  /** 磁吸偏置（px）：越过中点向吸引极倾斜，未越过为 0；始终保证 x+pull 落在 [0, travel] */
  pull: number;
  /** 松手后应到达的状态：越过中点则翻转，中点恰好持平保持原状态 */
  shouldCheck: boolean;
  /** 位移是否超过阈值（低于阈值按点击处理，不进入拖拽渲染） */
  moved: boolean;
}

export function resolveDragFrame({
  baseX,
  startX,
  x,
  travel = NEU_TOGGLE_TRAVEL,
  dragThreshold = 4,
}: DragFrameInput): DragFrameOutcome {
  const dx = x - startX;
  const raw = Math.min(travel, Math.max(0, baseX + dx));
  const half = travel / 2;
  let pull = 0;
  if (raw > half) {
    pull = Math.min(NEU_TOGGLE_MAGNET_PULL_PX, travel - raw);
  } else if (raw < half) {
    pull = -Math.min(NEU_TOGGLE_MAGNET_PULL_PX, raw);
  }
  const moved = Math.abs(dx) > dragThreshold;
  return { x: raw, pull, shouldCheck: raw > half, moved };
}
