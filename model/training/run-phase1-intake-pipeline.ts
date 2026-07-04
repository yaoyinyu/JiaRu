import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import {
  validateIntakeBatchManifest,
  type NailTextureIntakeBatchManifest,
} from "../../src/lib/nail-texture-dataset.ts";

const execFileAsync = promisify(execFile);
const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

interface CliOptions {
  manifestPath: string;
  imageDir: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

interface JsonScriptResult {
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
}

function parseArgs(argv: string[]): CliOptions {
  let manifestPath: string | undefined;
  let imageDir: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--manifest") {
      manifestPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--image-dir") {
      imageDir = path.resolve(argv[++index]);
      continue;
    }
  }

  if (!manifestPath || !imageDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest <manifest.json> --image-dir <dir>"
    );
  }

  return { manifestPath, imageDir };
}

async function runJsonScript(
  scriptPath: string,
  args: string[],
  env: NodeJS.ProcessEnv
): Promise<unknown> {
  const { stdout } = await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", scriptPath, ...args],
    {
      cwd: path.resolve("."),
      env,
    }
  );
  return JSON.parse(stdout);
}

async function runJsonScriptAllowFailure(
  scriptPath: string,
  args: string[],
  env: NodeJS.ProcessEnv
): Promise<JsonScriptResult> {
  try {
    return {
      ok: true,
      stdout: await runJsonScript(scriptPath, args, env),
    };
  } catch (error) {
    const execError = error as Error & { stdout?: string; stderr?: string };
    if (execError.stdout?.trim()) {
      try {
        return {
          ok: true,
          stdout: JSON.parse(execError.stdout),
          stderr: execError.stderr,
        };
      } catch {
        // Fall through to reporting the script failure.
      }
    }
    return {
      ok: false,
      stderr: execError.stderr || execError.message,
    };
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(
    await readFile(options.manifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;
  const validation = validateIntakeBatchManifest(manifest);
  const reportPath = path.join(
    datasetRoot,
    "metadata",
    `phase1-intake-${manifest.sourceGroup}.report.json`
  );

  await mkdir(path.dirname(reportPath), { recursive: true });

  const report: {
    datasetRoot: string;
    manifestPath: string;
    imageDir: string;
    reportPath: string;
    sourceGroup: string;
    ok: boolean;
    steps: StepResult[];
    validationIssues: typeof validation.issues;
    readinessSnapshot?: unknown;
  } = {
    datasetRoot,
    manifestPath: options.manifestPath,
    imageDir: options.imageDir,
    reportPath,
    sourceGroup: manifest.sourceGroup,
    ok: false,
    steps: [],
    validationIssues: validation.issues,
  };

  if (!validation.ok) {
    report.steps.push({
      name: "validate-manifest",
      ok: false,
      stdout: { issues: validation.issues },
    });
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const baseEnv = {
    ...process.env,
    DATASET_ROOT: datasetRoot,
  };

  const preflight = await runJsonScript(
    "model/training/validate-intake-batch.ts",
    ["--manifest", options.manifestPath, "--image-dir", options.imageDir],
    baseEnv
  );
  const preflightOk =
    typeof preflight === "object" &&
    preflight !== null &&
    "ok" in preflight &&
    Boolean((preflight as { ok: boolean }).ok);
  report.steps.push({
    name: "validate-intake-batch",
    ok: preflightOk,
    stdout: preflight,
  });
  if (!preflightOk) {
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const exportedOutputs: unknown[] = [];
  for (const item of manifest.items) {
    const imagePath = path.join(options.imageDir, item.fileName);
    const output = await runJsonScript(
      "model/training/export-fallback-annotations.ts",
      [
        ...(manifest.copyImagesToDataset ? ["--copy-image"] : []),
        ...(manifest.originType === "negative" ? ["--negative"] : []),
        "--source-group",
        manifest.sourceGroup,
        "--origin-type",
        manifest.originType,
        "--origin-ref",
        item.originRef?.trim() || manifest.defaultOriginRef,
        "--license",
        manifest.license,
        "--notes",
        item.notes?.trim() || "",
        imagePath,
      ],
      baseEnv
    );
    exportedOutputs.push(output);
  }
  report.steps.push({
    name: "export-fallback-annotations",
    ok: true,
    stdout: exportedOutputs,
  });

  for (const step of [
    "sync-sources-csv.ts",
    "audit-sources-csv.ts",
    "split-dataset.ts",
    "audit-labels.ts",
    "convert-annotations.ts",
  ] as const) {
    try {
      const output = await runJsonScript(
        `model/training/${step}`,
        [],
        baseEnv
      );
      report.steps.push({
        name: step.replace(/\.ts$/, ""),
        ok: true,
        stdout: output,
      });
    } catch (error) {
      const execError = error as Error & { stdout?: string; stderr?: string };
      report.steps.push({
        name: step.replace(/\.ts$/, ""),
        ok: false,
        stderr: execError.stderr || execError.message,
      });
      await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  const readiness = await runJsonScriptAllowFailure(
    "model/training/audit-phase1-readiness.ts",
    [],
    baseEnv
  );
  report.steps.push({
    name: "audit-phase1-readiness",
    ok: readiness.ok,
    stdout: readiness.stdout,
    stderr: readiness.stderr,
  });
  report.readinessSnapshot = readiness.stdout;
  if (!readiness.ok) {
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
