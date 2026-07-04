import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface ReviewedImportPipelineReportLike {
  ok: boolean;
  rootDir: string;
  reportPath: string;
  steps?: Array<{
    name?: string;
    stdout?: {
      sourceGroup?: string;
      datasetRoot?: string;
      reportPath?: string;
      importedDocuments?: Array<{ fileName?: string }>;
    };
  }>;
}

interface ReleaseTraceDraftLike {
  trainingReadiness?: {
    ok?: boolean | null;
    reportPath?: string | null;
    authorizationMode?: string | null;
    gates?: {
      sourceAudit?: boolean | null;
      sourceAuthorization?: boolean | null;
      phase1Readiness?: boolean | null;
    };
    totals?: { images?: number | null; validMasks?: number | null };
    failingSteps?: string[];
  } | null;
  batch?: {
    rootDir?: string | null;
    sourceGroup?: string | null;
    datasetRoot?: string | null;
    reviewedImportReportPath?: string | null;
    importedFileCount?: number;
  } | null;
  activeLearning?: {
    pipelineReportPath?: string | null;
    sampleDir?: string | null;
    imageDir?: string | null;
    priorityReportPath?: string | null;
    priorityFilters?: {
      reportPath?: string | null;
      minPriorityTier?: string | null;
      top?: number | null;
    } | null;
    importedSampleCount?: number;
    importedByPriority?: Record<string, number>;
    importedSamples?: Array<{
      samplePath?: string | null;
      priorityTier?: string | null;
      priorityScore?: number | null;
    }>;
    prioritySummary?: {
      backendBreakdown?: Record<string, number> | null;
      modelBackendBreakdown?: Record<string, number> | null;
      correctedCandidateSourceBreakdown?: Record<string, number> | null;
      reasonBreakdown?: Record<string, number> | null;
    } | null;
    readinessSnapshot?: {
      reportPath?: string | null;
      imageCountGate?: { ok?: boolean; actual?: number; required?: number } | null;
      validMaskCountGate?: { ok?: boolean; actual?: number; required?: number } | null;
      totals?: { images?: number; validMasks?: number } | null;
    } | null;
  } | null;
}

interface TrainingReleasePipelineReportLike {
  ok: boolean;
  reportPath?: string;
  paths?: {
    manifestPath?: string;
    trainOutputDir?: string;
    metricsPath?: string;
  };
  artifacts?: {
    trainingDatasetReadiness?: {
      ok?: boolean;
      outputPath?: string;
      authorizationMode?: string;
      steps?: Array<{ name?: string; ok?: boolean }>;
      totals?: { images?: number; validMasks?: number };
    } | null;
    manifest?: { version?: string; modelFile?: string } | null;
    finalAudit?: {
      decision?: { status?: string; summary?: string };
    } | null;
    finalAuditFailureSummary?: {
      totals?: { derivedAnnotationFailures?: number };
      categoryCounts?: Record<string, number>;
    } | null;
  };
  steps?: Array<{
    name?: string;
    stdout?: {
      finalReportPath?: string;
      failureSummaryPath?: string;
      recordPath?: string;
    };
  }>;
}

interface ReleaseDecisionReportLike {
  pipelineReportPath: string;
  compareSummaryPath?: string | null;
  performanceReportPath?: string | null;
  registryPath?: string | null;
  outputPath: string;
  candidateVersion: string | null;
  decision: {
    status: string;
    summary: string;
  };
  inputs?: {
    recognitionPerformanceOk?: boolean | null;
    recognitionPerformanceProfile?: string | null;
    recognitionPerformanceMaxElapsedMs?: number | null;
    recognitionPerformanceP95Ms?: number | null;
    recognitionPerformanceMaxMs?: number | null;
    recognitionPerformanceSlowSamples?: number | null;
    textureQualityGateOk?: boolean | null;
    phase2ExtractionRateOk?: boolean | null;
    phase2ExtractionEvidenceOk?: boolean | null;
    phase2ExtractionEvidenceScope?: string | null;
    directlyUsableRate?: number | null;
    contaminationRate?: number | null;
  };
}

interface PromotionReportLike {
  decisionReportPath: string;
  pipelineReportPath: string;
  registryPath: string;
  outputPath: string;
  candidateVersion: string | null;
  decisionStatus: string;
  manifestPath?: string;
  registerSummary?: {
    currentVersion?: string | null;
    registeredVersion?: string;
    snapshotPath?: string;
  };
}

interface RegistryLike {
  currentVersion: string | null;
  releases: Array<{ version: string }>;
}

interface CliOptions {
  releaseTraceDraftPath?: string;
  reviewedBatchImportPipelineReportPath?: string;
  trainingReleasePipelineReportPath: string;
  releaseDecisionReportPath?: string;
  promotionReportPath?: string;
  registryPath?: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-release-trace-index.ts --training-release-pipeline-report <training-release-pipeline-report.json> [--release-trace-draft <release-trace-draft.json>] [--reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>] [--release-decision-report <release-decision-report.json>] [--promotion-report <promotion-report.json>] [--registry <release-registry.json>] [--output <release-trace-index.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let releaseTraceDraftPath: string | undefined;
  let reviewedBatchImportPipelineReportPath: string | undefined;
  let trainingReleasePipelineReportPath = "";
  let releaseDecisionReportPath: string | undefined;
  let promotionReportPath: string | undefined;
  let registryPath: string | undefined;
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--release-trace-draft") {
      releaseTraceDraftPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--reviewed-batch-import-pipeline-report") {
      reviewedBatchImportPipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--training-release-pipeline-report") {
      trainingReleasePipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--release-decision-report") {
      releaseDecisionReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--promotion-report") {
      promotionReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--registry") {
      registryPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (!trainingReleasePipelineReportPath) usage();
  if (!outputPath) {
    outputPath = path.join(
      path.dirname(trainingReleasePipelineReportPath),
      "release-trace-index.json"
    );
  }

  return {
    releaseTraceDraftPath,
    reviewedBatchImportPipelineReportPath,
    trainingReleasePipelineReportPath,
    releaseDecisionReportPath,
    promotionReportPath,
    registryPath,
    outputPath,
  };
}

async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

async function readOptionalJson<T>(filePath?: string): Promise<T | null> {
  if (!filePath) return null;
  try {
    return await readJson<T>(filePath);
  } catch {
    return null;
  }
}

function findStep<T extends { name?: string; stdout?: unknown }>(
  steps: T[] | undefined,
  name: string
) {
  return steps?.find((step) => step.name === name);
}

const options = parseArgs(process.argv.slice(2));
const releaseTraceDraft = await readOptionalJson<ReleaseTraceDraftLike>(
  options.releaseTraceDraftPath
);
const reviewedBatchImportPipelineReport = await readOptionalJson<ReviewedImportPipelineReportLike>(
  options.reviewedBatchImportPipelineReportPath
);
const trainingReleasePipelineReport = await readJson<TrainingReleasePipelineReportLike>(
  options.trainingReleasePipelineReportPath
);
const releaseDecisionReport = await readOptionalJson<ReleaseDecisionReportLike>(
  options.releaseDecisionReportPath
);
const promotionReport = await readOptionalJson<PromotionReportLike>(
  options.promotionReportPath
);
const registry = await readOptionalJson<RegistryLike>(
  options.registryPath ??
    promotionReport?.registryPath ??
    releaseDecisionReport?.registryPath ??
    undefined
);

const importReviewedBatchStep = findStep(
  reviewedBatchImportPipelineReport?.steps,
  "import-reviewed-batch"
) as
  | {
      stdout?: {
        sourceGroup?: string;
        datasetRoot?: string;
        reportPath?: string;
        importedDocuments?: Array<{ fileName?: string }>;
      };
    }
  | undefined;

const finalAuditStep = findStep(
  trainingReleasePipelineReport.steps,
  "run-real-model-final-audit"
) as
  | {
      stdout?: {
        finalReportPath?: string;
        failureSummaryPath?: string;
        recordPath?: string;
      };
    }
  | undefined;

const candidateVersion =
  promotionReport?.candidateVersion ??
  releaseDecisionReport?.candidateVersion ??
  trainingReleasePipelineReport.artifacts?.manifest?.version ??
  null;

const pipelineTrainingReadiness =
  trainingReleasePipelineReport.artifacts?.trainingDatasetReadiness ?? null;
const trainingReadiness = pipelineTrainingReadiness
  ? {
      ok: pipelineTrainingReadiness.ok ?? null,
      reportPath: pipelineTrainingReadiness.outputPath ?? null,
      authorizationMode: pipelineTrainingReadiness.authorizationMode ?? null,
      gates: {
        sourceAudit:
          pipelineTrainingReadiness.steps?.find((step) => step.name === "audit-sources-csv")?.ok ??
          null,
        sourceAuthorization:
          pipelineTrainingReadiness.steps?.find(
            (step) => step.name === "audit-training-source-authorization"
          )?.ok ?? null,
        phase1Readiness:
          pipelineTrainingReadiness.steps?.find((step) => step.name === "audit-phase1-readiness")
            ?.ok ?? null,
      },
      totals: {
        images: pipelineTrainingReadiness.totals?.images ?? null,
        validMasks: pipelineTrainingReadiness.totals?.validMasks ?? null,
      },
      failingSteps:
        pipelineTrainingReadiness.steps
          ?.filter((step) => step.ok === false)
          .map((step) => step.name ?? "unknown") ?? [],
    }
  : releaseTraceDraft?.trainingReadiness ?? null;
const summary = {
  ok: true,
  outputPath: options.outputPath,
  candidateVersion,
  currentRegistryVersion:
    promotionReport?.registerSummary?.currentVersion ?? registry?.currentVersion ?? null,
  trainingReadiness,
  batch: reviewedBatchImportPipelineReport || releaseTraceDraft?.batch
    ? {
        rootDir:
          reviewedBatchImportPipelineReport?.rootDir ?? releaseTraceDraft?.batch?.rootDir ?? null,
        sourceGroup:
          importReviewedBatchStep?.stdout?.sourceGroup ??
          releaseTraceDraft?.batch?.sourceGroup ??
          null,
        datasetRoot:
          importReviewedBatchStep?.stdout?.datasetRoot ??
          releaseTraceDraft?.batch?.datasetRoot ??
          null,
        releaseTraceDraftPath: options.releaseTraceDraftPath ?? null,
        reviewedBatchImportPipelineReportPath:
          options.reviewedBatchImportPipelineReportPath ?? null,
        reviewedImportReportPath:
          importReviewedBatchStep?.stdout?.reportPath ??
          releaseTraceDraft?.batch?.reviewedImportReportPath ??
          null,
        importedFileCount:
          importReviewedBatchStep?.stdout?.importedDocuments?.length ??
          releaseTraceDraft?.batch?.importedFileCount ??
          0,
      }
    : null,
  activeLearning: releaseTraceDraft?.activeLearning
    ? {
        pipelineReportPath: releaseTraceDraft.activeLearning.pipelineReportPath ?? null,
        sampleDir: releaseTraceDraft.activeLearning.sampleDir ?? null,
        imageDir: releaseTraceDraft.activeLearning.imageDir ?? null,
        priorityReportPath: releaseTraceDraft.activeLearning.priorityReportPath ?? null,
        priorityFilters: releaseTraceDraft.activeLearning.priorityFilters ?? null,
        importedSampleCount: releaseTraceDraft.activeLearning.importedSampleCount ?? 0,
        importedByPriority: releaseTraceDraft.activeLearning.importedByPriority ?? null,
        prioritySummary: releaseTraceDraft.activeLearning.prioritySummary ?? null,
        readinessSnapshot: releaseTraceDraft.activeLearning.readinessSnapshot ?? null,
      }
    : null,
  release: {
    trainingReleasePipelineReportPath: options.trainingReleasePipelineReportPath,
    manifestPath: trainingReleasePipelineReport.paths?.manifestPath ?? null,
    metricsPath: trainingReleasePipelineReport.paths?.metricsPath ?? null,
    trainOutputDir: trainingReleasePipelineReport.paths?.trainOutputDir ?? null,
    finalAuditReportPath: finalAuditStep?.stdout?.finalReportPath ?? null,
    finalAuditFailureSummaryPath: finalAuditStep?.stdout?.failureSummaryPath ?? null,
    firstRunRecordPath: finalAuditStep?.stdout?.recordPath ?? null,
    finalAuditStatus:
      trainingReleasePipelineReport.artifacts?.finalAudit?.decision?.status ?? null,
    derivedAnnotationFailures:
      trainingReleasePipelineReport.artifacts?.finalAuditFailureSummary?.totals
        ?.derivedAnnotationFailures ?? 0,
    postprocessFailures:
      trainingReleasePipelineReport.artifacts?.finalAuditFailureSummary?.categoryCounts
        ?.postprocess ?? 0,
  },
  performance: releaseDecisionReport
    ? {
        ok: releaseDecisionReport.inputs?.recognitionPerformanceOk ?? null,
        profile: releaseDecisionReport.inputs?.recognitionPerformanceProfile ?? null,
        maxElapsedMs: releaseDecisionReport.inputs?.recognitionPerformanceMaxElapsedMs ?? null,
        p95Ms: releaseDecisionReport.inputs?.recognitionPerformanceP95Ms ?? null,
        maxMs: releaseDecisionReport.inputs?.recognitionPerformanceMaxMs ?? null,
        slowSamples: releaseDecisionReport.inputs?.recognitionPerformanceSlowSamples ?? null,
        performanceReportPath: releaseDecisionReport.performanceReportPath ?? null,
      }
    : null,
  quality: releaseDecisionReport
    ? {
        phase2ExtractionRateOk:
          releaseDecisionReport.inputs?.phase2ExtractionRateOk ?? null,
        directlyUsableRate:
          releaseDecisionReport.inputs?.directlyUsableRate ?? null,
        phase2ExtractionEvidenceOk:
          releaseDecisionReport.inputs?.phase2ExtractionEvidenceOk ?? null,
        phase2ExtractionEvidenceScope:
          releaseDecisionReport.inputs?.phase2ExtractionEvidenceScope ?? null,
        phase2RequiredUsableRate: 0.8,
        phase4TextureQualityGateOk:
          releaseDecisionReport.inputs?.textureQualityGateOk ?? null,
        contaminationRate:
          releaseDecisionReport.inputs?.contaminationRate ?? null,
      }
    : null,
  decision: releaseDecisionReport
    ? {
        releaseDecisionReportPath: options.releaseDecisionReportPath ?? null,
        compareSummaryPath: releaseDecisionReport.compareSummaryPath ?? null,
        registryPath:
          options.registryPath ??
          promotionReport?.registryPath ??
          releaseDecisionReport.registryPath ??
          null,
        status: releaseDecisionReport.decision.status,
        summary: releaseDecisionReport.decision.summary,
      }
    : null,
  promotion: promotionReport
    ? {
        promotionReportPath: options.promotionReportPath ?? null,
        decisionStatus: promotionReport.decisionStatus,
        manifestPath: promotionReport.manifestPath ?? null,
        registeredVersion: promotionReport.registerSummary?.registeredVersion ?? null,
        currentVersion: promotionReport.registerSummary?.currentVersion ?? null,
        snapshotPath: promotionReport.registerSummary?.snapshotPath ?? null,
      }
    : null,
  registry: registry
    ? {
        registryPath:
          options.registryPath ??
          promotionReport?.registryPath ??
          releaseDecisionReport?.registryPath ??
          null,
        currentVersion: registry.currentVersion,
        releaseCount: registry.releases.length,
        knownVersions: registry.releases.map((item) => item.version),
      }
    : null,
  links: {
    sourceGroupToCandidateVersion:
      (reviewedBatchImportPipelineReport || releaseTraceDraft?.batch) && candidateVersion
        ? `${
            importReviewedBatchStep?.stdout?.sourceGroup ??
            releaseTraceDraft?.batch?.sourceGroup ??
            "unknown"
          } -> ${candidateVersion}`
        : null,
    candidateVersionToFinalAudit:
      candidateVersion && finalAuditStep?.stdout?.finalReportPath
        ? `${candidateVersion} -> ${finalAuditStep.stdout.finalReportPath}`
        : null,
    candidateVersionToDecision:
      candidateVersion && releaseDecisionReport
        ? `${candidateVersion} -> ${releaseDecisionReport.decision.status}`
        : null,
    candidateVersionToRegistry:
      candidateVersion && (promotionReport?.registerSummary?.currentVersion ?? registry?.currentVersion)
        ? `${candidateVersion} -> ${promotionReport?.registerSummary?.currentVersion ?? registry?.currentVersion}`
        : null,
  },
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));


