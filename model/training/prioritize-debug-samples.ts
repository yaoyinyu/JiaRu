import path from "node:path";
import process from "node:process";
import { readFile, readdir } from "node:fs/promises";
import {
  assessDebugSamplePriority,
  type DebugSamplePriorityAssessment,
} from "../../src/lib/nail-texture-debug-priority.ts";
import type { NailDebugSampleRecord } from "../../src/lib/nail-texture-debug-sample.ts";

interface CliOptions {
  samplePaths: string[];
  sampleDir?: string;
  top: number | null;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types model/training/prioritize-debug-samples.ts [--sample-dir <dir> | <debug-sample.json> ...] [--top <n>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  const samplePaths: string[] = [];
  let sampleDir: string | undefined;
  let top: number | null = null;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--sample-dir") {
      sampleDir = path.resolve(argv[++index] ?? usage());
      continue;
    }
    if (arg === "--top") {
      top = Number(argv[++index] ?? usage());
      if (!Number.isInteger(top) || top <= 0) {
        throw new Error("--top must be a positive integer");
      }
      continue;
    }
    samplePaths.push(path.resolve(arg));
  }

  if (sampleDir && samplePaths.length > 0) {
    throw new Error("Use either --sample-dir or positional sample paths, not both.");
  }
  if (!sampleDir && samplePaths.length === 0) usage();

  return { samplePaths, sampleDir, top };
}

async function listJsonFiles(dirPath: string): Promise<string[]> {
  const entries = await readdir(dirPath, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(dirPath, entry.name))
    .filter((filePath) => {
      const name = path.basename(filePath);
      return (
        name !== "prioritized-debug-samples.json" &&
        name !== "debug-sample-active-learning-pipeline-report.json"
      );
    })
    .sort();
}

async function readSample(filePath: string): Promise<NailDebugSampleRecord> {
  return JSON.parse(await readFile(filePath, "utf8")) as NailDebugSampleRecord;
}

function summarizeReasonBreakdown(items: Array<DebugSamplePriorityAssessment & { samplePath: string }>) {
  const breakdown: Record<string, number> = {};
  for (const item of items) {
    for (const reason of item.reasons) {
      breakdown[reason.code] = (breakdown[reason.code] ?? 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(breakdown).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

function summarizeBackendBreakdown(items: Array<DebugSamplePriorityAssessment & { samplePath: string }>) {
  const breakdown: Record<string, number> = {};
  for (const item of items) {
    const key = item.backend;
    breakdown[key] = (breakdown[key] ?? 0) + 1;
  }
  return breakdown;
}

function summarizeModelBackendBreakdown(items: Array<DebugSamplePriorityAssessment & { samplePath: string }>) {
  const breakdown: Record<string, number> = {};
  for (const item of items) {
    const key = item.modelBackend ?? "unknown";
    breakdown[key] = (breakdown[key] ?? 0) + 1;
  }
  return breakdown;
}

function summarizeCandidateSourceBreakdown(items: Array<DebugSamplePriorityAssessment & { samplePath: string; correctedCandidates: NailDebugSampleRecord["correctedCandidates"] }>) {
  const breakdown: Record<string, number> = {};
  for (const item of items) {
    for (const candidate of item.correctedCandidates) {
      const key = candidate.source;
      breakdown[key] = (breakdown[key] ?? 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(breakdown).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}

function summarizeWarningBreakdown(
  items: Array<DebugSamplePriorityAssessment & { samplePath: string; warnings: string[] }>
) {
  const breakdown: Record<string, number> = {};
  for (const item of items) {
    for (const warning of item.warnings) {
      breakdown[warning] = (breakdown[warning] ?? 0) + 1;
    }
  }
  return Object.fromEntries(Object.entries(breakdown).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
}
const options = parseArgs(process.argv.slice(2));
const samplePaths = options.sampleDir ? await listJsonFiles(options.sampleDir) : options.samplePaths;

const ranked = (
  await Promise.all(
    samplePaths.map(async (samplePath) => {
      const record = await readSample(samplePath);
      return {
        samplePath,
        correctedCandidates: record.correctedCandidates,
        warnings: record.warnings,
        ...(assessDebugSamplePriority(record)),
      };
    })
  )
).sort(
  (a, b) =>
    b.priorityScore - a.priorityScore ||
    a.imageId.localeCompare(b.imageId)
);

const limited = options.top ? ranked.slice(0, options.top) : ranked;

const summary = {
  ok: true,
  sampleCount: ranked.length,
  returnedCount: limited.length,
  filters: {
    sampleDir: options.sampleDir ?? null,
    top: options.top,
  },
  totals: {
    highPriority: ranked.filter((item) => item.priorityTier === "high").length,
    mediumPriority: ranked.filter((item) => item.priorityTier === "medium").length,
    lowPriority: ranked.filter((item) => item.priorityTier === "low").length,
  },
  backendBreakdown: summarizeBackendBreakdown(ranked),
  modelBackendBreakdown: summarizeModelBackendBreakdown(ranked),
  correctedCandidateSourceBreakdown: summarizeCandidateSourceBreakdown(ranked),
  warningBreakdown: summarizeWarningBreakdown(ranked),
  reasonBreakdown: summarizeReasonBreakdown(ranked),
  nextSteps: [
    "优先回收 high priority 样本进入人工复核与训练集导入。",
    "重点查看 high_confidence_deleted、manual_candidate_added 和 low_confidence_corrected 三类样本。",
    "如果 fallback_backend_used 或 model_runtime_warning 较多，优先复核模型可用性与 fallback 覆盖差距。",
  ],
  ranked: limited,
};

console.log(JSON.stringify(summary, null, 2));
