export interface NailDetectionDebugRegion {
  cx: number;
  cy: number;
  angle: number;
  length: number;
  width: number;
  confidence: "high" | "medium" | "low";
  score: number;
}

export interface NailDetectionGroundTruthRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  area: number;
  cx: number;
  cy: number;
}

export interface NailDetectionDebugMatch {
  predictedIndex: number;
  truthIndex: number;
  distance: number;
}

export interface NailDetectionDebugPayload {
  input: string;
  annotation: string | null;
  output: string;
  candidateMaskOutput: string;
  skinMaskOutput: string;
  debugJsonOutput: string;
  width: number;
  height: number;
  count: number;
  backend: string;
  modelVersion?: string;
  modelInfo?: unknown;
  warnings: string[];
  debugOutputs?: unknown;
  regions: NailDetectionDebugRegion[];
  groundTruth?: NailDetectionGroundTruthRegion[] | null;
  matches?: NailDetectionDebugMatch[];
  maxCenterError?: number;
}

export interface NailDebugComparisonPair {
  baselineIndex: number;
  candidateIndex: number;
  centerDistance: number;
  scoreDelta: number;
  lengthDelta: number;
  widthDelta: number;
  angleDeltaDeg: number;
}

export interface NailDebugComparisonResult {
  ok: boolean;
  baseline: {
    backend: string;
    modelVersion?: string;
    count: number;
    warnings: string[];
    maxCenterError: number | null;
  };
  candidate: {
    backend: string;
    modelVersion?: string;
    count: number;
    warnings: string[];
    maxCenterError: number | null;
  };
  matchedCount: number;
  countDelta: number;
  averageCenterDistance: number;
  maxCenterDistance: number;
  averageScoreDelta: number;
  warningDiff: {
    added: string[];
    removed: string[];
  };
  maxCenterErrorDelta: number | null;
  unmatchedBaselineIndices: number[];
  unmatchedCandidateIndices: number[];
  pairs: NailDebugComparisonPair[];
  regressionReasons: string[];
}

export interface CompareNailDebugOptions {
  maxCenterDistance?: number;
  allowCountDecrease?: boolean;
}

function normalizeAngleDeltaDegrees(a: number, b: number): number {
  let delta = ((b - a) * 180) / Math.PI;
  while (delta <= -180) delta += 360;
  while (delta > 180) delta -= 360;
  return delta;
}

function sortRegionsLeftToRight(regions: NailDetectionDebugRegion[]) {
  return regions
    .map((region, index) => ({ region, index }))
    .sort((a, b) => a.region.cx - b.region.cx);
}

export function compareNailDebugPayloads(
  baseline: NailDetectionDebugPayload,
  candidate: NailDetectionDebugPayload,
  options: CompareNailDebugOptions = {}
): NailDebugComparisonResult {
  const maxCenterDistance = options.maxCenterDistance ?? 35;
  const allowCountDecrease = options.allowCountDecrease ?? false;

  const baselineSorted = sortRegionsLeftToRight(baseline.regions);
  const candidateSorted = sortRegionsLeftToRight(candidate.regions);
  const pairCount = Math.min(baselineSorted.length, candidateSorted.length);

  const pairs: NailDebugComparisonPair[] = [];
  for (let index = 0; index < pairCount; index++) {
    const base = baselineSorted[index];
    const next = candidateSorted[index];
    pairs.push({
      baselineIndex: base.index,
      candidateIndex: next.index,
      centerDistance: Math.hypot(base.region.cx - next.region.cx, base.region.cy - next.region.cy),
      scoreDelta: next.region.score - base.region.score,
      lengthDelta: next.region.length - base.region.length,
      widthDelta: next.region.width - base.region.width,
      angleDeltaDeg: normalizeAngleDeltaDegrees(base.region.angle, next.region.angle),
    });
  }

  const unmatchedBaselineIndices = baselineSorted.slice(pairCount).map((item) => item.index);
  const unmatchedCandidateIndices = candidateSorted.slice(pairCount).map((item) => item.index);

  const averageCenterDistance = pairs.length
    ? pairs.reduce((sum, pair) => sum + pair.centerDistance, 0) / pairs.length
    : 0;
  const maxPairCenterDistance = pairs.reduce(
    (max, pair) => Math.max(max, pair.centerDistance),
    0
  );
  const averageScoreDelta = pairs.length
    ? pairs.reduce((sum, pair) => sum + pair.scoreDelta, 0) / pairs.length
    : 0;

  const baselineWarnings = new Set(baseline.warnings);
  const candidateWarnings = new Set(candidate.warnings);
  const addedWarnings = [...candidateWarnings].filter((warning) => !baselineWarnings.has(warning));
  const removedWarnings = [...baselineWarnings].filter((warning) => !candidateWarnings.has(warning));

  const regressionReasons: string[] = [];
  if (!allowCountDecrease && candidate.count < baseline.count) {
    regressionReasons.push(`candidate_count_decreased:${candidate.count}<${baseline.count}`);
  }
  if (maxPairCenterDistance > maxCenterDistance) {
    regressionReasons.push(
      `max_center_distance_exceeded:${maxPairCenterDistance.toFixed(2)}>${maxCenterDistance}`
    );
  }
  if (addedWarnings.length > 0) {
    regressionReasons.push(`new_warnings:${addedWarnings.join(",")}`);
  }
  if (unmatchedBaselineIndices.length > 0) {
    regressionReasons.push(`unmatched_baseline:${unmatchedBaselineIndices.join(",")}`);
  }

  const baselineMaxCenterError =
    typeof baseline.maxCenterError === "number" ? baseline.maxCenterError : null;
  const candidateMaxCenterError =
    typeof candidate.maxCenterError === "number" ? candidate.maxCenterError : null;
  const maxCenterErrorDelta =
    baselineMaxCenterError !== null && candidateMaxCenterError !== null
      ? candidateMaxCenterError - baselineMaxCenterError
      : null;

  return {
    ok: regressionReasons.length === 0,
    baseline: {
      backend: baseline.backend,
      modelVersion: baseline.modelVersion,
      count: baseline.count,
      warnings: baseline.warnings,
      maxCenterError: baselineMaxCenterError,
    },
    candidate: {
      backend: candidate.backend,
      modelVersion: candidate.modelVersion,
      count: candidate.count,
      warnings: candidate.warnings,
      maxCenterError: candidateMaxCenterError,
    },
    matchedCount: pairs.length,
    countDelta: candidate.count - baseline.count,
    averageCenterDistance,
    maxCenterDistance: maxPairCenterDistance,
    averageScoreDelta,
    warningDiff: {
      added: addedWarnings,
      removed: removedWarnings,
    },
    maxCenterErrorDelta,
    unmatchedBaselineIndices,
    unmatchedCandidateIndices,
    pairs,
    regressionReasons,
  };
}
