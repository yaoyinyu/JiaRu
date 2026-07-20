import path from "node:path";
import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";

interface MemorySample {
  iteration: number;
  usedJSHeapBytes: number;
  browserPrivateBytes: number;
  browserWorkingSetBytes: number;
  browserProcessCount: number;
}

interface MemoryReport {
  version: string;
  profile: string;
  sessionId?: string;
  deviceFamily?: string;
  modelVersion?: string;
  backend?: string;
  inputSize?: number;
  sampleCount: number;
  samples: MemorySample[];
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-recognition-memory.ts --input <report.json> [--output <verification.json>] [--min-samples 20] [--max-js-growth-mib 32] [--max-private-growth-mib 128] [--max-consecutive-growth 18]"
  );
}

const args = process.argv.slice(2);
let inputPath: string | undefined;
let outputPath: string | undefined;
let minSamples = 20;
let maxJsGrowthMiB = 32;
let maxPrivateGrowthMiB = 128;
let maxConsecutiveGrowth = 18;
for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--input") inputPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--output") outputPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--min-samples") minSamples = Number(args[++index] ?? usage());
  else if (arg === "--max-js-growth-mib") maxJsGrowthMiB = Number(args[++index] ?? usage());
  else if (arg === "--max-private-growth-mib") maxPrivateGrowthMiB = Number(args[++index] ?? usage());
  else if (arg === "--max-consecutive-growth") maxConsecutiveGrowth = Number(args[++index] ?? usage());
  else usage();
}
if (!inputPath) usage();

const report = JSON.parse(await readFile(inputPath, "utf8")) as MemoryReport;
const samples = report.samples ?? [];
const errors: string[] = [];
const warnings: string[] = [];
if (report.version !== "nail-texture-recognition-memory/v1") {
  errors.push(`unsupported report version ${report.version}`);
}
if (samples.length < minSamples) {
  errors.push(`sample count ${samples.length} is below required minimum ${minSamples}`);
}
if (report.sampleCount !== samples.length) {
  errors.push(`sampleCount ${report.sampleCount} does not match samples length ${samples.length}`);
}

function average(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function maxConsecutiveIncrease(values: number[]): number {
  let current = 0;
  let maximum = 0;
  for (let index = 1; index < values.length; index++) {
    current = values[index]! > values[index - 1]! ? current + 1 : 0;
    maximum = Math.max(maximum, current);
  }
  return maximum;
}

const windowSize = Math.min(5, Math.floor(samples.length / 2));
const first = samples.slice(0, windowSize);
const last = samples.slice(-windowSize);
const jsGrowthBytes = average(last.map((sample) => sample.usedJSHeapBytes)) -
  average(first.map((sample) => sample.usedJSHeapBytes));
const privateGrowthBytes = average(last.map((sample) => sample.browserPrivateBytes)) -
  average(first.map((sample) => sample.browserPrivateBytes));
const jsConsecutiveGrowth = maxConsecutiveIncrease(samples.map((sample) => sample.usedJSHeapBytes));
const privateConsecutiveGrowth = maxConsecutiveIncrease(samples.map((sample) => sample.browserPrivateBytes));
const mib = 1024 * 1024;

if (jsGrowthBytes > maxJsGrowthMiB * mib) {
  errors.push(`JS heap last-window growth ${(jsGrowthBytes / mib).toFixed(2)}MiB exceeds ${maxJsGrowthMiB}MiB`);
}
if (privateGrowthBytes > maxPrivateGrowthMiB * mib) {
  errors.push(`browser private last-window growth ${(privateGrowthBytes / mib).toFixed(2)}MiB exceeds ${maxPrivateGrowthMiB}MiB`);
}
if (jsConsecutiveGrowth > maxConsecutiveGrowth) {
  errors.push(`JS heap increased for ${jsConsecutiveGrowth} consecutive transitions`);
}
if (privateConsecutiveGrowth > maxConsecutiveGrowth) {
  errors.push(`browser private memory increased for ${privateConsecutiveGrowth} consecutive transitions`);
}
if (samples.some((sample) => sample.browserProcessCount === 0)) {
  warnings.push("Some samples did not resolve Chromium process memory; process-level statistics may be incomplete.");
}

const summary = {
  ok: errors.length === 0,
  inputPath,
  profile: report.profile,
  identity: {
    sessionId: report.sessionId ?? null,
    deviceFamily: report.deviceFamily ?? null,
    modelVersion: report.modelVersion ?? null,
    backend: report.backend ?? null,
    inputSize: report.inputSize ?? null,
  },
  thresholds: { minSamples, maxJsGrowthMiB, maxPrivateGrowthMiB, maxConsecutiveGrowth },
  totals: { samples: samples.length },
  stats: {
    peakUsedJSHeapMiB: Number((Math.max(0, ...samples.map((sample) => sample.usedJSHeapBytes)) / mib).toFixed(2)),
    peakBrowserPrivateMiB: Number((Math.max(0, ...samples.map((sample) => sample.browserPrivateBytes)) / mib).toFixed(2)),
    peakBrowserWorkingSetMiB: Number((Math.max(0, ...samples.map((sample) => sample.browserWorkingSetBytes)) / mib).toFixed(2)),
    jsLastWindowGrowthMiB: Number((jsGrowthBytes / mib).toFixed(2)),
    privateLastWindowGrowthMiB: Number((privateGrowthBytes / mib).toFixed(2)),
    jsConsecutiveGrowth,
    privateConsecutiveGrowth,
  },
  errors,
  warnings,
  nextSteps: errors.length === 0
    ? ["Desktop Chromium memory and repeated-run stability are within the provisional baseline gate."]
    : ["Inspect repeated-run cleanup and browser process memory before promotion."],
};
if (outputPath) await writeFile(outputPath, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) process.exitCode = 1;
