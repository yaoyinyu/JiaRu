import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface ActiveLearningPipelineReportLike {
  ok: boolean;
  sampleDir: string;
  imageDir: string;
  reportPath: string;
  priorityReportPath: string;
  steps?: Array<{
    name?: string;
    stdout?: {
      reportPath?: string;
      imported?: number;
      outputs?: Array<{
        samplePath?: string;
        priorityTier?: "high" | "medium" | "low" | null;
        priorityScore?: number | null;
      }>;
      priorityFilters?: {
        reportPath?: string | null;
        minPriorityTier?: string | null;
        top?: number | null;
      };
      totals?: { images?: number; validMasks?: number };
      gates?: {
        imageCount?: { ok?: boolean; actual?: number; required?: number };
        validMaskCount?: { ok?: boolean; actual?: number; required?: number };
      };
      backendBreakdown?: Record<string, number>;
      modelBackendBreakdown?: Record<string, number>;
      correctedCandidateSourceBreakdown?: Record<string, number>;
      warningBreakdown?: Record<string, number>;
      reasonBreakdown?: Record<string, number>;
    };
  }>;
}

interface CliOptions {
  pipelineReportPath: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-active-learning-release-trace-draft.ts --pipeline-report <debug-sample-active-learning-pipeline-report.json> [--output <active-learning-release-trace-draft.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let pipelineReportPath = "";
  let outputPath = "";
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--pipeline-report") {
      pipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else usage();
  }
  if (!pipelineReportPath) usage();
  if (!outputPath) {
    outputPath = path.join(path.dirname(pipelineReportPath), "active-learning-release-trace-draft.json");
  }
  return { pipelineReportPath, outputPath };
}

function findStep(report: ActiveLearningPipelineReportLike, name: string) {
  return report.steps?.find((step) => step.name === name);
}

const options = parseArgs(process.argv.slice(2));
const report = JSON.parse(
  await readFile(options.pipelineReportPath, "utf8")
) as ActiveLearningPipelineReportLike;

const importStep = findStep(report, "import-debug-sample");
const readinessStep = findStep(report, "audit-phase1-readiness");
const priorityStep = findStep(report, "prioritize-debug-samples");

const outputs = importStep?.stdout?.outputs ?? [];
const importedByPriority = {
  high: outputs.filter((item) => item.priorityTier === "high").length,
  medium: outputs.filter((item) => item.priorityTier === "medium").length,
  low: outputs.filter((item) => item.priorityTier === "low").length,
  unknown: outputs.filter((item) => !item.priorityTier).length,
};

const summary = {
  ok: true,
  draft: true,
  outputPath: options.outputPath,
  candidateVersion: null,
  currentRegistryVersion: null,
  batch: null,
  activeLearning: {
    pipelineReportPath: options.pipelineReportPath,
    sampleDir: report.sampleDir,
    imageDir: report.imageDir,
    priorityReportPath: report.priorityReportPath,
    priorityFilters: importStep?.stdout?.priorityFilters ?? null,
    importedSampleCount: importStep?.stdout?.imported ?? 0,
    importedByPriority,
    importedSamples: outputs.map((item) => ({
      samplePath: item.samplePath ?? null,
      priorityTier: item.priorityTier ?? null,
      priorityScore: item.priorityScore ?? null,
    })),
    prioritySummary: priorityStep?.stdout
      ? {
          backendBreakdown: priorityStep.stdout.backendBreakdown ?? null,
          modelBackendBreakdown: priorityStep.stdout.modelBackendBreakdown ?? null,
          correctedCandidateSourceBreakdown:
            priorityStep.stdout.correctedCandidateSourceBreakdown ?? null,
          warningBreakdown: priorityStep.stdout.warningBreakdown ?? null,
          reasonBreakdown: priorityStep.stdout.reasonBreakdown ?? null,
        }
      : null,
    readinessSnapshot: readinessStep?.stdout
      ? {
          reportPath: readinessStep.stdout.reportPath ?? null,
          imageCountGate: readinessStep.stdout.gates?.imageCount ?? null,
          validMaskCountGate: readinessStep.stdout.gates?.validMaskCount ?? null,
          totals: readinessStep.stdout.totals ?? null,
        }
      : null,
  },
  release: {
    trainingReleasePipelineReportPath: null,
    manifestPath: null,
    metricsPath: null,
    trainOutputDir: null,
    finalAuditReportPath: null,
    finalAuditFailureSummaryPath: null,
    firstRunRecordPath: null,
    finalAuditStatus: null,
    derivedAnnotationFailures: 0,
    postprocessFailures: 0,
  },
  decision: null,
  promotion: null,
  registry: null,
  links: {
    sourceGroupToCandidateVersion: null,
    candidateVersionToFinalAudit: null,
    candidateVersionToDecision: null,
    candidateVersionToRegistry: null,
  },
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
