import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface PipelineReportLike {
  ok: boolean;
  reportPath?: string;
  artifacts?: {
    trainingDatasetReadiness?: {
      ok?: boolean;
      outputPath?: string;
      authorizationMode?: string;
      steps?: Array<{ name?: string; ok?: boolean }>;
      totals?: { images?: number; validMasks?: number };
    } | null;
    metrics?: Record<string, unknown> | null;
    manifest?: { version?: string; modelFile?: string } | null;
    finalAudit?: {
      ok?: boolean;
      decision?: { status?: "pass" | "needs_adjustment" | "blocked"; summary?: string; nextActions?: string[] };
      failureSummary?: {
        categoryCounts?: Record<string, number>;
      };
    } | null;
    finalAuditFailureSummary?: {
      categoryCounts?: Record<string, number>;
      totals?: {
        derivedAnnotationFailures?: number;
        inferredRecordFailure?: number;
        csvRows?: number;
      };
    } | null;
    recognitionPerformance?: RecognitionPerformanceReportLike | null;
    finalAuditTextureQualityGate?: {
      ok?: boolean;
      directlyUsableCount?: number;
      directlyUsableRate?: number;
      contaminatedCount?: number;
      contaminationRate?: number;
      totals?: {
        documents?: number;
        candidatesWithDebug?: number;
        directlyUsableCandidates?: number;
        contaminatedCandidates?: number;
      };
      rates?: {
        directlyUsableRate?: number | null;
        contaminationRate?: number | null;
        roughRectangleRate?: number | null;
      };
      evidence?: {
        ok?: boolean;
        scope?: string;
        representativeTestSplit?: boolean;
        documentsOk?: boolean;
        candidatesWithDebugOk?: boolean;
        candidatesWithPolygonOk?: boolean;
        minDocuments?: number;
        minCandidatesWithDebug?: number;
        minCandidatesWithPolygon?: number;
      };
      warningBreakdown?: Record<string, number>;
      warnings?: string[];
      nextSteps?: string[];
    } | null;
  };
  steps?: Array<{ name?: string; ok?: boolean }>;
}

interface RecognitionPerformanceReportLike {
  ok?: boolean;
  profile?: string;
  thresholds?: { maxElapsedMs?: number; minSamples?: number };
  totals?: { samples?: number; slowSamples?: number; skippedFiles?: number };
  stats?: { averageMs?: number | null; p95Ms?: number | null; maxMs?: number | null };
  errors?: string[];
  warnings?: string[];
  nextSteps?: string[];
}

interface CompareSummaryLike {
  ok: boolean;
  regressions?: string[];
  improvements?: string[];
  warnings?: string[];
  deltas?: {
    activeLearningImportedSamples?: number | null;
    activeLearningWarnings?: Record<string, number> | null;
    activeLearningBackends?: Record<string, number> | null;
    [key: string]: number | Record<string, number> | null | undefined;
  };
  baseline?: { version?: string } | null;
  candidate?: { version?: string } | null;
}

interface RegistryLike {
  currentVersion: string | null;
  releases: Array<{ version: string }>;
}

interface CliOptions {
  pipelineReportPath: string;
  compareSummaryPath?: string;
  performanceReportPath?: string;
  registryPath?: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report <training-release-pipeline-report.json> [--compare-summary <compare-summary.json>] [--performance-report <performance-report.json>] [--registry <release-registry.json>] [--output <release-decision-report.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let pipelineReportPath = "";
  let compareSummaryPath: string | undefined;
  let registryPath: string | undefined;
  let performanceReportPath: string | undefined;
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--pipeline-report") pipelineReportPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--compare-summary") compareSummaryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--registry") registryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--performance-report") performanceReportPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") outputPath = path.resolve(argv[++index] ?? usage());
    else usage();
  }

  if (!pipelineReportPath) usage();
  if (!outputPath) {
    outputPath = path.join(path.dirname(pipelineReportPath), "release-decision-report.json");
  }

  return { pipelineReportPath, compareSummaryPath, performanceReportPath, registryPath, outputPath };
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

function buildDecision(
  pipeline: PipelineReportLike,
  compare: CompareSummaryLike | null,
  recognitionPerformance: RecognitionPerformanceReportLike | null
): {
  status: "approve_candidate" | "hold_candidate" | "manual_review";
  summary: string;
  reasons: string[];
  nextActions: string[];
} {
  const reasons: string[] = [];
  const nextActions: string[] = [];

  if (!pipeline.ok) {
    reasons.push("training release pipeline did not pass");
    nextActions.push("Fix the failing pipeline step before considering release registration.");
  }

  const finalAuditStatus = pipeline.artifacts?.finalAudit?.decision?.status ?? "unknown";
  if (finalAuditStatus !== "pass") {
    reasons.push(`final audit status is ${finalAuditStatus}`);
    nextActions.push("Review final audit findings and rerun the release pipeline after adjustment.");
  }

  if (compare && !compare.ok) {
    reasons.push("candidate release comparison contains regressions");
    nextActions.push("Review compare-training-releases output and keep the baseline version available for rollback.");
  }

  const activeLearningWarningDelta = sumPositiveDeltas(compare?.deltas?.activeLearningWarnings);
  if (activeLearningWarningDelta > 0) {
    reasons.push(`active-learning warning signals increased by ${activeLearningWarningDelta}`);
    nextActions.push(
      "Review active-learning warning deltas before promotion; they may indicate model runtime, fallback, or postprocess regressions in corrected samples."
    );
  }

  if (recognitionPerformance?.ok === false) {
    const profile = recognitionPerformance.profile ?? "unknown";
    const slowSamples = recognitionPerformance.totals?.slowSamples ?? "unknown";
    const maxElapsedMs = recognitionPerformance.thresholds?.maxElapsedMs ?? "unknown";
    reasons.push(
      `recognition performance failed for ${profile} profile (${slowSamples} slow sample(s), budget ${maxElapsedMs}ms)`
    );
    nextActions.push(
      "Reduce model/runtime/postprocess latency or keep the candidate out of promotion until the performance gate passes."
    );
  }

  const trainingDatasetReadiness = pipeline.artifacts?.trainingDatasetReadiness ?? null;
  if (trainingDatasetReadiness?.ok === false) {
    const failingSteps =
      trainingDatasetReadiness.steps
        ?.filter((step) => step.ok === false)
        .map((step) => step.name ?? "unknown")
        .join(", ") || "unknown";
    reasons.push(`training dataset readiness failed (${failingSteps})`);
    nextActions.push(
      "Resolve source provenance, release authorization, and Phase 1 dataset coverage before retraining or promotion."
    );
  }

  const derivedAnnotationFailures = Number(
    pipeline.artifacts?.finalAuditFailureSummary?.totals?.derivedAnnotationFailures ?? 0
  );
  const postprocessFailures = Number(
    pipeline.artifacts?.finalAuditFailureSummary?.categoryCounts?.postprocess ?? 0
  );
  const textureQualityGate = pipeline.artifacts?.finalAuditTextureQualityGate ?? null;
  const textureQualityGateOk = textureQualityGate?.ok ?? null;
  const directlyUsableRate =
    textureQualityGate?.rates?.directlyUsableRate ??
    textureQualityGate?.directlyUsableRate ??
    null;
  const contaminationRate =
    textureQualityGate?.rates?.contaminationRate ??
    textureQualityGate?.contaminationRate ??
    null;
  const phase2ExtractionRateOk =
    typeof directlyUsableRate === "number" ? directlyUsableRate >= 0.8 : null;
  const phase2ExtractionEvidence = textureQualityGate?.evidence ?? null;
  const phase2ExtractionEvidenceOk = textureQualityGate
    ? phase2ExtractionEvidence?.ok === true &&
      phase2ExtractionEvidence.representativeTestSplit === true &&
      phase2ExtractionEvidence.scope === "release-test-split"
    : null;
  if (derivedAnnotationFailures > 0 || postprocessFailures > 0) {
    reasons.push(
      `final audit still reports ${postprocessFailures} postprocess failures and ${derivedAnnotationFailures} derived annotation failures`
    );
    if (finalAuditStatus === "pass" && pipeline.ok && (!compare || compare.ok)) {
      nextActions.push("Candidate is functional, but inspect failure summary before promoting as the new default.");
    }
  }

  if (phase2ExtractionRateOk === false) {
    reasons.push(
      `Phase 2 usable texture extraction rate ${directlyUsableRate?.toFixed(3)} is below required 0.800`
    );
    nextActions.push(
      "Improve test-split texture extraction to at least 80% before release promotion."
    );
  }
  if (phase2ExtractionEvidenceOk === false) {
    const evidenceScope = phase2ExtractionEvidence?.scope ?? "missing";
    reasons.push(`Phase 2 texture extraction evidence is not release-ready (${evidenceScope})`);
    nextActions.push(
      "Rerun the texture quality gate on a representative release test split with enough debug and polygon samples."
    );
  }
  if (textureQualityGateOk === false) {
    const usableRateText =
      typeof directlyUsableRate === "number" ? directlyUsableRate.toFixed(3) : "unknown";
    const contaminationRateText =
      typeof contaminationRate === "number" ? contaminationRate.toFixed(3) : "unknown";
    reasons.push(
      `texture quality gate failed (directly usable rate ${usableRateText}, contamination rate ${contaminationRateText})`
    );
    nextActions.push(
      "Review low-quality texture crops before promotion and improve directly usable coverage or reduce contamination."
    );
  }

  if (
    !pipeline.ok ||
    finalAuditStatus === "blocked" ||
    (compare && !compare.ok) ||
    recognitionPerformance?.ok === false ||
    trainingDatasetReadiness?.ok === false ||
    phase2ExtractionRateOk === false ||
    phase2ExtractionEvidenceOk === false
  ) {
    return {
      status: "hold_candidate",
      summary: "Do not promote this candidate yet.",
      reasons,
      nextActions,
    };
  }

  if (reasons.length > 0) {
    return {
      status: "manual_review",
      summary: "Core gates passed, but remaining failure signals still need human review.",
      reasons,
      nextActions: nextActions.length
        ? nextActions
        : ["Review failure summary and decide whether the remaining issues are acceptable for release."],
    };
  }

  return {
    status: "approve_candidate",
    summary: "Core release gates passed and no additional failure-summary concerns were detected.",
    reasons: [],
    nextActions: ["You can register this candidate version and preserve the report alongside the release decision."],
  };
}

function sumPositiveDeltas(record: Record<string, number> | null | undefined) {
  return Object.values(record ?? {}).reduce(
    (total, value) => total + (Number(value) > 0 ? Number(value) : 0),
    0
  );
}

const options = parseArgs(process.argv.slice(2));
const pipeline = await readJson<PipelineReportLike>(options.pipelineReportPath);
const compare = await readOptionalJson<CompareSummaryLike>(options.compareSummaryPath);
const performanceReport = await readOptionalJson<RecognitionPerformanceReportLike>(options.performanceReportPath);
const registry = await readOptionalJson<RegistryLike>(options.registryPath);

const manifest = pipeline.artifacts?.manifest ?? null;
const recognitionPerformance = performanceReport ?? pipeline.artifacts?.recognitionPerformance ?? null;
const decision = buildDecision(pipeline, compare, recognitionPerformance);
const decisionTextureQualityGate = pipeline.artifacts?.finalAuditTextureQualityGate ?? null;
const decisionDirectlyUsableRate =
  decisionTextureQualityGate?.rates?.directlyUsableRate ??
  decisionTextureQualityGate?.directlyUsableRate ??
  null;
const decisionContaminationRate =
  decisionTextureQualityGate?.rates?.contaminationRate ??
  decisionTextureQualityGate?.contaminationRate ??
  null;
const decisionPhase2ExtractionRateOk =
  typeof decisionDirectlyUsableRate === "number"
    ? decisionDirectlyUsableRate >= 0.8
    : null;
const decisionPhase2ExtractionEvidence = decisionTextureQualityGate?.evidence ?? null;
const decisionPhase2ExtractionEvidenceOk = decisionTextureQualityGate
  ? decisionPhase2ExtractionEvidence?.ok === true &&
    decisionPhase2ExtractionEvidence.representativeTestSplit === true &&
    decisionPhase2ExtractionEvidence.scope === "release-test-split"
  : null;

const summary = {
  ok: decision.status !== "hold_candidate",
  pipelineReportPath: options.pipelineReportPath,
  compareSummaryPath: options.compareSummaryPath ?? null,
  performanceReportPath: options.performanceReportPath ?? null,
  registryPath: options.registryPath ?? null,
  outputPath: options.outputPath,
  candidateVersion: manifest?.version ?? null,
  registryCurrentVersion: registry?.currentVersion ?? null,
  compareAvailable: Boolean(compare),
  decision,
  inputs: {
    pipelineOk: pipeline.ok,
    trainingDatasetReadinessOk:
      pipeline.artifacts?.trainingDatasetReadiness?.ok ?? null,
    finalAuditStatus: pipeline.artifacts?.finalAudit?.decision?.status ?? null,
    compareOk: compare ? compare.ok : null,
    activeLearningImportedSampleDelta:
      typeof compare?.deltas?.activeLearningImportedSamples === "number"
        ? compare.deltas.activeLearningImportedSamples
        : null,
    activeLearningWarningDelta: sumPositiveDeltas(compare?.deltas?.activeLearningWarnings),
    activeLearningWarningDeltas: compare?.deltas?.activeLearningWarnings ?? null,
    activeLearningBackendDeltas: compare?.deltas?.activeLearningBackends ?? null,
    recognitionPerformanceOk: recognitionPerformance?.ok ?? null,
    recognitionPerformanceProfile: recognitionPerformance?.profile ?? null,
    recognitionPerformanceMaxElapsedMs: recognitionPerformance?.thresholds?.maxElapsedMs ?? null,
    recognitionPerformanceP95Ms: recognitionPerformance?.stats?.p95Ms ?? null,
    recognitionPerformanceMaxMs: recognitionPerformance?.stats?.maxMs ?? null,
    recognitionPerformanceSlowSamples: recognitionPerformance?.totals?.slowSamples ?? null,
    derivedAnnotationFailures:
      pipeline.artifacts?.finalAuditFailureSummary?.totals?.derivedAnnotationFailures ?? 0,
    postprocessFailures: pipeline.artifacts?.finalAuditFailureSummary?.categoryCounts?.postprocess ?? 0,
    textureQualityGateOk: pipeline.artifacts?.finalAuditTextureQualityGate?.ok ?? null,
    phase2ExtractionRateOk: decisionPhase2ExtractionRateOk,
    phase2ExtractionEvidenceOk: decisionPhase2ExtractionEvidenceOk,
    phase2ExtractionEvidenceScope: decisionPhase2ExtractionEvidence?.scope ?? null,
    directlyUsableRate: decisionDirectlyUsableRate,
    contaminationRate: decisionContaminationRate,
  },
  artifacts: {
    manifest,
    trainingDatasetReadiness: pipeline.artifacts?.trainingDatasetReadiness ?? null,
    metrics: pipeline.artifacts?.metrics ?? null,
    finalAudit: pipeline.artifacts?.finalAudit ?? null,
    finalAuditFailureSummary: pipeline.artifacts?.finalAuditFailureSummary ?? null,
    finalAuditTextureQualityGate: pipeline.artifacts?.finalAuditTextureQualityGate ?? null,
    compareSummary: compare,
    recognitionPerformance,
    registry,
  },
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));

if (decision.status === "hold_candidate") {
  process.exitCode = 1;
}
