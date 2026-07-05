import path from "node:path";
import process from "node:process";
import { readdir, readFile } from "node:fs/promises";

interface FailureRow {
  fileName: string;
  stage: string;
  category: string;
  subcategory: string;
  severity: string;
  action: string;
  notes: string;
}

interface FirstRunRecordLike {
  model?: { artifactOk?: boolean };
  readiness?: {
    ok?: boolean;
    fixtureVerified?: boolean | null;
    imageVerified?: boolean | null;
    warnings?: string[];
  };
  observations?: {
    newWarnings?: string[];
  };
  decision?: {
    status?: "pass" | "needs_adjustment" | "blocked";
    nextActions?: string[];
  };
}

interface AnnotationDebugLike {
  warnings?: string[];
  extractionQualityOk?: boolean;
  extractionQualityWarnings?: string[];
  highlightPixels?: number;
  repairedPixels?: number;
  highlightRatio?: number;
}

interface AnnotationRecordLike {
  image?: {
    fileName?: string;
  };
  annotations?: Array<{
    attributes?: {
      debug?: AnnotationDebugLike;
    };
  }>;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/summarize-failure-cases.ts [--failure-csv <failure-classification.csv>] [--first-run-record <record.json>] [--annotation-dir <annotations-dir>]"
  );
}

const args = process.argv.slice(2);
let failureCsvPath: string | undefined;
let firstRunRecordPath: string | undefined;
let annotationDirPath: string | undefined;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--failure-csv") failureCsvPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--first-run-record") firstRunRecordPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--annotation-dir") annotationDirPath = path.resolve(args[++index] ?? usage());
  else usage();
}

if (!failureCsvPath && !firstRunRecordPath && !annotationDirPath) usage();

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === "\"") {
      if (inQuotes && line[i + 1] === "\"") {
        current += "\"";
        i++;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  values.push(current);
  return values;
}

function countBy(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values.filter(Boolean)) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

async function readFailureRows(filePath: string): Promise<FailureRow[]> {
  const csvText = await readFile(filePath, "utf8");
  const trimmed = csvText.trim();
  if (!trimmed) return [];
  const lines = trimmed.split(/\r?\n/).filter(Boolean);
  const header = parseCsvLine(lines[0] ?? "");
  const expected = ["fileName", "stage", "category", "subcategory", "severity", "action", "notes"];
  if (expected.some((key, index) => header[index] !== key)) {
    throw new Error(`Unexpected failure-classification.csv header: ${header.join(",")}`);
  }
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    return {
      fileName: (cells[0] ?? "").trim(),
      stage: (cells[1] ?? "").trim(),
      category: (cells[2] ?? "").trim(),
      subcategory: (cells[3] ?? "").trim(),
      severity: (cells[4] ?? "").trim(),
      action: (cells[5] ?? "").trim(),
      notes: (cells[6] ?? "").trim(),
    };
  });
}

function inferRecordCategory(record: FirstRunRecordLike): {
  category: "data" | "model" | "postprocess" | "ui" | "unknown";
  reason: string;
} {
  if (record.model?.artifactOk === false) {
    return { category: "model", reason: "model artifact failed or is missing" };
  }
  if (record.readiness?.fixtureVerified === false) {
    return { category: "postprocess", reason: "fixture/postprocess verification failed" };
  }
  if (record.readiness?.imageVerified === false) {
    return { category: "model", reason: "single-image detection verification failed" };
  }
  const warnings = [
    ...(record.readiness?.warnings ?? []),
    ...(record.observations?.newWarnings ?? []),
  ].join(" | ");
  if (/model_(manifest|inference)_error|onnx_(runtime_not_loaded|session_init_failed|session_or_tensor_unavailable)|model_outputs_empty_used_fallback|no_supported_model_backend/i.test(warnings)) {
    return { category: "model", reason: "warnings point to model runtime, manifest, session, or empty-output fallback issues" };
  }
  if (/browser integration|assignment|ui/i.test(warnings)) {
    return { category: "ui", reason: "warnings point to browser integration or assignment issues" };
  }
  if (/mask|angle|crop|postprocess/i.test(warnings)) {
    return { category: "postprocess", reason: "warnings point to mask/angle/crop instability" };
  }
  if (record.decision?.status === "blocked") {
    return { category: "model", reason: "record is blocked without a more specific signal" };
  }
  if (record.decision?.status === "needs_adjustment") {
    return { category: "ui", reason: "record needs adjustment but artifact is available" };
  }
  return { category: "unknown", reason: "no obvious failure signal was inferred" };
}

function createDerivedAnnotationRow(
  fileName: string,
  subcategory: string,
  notes: string
): FailureRow {
  return {
    fileName,
    stage: "postprocess",
    category: "postprocess",
    subcategory,
    severity: "derived",
    action: "review_annotation_debug",
    notes,
  };
}

function shouldDeriveHighlightFailure(debug: AnnotationDebugLike): boolean {
  return (debug.highlightRatio ?? 0) >= 0.12 || (debug.highlightPixels ?? 0) >= 8;
}

async function readDerivedAnnotationRows(annotationDir: string): Promise<FailureRow[]> {
  const entries = await readdir(annotationDir, { withFileTypes: true });
  const rows: FailureRow[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".json")) continue;

    const filePath = path.join(annotationDir, entry.name);
    const record = JSON.parse(await readFile(filePath, "utf8")) as AnnotationRecordLike;
    const annotationFileName = record.image?.fileName || entry.name;

    for (const [index, annotation] of (record.annotations ?? []).entries()) {
      const debug = annotation.attributes?.debug;
      if (!debug) continue;

      const sourceLabel =
        (record.annotations?.length ?? 0) > 1
          ? `${annotationFileName}#annotation-${index + 1}`
          : annotationFileName;

      for (const warning of debug.warnings ?? []) {
        rows.push(
          createDerivedAnnotationRow(
            sourceLabel,
            warning,
            "derived from annotation.attributes.debug.warnings"
          )
        );
      }

      for (const warning of debug.extractionQualityWarnings ?? []) {
        rows.push(
          createDerivedAnnotationRow(
            sourceLabel,
            warning,
            "derived from annotation.attributes.debug.extractionQualityWarnings"
          )
        );
      }

      if (shouldDeriveHighlightFailure(debug)) {
        rows.push(
          createDerivedAnnotationRow(
            sourceLabel,
            "highlight_hotspots",
            "derived from annotation.attributes.debug highlight ratio/pixels"
          )
        );
      }
    }
  }

  return rows;
}

const failureRows = failureCsvPath ? await readFailureRows(failureCsvPath) : [];
const firstRunRecord = firstRunRecordPath
  ? (JSON.parse(await readFile(firstRunRecordPath, "utf8")) as FirstRunRecordLike)
  : null;
const derivedAnnotationRows = annotationDirPath
  ? await readDerivedAnnotationRows(annotationDirPath)
  : [];

const csvCategoryCounts = countBy(failureRows.map((row) => row.category || "uncategorized"));
const csvSubcategoryCounts = countBy(
  failureRows.map((row) =>
    row.category && row.subcategory
      ? `${row.category}/${row.subcategory}`
      : row.subcategory || row.category || "uncategorized"
  )
);
const csvSeverityCounts = countBy(failureRows.map((row) => row.severity || "unspecified"));
const csvActionCounts = countBy(failureRows.map((row) => row.action || "unspecified"));
const csvStageCounts = countBy(failureRows.map((row) => row.stage || "unspecified"));

const derivedAnnotationCategoryCounts = countBy(
  derivedAnnotationRows.map((row) => row.category || "uncategorized")
);
const derivedAnnotationSubcategoryCounts = countBy(
  derivedAnnotationRows.map((row) =>
    row.category && row.subcategory
      ? `${row.category}/${row.subcategory}`
      : row.subcategory || row.category || "uncategorized"
  )
);

const inferredRecord = firstRunRecord ? inferRecordCategory(firstRunRecord) : null;

const mergedCategoryCounts = { ...csvCategoryCounts };
for (const [category, count] of Object.entries(derivedAnnotationCategoryCounts)) {
  mergedCategoryCounts[category] = (mergedCategoryCounts[category] ?? 0) + count;
}
if (inferredRecord && inferredRecord.category !== "unknown") {
  mergedCategoryCounts[inferredRecord.category] =
    (mergedCategoryCounts[inferredRecord.category] ?? 0) + 1;
}

const dominantCategories = Object.entries(mergedCategoryCounts)
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  .map(([category, count]) => ({ category, count }));

const nextSteps: string[] = [];
if ((mergedCategoryCounts.data ?? 0) > 0) {
  nextSteps.push("优先补数据：增加对应失败类型样本，或完善标注与负样本覆盖。");
}
if ((mergedCategoryCounts.model ?? 0) > 0) {
  nextSteps.push("优先检查模型：复看训练指标、漏检/误检样本，并考虑保留 baseline 版本回滚。");
}
if ((mergedCategoryCounts.postprocess ?? 0) > 0) {
  nextSteps.push("优先检查后处理：重点复核 angle、mask crop、quality ranking 与阈值策略。");
}
if ((mergedCategoryCounts.ui ?? 0) > 0) {
  nextSteps.push("优先检查 UI：重点复核候选映射、手动修正成本和交互反馈。");
}
if (nextSteps.length === 0) {
  nextSteps.push("当前没有明确失败分类输入，继续积累 failure-classification.csv 或 first-run record。");
}

const summary = {
  ok: true,
  failureCsvPath: failureCsvPath ?? null,
  firstRunRecordPath: firstRunRecordPath ?? null,
  annotationDirPath: annotationDirPath ?? null,
  totals: {
    csvRows: failureRows.length,
    derivedAnnotationFailures: derivedAnnotationRows.length,
    inferredRecordFailure:
      firstRunRecord && firstRunRecord.decision?.status && firstRunRecord.decision.status !== "pass"
        ? 1
        : 0,
  },
  categoryCounts: mergedCategoryCounts,
  dominantCategories,
  csvBreakdown: {
    categoryCounts: csvCategoryCounts,
    subcategoryCounts: csvSubcategoryCounts,
    severityCounts: csvSeverityCounts,
    actionCounts: csvActionCounts,
    stageCounts: csvStageCounts,
  },
  derivedAnnotationBreakdown: {
    categoryCounts: derivedAnnotationCategoryCounts,
    subcategoryCounts: derivedAnnotationSubcategoryCounts,
  },
  inferredFromFirstRunRecord: inferredRecord,
  nextSteps,
};

console.log(JSON.stringify(summary, null, 2));
