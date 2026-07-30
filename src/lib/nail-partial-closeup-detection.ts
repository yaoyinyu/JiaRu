import type { ImagePixels } from "./nail-image-detection.ts";
import type { NailTextureCandidate } from "./nail-texture-recognition/types.ts";

interface PreparedCloseupImage {
  width: number;
  height: number;
  scale: number;
  grayscale: Float32Array;
  red: Uint8Array;
  green: Uint8Array;
  blue: Uint8Array;
  painted: Uint8Array;
  skin: Uint8Array;
  smoothSkin: Uint8Array;
  handSupport: Uint8Array;
  handCenterX: number;
  handCenterY: number;
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
  sumRed: number;
  sumGreen: number;
  sumBlue: number;
}

export type PartialCloseupRejectionReason =
  | "touches_edge"
  | "area_too_small"
  | "area_too_large"
  | "short_axis_too_small"
  | "long_axis_too_large"
  | "aspect_ratio_too_large"
  | "fill_too_low"
  | "flat_mid_tone"
  | "outside_hand_support"
  | "raw_skin_ring_too_low"
  | "local_color_contrast_too_low"
  | "low_contrast_inside_skin_too_low"
  | "low_contrast_skin_ring_too_low"
  | "low_contrast_hand_support_too_low"
  | "low_contrast_inside_too_dark"
  | "low_contrast_inside_too_textured"
  | "low_contrast_boundary_gradient_too_low";

export interface PartialCloseupDetectionDiagnostics {
  analysisWidth: number;
  analysisHeight: number;
  componentCount: number;
  acceptedComponentCount: number;
  selectedCandidateCount: number;
  rejectionCounts: Partial<Record<PartialCloseupRejectionReason, number>>;
  strategy: "painted-color" | "low-contrast-boundary" | null;
  lowContrastComponentCount: number;
  lowContrastAcceptedComponentCount: number;
  lowContrastSelectedCandidateCount: number;
  lowContrastRejectionCounts: Partial<Record<PartialCloseupRejectionReason, number>>;
}

export interface PartialCloseupDetectionResult {
  candidates: NailTextureCandidate[];
  diagnostics: PartialCloseupDetectionDiagnostics;
}

interface RingEvidence {
  rawSkinRatio: number;
  smoothSkinRatio: number;
  handSupportRatio: number;
  colorDistance: number;
}

interface ComponentEvaluation {
  candidate: NailTextureCandidate | null;
  rejectionReasons: PartialCloseupRejectionReason[];
}

const MAX_ANALYSIS_DIMENSION = 640;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeNailAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI / 2) result -= Math.PI;
  while (result <= -Math.PI / 2) result += Math.PI;
  return result;
}

function dilateBinaryMask(
  mask: Uint8Array,
  width: number,
  height: number,
  radius = 1
): Uint8Array {
  const dilated = new Uint8Array(mask.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let value = 0;
      for (let dy = -radius; dy <= radius && value === 0; dy += 1) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -radius; dx <= radius; dx += 1) {
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
  return dilated;
}

function erodeBinaryMask(
  mask: Uint8Array,
  width: number,
  height: number,
  radius = 1
): Uint8Array {
  const eroded = new Uint8Array(mask.length);
  for (let y = radius; y < height - radius; y += 1) {
    for (let x = radius; x < width - radius; x += 1) {
      let value = 1;
      for (let dy = -radius; dy <= radius && value === 1; dy += 1) {
        for (let dx = -radius; dx <= radius; dx += 1) {
          if (!mask[(y + dy) * width + x + dx]) {
            value = 0;
            break;
          }
        }
      }
      eroded[y * width + x] = value;
    }
  }
  return eroded;
}

function openBinaryMask(mask: Uint8Array, width: number, height: number): Uint8Array {
  return dilateBinaryMask(erodeBinaryMask(mask, width, height), width, height);
}

function closeBinaryMask(
  mask: Uint8Array,
  width: number,
  height: number,
  radius = 1
): Uint8Array {
  return erodeBinaryMask(
    dilateBinaryMask(mask, width, height, radius),
    width,
    height,
    radius
  );
}

function findLargestMaskComponent(
  mask: Uint8Array,
  width: number,
  height: number
): { mask: Uint8Array; centerX: number; centerY: number } {
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  let largest: number[] = [];

  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let head = 0;
    let tail = 0;
    const pixels: number[] = [];
    queue[tail++] = start;
    visited[start] = 1;
    while (head < tail) {
      const index = queue[head++];
      pixels.push(index);
      const x = index % width;
      const y = Math.floor(index / width);
      for (let dy = -1; dy <= 1; dy += 1) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dx === 0 && dy === 0) continue;
          const nx = x + dx;
          if (nx < 0 || nx >= width) continue;
          const neighbor = ny * width + nx;
          if (mask[neighbor] && !visited[neighbor]) {
            visited[neighbor] = 1;
            queue[tail++] = neighbor;
          }
        }
      }
    }
    if (pixels.length > largest.length) largest = pixels;
  }

  const support = new Uint8Array(mask.length);
  let sumX = 0;
  let sumY = 0;
  for (const index of largest) {
    support[index] = 1;
    sumX += index % width;
    sumY += Math.floor(index / width);
  }
  return {
    mask: support,
    centerX: largest.length > 0 ? sumX / largest.length : width / 2,
    centerY: largest.length > 0 ? sumY / largest.length : height / 2,
  };
}

function prepareCloseupImage(source: ImagePixels): PreparedCloseupImage {
  const scale = Math.min(
    1,
    MAX_ANALYSIS_DIMENSION / Math.max(source.width, source.height)
  );
  const width = Math.max(1, Math.round(source.width * scale));
  const height = Math.max(1, Math.round(source.height * scale));
  const grayscale = new Float32Array(width * height);
  const red = new Uint8Array(width * height);
  const green = new Uint8Array(width * height);
  const blue = new Uint8Array(width * height);
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
      red[index] = r;
      green[index] = g;
      blue[index] = b;
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

  const hand = findLargestMaskComponent(skin, width, height);

  return {
    width,
    height,
    scale,
    grayscale,
    red,
    green,
    blue,
    painted: closeBinaryMask(openBinaryMask(painted, width, height), width, height),
    skin,
    smoothSkin,
    handSupport: hand.mask,
    handCenterX: hand.centerX,
    handCenterY: hand.centerY,
  };
}

function collectMaskComponents(
  mask: Uint8Array,
  analysis: PreparedCloseupImage
): Component[] {
  const { width, height, grayscale, red, green, blue } = analysis;
  const visited = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const components: Component[] = [];

  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
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
      sumRed: 0,
      sumGreen: 0,
      sumBlue: 0,
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
      component.sumRed += red[index];
      component.sumGreen += green[index];
      component.sumBlue += blue[index];

      for (let dy = -1; dy <= 1; dy += 1) {
        const ny = y + dy;
        if (ny < 0 || ny >= height) continue;
        for (let dx = -1; dx <= 1; dx += 1) {
          if (dx === 0 && dy === 0) continue;
          const nx = x + dx;
          if (nx < 0 || nx >= width) continue;
          const neighbor = ny * width + nx;
          if (mask[neighbor] && !visited[neighbor]) {
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

function collectComponents(analysis: PreparedCloseupImage): Component[] {
  return collectMaskComponents(analysis.painted, analysis);
}

function collectRingEvidence(
  component: Component,
  analysis: PreparedCloseupImage
): RingEvidence {
  const { width, height, red, green, blue, skin, smoothSkin, handSupport } = analysis;
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
  let rawSkin = 0;
  let smooth = 0;
  let support = 0;
  let ringRed = 0;
  let ringGreen = 0;
  let ringBlue = 0;
  for (let index = 0; index < direct.length; index += 1) {
    if (!direct[index]) continue;
    surrounding += 1;
    rawSkin += skin[index];
    smooth += smoothSkin[index];
    support += handSupport[index];
    if (skin[index]) {
      ringRed += red[index];
      ringGreen += green[index];
      ringBlue += blue[index];
    }
  }
  const componentRed = component.sumRed / component.area;
  const componentGreen = component.sumGreen / component.area;
  const componentBlue = component.sumBlue / component.area;
  const skinCount = Math.max(1, rawSkin);
  const deltaRed = componentRed - ringRed / skinCount;
  const deltaGreen = componentGreen - ringGreen / skinCount;
  const deltaBlue = componentBlue - ringBlue / skinCount;
  return {
    rawSkinRatio: surrounding > 0 ? rawSkin / surrounding : 0,
    smoothSkinRatio: surrounding > 0 ? smooth / surrounding : 0,
    handSupportRatio: surrounding > 0 ? support / surrounding : 0,
    colorDistance:
      Math.hypot(deltaRed, deltaGreen, deltaBlue) / Math.sqrt(3),
  };
}

function componentToCandidate(
  component: Component,
  analysis: PreparedCloseupImage,
  index: number
): ComponentEvaluation {
  const { width, height, scale } = analysis;
  const imageArea = width * height;
  const maxDimension = Math.max(width, height);
  const boxWidth = component.maxX - component.minX + 1;
  const boxHeight = component.maxY - component.minY + 1;
  const shorter = Math.min(boxWidth, boxHeight);
  const longer = Math.max(boxWidth, boxHeight);
  const fill = component.area / (boxWidth * boxHeight);
  const areaRatio = component.area / imageArea;
  const rejectionReasons: PartialCloseupRejectionReason[] = [];
  if (
    component.minX <= 1 ||
    component.minY <= 1 ||
    component.maxX >= width - 2 ||
    component.maxY >= height - 2
  ) rejectionReasons.push("touches_edge");
  if (areaRatio < 0.0033) rejectionReasons.push("area_too_small");
  if (areaRatio > 0.035) rejectionReasons.push("area_too_large");
  if (shorter < maxDimension * 0.035) rejectionReasons.push("short_axis_too_small");
  if (longer > maxDimension * 0.24) rejectionReasons.push("long_axis_too_large");
  if (longer / Math.max(1, shorter) > 3.2) {
    rejectionReasons.push("aspect_ratio_too_large");
  }
  if (fill < 0.32) rejectionReasons.push("fill_too_low");
  if (rejectionReasons.length > 0) return { candidate: null, rejectionReasons };

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
    return { candidate: null, rejectionReasons: ["flat_mid_tone"] };
  }
  const ring = collectRingEvidence(component, analysis);
  if (ring.handSupportRatio < 0.38) rejectionReasons.push("outside_hand_support");
  if (ring.rawSkinRatio < 0.52) rejectionReasons.push("raw_skin_ring_too_low");
  if (ring.colorDistance < 18) rejectionReasons.push("local_color_contrast_too_low");
  if (rejectionReasons.length > 0) return { candidate: null, rejectionReasons };

  const inverseScale = 1 / scale;
  return {
    candidate: {
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
      score:
        areaRatio *
        (0.5 * ring.rawSkinRatio +
          0.3 * ring.handSupportRatio +
          0.2 * ring.smoothSkinRatio) *
        (1 + Math.min(1, ring.colorDistance / 48)) *
        (1 + Math.min(1, grayStandardDeviation / 32)),
      confidence: "low",
      source: "partial-closeup",
      suggestedFinger: null,
      warnings: ["partial_closeup_color_detection"],
    },
    rejectionReasons: [],
  };
}

interface LowContrastBoundaryResult {
  candidates: NailTextureCandidate[];
  componentCount: number;
  acceptedComponentCount: number;
  rejectionCounts: Partial<Record<PartialCloseupRejectionReason, number>>;
}

function blurGrayscale(
  grayscale: Float32Array,
  width: number,
  height: number
): Float32Array {
  const kernel = [1 / 16, 4 / 16, 6 / 16, 4 / 16, 1 / 16];
  const horizontal = new Float32Array(grayscale.length);
  const blurred = new Float32Array(grayscale.length);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let value = 0;
      for (let offset = -2; offset <= 2; offset += 1) {
        const sampleX = clamp(x + offset, 0, width - 1);
        value += grayscale[y * width + sampleX] * kernel[offset + 2];
      }
      horizontal[y * width + x] = value;
    }
  }
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let value = 0;
      for (let offset = -2; offset <= 2; offset += 1) {
        const sampleY = clamp(y + offset, 0, height - 1);
        value += horizontal[sampleY * width + x] * kernel[offset + 2];
      }
      blurred[y * width + x] = value;
    }
  }
  return blurred;
}

function computeSobelMagnitude(
  grayscale: Float32Array,
  width: number,
  height: number
): Float32Array {
  const blurred = blurGrayscale(grayscale, width, height);
  const magnitude = new Float32Array(grayscale.length);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const topLeft = blurred[(y - 1) * width + x - 1];
      const top = blurred[(y - 1) * width + x];
      const topRight = blurred[(y - 1) * width + x + 1];
      const left = blurred[y * width + x - 1];
      const right = blurred[y * width + x + 1];
      const bottomLeft = blurred[(y + 1) * width + x - 1];
      const bottom = blurred[(y + 1) * width + x];
      const bottomRight = blurred[(y + 1) * width + x + 1];
      const gradientX =
        -topLeft - 2 * left - bottomLeft + topRight + 2 * right + bottomRight;
      const gradientY =
        -topLeft - 2 * top - topRight + bottomLeft + 2 * bottom + bottomRight;
      magnitude[y * width + x] = Math.hypot(gradientX, gradientY);
    }
  }
  return magnitude;
}

function lowContrastComponentToCandidate(
  component: Component,
  analysis: PreparedCloseupImage,
  edgeMagnitude: Float32Array,
  thresholdIndex: number,
  componentIndex: number
): ComponentEvaluation {
  const { width, height, scale, grayscale, skin, handSupport } = analysis;
  const imageArea = width * height;
  const maxDimension = Math.max(width, height);
  const boxWidth = component.maxX - component.minX + 1;
  const boxHeight = component.maxY - component.minY + 1;
  const shorter = Math.min(boxWidth, boxHeight);
  const longer = Math.max(boxWidth, boxHeight);
  const fill = component.area / (boxWidth * boxHeight);
  const areaRatio = component.area / imageArea;
  const rejectionReasons: PartialCloseupRejectionReason[] = [];
  if (
    component.minX <= 1 ||
    component.minY <= 1 ||
    component.maxX >= width - 2 ||
    component.maxY >= height - 2
  ) rejectionReasons.push("touches_edge");
  if (areaRatio < 0.0014) rejectionReasons.push("area_too_small");
  if (areaRatio > 0.015) rejectionReasons.push("area_too_large");
  if (shorter < maxDimension * 0.034) rejectionReasons.push("short_axis_too_small");
  if (longer > maxDimension * 0.18) rejectionReasons.push("long_axis_too_large");
  if (longer / Math.max(1, shorter) > 2.7) {
    rejectionReasons.push("aspect_ratio_too_large");
  }
  if (fill < 0.34) rejectionReasons.push("fill_too_low");
  if (rejectionReasons.length > 0) return { candidate: null, rejectionReasons };

  const meanGray = component.sumGray / component.area;
  const grayVariance = Math.max(
    0,
    component.sumGraySquared / component.area - meanGray * meanGray
  );
  const grayStandardDeviation = Math.sqrt(grayVariance);
  let insideSkin = 0;
  const componentMask = new Uint8Array(width * height);
  for (const pixel of component.pixels) {
    componentMask[pixel] = 1;
    insideSkin += skin[pixel];
  }
  const ringMask = dilateBinaryMask(componentMask, width, height, 4);
  let ringPixels = 0;
  let ringSkin = 0;
  let ringSupport = 0;
  let ringGradient = 0;
  for (let index = 0; index < ringMask.length; index += 1) {
    if (!ringMask[index] || componentMask[index]) continue;
    ringPixels += 1;
    ringSkin += skin[index];
    ringSupport += handSupport[index];
    ringGradient += edgeMagnitude[index];
  }
  const insideSkinRatio = insideSkin / component.area;
  const ringSkinRatio = ringPixels > 0 ? ringSkin / ringPixels : 0;
  const ringSupportRatio = ringPixels > 0 ? ringSupport / ringPixels : 0;
  const meanRingGradient = ringPixels > 0 ? ringGradient / ringPixels : 0;
  if (insideSkinRatio < 0.88) {
    rejectionReasons.push("low_contrast_inside_skin_too_low");
  }
  if (ringSkinRatio < 0.82) rejectionReasons.push("low_contrast_skin_ring_too_low");
  if (ringSupportRatio < 0.72) {
    rejectionReasons.push("low_contrast_hand_support_too_low");
  }
  if (meanGray < 90) rejectionReasons.push("low_contrast_inside_too_dark");
  if (grayStandardDeviation > 15) {
    rejectionReasons.push("low_contrast_inside_too_textured");
  }
  if (meanRingGradient < 36) {
    rejectionReasons.push("low_contrast_boundary_gradient_too_low");
  }
  if (rejectionReasons.length > 0) return { candidate: null, rejectionReasons };

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
  const inverseScale = 1 / scale;
  const componentLength = maxAlong - minAlong + 1;
  const componentWidth = maxAcross - minAcross + 1;
  return {
    candidate: {
      id: `partial-closeup-low-contrast-${thresholdIndex}-${componentIndex}`,
      cx: cx * inverseScale,
      cy: cy * inverseScale,
      angle: normalizeNailAngle(majorAxis - Math.PI / 2),
      length:
        clamp(componentLength * 1.25, maxDimension * 0.055, maxDimension * 0.2) *
        inverseScale,
      width:
        clamp(componentWidth * 1.45, maxDimension * 0.034, maxDimension * 0.15) *
        inverseScale,
      score:
        areaRatio *
        (1 + meanRingGradient / 64) *
        (0.5 * insideSkinRatio + 0.3 * ringSkinRatio + 0.2 * ringSupportRatio),
      confidence: "low",
      source: "partial-closeup",
      suggestedFinger: null,
      warnings: ["partial_closeup_low_contrast_boundary"],
    },
    rejectionReasons: [],
  };
}

function mergeLowContrastCandidates(
  candidates: NailTextureCandidate[],
  maxDimension: number
): NailTextureCandidate[] {
  const merged: NailTextureCandidate[] = [];
  for (const candidate of [...candidates].sort((a, b) => b.score - a.score)) {
    const duplicateIndex = merged.findIndex(
      (existing) =>
        Math.hypot(existing.cx - candidate.cx, existing.cy - candidate.cy) <=
        maxDimension * 0.055
    );
    if (duplicateIndex < 0) {
      merged.push(candidate);
      continue;
    }
    const existing = merged[duplicateIndex];
    if (candidate.length * candidate.width > existing.length * existing.width) {
      merged[duplicateIndex] = candidate;
    }
  }
  return merged;
}

function collectCandidateClusters(
  candidates: NailTextureCandidate[],
  maxDistance: number
): NailTextureCandidate[][] {
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
  });
}

function detectLowContrastBoundaryCandidates(
  analysis: PreparedCloseupImage,
  sourceMaxDimension: number
): LowContrastBoundaryResult {
  const { width, height, grayscale } = analysis;
  const edgeMagnitude = computeSobelMagnitude(grayscale, width, height);
  const evaluations: ComponentEvaluation[] = [];
  let componentCount = 0;
  for (const [thresholdIndex, threshold] of [22, 24].entries()) {
    const edgeMask = new Uint8Array(edgeMagnitude.length);
    for (let index = 0; index < edgeMask.length; index += 1) {
      edgeMask[index] = edgeMagnitude[index] > threshold ? 1 : 0;
    }
    const closedEdgeMask = closeBinaryMask(edgeMask, width, height, 2);
    const interiorMask = new Uint8Array(closedEdgeMask.length);
    for (let index = 0; index < interiorMask.length; index += 1) {
      interiorMask[index] = closedEdgeMask[index] ? 0 : 1;
    }
    const components = collectMaskComponents(interiorMask, analysis);
    componentCount += components.length;
    evaluations.push(
      ...components.map((component, componentIndex) =>
        lowContrastComponentToCandidate(
          component,
          analysis,
          edgeMagnitude,
          thresholdIndex,
          componentIndex
        )
      )
    );
  }

  const rejectionCounts: Partial<Record<PartialCloseupRejectionReason, number>> = {};
  for (const evaluation of evaluations) {
    for (const reason of evaluation.rejectionReasons) {
      rejectionCounts[reason] = (rejectionCounts[reason] ?? 0) + 1;
    }
  }
  const accepted = evaluations
    .map((evaluation) => evaluation.candidate)
    .filter((candidate): candidate is NailTextureCandidate => candidate !== null);
  const merged = mergeLowContrastCandidates(accepted, sourceMaxDimension);
  const clusters = collectCandidateClusters(merged, sourceMaxDimension * 0.21);
  const best = clusters[0] ?? [];
  const competing = clusters[1] ?? [];
  const selected =
    best.length >= 4 && best.length <= 5 && competing.length < 4 ? best : [];
  return {
    candidates: selected,
    componentCount,
    acceptedComponentCount: merged.length,
    rejectionCounts,
  };
}

function selectCoherentCandidateCluster(
  candidates: NailTextureCandidate[],
  maxDistance: number
): NailTextureCandidate[] {
  return collectCandidateClusters(candidates, maxDistance)[0] ?? [];
}

export function assignPartialCloseupCandidateFingers(
  candidates: NailTextureCandidate[],
  handCenterX: number,
  handCenterY: number
): NailTextureCandidate[] {
  if (candidates.length !== 5) {
    return [...candidates]
      .sort((a, b) => a.cx + a.cy * 0.12 - (b.cx + b.cy * 0.12))
      .map((candidate, index) => ({ ...candidate, suggestedFinger: index }));
  }

  const angular = candidates
    .map((candidate) => ({
      candidate,
      angle:
        (Math.atan2(candidate.cy - handCenterY, candidate.cx - handCenterX) +
          Math.PI * 2) %
        (Math.PI * 2),
    }))
    .sort((a, b) => a.angle - b.angle);
  let largestGap = Number.NEGATIVE_INFINITY;
  let start = 0;
  for (let index = 0; index < angular.length; index += 1) {
    const current = angular[index].angle;
    const next =
      angular[(index + 1) % angular.length].angle +
      (index === angular.length - 1 ? Math.PI * 2 : 0);
    const gap = next - current;
    if (gap > largestGap) {
      largestGap = gap;
      start = (index + 1) % angular.length;
    }
  }
  const ordered = angular.map(
    (_, offset) => angular[(start + offset) % angular.length].candidate
  );
  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  const firstNeighborGap = Math.hypot(
    first.cx - ordered[1].cx,
    first.cy - ordered[1].cy
  );
  const lastNeighborGap = Math.hypot(
    last.cx - ordered[ordered.length - 2].cx,
    last.cy - ordered[ordered.length - 2].cy
  );
  const firstThumbScore = first.width * 1.35 + firstNeighborGap * 0.35;
  const lastThumbScore = last.width * 1.35 + lastNeighborGap * 0.35;
  if (lastThumbScore > firstThumbScore) ordered.reverse();
  const thumbScoreMargin =
    Math.abs(firstThumbScore - lastThumbScore) /
    Math.max(firstThumbScore, lastThumbScore, 1);
  if (thumbScoreMargin < 0.02) {
    return ordered.map((candidate) => ({
      ...candidate,
      confidence: "low",
      suggestedFinger: null,
      warnings: [...(candidate.warnings ?? []), "partial_closeup_finger_order_ambiguous"],
    }));
  }
  return ordered.map((candidate, index) => ({ ...candidate, suggestedFinger: index }));
}

/**
 * 保守定位局部近景中的已上色甲面。该路径只作为完整手部几何失败后的候选生成器；
 * 返回 2 至 5 个相互独立、由同一手部肤色邻域支持的大连通区域，否则拒绝自动展示。
 */
export function detectPartialCloseupNails(
  source: ImagePixels
): PartialCloseupDetectionResult {
  if (source.width < 64 || source.height < 64) {
    return {
      candidates: [],
      diagnostics: {
        analysisWidth: source.width,
        analysisHeight: source.height,
        componentCount: 0,
        acceptedComponentCount: 0,
        selectedCandidateCount: 0,
        rejectionCounts: {},
        strategy: null,
        lowContrastComponentCount: 0,
        lowContrastAcceptedComponentCount: 0,
        lowContrastSelectedCandidateCount: 0,
        lowContrastRejectionCounts: {},
      },
    };
  }
  const analysis = prepareCloseupImage(source);
  const components = collectComponents(analysis);
  const evaluations = components.map((component, index) =>
    componentToCandidate(component, analysis, index)
  );
  const rejectionCounts: Partial<Record<PartialCloseupRejectionReason, number>> = {};
  for (const evaluation of evaluations) {
    for (const reason of evaluation.rejectionReasons) {
      rejectionCounts[reason] = (rejectionCounts[reason] ?? 0) + 1;
    }
  }
  const candidates = evaluations
    .map((evaluation) => evaluation.candidate)
    .filter((candidate): candidate is NailTextureCandidate => candidate !== null);
  const coherentCandidates = selectCoherentCandidateCluster(
    candidates,
    Math.max(source.width, source.height) * 0.32
  )
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  let finalCandidates = coherentCandidates.length >= 2 ? coherentCandidates : [];
  let strategy: PartialCloseupDetectionDiagnostics["strategy"] =
    finalCandidates.length >= 2 ? "painted-color" : null;
  let lowContrastComponentCount = 0;
  let lowContrastAcceptedComponentCount = 0;
  let lowContrastRejectionCounts: Partial<
    Record<PartialCloseupRejectionReason, number>
  > = {};
  if (finalCandidates.length < 2) {
    const lowContrast = detectLowContrastBoundaryCandidates(
      analysis,
      Math.max(source.width, source.height)
    );
    finalCandidates = lowContrast.candidates;
    lowContrastComponentCount = lowContrast.componentCount;
    lowContrastAcceptedComponentCount = lowContrast.acceptedComponentCount;
    lowContrastRejectionCounts = lowContrast.rejectionCounts;
    if (finalCandidates.length >= 4) strategy = "low-contrast-boundary";
  }
  const diagnostics: PartialCloseupDetectionDiagnostics = {
    analysisWidth: analysis.width,
    analysisHeight: analysis.height,
    componentCount: components.length,
    acceptedComponentCount: candidates.length,
    selectedCandidateCount: finalCandidates.length,
    rejectionCounts,
    strategy,
    lowContrastComponentCount,
    lowContrastAcceptedComponentCount,
    lowContrastSelectedCandidateCount:
      strategy === "low-contrast-boundary" ? finalCandidates.length : 0,
    lowContrastRejectionCounts,
  };
  if (finalCandidates.length < 2) return { candidates: [], diagnostics };
  const confidence = strategy === "painted-color" && finalCandidates.length >= 4
    ? "medium"
    : "low";
  const ordered = assignPartialCloseupCandidateFingers(
    finalCandidates,
    analysis.handCenterX / analysis.scale,
    analysis.handCenterY / analysis.scale
  );
  return {
    candidates: ordered.map((candidate) => ({
      ...candidate,
      confidence: candidate.suggestedFinger == null ? "low" : confidence,
    })),
    diagnostics,
  };
}

export function detectPartialCloseupNailCandidates(
  source: ImagePixels
): NailTextureCandidate[] {
  return detectPartialCloseupNails(source).candidates;
}
