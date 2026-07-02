import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";

interface ReviewedImportReportLike {
  ok: boolean;
  rootDir: string;
  datasetRoot: string;
  sourceGroup: string;
  reportPath: string;
  importedDocuments?: Array<{ fileName?: string }>;
}

interface CliOptions {
  reviewedImportReportPath: string;
  rootDir: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-initial-release-trace-draft.ts --reviewed-import-report <reviewed-import-*.report.json> --root-dir <seed-batch-dir> [--output <release-trace-draft.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let reviewedImportReportPath = "";
  let rootDir = "";
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--reviewed-import-report") {
      reviewedImportReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--root-dir") {
      rootDir = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (!reviewedImportReportPath || !rootDir) usage();
  if (!outputPath) {
    outputPath = path.join(rootDir, "release-trace-draft.json");
  }

  return { reviewedImportReportPath, rootDir, outputPath };
}

const options = parseArgs(process.argv.slice(2));
const reviewedImportReport = JSON.parse(
  await readFile(options.reviewedImportReportPath, "utf8")
) as ReviewedImportReportLike;

const summary = {
  ok: true,
  draft: true,
  outputPath: options.outputPath,
  candidateVersion: null,
  currentRegistryVersion: null,
  batch: {
    rootDir: options.rootDir,
    sourceGroup: reviewedImportReport.sourceGroup,
    datasetRoot: reviewedImportReport.datasetRoot,
    reviewedImportReportPath: reviewedImportReport.reportPath,
    importedFileCount: reviewedImportReport.importedDocuments?.length ?? 0,
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
