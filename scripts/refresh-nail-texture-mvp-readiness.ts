import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

interface CliOptions {
  datasetRoot: string;
  manifestPath: string;
  packageJsonPath: string;
  outputPath: string;
  mvpReportPath: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  command: string[];
  stdout: unknown;
  stderr: string | null;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/refresh-nail-texture-mvp-readiness.ts " +
      "[--dataset-root <dataset>] [--manifest <manifest.json>] [--package-json <package.json>] " +
      "[--mvp-report <mvp-readiness.json>] [--output <refresh-report.json>]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let datasetRoot = path.resolve("model/datasets/nail-texture-v1");
  let manifestPath = path.resolve("public/models/nail-texture-seg/manifest.json");
  let packageJsonPath = path.resolve("package.json");
  let outputPath = path.resolve("model/exports/nail-texture-mvp-readiness-refresh.json");
  let mvpReportPath = path.resolve("model/exports/nail-texture-mvp-readiness.json");

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (!value) usage();
    if (arg === "--dataset-root") datasetRoot = path.resolve(value);
    else if (arg === "--manifest") manifestPath = path.resolve(value);
    else if (arg === "--package-json") packageJsonPath = path.resolve(value);
    else if (arg === "--mvp-report") mvpReportPath = path.resolve(value);
    else if (arg === "--output") outputPath = path.resolve(value);
    else usage();
    index += 1;
  }

  return { datasetRoot, manifestPath, packageJsonPath, outputPath, mvpReportPath };
}

function parseOutput(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
}

async function runStep(name: string, command: string[]): Promise<StepResult> {
  try {
    const { stdout, stderr } = await execFileAsync(command[0]!, command.slice(1), {
      cwd: path.resolve("."),
    });
    return {
      name,
      ok: true,
      command,
      stdout: parseOutput(stdout),
      stderr: stderr.trim() || null,
    };
  } catch (error) {
    const execError = error as Error & { stdout?: string; stderr?: string };
    return {
      name,
      ok: false,
      command,
      stdout: parseOutput(execError.stdout ?? ""),
      stderr: execError.stderr?.trim() || execError.message,
    };
  }
}

async function readJsonIfExists(filePath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const trainingReadinessPath = path.join(
    options.datasetRoot,
    "metadata",
    "training-dataset-readiness-release.json"
  );
  const nodeArgs = [process.execPath, "--no-warnings", "--experimental-strip-types"];
  const steps: StepResult[] = [];

  steps.push(
    await runStep("refresh-training-dataset-readiness", [
      ...nodeArgs,
      "model/training/verify-training-dataset-readiness.ts",
      "--dataset-root",
      options.datasetRoot,
      "--authorization-mode",
      "release",
      "--output",
      trainingReadinessPath,
    ])
  );

  // A failed dataset gate is useful evidence, so always create the aggregate report.
  steps.push(
    await runStep("audit-mvp-readiness", [
      ...nodeArgs,
      "scripts/audit-nail-texture-mvp-readiness.ts",
      "--dataset-root",
      options.datasetRoot,
      "--manifest",
      options.manifestPath,
      "--package-json",
      options.packageJsonPath,
      "--output",
      options.mvpReportPath,
    ])
  );

  const report = {
    ok: steps.every((step) => step.ok),
    generatedAt: new Date().toISOString(),
    paths: {
      datasetRoot: options.datasetRoot,
      manifestPath: options.manifestPath,
      packageJsonPath: options.packageJsonPath,
      trainingReadinessPath,
      mvpReportPath: options.mvpReportPath,
      outputPath: options.outputPath,
    },
    steps,
    artifacts: {
      trainingDatasetReadiness: await readJsonIfExists(trainingReadinessPath),
      mvpReadiness: await readJsonIfExists(options.mvpReportPath),
    },
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exitCode = 1;
}

await main();
