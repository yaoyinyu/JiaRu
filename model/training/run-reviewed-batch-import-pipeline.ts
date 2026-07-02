import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, writeFile } from "node:fs/promises";

const execFileAsync = promisify(execFile);

interface CliOptions {
  rootDir: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

function stepArgs(name: string, rootDir: string): string[] {
  if (
    name === "audit-phase1-readiness" ||
    name === "plan-phase1-collection" ||
    name === "generate-first-batch-checklist"
  ) {
    return [];
  }
  return ["--root-dir", rootDir];
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir <seed-batch-dir>"
    );
  }
  return { rootDir };
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
    if (execError.stdout) {
      return JSON.parse(execError.stdout);
    }
    throw error;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reportPath = path.join(options.rootDir, "reviewed-batch-import-pipeline-report.json");
  await mkdir(path.dirname(reportPath), { recursive: true });

  const report: {
    ok: boolean;
    rootDir: string;
    reportPath: string;
    steps: StepResult[];
  } = {
    ok: false,
    rootDir: options.rootDir,
    reportPath,
    steps: [],
  };

  let reviewedImportReportPath: string | null = null;

  for (const [name, script, softFail] of [
    ["audit-seed-batch-workspace", "model/training/audit-seed-batch-workspace.ts", false],
    ["import-reviewed-batch", "model/training/import-reviewed-batch.ts", false],
    ["audit-phase1-readiness", "model/training/audit-phase1-readiness.ts", true],
    ["plan-phase1-collection", "model/training/plan-phase1-collection.ts", true],
    ["generate-first-batch-checklist", "model/training/generate-first-batch-checklist.ts", true],
  ] as const) {
    try {
      const stdout = await runJsonScript(script, stepArgs(name, options.rootDir));
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
      if (
        name === "import-reviewed-batch" &&
        typeof stdout === "object" &&
        stdout !== null &&
        "reportPath" in stdout &&
        typeof (stdout as { reportPath?: unknown }).reportPath === "string"
      ) {
        reviewedImportReportPath = (stdout as { reportPath: string }).reportPath;
      }
    } catch (error) {
      const execError = error as Error & { stderr?: string };
      report.steps.push({
        name,
        ok: false,
        stderr: execError.stderr || execError.message,
      });
      await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  if (reviewedImportReportPath) {
    try {
      const stdout = await runJsonScript("scripts/build-initial-release-trace-draft.ts", [
        "--reviewed-import-report",
        reviewedImportReportPath,
        "--root-dir",
        options.rootDir,
      ]);
      report.steps.push({
        name: "build-initial-release-trace-draft",
        ok: true,
        stdout,
      });
    } catch (error) {
      const execError = error as Error & { stderr?: string };
      report.steps.push({
        name: "build-initial-release-trace-draft",
        ok: false,
        stderr: execError.stderr || execError.message,
      });
      await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");

  try {
    const stdout = await runJsonScript("scripts/build-reviewed-batch-release-handoff.ts", [
      "--root-dir",
      options.rootDir,
      "--reviewed-batch-import-pipeline-report",
      reportPath,
    ]);
    report.steps.push({
      name: "build-reviewed-batch-release-handoff",
      ok: true,
      stdout,
    });
  } catch (error) {
    const execError = error as Error & { stderr?: string };
    report.steps.push({
      name: "build-reviewed-batch-release-handoff",
      ok: false,
      stderr: execError.stderr || execError.message,
    });
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  report.ok = report.steps.every((step) => step.ok);
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main();
