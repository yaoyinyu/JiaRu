import type {
  NailMask,
  NailTextureCandidate,
  NailTextureCandidateConfidence,
} from "./types.ts";
import type { NailTexturePreprocessResult } from "./preprocess.ts";
import { inferSuggestedFingers } from "./finger-assignment.ts";
import { rankNailTextureCandidates } from "./quality.ts";

export interface ModelTensorLike {
  data: ArrayLike<number>;
  dims?: readonly number[];
}

export interface PostprocessModelOutputsOptions {
  maxCandidates?: number;
  scoreThreshold?: number;
  maskThreshold?: number;
  nmsThreshold?: number;
  preNmsTopK?: number;
  includeLowConfidenceCandidates?: boolean;
}

interface CandidateAngleEvidence {
  reliable: boolean;
}

interface RawDetectionCandidate {
  id: string;
  cx: number;
  cy: number;
  width: number;
  length: number;
  score: number;
  coefficients: number[];
}

function scoreToConfidence(score: number): NailTextureCandidateConfidence {
  if (score >= 0.75) return "high";
  if (score >= 0.5) return "medium";
  return "low";
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeHalfTurnAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI / 2) result -= Math.PI;
  while (result <= -Math.PI / 2) result += Math.PI;
  return result;
}

function flattenDetectionRows(tensor: ModelTensorLike): number[][] {
  const values = Array.from(tensor.data, (value) => Number(value) || 0);
  const dims = tensor.dims ? Array.from(tensor.dims) : [];

  if (dims.length === 3 && dims[0] === 1) {
    const [, first, second] = dims;
    const output: number[][] = [];
    const looksLikeAttributeCount = (value: number) => value >= 5 && value <= 256;
    const channelMajor =
      looksLikeAttributeCount(first) &&
      (!looksLikeAttributeCount(second) || second > first);

    if (channelMajor) {
      for (let prediction = 0; prediction < second; prediction++) {
        const row: number[] = [];
        for (let attribute = 0; attribute < first; attribute++) {
          row.push(values[attribute * second + prediction] ?? 0);
        }
        output.push(row);
      }
      return output;
    }

    for (let row = 0; row < first; row++) {
      output.push(values.slice(row * second, (row + 1) * second));
    }
    return output;
  }

  if (dims.length === 2) {
    const [rows, cols] = dims;
    const output: number[][] = [];
    for (let row = 0; row < rows; row++) {
      output.push(values.slice(row * cols, (row + 1) * cols));
    }
    return output;
  }

  const fallbackCols = values.length % 6 === 0 ? 6 : values.length % 5 === 0 ? 5 : 0;
  if (fallbackCols > 0) {
    const output: number[][] = [];
    for (let offset = 0; offset < values.length; offset += fallbackCols) {
      output.push(values.slice(offset, offset + fallbackCols));
    }
    return output;
  }

  return [];
}

function sigmoid(value: number): number {
  return 1 / (1 + Math.exp(-value));
}

function tensorVolume(dims: readonly number[] | undefined): number {
  return dims?.reduce((product, dim) => product * dim, 1) ?? 0;
}

function isPrototypeTensor(tensor: ModelTensorLike): boolean {
  const dims = tensor.dims ? Array.from(tensor.dims) : [];
  return dims.length === 4 || (dims.length === 3 && dims[0] > 1);
}

function selectDetectionTensor(outputs: Record<string, ModelTensorLike>): ModelTensorLike | null {
  const tensors = Object.values(outputs);
  if (tensors.length === 0) return null;
  return (
    tensors.find((tensor) => {
      const dims = tensor.dims ? Array.from(tensor.dims) : [];
      return dims.length === 2 || (dims.length === 3 && dims[0] === 1);
    }) ?? tensors[0]
  );
}

function selectPrototypeTensor(
  outputs: Record<string, ModelTensorLike>,
  detectionTensor: ModelTensorLike | null
): ModelTensorLike | null {
  const tensors = Object.values(outputs)
    .filter((tensor) => tensor !== detectionTensor)
    .filter((tensor) => isPrototypeTensor(tensor))
    .sort((a, b) => tensorVolume(b.dims) - tensorVolume(a.dims));
  return tensors[0] ?? null;
}

function decodePrototypeShape(
  tensor: ModelTensorLike
): { channels: number; height: number; width: number } | null {
  const dims = tensor.dims ? Array.from(tensor.dims) : [];
  if (dims.length === 4 && dims[0] === 1) {
    const [, channels, height, width] = dims;
    return { channels, height, width };
  }
  if (dims.length === 3) {
    const [channels, height, width] = dims;
    return { channels, height, width };
  }
  return null;
}

function decodeCandidateMask(
  prototypeTensor: ModelTensorLike,
  coefficients: number[],
  preprocess: NailTexturePreprocessResult,
  maskThreshold: number,
  modelBox: Pick<RawDetectionCandidate, "cx" | "cy" | "width" | "length">
): NailMask | undefined {
  const shape = decodePrototypeShape(prototypeTensor);
  if (!shape || coefficients.length === 0) return undefined;

  const { channels, height, width } = shape;
  const source = prototypeTensor.data;
  const padLeft = preprocess.padLeft ?? 0;
  const padTop = preprocess.padTop ?? 0;
  const resizedWidth = preprocess.resizedWidth ?? preprocess.inputSize;
  const resizedHeight = preprocess.resizedHeight ?? preprocess.inputSize;
  const contentMinX = clamp(Math.floor((padLeft / preprocess.inputSize) * width), 0, width - 1);
  const contentMinY = clamp(Math.floor((padTop / preprocess.inputSize) * height), 0, height - 1);
  const contentMaxX = clamp(
    Math.ceil(((padLeft + resizedWidth) / preprocess.inputSize) * width),
    contentMinX + 1,
    width
  );
  const contentMaxY = clamp(
    Math.ceil(((padTop + resizedHeight) / preprocess.inputSize) * height),
    contentMinY + 1,
    height
  );
  const outputWidth = contentMaxX - contentMinX;
  const outputHeight = contentMaxY - contentMinY;
  const binary = new Uint8Array(outputWidth * outputHeight);

  const boxMinX = clamp(
    Math.floor(((modelBox.cx - modelBox.width / 2) / preprocess.inputSize) * width),
    contentMinX,
    contentMaxX - 1
  );
  const boxMaxX = clamp(
    Math.ceil(((modelBox.cx + modelBox.width / 2) / preprocess.inputSize) * width),
    boxMinX + 1,
    contentMaxX
  );
  const boxMinY = clamp(
    Math.floor(((modelBox.cy - modelBox.length / 2) / preprocess.inputSize) * height),
    contentMinY,
    contentMaxY - 1
  );
  const boxMaxY = clamp(
    Math.ceil(((modelBox.cy + modelBox.length / 2) / preprocess.inputSize) * height),
    boxMinY + 1,
    contentMaxY
  );

  for (let y = boxMinY; y < boxMaxY; y++) {
    for (let x = boxMinX; x < boxMaxX; x++) {
      let activation = 0;
      for (let channel = 0; channel < channels; channel++) {
        const coefficient = coefficients[channel] ?? 0;
        if (coefficient === 0) continue;
        const offset = channel * width * height + y * width + x;
        activation += coefficient * (Number(source[offset]) || 0);
      }
      const outputX = x - contentMinX;
      const outputY = y - contentMinY;
      binary[outputY * outputWidth + outputX] =
        sigmoid(activation) >= maskThreshold ? 1 : 0;
    }
  }

  return {
    width: outputWidth,
    height: outputHeight,
    data: binary,
    originX: 0,
    originY: 0,
    scale: Math.max(
      preprocess.originalWidth / outputWidth,
      preprocess.originalHeight / outputHeight
    ),
  };
}

function rawCandidateIou(left: RawDetectionCandidate, right: RawDetectionCandidate): number {
  const leftMinX = left.cx - left.width / 2;
  const leftMaxX = left.cx + left.width / 2;
  const leftMinY = left.cy - left.length / 2;
  const leftMaxY = left.cy + left.length / 2;
  const rightMinX = right.cx - right.width / 2;
  const rightMaxX = right.cx + right.width / 2;
  const rightMinY = right.cy - right.length / 2;
  const rightMaxY = right.cy + right.length / 2;
  const intersectionWidth = Math.max(0, Math.min(leftMaxX, rightMaxX) - Math.max(leftMinX, rightMinX));
  const intersectionHeight = Math.max(0, Math.min(leftMaxY, rightMaxY) - Math.max(leftMinY, rightMinY));
  const intersection = intersectionWidth * intersectionHeight;
  if (intersection <= 0) return 0;
  const leftArea = Math.max(1, left.width * left.length);
  const rightArea = Math.max(1, right.width * right.length);
  return intersection / (leftArea + rightArea - intersection);
}

function suppressRawCandidates(
  candidates: RawDetectionCandidate[],
  overlapThreshold: number,
  limit: number
): RawDetectionCandidate[] {
  const kept: RawDetectionCandidate[] = [];
  for (const candidate of candidates) {
    if (kept.some((selected) => rawCandidateIou(candidate, selected) >= overlapThreshold)) {
      continue;
    }
    kept.push(candidate);
    if (kept.length >= limit) break;
  }
  return kept;
}

function modelCoordinateToOriginal(
  value: number,
  padding: number,
  preprocess: NailTexturePreprocessResult,
  legacyInverseScale: number,
  max: number
): number {
  const resizeScale = preprocess.resizeScale ?? 1 / legacyInverseScale;
  return clamp((value - padding) / resizeScale, 0, max);
}

function modelLengthToOriginal(
  value: number,
  preprocess: NailTexturePreprocessResult,
  legacyInverseScale: number,
  max: number
): number {
  const resizeScale = preprocess.resizeScale ?? 1 / legacyInverseScale;
  return clamp(value / resizeScale, 1, max);
}

export function estimateMaskPrincipalAngle(mask: NailMask): number | null {
  let total = 0;
  let meanX = 0;
  let meanY = 0;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      total++;
      meanX += x;
      meanY += y;
    }
  }

  if (total < 4) return null;
  meanX /= total;
  meanY /= total;

  let mu20 = 0;
  let mu02 = 0;
  let mu11 = 0;

  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!mask.data[y * mask.width + x]) continue;
      const dx = x - meanX;
      const dy = y - meanY;
      mu20 += dx * dx;
      mu02 += dy * dy;
      mu11 += dx * dy;
    }
  }

  const trace = mu20 + mu02;
  const delta = Math.sqrt((mu20 - mu02) ** 2 + 4 * mu11 * mu11);
  const major = (trace + delta) / 2;
  const minor = (trace - delta) / 2;
  if (major <= 0) return null;
  const axisRatio = minor <= 1e-6 ? Number.POSITIVE_INFINITY : major / minor;
  if (axisRatio < 1.1) return null;

  const axisAngle = 0.5 * Math.atan2(2 * mu11, mu20 - mu02);
  return normalizeHalfTurnAngle(axisAngle + Math.PI / 2);
}

function candidateAspectRatio(candidate: Pick<NailTextureCandidate, "width" | "length">): number {
  const shorter = Math.min(candidate.width, candidate.length);
  const longer = Math.max(candidate.width, candidate.length);
  return shorter <= 0 ? Number.POSITIVE_INFINITY : longer / shorter;
}

function isReliableOrientationCandidate(
  candidate: Pick<NailTextureCandidate, "width" | "length">,
  angleWasEstimatedFromMask: boolean
): boolean {
  return angleWasEstimatedFromMask && candidateAspectRatio(candidate) >= 1.2;
}

function averageHalfTurnAngle(angles: number[]): number | null {
  if (angles.length === 0) return null;

  let x = 0;
  let y = 0;
  for (const angle of angles) {
    x += Math.cos(angle * 2);
    y += Math.sin(angle * 2);
  }

  if (Math.abs(x) < 1e-6 && Math.abs(y) < 1e-6) return null;
  return normalizeHalfTurnAngle(0.5 * Math.atan2(y, x));
}

export function stabilizeNailTextureCandidateAngles(
  candidates: NailTextureCandidate[],
  evidences?: CandidateAngleEvidence[]
): NailTextureCandidate[] {
  if (candidates.length === 0) return [];

  const reliableAngles = candidates
    .map((candidate, index) => ({
      candidate,
      evidence: evidences?.[index],
    }))
    .filter((item) => item.evidence?.reliable)
    .map((item) => item.candidate.angle);

  const sharedAngle = averageHalfTurnAngle(reliableAngles);

  return candidates.map((candidate, index) => {
    const evidence = evidences?.[index];
    if (evidence?.reliable) return candidate;

    const stabilizedAngle = sharedAngle ?? 0;
    const warning = sharedAngle == null ? "angle_defaulted_vertical" : "angle_stabilized_from_group";
    const warnings = candidate.warnings?.includes(warning)
      ? candidate.warnings
      : [...(candidate.warnings ?? []), warning];

    return {
      ...candidate,
      angle: stabilizedAngle,
      warnings,
    };
  });
}

export function postprocessNailTextureDetections(
  outputs: Record<string, ModelTensorLike>,
  preprocess: NailTexturePreprocessResult,
  options: PostprocessModelOutputsOptions = {}
): NailTextureCandidate[] {
  const detectionTensor = selectDetectionTensor(outputs);
  if (!detectionTensor) return [];
  const prototypeTensor = selectPrototypeTensor(outputs, detectionTensor);

  const scoreThreshold = options.includeLowConfidenceCandidates
    ? 0
    : options.scoreThreshold ?? 0.35;
  const maxCandidates = options.maxCandidates ?? 10;
  const maskThreshold = options.maskThreshold ?? 0.5;
  const nmsThreshold = options.nmsThreshold ?? 0.55;
  const preNmsTopK = Math.max(maxCandidates, options.preNmsTopK ?? 100);
  const rows = flattenDetectionRows(detectionTensor);

  const rawCandidates = rows
    .filter((row) => row.length >= 5)
    .map((row, index) => {
      const [cx, cy, width, length, score] = row;
      return {
        id: `model-raw-${index + 1}`,
        cx,
        cy,
        width,
        length,
        score,
        coefficients: row.slice(5),
      } satisfies RawDetectionCandidate;
    })
    .filter((candidate) =>
      Number.isFinite(candidate.cx) &&
      Number.isFinite(candidate.cy) &&
      Number.isFinite(candidate.width) &&
      Number.isFinite(candidate.length) &&
      Number.isFinite(candidate.score) &&
      candidate.width > 0 &&
      candidate.length > 0 &&
      candidate.score >= scoreThreshold
    )
    .sort((left, right) => right.score - left.score)
    .slice(0, preNmsTopK);

  const selectedRawCandidates = suppressRawCandidates(
    rawCandidates,
    nmsThreshold,
    Math.max(maxCandidates, maxCandidates * 2)
  );

  const angleEvidenceById = new Map<string, CandidateAngleEvidence>();
  const candidates = selectedRawCandidates.map((raw, index) => {
      const mask =
        prototypeTensor && raw.coefficients.length > 0
          ? decodeCandidateMask(
              prototypeTensor,
              raw.coefficients,
              preprocess,
              maskThreshold,
              raw
            )
          : undefined;
      const estimatedAngle = mask ? estimateMaskPrincipalAngle(mask) : null;
      const candidate = {
        id: `model-${index + 1}`,
        cx: modelCoordinateToOriginal(
          raw.cx,
          preprocess.padLeft ?? 0,
          preprocess,
          preprocess.scaleX,
          preprocess.originalWidth
        ),
        cy: modelCoordinateToOriginal(
          raw.cy,
          preprocess.padTop ?? 0,
          preprocess,
          preprocess.scaleY,
          preprocess.originalHeight
        ),
        width: modelLengthToOriginal(
          raw.width,
          preprocess,
          preprocess.scaleX,
          preprocess.originalWidth
        ),
        length: modelLengthToOriginal(
          raw.length,
          preprocess,
          preprocess.scaleY,
          preprocess.originalHeight
        ),
        score: raw.score,
        mask,
        angle: estimatedAngle ?? 0,
      };
      angleEvidenceById.set(candidate.id, {
        reliable: isReliableOrientationCandidate(candidate, estimatedAngle != null),
      });
      return candidate;
    });

  const ranked = rankNailTextureCandidates(
    candidates.map((candidate) => ({
      id: candidate.id,
      cx: candidate.cx,
      cy: candidate.cy,
      length: candidate.length,
      width: candidate.width,
      angle: candidate.angle,
      score: candidate.score,
      confidence: scoreToConfidence(candidate.score),
      source: "model" as const,
      mask: candidate.mask,
      suggestedFinger: null,
    })),
    {
      imageWidth: preprocess.originalWidth,
      imageHeight: preprocess.originalHeight,
      maxCandidates,
      includeLowConfidenceCandidates: options.includeLowConfidenceCandidates,
      scoreThreshold,
    }
  );
  const stabilized = stabilizeNailTextureCandidateAngles(
    ranked,
    ranked.map((candidate) => angleEvidenceById.get(candidate.id) ?? { reliable: false })
  );

  const suggestedFingers = inferSuggestedFingers(stabilized.length);
  return stabilized.map((candidate, index) => ({
    ...candidate,
    id: `model-${index + 1}`,
    suggestedFinger: suggestedFingers[index] ?? null,
  }));
}
