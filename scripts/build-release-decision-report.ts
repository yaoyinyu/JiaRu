import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface PipelineReportLike {
  ok: boolean;
  reportPath?: string;
  artifacts?: {
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
    finalAuditTextureQualityGate?: {
      ok?: boolean;
      directlyUsableCount?: number;
      directlyUsableRate?: number;
      contaminatedCount?: number;
      contaminationRate?: number;
      warningBreakdown?: Record<string, number>;
      warnings?: string[];
      nextSteps?: string[];
    } | null;
  };
  steps?: Array<{ name?: string; ok?: boolean }>;
}

interface CompareSummaryLike {
  ok: boolean;
  regressions?: string[];
  improvements?: string[];
  warnings?: string[];
  deltas?: Record<string, number | null>;
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
  registryPath?: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-release-decision-report.ts --pipeline-report <training-release-pipeline-report.json> [--compare-summary <compare-summary.json>] [--registry <release-registry.json>] [--output <release-decision-report.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let pipelineReportPath = "";
  let compareSummaryPath: string | undefined;
  let registryPath: string | undefined;
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--pipeline-report") pipelineReportPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--compare-summary") compareSummaryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--registry") registryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") outputPath = path.resolve(argv[++index] ?? usage());
    else usage();
  }

  if (!pipelineReportPath) usage();
  if (!outputPath) {
    outputPath = path.join(path.dirname(pipelineReportPath), "release-decision-report.json");
  }

  return { pipelineReportPath, compareSummaryPath, registryPath, outputPath };
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
  compare: CompareSummaryLike | null
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

  const derivedAnnotationFailures = Number(
    pipeline.artifacts?.finalAuditFailureSummary?.totals?.derivedAnnotationFailures ?? 0
  );
  const postprocessFailures = Number(
    pipeline.artifacts?.finalAuditFailureSummary?.categoryCounts?.postprocess ?? 0
  );
  const textureQualityGate = pipeline.artifacts?.finalAuditTextureQualityGate ?? null;
  const textureQualityGateOk = textureQualityGate?.ok ?? null;
  const directlyUsableRate = textureQualityGate?.directlyUsableRate ?? null;
  const contaminationRate = textureQualityGate?.contaminationRate ?? null;
  if (derivedAnnotationFailures > 0 || postprocessFailures > 0) {
    reasons.push(
      `final audit still reports ${postprocessFailures} postprocess failures and ${derivedAnnotationFailures} derived annotation failures`
    );
    if (finalAuditStatus === "pass" && pipeline.ok && (!compare || compare.ok)) {
      nextActions.push("Candidate is functional, but inspect failure summary before promoting as the new default.");
    }
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

  if (!pipeline.ok || finalAuditStatus === "blocked" || (compare && !compare.ok)) {
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

const options = parseArgs(process.argv.slice(2));
const pipeline = await readJson<PipelineReportLike>(options.pipelineReportPath);
const compare = await readOptionalJson<CompareSummaryLike>(options.compareSummaryPath);
const registry = await readOptionalJson<RegistryLike>(options.registryPath);

const manifest = pipeline.artifacts?.manifest ?? null;
const decision = buildDecision(pipeline, compare);

const summary = {
  ok: decision.status !== "hold_candidate",
  pipelineReportPath: options.pipelineReportPath,
  compareSummaryPath: options.compareSummaryPath ?? null,
  registryPath: options.registryPath ?? null,
  outputPath: options.outputPath,
  candidateVersion: manifest?.version ?? null,
  registryCurrentVersion: registry?.currentVersion ?? null,
  compareAvailable: Boolean(compare),
  decision,
  inputs: {
    pipelineOk: pipeline.ok,
    finalAuditStatus: pipeline.artifacts?.finalAudit?.decision?.status ?? null,
    compareOk: compare ? compare.ok : null,
    derivedAnnotationFailures:
      pipeline.artifacts?.finalAuditFailureSummary?.totals?.derivedAnnotationFailures ?? 0,
    postprocessFailures: pipeline.artifacts?.finalAuditFailureSummary?.categoryCounts?.postprocess ?? 0,
    textureQualityGateOk: pipeline.artifacts?.finalAuditTextureQualityGate?.ok ?? null,
    directlyUsableRate: pipeline.artifacts?.finalAuditTextureQualityGate?.directlyUsableRate ?? null,
    contaminationRate: pipeline.artifacts?.finalAuditTextureQualityGate?.contaminationRate ?? null,
  },
  artifacts: {
    manifest,
    metrics: pipeline.artifacts?.metrics ?? null,
    finalAudit: pipeline.artifacts?.finalAudit ?? null,
    finalAuditFailureSummary: pipeline.artifacts?.finalAuditFailureSummary ?? null,
    finalAuditTextureQualityGate: pipeline.artifacts?.finalAuditTextureQualityGate ?? null,
    compareSummary: compare,
    registry,
  },
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));

if (decision.status === "hold_candidate") {
  process.exitCode = 1;
}
