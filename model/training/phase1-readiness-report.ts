import path from "node:path";
import { readFile, readdir } from "node:fs/promises";
import {
  auditAnnotationDocument,
  parseSourceRecords,
  readAnnotationDocument,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

export const DEFAULT_DATASET_ROOT = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

export interface DatasetSplit {
  train: string[];
  val: string[];
  test: string[];
}

export interface Phase1ReadinessGate {
  ok: boolean;
  actual: number;
  required: number;
}

export interface Phase1ReadinessReport {
  ok: boolean;
  datasetRoot: string;
  reportPath: string;
  totals: {
    images: number;
    masks: number;
    validMasks: number;
    filesWithErrors: number;
    filesWithWarnings: number;
  };
  splitCounts: {
    train: number;
    val: number;
    test: number;
  };
  testCoverage: {
    negatives: number;
    complexBackground: number;
    sampleKinds: Record<string, number>;
    backgrounds: Record<string, number>;
  };
  gates: {
    imageCount: Phase1ReadinessGate;
    validMaskCount: Phase1ReadinessGate;
    labelAuditPass: Phase1ReadinessGate;
    testSplitHasNegative: Phase1ReadinessGate;
    testSplitHasComplexBackground: Phase1ReadinessGate;
  };
  warnings: string[];
  fileResults: Array<{
    fileName: string;
    ok: boolean;
    polygonCount: number;
    errorCount: number;
    warningCount: number;
  }>;
}

export function phase1ReadinessPaths(datasetRoot: string) {
  const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
  const metadataDir = path.join(datasetRoot, "metadata");
  return {
    annotationDir,
    metadataDir,
    splitPath: path.join(metadataDir, "split.json"),
    sourcesCsvPath: path.join(metadataDir, "sources.csv"),
    reportPath: path.join(metadataDir, "phase1-readiness.json"),
  };
}

function parseTaggedNotes(notes: string): Record<string, string> {
  const tags: Record<string, string> = {};
  for (const part of notes.split(";")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    if (key) tags[key] = value;
  }
  return tags;
}

function countBy(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values.filter(Boolean)) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

function isComplexBackground(record: SourceRecord): boolean {
  const tags = parseTaggedNotes(record.notes);
  if (tags.reason === "complex_background" || tags.reason === "background_confusion") {
    return true;
  }
  if (tags.background === "dark" || tags.background === "mixed") {
    return true;
  }
  return false;
}

async function readDocuments(annotationDir: string): Promise<NailTextureAnnotationDocument[]> {
  try {
    const entries = await readdir(annotationDir, { withFileTypes: true });
    const files = entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
      .map((entry) => path.join(annotationDir, entry.name))
      .sort();

    const documents: NailTextureAnnotationDocument[] = [];
    for (const filePath of files) {
      documents.push(await readAnnotationDocument(filePath));
    }
    return documents;
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

async function readSplit(splitPath: string): Promise<DatasetSplit> {
  try {
    return JSON.parse(await readFile(splitPath, "utf8")) as DatasetSplit;
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") {
      return { train: [], val: [], test: [] };
    }
    throw error;
  }
}

async function readSources(sourcesCsvPath: string): Promise<SourceRecord[]> {
  try {
    return parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

export async function buildPhase1ReadinessReport(
  datasetRoot = DEFAULT_DATASET_ROOT
): Promise<Phase1ReadinessReport> {
  const paths = phase1ReadinessPaths(datasetRoot);
  const documents = await readDocuments(paths.annotationDir);
  const split = await readSplit(paths.splitPath);
  const sources = await readSources(paths.sourcesCsvPath);

  let totalMasks = 0;
  let validMasks = 0;
  let errorFileCount = 0;
  let warningFileCount = 0;
  const fileResults = documents.map((document) => {
    const result = auditAnnotationDocument(document);
    totalMasks += result.polygonCount;
    const errorCount = result.issues.filter((issue) => issue.severity === "error").length;
    const warningCount = result.issues.filter((issue) => issue.severity === "warning").length;
    if (errorCount > 0) errorFileCount++;
    if (warningCount > 0) warningFileCount++;
    if (errorCount === 0) {
      validMasks += result.polygonCount;
    }
    return {
      fileName: document.image.fileName,
      ok: result.ok,
      polygonCount: result.polygonCount,
      errorCount,
      warningCount,
    };
  });

  const testFiles = new Set(split.test);
  const testSources = sources.filter((record) => testFiles.has(record.fileName));
  const testNegativeCount = testSources.filter(
    (record) => record.negative || record.originType === "negative"
  ).length;
  const testComplexBackgroundCount = testSources.filter(isComplexBackground).length;

  const gates = {
    imageCount: {
      ok: documents.length >= 200,
      actual: documents.length,
      required: 200,
    },
    validMaskCount: {
      ok: validMasks >= 800,
      actual: validMasks,
      required: 800,
    },
    labelAuditPass: {
      ok: errorFileCount === 0,
      actual: errorFileCount,
      required: 0,
    },
    testSplitHasNegative: {
      ok: testNegativeCount > 0,
      actual: testNegativeCount,
      required: 1,
    },
    testSplitHasComplexBackground: {
      ok: testComplexBackgroundCount > 0,
      actual: testComplexBackgroundCount,
      required: 1,
    },
  };

  const warnings: string[] = [];
  if (documents.length === 0) warnings.push("dataset currently has no annotation documents");
  if (split.train.length + split.val.length + split.test.length === 0) {
    warnings.push("split.json is missing or currently empty");
  }
  if (sources.length === 0) {
    warnings.push("sources.csv is missing or currently empty");
  }
  if (!gates.imageCount.ok) {
    warnings.push(`need ${gates.imageCount.required - gates.imageCount.actual} more images to reach 200`);
  }
  if (!gates.validMaskCount.ok) {
    warnings.push(
      `need ${gates.validMaskCount.required - gates.validMaskCount.actual} more valid nail masks to reach 800`
    );
  }
  if (!gates.labelAuditPass.ok) {
    warnings.push(`label audit still has ${errorFileCount} files with error-level issues`);
  }
  if (!gates.testSplitHasNegative.ok) warnings.push("test split does not yet contain a negative sample");
  if (!gates.testSplitHasComplexBackground.ok) {
    warnings.push("test split does not yet contain a complex-background sample");
  }
  if (warningFileCount > 0) warnings.push(`label audit still has ${warningFileCount} files with warning-level issues`);

  return {
    ok: Object.values(gates).every((gate) => gate.ok),
    datasetRoot,
    reportPath: paths.reportPath,
    totals: {
      images: documents.length,
      masks: totalMasks,
      validMasks,
      filesWithErrors: errorFileCount,
      filesWithWarnings: warningFileCount,
    },
    splitCounts: {
      train: split.train.length,
      val: split.val.length,
      test: split.test.length,
    },
    testCoverage: {
      negatives: testNegativeCount,
      complexBackground: testComplexBackgroundCount,
      sampleKinds: countBy(
        testSources.map((record) => parseTaggedNotes(record.notes).sample || record.originType)
      ),
      backgrounds: countBy(
        testSources.map((record) => parseTaggedNotes(record.notes).background || "unspecified")
      ),
    },
    gates,
    warnings,
    fileResults,
  };
}
