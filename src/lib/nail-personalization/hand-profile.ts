import type { NailTextureCandidate } from "../nail-texture-recognition/types.ts";
import type {
  FingerIndex,
  HandProfile,
  HandShapeClass,
  HandShapeSource,
  NailBedMetrics,
} from "./types.ts";

/** 手型分类阈值（预注册假设，标定要求见设计文档 §8）。 */
export const HAND_SHAPE_THRESHOLDS = {
  wideShortMaxAspect: 1.25,
  wideShortMinPalmAspect: 0.72,
  narrowLongMinAspect: 1.55,
  narrowLongMaxPalmAspect: 0.62,
  slimTaperedMinThumbRatio: 0.78,
  slimTaperedMinAspect: 1.4,
} as const;

/** completeness 权重：base + mask + finger = 1。 */
export const COMPLETENESS_WEIGHTS = {
  base: 0.6,
  mask: 0.25,
  finger: 0.15,
} as const;

/** 重复甲面判据。 */
export const DUPLICATE_CENTER_RATIO = 0.6;
export const DUPLICATE_ANGLE_TOLERANCE_RAD = (25 * Math.PI) / 180;

/** 手轴估计所需的最小有效候选数。 */
export const MIN_VALID_CANDIDATES_FOR_AXIS = 3;

/** 异常几何剔除区间。 */
export const ASPECT_RATIO_RANGE = [0.4, 4.0] as const;

const DEFAULT_EXPECTED_CANDIDATES = 5;

function median(values: readonly number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function filterValid(candidates: readonly NailTextureCandidate[]): NailTextureCandidate[] {
  return candidates.filter((candidate) => {
    if (!Number.isFinite(candidate.length) || !Number.isFinite(candidate.width)) return false;
    if (candidate.length <= 0 || candidate.width <= 0) return false;
    if (!Number.isFinite(candidate.cx) || !Number.isFinite(candidate.cy)) return false;
    const aspectRatio = candidate.length / candidate.width;
    return aspectRatio >= ASPECT_RATIO_RANGE[0] && aspectRatio <= ASPECT_RATIO_RANGE[1];
  });
}

/** 重复甲面：中心距 < 较小半长轴 × 0.6 且长轴夹角 < 25°，保留 score 较高者。 */
function dedupe(candidates: readonly NailTextureCandidate[]): {
  kept: NailTextureCandidate[];
  duplicates: number;
} {
  const sorted = [...candidates].sort((left, right) => right.score - left.score);
  const kept: NailTextureCandidate[] = [];
  let duplicates = 0;
  for (const candidate of sorted) {
    const collision = kept.some((existing) => {
      const dx = existing.cx - candidate.cx;
      const dy = existing.cy - candidate.cy;
      const distance = Math.hypot(dx, dy);
      const threshold = Math.min(existing.length, candidate.length) * 0.5 * DUPLICATE_CENTER_RATIO;
      if (distance >= threshold) return false;
      let delta = Math.abs(existing.angle - candidate.angle);
      while (delta > Math.PI) delta = Math.abs(delta - Math.PI * 2);
      if (delta > Math.PI / 2) delta = Math.abs(delta - Math.PI);
      return delta < DUPLICATE_ANGLE_TOLERANCE_RAD;
    });
    if (collision) {
      duplicates += 1;
      continue;
    }
    kept.push(candidate);
  }
  return { kept, duplicates };
}

/**
 * 手轴估计：指甲长轴无方向性，按倍角求轴向均值（mod π）。
 * 有效候选 < 3 或 angle 缺失时返回 null，调用方据此跳过旋转归一化。
 */
function estimateAxisAngle(candidates: readonly NailTextureCandidate[]): number | null {
  const angles = candidates
    .map((candidate) => candidate.angle)
    .filter((angle) => Number.isFinite(angle));
  if (angles.length < MIN_VALID_CANDIDATES_FOR_AXIS) return null;
  let sinSum = 0;
  let cosSum = 0;
  for (const angle of angles) {
    sinSum += Math.sin(angle * 2);
    cosSum += Math.cos(angle * 2);
  }
  if (sinSum === 0 && cosSum === 0) return null;
  return Math.atan2(sinSum, cosSum) / 2;
}

export function analyzeHandProfile(
  candidates: readonly NailTextureCandidate[],
  options?: { expectedCandidates?: number }
): HandProfile {
  const expectedCandidates = Math.max(1, options?.expectedCandidates ?? DEFAULT_EXPECTED_CANDIDATES);
  const warnings: string[] = [];

  if (candidates.length === 0) {
    return {
      shape: "balanced",
      shapeSource: "insufficient-evidence",
      palmAspect: null,
      thumbRatio: null,
      nailBeds: [],
      medianNailAspect: 0,
      completeness: 0,
      duplicateCandidates: 0,
      warnings: ["hand_profile_no_valid_candidates"],
    };
  }

  const filtered = filterValid(candidates);
  if (filtered.length < candidates.length) {
    warnings.push("hand_profile_invalid_candidates_dropped");
  }
  const { kept, duplicates } = dedupe(filtered);
  if (duplicates > 0) warnings.push("hand_profile_duplicate_candidates");

  if (kept.length === 0) {
    return {
      shape: "balanced",
      shapeSource: "insufficient-evidence",
      palmAspect: null,
      thumbRatio: null,
      nailBeds: [],
      medianNailAspect: 0,
      completeness: 0,
      duplicateCandidates: duplicates,
      warnings: [...warnings, "hand_profile_no_valid_candidates"],
    };
  }

  const axisAngle = estimateAxisAngle(kept);
  if (axisAngle === null) warnings.push("hand_profile_axis_unknown");

  const cos = axisAngle === null ? 1 : Math.cos(-axisAngle);
  const sin = axisAngle === null ? 0 : Math.sin(-axisAngle);
  const points = kept.map((candidate) => {
    const dx = candidate.cx;
    const dy = candidate.cy;
    return { candidate, x: dx * cos - dy * sin, y: dx * sin + dy * cos };
  });

  const widths = kept.map((candidate) => candidate.width);
  const medianWidth = median(widths);
  const medianLength = median(kept.map((candidate) => candidate.length));

  const nailBeds: NailBedMetrics[] = kept.map((candidate) => ({
    finger: (candidate.suggestedFinger ?? null) as FingerIndex | null,
    lengthPx: candidate.length,
    widthPx: candidate.width,
    aspectRatio: candidate.length / candidate.width,
    relativeWidth: medianWidth > 0 ? candidate.width / medianWidth : 1,
  }));

  const medianNailAspect = median(nailBeds.map((bed) => bed.aspectRatio));

  let palmAspect: number | null = null;
  if (axisAngle !== null) {
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    // 旋转后指甲长轴对齐 +x：x 跨度为「沿指方向」，y 跨度为「跨指方向」。
    // palmAspect = 跨指跨度 / (沿指跨度 + 甲长中位数) ≈ 掌宽 / 掌长，
    // 与 HAND_SHAPE_THRESHOLDS 的口径一致（wide-short 取大值、narrow-long 取小值）。
    const alongSpan = Math.max(...xs) - Math.min(...xs);
    const acrossSpan = Math.max(...ys) - Math.min(...ys);
    const denominator = alongSpan + medianLength;
    if (denominator > 0) palmAspect = acrossSpan / denominator;
  }

  const thumbBed = nailBeds.find((bed) => bed.finger === 0);
  let thumbRatio: number | null = null;
  if (thumbBed) {
    const others = nailBeds.filter((bed) => bed.finger !== 0).map((bed) => bed.widthPx);
    const maxOther = others.length > 0 ? Math.max(...others) : 0;
    if (maxOther > 0) thumbRatio = thumbBed.widthPx / maxOther;
  }
  if (thumbRatio === null) warnings.push("hand_profile_thumb_unknown");

  let shape: HandShapeClass = "balanced";
  let shapeSource: HandShapeSource = "classified";
  if (medianNailAspect < HAND_SHAPE_THRESHOLDS.wideShortMaxAspect
    && palmAspect !== null
    && palmAspect > HAND_SHAPE_THRESHOLDS.wideShortMinPalmAspect) {
    shape = "wide-short";
  } else if (medianNailAspect > HAND_SHAPE_THRESHOLDS.narrowLongMinAspect
    && palmAspect !== null
    && palmAspect < HAND_SHAPE_THRESHOLDS.narrowLongMaxPalmAspect) {
    shape = "narrow-long";
  } else if (thumbRatio !== null
    && thumbRatio > HAND_SHAPE_THRESHOLDS.slimTaperedMinThumbRatio
    && medianNailAspect > HAND_SHAPE_THRESHOLDS.slimTaperedMinAspect) {
    shape = "slim-tapered";
  } else {
    shape = "balanced";
    // 关键几何量缺失导致的回落不得记为"确认为均衡手型"。
    if (palmAspect === null || thumbRatio === null) shapeSource = "insufficient-evidence";
  }

  const maskRatio = kept.filter((candidate) => candidate.mask).length / kept.length;
  const fingerRatio = kept.filter((candidate) => candidate.suggestedFinger !== null).length / kept.length;
  const qualityFactor = COMPLETENESS_WEIGHTS.base
    + COMPLETENESS_WEIGHTS.mask * maskRatio
    + COMPLETENESS_WEIGHTS.finger * fingerRatio;
  const completeness = clamp01((kept.length / expectedCandidates) * qualityFactor);
  if (completeness < 0.6) warnings.push("hand_profile_insufficient_candidates");

  return {
    shape,
    shapeSource,
    palmAspect,
    thumbRatio,
    nailBeds,
    medianNailAspect,
    completeness,
    duplicateCandidates: duplicates,
    warnings,
  };
}
