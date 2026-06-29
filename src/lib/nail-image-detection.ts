export interface ImagePixels {
  width: number;
  height: number;
  data: ArrayLike<number>;
}

export interface DetectedNailRegion {
  cx: number;
  cy: number;
  angle: number;
  length: number;
  width: number;
  confidence: "high" | "low";
  score: number;
}

export interface NailDetectionMasks {
  width: number;
  height: number;
  candidate: Uint8Array;
  skin: Uint8Array;
}

interface AnalysisImage {
  width: number;
  height: number;
  scale: number;
  grayscale: Float32Array;
  skin: Uint8Array;
}

interface SaliencyAnalysis extends AnalysisImage {
  score: Float32Array;
  maxScore: number;
}

interface Peak {
  x: number;
  y: number;
  score: number;
}

interface PeakCluster {
  peaks: Peak[];
  weight: number;
  x: number;
  y: number;
  score: number;
}

const MAX_ANALYSIS_DIMENSION = 480;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeNailAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI / 2) result -= Math.PI;
  while (result <= -Math.PI / 2) result += Math.PI;
  return result;
}

function saturation(r: number, g: number, b: number): number {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
}

function prepareImage(source: ImagePixels): AnalysisImage {
  const scale = Math.min(
    1,
    MAX_ANALYSIS_DIMENSION / Math.max(source.width, source.height)
  );
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  const grayscale = new Float32Array(width * height);
  const skin = new Uint8Array(width * height);

  for (let y = 0; y < height; y++) {
    const sourceY = Math.min(source.height - 1, Math.floor(y / scale));
    for (let x = 0; x < width; x++) {
      const sourceX = Math.min(source.width - 1, Math.floor(x / scale));
      const sourceIndex = (sourceY * source.width + sourceX) * 4;
      const r = source.data[sourceIndex];
      const g = source.data[sourceIndex + 1];
      const b = source.data[sourceIndex + 2];
      const index = y * width + x;
      const sat = saturation(r, g, b);
      const value = Math.max(r, g, b) / 255;
      const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
      const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;

      grayscale[index] = r * 0.299 + g * 0.587 + b * 0.114;
      skin[index] =
        cr > 128 &&
        cr < 184 &&
        cb > 72 &&
        cb < 137 &&
        sat > 20 / 255 &&
        sat < 150 / 255 &&
        value < 250 / 255
          ? 1
          : 0;
    }
  }

  return { width, height, scale, grayscale, skin };
}

function integralImage(
  values: ArrayLike<number>,
  width: number,
  height: number
): Float64Array {
  const stride = width + 1;
  const integral = new Float64Array((width + 1) * (height + 1));
  for (let y = 0; y < height; y++) {
    let rowSum = 0;
    for (let x = 0; x < width; x++) {
      rowSum += values[y * width + x];
      integral[(y + 1) * stride + x + 1] =
        integral[y * stride + x + 1] + rowSum;
    }
  }
  return integral;
}

function boxMean(
  integral: Float64Array,
  width: number,
  height: number,
  x: number,
  y: number,
  boxWidth: number,
  boxHeight: number
): number {
  const halfWidth = Math.floor(boxWidth / 2);
  const halfHeight = Math.floor(boxHeight / 2);
  const x0 = Math.max(0, x - halfWidth);
  const y0 = Math.max(0, y - halfHeight);
  const x1 = Math.min(width - 1, x + halfWidth);
  const y1 = Math.min(height - 1, y + halfHeight);
  const stride = width + 1;
  const sum =
    integral[(y1 + 1) * stride + x1 + 1] -
    integral[y0 * stride + x1 + 1] -
    integral[(y1 + 1) * stride + x0] +
    integral[y0 * stride + x0];
  return sum / ((x1 - x0 + 1) * (y1 - y0 + 1));
}

function calculateSaliency(source: ImagePixels): SaliencyAnalysis {
  const prepared = prepareImage(source);
  const { width, height, grayscale, skin } = prepared;
  const edge = new Float32Array(width * height);

  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const index = y * width + x;
      edge[index] = Math.abs(
        grayscale[index] * 4 -
        grayscale[index - 1] -
        grayscale[index + 1] -
        grayscale[index - width] -
        grayscale[index + width]
      );
    }
  }

  const edgeIntegral = integralImage(edge, width, height);
  const skinIntegral = integralImage(skin, width, height);
  const innerWidth = Math.max(11, Math.round(width * 0.041));
  const innerHeight = Math.max(15, Math.round(height * 0.096));
  const outerWidth = Math.max(innerWidth + 8, Math.round(width * 0.117));
  const outerHeight = Math.max(innerHeight + 12, Math.round(height * 0.229));
  const marginX = Math.round(width * 0.035);
  const marginY = Math.round(height * 0.055);
  const score = new Float32Array(width * height);
  let maxScore = 0;

  for (let y = marginY; y < height - marginY; y++) {
    for (let x = marginX; x < width - marginX; x++) {
      const texture = boxMean(
        edgeIntegral,
        width,
        height,
        x,
        y,
        innerWidth,
        innerHeight
      );
      const outerSkin = boxMean(
        skinIntegral,
        width,
        height,
        x,
        y,
        outerWidth,
        outerHeight
      );
      const innerSkin = boxMean(
        skinIntegral,
        width,
        height,
        x,
        y,
        innerWidth,
        innerHeight
      );
      const value = texture * (0.2 + outerSkin) * (1 - 0.65 * innerSkin);
      score[y * width + x] = value;
      maxScore = Math.max(maxScore, value);
    }
  }

  return { ...prepared, score, maxScore };
}

function findPeaks(analysis: SaliencyAnalysis): Peak[] {
  const { width, height, score, maxScore } = analysis;
  if (maxScore <= 0) return [];
  const working = new Float32Array(score);
  const threshold = maxScore * 0.3;
  const suppressionRadius = Math.max(12, Math.round(Math.max(width, height) * 0.095));
  const radiusSquared = suppressionRadius * suppressionRadius;
  const peaks: Peak[] = [];

  while (peaks.length < 12) {
    let bestIndex = -1;
    let bestScore = 0;
    for (let index = 0; index < working.length; index++) {
      if (working[index] > bestScore) {
        bestScore = working[index];
        bestIndex = index;
      }
    }
    if (bestIndex < 0 || bestScore < threshold) break;
    const x = bestIndex % width;
    const y = Math.floor(bestIndex / width);
    peaks.push({ x, y, score: bestScore });

    const minX = Math.max(0, x - suppressionRadius);
    const maxX = Math.min(width - 1, x + suppressionRadius);
    const minY = Math.max(0, y - suppressionRadius);
    const maxY = Math.min(height - 1, y + suppressionRadius);
    for (let sy = minY; sy <= maxY; sy++) {
      for (let sx = minX; sx <= maxX; sx++) {
        const dx = sx - x;
        const dy = sy - y;
        if (dx * dx + dy * dy <= radiusSquared) {
          working[sy * width + sx] = 0;
        }
      }
    }
  }

  return peaks;
}

function clusterPeaks(peaks: Peak[], width: number, height: number): PeakCluster[] {
  const clusterRadius = Math.max(width, height) * 0.13;
  const clusters: PeakCluster[] = [];

  for (const peak of peaks) {
    let target: PeakCluster | undefined;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const cluster of clusters) {
      const distance = Math.hypot(peak.x - cluster.x, peak.y - cluster.y);
      if (distance < clusterRadius && distance < bestDistance) {
        target = cluster;
        bestDistance = distance;
      }
    }

    if (!target) {
      clusters.push({
        peaks: [peak],
        weight: peak.score,
        x: peak.x,
        y: peak.y,
        score: peak.score,
      });
      continue;
    }

    target.peaks.push(peak);
    target.x = (target.x * target.weight + peak.x * peak.score) /
      (target.weight + peak.score);
    target.y = (target.y * target.weight + peak.y * peak.score) /
      (target.weight + peak.score);
    target.weight += peak.score;
    target.score = Math.max(target.score, peak.score);
  }

  return clusters.sort((a, b) => b.weight - a.weight);
}

function estimateClusterSpread(cluster: PeakCluster): number {
  let spread = 0;
  for (let i = 0; i < cluster.peaks.length; i++) {
    for (let j = i + 1; j < cluster.peaks.length; j++) {
      spread = Math.max(
        spread,
        Math.hypot(
          cluster.peaks[i].x - cluster.peaks[j].x,
          cluster.peaks[i].y - cluster.peaks[j].y
        )
      );
    }
  }
  return spread;
}

function estimateFingerAxis(
  cx: number,
  cy: number,
  length: number,
  nailWidth: number,
  skin: Uint8Array,
  width: number,
  height: number
): number {
  const directionCount = 24;
  const start = length * 0.45;
  const end = length * 1.9;
  const halfWidth = nailWidth * 0.5;
  const step = 3;
  let bestAxis = Math.PI / 2;
  let bestScore = Number.NEGATIVE_INFINITY;

  function density(angle: number): number {
    const ux = Math.cos(angle);
    const uy = Math.sin(angle);
    const vx = -uy;
    const vy = ux;
    let skinPixels = 0;
    let samples = 0;
    for (let along = start; along <= end; along += step) {
      for (let across = -halfWidth; across <= halfWidth; across += step) {
        const x = Math.round(cx + ux * along + vx * across);
        const y = Math.round(cy + uy * along + vy * across);
        if (x < 0 || y < 0 || x >= width || y >= height) continue;
        skinPixels += skin[y * width + x];
        samples++;
      }
    }
    return samples > 0 ? skinPixels / samples : 0;
  }

  for (let i = 0; i < directionCount / 2; i++) {
    const angle = i * Math.PI / (directionCount / 2);
    const forward = density(angle);
    const backward = density(angle + Math.PI);
    const axisScore = Math.max(forward, backward) + Math.abs(forward - backward) * 0.4;
    if (axisScore > bestScore) {
      bestScore = axisScore;
      bestAxis = angle;
    }
  }

  return bestAxis;
}

export function createNailDetectionMasks(source: ImagePixels): NailDetectionMasks {
  const analysis = calculateSaliency(source);
  const candidate = new Uint8Array(analysis.score.length);
  const threshold = analysis.maxScore * 0.3;
  for (let i = 0; i < candidate.length; i++) {
    candidate[i] = analysis.score[i] >= threshold ? 1 : 0;
  }
  return {
    width: analysis.width,
    height: analysis.height,
    candidate,
    skin: analysis.skin,
  };
}

export function detectNailRegionsFromImageData(
  source: ImagePixels
): DetectedNailRegion[] {
  if (source.width < 32 || source.height < 32) return [];
  const analysis = calculateSaliency(source);
  const peaks = findPeaks(analysis);
  const clusters = clusterPeaks(peaks, analysis.width, analysis.height);
  const maxDimension = Math.max(analysis.width, analysis.height);
  const selected = clusters.slice(0, 5).map((cluster) => {
    const spread = estimateClusterSpread(cluster);
    const length = clamp(
      Math.max(maxDimension * 0.125, spread + maxDimension * 0.055),
      maxDimension * 0.105,
      maxDimension * 0.175
    );
    const nailWidth = clamp(
      length * 0.72,
      maxDimension * 0.07,
      maxDimension * 0.115
    );
    const axis = estimateFingerAxis(
      cluster.x,
      cluster.y,
      length,
      nailWidth,
      analysis.skin,
      analysis.width,
      analysis.height
    );
    const inverseScale = 1 / analysis.scale;

    return {
      cx: cluster.x * inverseScale,
      cy: cluster.y * inverseScale,
      angle: normalizeNailAngle(axis - Math.PI / 2),
      length: length * inverseScale,
      width: nailWidth * inverseScale,
      confidence: cluster.score >= analysis.maxScore * 0.32 ? "high" as const : "low" as const,
      score: cluster.weight,
    };
  });

  return selected.sort((a, b) => a.cx - b.cx);
}
