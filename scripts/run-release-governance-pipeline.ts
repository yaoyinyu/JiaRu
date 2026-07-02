import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface CliOptions {
  trainingReleasePipelineReportPath: string;
  compareSummaryPath?: string;
  registryPath?: string;
  releaseTraceDraftPath?: string;
  reviewedBatchImportPipelineReportPath?: string;
  historyManifestPath?: string;
  decisionReportPath: string;
  promotionReportPath: string;
  traceIndexPath: string;
  traceRegistrationReportPath: string;
  outputPath: string;
  allowManualReview: boolean;
  setCurrent: boolean;
  promote: boolean;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
  command: string[];
}

function findStep(steps: StepResult[], name: string): StepResult | undefined {
  return steps.find((step) => step.name === name);
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/run-release-governance-pipeline.ts --training-release-pipeline-report <training-release-pipeline-report.json> [--compare-summary <compare-summary.json>] [--registry <release-registry.json>] [--release-trace-draft <release-trace-draft.json>] [--reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>] [--history-manifest <release-history-manifest.json>] [--decision-report <release-decision-report.json>] [--promotion-report <promotion-report.json>] [--trace-index <release-trace-index.json>] [--trace-registration-report <trace-registration-report.json>] [--output <release-governance-pipeline-report.json>] [--allow-manual-review true|false] [--set-current true|false] [--promote true|false]"
  );
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  usage();
}

function parseArgs(argv: string[]): CliOptions {
  let trainingReleasePipelineReportPath = "";
  let compareSummaryPath: string | undefined;
  let registryPath: string | undefined;
  let releaseTraceDraftPath: string | undefined;
  let reviewedBatchImportPipelineReportPath: string | undefined;
  let historyManifestPath: string | undefined;
  let decisionReportPath = "";
  let promotionReportPath = "";
  let traceIndexPath = "";
  let traceRegistrationReportPath = "";
  let outputPath = "";
  let allowManualReview = false;
  let setCurrent = true;
  let promote = true;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--training-release-pipeline-report") {
      trainingReleasePipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--compare-summary") {
      compareSummaryPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--registry") {
      registryPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--release-trace-draft") {
      releaseTraceDraftPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--reviewed-batch-import-pipeline-report") {
      reviewedBatchImportPipelineReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--history-manifest") {
      historyManifestPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--decision-report") {
      decisionReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--promotion-report") {
      promotionReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--trace-index") {
      traceIndexPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--trace-registration-report") {
      traceRegistrationReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      outputPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--allow-manual-review") {
      allowManualReview = parseBoolean(argv[++index] ?? usage());
    } else if (arg === "--set-current") {
      setCurrent = parseBoolean(argv[++index] ?? usage());
    } else if (arg === "--promote") {
      promote = parseBoolean(argv[++index] ?? usage());
    } else {
      usage();
    }
  }

  if (!trainingReleasePipelineReportPath) usage();

  const reportDir = path.dirname(trainingReleasePipelineReportPath);
  if (!decisionReportPath) decisionReportPath = path.join(reportDir, "release-decision-report.json");
  if (!promotionReportPath) promotionReportPath = path.join(reportDir, "promotion-report.json");
  if (!traceIndexPath) traceIndexPath = path.join(reportDir, "release-trace-index.json");
  if (!traceRegistrationReportPath) {
    traceRegistrationReportPath = path.join(reportDir, "trace-registration-report.json");
  }
  if (!outputPath) outputPath = path.join(reportDir, "release-governance-pipeline-report.json");

  return {
    trainingReleasePipelineReportPath,
    compareSummaryPath,
    registryPath,
    releaseTraceDraftPath,
    reviewedBatchImportPipelineReportPath,
    historyManifestPath,
    decisionReportPath,
    promotionReportPath,
    traceIndexPath,
    traceRegistrationReportPath,
    outputPath,
    allowManualReview,
    setCurrent,
    promote,
  };
}

function tryParseJson(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
}

async function runCommand(name: string, command: string[], cwd: string): Promise<StepResult> {
  try {
    const { stdout } = await execFileAsync(command[0]!, command.slice(1), { cwd });
    return {
      name,
      ok: true,
      stdout: tryParseJson(stdout),
      command,
    };
  } catch (error) {
    const execError = error as Error & { stdout?: string; stderr?: string };
    return {
      name,
      ok: false,
      stdout: execError.stdout ? tryParseJson(execError.stdout) : undefined,
      stderr: execError.stderr || execError.message,
      command,
    };
  }
}

async function readJsonIfExists(filePath?: string): Promise<unknown | null> {
  if (!filePath) return null;
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function finish(options: CliOptions, steps: StepResult[]) {
  const decisionStep = findStep(steps, "build-release-decision-report");
  const promotionStep = findStep(steps, "promote-approved-release");
  const traceIndexStep = findStep(steps, "build-release-trace-index");
  const traceRegistrationStep = findStep(steps, "register-release-trace-index");

  const decisionStatus =
    typeof decisionStep?.stdout === "object" &&
    decisionStep.stdout !== null &&
    "decision" in decisionStep.stdout &&
    typeof (decisionStep.stdout as { decision?: { status?: unknown } }).decision?.status === "string"
      ? String((decisionStep.stdout as { decision: { status: string } }).decision.status)
      : null;
  const promotionAttempted = promotionStep?.command.length ? true : false;
  const promotionSucceeded = promotionAttempted ? Boolean(promotionStep?.ok) : !options.promote;
  const decisionAllowsPromotion =
    decisionStatus === "approve_candidate" ||
    (decisionStatus === "manual_review" && options.allowManualReview);
  const reportOk =
    Boolean(traceIndexStep?.ok) &&
    Boolean(traceRegistrationStep?.ok) &&
    decisionAllowsPromotion &&
    promotionSucceeded;

  const report = {
    ok: reportOk,
    outputPath: options.outputPath,
    inputs: {
      trainingReleasePipelineReportPath: options.trainingReleasePipelineReportPath,
      compareSummaryPath: options.compareSummaryPath ?? null,
      registryPath: options.registryPath ?? null,
      releaseTraceDraftPath: options.releaseTraceDraftPath ?? null,
      reviewedBatchImportPipelineReportPath: options.reviewedBatchImportPipelineReportPath ?? null,
      historyManifestPath: options.historyManifestPath ?? null,
      allowManualReview: options.allowManualReview,
      setCurrent: options.setCurrent,
      promote: options.promote,
    },
    paths: {
      decisionReportPath: options.decisionReportPath,
      promotionReportPath: options.promotionReportPath,
      traceIndexPath: options.traceIndexPath,
      traceRegistrationReportPath: options.traceRegistrationReportPath,
    },
    steps,
    artifacts: {
      trainingReleasePipeline: await readJsonIfExists(options.trainingReleasePipelineReportPath),
      releaseDecision: (await readJsonIfExists(options.decisionReportPath)) ?? decisionStep?.stdout ?? null,
      promotion: (await readJsonIfExists(options.promotionReportPath)) ?? promotionStep?.stdout ?? null,
      traceIndex: (await readJsonIfExists(options.traceIndexPath)) ?? traceIndexStep?.stdout ?? null,
      traceRegistration:
        (await readJsonIfExists(options.traceRegistrationReportPath)) ??
        traceRegistrationStep?.stdout ??
        null,
      historyManifest: await readJsonIfExists(
        options.historyManifestPath ?? path.join(path.dirname(options.traceIndexPath), "release-history-manifest.json")
      ),
    },
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const cwd = path.resolve(".");
  const steps: StepResult[] = [];

  const decisionCommand = [
    process.execPath,
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/build-release-decision-report.ts",
    "--pipeline-report",
    options.trainingReleasePipelineReportPath,
    "--output",
    options.decisionReportPath,
    ...(options.compareSummaryPath ? ["--compare-summary", options.compareSummaryPath] : []),
    ...(options.registryPath ? ["--registry", options.registryPath] : []),
  ];
  const decisionResult = await runCommand("build-release-decision-report", decisionCommand, cwd);
  steps.push(decisionResult);

  let promotionResult: StepResult = {
    name: "promote-approved-release",
    ok: true,
    stdout: {
      skipped: true,
      reason: options.promote
        ? "promotion was skipped because release decision did not allow automatic promotion"
        : "promotion was disabled by --promote false",
    },
    command: [],
  };

  const decisionStatus =
    typeof decisionResult.stdout === "object" &&
    decisionResult.stdout !== null &&
    "decision" in decisionResult.stdout &&
    typeof (decisionResult.stdout as { decision?: { status?: unknown } }).decision?.status === "string"
      ? String((decisionResult.stdout as { decision: { status: string } }).decision.status)
      : null;

  const shouldAttemptPromotion =
    options.promote &&
    (decisionStatus === "approve_candidate" ||
      (decisionStatus === "manual_review" && options.allowManualReview));

  if (shouldAttemptPromotion) {
    const promotionCommand = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/promote-approved-release.ts",
      "--decision-report",
      options.decisionReportPath,
      "--output",
      options.promotionReportPath,
      "--set-current",
      String(options.setCurrent),
      "--allow-manual-review",
      String(options.allowManualReview),
      ...(options.registryPath ? ["--registry", options.registryPath] : []),
    ];
    promotionResult = await runCommand("promote-approved-release", promotionCommand, cwd);
  }
  steps.push(promotionResult);
  const promotionWasExecuted = promotionResult.command.length > 0;

  const traceIndexCommand = [
    process.execPath,
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/build-release-trace-index.ts",
    "--training-release-pipeline-report",
    options.trainingReleasePipelineReportPath,
    "--release-decision-report",
    options.decisionReportPath,
    "--output",
    options.traceIndexPath,
    ...(options.releaseTraceDraftPath ? ["--release-trace-draft", options.releaseTraceDraftPath] : []),
    ...(options.reviewedBatchImportPipelineReportPath
      ? ["--reviewed-batch-import-pipeline-report", options.reviewedBatchImportPipelineReportPath]
      : []),
    ...(promotionWasExecuted && promotionResult.ok ? ["--promotion-report", options.promotionReportPath] : []),
    ...(options.registryPath ? ["--registry", options.registryPath] : []),
  ];
  const traceIndexResult = await runCommand("build-release-trace-index", traceIndexCommand, cwd);
  steps.push(traceIndexResult);

  let traceRegistrationResult: StepResult = {
    name: "register-release-trace-index",
    ok: true,
    stdout: {
      skipped: !(promotionWasExecuted && promotionResult.ok),
      reason:
        promotionWasExecuted && promotionResult.ok
          ? "trace registration skipped because trace index step did not run"
          : "trace history registration only runs after a successful promotion",
    },
    command: [],
  };

  if (promotionWasExecuted && promotionResult.ok && traceIndexResult.ok) {
    const traceRegistrationCommand = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-release-trace-index.ts",
      "--trace-index",
      options.traceIndexPath,
      "--output",
      options.traceRegistrationReportPath,
      ...(options.historyManifestPath ? ["--history-manifest", options.historyManifestPath] : []),
    ];
    traceRegistrationResult = await runCommand(
      "register-release-trace-index",
      traceRegistrationCommand,
      cwd
    );
  }
  steps.push(traceRegistrationResult);

  await finish(options, steps);
}

await main();
