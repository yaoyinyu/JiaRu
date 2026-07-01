import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const execFileAsync = promisify(execFile);

interface CliOptions {
  dataset: string;
  trainOutputDir: string;
  browserModelDir: string;
  runName: string;
  modelVersion: string;
  trainModel: string;
  epochs: number;
  imgsz: number;
  batch: string;
  patience: number;
  device: string;
  workers: number;
  split: "train" | "val" | "test";
  dryRun: boolean;
  skipTrain: boolean;
  skipEvaluate: boolean;
  skipExport: boolean;
  minSegMap50: number;
  minBoxMap50: number;
  maxModelMb: number;
  finalAuditImage?: string;
  finalAuditOutputDir?: string;
  finalAuditDebugPrefix: string;
  finalAuditDump?: string;
  finalAuditFixtureOut?: string;
  finalAuditAnnotationDir?: string;
  finalAuditAnnotation?: string;
  finalAuditUiReview?: string;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
  command: string[];
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    dataset: path.resolve("model/training/dataset.yaml"),
    trainOutputDir: path.resolve("model/exports/nail-texture-seg-v1"),
    browserModelDir: path.resolve("public/models/nail-texture-seg"),
    runName: "nail-texture-seg-v1",
    modelVersion: "nail-texture-seg-v1",
    trainModel: "yolo11n-seg.pt",
    epochs: 100,
    imgsz: 640,
    batch: "auto",
    patience: 20,
    device: "auto",
    workers: 8,
    split: "test",
    dryRun: false,
    skipTrain: false,
    skipEvaluate: false,
    skipExport: false,
    minSegMap50: 0.75,
    minBoxMap50: 0.85,
    maxModelMb: 15,
    finalAuditDebugPrefix: "real-model",
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--dataset") options.dataset = path.resolve(argv[++index]);
    else if (arg === "--train-output-dir") options.trainOutputDir = path.resolve(argv[++index]);
    else if (arg === "--browser-model-dir") options.browserModelDir = path.resolve(argv[++index]);
    else if (arg === "--run-name") options.runName = argv[++index] ?? options.runName;
    else if (arg === "--model-version") options.modelVersion = argv[++index] ?? options.modelVersion;
    else if (arg === "--model") options.trainModel = argv[++index] ?? options.trainModel;
    else if (arg === "--epochs") options.epochs = Number(argv[++index]);
    else if (arg === "--imgsz") options.imgsz = Number(argv[++index]);
    else if (arg === "--batch") options.batch = argv[++index] ?? options.batch;
    else if (arg === "--patience") options.patience = Number(argv[++index]);
    else if (arg === "--device") options.device = argv[++index] ?? options.device;
    else if (arg === "--workers") options.workers = Number(argv[++index]);
    else if (arg === "--split") options.split = (argv[++index] as CliOptions["split"]) ?? options.split;
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--skip-train") options.skipTrain = true;
    else if (arg === "--skip-evaluate") options.skipEvaluate = true;
    else if (arg === "--skip-export") options.skipExport = true;
    else if (arg === "--min-seg-map50") options.minSegMap50 = Number(argv[++index]);
    else if (arg === "--min-box-map50") options.minBoxMap50 = Number(argv[++index]);
    else if (arg === "--max-model-mb") options.maxModelMb = Number(argv[++index]);
    else if (arg === "--final-audit-image") options.finalAuditImage = path.resolve(argv[++index]);
    else if (arg === "--final-audit-output-dir") options.finalAuditOutputDir = path.resolve(argv[++index]);
    else if (arg === "--final-audit-debug-prefix") options.finalAuditDebugPrefix = argv[++index] ?? options.finalAuditDebugPrefix;
    else if (arg === "--final-audit-dump") options.finalAuditDump = path.resolve(argv[++index]);
    else if (arg === "--final-audit-fixture-out") options.finalAuditFixtureOut = path.resolve(argv[++index]);
    else if (arg === "--final-audit-annotation-dir") options.finalAuditAnnotationDir = path.resolve(argv[++index]);
    else if (arg === "--final-audit-annotation") options.finalAuditAnnotation = path.resolve(argv[++index]);
    else if (arg === "--final-audit-ui-review") options.finalAuditUiReview = path.resolve(argv[++index]);
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/run-training-release-pipeline.ts [--dataset <dataset.yaml>] [--train-output-dir <dir>] [--browser-model-dir <dir>] [--run-name <name>] [--model-version <name>] [--model <checkpoint>] [--epochs <n>] [--imgsz <n>] [--batch <value>] [--patience <n>] [--device <value>] [--workers <n>] [--split <train|val|test>] [--dry-run] [--skip-train] [--skip-evaluate] [--skip-export] [--min-seg-map50 <n>] [--min-box-map50 <n>] [--max-model-mb <n>] [--final-audit-image <image>] [--final-audit-output-dir <dir>] [--final-audit-debug-prefix <name>] [--final-audit-dump <dump.json>] [--final-audit-fixture-out <fixture.json>] [--final-audit-annotation-dir <annotations-dir>] [--final-audit-annotation <annotation-image>] [--final-audit-ui-review <ui-review.json>]"
      );
    }
  }

  return options;
}

function resolveBestWeightsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, options.runName, "weights", "best.pt");
}

function resolveMetricsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, "metrics.json");
}

function resolveManifestPath(options: CliOptions): string {
  return path.join(options.browserModelDir, "manifest.json");
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

async function runCommand(
  name: string,
  command: string[],
  cwd: string
): Promise<StepResult> {
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

async function readJsonIfExists(filePath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch {
    return null;
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const cwd = path.resolve(".");
  const reportPath = path.join(options.trainOutputDir, "training-release-pipeline-report.json");
  await mkdir(path.dirname(reportPath), { recursive: true });

  const weightsPath = resolveBestWeightsPath(options);
  const metricsPath = resolveMetricsPath(options);
  const manifestPath = resolveManifestPath(options);

  const steps: StepResult[] = [];

  if (!options.skipTrain) {
    const command = [
      "python",
      "model/training/train-yolo-seg.py",
      "--dataset",
      options.dataset,
      "--output-dir",
      options.trainOutputDir,
      "--model",
      options.trainModel,
      "--epochs",
      String(options.epochs),
      "--imgsz",
      String(options.imgsz),
      "--batch",
      options.batch,
      "--patience",
      String(options.patience),
      "--device",
      options.device,
      "--workers",
      String(options.workers),
      "--run-name",
      options.runName,
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const result = await runCommand("train-yolo-seg", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

  if (!options.skipEvaluate) {
    const command = [
      "python",
      "model/training/evaluate.py",
      "--dataset",
      options.dataset,
      "--train-output-dir",
      options.trainOutputDir,
      "--run-name",
      options.runName,
      "--weights",
      weightsPath,
      "--output",
      metricsPath,
      "--split",
      options.split,
      "--imgsz",
      String(options.imgsz),
      "--device",
      options.device,
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const result = await runCommand("evaluate", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

  if (!options.skipExport) {
    const command = [
      "python",
      "model/training/export-onnx.py",
      "--train-output-dir",
      options.trainOutputDir,
      "--run-name",
      options.runName,
      "--weights",
      weightsPath,
      "--output-dir",
      options.browserModelDir,
      "--model-version",
      options.modelVersion,
      "--input-size",
      String(options.imgsz),
      "--task",
      "segment",
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const result = await runCommand("export-onnx", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

  if (!options.dryRun) {
    const command = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-training-release.ts",
      "--metrics",
      metricsPath,
      "--manifest",
      manifestPath,
      "--min-seg-map50",
      String(options.minSegMap50),
      "--min-box-map50",
      String(options.minBoxMap50),
      "--max-model-mb",
      String(options.maxModelMb),
    ];
    const result = await runCommand("verify-training-release", command, cwd);
    steps.push(result);
    if (!result.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }

    if (options.finalAuditImage) {
      const finalAuditOutputDir =
        options.finalAuditOutputDir ?? path.join(options.trainOutputDir, "real-model-final-audit");
      const command = [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/run-real-model-final-audit.ts",
        "--manifest",
        manifestPath,
        "--image",
        options.finalAuditImage,
        "--output-dir",
        finalAuditOutputDir,
        "--debug-prefix",
        options.finalAuditDebugPrefix,
        "--metrics",
        metricsPath,
        ...(options.finalAuditDump ? ["--dump", options.finalAuditDump] : []),
        ...(options.finalAuditFixtureOut ? ["--fixture-out", options.finalAuditFixtureOut] : []),
        ...(options.finalAuditAnnotationDir ? ["--annotation-dir", options.finalAuditAnnotationDir] : []),
        ...(options.finalAuditAnnotation ? ["--annotation", options.finalAuditAnnotation] : []),
        ...(options.finalAuditUiReview ? ["--ui-review", options.finalAuditUiReview] : []),
      ];
      const finalAuditResult = await runCommand("run-real-model-final-audit", command, cwd);
      steps.push(finalAuditResult);
      return await finish(finalAuditResult.ok, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }

    steps.push({
      name: "run-real-model-final-audit",
      ok: true,
      stdout: {
        skipped: true,
        reason: "final audit was skipped because --final-audit-image was not provided",
      },
      command: [],
    });
    return await finish(true, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

  steps.push({
    name: "verify-training-release",
    ok: true,
    stdout: {
      skipped: true,
      reason: "dry-run mode only validates configuration; no real metrics or exported artifact were produced",
    },
    command: [],
  });
  steps.push({
    name: "run-real-model-final-audit",
    ok: true,
    stdout: {
      skipped: true,
      reason: "final audit is unavailable in dry-run mode because no real artifact is produced",
    },
    command: [],
  });
  return await finish(true, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
}

async function finish(
  ok: boolean,
  options: CliOptions,
  reportPath: string,
  steps: StepResult[],
  weightsPath: string,
  metricsPath: string,
  manifestPath: string
) {
  const report = {
    ok: ok && steps.every((step) => step.ok),
    reportPath,
    mode: options.dryRun ? "dry-run" : "real-run",
    paths: {
      dataset: options.dataset,
      trainOutputDir: options.trainOutputDir,
      browserModelDir: options.browserModelDir,
      weightsPath,
      metricsPath,
      manifestPath,
    },
    options: {
      runName: options.runName,
      modelVersion: options.modelVersion,
      trainModel: options.trainModel,
      epochs: options.epochs,
      imgsz: options.imgsz,
      batch: options.batch,
      patience: options.patience,
      device: options.device,
      workers: options.workers,
      split: options.split,
      skipTrain: options.skipTrain,
      skipEvaluate: options.skipEvaluate,
      skipExport: options.skipExport,
      minSegMap50: options.minSegMap50,
      minBoxMap50: options.minBoxMap50,
      maxModelMb: options.maxModelMb,
      finalAuditImage: options.finalAuditImage ?? null,
      finalAuditOutputDir:
        options.finalAuditOutputDir ?? path.join(options.trainOutputDir, "real-model-final-audit"),
      finalAuditDebugPrefix: options.finalAuditDebugPrefix,
      finalAuditDump: options.finalAuditDump ?? null,
      finalAuditFixtureOut: options.finalAuditFixtureOut ?? null,
      finalAuditAnnotationDir: options.finalAuditAnnotationDir ?? null,
      finalAuditAnnotation: options.finalAuditAnnotation ?? null,
      finalAuditUiReview: options.finalAuditUiReview ?? null,
    },
    steps,
    artifacts: {
      trainSummary: await readJsonIfExists(path.join(options.trainOutputDir, "train-summary.json")),
      metrics: await readJsonIfExists(metricsPath),
      manifest: await readJsonIfExists(manifestPath),
      finalAudit: await readJsonIfExists(
        path.join(
          options.finalAuditOutputDir ?? path.join(options.trainOutputDir, "real-model-final-audit"),
          "real-model-final-audit-report.json"
        )
      ),
      finalAuditFailureSummary: await readJsonIfExists(
        path.join(
          options.finalAuditOutputDir ?? path.join(options.trainOutputDir, "real-model-final-audit"),
          "failure-case-summary.json"
        )
      ),
    },
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exitCode = 1;
}

await main();
