import path from "node:path";
import process from "node:process";
import { readdir, readFile, writeFile } from "node:fs/promises";

type PerformanceProfile = "desktop" | "mobile";

interface CliOptions {
  inputs: string[];
  sampleDir?: string;
  outputPath?: string;
  profile: PerformanceProfile;
  maxElapsedMs: number;
  maxClientOverheadMs?: number;
  minSamples: number;
}

interface TimingSample {
  filePath: string;
  imageId: string | null;
  backend: string | null;
  modelVersion: string | null;
  elapsedMs: number;
  workerElapsedMs: number | null;
  clientOverheadMs: number | null;
}

const PROFILE_BUDGETS: Record<PerformanceProfile, number> = {
  desktop: 800,
  mobile: 1500,
};

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-recognition-performance.ts [--profile desktop|mobile] [--max-elapsed-ms <n>] [--max-client-overhead-ms <n>] [--min-samples <n>] [--sample-dir <dir>] [--output <report.json>] <debug-json-or-sample.json>..."
  );
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    inputs: [],
    profile: "desktop",
    maxElapsedMs: PROFILE_BUDGETS.desktop,
    minSamples: 1,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--profile") {
      const profile = argv[++index] as PerformanceProfile | undefined;
      if (profile !== "desktop" && profile !== "mobile") usage();
      options.profile = profile;
      options.maxElapsedMs = PROFILE_BUDGETS[profile];
    } else if (arg === "--max-elapsed-ms") {
      options.maxElapsedMs = Number(argv[++index] ?? usage());
    } else if (arg === "--max-client-overhead-ms") {
      options.maxClientOverheadMs = Number(argv[++index] ?? usage());
    } else if (arg === "--min-samples") {
      options.minSamples = Number(argv[++index] ?? usage());
    } else if (arg === "--sample-dir") {
      options.sampleDir = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      options.outputPath = path.resolve(argv[++index] ?? usage());
    } else if (arg.startsWith("--")) {
      usage();
    } else {
      options.inputs.push(path.resolve(arg));
    }
  }

  if (!Number.isFinite(options.maxElapsedMs) || options.maxElapsedMs <= 0) {
    throw new Error("--max-elapsed-ms must be a positive number");
  }
  if (!Number.isInteger(options.minSamples) || options.minSamples < 1) {
    throw new Error("--min-samples must be a positive integer");
  }
  if (
    options.maxClientOverheadMs != null &&
    (!Number.isFinite(options.maxClientOverheadMs) || options.maxClientOverheadMs < 0)
  ) {
    throw new Error("--max-client-overhead-ms must be zero or a positive number");
  }

  return options;
}

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

async function collectJsonFiles(dirPath: string): Promise<string[]> {
  const entries = await readdir(dirPath, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".json"))
    .map((entry) => path.join(dirPath, entry.name))
    .sort();
}

async function loadSample(filePath: string): Promise<TimingSample | null> {
  const document = JSON.parse(await readFile(filePath, "utf8")) as Record<string, unknown>;
  const elapsedMs = toNumber(document.elapsedMs);
  if (elapsedMs == null) return null;
  const workerElapsedMs = toNumber(document.workerElapsedMs);

  return {
    filePath,
    imageId: toStringOrNull(document.imageId) ?? toStringOrNull(document.input),
    backend: toStringOrNull(document.backend),
    modelVersion: toStringOrNull(document.modelVersion),
    elapsedMs,
    workerElapsedMs,
    clientOverheadMs:
      workerElapsedMs == null ? null : Math.max(0, elapsedMs - workerElapsedMs),
  };
}

function percentile(values: number[], ratio: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * ratio) - 1);
  return Number(sorted[index]!.toFixed(2));
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2));
}

const options = parseArgs(process.argv.slice(2));
const inputPaths = [
  ...options.inputs,
  ...(options.sampleDir ? await collectJsonFiles(options.sampleDir) : []),
];

const samples: TimingSample[] = [];
const skippedFiles: string[] = [];
for (const filePath of inputPaths) {
  const sample = await loadSample(filePath);
  if (sample) samples.push(sample);
  else skippedFiles.push(filePath);
}

const elapsedValues = samples.map((sample) => sample.elapsedMs);
const workerElapsedValues = samples
  .map((sample) => sample.workerElapsedMs)
  .filter((value): value is number => value != null);
const clientOverheadValues = samples
  .map((sample) => sample.clientOverheadMs)
  .filter((value): value is number => value != null);
const slowSamples = samples.filter((sample) => sample.elapsedMs > options.maxElapsedMs);
const slowClientOverheadSamples =
  options.maxClientOverheadMs == null
    ? []
    : samples.filter(
        (sample) =>
          sample.clientOverheadMs != null &&
          sample.clientOverheadMs > options.maxClientOverheadMs!
      );
const missingWorkerTimingSamples = samples.filter((sample) => sample.workerElapsedMs == null);
const errors: string[] = [];
if (samples.length < options.minSamples) {
  errors.push(`sample count ${samples.length} is below required minimum ${options.minSamples}`);
}
if (slowSamples.length > 0) {
  errors.push(`${slowSamples.length} sample(s) exceeded ${options.profile} budget ${options.maxElapsedMs}ms`);
}
if (slowClientOverheadSamples.length > 0) {
  errors.push(
    `${slowClientOverheadSamples.length} sample(s) exceeded client overhead budget ${options.maxClientOverheadMs}ms`
  );
}

const warnings = [
  ...(skippedFiles.length > 0 ? ["Some JSON files did not contain elapsedMs and were skipped."] : []),
  ...(missingWorkerTimingSamples.length > 0
    ? [
        `${missingWorkerTimingSamples.length} sample(s) did not contain workerElapsedMs; client overhead stats are incomplete.`,
      ]
    : []),
];

const summary = {
  ok: errors.length === 0,
  profile: options.profile,
  thresholds: {
    maxElapsedMs: options.maxElapsedMs,
    maxClientOverheadMs: options.maxClientOverheadMs ?? null,
    minSamples: options.minSamples,
  },
  totals: {
    inputFiles: inputPaths.length,
    samples: samples.length,
    skippedFiles: skippedFiles.length,
    slowSamples: slowSamples.length,
    slowClientOverheadSamples: slowClientOverheadSamples.length,
    missingWorkerTimingSamples: missingWorkerTimingSamples.length,
  },
  stats: {
    averageMs: average(elapsedValues),
    p50Ms: percentile(elapsedValues, 0.5),
    p95Ms: percentile(elapsedValues, 0.95),
    maxMs: elapsedValues.length > 0 ? Number(Math.max(...elapsedValues).toFixed(2)) : null,
    averageWorkerMs: average(workerElapsedValues),
    p95WorkerMs: percentile(workerElapsedValues, 0.95),
    averageClientOverheadMs: average(clientOverheadValues),
    p95ClientOverheadMs: percentile(clientOverheadValues, 0.95),
  },
  samples,
  slowSamples,
  slowClientOverheadSamples,
  skippedFiles,
  errors,
  warnings,
  nextSteps:
    errors.length === 0
      ? ["Recognition performance is within the selected budget."]
      : ["Review slow samples, model backend selection, and postprocess cost before promotion."],
};

if (options.outputPath) {
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
}

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) {
  process.exitCode = 1;
}