import type { NailCoarseInstance } from "./nail-texture-recognition/stage-a-coarse.ts";

/** 逐指分割命中滞回状态：hit 为当前是否计入融合，streak 为剩余保持帧数。 */
export interface SegFingerHit {
  hit: boolean;
  streak: number;
}

export interface TipPoint {
  x: number;
  y: number;
}

/** 实例中心落在指尖半径内，或指尖落在实例外扩盒内，视为该指命中。 */
export function instanceMatchesTip(
  instance: NailCoarseInstance,
  tip: TipPoint,
  radius: number,
): boolean {
  const dx = instance.cx - tip.x;
  const dy = instance.cy - tip.y;
  if (dx * dx + dy * dy <= radius * radius) return true;
  const halfW = instance.w / 2 + radius;
  const halfH = instance.h / 2 + radius;
  return Math.abs(dx) <= halfW && Math.abs(dy) <= halfH;
}

/** 冷启动兜底槽位分配：按水平位置左→右排序映射到 5 槽（近似指序，供无关键点时兜底贴合）。 */
export function assignSegSlots<T extends { cx: number; score: number }>(
  instances: readonly T[],
  minScore = 0.35,
  slots = 5,
): { slot: number; instance: T }[] {
  return instances
    .filter(i => i.score >= minScore)
    .slice()
    .sort((a, b) => a.cx - b.cx)
    .slice(0, slots)
    .map((instance, slot) => ({ slot, instance }));
}

/**
 * 关键帧调度：距上次关键帧 ≥ intervalMs 且当前无在途请求时才调度，
 * 保证 2–4fps 粗分割不堆积、不抢占主跟踪帧预算。
 */
export function shouldScheduleKeyframe(
  nowMs: number,
  lastKeyframeMs: number,
  intervalMs: number,
  busy: boolean,
): boolean {
  return !busy && nowMs - lastKeyframeMs >= intervalMs;
}

/**
 * 实例→手指关联 + 滞回：命中即置 hit 并重置 streak=holdFrames；未命中 streak 递减，
 * streak>0 期间保持 hit，避免稀疏关键帧证据造成逐帧闪烁。
 */
export function updateSegHits(
  prev: Readonly<Record<number, SegFingerHit>>,
  tips: Readonly<Record<number, TipPoint>>,
  instances: readonly NailCoarseInstance[],
  radius: number,
  holdFrames: number,
): Record<number, SegFingerHit> {
  const next: Record<number, SegFingerHit> = {};
  for (const key of Object.keys(tips)) {
    const finger = Number(key);
    const tip = tips[finger];
    const matched = instances.some(inst => instanceMatchesTip(inst, tip, radius));
    const prevStreak = prev[finger]?.streak ?? 0;
    const streak = matched ? holdFrames : Math.max(0, prevStreak - 1);
    next[finger] = { hit: matched || streak > 0, streak };
  }
  return next;
}