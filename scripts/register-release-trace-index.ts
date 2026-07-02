import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface ReleaseHistoryManifestLike {
  entries?: Array<{ traceIndexPath?: string | null }>;
  outputPath?: string;
}

interface CliOptions {
  traceIndexPath: string;
  historyManifestPath: string;
  outputPath: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/register-release-trace-index.ts --trace-index <release-trace-index.json> [--history-manifest <release-history-manifest.json>] [--output <trace-registration-report.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let traceIndexPath = "";
  let historyManifestPath = "";
  let outputPath = "";

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--trace-index") {
      traceIndexPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--history-manifest") {
      historyManifestPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (!traceIndexPath) usage();
  if (!historyManifestPath) {
    historyManifestPath = path.join(path.dirname(traceIndexPath), "release-history-manifest.json");
  }
  if (!outputPath) {
    outputPath = path.join(path.dirname(traceIndexPath), "trace-registration-report.json");
  }

  return { traceIndexPath, historyManifestPath, outputPath };
}

async function readOptionalJson<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const existing = await readOptionalJson<ReleaseHistoryManifestLike>(options.historyManifestPath);
  const existingTraceIndexPaths = Array.from(
    new Set(
      (existing?.entries ?? [])
        .map((entry) => entry.traceIndexPath)
        .filter((value): value is string => Boolean(value))
    )
  );

  if (!existingTraceIndexPaths.includes(options.traceIndexPath)) {
    existingTraceIndexPaths.push(options.traceIndexPath);
  }

  const command = [
    process.execPath,
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/build-release-history-manifest.ts",
    ...existingTraceIndexPaths.flatMap((item) => ["--trace-index", item]),
    "--output",
    options.historyManifestPath,
  ];

  const { stdout } = await execFileAsync(command[0]!, command.slice(1), {
    cwd: path.resolve("."),
  });
  const historyManifest = JSON.parse(stdout) as {
    totals?: { traceIndexes?: number };
    entries?: Array<{ traceIndexPath?: string | null }>;
    outputPath?: string;
  };

  const summary = {
    ok: true,
    traceIndexPath: options.traceIndexPath,
    historyManifestPath: options.historyManifestPath,
    outputPath: options.outputPath,
    traceIndexCount: historyManifest.totals?.traceIndexes ?? 0,
    includedTraceIndexes:
      historyManifest.entries
        ?.map((entry) => entry.traceIndexPath)
        .filter((value): value is string => Boolean(value)) ?? [],
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
  console.log(JSON.stringify(summary, null, 2));
}

await main();
