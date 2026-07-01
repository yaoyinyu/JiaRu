import path from "node:path";
import process from "node:process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface CliOptions {
  manifestPath: string;
  imagePath: string;
  outputDir: string;
  debugPrefix: string;
  annotationDirPath?: string;
  metricsPath?: string;
  dumpPath?: string;
  fixtureOutPath?: string;
  annotationPath?: string;
  uiReviewPath?: string;
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    outputDir: path.resolve("model/debug/real-model-final-audit"),
    debugPrefix: "real-model",
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") options.manifestPath = path.resolve(argv[++index]);
    else if (arg === "--image") options.imagePath = path.resolve(argv[++index]);
    else if (arg === "--output-dir") options.outputDir = path.resolve(argv[++index]);
    else if (arg === "--debug-prefix") options.debugPrefix = argv[++index];
    else if (arg === "--annotation-dir") options.annotationDirPath = path.resolve(argv[++index]);
    else if (arg === "--metrics") options.metricsPath = path.resolve(argv[++index]);
    else if (arg === "--dump") options.dumpPath = path.resolve(argv[++index]);
    else if (arg === "--fixture-out") options.fixtureOutPath = path.resolve(argv[++index]);
    else if (arg === "--annotation") options.annotationPath = path.resolve(argv[++index]);
    else if (arg === "--ui-review") options.uiReviewPath = path.resolve(argv[++index]);
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/run-real-model-final-audit.ts --image <image> [--manifest <manifest.json>] [--output-dir <dir>] [--debug-prefix <name>] [--annotation-dir <annotations-dir>] [--metrics <metrics.json>] [--dump <dump.json>] [--fixture-out <fixture.json>] [--annotation <green-annotation-image>] [--ui-review <ui-review.json>]"
      );
    }
  }

  if (!options.imagePath) {
    throw new Error("image path is required via --image");
  }

  return options as CliOptions;
}

async function runJsonScript(scriptPath: string, args: string[]) {
  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
      { cwd: path.resolve(".") }
    );
    return JSON.parse(stdout) as Record<string, unknown>;
  } catch (error) {
    const execError = error as { stdout?: string };
    if (execError.stdout) {
      return JSON.parse(execError.stdout) as Record<string, unknown>;
    }
    throw error;
  }
}

const options = parseArgs(process.argv.slice(2));
await mkdir(options.outputDir, { recursive: true });

const recordPath = path.join(options.outputDir, "real-model-first-run-record.json");
const finalReportPath = path.join(options.outputDir, "real-model-final-audit-report.json");
const failureSummaryPath = path.join(options.outputDir, "failure-case-summary.json");

const recordArgs = [
  "--manifest",
  options.manifestPath,
  "--image",
  options.imagePath,
  "--output",
  recordPath,
  "--debug-output-dir",
  options.outputDir,
  "--debug-prefix",
  options.debugPrefix,
];
if (options.metricsPath) recordArgs.push("--metrics", options.metricsPath);
if (options.dumpPath) recordArgs.push("--dump", options.dumpPath);
if (options.fixtureOutPath) recordArgs.push("--fixture-out", options.fixtureOutPath);
if (options.annotationPath) recordArgs.push("--annotation", options.annotationPath);
if (options.uiReviewPath) recordArgs.push("--ui-review", options.uiReviewPath);

const firstRunBuild = await runJsonScript("scripts/build-real-model-first-run-record.ts", recordArgs);
const firstRunRecord = JSON.parse(await readFile(recordPath, "utf8")) as {
  decision: { status: "pass" | "needs_adjustment" | "blocked"; summary: string; nextActions: string[] };
  readiness: { ok: boolean; warnings: string[] };
};
const failureSummaryArgs = [
  "--first-run-record",
  recordPath,
];
if (options.annotationDirPath) {
  failureSummaryArgs.push("--annotation-dir", options.annotationDirPath);
}
const failureSummary = await runJsonScript("scripts/summarize-failure-cases.ts", failureSummaryArgs);
await writeFile(failureSummaryPath, JSON.stringify(failureSummary, null, 2), "utf8");

const summary = {
  ok: firstRunRecord.decision.status === "pass",
  manifestPath: options.manifestPath,
  imagePath: options.imagePath,
  outputDir: options.outputDir,
  annotationDirPath: options.annotationDirPath ?? null,
  recordPath,
  failureSummaryPath,
  firstRunBuild,
  failureSummary,
  decision: firstRunRecord.decision,
  readiness: firstRunRecord.readiness,
  nextSteps:
    firstRunRecord.decision.status === "pass"
      ? [
          "Final audit passed. Preserve this report and continue with broader product-level regression.",
        ]
      : firstRunRecord.decision.nextActions,
};

await writeFile(finalReportPath, JSON.stringify(summary, null, 2), "utf8");
console.log(
  JSON.stringify(
    {
      ...summary,
      finalReportPath,
    },
    null,
    2
  )
);

if (!summary.ok) {
  process.exitCode = 1;
}
