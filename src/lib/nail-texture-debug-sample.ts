import type {
  NailTextureCandidateConfidence,
  NailTextureCandidateSource,
  NailTextureModelBackend,
} from "./nail-texture-recognition/types.ts";

export interface NailDebugSampleCandidate {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  length: number;
  width: number;
  assignedFinger: number | null;
  confidence: NailTextureCandidateConfidence;
  source: NailTextureCandidateSource;
  hasMask: boolean;
  warnings: string[];
  extractionDiagnostics?: {
    qualityWarnings: string[];
    qualityOk: boolean;
    highlightPixels: number;
    repairedPixels: number;
    highlightRatio: number;
  };
}

export interface NailDebugSampleDetectionSummary {
  backend: "model" | "fallback";
  modelVersion?: string;
  modelBackend?: NailTextureModelBackend;
  elapsedMs?: number;
  workerElapsedMs?: number;
  maxCandidates?: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  warnings: string[];
}

export interface NailDebugSampleRecord {
  imageId: string;
  imageUrl: string;
  image: {
    width: number;
    height: number;
  };
  backend: "model" | "fallback";
  modelVersion: string;
  modelBackend?: NailTextureModelBackend;
  elapsedMs: number;
  workerElapsedMs?: number;
  recognitionOptions?: {
    maxCandidates?: number;
    workerTimeoutMs?: number;
    includeLowConfidenceCandidates?: boolean;
  };
  warnings: string[];
  originalCandidates: NailDebugSampleCandidate[];
  correctedCandidates: NailDebugSampleCandidate[];
  createdAt: string;
}

export interface NailDebugSampleRegionLike {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
  confidence?: NailTextureCandidateConfidence;
  source?: NailTextureCandidateSource;
  mask?: unknown;
  warnings?: string[];
  extractionDiagnostics?: {
    quality: {
      ok: boolean;
      warnings: string[];
    };
    highlightRepair: {
      highlightPixels: number;
      repairedPixels: number;
      highlightRatio: number;
    };
  };
}

export function toNailDebugSampleCandidate(
  region: NailDebugSampleRegionLike
): NailDebugSampleCandidate {
  return {
    id: region.id,
    cx: region.cx,
    cy: region.cy,
    angle: region.angle,
    length: region.nl,
    width: region.nw,
    assignedFinger: region.assignedFinger,
    confidence: region.confidence ?? "low",
    source: region.source ?? "manual",
    hasMask: Boolean(region.mask),
    warnings: [...(region.warnings ?? [])],
    extractionDiagnostics: region.extractionDiagnostics
      ? {
          qualityWarnings: [...region.extractionDiagnostics.quality.warnings],
          qualityOk: region.extractionDiagnostics.quality.ok,
          highlightPixels: region.extractionDiagnostics.highlightRepair.highlightPixels,
          repairedPixels: region.extractionDiagnostics.highlightRepair.repairedPixels,
          highlightRatio: region.extractionDiagnostics.highlightRepair.highlightRatio,
        }
      : undefined,
  };
}

export function createLocalNailDebugSample(args: {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  detectionSummary: NailDebugSampleDetectionSummary | null;
  originalRegions: NailDebugSampleRegionLike[];
  correctedRegions: NailDebugSampleRegionLike[];
  createdAt?: string;
}): NailDebugSampleRecord {
  const createdAt = args.createdAt ?? new Date().toISOString();
  const summary = args.detectionSummary;

  return {
    imageId: `local-debug-${createdAt.replaceAll(":", "-")}`,
    imageUrl: args.imageUrl,
    image: {
      width: args.imageWidth,
      height: args.imageHeight,
    },
    backend: summary?.backend ?? "fallback",
    modelVersion:
      summary?.modelVersion ??
      (summary?.backend === "model" ? "model-unknown" : "fallback-v0"),
    modelBackend: summary?.modelBackend,
    elapsedMs: summary?.elapsedMs ?? 0,
    workerElapsedMs: summary?.workerElapsedMs,
    recognitionOptions:
      summary &&
      (summary.maxCandidates != null ||
        summary.workerTimeoutMs != null ||
        summary.includeLowConfidenceCandidates != null)
        ? {
            maxCandidates: summary.maxCandidates,
            workerTimeoutMs: summary.workerTimeoutMs,
            includeLowConfidenceCandidates: summary.includeLowConfidenceCandidates,
          }
        : undefined,
    warnings: summary?.warnings ?? [],
    originalCandidates: args.originalRegions.map(toNailDebugSampleCandidate),
    correctedCandidates: args.correctedRegions.map(toNailDebugSampleCandidate),
    createdAt,
  };
}

export function createNailDebugSampleFilename(record: NailDebugSampleRecord): string {
  return `${record.imageId}.json`;
}
