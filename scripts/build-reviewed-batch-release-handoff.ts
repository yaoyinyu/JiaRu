import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface ReviewedBatchImportPipelineReportLike {
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
  draft?: boolean;
  batch?: {
    rootDir?: string | null;
    sourceGroup?: string | null;
    datasetRoot?: string | null;
    reviewedImportReportPath?: string | null;
    importedFileCount?: number;
  } | null;
}

interface CliOptions {
  rootDir: string;
  reviewedBatchImportPipelineReportPath: string;
  releaseTraceDraftPath: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-reviewed-batch-release-handoff.ts --root-dir <seed-batch-dir> [--reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>] [--release-trace-draft <release-trace-draft.json>] [--output <reviewed-batch-release-handoff.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir = "";
  let reviewedBatchImportPipelineReportPath = "";
  let releaseTraceDraftPath = "";
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--root-dir") {
      rootDir = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--reviewed-batch-import-pipeline-report") {
      reviewedBatchImportPipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--release-trace-draft") {
      releaseTraceDraftPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (!rootDir) usage();
  if (!reviewedBatchImportPipelineReportPath) {
    reviewedBatchImportPipelineReportPath = path.join(rootDir, "reviewed-batch-import-pipeline-report.json");
  }
  if (!releaseTraceDraftPath) {
    releaseTraceDraftPath = path.join(rootDir, "release-trace-draft.json");
  }
  if (!outputPath) {
    outputPath = path.join(rootDir, "reviewed-batch-release-handoff.json");
  }

  return {
    rootDir,
    reviewedBatchImportPipelineReportPath,
    releaseTraceDraftPath,
    outputPath,
  };
}

async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

function findImportStep(report: ReviewedBatchImportPipelineReportLike) {
  return report.steps?.find((step) => step.name === "import-reviewed-batch");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reviewedBatchImportPipelineReport =
    await readJson<ReviewedBatchImportPipelineReportLike>(options.reviewedBatchImportPipelineReportPath);
  const releaseTraceDraft = await readJson<ReleaseTraceDraftLike>(options.releaseTraceDraftPath);
  const importStep = findImportStep(reviewedBatchImportPipelineReport);

  const summary = {
    ok: true,
    version: "reviewed-batch-release-handoff/v1",
    outputPath: options.outputPath,
    rootDir: options.rootDir,
    generatedAt: new Date().toISOString(),
    reviewedBatchImportPipelineReportPath: options.reviewedBatchImportPipelineReportPath,
    releaseTraceDraftPath: options.releaseTraceDraftPath,
    batch: {
      sourceGroup:
        importStep?.stdout?.sourceGroup ?? releaseTraceDraft.batch?.sourceGroup ?? null,
      datasetRoot:
        importStep?.stdout?.datasetRoot ?? releaseTraceDraft.batch?.datasetRoot ?? null,
      reviewedImportReportPath:
        importStep?.stdout?.reportPath ?? releaseTraceDraft.batch?.reviewedImportReportPath ?? null,
      importedFileCount:
        importStep?.stdout?.importedDocuments?.length ??
        releaseTraceDraft.batch?.importedFileCount ??
        0,
    },
    governanceHints: {
      reviewedBatchRootDir: options.rootDir,
      reviewedBatchImportPipelineReportPath: options.reviewedBatchImportPipelineReportPath,
      releaseTraceDraftPath: options.releaseTraceDraftPath,
    },
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
  console.log(JSON.stringify(summary, null, 2));
}

await main();
