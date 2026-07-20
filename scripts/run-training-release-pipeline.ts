import path from "node:path";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";

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
  skipSourceAuthorization: boolean;
  skipTrainingEnvironmentCheck: boolean;
  requireLocalModel: boolean;
  candidateMode: boolean;
  candidateInputReport?: string;
  candidateValidationReport?: string;
  calibrationDataset?: string;
  calibrationDatasetReport?: string;
  calibrationTruthAudit?: string;
  calibrationOutput?: string;
  releaseTestDataset?: string;
  releaseTestReport?: string;
  sourceAuthorizationDatasetRoot: string;
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
  runGovernance: boolean;
  governanceCompareSummary?: string;
  governancePerformanceReport?: string;
  governanceRegistry?: string;
  governanceReleaseTraceDraft?: string;
  governanceReviewedBatchImportPipelineReport?: string;
  governanceReviewedBatchRootDir?: string;
  governanceReviewedBatchReleaseHandoff?: string;
  governanceActiveLearningHandoff?: string;
  governanceHistoryManifest?: string;
  governanceAllowManualReview: boolean;
  governanceSetCurrent: boolean;
  governancePromote: boolean;
}

interface StepResult {
  name: string;
  ok: boolean;
  stdout?: unknown;
  stderr?: string;
  command: string[];
}

function resolveDefaultTrainOutputDir(modelVersion: string): string {
  return path.resolve(path.join("model", "exports", modelVersion));
}

function resolveDefaultRunName(modelVersion: string): string {
  return modelVersion;
}

function resolveDefaultGovernanceCompareSummary(trainOutputDir: string): string {
  return path.join(trainOutputDir, "compare-summary.json");
}

function resolveDefaultGovernancePerformanceReport(trainOutputDir: string): string {
  return path.join(trainOutputDir, "performance-report.mobile.json");
}

function resolveDefaultGovernanceRegistry(browserModelDir: string): string {
  return path.join(browserModelDir, "release-registry.json");
}

function resolveDefaultGovernanceHistoryManifest(trainOutputDir: string): string {
  return path.join(trainOutputDir, "release-history-manifest.json");
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    dataset: path.resolve("model/training/dataset.yaml"),
    trainOutputDir: resolveDefaultTrainOutputDir("nail-texture-seg-v1"),
    browserModelDir: path.resolve("public/models/nail-texture-seg"),
    runName: resolveDefaultRunName("nail-texture-seg-v1"),
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
    skipSourceAuthorization: false,
    skipTrainingEnvironmentCheck: false,
    requireLocalModel: false,
    candidateMode: false,
    sourceAuthorizationDatasetRoot: path.resolve("model/datasets/nail-texture-v1"),
    minSegMap50: 0.75,
    minBoxMap50: 0.85,
    maxModelMb: 15,
    finalAuditDebugPrefix: "real-model",
    runGovernance: false,
    governanceAllowManualReview: false,
    governanceSetCurrent: true,
    governancePromote: true,
  };
  const explicit = {
    trainOutputDir: false,
    runName: false,
    modelVersion: false,
    governanceCompareSummary: false,
    governancePerformanceReport: false,
    governanceRegistry: false,
    governanceHistoryManifest: false,
    split: false,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--dataset") options.dataset = path.resolve(argv[++index]);
    else if (arg === "--train-output-dir") {
      explicit.trainOutputDir = true;
      options.trainOutputDir = path.resolve(argv[++index]);
    }
    else if (arg === "--browser-model-dir") options.browserModelDir = path.resolve(argv[++index]);
    else if (arg === "--run-name") {
      explicit.runName = true;
      options.runName = argv[++index] ?? options.runName;
    }
    else if (arg === "--model-version") {
      explicit.modelVersion = true;
      options.modelVersion = argv[++index] ?? options.modelVersion;
    }
    else if (arg === "--model") options.trainModel = argv[++index] ?? options.trainModel;
    else if (arg === "--epochs") options.epochs = Number(argv[++index]);
    else if (arg === "--imgsz") options.imgsz = Number(argv[++index]);
    else if (arg === "--batch") options.batch = argv[++index] ?? options.batch;
    else if (arg === "--patience") options.patience = Number(argv[++index]);
    else if (arg === "--device") options.device = argv[++index] ?? options.device;
    else if (arg === "--workers") options.workers = Number(argv[++index]);
    else if (arg === "--split") {
      explicit.split = true;
      options.split = (argv[++index] as CliOptions["split"]) ?? options.split;
    }
    else if (arg === "--dry-run") options.dryRun = true;
    else if (arg === "--skip-train") options.skipTrain = true;
    else if (arg === "--skip-evaluate") options.skipEvaluate = true;
    else if (arg === "--skip-export") options.skipExport = true;
    else if (arg === "--skip-source-authorization") options.skipSourceAuthorization = true;
    else if (arg === "--skip-training-environment-check") options.skipTrainingEnvironmentCheck = true;
    else if (arg === "--require-local-model") options.requireLocalModel = true;
    else if (arg === "--candidate-mode") options.candidateMode = true;
    else if (arg === "--candidate-input-report") {
      options.candidateInputReport = path.resolve(argv[++index]);
    }
    else if (arg === "--candidate-validation-report") {
      options.candidateValidationReport = path.resolve(argv[++index]);
    }
    else if (arg === "--calibration-dataset") {
      options.calibrationDataset = path.resolve(argv[++index]);
    }
    else if (arg === "--calibration-dataset-report") {
      options.calibrationDatasetReport = path.resolve(argv[++index]);
    }
    else if (arg === "--calibration-truth-audit") {
      options.calibrationTruthAudit = path.resolve(argv[++index]);
    }
    else if (arg === "--calibration-output") {
      options.calibrationOutput = path.resolve(argv[++index]);
    }
    else if (arg === "--release-test-dataset") {
      options.releaseTestDataset = path.resolve(argv[++index]);
    }
    else if (arg === "--release-test-report") {
      options.releaseTestReport = path.resolve(argv[++index]);
    }
    else if (arg === "--source-authorization-dataset-root") {
      options.sourceAuthorizationDatasetRoot = path.resolve(argv[++index]);
    }
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
    else if (arg === "--run-governance") options.runGovernance = true;
    else if (arg === "--governance-compare-summary") {
      explicit.governanceCompareSummary = true;
      options.governanceCompareSummary = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-performance-report") {
      explicit.governancePerformanceReport = true;
      options.governancePerformanceReport = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-registry") {
      explicit.governanceRegistry = true;
      options.governanceRegistry = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-release-trace-draft") options.governanceReleaseTraceDraft = path.resolve(argv[++index]);
    else if (arg === "--governance-reviewed-batch-import-pipeline-report") {
      options.governanceReviewedBatchImportPipelineReport = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-reviewed-batch-root-dir") {
      options.governanceReviewedBatchRootDir = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-reviewed-batch-release-handoff") {
      options.governanceReviewedBatchReleaseHandoff = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-active-learning-handoff") {
      options.governanceActiveLearningHandoff = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-history-manifest") {
      explicit.governanceHistoryManifest = true;
      options.governanceHistoryManifest = path.resolve(argv[++index]);
    }
    else if (arg === "--governance-allow-manual-review") {
      options.governanceAllowManualReview = (argv[++index] ?? "").trim().toLowerCase() === "true";
    }
    else if (arg === "--governance-set-current") {
      options.governanceSetCurrent = (argv[++index] ?? "").trim().toLowerCase() !== "false";
    }
    else if (arg === "--governance-promote") {
      options.governancePromote = (argv[++index] ?? "").trim().toLowerCase() !== "false";
    }
    else {
      throw new Error(
        "Usage: node --experimental-strip-types scripts/run-training-release-pipeline.ts [--dataset <dataset.yaml>] [--train-output-dir <dir>] [--browser-model-dir <dir>] [--run-name <name>] [--model-version <name>] [--model <checkpoint>] [--epochs <n>] [--imgsz <n>] [--batch <value>] [--patience <n>] [--device <value>] [--workers <n>] [--split <train|val|test>] [--dry-run] [--skip-train] [--skip-evaluate] [--skip-export] [--skip-source-authorization] [--skip-training-environment-check] [--require-local-model] [--candidate-mode --candidate-input-report <report.json> --calibration-dataset <dataset.yaml> --calibration-dataset-report <report.json> --calibration-truth-audit <audit.json> --calibration-output <report.json> --release-test-dataset <dataset.yaml> --release-test-report <report.json>] [--source-authorization-dataset-root <dir>] [--min-seg-map50 <n>] [--min-box-map50 <n>] [--max-model-mb <n>] [--final-audit-image <image>] [--final-audit-output-dir <dir>] [--final-audit-debug-prefix <name>] [--final-audit-dump <dump.json>] [--final-audit-fixture-out <fixture.json>] [--final-audit-annotation-dir <annotations-dir>] [--final-audit-annotation <annotation-image>] [--final-audit-ui-review <ui-review.json>] [--run-governance] [--governance-compare-summary <compare-summary.json>] [--governance-performance-report <performance-report.json>] [--governance-registry <release-registry.json>] [--governance-release-trace-draft <release-trace-draft.json>] [--governance-reviewed-batch-import-pipeline-report <reviewed-batch-import-pipeline-report.json>] [--governance-reviewed-batch-root-dir <seed-batch-dir>] [--governance-reviewed-batch-release-handoff <reviewed-batch-release-handoff.json>] [--governance-active-learning-handoff <debug-sample-active-learning-handoff.json>] [--governance-history-manifest <release-history-manifest.json>] [--governance-allow-manual-review true|false] [--governance-set-current true|false] [--governance-promote true|false]"
      );
    }
  }

  if (!explicit.runName) {
    options.runName = resolveDefaultRunName(options.modelVersion);
  }
  if (!explicit.trainOutputDir) {
    options.trainOutputDir = resolveDefaultTrainOutputDir(options.modelVersion);
  }
  if (!explicit.governanceCompareSummary) {
    options.governanceCompareSummary = resolveDefaultGovernanceCompareSummary(options.trainOutputDir);
  }
  if (!explicit.governancePerformanceReport) {
    options.governancePerformanceReport = resolveDefaultGovernancePerformanceReport(options.trainOutputDir);
  }
  if (!explicit.governanceRegistry) {
    options.governanceRegistry = resolveDefaultGovernanceRegistry(options.browserModelDir);
  }
  if (!explicit.governanceHistoryManifest) {
    options.governanceHistoryManifest = resolveDefaultGovernanceHistoryManifest(options.trainOutputDir);
  }
  if (options.candidateMode) {
    const requiredCandidateOptions: Array<[string, string | undefined]> = [
      ["--candidate-input-report", options.candidateInputReport],
      ["--calibration-dataset", options.calibrationDataset],
      ["--calibration-dataset-report", options.calibrationDatasetReport],
      ["--calibration-truth-audit", options.calibrationTruthAudit],
      ["--calibration-output", options.calibrationOutput],
      ["--release-test-dataset", options.releaseTestDataset],
      ["--release-test-report", options.releaseTestReport],
    ];
    const missing = requiredCandidateOptions
      .filter(([, value]) => !value)
      .map(([flag]) => flag);
    if (missing.length > 0) {
      throw new Error(`--candidate-mode requires ${missing.join(", ")}`);
    }
    if (explicit.split) {
      throw new Error("--candidate-mode forbids --split; canonical validation is fixed to val and frozen release-test is fixed to test");
    }
    const laneDatasets = [options.dataset, options.calibrationDataset!, options.releaseTestDataset!]
      .map((value) => normalizePathIdentity(value));
    if (new Set(laneDatasets).size !== laneDatasets.length) {
      throw new Error("candidate training, calibration, and release-test datasets must use three different paths");
    }
    if (options.skipEvaluate) {
      throw new Error("--candidate-mode forbids --skip-evaluate because no hash-bound calibration and frozen-test resume evidence was provided");
    }
    if (options.skipExport) {
      throw new Error("--candidate-mode forbids --skip-export because no hash-bound candidate export resume evidence was provided");
    }
  }

  return options;
}

function normalizePathIdentity(filePath: string): string {
  const normalized = path.normalize(path.resolve(filePath));
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function pathsEqual(left: string, right: string): boolean {
  return normalizePathIdentity(left) === normalizePathIdentity(right);
}

function resolveBestWeightsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, options.runName, "weights", "best.pt");
}

function resolveMetricsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, "metrics.json");
}

function resolveCalibrationMetricsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, "calibration", "metrics.val.json");
}

function resolveReleaseTestMetricsPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, "release-test", "metrics.test.json");
}

function resolveEvaluationArtifactsDir(options: CliOptions): string {
  return path.join(options.trainOutputDir, "evaluation-artifacts");
}

function resolveEvaluationArtifactIndexPath(options: CliOptions): string {
  return path.join(resolveEvaluationArtifactsDir(options), "evaluation-artifacts.json");
}

function resolveCalibrationEvaluationArtifactsDir(options: CliOptions): string {
  return path.join(options.trainOutputDir, "calibration", "evaluation-artifacts");
}

function resolveCalibrationEvaluationArtifactIndexPath(options: CliOptions): string {
  return path.join(resolveCalibrationEvaluationArtifactsDir(options), "evaluation-artifacts.json");
}

function resolveReleaseTestEvaluationArtifactsDir(options: CliOptions): string {
  return path.join(options.trainOutputDir, "release-test", "evaluation-artifacts");
}

function resolveReleaseTestEvaluationArtifactIndexPath(options: CliOptions): string {
  return path.join(resolveReleaseTestEvaluationArtifactsDir(options), "evaluation-artifacts.json");
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

async function pathExists(filePath?: string): Promise<boolean> {
  if (!filePath) return false;
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function sha256File(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function fileEvidence(filePath?: string): Promise<{ path: string; sha256: string } | null> {
  if (!filePath || !(await pathExists(filePath))) return null;
  return { path: filePath, sha256: await sha256File(filePath) };
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return value as Record<string, unknown>;
}

async function readRequiredJson(filePath: string, label: string): Promise<Record<string, unknown>> {
  try {
    return asRecord(JSON.parse(await readFile(filePath, "utf8")), label);
  } catch (error) {
    throw new Error(`${label} cannot be read: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function evidencePath(document: Record<string, unknown>, key: string, label: string): string {
  const inputs = asRecord(document.inputs, `${label} inputs`);
  const evidence = asRecord(inputs[key], `${label} ${key}`);
  const filePath = String(evidence.path ?? "").trim();
  if (!filePath) throw new Error(`${label} ${key} path is missing`);
  return path.resolve(filePath);
}

async function requireEvidenceHash(
  document: Record<string, unknown>,
  key: string,
  expectedPath: string,
  label: string
): Promise<void> {
  const inputs = asRecord(document.inputs, `${label} inputs`);
  const evidence = asRecord(inputs[key], `${label} ${key}`);
  const boundPath = String(evidence.path ?? "").trim();
  const boundSha256 = String(evidence.sha256 ?? "").trim();
  if (!boundPath || !pathsEqual(boundPath, expectedPath)) {
    throw new Error(`${label} ${key} belongs to another path`);
  }
  if (!boundSha256 || boundSha256 !== await sha256File(expectedPath)) {
    throw new Error(`${label} ${key} SHA-256 binding has drifted`);
  }
}

async function verifyCandidateLaneInputs(options: CliOptions): Promise<void> {
  const requiredFiles: Array<[string, string]> = [
    [options.dataset, "candidate training dataset"],
    [options.candidateInputReport!, "candidate input report"],
    [options.calibrationDataset!, "canonical validation dataset"],
    [options.calibrationDatasetReport!, "canonical validation materialization report"],
    [options.calibrationTruthAudit!, "canonical validation truth audit"],
    [options.releaseTestDataset!, "frozen release-test dataset"],
    [options.releaseTestReport!, "frozen release-test materialization report"],
  ];
  for (const [filePath, label] of requiredFiles) {
    if (!(await pathExists(filePath))) throw new Error(`${label} does not exist: ${filePath}`);
  }

  const candidate = await readRequiredJson(options.candidateInputReport!, "candidate input report");
  if (
    candidate.ok !== true ||
    candidate.status !== "PASS" ||
    candidate.decision !== "approved_candidate_training_input" ||
    candidate.candidateTrainingEligible !== true
  ) {
    throw new Error("candidate input report is not an approved PASS");
  }
  if (!pathsEqual(String(candidate.datasetYaml ?? ""), options.dataset)) {
    throw new Error("candidate input report belongs to another training dataset");
  }
  await requireEvidenceHash(
    candidate,
    "validationDatasetYaml",
    options.calibrationDataset!,
    "candidate input report"
  );
  await requireEvidenceHash(
    candidate,
    "validationFinalAudit",
    options.calibrationTruthAudit!,
    "candidate input report"
  );
  const frozenManifestPath = evidencePath(candidate, "frozenTestManifest", "candidate input report");
  await requireEvidenceHash(candidate, "frozenTestManifest", frozenManifestPath, "candidate input report");

  const calibrationReport = await readRequiredJson(
    options.calibrationDatasetReport!,
    "canonical validation materialization report"
  );
  if (calibrationReport.ok !== true) {
    throw new Error("canonical validation materialization report is not approved");
  }
  if (!pathsEqual(String(calibrationReport.datasetYaml ?? ""), options.calibrationDataset!)) {
    throw new Error("canonical validation materialization report belongs to another dataset");
  }

  const calibrationAudit = await readRequiredJson(
    options.calibrationTruthAudit!,
    "canonical validation truth audit"
  );
  const calibrationAuditInputs = asRecord(
    calibrationAudit.inputs,
    "canonical validation truth audit inputs"
  );
  if (
    calibrationAudit.ok !== true ||
    calibrationAudit.decision !== "approved_as_calibration_truth" ||
    calibrationAudit.calibrationTruthEligible !== true ||
    calibrationAuditInputs.split !== "val" ||
    !pathsEqual(String(calibrationAuditInputs.datasetYaml ?? ""), options.calibrationDataset!) ||
    calibrationAuditInputs.datasetYamlSha256 !== await sha256File(options.calibrationDataset!)
  ) {
    throw new Error("canonical validation truth audit does not bind the selected calibration dataset");
  }

  const releaseReport = await readRequiredJson(
    options.releaseTestReport!,
    "frozen release-test materialization report"
  );
  const releaseCounts = asRecord(releaseReport.counts, "frozen release-test counts");
  const releaseIsolation = asRecord(
    releaseReport.sourceIsolation,
    "frozen release-test source isolation"
  );
  if (
    releaseReport.ok !== true ||
    releaseReport.decision !== "evaluation_only_frozen_reviewed_snapshot" ||
    releaseReport.trainingUse !== "prohibited" ||
    !pathsEqual(String(releaseReport.datasetYaml ?? ""), options.releaseTestDataset!) ||
    Number(releaseCounts.images ?? 0) <= 0 ||
    !Array.isArray(releaseIsolation.parentSourceGroupOverlap) ||
    releaseIsolation.parentSourceGroupOverlap.length !== 0 ||
    !Array.isArray(releaseIsolation.exactImageHashOverlap) ||
    releaseIsolation.exactImageHashOverlap.length !== 0 ||
    (Array.isArray(releaseReport.errors) && releaseReport.errors.length !== 0)
  ) {
    throw new Error("frozen release-test report is not an isolated non-empty evaluation-only dataset");
  }

  const evaluationManifestPath = path.resolve(String(releaseReport.evaluationManifest ?? ""));
  if (!(await pathExists(evaluationManifestPath))) {
    throw new Error("frozen release-test evaluation manifest does not exist");
  }
  const evaluationManifest = await readRequiredJson(
    evaluationManifestPath,
    "frozen release-test evaluation manifest"
  );
  const frozenManifest = await readRequiredJson(frozenManifestPath, "frozen release-test snapshot manifest");
  const evaluationCounts = asRecord(
    evaluationManifest.counts,
    "frozen release-test evaluation manifest counts"
  );
  if (
    evaluationManifest.decision !== "evaluation_only_frozen_reviewed_snapshot" ||
    evaluationManifest.trainingUse !== "prohibited" ||
    evaluationManifest.sourceItemsSha256 !== frozenManifest.itemsSha256 ||
    Number(evaluationCounts.images ?? -1) !== Number(releaseCounts.images ?? -2) ||
    evaluationManifest.recordsSha256 !== releaseReport.recordsSha256
  ) {
    throw new Error("frozen release-test report is not bound to the candidate frozen snapshot");
  }
}

function plannedStep(name: string, command: string[]): StepResult {
  return {
    name,
    ok: true,
    stdout: { planned: true, dryRun: true },
    command,
  };
}

async function runCandidateCommand(
  options: CliOptions,
  name: string,
  command: string[],
  cwd: string
): Promise<StepResult> {
  return options.dryRun ? plannedStep(name, command) : runCommand(name, command, cwd);
}

async function verifyCandidateResume(
  options: CliOptions,
  weightsPath: string
): Promise<StepResult> {
  const summaryPath = path.join(options.trainOutputDir, "train-summary.json");
  const command = ["internal:verify-candidate-resume", summaryPath];
  try {
    const summary = (await readJsonIfExists(summaryPath)) as
      | {
          dataset_yaml?: string;
          dataset_yaml_sha256?: string;
          training_intent?: string;
          candidate_input_evidence?: { path?: string; sha256?: string };
          best_weights_path?: string;
          best_weights_sha256?: string;
        }
      | null;
    if (!summary) throw new Error("candidate --skip-train requires train-summary.json");
    if (summary.training_intent !== "candidate") {
      throw new Error("existing train summary is not a candidate run");
    }
    if (path.resolve(summary.dataset_yaml ?? "") !== options.dataset) {
      throw new Error("existing train summary belongs to another dataset");
    }
    if (summary.dataset_yaml_sha256 !== await sha256File(options.dataset)) {
      throw new Error("candidate dataset changed after the existing training run");
    }
    if (
      path.resolve(summary.candidate_input_evidence?.path ?? "") !==
        options.candidateInputReport ||
      summary.candidate_input_evidence?.sha256 !==
        (await sha256File(options.candidateInputReport!))
    ) {
      throw new Error("existing train summary belongs to another candidate input report");
    }
    if (
      path.resolve(summary.best_weights_path ?? "") !== weightsPath ||
      summary.best_weights_sha256 !== (await sha256File(weightsPath))
    ) {
      throw new Error("existing candidate weights are missing or hash-drifted");
    }
    return {
      name: "verify-candidate-resume",
      ok: true,
      stdout: { summaryPath, weightsPath },
      command,
    };
  } catch (error) {
    return {
      name: "verify-candidate-resume",
      ok: false,
      stderr: error instanceof Error ? error.message : String(error),
      command,
    };
  }
}

async function resolveGovernanceContext(options: CliOptions): Promise<{
  releaseTraceDraftPath: string | null;
  reviewedBatchImportPipelineReportPath: string | null;
  reviewedBatchReleaseHandoffPath: string | null;
  reviewedBatchRootDir: string | null;
  activeLearningHandoffPath: string | null;
}> {
  let releaseTraceDraftPath = options.governanceReleaseTraceDraft ?? null;
  let reviewedBatchImportPipelineReportPath =
    options.governanceReviewedBatchImportPipelineReport ?? null;
  let reviewedBatchReleaseHandoffPath = options.governanceReviewedBatchReleaseHandoff ?? null;
  let reviewedBatchRootDir = options.governanceReviewedBatchRootDir ?? null;
  const activeLearningHandoffPath = options.governanceActiveLearningHandoff ?? null;

  if (reviewedBatchReleaseHandoffPath) {
    const handoff = (await readJsonIfExists(reviewedBatchReleaseHandoffPath)) as
      | {
          rootDir?: string;
          governanceHints?: {
            reviewedBatchRootDir?: string | null;
            reviewedBatchImportPipelineReportPath?: string | null;
            releaseTraceDraftPath?: string | null;
          };
        }
      | null;
    reviewedBatchRootDir =
      reviewedBatchRootDir ??
      handoff?.governanceHints?.reviewedBatchRootDir ??
      handoff?.rootDir ??
      null;
    releaseTraceDraftPath =
      releaseTraceDraftPath ?? handoff?.governanceHints?.releaseTraceDraftPath ?? null;
    reviewedBatchImportPipelineReportPath =
      reviewedBatchImportPipelineReportPath ??
      handoff?.governanceHints?.reviewedBatchImportPipelineReportPath ??
      null;
  }

  if (activeLearningHandoffPath) {
    const handoff = (await readJsonIfExists(activeLearningHandoffPath)) as
      | {
          governanceHints?: {
            activeLearningPipelineReportPath?: string | null;
            activeLearningReleaseTraceDraftPath?: string | null;
          };
        }
      | null;
    releaseTraceDraftPath =
      releaseTraceDraftPath ??
      handoff?.governanceHints?.activeLearningReleaseTraceDraftPath ??
      null;
  }

  if (reviewedBatchRootDir) {
    const draftCandidate = path.join(
      reviewedBatchRootDir,
      "release-trace-draft.json"
    );
    const reportCandidate = path.join(
      reviewedBatchRootDir,
      "reviewed-batch-import-pipeline-report.json"
    );
    const handoffCandidate = path.join(
      reviewedBatchRootDir,
      "reviewed-batch-release-handoff.json"
    );
    if (!releaseTraceDraftPath && (await pathExists(draftCandidate))) {
      releaseTraceDraftPath = draftCandidate;
    }
    if (!reviewedBatchImportPipelineReportPath && (await pathExists(reportCandidate))) {
      reviewedBatchImportPipelineReportPath = reportCandidate;
    }
    if (!reviewedBatchReleaseHandoffPath && (await pathExists(handoffCandidate))) {
      reviewedBatchReleaseHandoffPath = handoffCandidate;
    }
  }

  if (!releaseTraceDraftPath && reviewedBatchImportPipelineReportPath) {
    const reviewedBatchImportPipelineReport = (await readJsonIfExists(
      reviewedBatchImportPipelineReportPath
    )) as { rootDir?: string } | null;
    const rootDir = reviewedBatchImportPipelineReport?.rootDir;
    if (rootDir) {
      const draftCandidate = path.join(rootDir, "release-trace-draft.json");
      if (await pathExists(draftCandidate)) {
        releaseTraceDraftPath = draftCandidate;
      }
    }
  }

  if (!reviewedBatchImportPipelineReportPath && releaseTraceDraftPath) {
    const releaseTraceDraft = (await readJsonIfExists(releaseTraceDraftPath)) as
      | { batch?: { rootDir?: string | null } | null }
      | null;
    const rootDir = releaseTraceDraft?.batch?.rootDir;
    if (rootDir) {
      const reportCandidate = path.join(rootDir, "reviewed-batch-import-pipeline-report.json");
      if (await pathExists(reportCandidate)) {
        reviewedBatchImportPipelineReportPath = reportCandidate;
      }
    }
  }

  return {
    releaseTraceDraftPath,
    reviewedBatchImportPipelineReportPath,
    reviewedBatchReleaseHandoffPath,
    reviewedBatchRootDir,
    activeLearningHandoffPath,
  };
}

function resolveGovernanceReportPath(options: CliOptions): string {
  return path.join(options.trainOutputDir, "release-governance-pipeline-report.json");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const cwd = path.resolve(".");
  const reportPath = path.join(options.trainOutputDir, "training-release-pipeline-report.json");

  const weightsPath = resolveBestWeightsPath(options);
  const metricsPath = options.candidateMode
    ? resolveReleaseTestMetricsPath(options)
    : resolveMetricsPath(options);
  const evaluationArtifactsDir = resolveEvaluationArtifactsDir(options);
  const evaluationArtifactIndexPath = resolveEvaluationArtifactIndexPath(options);
  const calibrationMetricsPath = resolveCalibrationMetricsPath(options);
  const calibrationEvaluationArtifactsDir = resolveCalibrationEvaluationArtifactsDir(options);
  const calibrationEvaluationArtifactIndexPath = resolveCalibrationEvaluationArtifactIndexPath(options);
  const releaseTestMetricsPath = resolveReleaseTestMetricsPath(options);
  const releaseTestEvaluationArtifactsDir = resolveReleaseTestEvaluationArtifactsDir(options);
  const releaseTestEvaluationArtifactIndexPath = resolveReleaseTestEvaluationArtifactIndexPath(options);
  const manifestPath = resolveManifestPath(options);

  const steps: StepResult[] = [];
  if (options.candidateMode) {
    await verifyCandidateLaneInputs(options);
    if (
      pathsEqual(options.calibrationOutput!, calibrationMetricsPath) ||
      pathsEqual(options.calibrationOutput!, releaseTestMetricsPath)
    ) {
      throw new Error("--calibration-output must not overwrite canonical val or frozen release-test metrics");
    }
    if (options.skipTrain) {
      const resumeResult = await verifyCandidateResume(options, weightsPath);
      steps.push(resumeResult);
      if (!resumeResult.ok) {
        return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
      }
    }
    const command = [
      "python",
      "model/training/train-yolo-seg.py",
      "--dataset",
      options.dataset,
      "--output-dir",
      options.trainOutputDir,
      "--candidate-mode",
      "--candidate-input-report",
      options.candidateInputReport!,
      "--dry-run",
    ];
    const result = await runCandidateCommand(options, "candidate-input-preflight", command, cwd);
    steps.push(result);
    if (!result.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }
    const releaseTestPreflightCommand = [
      "python",
      "model/training/materialize-frozen-release-test-evaluation.py",
      "--verify-report",
      options.releaseTestReport!,
      "--expected-dataset",
      options.releaseTestDataset!,
    ];
    const releaseTestPreflightResult = await runCandidateCommand(
      options,
      "release-test-preflight",
      releaseTestPreflightCommand,
      cwd
    );
    steps.push(releaseTestPreflightResult);
    if (!releaseTestPreflightResult.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }
  }
  if (
    !options.candidateMode &&
    !options.dryRun &&
    !options.skipTrain &&
    !options.skipSourceAuthorization
  ) {
    const command = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "model/training/verify-training-dataset-readiness.ts",
      "--dataset-root",
      options.sourceAuthorizationDatasetRoot,
      "--authorization-mode",
      "release",
      "--output",
      path.join(options.trainOutputDir, "training-dataset-readiness-release.json"),
    ];
    const result = await runCommand("verify-training-dataset-readiness", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }
  if (!options.skipTrain && !options.skipTrainingEnvironmentCheck) {
    const command = [
      "python",
      "model/training/check-training-environment.py",
      "--dataset",
      options.dataset,
      "--output-dir",
      options.trainOutputDir,
      "--model",
      options.trainModel,
      "--run-name",
      options.runName,
      ...(options.requireLocalModel ? ["--require-local-model"] : []),
      ...(!options.dryRun ? ["--strict"] : []),
    ];
    const result = options.candidateMode
      ? await runCandidateCommand(options, "check-training-environment", command, cwd)
      : await runCommand("check-training-environment", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

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
      ...(options.candidateMode
        ? ["--candidate-mode", "--candidate-input-report", options.candidateInputReport!]
        : []),
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const result = options.candidateMode
      ? await runCandidateCommand(options, "train-yolo-seg", command, cwd)
      : await runCommand("train-yolo-seg", command, cwd);
    steps.push(result);
    if (!result.ok) return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
  }

  if (options.candidateMode) {
    const calibrationEvaluateCommand = [
      "python",
      "model/training/evaluate.py",
      "--dataset",
      options.calibrationDataset!,
      "--train-output-dir",
      options.trainOutputDir,
      "--run-name",
      options.runName,
      "--weights",
      weightsPath,
      "--output",
      calibrationMetricsPath,
      "--artifacts-dir",
      calibrationEvaluationArtifactsDir,
      "--split",
      "val",
      "--imgsz",
      String(options.imgsz),
      "--device",
      options.device,
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const calibrationEvaluateResult = await runCandidateCommand(
      options,
      "evaluate-canonical-validation",
      calibrationEvaluateCommand,
      cwd
    );
    steps.push(calibrationEvaluateResult);
    if (!calibrationEvaluateResult.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }

    if (!options.dryRun) {
      const verifyCalibrationCommand = [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-evaluation-artifacts.ts",
        "--index",
        calibrationEvaluationArtifactIndexPath,
        "--require-split",
        "val",
      ];
      const verifyCalibrationResult = await runCommand(
        "verify-canonical-validation-artifacts",
        verifyCalibrationCommand,
        cwd
      );
      steps.push(verifyCalibrationResult);
      if (!verifyCalibrationResult.ok) {
        return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
      }
    }

    const calibrateCommand = [
      "python",
      "model/training/calibrate-model-score-threshold.py",
      "--dataset",
      options.calibrationDataset!,
      "--dataset-report",
      options.calibrationDatasetReport!,
      "--metrics",
      calibrationMetricsPath,
      "--truth-audit",
      options.calibrationTruthAudit!,
      "--output",
      options.calibrationOutput!,
    ];
    const calibrateResult = await runCandidateCommand(
      options,
      "calibrate-model-score-threshold",
      calibrateCommand,
      cwd
    );
    steps.push(calibrateResult);
    if (!calibrateResult.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }

    const releaseTestEvaluateCommand = [
      "python",
      "model/training/evaluate.py",
      "--dataset",
      options.releaseTestDataset!,
      "--train-output-dir",
      options.trainOutputDir,
      "--run-name",
      options.runName,
      "--weights",
      weightsPath,
      "--output",
      releaseTestMetricsPath,
      "--artifacts-dir",
      releaseTestEvaluationArtifactsDir,
      "--split",
      "test",
      "--imgsz",
      String(options.imgsz),
      "--device",
      options.device,
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const releaseTestEvaluateResult = await runCandidateCommand(
      options,
      "evaluate-frozen-release-test",
      releaseTestEvaluateCommand,
      cwd
    );
    steps.push(releaseTestEvaluateResult);
    if (!releaseTestEvaluateResult.ok) {
      return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
    }

    if (!options.dryRun) {
      const verifyReleaseTestCommand = [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-evaluation-artifacts.ts",
        "--index",
        releaseTestEvaluationArtifactIndexPath,
        "--require-split",
        "test",
      ];
      const verifyReleaseTestResult = await runCommand(
        "verify-frozen-release-test-artifacts",
        verifyReleaseTestCommand,
        cwd
      );
      steps.push(verifyReleaseTestResult);
      if (!verifyReleaseTestResult.ok) {
        return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
      }
    }
  } else if (!options.skipEvaluate) {
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
      "--artifacts-dir",
      evaluationArtifactsDir,
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

    if (!options.dryRun) {
      const verifyCommand = [
        process.execPath,
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-evaluation-artifacts.ts",
        "--index",
        evaluationArtifactIndexPath,
        "--require-split",
        options.split,
      ];
      const verifyResult = await runCommand("verify-evaluation-artifacts", verifyCommand, cwd);
      steps.push(verifyResult);
      if (!verifyResult.ok) {
        return await finish(false, options, reportPath, steps, weightsPath, metricsPath, manifestPath);
      }
    }
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
      ...(options.candidateMode
        ? ["--candidate-mode", "--calibration-report", options.calibrationOutput!]
        : []),
      ...(options.dryRun ? ["--dry-run"] : []),
    ];
    const result = options.candidateMode
      ? await runCandidateCommand(options, "export-onnx", command, cwd)
      : await runCommand("export-onnx", command, cwd);
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
  const governanceReportPath = resolveGovernanceReportPath(options);
  let governanceStep = steps.find((step) => step.name === "run-release-governance-pipeline");
  const governanceContext = await resolveGovernanceContext(options);

  const buildReport = async () => ({
    ok: ok && steps.every((step) => step.ok),
    reportPath,
    mode: options.dryRun ? "dry-run" : "real-run",
    paths: {
      dataset: options.dataset,
      trainingDataset: options.dataset,
      calibrationDataset: options.calibrationDataset ?? null,
      calibrationDatasetReport: options.calibrationDatasetReport ?? null,
      calibrationTruthAudit: options.calibrationTruthAudit ?? null,
      calibrationOutput: options.calibrationOutput ?? null,
      releaseTestDataset: options.releaseTestDataset ?? null,
      releaseTestReport: options.releaseTestReport ?? null,
      trainOutputDir: options.trainOutputDir,
      browserModelDir: options.browserModelDir,
      weightsPath,
      metricsPath,
      evaluationArtifactsDir: resolveEvaluationArtifactsDir(options),
      evaluationArtifactIndexPath: resolveEvaluationArtifactIndexPath(options),
      calibrationMetricsPath: options.candidateMode
        ? resolveCalibrationMetricsPath(options)
        : null,
      calibrationEvaluationArtifactsDir: options.candidateMode
        ? resolveCalibrationEvaluationArtifactsDir(options)
        : null,
      calibrationEvaluationArtifactIndexPath: options.candidateMode
        ? resolveCalibrationEvaluationArtifactIndexPath(options)
        : null,
      releaseTestMetricsPath: options.candidateMode
        ? resolveReleaseTestMetricsPath(options)
        : null,
      releaseTestEvaluationArtifactsDir: options.candidateMode
        ? resolveReleaseTestEvaluationArtifactsDir(options)
        : null,
      releaseTestEvaluationArtifactIndexPath: options.candidateMode
        ? resolveReleaseTestEvaluationArtifactIndexPath(options)
        : null,
      manifestPath,
      governanceReportPath: options.runGovernance ? governanceReportPath : null,
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
      skipSourceAuthorization: options.skipSourceAuthorization,
      skipTrainingEnvironmentCheck: options.skipTrainingEnvironmentCheck,
      requireLocalModel: options.requireLocalModel,
      trainingIntent: options.candidateMode ? "candidate" : "experiment",
      candidateInputReport: options.candidateInputReport ?? null,
      candidateValidationReport: options.candidateValidationReport ?? null,
      calibrationDataset: options.calibrationDataset ?? null,
      calibrationDatasetReport: options.calibrationDatasetReport ?? null,
      calibrationTruthAudit: options.calibrationTruthAudit ?? null,
      calibrationOutput: options.calibrationOutput ?? null,
      releaseTestDataset: options.releaseTestDataset ?? null,
      releaseTestReport: options.releaseTestReport ?? null,
      sourceAuthorizationDatasetRoot: options.sourceAuthorizationDatasetRoot,
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
      runGovernance: options.runGovernance,
      governanceCompareSummary: options.governanceCompareSummary ?? null,
      governancePerformanceReport: options.governancePerformanceReport ?? null,
      governanceRegistry: options.governanceRegistry ?? null,
      governanceReleaseTraceDraft: governanceContext.releaseTraceDraftPath,
      governanceReviewedBatchImportPipelineReport:
        governanceContext.reviewedBatchImportPipelineReportPath,
      governanceReviewedBatchRootDir: governanceContext.reviewedBatchRootDir,
      governanceReviewedBatchReleaseHandoff:
        governanceContext.reviewedBatchReleaseHandoffPath,
      governanceActiveLearningHandoff: governanceContext.activeLearningHandoffPath,
      governanceHistoryManifest: options.governanceHistoryManifest ?? null,
      governanceAllowManualReview: options.governanceAllowManualReview,
      governanceSetCurrent: options.governanceSetCurrent,
      governancePromote: options.governancePromote,
    },
    evidence: options.candidateMode
      ? {
          trainingDataset: await fileEvidence(options.dataset),
          candidateInputReport: await fileEvidence(options.candidateInputReport),
          calibrationDataset: await fileEvidence(options.calibrationDataset),
          calibrationDatasetReport: await fileEvidence(options.calibrationDatasetReport),
          calibrationTruthAudit: await fileEvidence(options.calibrationTruthAudit),
          calibrationOutput: await fileEvidence(options.calibrationOutput),
          releaseTestDataset: await fileEvidence(options.releaseTestDataset),
          releaseTestReport: await fileEvidence(options.releaseTestReport),
        }
      : null,
    steps,
    artifacts: {
      trainSummary: await readJsonIfExists(path.join(options.trainOutputDir, "train-summary.json")),
      trainingDatasetReadiness: await readJsonIfExists(
        path.join(options.trainOutputDir, "training-dataset-readiness-release.json")
      ),
      metrics: await readJsonIfExists(metricsPath),
      calibrationMetrics: options.candidateMode
        ? await readJsonIfExists(resolveCalibrationMetricsPath(options))
        : null,
      calibration: options.candidateMode
        ? await readJsonIfExists(options.calibrationOutput ?? "")
        : null,
      releaseTestMetrics: options.candidateMode
        ? await readJsonIfExists(resolveReleaseTestMetricsPath(options))
        : null,
      recognitionPerformance: await readJsonIfExists(options.governancePerformanceReport ?? ""),
      evaluationArtifacts: await readJsonIfExists(
        options.candidateMode
          ? resolveReleaseTestEvaluationArtifactIndexPath(options)
          : resolveEvaluationArtifactIndexPath(options)
      ),
      calibrationEvaluationArtifacts: options.candidateMode
        ? await readJsonIfExists(resolveCalibrationEvaluationArtifactIndexPath(options))
        : null,
      releaseTestEvaluationArtifacts: options.candidateMode
        ? await readJsonIfExists(resolveReleaseTestEvaluationArtifactIndexPath(options))
        : null,
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
      finalAuditTextureQualityGate: await readJsonIfExists(
        path.join(
          options.finalAuditOutputDir ?? path.join(options.trainOutputDir, "real-model-final-audit"),
          "texture-quality-gate.json"
        )
      ),
      releaseGovernance: await readJsonIfExists(governanceReportPath),
    },
  });

  let report = await buildReport();
  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");

  if (options.runGovernance && !options.dryRun && !governanceStep) {
    const governanceCommand = [
      process.execPath,
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/run-release-governance-pipeline.ts",
      "--training-release-pipeline-report",
      reportPath,
      ...(options.governanceCompareSummary ? ["--compare-summary", options.governanceCompareSummary] : []),
      ...(options.governancePerformanceReport ? ["--performance-report", options.governancePerformanceReport] : []),
      ...(options.governanceRegistry ? ["--registry", options.governanceRegistry] : []),
      ...(governanceContext.releaseTraceDraftPath
        ? ["--release-trace-draft", governanceContext.releaseTraceDraftPath]
        : []),
      ...(governanceContext.reviewedBatchImportPipelineReportPath
        ? ["--reviewed-batch-import-pipeline-report", governanceContext.reviewedBatchImportPipelineReportPath]
        : []),
      ...(options.governanceHistoryManifest ? ["--history-manifest", options.governanceHistoryManifest] : []),
      "--allow-manual-review",
      String(options.governanceAllowManualReview),
      "--set-current",
      String(options.governanceSetCurrent),
      "--promote",
      String(options.governancePromote),
    ];
    governanceStep = await runCommand("run-release-governance-pipeline", governanceCommand, path.resolve("."));
    steps.push(governanceStep);
    report = await buildReport();
  }

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exitCode = 1;
}

await main();
