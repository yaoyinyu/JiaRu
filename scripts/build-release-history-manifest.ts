import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface ReleaseTraceIndexLike {
  candidateVersion: string | null;
  currentRegistryVersion: string | null;
  batch?: {
    sourceGroup?: string | null;
    datasetRoot?: string | null;
    importedFileCount?: number;
  } | null;
  activeLearning?: {
    importedSampleCount?: number;
    importedByPriority?: Record<string, number> | null;
    prioritySummary?: {
      warningBreakdown?: Record<string, number> | null;
      backendBreakdown?: Record<string, number> | null;
    } | null;
    readinessSnapshot?: {
      totals?: { images?: number; validMasks?: number } | null;
    } | null;
  } | null;
  release?: {
    trainingReleasePipelineReportPath?: string | null;
    finalAuditStatus?: string | null;
    derivedAnnotationFailures?: number;
    postprocessFailures?: number;
    failureCategoryCounts?: Record<string, number> | null;
    failureSummaryTotals?: {
      csvRows?: number;
      derivedAnnotationFailures?: number;
      inferredRecordFailures?: number;
    } | null;
  } | null;
  performance?: {
    ok?: boolean | null;
    profile?: string | null;
    maxElapsedMs?: number | null;
    maxClientOverheadMs?: number | null;
    p95Ms?: number | null;
    maxMs?: number | null;
    p95WorkerMs?: number | null;
    p95ClientOverheadMs?: number | null;
    slowSamples?: number | null;
    slowClientOverheadSamples?: number | null;
    missingWorkerTimingSamples?: number | null;
    performanceReportPath?: string | null;
  } | null;
  quality?: {
    phase2ExtractionRateOk?: boolean | null;
    directlyUsableRate?: number | null;
    phase2ExtractionEvidenceOk?: boolean | null;
    phase2ExtractionEvidenceScope?: string | null;
    phase2RequiredUsableRate?: number | null;
    phase4TextureQualityGateOk?: boolean | null;
    contaminationRate?: number | null;
  } | null;
  decision?: {
    status?: string | null;
    summary?: string | null;
  } | null;
  promotion?: {
    registeredVersion?: string | null;
    currentVersion?: string | null;
  } | null;
  registry?: {
    currentVersion?: string | null;
  } | null;
  links?: {
    sourceGroupToCandidateVersion?: string | null;
  } | null;
}

interface CliOptions {
  traceIndexPaths: string[];
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-release-history-manifest.ts --trace-index <release-trace-index.json> [--trace-index <release-trace-index.json> ...] [--output <release-history-manifest.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  const traceIndexPaths: string[] = [];
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--trace-index") {
      traceIndexPaths.push(path.resolve(argv[++index] ?? usage()));
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (traceIndexPaths.length === 0) usage();
  if (!outputPath) {
    outputPath = path.join(path.dirname(traceIndexPaths[0]!), "release-history-manifest.json");
  }

  return { traceIndexPaths, outputPath };
}

async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

function sortNullableText(value: string | null | undefined) {
  return value ?? "";
}

function addCounts(target: Record<string, number>, source: Record<string, number> | null | undefined) {
  if (!source) return;
  for (const [key, value] of Object.entries(source)) {
    target[key] = (target[key] ?? 0) + value;
  }
}

const options = parseArgs(process.argv.slice(2));
const indexes = await Promise.all(
  options.traceIndexPaths.map(async (traceIndexPath) => ({
    traceIndexPath,
    trace: await readJson<ReleaseTraceIndexLike>(traceIndexPath),
  }))
);

const entries = indexes
  .map(({ traceIndexPath, trace }) => ({
    traceIndexPath,
    candidateVersion: trace.candidateVersion,
    sourceGroup: trace.batch?.sourceGroup ?? null,
    importedFileCount: trace.batch?.importedFileCount ?? 0,
    datasetRoot: trace.batch?.datasetRoot ?? null,
    finalAuditStatus: trace.release?.finalAuditStatus ?? null,
    derivedAnnotationFailures: trace.release?.derivedAnnotationFailures ?? 0,
    postprocessFailures: trace.release?.postprocessFailures ?? 0,
    failureCategoryCounts: trace.release?.failureCategoryCounts ?? null,
    failureSummaryTotals: trace.release?.failureSummaryTotals ?? null,
    failureCategoryTotal: Object.values(trace.release?.failureCategoryCounts ?? {}).reduce(
      (total, value) => total + value,
      0
    ),
    failureSummaryCsvRows: trace.release?.failureSummaryTotals?.csvRows ?? 0,
    failureSummaryInferredRecordFailures:
      trace.release?.failureSummaryTotals?.inferredRecordFailures ?? 0,
    performanceOk: trace.performance?.ok ?? null,
    performanceProfile: trace.performance?.profile ?? null,
    performanceMaxElapsedMs: trace.performance?.maxElapsedMs ?? null,
    performanceMaxClientOverheadMs: trace.performance?.maxClientOverheadMs ?? null,
    performanceP95Ms: trace.performance?.p95Ms ?? null,
    performanceMaxMs: trace.performance?.maxMs ?? null,
    performanceP95WorkerMs: trace.performance?.p95WorkerMs ?? null,
    performanceP95ClientOverheadMs: trace.performance?.p95ClientOverheadMs ?? null,
    performanceSlowSamples: trace.performance?.slowSamples ?? 0,
    performanceSlowClientOverheadSamples: trace.performance?.slowClientOverheadSamples ?? 0,
    performanceMissingWorkerTimingSamples: trace.performance?.missingWorkerTimingSamples ?? 0,
    performanceReportPath: trace.performance?.performanceReportPath ?? null,
    qualityPhase2ExtractionRateOk: trace.quality?.phase2ExtractionRateOk ?? null,
    qualityDirectlyUsableRate: trace.quality?.directlyUsableRate ?? null,
    qualityPhase2ExtractionEvidenceOk: trace.quality?.phase2ExtractionEvidenceOk ?? null,
    qualityPhase2ExtractionEvidenceScope: trace.quality?.phase2ExtractionEvidenceScope ?? null,
    qualityPhase4TextureQualityGateOk: trace.quality?.phase4TextureQualityGateOk ?? null,
    qualityContaminationRate: trace.quality?.contaminationRate ?? null,
    decisionStatus: trace.decision?.status ?? null,
    decisionSummary: trace.decision?.summary ?? null,
    registeredVersion: trace.promotion?.registeredVersion ?? null,
    currentRegistryVersion:
      trace.promotion?.currentVersion ?? trace.registry?.currentVersion ?? trace.currentRegistryVersion ?? null,
    sourceGroupToCandidateVersion: trace.links?.sourceGroupToCandidateVersion ?? null,
    trainingReleasePipelineReportPath: trace.release?.trainingReleasePipelineReportPath ?? null,
    activeLearningImportedSampleCount: trace.activeLearning?.importedSampleCount ?? 0,
    activeLearningImportedByPriority: trace.activeLearning?.importedByPriority ?? null,
    activeLearningWarningBreakdown:
      trace.activeLearning?.prioritySummary?.warningBreakdown ?? null,
    activeLearningBackendBreakdown:
      trace.activeLearning?.prioritySummary?.backendBreakdown ?? null,
    activeLearningReadinessTotals:
      trace.activeLearning?.readinessSnapshot?.totals ?? null,
  }))
  .sort(
    (a, b) =>
      sortNullableText(a.candidateVersion).localeCompare(sortNullableText(b.candidateVersion)) ||
      sortNullableText(a.sourceGroup).localeCompare(sortNullableText(b.sourceGroup)) ||
      a.traceIndexPath.localeCompare(b.traceIndexPath)
  );

const decisionCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.decisionStatus || "unknown";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const finalAuditStatusCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.finalAuditStatus || "unknown";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const performanceStatusCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.performanceOk == null ? "unknown" : entry.performanceOk ? "pass" : "fail";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const performanceProfileCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.performanceProfile || "unknown";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const phase2ExtractionStatusCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.qualityPhase2ExtractionRateOk == null ? "unknown" : entry.qualityPhase2ExtractionRateOk ? "pass" : "fail";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const textureQualityStatusCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.qualityPhase4TextureQualityGateOk == null ? "unknown" : entry.qualityPhase4TextureQualityGateOk ? "pass" : "fail";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const phase2EvidenceScopeCounts = entries.reduce<Record<string, number>>((acc, entry) => {
  const key = entry.qualityPhase2ExtractionEvidenceScope || "unknown";
  acc[key] = (acc[key] ?? 0) + 1;
  return acc;
}, {});

const registeredVersions = Array.from(
  new Set(entries.map((entry) => entry.registeredVersion).filter(Boolean))
);
const sourceGroups = Array.from(
  new Set(entries.map((entry) => entry.sourceGroup).filter(Boolean))
);
const activeLearningImportedSamples = entries.reduce(
  (total, entry) => total + entry.activeLearningImportedSampleCount,
  0
);
const activeLearningWarningBreakdown: Record<string, number> = {};
const activeLearningImportedByPriority: Record<string, number> = {};
const activeLearningBackendBreakdown: Record<string, number> = {};
for (const entry of entries) {
  addCounts(activeLearningWarningBreakdown, entry.activeLearningWarningBreakdown);
  addCounts(activeLearningImportedByPriority, entry.activeLearningImportedByPriority);
  addCounts(activeLearningBackendBreakdown, entry.activeLearningBackendBreakdown);
}

const failureCategoryBreakdown: Record<string, number> = {};
for (const entry of entries) {
  addCounts(failureCategoryBreakdown, entry.failureCategoryCounts);
}
const failureTraceIndexes = entries.filter(
  (entry) => entry.failureCategoryCounts || entry.failureSummaryTotals
).length;
const failureCategoryTotal = entries.reduce((total, entry) => total + entry.failureCategoryTotal, 0);
const failureSummaryCsvRows = entries.reduce(
  (total, entry) => total + entry.failureSummaryCsvRows,
  0
);
const failureSummaryInferredRecordFailures = entries.reduce(
  (total, entry) => total + entry.failureSummaryInferredRecordFailures,
  0
);

const performanceTraceIndexes = entries.filter((entry) => entry.performanceOk != null).length;
const failedPerformanceTraceIndexes = entries.filter((entry) => entry.performanceOk === false).length;
const performanceSlowSamples = entries.reduce((total, entry) => total + entry.performanceSlowSamples, 0);
const performanceSlowClientOverheadSamples = entries.reduce(
  (total, entry) => total + entry.performanceSlowClientOverheadSamples,
  0
);
const performanceMissingWorkerTimingSamples = entries.reduce(
  (total, entry) => total + entry.performanceMissingWorkerTimingSamples,
  0
);
const qualityTraceIndexes = entries.filter(
  (entry) =>
    entry.qualityPhase2ExtractionRateOk != null ||
    entry.qualityPhase4TextureQualityGateOk != null ||
    entry.qualityDirectlyUsableRate != null ||
    entry.qualityContaminationRate != null
).length;
const failedPhase2ExtractionTraceIndexes = entries.filter(
  (entry) => entry.qualityPhase2ExtractionRateOk === false
).length;
const failedTextureQualityTraceIndexes = entries.filter(
  (entry) => entry.qualityPhase4TextureQualityGateOk === false
).length;
const directlyUsableRates = entries
  .map((entry) => entry.qualityDirectlyUsableRate)
  .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
const contaminationRates = entries
  .map((entry) => entry.qualityContaminationRate)
  .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
const averageDirectlyUsableRate = directlyUsableRates.length
  ? Number((directlyUsableRates.reduce((sum, value) => sum + value, 0) / directlyUsableRates.length).toFixed(4))
  : null;
const averageContaminationRate = contaminationRates.length
  ? Number((contaminationRates.reduce((sum, value) => sum + value, 0) / contaminationRates.length).toFixed(4))
  : null;

const summary = {
  ok: true,
  outputPath: options.outputPath,
  totals: {
    traceIndexes: entries.length,
    uniqueCandidateVersions: new Set(entries.map((entry) => entry.candidateVersion).filter(Boolean)).size,
    uniqueSourceGroups: sourceGroups.length,
    registeredVersions: registeredVersions.length,
    activeLearningTraceIndexes: entries.filter(
      (entry) => entry.activeLearningImportedSampleCount > 0 || entry.activeLearningWarningBreakdown
    ).length,
    activeLearningImportedSamples,
    failureTraceIndexes,
    failureCategoryTotal,
    failureSummaryCsvRows,
    failureSummaryInferredRecordFailures,
    performanceTraceIndexes,
    failedPerformanceTraceIndexes,
    performanceSlowSamples,
    performanceSlowClientOverheadSamples,
    performanceMissingWorkerTimingSamples,
    qualityTraceIndexes,
    failedPhase2ExtractionTraceIndexes,
    failedTextureQualityTraceIndexes,
    averageDirectlyUsableRate,
    averageContaminationRate,
  },
  decisionCounts,
  finalAuditStatusCounts,
  performanceStatusCounts,
  performanceProfileCounts,
  phase2ExtractionStatusCounts,
  textureQualityStatusCounts,
  phase2EvidenceScopeCounts,
  activeLearning: {
    importedByPriority: activeLearningImportedByPriority,
    warningBreakdown: activeLearningWarningBreakdown,
    backendBreakdown: activeLearningBackendBreakdown,
  },
  failureSummary: {
    categoryBreakdown: failureCategoryBreakdown,
    categoryTotal: failureCategoryTotal,
    csvRows: failureSummaryCsvRows,
    inferredRecordFailures: failureSummaryInferredRecordFailures,
    derivedAnnotationFailures: entries.reduce(
      (total, entry) => total + entry.derivedAnnotationFailures,
      0
    ),
    postprocessFailures: entries.reduce((total, entry) => total + entry.postprocessFailures, 0),
  },
  performance: {
    statusCounts: performanceStatusCounts,
    profileCounts: performanceProfileCounts,
    slowSamples: performanceSlowSamples,
    slowClientOverheadSamples: performanceSlowClientOverheadSamples,
    missingWorkerTimingSamples: performanceMissingWorkerTimingSamples,
  },
  quality: {
    phase2ExtractionStatusCounts,
    textureQualityStatusCounts,
    phase2EvidenceScopeCounts,
    failedPhase2ExtractionTraceIndexes,
    failedTextureQualityTraceIndexes,
    averageDirectlyUsableRate,
    averageContaminationRate,
  },
  sourceGroups,
  registeredVersions,
  entries,
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
