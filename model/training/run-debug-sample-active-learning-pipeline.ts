import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import type { SourceRecord } from "../../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

interface CliOptions {
  sampleDir: string;
  imageDir: string;
  copyImage: boolean;
  sourceGroup?: string;
  originType: SourceRecord["originType"];
  originRef: string;
  license: string;
  notes: string;
  minPriorityTier?: "high" | "medium" | "low";
  top?: number;
  priorityReportPath: string;
  reportPath: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types model/training/run-debug-sample-active-learning-pipeline.ts --sample-dir <dir> --image-dir <dir> [--copy-image] [--source-group <name>] [--origin-type <reference|web|user|merchant|negative|other>] [--origin-ref <text>] [--license <text>] [--notes <text>] [--min-priority <high|medium|low>] [--top <n>] [--priority-report <path>] [--output <report.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let sampleDir: string | undefined;
  let imageDir: string | undefined;
  let copyImage = false;
  let sourceGroup: string | undefined;
  let originType: SourceRecord["originType"] = "user";
  let originRef = "";
  let license = "";
  let notes = "";
  let minPriorityTier: CliOptions["minPriorityTier"];
  let top: number | undefined;
  let priorityReportPath: string | undefined;
  let reportPath: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--sample-dir") sampleDir = path.resolve(argv[++index] ?? usage());
    else if (arg === "--image-dir") imageDir = path.resolve(argv[++index] ?? usage());
    else if (arg === "--copy-image") copyImage = true;
    else if (arg === "--source-group") sourceGroup = argv[++index];
    else if (arg === "--origin-type") originType = argv[++index] as SourceRecord["originType"];
    else if (arg === "--origin-ref") originRef = argv[++index] ?? "";
    else if (arg === "--license") license = argv[++index] ?? "";
    else if (arg === "--notes") notes = argv[++index] ?? "";
    else if (arg === "--min-priority") {
      const tier = argv[++index] as CliOptions["minPriorityTier"];
      if (tier !== "high" && tier !== "medium" && tier !== "low") {
        throw new Error("--min-priority must be one of: high, medium, low");
      }
      minPriorityTier = tier;
    } else if (arg === "--top") {
      top = Number(argv[++index] ?? usage());
      if (!Number.isInteger(top) || top <= 0) {
        throw new Error("--top must be a positive integer");
      }
    } else if (arg === "--priority-report") {
      priorityReportPath = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--output") {
      reportPath = path.resolve(argv[++index] ?? usage());
    } else usage();
  }

  if (!sampleDir || !imageDir) usage();
  if (!priorityReportPath) {
    priorityReportPath = path.join(sampleDir, "prioritized-debug-samples.json");
  }
  if (!reportPath) {
    reportPath = path.join(sampleDir, "debug-sample-active-learning-pipeline-report.json");
  }

  return {
    sampleDir,
    imageDir,
    copyImage,
    sourceGroup,
    originType,
    originRef,
    license,
    notes,
    minPriorityTier,
    top,
    priorityReportPath,
    reportPath,
  };
}

async function runJsonScript(scriptPath: string, args: string[]): Promise<unknown> {
  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
      {
        cwd: path.resolve("."),
        env: process.env,
      }
    );
    return JSON.parse(stdout);
  } catch (error) {
    const execError = error as Error & { stdout?: string };
    if (execError.stdout) return JSON.parse(execError.stdout);
    throw error;
  }
}

async function persistReport(reportPath: string, report: unknown) {
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  await mkdir(path.dirname(options.reportPath), { recursive: true });
  await mkdir(path.dirname(options.priorityReportPath), { recursive: true });

  const report: {
    ok: boolean;
    sampleDir: string;
    imageDir: string;
    reportPath: string;
    priorityReportPath: string;
    artifacts?: {
      activeLearningReleaseTraceDraftPath?: string | null;
      activeLearningHandoffPath?: string | null;
    };
    steps: StepResult[];
  } = {
    ok: false,
    sampleDir: options.sampleDir,
    imageDir: options.imageDir,
    reportPath: options.reportPath,
    priorityReportPath: options.priorityReportPath,
    artifacts: {
      activeLearningReleaseTraceDraftPath: null,
      activeLearningHandoffPath: null,
    },
    steps: [],
  };

  for (const [name, script, args, softFail] of [
    [
      "prioritize-debug-samples",
      "model/training/prioritize-debug-samples.ts",
      [
        "--sample-dir",
        options.sampleDir,
        ...(options.top ? ["--top", String(options.top)] : []),
      ],
      false,
    ],
    [
      "import-debug-sample",
      "model/training/import-debug-sample.ts",
      [
        "--sample-dir",
        options.sampleDir,
        "--image-dir",
        options.imageDir,
        "--priority-report",
        options.priorityReportPath,
        ...(options.minPriorityTier ? ["--min-priority", options.minPriorityTier] : []),
        ...(options.top ? ["--top", String(options.top)] : []),
        ...(options.copyImage ? ["--copy-image"] : []),
        ...(options.sourceGroup ? ["--source-group", options.sourceGroup] : []),
        "--origin-type",
        options.originType,
        "--origin-ref",
        options.originRef,
        "--license",
        options.license,
        "--notes",
        options.notes,
      ],
      false,
    ],
    ["sync-sources-csv", "model/training/sync-sources-csv.ts", [], false],
    ["audit-sources-csv", "model/training/audit-sources-csv.ts", [], false],
    ["split-dataset", "model/training/split-dataset.ts", [], false],
    ["audit-labels", "model/training/audit-labels.ts", [], false],
    ["convert-annotations", "model/training/convert-annotations.ts", [], false],
    ["audit-phase1-readiness", "model/training/audit-phase1-readiness.ts", [], true],
    ["plan-phase1-collection", "model/training/plan-phase1-collection.ts", [], true],
    ["generate-first-batch-checklist", "model/training/generate-first-batch-checklist.ts", [], true],
  ] as const) {
    try {
      const stdout = await runJsonScript(script, args);
      if (name === "prioritize-debug-samples") {
        await writeFile(options.priorityReportPath, JSON.stringify(stdout, null, 2), "utf8");
      }
      const parsedOk =
        typeof stdout === "object" &&
        stdout !== null &&
        "ok" in stdout &&
        typeof (stdout as { ok: unknown }).ok === "boolean"
          ? Boolean((stdout as { ok: boolean }).ok)
          : true;
      report.steps.push({
        name,
        ok: softFail ? true : parsedOk,
        stdout,
      });
    } catch (error) {
      const execError = error as Error & { stderr?: string };
      report.steps.push({
        name,
        ok: false,
        stderr: execError.stderr || execError.message,
      });
      await persistReport(options.reportPath, report);
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  await persistReport(options.reportPath, report);

  const activeLearningReleaseTraceDraftPath = path.join(
    path.dirname(options.reportPath),
    "active-learning-release-trace-draft.json"
  );
  try {
    const stdout = await runJsonScript("scripts/build-active-learning-release-trace-draft.ts", [
      "--pipeline-report",
      options.reportPath,
      "--output",
      activeLearningReleaseTraceDraftPath,
    ]);
    report.steps.push({
      name: "build-active-learning-release-trace-draft",
      ok: true,
      stdout,
    });
    report.artifacts!.activeLearningReleaseTraceDraftPath = activeLearningReleaseTraceDraftPath;
  } catch (error) {
    const execError = error as Error & { stderr?: string };
    report.steps.push({
      name: "build-active-learning-release-trace-draft",
      ok: false,
      stderr: execError.stderr || execError.message,
    });
    await persistReport(options.reportPath, report);
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const activeLearningHandoffPath = path.join(
    path.dirname(options.reportPath),
    "debug-sample-active-learning-handoff.json"
  );
  try {
    const stdout = await runJsonScript("scripts/build-debug-sample-active-learning-handoff.ts", [
      "--pipeline-report",
      options.reportPath,
      "--release-trace-draft",
      activeLearningReleaseTraceDraftPath,
      "--output",
      activeLearningHandoffPath,
    ]);
    report.steps.push({
      name: "build-debug-sample-active-learning-handoff",
      ok: true,
      stdout,
    });
    report.artifacts!.activeLearningHandoffPath = activeLearningHandoffPath;
  } catch (error) {
    const execError = error as Error & { stderr?: string };
    report.steps.push({
      name: "build-debug-sample-active-learning-handoff",
      ok: false,
      stderr: execError.stderr || execError.message,
    });
    await persistReport(options.reportPath, report);
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  report.ok = report.steps.every((step) => step.ok);
  await persistReport(options.reportPath, report);
  console.log(JSON.stringify(report, null, 2));
}

await main();
