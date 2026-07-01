import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, writeFile } from "node:fs/promises";
import type { SourceRecord } from "../../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);

interface CliOptions {
  sourceDir: string;
  rootDir: string;
  sourceGroup: string;
  originType: SourceRecord["originType"];
  license: string;
  defaultOriginRef: string;
  copyImagesToDataset: boolean;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

function parseBooleanFlag(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  throw new Error(`Expected boolean value "true" or "false", received: ${value}`);
}

function parseArgs(argv: string[]): CliOptions {
  let sourceDir: string | undefined;
  let rootDir: string | undefined;
  let sourceGroup: string | undefined;
  let originType: SourceRecord["originType"] | undefined;
  let license = "internal-test-only";
  let defaultOriginRef: string | undefined;
  let copyImagesToDataset = true;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--source-dir") sourceDir = path.resolve(argv[++index]);
    else if (arg === "--root-dir") rootDir = path.resolve(argv[++index]);
    else if (arg === "--source-group") sourceGroup = argv[++index]?.trim();
    else if (arg === "--origin-type") originType = argv[++index] as SourceRecord["originType"];
    else if (arg === "--license") license = argv[++index]?.trim() || license;
    else if (arg === "--default-origin-ref") defaultOriginRef = argv[++index]?.trim();
    else if (arg === "--copy-images-to-dataset") {
      copyImagesToDataset = parseBooleanFlag(argv[++index] ?? "");
    }
  }

  if (!sourceDir || !rootDir || !sourceGroup || !originType || !defaultOriginRef) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/run-local-batch-bootstrap-pipeline.ts --source-dir <dir> --root-dir <dir> --source-group <name> --origin-type <reference|web|user|merchant|negative|other> --default-origin-ref <text> [--license <text>] [--copy-images-to-dataset <true|false>]"
    );
  }

  return {
    sourceDir,
    rootDir,
    sourceGroup,
    originType,
    license,
    defaultOriginRef,
    copyImagesToDataset,
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
    if (execError.stdout) {
      return JSON.parse(execError.stdout);
    }
    throw error;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reportPath = path.join(options.rootDir, "local-batch-bootstrap-pipeline-report.json");
  await mkdir(path.dirname(reportPath), { recursive: true });

  const report: {
    ok: boolean;
    sourceDir: string;
    rootDir: string;
    reportPath: string;
    steps: StepResult[];
  } = {
    ok: false,
    sourceDir: options.sourceDir,
    rootDir: options.rootDir,
    reportPath,
    steps: [],
  };

  for (const [name, script, args] of [
    [
      "bootstrap-seed-batch",
      "model/training/bootstrap-seed-batch.ts",
      [
        "--source-dir",
        options.sourceDir,
        "--root-dir",
        options.rootDir,
        "--source-group",
        options.sourceGroup,
        "--origin-type",
        options.originType,
        "--license",
        options.license,
        "--default-origin-ref",
        options.defaultOriginRef,
        "--copy-images-to-dataset",
        String(options.copyImagesToDataset),
      ],
    ],
    [
      "run-seed-batch-prep-pipeline",
      "model/training/run-seed-batch-prep-pipeline.ts",
      ["--root-dir", options.rootDir],
    ],
    [
      "audit-seed-batch-workspace",
      "model/training/audit-seed-batch-workspace.ts",
      ["--root-dir", options.rootDir],
    ],
  ] as const) {
    try {
      const stdout = await runJsonScript(script, args);
      report.steps.push({ name, ok: true, stdout });
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
