import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { DEFAULT_DATASET_ROOT } from "./phase1-readiness-report.ts";

const execFileAsync = promisify(execFile);

type AuthorizationMode = "internal" | "release";

interface CliOptions {
  datasetRoot: string;
  authorizationMode: AuthorizationMode;
  outputPath: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
  command: string[];
}

function readArg(argv: string[], name: string): string | undefined {
  const index = argv.indexOf(name);
  if (index === -1) return undefined;
  return argv[index + 1];
}

function parseArgs(argv: string[]): CliOptions {
  const datasetRoot = path.resolve(
    readArg(argv, "--dataset-root") ?? process.env.DATASET_ROOT ?? DEFAULT_DATASET_ROOT
  );
  const rawMode = readArg(argv, "--authorization-mode") ?? "release";
  if (rawMode !== "internal" && rawMode !== "release") {
    throw new Error("--authorization-mode must be internal or release");
  }

  const outputPath = path.resolve(
    readArg(argv, "--output") ??
      path.join(datasetRoot, "metadata", `training-dataset-readiness-${rawMode}.json`)
  );

  return {
    datasetRoot,
    authorizationMode: rawMode,
    outputPath,
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

async function runStep(
  name: string,
  command: string[],
  datasetRoot: string
): Promise<StepResult> {
  try {
    const { stdout } = await execFileAsync(command[0]!, command.slice(1), {
      cwd: path.resolve("."),
      env: { ...process.env, DATASET_ROOT: datasetRoot },
    });
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

async function readJsonIfExists(filePath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const metadataDir = path.join(options.datasetRoot, "metadata");
  await mkdir(metadataDir, { recursive: true });

  const steps: StepResult[] = [];
  const sourceAuditPath = path.join(metadataDir, "sources-audit.json");
  const authorizationAuditPath = path.join(
    metadataDir,
    `training-source-authorization-${options.authorizationMode}.json`
  );
  const phase1ReadinessPath = path.join(metadataDir, "phase1-readiness.json");

  steps.push(
    await runStep(
      "audit-sources-csv",
      [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-sources-csv.ts",
      ],
      options.datasetRoot
    )
  );

  steps.push(
    await runStep(
      "audit-training-source-authorization",
      [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-training-source-authorization.ts",
        "--mode",
        options.authorizationMode,
        "--output",
        authorizationAuditPath,
      ],
      options.datasetRoot
    )
  );

  steps.push(
    await runStep(
      "audit-phase1-readiness",
      [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "model/training/audit-phase1-readiness.ts",
      ],
      options.datasetRoot
    )
  );

  const report = {
    ok: steps.every((step) => step.ok),
    datasetRoot: options.datasetRoot,
    authorizationMode: options.authorizationMode,
    outputPath: options.outputPath,
    artifactPaths: {
      sourceAudit: sourceAuditPath,
      sourceAuthorization: authorizationAuditPath,
      phase1Readiness: phase1ReadinessPath,
    },
    steps,
    artifacts: {
      sourceAudit: await readJsonIfExists(sourceAuditPath),
      sourceAuthorization: await readJsonIfExists(authorizationAuditPath),
      phase1Readiness: await readJsonIfExists(phase1ReadinessPath),
    },
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();