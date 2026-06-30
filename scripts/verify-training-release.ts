import path from "node:path";
import process from "node:process";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFile } from "node:fs/promises";

const execFileAsync = promisify(execFile);

interface MetricsLike {
  dataset_yaml: string;
  dataset_root: string;
  weights: string;
  output: string;
  split: "train" | "val" | "test";
  imgsz: number;
  device: string;
  dry_run: boolean;
  box_map50: number;
  box_map: number;
  seg_map50: number;
  seg_map: number;
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
    "Usage: node --experimental-strip-types scripts/verify-training-release.ts --metrics <metrics.json> --manifest <manifest.json> [--min-seg-map50 0.75] [--min-box-map50 0.85] [--max-model-mb 15]"
  );
}

const args = process.argv.slice(2);
let metricsPath = "model/exports/nail-texture-seg-v1/metrics.json";
let manifestPath = "public/models/nail-texture-seg/manifest.json";
let minSegMap50 = 0.75;
let minBoxMap50 = 0.85;
let maxModelMb = 15;

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
  usage();
}

const absoluteMetricsPath = path.resolve(metricsPath);
const absoluteManifestPath = path.resolve(manifestPath);
const metrics = JSON.parse(
  await readFile(absoluteMetricsPath, "utf8")
) as MetricsLike;

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

if (metrics.split !== "test") {
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
