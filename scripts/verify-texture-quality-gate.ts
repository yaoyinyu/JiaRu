import path from "node:path";
import process from "node:process";
import { readdir, readFile, writeFile } from "node:fs/promises";

interface CliOptions {
  annotationDirPath: string;
  outputPath?: string;
  minUsableRate: number;
  maxContaminationRate: number;
  maxHighlightRatioForUsable: number;
  maxHighlightPixelsForUsable: number;
}

interface AnnotationDebugLike {
  warnings?: unknown;
  extractionQualityOk?: unknown;
  extractionQualityWarnings?: unknown;
  highlightPixels?: unknown;
  repairedPixels?: unknown;
  highlightRatio?: unknown;
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    minUsableRate: 0.85,
    maxContaminationRate: 0.1,
    maxHighlightRatioForUsable: 0.12,
    maxHighlightPixelsForUsable: 8,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--annotation-dir") options.annotationDirPath = path.resolve(argv[++index] ?? "");
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index] ?? "");
    else if (arg === "--min-usable-rate") options.minUsableRate = Number(argv[++index] ?? "");
    else if (arg === "--max-contamination-rate") options.maxContaminationRate = Number(argv[++index] ?? "");
    else if (arg === "--max-highlight-ratio-for-usable") options.maxHighlightRatioForUsable = Number(argv[++index] ?? "");
    else if (arg === "--max-highlight-pixels-for-usable") options.maxHighlightPixelsForUsable = Number(argv[++index] ?? "");
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/verify-texture-quality-gate.ts --annotation-dir <dir> [--output <report.json>] [--min-usable-rate 0.85] [--max-contamination-rate 0.1] [--max-highlight-ratio-for-usable 0.12] [--max-highlight-pixels-for-usable 8]"
      );
    }
  }

  if (!options.annotationDirPath) {
    throw new Error("annotation dir is required via --annotation-dir");
  }

  return options as CliOptions;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordCount(target: Record<string, number>, key: string) {
  target[key] = (target[key] ?? 0) + 1;
}

function roundRate(value: number | null): number | null {
  return value == null ? null : Number(value.toFixed(4));
}

async function listJsonFiles(dirPath: string): Promise<string[]> {
  const entries = await readdir(dirPath, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(dirPath, entry.name))
    .sort();
}

function isDirectlyUsable(
  debug: AnnotationDebugLike,
  options: CliOptions
): boolean {
  const warnings = toStringArray(debug.warnings);
  const qualityWarnings = toStringArray(debug.extractionQualityWarnings);
  const qualityOk = debug.extractionQualityOk === false ? false : true;
  const highlightRatio = toNumber(debug.highlightRatio) ?? 0;
  const highlightPixels = toNumber(debug.highlightPixels) ?? 0;

  return (
    warnings.length === 0 &&
    qualityWarnings.length === 0 &&
    qualityOk &&
    highlightRatio < options.maxHighlightRatioForUsable &&
    highlightPixels < options.maxHighlightPixelsForUsable
  );
}

function isContaminated(debug: AnnotationDebugLike): boolean {
  const warnings = new Set([
    ...toStringArray(debug.warnings),
    ...toStringArray(debug.extractionQualityWarnings),
  ]);
  return warnings.has("dirty_mask_crop");
}

const options = parseArgs(process.argv.slice(2));
const files = await listJsonFiles(options.annotationDirPath);

const qualityWarningCounts: Record<string, number> = {};
const candidateWarningCounts: Record<string, number> = {};
let documents = 0;
let candidates = 0;
let candidatesWithDebug = 0;
let directlyUsableCandidates = 0;
let contaminatedCandidates = 0;

for (const filePath of files) {
  const document = JSON.parse(await readFile(filePath, "utf8")) as {
    annotations?: Array<{ attributes?: { debug?: AnnotationDebugLike } }>;
  };
  documents++;
  for (const annotation of document.annotations ?? []) {
    candidates++;
    const debug = annotation.attributes?.debug;
    if (!debug || typeof debug !== "object") continue;
    candidatesWithDebug++;

    for (const warning of toStringArray(debug.warnings)) {
      recordCount(candidateWarningCounts, warning);
    }
    for (const warning of toStringArray(debug.extractionQualityWarnings)) {
      recordCount(qualityWarningCounts, warning);
    }

    if (isDirectlyUsable(debug, options)) {
      directlyUsableCandidates++;
    }
    if (isContaminated(debug)) {
      contaminatedCandidates++;
    }
  }
}

const directlyUsableRate = candidatesWithDebug > 0 ? directlyUsableCandidates / candidatesWithDebug : null;
const contaminationRate = candidatesWithDebug > 0 ? contaminatedCandidates / candidatesWithDebug : null;

const warnings: string[] = [];
if (documents === 0) warnings.push("annotation dir does not contain any json documents");
if (candidates === 0) warnings.push("annotation documents do not contain any nail candidates");
if (candidatesWithDebug === 0) warnings.push("annotation candidates do not contain debug extraction diagnostics");
if (directlyUsableRate != null && directlyUsableRate < options.minUsableRate) {
  warnings.push(
    `directly usable rate ${roundRate(directlyUsableRate)} is below target ${options.minUsableRate}`
  );
}
if (contaminationRate != null && contaminationRate >= options.maxContaminationRate) {
  warnings.push(
    `contamination rate ${roundRate(contaminationRate)} is not below target ${options.maxContaminationRate}`
  );
}

const nextSteps: string[] = [];
if (directlyUsableRate != null && directlyUsableRate < options.minUsableRate) {
  nextSteps.push("优先复核低质量候选与提取后 diagnostics，减少需要人工调整的纹理样本。");
}
if (contaminationRate != null && contaminationRate >= options.maxContaminationRate) {
  nextSteps.push("优先处理 dirty_mask_crop 类问题，降低皮肤或背景污染进入最终纹理的比例。");
}
if (candidatesWithDebug === 0) {
  nextSteps.push("先继续积累带 extraction diagnostics 的 debug annotation 样本，再重跑该门禁。");
}
if (nextSteps.length === 0) {
  nextSteps.push("纹理可用率与污染率门禁当前通过，可以继续扩大真实样本审计范围。");
}

const summary = {
  ok:
    candidatesWithDebug > 0 &&
    directlyUsableRate != null &&
    directlyUsableRate >= options.minUsableRate &&
    contaminationRate != null &&
    contaminationRate < options.maxContaminationRate,
  annotationDirPath: options.annotationDirPath,
  thresholds: {
    minUsableRate: options.minUsableRate,
    maxContaminationRate: options.maxContaminationRate,
    maxHighlightRatioForUsable: options.maxHighlightRatioForUsable,
    maxHighlightPixelsForUsable: options.maxHighlightPixelsForUsable,
  },
  totals: {
    documents,
    candidates,
    candidatesWithDebug,
    directlyUsableCandidates,
    contaminatedCandidates,
  },
  rates: {
    directlyUsableRate: roundRate(directlyUsableRate),
    contaminationRate: roundRate(contaminationRate),
  },
  warningBreakdown: {
    candidateWarnings: candidateWarningCounts,
    qualityWarnings: qualityWarningCounts,
  },
  warnings,
  nextSteps,
};

if (options.outputPath) {
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
}

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) {
  process.exitCode = 1;
}
