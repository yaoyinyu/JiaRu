import {
  summarizeMaskExtractionQuality,
} from "./extract-mask-texture.ts";
import type { NailTextureCandidate } from "./types.ts";

export interface RankNailTextureCandidatesOptions {
  imageWidth: number;
  imageHeight: number;
  maxCandidates?: number;
  duplicateOverlapThreshold?: number;
  includeLowConfidenceCandidates?: boolean;
  sourceImage?: {
    width: number;
    height: number;
    data: ArrayLike<number>;
  };
}

export interface NailTextureCandidateAssessment {
  adjustedScore: number;
  confidence: NailTextureCandidate["confidence"];
  warnings: string[];
  highlightRatio: number;
}

function adjustedConfidence(score: number): NailTextureCandidate["confidence"] {
  if (score >= 0.75) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function areaRatio(candidate: NailTextureCandidate, imageArea: number): number {
  return (candidate.width * candidate.length) / imageArea;
}

function aspectRatio(candidate: NailTextureCandidate): number {
  const shorter = Math.min(candidate.width, candidate.length);
  const longer = Math.max(candidate.width, candidate.length);
  return shorter <= 0 ? Number.POSITIVE_INFINITY : longer / shorter;
}

function scorePenalty(candidate: NailTextureCandidate, imageArea: number): number {
  let penalty = 0;
  const ratio = areaRatio(candidate, imageArea);
  if (ratio < 0.0008 || ratio > 0.08) penalty += 0.4;
  const aspect = aspectRatio(candidate);
  if (aspect < 1 || aspect > 4.5) penalty += 0.2;
  return penalty;
}

function colorSaturation(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
}

function estimateHighlightRatio(
  candidate: NailTextureCandidate,
  sourceImage: RankNailTextureCandidatesOptions["sourceImage"]
): number {
  if (!sourceImage) return 0;

  const halfWidth = Math.max(1, candidate.width * 0.5);
  const halfLength = Math.max(1, candidate.length * 0.5);
  const cos = Math.cos(-candidate.angle);
  const sin = Math.sin(-candidate.angle);
  const minX = Math.max(0, Math.floor(candidate.cx - halfWidth));
  const maxX = Math.min(sourceImage.width - 1, Math.ceil(candidate.cx + halfWidth));
  const minY = Math.max(0, Math.floor(candidate.cy - halfLength));
  const maxY = Math.min(sourceImage.height - 1, Math.ceil(candidate.cy + halfLength));

  let highlightPixels = 0;
  let sampledPixels = 0;

  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const dx = x - candidate.cx;
      const dy = y - candidate.cy;
      const localX = dx * cos - dy * sin;
      const localY = dx * sin + dy * cos;
      const ellipse =
        (localX * localX) / (halfWidth * halfWidth) +
        (localY * localY) / (halfLength * halfLength);
      if (ellipse > 1) continue;

      const offset = (y * sourceImage.width + x) * 4;
      const r = Number(sourceImage.data[offset] ?? 0);
      const g = Number(sourceImage.data[offset + 1] ?? 0);
      const b = Number(sourceImage.data[offset + 2] ?? 0);
      const max = Math.max(r, g, b);
      const sat = colorSaturation(r, g, b);

      sampledPixels++;
      if (max >= 245 && sat <= 0.12) {
        highlightPixels++;
      }
    }
  }

  return sampledPixels > 0 ? highlightPixels / sampledPixels : 0;
}

function maskWarningPenalty(warning: string): number {
  switch (warning) {
    case "highlight_hotspots":
      return 0.1;
    default:
      return 0;
  }
}

function withLowScoreDebugWarning(candidate: NailTextureCandidate): NailTextureCandidate {
  if (candidate.score >= 0.35) return candidate;
  const warning = "low_score_debug_candidate";
  return {
    ...candidate,
    warnings: candidate.warnings?.includes(warning)
      ? candidate.warnings
      : [...(candidate.warnings ?? []), warning],
  };
}

function candidateBounds(candidate: NailTextureCandidate): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} {
  const halfWidth = Math.max(0.5, candidate.width * 0.5);
  const halfLength = Math.max(0.5, candidate.length * 0.5);
  return {
    minX: candidate.cx - halfWidth,
    minY: candidate.cy - halfLength,
    maxX: candidate.cx + halfWidth,
    maxY: candidate.cy + halfLength,
  };
}

function candidateOverlapRatio(
  left: NailTextureCandidate,
  right: NailTextureCandidate
): number {
  const a = candidateBounds(left);
  const b = candidateBounds(right);
  const overlapWidth = Math.max(0, Math.min(a.maxX, b.maxX) - Math.max(a.minX, b.minX));
  const overlapHeight = Math.max(0, Math.min(a.maxY, b.maxY) - Math.max(a.minY, b.minY));
  const intersection = overlapWidth * overlapHeight;
  if (intersection <= 0) return 0;

  const leftArea = Math.max(1, (a.maxX - a.minX) * (a.maxY - a.minY));
  const rightArea = Math.max(1, (b.maxX - b.minX) * (b.maxY - b.minY));
  return intersection / (leftArea + rightArea - intersection);
}

function suppressDuplicateCandidates(
  candidates: NailTextureCandidate[],
  overlapThreshold: number
): NailTextureCandidate[] {
  if (overlapThreshold <= 0 || overlapThreshold > 1) return candidates;

  const kept: NailTextureCandidate[] = [];
  for (const candidate of candidates) {
    const overlapsKept = kept.some(
      (selected) => candidateOverlapRatio(candidate, selected) >= overlapThreshold
    );
    if (!overlapsKept) kept.push(candidate);
  }
  return kept;
}

export function assessNailTextureCandidate(
  candidate: NailTextureCandidate,
  options: Pick<RankNailTextureCandidatesOptions, "imageWidth" | "imageHeight" | "sourceImage">
): NailTextureCandidateAssessment {
  const imageArea = options.imageWidth * options.imageHeight;
  const warnings = [...(candidate.warnings ?? [])];
  let penalty = scorePenalty(candidate, imageArea);

  if (candidate.mask) {
    for (const warning of summarizeMaskExtractionQuality(candidate.mask).warnings) {
      if (!warnings.includes(warning)) warnings.push(warning);
    }
  }

  const highlightRatio = estimateHighlightRatio(candidate, options.sourceImage);
  if (highlightRatio >= 0.18 && !warnings.includes("highlight_hotspots")) {
    warnings.push("highlight_hotspots");
  }

  for (const warning of warnings) {
    penalty += maskWarningPenalty(warning);
  }

  const adjustedScore = Math.max(0, candidate.score - penalty);
  return {
    adjustedScore,
    confidence: adjustedConfidence(adjustedScore),
    warnings,
    highlightRatio: Number(highlightRatio.toFixed(4)),
  };
}

export function rankNailTextureCandidates(
  candidates: NailTextureCandidate[],
  options: RankNailTextureCandidatesOptions
): NailTextureCandidate[] {
  const maxCandidates = options.maxCandidates ?? 10;
  const duplicateOverlapThreshold = options.duplicateOverlapThreshold ?? 0.55;
  const includeLowConfidenceCandidates = options.includeLowConfidenceCandidates ?? false;

  const scored = candidates
    .map((candidate) => {
      const assessment = assessNailTextureCandidate(candidate, options);
      return {
        ...candidate,
        score: assessment.adjustedScore,
        confidence: assessment.confidence,
        warnings: assessment.warnings,
      };
    })
    .filter((candidate) => {
      const ratio = areaRatio(candidate, options.imageWidth * options.imageHeight);
      return ratio >= 0.0008 && ratio <= 0.08;
    })
    .filter((candidate) => includeLowConfidenceCandidates || candidate.score >= 0.35)
    .map((candidate) =>
      includeLowConfidenceCandidates ? withLowScoreDebugWarning(candidate) : candidate
    )
    .sort((a, b) => b.score - a.score);

  return suppressDuplicateCandidates(scored, duplicateOverlapThreshold)
    .slice(0, maxCandidates)
    .sort((a, b) => a.cx - b.cx);
}
