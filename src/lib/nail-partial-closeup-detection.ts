import type { ImagePixels } from "./nail-image-detection.ts";
import type { NailTextureCandidate } from "./nail-texture-recognition/types.ts";

interface PreparedCloseupImage {
  width: number;
  height: number;
  scale: number;
  grayscale: Float32Array;
  painted: Uint8Array;
  smoothSkin: Uint8Array;
}

interface Component {
  pixels: number[];
  area: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  sumX: number;
  sumY: number;
  sumXX: number;
  sumYY: number;
  sumXY: number;
  sumGray: number;
  sumGraySquared: number;
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

function closeBinaryMask(mask: Uint8Array, width: number, height: number): Uint8Array {
  const dilated = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let value = 0;
      for (let dy = -1; dy <= 1 && value === 0; dy += 1) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          const nx = x + dx;
          if (nx >= 0 && nx < width && mask[ny * width + nx]) {
            value = 1;
            break;
          }
        }
      }
      dilated[y * width + x] = value;
    }
  }

  const closed = new Uint8Array(mask.length);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      let value = 1;
      for (let dy = -1; dy <= 1 && value === 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (!dilated[(y + dy) * width + x + dx]) {
            value = 0;
            break;
          }
        }
      }
      closed[y * width + x] = value;
    }
  }
  return closed;
}

function prepareCloseupImage(source: ImagePixels): PreparedCloseupImage {
  const scale = Math.min(
    1,
    MAX_ANALYSIS_DIMENSION / Math.max(source.width, source.height)
  );
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  const grayscale = new Float32Array(width * height);
  const skin = new Uint8Array(width * height);
  const painted = new Uint8Array(width * height);

  for (let y = 0; y < height; y += 1) {
    const sourceY = Math.min(source.height - 1, Math.floor(y / scale));
    for (let x = 0; x < width; x += 1) {
      const sourceX = Math.min(source.width - 1, Math.floor(x / scale));
      const sourceIndex = (sourceY * source.width + sourceX) * 4;
      const r = source.data[sourceIndex];
      const g = source.data[sourceIndex + 1];
      const b = source.data[sourceIndex + 2];
      const maximum = Math.max(r, g, b);
      const minimum = Math.min(r, g, b);
      const colorSaturation = maximum > 0 ? (maximum - minimum) / maximum : 0;
      const gray = r * 0.299 + g * 0.587 + b * 0.114;
      const isSkin =
        (r > 75 &&
          g > 38 &&
          b > 22 &&
          r > g + 4 &&
          r > b + 12 &&
          colorSaturation > 0.08 &&
          colorSaturation < 0.68) ||
        (r > 165 &&
          g > 140 &&
          b > 120 &&
          r >= g + 2 &&
          r >= b + 8 &&
          colorSaturation < 0.35);
      const index = y * width + x;
      grayscale[index] = gray;
      skin[index] = isSkin ? 1 : 0;
      painted[index] = !isSkin && gray < 225 ? 1 : 0;
    }
  }

  const laplacian = new Float32Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      laplacian[index] = Math.abs(
        grayscale[index] * 4 -
          grayscale[index - 1] -
          grayscale[index + 1] -
          grayscale[index - width] -
          grayscale[index + width]
      );
    }
  }

  const smoothSkin = new Uint8Array(width * height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      if (!skin[index]) continue;
      let localEdge = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          localEdge += laplacian[(y + dy) * width + x + dx];
        }
      }
      smoothSkin[index] = localEdge / 9 < 20 ? 1 : 0;
    }
  }

  return {
    width,
    height,
    scale,
    grayscale,
    painted: closeBinaryMask(painted, width, height),
    smoothSkin,
  };
}

function collectComponents(analysis: PreparedCloseupImage): Component[] {
  const { width, height, grayscale, painted } = analysis;
  const visited = new Uint8Array(painted.length);
  const queue = new Int32Array(painted.length);
  const components: Component[] = [];

  for (let start = 0; start < painted.length; start += 1) {
    if (!painted[start] || visited[start]) continue;
    let head = 0;
    let tail = 0;
    queue[tail++] = start;
    visited[start] = 1;
    const component: Component = {
      pixels: [],
      area: 0,
      minX: width,
      minY: height,
      maxX: 0,
      maxY: 0,
      sumX: 0,
      sumY: 0,
      sumXX: 0,
      sumYY: 0,
      sumXY: 0,
      sumGray: 0,
      sumGraySquared: 0,
    };

    while (head < tail) {
      const index = queue[head++];
      const x = index % width;
      const y = Math.floor(index / width);
      const gray = grayscale[index];
      component.pixels.push(index);
      component.area += 1;
      component.minX = Math.min(component.minX, x);
      component.minY = Math.min(component.minY, y);
      component.maxX = Math.max(component.maxX, x);
      component.maxY = Math.max(component.maxY, y);
      component.sumX += x;
      component.sumY += y;
      component.sumXX += x * x;
      component.sumYY += y * y;
      component.sumXY += x * y;
      component.sumGray += gray;
      component.sumGraySquared += gray * gray;

      for (let dy = -1; dy <= 1; dy += 1) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dx === 0 && dy === 0) continue;
          const nx = x + dx;
          if (nx < 0 || nx >= width) continue;
          const neighbor = ny * width + nx;
          if (painted[neighbor] && !visited[neighbor]) {
            visited[neighbor] = 1;
            queue[tail++] = neighbor;
          }
        }
      }
    }
    components.push(component);
  }
  return components;
}

function directSmoothSkinRatio(
  component: Component,
  analysis: PreparedCloseupImage
): number {
  const { width, height, smoothSkin } = analysis;
  const direct = new Uint8Array(width * height);
  for (const index of component.pixels) {
    const x = index % width;
    const y = Math.floor(index / width);
    for (let dy = -3; dy <= 3; dy += 1) {
      const ny = y + dy;
      if (ny < 0 || ny >= height) continue;
      for (let dx = -3; dx <= 3; dx += 1) {
        const nx = x + dx;
        if (nx >= 0 && nx < width) direct[ny * width + nx] = 1;
      }
    }
  }
  for (const index of component.pixels) direct[index] = 0;

  let surrounding = 0;
  let skin = 0;
  for (let index = 0; index < direct.length; index += 1) {
    if (!direct[index]) continue;
    surrounding += 1;
    skin += smoothSkin[index];
  }
  return surrounding > 0 ? skin / surrounding : 0;
}

function componentToCandidate(
  component: Component,
  analysis: PreparedCloseupImage,
  index: number
): NailTextureCandidate | null {
  const { width, height, scale } = analysis;
  const imageArea = width * height;
  const maxDimension = Math.max(width, height);
  const boxWidth = component.maxX - component.minX + 1;
  const boxHeight = component.maxY - component.minY + 1;
  const shorter = Math.min(boxWidth, boxHeight);
  const longer = Math.max(boxWidth, boxHeight);
  const fill = component.area / (boxWidth * boxHeight);
  const areaRatio = component.area / imageArea;
  if (
    component.minX <= 1 ||
    component.minY <= 1 ||
    component.maxX >= width - 2 ||
    component.maxY >= height - 2 ||
    areaRatio < 0.0033 ||
    areaRatio > 0.035 ||
    shorter < maxDimension * 0.035 ||
    longer > maxDimension * 0.24 ||
    longer / Math.max(1, shorter) > 3.2 ||
    fill < 0.32
  ) {
    return null;
  }

  const cx = component.sumX / component.area;
  const cy = component.sumY / component.area;
  const varianceX = component.sumXX / component.area - cx * cx;
  const varianceY = component.sumYY / component.area - cy * cy;
  const covariance = component.sumXY / component.area - cx * cy;
  const majorAxis = 0.5 * Math.atan2(2 * covariance, varianceX - varianceY);
  const cos = Math.cos(majorAxis);
  const sin = Math.sin(majorAxis);
  let minAlong = Number.POSITIVE_INFINITY;
  let maxAlong = Number.NEGATIVE_INFINITY;
  let minAcross = Number.POSITIVE_INFINITY;
  let maxAcross = Number.NEGATIVE_INFINITY;
  for (const pixel of component.pixels) {
    const x = pixel % width;
    const y = Math.floor(pixel / width);
    const dx = x - cx;
    const dy = y - cy;
    const along = dx * cos + dy * sin;
    const across = -dx * sin + dy * cos;
    minAlong = Math.min(minAlong, along);
    maxAlong = Math.max(maxAlong, along);
    minAcross = Math.min(minAcross, across);
    maxAcross = Math.max(maxAcross, across);
  }
  const componentLength = maxAlong - minAlong + 1;
  const componentWidth = maxAcross - minAcross + 1;
  const meanGray = component.sumGray / component.area;
  const grayVariance = Math.max(
    0,
    component.sumGraySquared / component.area - meanGray * meanGray
  );
  const grayStandardDeviation = Math.sqrt(grayVariance);
  if (meanGray >= 55 && grayStandardDeviation < 18) {
    return null;
  }
  const nearbySkin = directSmoothSkinRatio(component, analysis);
  if (nearbySkin < 0.24) {
    return null;
  }

  const inverseScale = 1 / scale;
  return {
    id: `partial-closeup-${index}`,
    cx: cx * inverseScale,
    cy: cy * inverseScale,
    angle: normalizeNailAngle(majorAxis - Math.PI / 2),
    length:
      clamp(componentLength * 1.12, maxDimension * 0.065, maxDimension * 0.24) *
      inverseScale,
    width:
      clamp(componentWidth * 1.18, maxDimension * 0.035, maxDimension * 0.16) *
      inverseScale,
    score: areaRatio * nearbySkin * (1 + Math.min(1, grayStandardDeviation / 32)),
    confidence: "low",
    source: "partial-closeup",
    suggestedFinger: null,
    warnings: ["partial_closeup_color_detection"],
  };
}

function selectCoherentCandidateCluster(
  candidates: NailTextureCandidate[],
  maxDistance: number
): NailTextureCandidate[] {
  const visited = new Uint8Array(candidates.length);
  const clusters: NailTextureCandidate[][] = [];

  for (let start = 0; start < candidates.length; start += 1) {
    if (visited[start]) continue;
    const queue = [start];
    visited[start] = 1;
    const cluster: NailTextureCandidate[] = [];

    while (queue.length > 0) {
      const currentIndex = queue.shift();
      if (currentIndex == null) break;
      const current = candidates[currentIndex];
      cluster.push(current);
      for (let index = 0; index < candidates.length; index += 1) {
        if (visited[index]) continue;
        const candidate = candidates[index];
        if (Math.hypot(candidate.cx - current.cx, candidate.cy - current.cy) <= maxDistance) {
          visited[index] = 1;
          queue.push(index);
        }
      }
    }
    clusters.push(cluster);
  }

  return clusters.sort((a, b) => {
    if (b.length !== a.length) return b.length - a.length;
    return (
      b.reduce((sum, candidate) => sum + candidate.score, 0) -
      a.reduce((sum, candidate) => sum + candidate.score, 0)
    );
  })[0] ?? [];
}

/**
 * 保守定位局部近景中的已上色甲面。该路径只作为完整手部几何失败后的候选生成器；
 * 返回 2 至 5 个相互独立、紧邻平滑皮肤的大连通区域，否则拒绝自动展示。
 */
export function detectPartialCloseupNailCandidates(
  source: ImagePixels
): NailTextureCandidate[] {
  if (source.width < 64 || source.height < 64) return [];
  const analysis = prepareCloseupImage(source);
  const candidates = collectComponents(analysis)
    .map((component, index) => componentToCandidate(component, analysis, index))
    .filter((candidate): candidate is NailTextureCandidate => candidate !== null);
  const coherentCandidates = selectCoherentCandidateCluster(
    candidates,
    Math.max(source.width, source.height) * 0.32
  )
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  if (coherentCandidates.length < 2) return [];
  const confidence = coherentCandidates.length >= 4 ? "medium" : "low";
  return coherentCandidates
    .sort((a, b) => a.cx + a.cy * 0.12 - (b.cx + b.cy * 0.12))
    .map((candidate, index) => ({
      ...candidate,
      confidence,
      suggestedFinger: index,
    }));
}
