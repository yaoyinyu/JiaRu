export interface NailDebugSampleCandidate {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  length: number;
  width: number;
  assignedFinger: number | null;
  confidence: "high" | "low";
  hasMask: boolean;
}

export interface NailDebugSampleDetectionSummary {
  backend: "model" | "fallback";
  modelVersion?: string;
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
  confidence?: "high" | "low";
  mask?: unknown;
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
    hasMask: Boolean(region.mask),
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
    warnings: summary?.warnings ?? [],
    originalCandidates: args.originalRegions.map(toNailDebugSampleCandidate),
    correctedCandidates: args.correctedRegions.map(toNailDebugSampleCandidate),
    createdAt,
  };
}

export function createNailDebugSampleFilename(record: NailDebugSampleRecord): string {
  return `${record.imageId}.json`;
}
