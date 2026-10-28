import type { NailTextureCandidate } from "./types.ts";

/**
 * 候选与上游抠图实例的一一匹配。
 *
 * 上游实例数可能少于本地候选数（同图 4 vs 5 是已记录现象），索引顺序也不保证
 * 与本地候选一致，因此**只能**按外接框 IoU 贪心匹配：
 * - 每个实例最多被一个候选使用，反之亦然；
 * - 不做数量补齐、不按分数截断、不按索引硬配；
 * - 未命中的候选保留本地 mask，未命中的实例直接丢弃。
 */

export type Box = [number, number, number, number];

export interface MatchCandidate {
  id: string;
  box: Box;
}

export interface MatchInstance {
  index: number;
  box: Box;
}

export interface MaskMatch {
  candidateId: string;
  instanceIndex: number;
  iou: number;
}

export interface MaskMatchResult {
  matches: MaskMatch[];
  /** 未匹配到实例的候选（保留本地结果） */
  unmatchedCandidateIds: string[];
  /** 未被任何候选使用的实例（丢弃，不追加候选） */
  unmatchedInstanceIndexes: number[];
}

/** 旋转矩形（中心 + 长轴/短轴 + 角度）的轴对齐外接框。 */
export function rotatedRectBounds(
  cx: number,
  cy: number,
  length: number,
  width: number,
  angle: number
): Box {
  const halfLength = Math.abs(length) / 2;
  const halfWidth = Math.abs(width) / 2;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  // 四条角点旋转后取极值：外接框半宽/半高 = |L/2·cos| + |W/2·sin| 等
  const extentX = Math.abs(halfLength * cos) + Math.abs(halfWidth * sin);
  const extentY = Math.abs(halfLength * sin) + Math.abs(halfWidth * cos);
  return [cx - extentX, cy - extentY, cx + extentX, cy + extentY];
}

export function candidateBounds(candidate: NailTextureCandidate): Box {
  return rotatedRectBounds(
    candidate.cx,
    candidate.cy,
    candidate.length,
    candidate.width,
    candidate.angle
  );
}

function boxArea(box: Box): number {
  return Math.max(0, box[2] - box[0]) * Math.max(0, box[3] - box[1]);
}

export function boxIou(a: Box, b: Box): number {
  const left = Math.max(a[0], b[0]);
  const top = Math.max(a[1], b[1]);
  const right = Math.min(a[2], b[2]);
  const bottom = Math.min(a[3], b[3]);
  const intersection = Math.max(0, right - left) * Math.max(0, bottom - top);
  if (intersection <= 0) return 0;
  const union = boxArea(a) + boxArea(b) - intersection;
  return union > 0 ? intersection / union : 0;
}

/**
 * 贪心一一匹配：候选按 IoU 从高到低占用实例。
 * 同分时按 candidateId、instanceIndex 字典序决定，保证同一输入顺序无关且稳定。
 */
export function matchMasksByIou(
  candidates: MatchCandidate[],
  instances: MatchInstance[],
  minIou = 0.3
): MaskMatchResult {
  const pairs: MaskMatch[] = [];
  for (const candidate of candidates) {
    for (const instance of instances) {
      const iou = boxIou(candidate.box, instance.box);
      if (iou > 0 && iou >= minIou) {
        pairs.push({ candidateId: candidate.id, instanceIndex: instance.index, iou });
      }
    }
  }

  pairs.sort((a, b) => {
    if (b.iou !== a.iou) return b.iou - a.iou;
    if (a.candidateId !== b.candidateId) return a.candidateId < b.candidateId ? -1 : 1;
    return a.instanceIndex - b.instanceIndex;
  });

  const usedCandidates = new Set<string>();
  const usedInstances = new Set<number>();
  const matches: MaskMatch[] = [];
  for (const pair of pairs) {
    if (usedCandidates.has(pair.candidateId) || usedInstances.has(pair.instanceIndex)) continue;
    usedCandidates.add(pair.candidateId);
    usedInstances.add(pair.instanceIndex);
    matches.push(pair);
  }

  return {
    matches,
    unmatchedCandidateIds: candidates
      .filter((candidate) => !usedCandidates.has(candidate.id))
      .map((candidate) => candidate.id),
    unmatchedInstanceIndexes: instances
      .filter((instance) => !usedInstances.has(instance.index))
      .map((instance) => instance.index),
  };
}

export interface MatteMatch extends MaskMatch {
  /** center：实例中心落在候选外接框（含少量外扩）内；iou：仅靠重叠度命中 */
  reason: "center" | "iou";
}

export interface MatteMatchOptions {
  /** 重叠度兜底下限；低于此值且中心不在框内则不匹配 */
  minIou?: number;
  /** 中心点判定的外扩比例（相对候选框宽高） */
  centerPadding?: number;
}

export interface MatteMatchResult extends MaskMatchResult {
  matches: MatteMatch[];
}

/**
 * 实例中心是否落在候选外接框内（可外扩）。
 *
 * 本地候选外接框来自 MediaPipe 几何推导，通常比上游甲面框更松、位置略偏，
 * 因此中心归属比纯 IoU 更稳健；外扩只用于判定归属，不改变任何几何输出。
 */
export function instanceCenterInsideCandidate(
  instanceBox: Box,
  candidateBox: Box,
  padding = 0.15
): boolean {
  const cx = (instanceBox[0] + instanceBox[2]) / 2;
  const cy = (instanceBox[1] + instanceBox[3]) / 2;
  const padX = Math.max(0, candidateBox[2] - candidateBox[0]) * padding;
  const padY = Math.max(0, candidateBox[3] - candidateBox[1]) * padding;
  return (
    cx >= candidateBox[0] - padX &&
    cx <= candidateBox[2] + padX &&
    cy >= candidateBox[1] - padY &&
    cy <= candidateBox[3] + padY
  );
}

/**
 * 精细抠图专用一一匹配：中心归属优先，IoU 兜底。
 *
 * 上游 `visual_prompt` 在当前权重上恒定返回空（2026-10-28 实测），实际调用改为
 * 文本 `matting`，实例与候选之间只剩几何关系。排序键为「中心命中优先 → IoU 高优先」，
 * 同分按 candidateId、instanceIndex 字典序，保证输入顺序无关且结果稳定。
 */
export function matchMasksToCandidates(
  candidates: MatchCandidate[],
  instances: MatchInstance[],
  options: MatteMatchOptions = {}
): MatteMatchResult {
  const minIou = options.minIou ?? 0.15;
  const padding = options.centerPadding ?? 0.15;

  const pairs: Array<MatteMatch & { rank: number }> = [];
  for (const candidate of candidates) {
    for (const instance of instances) {
      const iou = boxIou(candidate.box, instance.box);
      const centered = instanceCenterInsideCandidate(instance.box, candidate.box, padding);
      if (!centered && iou < minIou) continue;
      const reason: MatteMatch["reason"] = centered ? "center" : "iou";
      // 中心命中整体优先于纯 IoU：加 1 保证任何中心命中都排在所有纯 IoU 之前
      pairs.push({
        candidateId: candidate.id,
        instanceIndex: instance.index,
        iou,
        reason,
        rank: centered ? 1 + iou : iou,
      });
    }
  }

  pairs.sort((a, b) => {
    if (b.rank !== a.rank) return b.rank - a.rank;
    if (b.iou !== a.iou) return b.iou - a.iou;
    if (a.candidateId !== b.candidateId) return a.candidateId < b.candidateId ? -1 : 1;
    return a.instanceIndex - b.instanceIndex;
  });

  const usedCandidates = new Set<string>();
  const usedInstances = new Set<number>();
  const matches: MatteMatch[] = [];
  for (const pair of pairs) {
    if (usedCandidates.has(pair.candidateId) || usedInstances.has(pair.instanceIndex)) continue;
    usedCandidates.add(pair.candidateId);
    usedInstances.add(pair.instanceIndex);
    matches.push({
      candidateId: pair.candidateId,
      instanceIndex: pair.instanceIndex,
      iou: pair.iou,
      reason: pair.reason,
    });
  }

  return {
    matches,
    unmatchedCandidateIds: candidates
      .filter((candidate) => !usedCandidates.has(candidate.id))
      .map((candidate) => candidate.id),
    unmatchedInstanceIndexes: instances
      .filter((instance) => !usedInstances.has(instance.index))
      .map((instance) => instance.index),
  };
}
