import path from "node:path";
import process from "node:process";
import { readdir, readFile, writeFile } from "node:fs/promises";

interface CliOptions {
  annotationDirPath: string;
  outputPath?: string;
  evidenceScope: "local-debug" | "release-test-split";
  minUsableRate: number;
  maxContaminationRate: number;
  minDocuments: number;
  minCandidatesWithDebug: number;
  minCandidatesWithPolygon: number;
  maxHighlightRatioForUsable: number;
  maxHighlightPixelsForUsable: number;
  maxRoughRectangleRate: number;
  minPolygonPointsForShapePreserved: number;
  maxPolygonBoundsFillRatio: number;
}

interface AnnotationDebugLike {
  warnings?: unknown;
  extractionQualityOk?: unknown;
  extractionQualityWarnings?: unknown;
  highlightPixels?: unknown;
  repairedPixels?: unknown;
  highlightRatio?: unknown;
}

interface PointLike {
  x?: unknown;
  y?: unknown;
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    evidenceScope: "local-debug",
    minUsableRate: 0.85,
    maxContaminationRate: 0.1,
    minDocuments: 1,
    minCandidatesWithDebug: 1,
    minCandidatesWithPolygon: 1,
    maxHighlightRatioForUsable: 0.12,
    maxHighlightPixelsForUsable: 8,
    maxRoughRectangleRate: 0.15,
    minPolygonPointsForShapePreserved: 5,
    maxPolygonBoundsFillRatio: 0.96,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--annotation-dir") options.annotationDirPath = path.resolve(argv[++index] ?? "");
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index] ?? "");
    else if (arg === "--evidence-scope") {
      const scope = argv[++index];
      if (scope !== "local-debug" && scope !== "release-test-split") {
        throw new Error("--evidence-scope must be local-debug or release-test-split");
      }
      options.evidenceScope = scope;
    }
    else if (arg === "--min-usable-rate") options.minUsableRate = Number(argv[++index] ?? "");
    else if (arg === "--max-contamination-rate") options.maxContaminationRate = Number(argv[++index] ?? "");
    else if (arg === "--min-documents") options.minDocuments = Number(argv[++index] ?? "");
    else if (arg === "--min-candidates-with-debug") options.minCandidatesWithDebug = Number(argv[++index] ?? "");
    else if (arg === "--min-candidates-with-polygon") options.minCandidatesWithPolygon = Number(argv[++index] ?? "");
    else if (arg === "--max-highlight-ratio-for-usable") options.maxHighlightRatioForUsable = Number(argv[++index] ?? "");
    else if (arg === "--max-highlight-pixels-for-usable") options.maxHighlightPixelsForUsable = Number(argv[++index] ?? "");
    else if (arg === "--max-rough-rectangle-rate") options.maxRoughRectangleRate = Number(argv[++index] ?? "");
    else if (arg === "--min-polygon-points-for-shape-preserved") options.minPolygonPointsForShapePreserved = Number(argv[++index] ?? "");
    else if (arg === "--max-polygon-bounds-fill-ratio") options.maxPolygonBoundsFillRatio = Number(argv[++index] ?? "");
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/verify-texture-quality-gate.ts --annotation-dir <dir> [--output <report.json>] [--evidence-scope local-debug|release-test-split] [--min-documents 1] [--min-candidates-with-debug 1] [--min-candidates-with-polygon 1] [--min-usable-rate 0.85] [--max-contamination-rate 0.1] [--max-highlight-ratio-for-usable 0.12] [--max-highlight-pixels-for-usable 8] [--max-rough-rectangle-rate 0.15]"
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

function polygonArea(points: Array<{ x: number; y: number }>): number {
  let sum = 0;
  for (let index = 0; index < points.length; index++) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    sum += current.x * next.y - next.x * current.y;
  }
  return Math.abs(sum / 2);
}

function normalizePolygon(points: PointLike[] | undefined): Array<{ x: number; y: number }> {
  if (!Array.isArray(points)) return [];
  return points.flatMap((point) => {
    const x = toNumber(point.x);
    const y = toNumber(point.y);
    return x == null || y == null ? [] : [{ x, y }];
  });
}

function polygonBoundsFillRatio(points: Array<{ x: number; y: number }>): number | null {
  if (points.length < 3) return null;
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const boundsArea = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
  if (boundsArea <= 0) return null;
  return polygonArea(points) / boundsArea;
}

function isRoughRectanglePolygon(points: Array<{ x: number; y: number }>, options: CliOptions): boolean {
  const fillRatio = polygonBoundsFillRatio(points);
  return (
    points.length < options.minPolygonPointsForShapePreserved ||
    (fillRatio != null && fillRatio >= options.maxPolygonBoundsFillRatio)
  );
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
let candidatesWithPolygon = 0;
let roughRectangleCandidates = 0;

for (const filePath of files) {
  const document = JSON.parse(await readFile(filePath, "utf8")) as {
    annotations?: Array<{ polygon?: PointLike[]; attributes?: { debug?: AnnotationDebugLike } }>;
  };
  documents++;
  for (const annotation of document.annotations ?? []) {
    candidates++;

    const polygon = normalizePolygon(annotation.polygon);
    if (polygon.length > 0) {
      candidatesWithPolygon++;
      if (isRoughRectanglePolygon(polygon, options)) {
        roughRectangleCandidates++;
      }
    }

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
const roughRectangleRate = candidatesWithPolygon > 0 ? roughRectangleCandidates / candidatesWithPolygon : null;
const evidence = {
  scope: options.evidenceScope,
  documentsOk: documents >= options.minDocuments,
  candidatesWithDebugOk: candidatesWithDebug >= options.minCandidatesWithDebug,
  candidatesWithPolygonOk: candidatesWithPolygon >= options.minCandidatesWithPolygon,
  representativeTestSplit: options.evidenceScope === "release-test-split",
  minDocuments: options.minDocuments,
  minCandidatesWithDebug: options.minCandidatesWithDebug,
  minCandidatesWithPolygon: options.minCandidatesWithPolygon,
};
const evidenceOk =
  evidence.documentsOk &&
  evidence.candidatesWithDebugOk &&
  evidence.candidatesWithPolygonOk;

const warnings: string[] = [];
if (documents === 0) warnings.push("annotation dir does not contain any json documents");
if (candidates === 0) warnings.push("annotation documents do not contain any nail candidates");
if (candidatesWithDebug === 0) warnings.push("annotation candidates do not contain debug extraction diagnostics");
if (candidatesWithPolygon === 0) warnings.push("annotation candidates do not contain polygon masks for shape-preservation checks");
if (!evidence.documentsOk) {
  warnings.push(`evidence document count ${documents} is below required ${options.minDocuments}`);
}
if (!evidence.candidatesWithDebugOk) {
  warnings.push(
    `debug candidate count ${candidatesWithDebug} is below required ${options.minCandidatesWithDebug}`
  );
}
if (!evidence.candidatesWithPolygonOk) {
  warnings.push(
    `polygon candidate count ${candidatesWithPolygon} is below required ${options.minCandidatesWithPolygon}`
  );
}
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
if (roughRectangleRate != null && roughRectangleRate > options.maxRoughRectangleRate) {
  warnings.push(
    `rough rectangle polygon rate ${roundRate(roughRectangleRate)} is above target ${options.maxRoughRectangleRate}`
  );
}

const nextSteps: string[] = [];
if (!evidenceOk) {
  nextSteps.push("先扩大验收样本，并确保样本中同时包含 extraction diagnostics 与 polygon mask，再把该结果作为发布证据。");
}
if (options.evidenceScope !== "release-test-split") {
  nextSteps.push("发布候选模型前，请使用 --evidence-scope release-test-split 在独立测试集上重跑质量门禁。");
}
if (directlyUsableRate != null && directlyUsableRate < options.minUsableRate) {
  nextSteps.push("优先复核低质量候选与提取后的 diagnostics，减少需要人工调整的纹理样本。");
}
if (contaminationRate != null && contaminationRate >= options.maxContaminationRate) {
  nextSteps.push("优先处理 dirty_mask_crop 类问题，降低皮肤或背景污染进入最终纹理的比例。");
}
if (roughRectangleRate != null && roughRectangleRate > options.maxRoughRectangleRate) {
  nextSteps.push("优先复核粗糙矩形 polygon，确保异形甲、圆甲和长甲保留真实轮廓，而不是退化成矩形裁剪。");
}
if (candidatesWithDebug === 0) {
  nextSteps.push("先继续积累带 extraction diagnostics 的 debug annotation 样本，再重跑该门禁。");
}
if (candidatesWithPolygon === 0) {
  nextSteps.push("先导入带 polygon mask 的 annotation，再验证形状保真门禁。");
}
if (nextSteps.length === 0) {
  nextSteps.push("纹理可用率、污染率与形状保真门禁当前通过，可以继续扩大真实样本审计范围。");
}

const summary = {
  ok:
    evidenceOk &&
    candidatesWithDebug > 0 &&
    candidatesWithPolygon > 0 &&
    directlyUsableRate != null &&
    directlyUsableRate >= options.minUsableRate &&
    contaminationRate != null &&
    contaminationRate < options.maxContaminationRate &&
    roughRectangleRate != null &&
    roughRectangleRate <= options.maxRoughRectangleRate,
  annotationDirPath: options.annotationDirPath,
  thresholds: {
    minUsableRate: options.minUsableRate,
    maxContaminationRate: options.maxContaminationRate,
    minDocuments: options.minDocuments,
    minCandidatesWithDebug: options.minCandidatesWithDebug,
    minCandidatesWithPolygon: options.minCandidatesWithPolygon,
    maxHighlightRatioForUsable: options.maxHighlightRatioForUsable,
    maxHighlightPixelsForUsable: options.maxHighlightPixelsForUsable,
    maxRoughRectangleRate: options.maxRoughRectangleRate,
    minPolygonPointsForShapePreserved: options.minPolygonPointsForShapePreserved,
    maxPolygonBoundsFillRatio: options.maxPolygonBoundsFillRatio,
  },
  evidence: {
    ...evidence,
    ok: evidenceOk,
  },
  totals: {
    documents,
    candidates,
    candidatesWithDebug,
    directlyUsableCandidates,
    contaminatedCandidates,
    candidatesWithPolygon,
    roughRectangleCandidates,
  },
  rates: {
    directlyUsableRate: roundRate(directlyUsableRate),
    contaminationRate: roundRate(contaminationRate),
    roughRectangleRate: roundRate(roughRectangleRate),
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