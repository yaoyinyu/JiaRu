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

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/run-seed-batch-prep-pipeline.ts --root-dir <seed-batch-dir>"
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
  const reportPath = path.join(options.rootDir, "seed-batch-prep-pipeline-report.json");
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

  for (const [name, script, softFail] of [
    ["audit-seed-batch-workspace", "model/training/audit-seed-batch-workspace.ts", false],
    ["audit-screening-review", "model/training/audit-screening-review.ts", true],
    ["build-reviewed-intake-batch", "model/training/build-reviewed-intake-batch.ts", false],
    ["prepare-reviewed-annotations", "model/training/prepare-reviewed-annotations.ts", false],
  ] as const) {
    try {
      const stdout = await runJsonScript(script, ["--root-dir", options.rootDir]);
      const parsedOk =
        typeof stdout === "object" &&
        stdout !== null &&
        "ok" in stdout &&
        typeof (stdout as { ok: unknown }).ok === "boolean"
          ? Boolean((stdout as { ok: boolean }).ok)
          : true;
      report.steps.push({ name, ok: softFail ? true : parsedOk, stdout });
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

  report.ok = report.steps.every((step) => step.ok);
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main();
