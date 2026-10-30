/**
 * 多纹理提取自动流程的纯逻辑：自动指位分配。
 * 机器先给出最优推断，用户仍可在选择器中手动修正（兜底入口保留）。
 */

export const AUTO_FINGER_GUESS_WARNING = "auto_finger_guess";

export interface AutoFingerAssignableRegion {
  id: string;
  cx: number;
  assignedFinger: number | null;
  warnings?: string[];
}

export interface AutoFingerAssignment {
  id: string;
  finger: number;
  guessed: boolean;
}

const FINGER_COUNT = 5;

/**
 * 为未分配指位的区域补充自动推断：
 * 1) 识别阶段已带 assignedFinger 的区域保持不变；
 * 2) 其余区域按画面 x 序（从左到右）依次填入空闲指位（0=拇指 … 4=小指），
 *    并在 warnings 中加入 auto_finger_guess，提示用户可修正；
 * 3) 待分配区域多于空闲指位时，多出的保持 null，等待用户手动分配。
 */
export function autoAssignNailRegionFingers<T extends AutoFingerAssignableRegion>(
  regions: readonly T[]
): { regions: T[]; assignments: AutoFingerAssignment[]; guessedCount: number } {
  const taken = new Set<number>();
  for (const region of regions) {
    if (region.assignedFinger !== null) taken.add(region.assignedFinger);
  }
  const freeFingers: number[] = [];
  for (let finger = 0; finger < FINGER_COUNT; finger += 1) {
    if (!taken.has(finger)) freeFingers.push(finger);
  }

  const pending = regions
    .filter((region) => region.assignedFinger === null)
    .sort((a, b) => a.cx - b.cx);

  const assignments: AutoFingerAssignment[] = [];
  const fingerById = new Map<string, number>();
  pending.forEach((region, index) => {
    const finger = freeFingers[index];
    if (finger === undefined) return;
    fingerById.set(region.id, finger);
    assignments.push({ id: region.id, finger, guessed: true });
  });

  const nextRegions = regions.map((region) => {
    const finger = fingerById.get(region.id);
    if (finger === undefined) return region;
    return {
      ...region,
      assignedFinger: finger,
      warnings: [...(region.warnings ?? []), AUTO_FINGER_GUESS_WARNING],
    };
  });
  return { regions: nextRegions, assignments, guessedCount: assignments.length };
}
