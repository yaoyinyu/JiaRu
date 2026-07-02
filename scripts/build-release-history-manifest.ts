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
  release?: {
    trainingReleasePipelineReportPath?: string | null;
    finalAuditStatus?: string | null;
    derivedAnnotationFailures?: number;
    postprocessFailures?: number;
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
    decisionStatus: trace.decision?.status ?? null,
    decisionSummary: trace.decision?.summary ?? null,
    registeredVersion: trace.promotion?.registeredVersion ?? null,
    currentRegistryVersion:
      trace.promotion?.currentVersion ?? trace.registry?.currentVersion ?? trace.currentRegistryVersion ?? null,
    sourceGroupToCandidateVersion: trace.links?.sourceGroupToCandidateVersion ?? null,
    trainingReleasePipelineReportPath: trace.release?.trainingReleasePipelineReportPath ?? null,
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

const registeredVersions = Array.from(
  new Set(entries.map((entry) => entry.registeredVersion).filter(Boolean))
);
const sourceGroups = Array.from(
  new Set(entries.map((entry) => entry.sourceGroup).filter(Boolean))
);

const summary = {
  ok: true,
  outputPath: options.outputPath,
  totals: {
    traceIndexes: entries.length,
    uniqueCandidateVersions: new Set(entries.map((entry) => entry.candidateVersion).filter(Boolean)).size,
    uniqueSourceGroups: sourceGroups.length,
    registeredVersions: registeredVersions.length,
  },
  decisionCounts,
  finalAuditStatusCounts,
  sourceGroups,
  registeredVersions,
  entries,
};

await mkdir(path.dirname(options.outputPath), { recursive: true });
await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
