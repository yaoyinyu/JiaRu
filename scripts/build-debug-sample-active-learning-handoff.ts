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
        priorityTier?: "high" | "medium" | "low" | null;
      }>;
      priorityFilters?: {
        reportPath?: string | null;
        minPriorityTier?: string | null;
        top?: number | null;
      };
      backendBreakdown?: Record<string, number>;
      modelBackendBreakdown?: Record<string, number>;
      correctedCandidateSourceBreakdown?: Record<string, number>;
      reasonBreakdown?: Record<string, number>;
    };
  }>;
}

interface ActiveLearningReleaseTraceDraftLike {
  activeLearning?: {
    importedSampleCount?: number;
    importedByPriority?: Record<string, number>;
    priorityFilters?: {
      reportPath?: string | null;
      minPriorityTier?: string | null;
      top?: number | null;
    } | null;
    prioritySummary?: {
      backendBreakdown?: Record<string, number> | null;
      modelBackendBreakdown?: Record<string, number> | null;
      correctedCandidateSourceBreakdown?: Record<string, number> | null;
      reasonBreakdown?: Record<string, number> | null;
    } | null;
  } | null;
}

interface CliOptions {
  pipelineReportPath: string;
  releaseTraceDraftPath: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-debug-sample-active-learning-handoff.ts --pipeline-report <debug-sample-active-learning-pipeline-report.json> [--release-trace-draft <active-learning-release-trace-draft.json>] [--output <debug-sample-active-learning-handoff.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let pipelineReportPath = "";
  let releaseTraceDraftPath = "";
  let outputPath = "";
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--pipeline-report") {
      pipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--release-trace-draft") {
      releaseTraceDraftPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else usage();
  }
  if (!pipelineReportPath) usage();
  if (!releaseTraceDraftPath) {
    releaseTraceDraftPath = path.join(path.dirname(pipelineReportPath), "active-learning-release-trace-draft.json");
  }
  if (!outputPath) {
    outputPath = path.join(path.dirname(pipelineReportPath), "debug-sample-active-learning-handoff.json");
  }
  return { pipelineReportPath, releaseTraceDraftPath, outputPath };
}

function findStep(report: ActiveLearningPipelineReportLike, name: string) {
  return report.steps?.find((step) => step.name === name);
}

const options = parseArgs(process.argv.slice(2));
const pipelineReport = JSON.parse(
  await readFile(options.pipelineReportPath, "utf8")
) as ActiveLearningPipelineReportLike;
const releaseTraceDraft = JSON.parse(
  await readFile(options.releaseTraceDraftPath, "utf8")
) as ActiveLearningReleaseTraceDraftLike;

const importStep = findStep(pipelineReport, "import-debug-sample");
const priorityStep = findStep(pipelineReport, "prioritize-debug-samples");

const summary = {
  ok: true,
  version: "debug-sample-active-learning-handoff/v1",
  outputPath: options.outputPath,
  generatedAt: new Date().toISOString(),
  pipelineReportPath: options.pipelineReportPath,
  releaseTraceDraftPath: options.releaseTraceDraftPath,
  activeLearning: {
    sampleDir: pipelineReport.sampleDir,
    imageDir: pipelineReport.imageDir,
    priorityReportPath: pipelineReport.priorityReportPath,
    importedSampleCount:
      importStep?.stdout?.imported ??
      releaseTraceDraft.activeLearning?.importedSampleCount ??
      0,
    importedByPriority:
      releaseTraceDraft.activeLearning?.importedByPriority ?? null,
    priorityFilters:
      importStep?.stdout?.priorityFilters ??
      releaseTraceDraft.activeLearning?.priorityFilters ??
      null,
    prioritySummary:
      releaseTraceDraft.activeLearning?.prioritySummary ??
      (priorityStep?.stdout
        ? {
            backendBreakdown: priorityStep.stdout.backendBreakdown ?? null,
            modelBackendBreakdown: priorityStep.stdout.modelBackendBreakdown ?? null,
            correctedCandidateSourceBreakdown:
              priorityStep.stdout.correctedCandidateSourceBreakdown ?? null,
            reasonBreakdown: priorityStep.stdout.reasonBreakdown ?? null,
          }
        : null),
  },
  governanceHints: {
    activeLearningPipelineReportPath: options.pipelineReportPath,
    activeLearningReleaseTraceDraftPath: options.releaseTraceDraftPath,
  },
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
