import path from "node:path";
import process from "node:process";
import { readFile, stat } from "node:fs/promises";

interface EvaluationArtifactIndex {
  schema_version?: number;
  split?: string;
  artifacts_dir?: string;
  files?: string[];
  counts?: {
    total?: number;
    plots?: number;
    prediction_labels?: number;
    json?: number;
  };
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-evaluation-artifacts.ts --index <evaluation-artifacts.json> [--require-split test]"
  );
}

function parseArgs(argv: string[]) {
  let indexPath = "";
  let requiredSplit = "test";
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--index") indexPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--require-split") requiredSplit = argv[++index] ?? usage();
    else usage();
  }
  if (!indexPath) usage();
  return { indexPath, requiredSplit };
}

const options = parseArgs(process.argv.slice(2));
const artifactIndex = JSON.parse(
  await readFile(options.indexPath, "utf8")
) as EvaluationArtifactIndex;
const files = Array.isArray(artifactIndex.files) ? artifactIndex.files : [];
const normalizedFiles = files.map((file) => file.replaceAll("\\", "/"));
const errors: string[] = [];
const warnings: string[] = [];
const indexDir = path.dirname(options.indexPath);
const declaredArtifactsDir = artifactIndex.artifacts_dir
  ? path.resolve(artifactIndex.artifacts_dir)
  : null;
const unsafePaths: string[] = [];
const duplicatePaths = normalizedFiles.filter(
  (file, index) => normalizedFiles.indexOf(file) !== index
);
const missingOrEmptyFiles: string[] = [];
const existingFiles: string[] = [];

if (declaredArtifactsDir && declaredArtifactsDir !== indexDir) {
  errors.push("artifacts_dir must match the directory containing the artifact index");
}
for (const file of normalizedFiles) {
  const resolvedFile = path.resolve(indexDir, file);
  const relativeToIndex = path.relative(indexDir, resolvedFile);
  if (
    path.isAbsolute(file) ||
    relativeToIndex.startsWith("..") ||
    path.isAbsolute(relativeToIndex)
  ) {
    unsafePaths.push(file);
    continue;
  }
  try {
    const fileStat = await stat(resolvedFile);
    if (!fileStat.isFile() || fileStat.size <= 0) {
      missingOrEmptyFiles.push(file);
    } else {
      existingFiles.push(file);
    }
  } catch {
    missingOrEmptyFiles.push(file);
  }
}

if (unsafePaths.length > 0) {
  errors.push(`artifact index contains unsafe paths: ${unsafePaths.join(", ")}`);
}
if (duplicatePaths.length > 0) {
  errors.push(
    `artifact index contains duplicate paths: ${[...new Set(duplicatePaths)].join(", ")}`
  );
}
if (missingOrEmptyFiles.length > 0) {
  errors.push(
    `artifact files are missing, empty, or not regular files: ${missingOrEmptyFiles.join(", ")}`
  );
}
if (artifactIndex.schema_version !== 1) {
  errors.push("artifact index schema_version must be 1");
}
if (artifactIndex.split !== options.requiredSplit) {
  errors.push(
    `evaluation split must be ${options.requiredSplit}, got ${artifactIndex.split ?? "missing"}`
  );
}

const computedCounts = {
  total: normalizedFiles.length,
  plots: normalizedFiles.filter((file) => /\.(?:png|jpe?g)$/i.test(file)).length,
  prediction_labels: normalizedFiles.filter(
    (file) => file.startsWith("labels/") && file.endsWith(".txt")
  ).length,
  json: normalizedFiles.filter((file) => file.toLowerCase().endsWith(".json")).length,
};
for (const key of Object.keys(computedCounts) as Array<keyof typeof computedCounts>) {
  if (artifactIndex.counts?.[key] !== computedCounts[key]) {
    errors.push(
      `artifact count ${key} must be ${computedCounts[key]}, got ${artifactIndex.counts?.[key] ?? "missing"}`
    );
  }
}

if (
  !existingFiles.some((file) =>
    /(^|\/)confusion_matrix(?:_normalized)?\.png$/i.test(file)
  )
) {
  errors.push("confusion matrix plot is missing");
}
if (
  !existingFiles.some((file) =>
    /(^|\/)(?:val|test)_batch\d+_pred\.(?:png|jpe?g)$/i.test(file)
  )
) {
  errors.push("prediction-versus-ground-truth visualization is missing");
}
if (!existingFiles.some((file) => /(^|\/)PR_curve\.png$/i.test(file))) {
  warnings.push("PR curve plot is missing");
}
if (
  !existingFiles.some(
    (file) => file.startsWith("labels/") && file.endsWith(".txt")
  )
) {
  warnings.push(
    "per-image prediction labels are empty; verify this is expected for a negative-only split"
  );
}

const summary = {
  ok: errors.length === 0,
  indexPath: options.indexPath,
  split: artifactIndex.split ?? null,
  artifactsDir: artifactIndex.artifacts_dir ?? null,
  counts: artifactIndex.counts ?? null,
  evidence: {
    verifiedFileCount: existingFiles.length,
    confusionMatrices: existingFiles.filter((file) =>
      /(^|\/)confusion_matrix(?:_normalized)?\.png$/i.test(file)
    ),
    predictionVisualizations: existingFiles.filter((file) =>
      /(^|\/)(?:val|test)_batch\d+_pred\.(?:png|jpe?g)$/i.test(file)
    ),
    prCurves: existingFiles.filter((file) => /(^|\/)PR_curve\.png$/i.test(file)),
    predictionLabelCount: existingFiles.filter(
      (file) => file.startsWith("labels/") && file.endsWith(".txt")
    ).length,
  },
  integrity: {
    declaredFileCount: normalizedFiles.length,
    computedCounts,
    unsafePaths,
    duplicatePaths: [...new Set(duplicatePaths)],
    missingOrEmptyFiles: [...new Set(missingOrEmptyFiles)],
  },
  errors,
  warnings,
  nextSteps:
    errors.length > 0
      ? ["Rerun evaluate.py with plots enabled and inspect the validation output directory."]
      : ["Review confusion matrices and prediction visualizations before release approval."],
};

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) process.exitCode = 1;