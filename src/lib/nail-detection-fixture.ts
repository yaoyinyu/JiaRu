import type { NailTextureCandidate } from "./nail-texture-recognition/types.ts";

export const NAIL_DETECTION_FIXTURE_VERSION = "nail-detection-fixture/v1";

export interface NailDetectionGroundTruthRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  area: number;
  cx: number;
  cy: number;
}

export interface NailDetectionGroundTruthFixture {
  version: typeof NAIL_DETECTION_FIXTURE_VERSION;
  id: string;
  imagePath: string;
  annotationPath?: string;
  expected: {
    candidateCount: number;
    maxCenterError: number;
  };
  truthRegions: NailDetectionGroundTruthRegion[];
}

export interface NailDetectionMatchResult {
  predictedIndex: number;
  truthIndex: number;
  distance: number;
}

export interface NailDetectionFixtureComparison {
  matches: NailDetectionMatchResult[];
  maxCenterError: number;
  matchedTruthCount: number;
}

export function findGreenAnnotationComponents(
  pixels: Buffer | Uint8Array,
  width: number,
  height: number,
  minArea: number = 200
): NailDetectionGroundTruthRegion[] {
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < width * height; index++) {
    const r = pixels[index * 4] ?? 0;
    const g = pixels[index * 4 + 1] ?? 0;
    const b = pixels[index * 4 + 2] ?? 0;
    mask[index] = g > 180 && g > r * 1.5 && g > b * 1.5 ? 1 : 0;
  }

  const seen = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const components: NailDetectionGroundTruthRegion[] = [];

  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || seen[start]) continue;

    let head = 0;
    let tail = 0;
    let minX = width;
    let minY = height;
    let maxX = 0;
    let maxY = 0;
    let area = 0;
    let sumX = 0;
    let sumY = 0;

    queue[tail++] = start;
    seen[start] = 1;

    while (head < tail) {
      const current = queue[head++];
      const x = current % width;
      const y = Math.floor(current / width);
      area++;
      sumX += x;
      sumY += y;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);

      for (let ny = y - 1; ny <= y + 1; ny++) {
        for (let nx = x - 1; nx <= x + 1; nx++) {
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const next = ny * width + nx;
          if (!mask[next] || seen[next]) continue;
          seen[next] = 1;
          queue[tail++] = next;
        }
      }
    }

    if (area >= minArea) {
      components.push({
        x: minX,
        y: minY,
        width: maxX - minX + 1,
        height: maxY - minY + 1,
        area,
        cx: sumX / area,
        cy: sumY / area,
      });
    }
  }

  return components.sort((a, b) => a.cx - b.cx);
}

export function compareDetectedRegionsToFixture(
  candidates: Array<Pick<NailTextureCandidate, "cx" | "cy">>,
  truthRegions: NailDetectionGroundTruthRegion[]
): NailDetectionFixtureComparison {
  const matches: NailDetectionMatchResult[] = [];
  const used = new Set<number>();
  let maxCenterError = 0;

  for (let truthIndex = 0; truthIndex < truthRegions.length; truthIndex++) {
    const truth = truthRegions[truthIndex];
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;

    for (let predictedIndex = 0; predictedIndex < candidates.length; predictedIndex++) {
      if (used.has(predictedIndex)) continue;
      const candidate = candidates[predictedIndex];
      const distance = Math.hypot(candidate.cx - truth.cx, candidate.cy - truth.cy);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = predictedIndex;
      }
    }

    if (bestIndex >= 0) {
      used.add(bestIndex);
      matches.push({ predictedIndex: bestIndex, truthIndex, distance: bestDistance });
      maxCenterError = Math.max(maxCenterError, bestDistance);
    }
  }

  return {
    matches,
    maxCenterError,
    matchedTruthCount: matches.length,
  };
}
