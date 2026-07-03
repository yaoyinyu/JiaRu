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
}

interface CandidateAngleEvidence {
  reliable: boolean;
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
    const [, rows, cols] = dims;
    const output: number[][] = [];
    for (let row = 0; row < rows; row++) {
      output.push(values.slice(row * cols, (row + 1) * cols));
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
  maskThreshold: number
): NailMask | undefined {
  const shape = decodePrototypeShape(prototypeTensor);
  if (!shape || coefficients.length === 0) return undefined;

  const { channels, height, width } = shape;
  const source = Array.from(prototypeTensor.data, (value) => Number(value) || 0);
  const binary = new Uint8Array(width * height);
  const scale = preprocess.inputSize / width;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let activation = 0;
      for (let channel = 0; channel < channels; channel++) {
        const coefficient = coefficients[channel] ?? 0;
        if (coefficient === 0) continue;
        const offset = channel * width * height + y * width + x;
        activation += coefficient * source[offset];
      }
      binary[y * width + x] = sigmoid(activation) >= maskThreshold ? 1 : 0;
    }
  }

  return {
    width,
    height,
    data: binary,
    originX: 0,
    originY: 0,
    scale,
  };
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

  const scoreThreshold = options.scoreThreshold ?? 0.35;
  const maxCandidates = options.maxCandidates ?? 10;
  const maskThreshold = options.maskThreshold ?? 0.5;
  const rows = flattenDetectionRows(detectionTensor);

  const angleEvidences: CandidateAngleEvidence[] = [];
  const candidates = rows
    .filter((row) => row.length >= 5)
    .map((row, index) => {
      const [cx, cy, width, length, score] = row;
      const coefficients = row.slice(5);
      const mask =
        prototypeTensor && coefficients.length > 0
          ? decodeCandidateMask(prototypeTensor, coefficients, preprocess, maskThreshold)
          : undefined;
      const estimatedAngle = mask ? estimateMaskPrincipalAngle(mask) : null;
      const candidate = {
        id: `model-${index + 1}`,
        cx: clamp(cx * preprocess.scaleX, 0, preprocess.originalWidth),
        cy: clamp(cy * preprocess.scaleY, 0, preprocess.originalHeight),
        width: clamp(width * preprocess.scaleX, 1, preprocess.originalWidth),
        length: clamp(length * preprocess.scaleY, 1, preprocess.originalHeight),
        score,
        mask,
        angle: estimatedAngle ?? 0,
      };
      angleEvidences.push({
        reliable: isReliableOrientationCandidate(candidate, estimatedAngle != null),
      });
      return candidate;
    })
    .filter((row) => row.score >= scoreThreshold);

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
    }
  );
  const evidenceById = new Map(
    candidates.map((candidate, index) => [candidate.id, angleEvidences[index] as CandidateAngleEvidence])
  );
  const stabilized = stabilizeNailTextureCandidateAngles(
    ranked,
    ranked.map((candidate) => evidenceById.get(candidate.id) ?? { angle: candidate.angle, reliable: false })
  );

  const suggestedFingers = inferSuggestedFingers(stabilized.length);
  return stabilized.map((candidate, index) => ({
    ...candidate,
    id: `model-${index + 1}`,
    suggestedFinger: suggestedFingers[index] ?? null,
  }));
}
