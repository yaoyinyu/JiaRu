import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface ReleaseDecisionReportLike {
  pipelineReportPath: string;
  candidateVersion: string | null;
  decision: {
    status: "approve_candidate" | "manual_review" | "hold_candidate";
    summary: string;
    reasons: string[];
    nextActions: string[];
  };
}

interface PipelineReportLike {
  paths?: {
    manifestPath?: string;
  };
}

interface RegisterSummaryLike {
  ok: boolean;
  manifestPath: string;
  registryPath: string;
  snapshotPath: string;
  currentVersion: string | null;
  releaseCount: number;
  registeredVersion: string;
}

interface TraceRegistrationSummaryLike {
  ok: boolean;
  traceIndexPath: string;
  historyManifestPath: string;
  outputPath: string;
  traceIndexCount: number;
  includedTraceIndexes: string[];
}

interface CliOptions {
  decisionReportPath: string;
  registryPath?: string;
  traceIndexPath?: string;
  historyManifestPath?: string;
  traceRegistrationOutputPath?: string;
  outputPath: string;
  setCurrent: boolean;
  allowManualReview: boolean;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/promote-approved-release.ts --decision-report <release-decision-report.json> [--registry <release-registry.json>] [--trace-index <release-trace-index.json>] [--history-manifest <release-history-manifest.json>] [--trace-registration-output <trace-registration-report.json>] [--output <promotion-report.json>] [--set-current true|false] [--allow-manual-review true|false]"
  );
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  usage();
}

function parseArgs(argv: string[]): CliOptions {
  let decisionReportPath = "";
  let registryPath: string | undefined;
  let traceIndexPath: string | undefined;
  let historyManifestPath: string | undefined;
  let traceRegistrationOutputPath: string | undefined;
  let outputPath = "";
  let setCurrent = true;
  let allowManualReview = false;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--decision-report") decisionReportPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--registry") registryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--trace-index") traceIndexPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--history-manifest") historyManifestPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--trace-registration-output") {
      traceRegistrationOutputPath = path.resolve(argv[++index] ?? usage());
    }
    else if (arg === "--output") outputPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--set-current") setCurrent = parseBoolean(argv[++index] ?? usage());
    else if (arg === "--allow-manual-review") allowManualReview = parseBoolean(argv[++index] ?? usage());
    else usage();
  }

  if (!decisionReportPath) usage();
  if (!outputPath) {
    outputPath = path.join(path.dirname(decisionReportPath), "promotion-report.json");
  }

  return {
    decisionReportPath,
    registryPath,
    traceIndexPath,
    historyManifestPath,
    traceRegistrationOutputPath,
    outputPath,
    setCurrent,
    allowManualReview,
  };
}

async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const decisionReport = await readJson<ReleaseDecisionReportLike>(options.decisionReportPath);
  const pipelineReport = await readJson<PipelineReportLike>(decisionReport.pipelineReportPath);
  const manifestPath = pipelineReport.paths?.manifestPath ? path.resolve(pipelineReport.paths.manifestPath) : "";

  if (!manifestPath) {
    throw new Error("decision report points to a pipeline report without paths.manifestPath");
  }

  const allowed =
    decisionReport.decision.status === "approve_candidate" ||
    (decisionReport.decision.status === "manual_review" && options.allowManualReview);

  const baseSummary = {
    ok: false,
    decisionReportPath: options.decisionReportPath,
    pipelineReportPath: decisionReport.pipelineReportPath,
    registryPath:
      options.registryPath ?? path.resolve(path.dirname(manifestPath), "release-registry.json"),
    outputPath: options.outputPath,
    candidateVersion: decisionReport.candidateVersion,
    decisionStatus: decisionReport.decision.status,
    allowManualReview: options.allowManualReview,
    setCurrent: options.setCurrent,
  };

  if (!allowed) {
    const summary = {
      ...baseSummary,
      reason:
        decisionReport.decision.status === "hold_candidate"
          ? "promotion blocked because release decision report is hold_candidate"
          : "promotion blocked because release decision report requires manual_review",
      nextActions: decisionReport.decision.nextActions,
    };
    await mkdir(path.dirname(options.outputPath), { recursive: true });
    await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
    console.log(JSON.stringify(summary, null, 2));
    process.exitCode = 1;
    return;
  }

  const command = [
    process.execPath,
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/register-model-release.ts",
    "--manifest",
    manifestPath,
    "--registry",
    options.registryPath ?? path.resolve(path.dirname(manifestPath), "release-registry.json"),
    "--set-current",
    String(options.setCurrent),
  ];

  const { stdout } = await execFileAsync(command[0]!, command.slice(1), {
    cwd: path.resolve("."),
  });
  const registerSummary = JSON.parse(stdout) as RegisterSummaryLike;

  let traceRegistrationSummary: TraceRegistrationSummaryLike | null = null;
  if (options.traceIndexPath) {
    const traceRegistrationCommand = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-release-trace-index.ts",
      "--trace-index",
      options.traceIndexPath,
    ];
    if (options.historyManifestPath) {
      traceRegistrationCommand.push("--history-manifest", options.historyManifestPath);
    }
    if (options.traceRegistrationOutputPath) {
      traceRegistrationCommand.push("--output", options.traceRegistrationOutputPath);
    }

    const { stdout: traceRegistrationStdout } = await execFileAsync(
      traceRegistrationCommand[0]!,
      traceRegistrationCommand.slice(1),
      {
        cwd: path.resolve("."),
      }
    );
    traceRegistrationSummary = JSON.parse(
      traceRegistrationStdout
    ) as TraceRegistrationSummaryLike;
  }

  const summary = {
    ...baseSummary,
    ok: registerSummary.ok,
    manifestPath,
    registerSummary,
    traceRegistrationSummary,
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
  console.log(JSON.stringify(summary, null, 2));
}

await main();
