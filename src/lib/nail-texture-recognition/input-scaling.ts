import type { NailTextureCandidate } from "./types.ts";

export interface DetectionInputGeometry {
  width: number;
  height: number;
  scaleX: number;
  scaleY: number;
  rgbaBytes: number;
}

export function calculateDetectionInputGeometry(
  originalWidth: number,
  originalHeight: number,
  maxDimension: number
): DetectionInputGeometry {
  if (
    !Number.isFinite(originalWidth) ||
    !Number.isFinite(originalHeight) ||
    originalWidth <= 0 ||
    originalHeight <= 0
  ) {
    throw new Error("invalid_detection_image_dimensions");
  }
  if (!Number.isFinite(maxDimension) || maxDimension < 1) {
    throw new Error("invalid_detection_max_dimension");
  }

  const scale = Math.min(1, maxDimension / Math.max(originalWidth, originalHeight));
  const width = Math.max(1, Math.round(originalWidth * scale));
  const height = Math.max(1, Math.round(originalHeight * scale));
  return {
    width,
    height,
    scaleX: width / originalWidth,
    scaleY: height / originalHeight,
    rgbaBytes: width * height * 4,
  };
}

export function remapNailTextureCandidatesToOriginal(
  candidates: NailTextureCandidate[],
  geometry: Pick<DetectionInputGeometry, "scaleX" | "scaleY">,
  originalWidth: number,
  originalHeight: number
): NailTextureCandidate[] {
  const inverseScaleX = 1 / geometry.scaleX;
  const inverseScaleY = 1 / geometry.scaleY;
  return candidates.map((candidate) => ({
    ...candidate,
    cx: Math.max(0, Math.min(originalWidth, candidate.cx * inverseScaleX)),
    cy: Math.max(0, Math.min(originalHeight, candidate.cy * inverseScaleY)),
    width: Math.max(1, Math.min(originalWidth, candidate.width * inverseScaleX)),
    length: Math.max(1, Math.min(originalHeight, candidate.length * inverseScaleY)),
  }));
}
