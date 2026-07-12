import path from "node:path";
import { createHash } from "node:crypto";

export interface NailDebugArtifactPaths {
  output: string;
  candidateMaskOutput: string;
  skinMaskOutput: string;
  debugJsonOutput: string;
  modelOutputDumpPath: string;
}

function sanitizeSegment(value: string, maxLength = 40): string {
  const sanitized = value.trim().replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-");
  const digest = createHash("sha256").update(value).digest("hex").slice(0, 12);
  if (!sanitized.replace(/[._-]/g, "")) return `item-${digest}`;
  if (sanitized.length <= maxLength) return sanitized;
  return `${sanitized.slice(0, maxLength - digest.length - 1)}-${digest}`;
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
    debugJsonOutput: path.join(directory, `${baseName}-detection-debug.json`),
    modelOutputDumpPath: path.join(directory, `${baseName}-model-output-dump.json`),
  };
}
