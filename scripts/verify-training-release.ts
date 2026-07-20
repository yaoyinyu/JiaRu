import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { promisify } from "node:util";
import { readFile, readdir } from "node:fs/promises";

const execFileAsync = promisify(execFile);

interface MetricsLike {
  dataset_yaml: string;
  dataset_root: string;
  dataset_yaml_sha256?: string;
  weights: string;
  weights_sha256?: string;
  output: string;
  artifacts_dir?: string;
  artifact_index?: string;
  split: "train" | "val" | "test";
  imgsz: number;
  device: string;
  dry_run: boolean;
  box_map50: number;
  box_map: number;
  seg_map50: number;
  seg_map: number;
  source_dataset_inventory_sha256_before?: string;
  source_dataset_inventory_sha256_after?: string;
  source_dataset_unchanged?: boolean;
  evaluation_artifacts?: {
    directory?: string;
    index?: string;
    index_sha256?: string;
    files_sha256?: string;
  };
}

interface ManifestLike {
  scoreThreshold?: number;
  scoreThresholdEvidence?: {
    path?: string;
    sha256?: string;
    datasetYamlSha256?: string;
    metricsSha256?: string;
    artifactIndexSha256?: string;
    weightsSha256?: string;
    decision?: string;
  };
}

interface ReleaseTestReportLike {
  ok?: boolean;
  status?: string;
  decision?: string;
  trainingUse?: string;
  datasetYaml?: string;
  counts?: { images?: number; trainImages?: number; validationImages?: number; testImages?: number };
  artifacts?: { datasetYaml?: { path?: string; sha256?: string } };
  files_sha256?: string;
}

interface CalibrationReportLike {
  decision?: string;
  calibrationEligible?: boolean;
  manifestScoreThreshold?: number | null;
  inputs?: {
    datasetYamlSha256?: string;
    metricsSha256?: string;
    artifactIndexSha256?: string;
    weightsSha256?: string;
  };
}

interface EvaluationArtifactIndexLike {
  split?: string;
  artifacts_dir?: string;
  files?: string[];
  file_records?: Array<{ path?: string; sha256?: string }>;
  files_sha256?: string;
  prediction_records?: Array<{ stem?: string; path?: string | null; sha256?: string | null; prediction_count?: number }>;
  prediction_records_sha256?: string;
}

interface ArtifactSummary {
  manifestPath: string;
  modelPath: string;
  version: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  labels: string[];
  modelExists: boolean;
  modelSizeBytes: number;
  modelSizeMb: number;
  maxModelMb: number;
  ok: boolean;
  errors: string[];
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-training-release.ts --metrics <metrics.json> --manifest <manifest.json> [--candidate-mode --calibration-report <report.json> --release-test-report <report.json>] [--min-seg-map50 0.75] [--min-box-map50 0.85] [--max-model-mb 15]"
  );
}

function normalizePath(filePath: string): string {
  const normalized = path.normalize(path.resolve(filePath));
  return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function samePath(left: string, right: string): boolean {
  return normalizePath(left) === normalizePath(right);
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`)
    .join(",")}}`;
}

function sha256Buffer(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(filePath: string): Promise<string> {
  return sha256Buffer(await readFile(filePath));
}

async function listFiles(root: string): Promise<string[]> {
  const output: string[] = [];
  async function visit(current: string): Promise<void> {
    for (const entry of await readdir(current, { withFileTypes: true })) {
      const absolute = path.join(current, entry.name);
      if (entry.isDirectory()) await visit(absolute);
      else if (entry.isFile()) output.push(path.relative(root, absolute).split(path.sep).join("/"));
    }
  }
  await visit(root);
  return output.sort();
}

function safeRelative(relativePath: string): boolean {
  return Boolean(relativePath) && !path.isAbsolute(relativePath) && !relativePath.split(/[\\/]+/).includes("..");
}

async function runDeepVerifier(command: string[]): Promise<{ ok: boolean; value?: unknown; error?: string }> {
  try {
    const { stdout } = await execFileAsync(command[0]!, command.slice(1), { cwd: path.resolve(".") });
    return { ok: true, value: JSON.parse(stdout) };
  } catch (error) {
    const failure = error as Error & { stdout?: string; stderr?: string };
    return { ok: false, error: (failure.stderr || failure.stdout || failure.message).trim() };
  }
}

const args = process.argv.slice(2);
let metricsPath = "model/exports/nail-texture-seg-v1/metrics.json";
let manifestPath = "public/models/nail-texture-seg/manifest.json";
let minSegMap50 = 0.75;
let minBoxMap50 = 0.85;
let maxModelMb = 15;
let candidateMode = false;
let calibrationReportPath: string | undefined;
let releaseTestReportPath: string | undefined;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--metrics") {
    metricsPath = args[++index] ?? usage();
    continue;
  }
  if (arg === "--manifest") {
    manifestPath = args[++index] ?? usage();
    continue;
  }
  if (arg === "--min-seg-map50") {
    minSegMap50 = Number(args[++index]);
    if (!Number.isFinite(minSegMap50)) usage();
    continue;
  }
  if (arg === "--min-box-map50") {
    minBoxMap50 = Number(args[++index]);
    if (!Number.isFinite(minBoxMap50)) usage();
    continue;
  }
  if (arg === "--max-model-mb") {
    maxModelMb = Number(args[++index]);
    if (!Number.isFinite(maxModelMb) || maxModelMb <= 0) usage();
    continue;
  }
  if (arg === "--candidate-mode") {
    candidateMode = true;
    continue;
  }
  if (arg === "--calibration-report") {
    calibrationReportPath = args[++index] ?? usage();
    continue;
  }
  if (arg === "--release-test-report") {
    releaseTestReportPath = args[++index] ?? usage();
    continue;
  }
  usage();
}

if (candidateMode && (!calibrationReportPath || !releaseTestReportPath)) {
  throw new Error("--candidate-mode requires --calibration-report and --release-test-report");
}
if (!candidateMode && (calibrationReportPath || releaseTestReportPath)) {
  throw new Error("candidate evidence arguments require --candidate-mode");
}

const absoluteMetricsPath = path.resolve(metricsPath);
const absoluteManifestPath = path.resolve(manifestPath);
const metrics = JSON.parse(
  await readFile(absoluteMetricsPath, "utf8")
) as MetricsLike;
const manifest = JSON.parse(await readFile(absoluteManifestPath, "utf8")) as ManifestLike;

const { stdout: artifactStdout } = await execFileAsync(
  process.execPath,
  [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/verify-model-artifact.ts",
    absoluteManifestPath,
    "--max-model-mb",
    String(maxModelMb),
  ],
  {
    cwd: path.resolve("."),
  }
);
const artifact = JSON.parse(artifactStdout) as ArtifactSummary;

const errors: string[] = [];
const warnings: string[] = [];

if (candidateMode && metrics.split !== "test") {
  errors.push(`candidate release metrics split must be test, found ${metrics.split}`);
} else if (metrics.split !== "test") {
  warnings.push(`metrics split is ${metrics.split}; release gating is usually done on test split`);
}
if (metrics.dry_run) {
  errors.push("metrics file must come from a real evaluation run, not dry-run output");
}
if (!Number.isFinite(metrics.seg_map50) || metrics.seg_map50 < minSegMap50) {
  errors.push(`seg_map50 ${metrics.seg_map50} is below required threshold ${minSegMap50}`);
}
if (!Number.isFinite(metrics.box_map50) || metrics.box_map50 < minBoxMap50) {
  errors.push(`box_map50 ${metrics.box_map50} is below required threshold ${minBoxMap50}`);
}
if (!Number.isFinite(metrics.imgsz) || metrics.imgsz <= 0) {
  errors.push("metrics.imgsz must be a positive number");
}
if (artifact.inputSize !== metrics.imgsz) {
  errors.push(
    `manifest inputSize ${artifact.inputSize} does not match metrics imgsz ${metrics.imgsz}`
  );
}

const expectedVersion = path.basename(path.dirname(absoluteMetricsPath));
if (artifact.version !== expectedVersion) {
  warnings.push(
    `manifest version ${artifact.version} does not match metrics parent directory ${expectedVersion}`
  );
}
if (!artifact.labels.includes("nail_texture")) {
  errors.push("manifest labels must include nail_texture");
}
if (!artifact.ok) {
  errors.push(...artifact.errors);
}

const candidateEvidence: Record<string, unknown> | null = candidateMode ? {} : null;
if (candidateMode) {
  const absoluteCalibrationReport = path.resolve(calibrationReportPath!);
  const absoluteReleaseTestReport = path.resolve(releaseTestReportPath!);
  const absoluteWeights = path.resolve(metrics.weights ?? "");
  const absoluteDataset = path.resolve(metrics.dataset_yaml ?? "");

  try {
    if ((await sha256File(absoluteMetricsPath)).length !== 64) {
      errors.push("release metrics file SHA-256 could not be computed");
    }
    const currentWeightsSha256 = await sha256File(absoluteWeights);
    if (metrics.weights_sha256 !== currentWeightsSha256) {
      errors.push("release metrics weights SHA-256 does not match the current checkpoint");
    }
    const currentDatasetSha256 = await sha256File(absoluteDataset);
    if (metrics.dataset_yaml_sha256 !== currentDatasetSha256) {
      errors.push("release metrics dataset YAML SHA-256 does not match the current file");
    }

    const releaseReport = JSON.parse(
      await readFile(absoluteReleaseTestReport, "utf8")
    ) as ReleaseTestReportLike;
    const reportDataset = releaseReport.artifacts?.datasetYaml?.path ?? releaseReport.datasetYaml ?? "";
    if (!samePath(reportDataset, absoluteDataset)) {
      errors.push("release metrics dataset does not match the frozen release-test report");
    }
    if (releaseReport.artifacts?.datasetYaml?.sha256 !== currentDatasetSha256) {
      errors.push("frozen release-test report dataset YAML hash does not match current data");
    }
    if (
      releaseReport.ok !== true ||
      releaseReport.status !== "PASS" ||
      releaseReport.decision !== "evaluation_only_frozen_reviewed_snapshot" ||
      releaseReport.trainingUse !== "prohibited"
    ) {
      errors.push("release-test report is not an approved evaluation-only frozen snapshot");
    }
    if (
      releaseReport.counts?.trainImages !== 0 ||
      releaseReport.counts?.validationImages !== 0 ||
      !Number.isInteger(releaseReport.counts?.testImages) ||
      (releaseReport.counts?.testImages ?? 0) < 1 ||
      releaseReport.counts?.images !== releaseReport.counts?.testImages
    ) {
      errors.push("release-test report split counts are not test-only and non-empty");
    }
    if (
      metrics.source_dataset_unchanged !== true ||
      metrics.source_dataset_inventory_sha256_before !== releaseReport.files_sha256 ||
      metrics.source_dataset_inventory_sha256_after !== releaseReport.files_sha256
    ) {
      errors.push("release metrics do not bind the unchanged frozen release-test dataset inventory");
    }

    const releaseVerifier = await runDeepVerifier([
      "python",
      "model/training/materialize-frozen-release-test-evaluation.py",
      "--verify-report",
      absoluteReleaseTestReport,
      "--expected-dataset",
      absoluteDataset,
    ]);
    if (!releaseVerifier.ok) {
      errors.push(`frozen release-test deep verification failed: ${releaseVerifier.error}`);
    }

    const artifactIndexPath = path.resolve(
      metrics.evaluation_artifacts?.index ?? metrics.artifact_index ?? ""
    );
    const artifactIndexBytes = await readFile(artifactIndexPath);
    const artifactIndexSha256 = sha256Buffer(artifactIndexBytes);
    const artifactIndex = JSON.parse(artifactIndexBytes.toString("utf8")) as EvaluationArtifactIndexLike;
    if (artifactIndex.split !== "test") errors.push("evaluation artifact index split must be test");
    if (metrics.evaluation_artifacts?.index_sha256 !== artifactIndexSha256) {
      errors.push("release metrics evaluation artifact index hash has drifted");
    }
    if (!samePath(metrics.artifacts_dir ?? "", path.dirname(artifactIndexPath))) {
      errors.push("release metrics artifact directory does not match the artifact index");
    }
    if (
      !samePath(metrics.evaluation_artifacts?.directory ?? "", path.dirname(artifactIndexPath)) ||
      !samePath(artifactIndex.artifacts_dir ?? "", path.dirname(artifactIndexPath))
    ) {
      errors.push("evaluation artifact directory evidence is inconsistent");
    }
    const currentArtifactFiles = (await listFiles(path.dirname(artifactIndexPath))).filter(
      (item) => item !== path.basename(artifactIndexPath)
    );
    if (JSON.stringify(currentArtifactFiles) !== JSON.stringify(artifactIndex.files ?? [])) {
      errors.push("evaluation artifact inventory has unknown, missing, or reordered files");
    }
    const currentArtifactRecords = await Promise.all(
      currentArtifactFiles.map(async (relativePath) => ({
        path: relativePath,
        sha256: await sha256File(path.join(path.dirname(artifactIndexPath), relativePath)),
      }))
    );
    if (JSON.stringify(currentArtifactRecords) !== JSON.stringify(artifactIndex.file_records ?? [])) {
      errors.push("evaluation artifact file records or hashes have drifted");
    }
    const filesSha256 = sha256Buffer(canonicalJson(currentArtifactRecords));
    if (
      artifactIndex.files_sha256 !== filesSha256 ||
      metrics.evaluation_artifacts?.files_sha256 !== filesSha256
    ) {
      errors.push("evaluation artifact aggregate hash has drifted");
    }
    const predictionRecords = artifactIndex.prediction_records ?? [];
    if (predictionRecords.length !== releaseReport.counts?.images) {
      errors.push("evaluation prediction records do not cover every frozen test image");
    }
    if (artifactIndex.prediction_records_sha256 !== sha256Buffer(canonicalJson(predictionRecords))) {
      errors.push("evaluation prediction record aggregate hash has drifted");
    }
    const artifactHashByPath = new Map(currentArtifactRecords.map((item) => [item.path, item.sha256]));
    const predictionStems = new Set<string>();
    const predictionPaths = new Set<string>();
    for (const record of predictionRecords) {
      if (!record.stem || !Number.isInteger(record.prediction_count) || (record.prediction_count ?? -1) < 0) {
        errors.push("evaluation prediction record is malformed");
        break;
      }
      if (predictionStems.has(record.stem)) {
        errors.push("evaluation prediction records contain duplicate image stems");
        break;
      }
      predictionStems.add(record.stem);
      if (record.path !== null && (!record.path || !safeRelative(record.path))) {
        errors.push("evaluation prediction record contains an unsafe path");
        break;
      }
      if (record.path === null && (record.sha256 !== null || record.prediction_count !== 0)) {
        errors.push("zero-prediction record must explicitly use null path/hash and count zero");
        break;
      }
      if (record.path !== null) {
        if (predictionPaths.has(record.path)) {
          errors.push("evaluation prediction records reuse a prediction file");
          break;
        }
        predictionPaths.add(record.path);
        if (
          (record.prediction_count ?? 0) < 1 ||
          artifactHashByPath.get(record.path) !== record.sha256
        ) {
          errors.push("evaluation prediction record is not bound to its current artifact file");
          break;
        }
      }
    }

    const calibrationVerifier = await runDeepVerifier([
      "python",
      "model/training/calibrate-model-score-threshold.py",
      "--verify-report",
      absoluteCalibrationReport,
      "--expected-weights",
      absoluteWeights,
    ]);
    if (!calibrationVerifier.ok) {
      errors.push(`calibration deep verification failed: ${calibrationVerifier.error}`);
    }
    const calibrationReport = JSON.parse(
      await readFile(absoluteCalibrationReport, "utf8")
    ) as CalibrationReportLike;
    const evidence = manifest.scoreThresholdEvidence;
    const calibrationReportSha256 = await sha256File(absoluteCalibrationReport);
    if (!evidence) {
      errors.push("candidate manifest is missing scoreThresholdEvidence");
    } else {
      const expectedEvidence = {
        path: absoluteCalibrationReport,
        sha256: calibrationReportSha256,
        datasetYamlSha256: calibrationReport.inputs?.datasetYamlSha256,
        metricsSha256: calibrationReport.inputs?.metricsSha256,
        artifactIndexSha256: calibrationReport.inputs?.artifactIndexSha256,
        weightsSha256: calibrationReport.inputs?.weightsSha256,
        decision: calibrationReport.decision,
      };
      if (!samePath(evidence.path ?? "", expectedEvidence.path)) {
        errors.push("candidate manifest calibration report path does not match");
      }
      for (const key of ["sha256", "datasetYamlSha256", "metricsSha256", "artifactIndexSha256", "weightsSha256", "decision"] as const) {
        if (evidence[key] !== expectedEvidence[key]) {
          errors.push(`candidate manifest scoreThresholdEvidence.${key} does not match`);
        }
      }
    }
    if (
      calibrationReport.decision !== "calibrated_threshold_ready_for_candidate_manifest" ||
      calibrationReport.calibrationEligible !== true ||
      typeof calibrationReport.manifestScoreThreshold !== "number" ||
      manifest.scoreThreshold !== calibrationReport.manifestScoreThreshold
    ) {
      errors.push("candidate manifest scoreThreshold is not derived from an eligible calibration report");
    }
    if (calibrationReport.inputs?.weightsSha256 !== metrics.weights_sha256) {
      errors.push("calibration and frozen release-test metrics do not use the same weights");
    }

    Object.assign(candidateEvidence!, {
      calibrationReport: absoluteCalibrationReport,
      calibrationReportSha256,
      releaseTestReport: absoluteReleaseTestReport,
      releaseTestDataset: absoluteDataset,
      releaseTestDatasetFilesSha256: releaseReport.files_sha256,
      evaluationArtifactIndex: artifactIndexPath,
      evaluationArtifactIndexSha256: artifactIndexSha256,
      weights: absoluteWeights,
      weightsSha256: currentWeightsSha256,
    });
  } catch (error) {
    errors.push(`candidate evidence is unreadable or incomplete: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const summary = {
  ok: errors.length === 0,
  metricsPath: absoluteMetricsPath,
  manifestPath: absoluteManifestPath,
  thresholds: {
    minSegMap50,
    minBoxMap50,
    maxModelMb,
  },
  metrics: {
    split: metrics.split,
    imgsz: metrics.imgsz,
    box_map50: metrics.box_map50,
    box_map: metrics.box_map,
    seg_map50: metrics.seg_map50,
    seg_map: metrics.seg_map,
  },
  artifact: {
    version: artifact.version,
    modelPath: artifact.modelPath,
    inputSize: artifact.inputSize,
    modelExists: artifact.modelExists,
    modelSizeMb: artifact.modelSizeMb,
    labels: artifact.labels,
    backendPreferences: artifact.backendPreferences,
  },
  candidateMode,
  candidateEvidence,
  errors,
  warnings,
  nextSteps:
    errors.length === 0
      ? ["Release candidate passes current training and export verification gates."]
      : [
          "Fix the failing metric or export inconsistency, then rerun verify-training-release.ts.",
        ],
};

console.log(JSON.stringify(summary, null, 2));
if (errors.length > 0) {
  process.exitCode = 1;
}
