import path from "node:path";
import type { NailTextureCandidate } from "./types.ts";

export interface NailDebugArtifactPaths {
  output: string;
  candidateMaskOutput: string;
  skinMaskOutput: string;
  recognitionMaskOutput: string;
  debugJsonOutput: string;
  modelOutputDumpPath: string;
}

function sanitizeSegment(value: string): string {
  return value.trim().replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-");
}

export function buildNailDebugArtifactPaths(args: {
  inputPath: string;
  outputDir?: string;
  prefix?: string;
}): NailDebugArtifactPaths {
  const absoluteInput = path.resolve(args.inputPath);
  const directory = path.resolve(args.outputDir ?? path.dirname(absoluteInput));
  const inputStem = path.basename(absoluteInput, path.extname(absoluteInput));
  const prefix = sanitizeSegment(args.prefix ?? "nail");
  const baseName = `${prefix}-${sanitizeSegment(inputStem)}`;

  return {
    output: path.join(directory, `${baseName}-detection-debug.png`),
    candidateMaskOutput: path.join(directory, `${baseName}-candidate-mask.png`),
    skinMaskOutput: path.join(directory, `${baseName}-skin-mask.png`),
    recognitionMaskOutput: path.join(directory, `${baseName}-recognition-mask-overlay.png`),
    debugJsonOutput: path.join(directory, `${baseName}-detection-debug.json`),
    modelOutputDumpPath: path.join(directory, `${baseName}-model-output-dump.json`),
  };
}
export interface NailRecognitionMaskOverlayResult {
  width: number;
  height: number;
  data: Uint8Array;
  maskCandidateCount: number;
  coveredPixels: number;
}

const MASK_COLORS: Array<[number, number, number]> = [
  [0, 255, 136],
  [255, 190, 0],
  [0, 180, 255],
  [255, 80, 160],
  [170, 120, 255],
];

export function buildNailRecognitionMaskOverlay(args: {
  width: number;
  height: number;
  candidates: Pick<NailTextureCandidate, "mask">[];
  preprocess?: {
    inputSize: number;
    originalWidth: number;
    originalHeight: number;
    scaleX: number;
    scaleY: number;
  } | null;
}): NailRecognitionMaskOverlayResult {
  const width = Math.max(1, Math.round(args.width));
  const height = Math.max(1, Math.round(args.height));
  const data = new Uint8Array(width * height * 4);
  let maskCandidateCount = 0;
  let coveredPixels = 0;

  for (let candidateIndex = 0; candidateIndex < args.candidates.length; candidateIndex++) {
    const mask = args.candidates[candidateIndex]?.mask;
    if (!mask || mask.width <= 0 || mask.height <= 0) continue;
    maskCandidateCount++;
    const color = MASK_COLORS[candidateIndex % MASK_COLORS.length];
    const scaleX = args.preprocess?.scaleX ?? width / Math.max(1, mask.width * mask.scale);
    const scaleY = args.preprocess?.scaleY ?? height / Math.max(1, mask.height * mask.scale);

    for (let y = 0; y < mask.height; y++) {
      for (let x = 0; x < mask.width; x++) {
        const maskIndex = y * mask.width + x;
        if (!mask.data[maskIndex]) continue;
        const modelX = mask.originX + (x + 0.5) * mask.scale;
        const modelY = mask.originY + (y + 0.5) * mask.scale;
        const outputX = Math.min(width - 1, Math.max(0, Math.floor(modelX * scaleX)));
        const outputY = Math.min(height - 1, Math.max(0, Math.floor(modelY * scaleY)));
        const outputIndex = (outputY * width + outputX) * 4;
        if (data[outputIndex + 3] === 0) coveredPixels++;
        data[outputIndex] = color[0];
        data[outputIndex + 1] = color[1];
        data[outputIndex + 2] = color[2];
        data[outputIndex + 3] = 150;
      }
    }
  }

  return { width, height, data, maskCandidateCount, coveredPixels };
}
