import { createHash } from "node:crypto";
import { access, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

interface CliOptions {
  datasetRoot: string;
  manifestPath: string;
  packageJsonPath: string;
  outputPath?: string;
  deferRealAssets: boolean;
}

interface CheckResult {
  name: string;
  ok: boolean;
  summary: string;
  evidence: Record<string, unknown>;
  nextSteps: string[];
  commands: string[];
  deferred?: boolean;
}

interface Phase1ReadinessReport {
  ok?: boolean;
  totals?: {
    images?: number;
    validMasks?: number;
  };
  splitCounts?: {
    train?: number;
    val?: number;
    test?: number;
  };
  gates?: {
    imageCount?: { ok?: boolean; actual?: number; required?: number };
    validMaskCount?: { ok?: boolean; actual?: number; required?: number };
    labelAuditPass?: { ok?: boolean };
    testSplitHasNegative?: { ok?: boolean; actual?: number; required?: number };
    testSplitHasComplexBackground?: { ok?: boolean; actual?: number; required?: number };
  };
}

interface TrainingDatasetReadinessReport {
  ok?: boolean;
  authorizationMode?: string;
  artifactPaths?: {
    sourceAuthorization?: string;
    phase1Readiness?: string;
  };
  artifacts?: {
    sourceAuthorization?: {
      ok?: boolean;
      mode?: string;
      recordCount?: number;
      issues?: Array<{ severity?: string; code?: string }>;
    } | null;
    phase1Readiness?: Phase1ReadinessReport | null;
  };
  steps?: Array<{ name?: string; ok?: boolean }>;
}
interface ModelManifest {
  version?: string;
  inputSize?: number;
  task?: string;
  modelFile?: string;
  backendPreferences?: string[];
  labels?: string[];
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-nail-texture-mvp-readiness.ts [--dataset-root <dir>] [--manifest <manifest.json>] [--package-json <package.json>] [--output <report.json>] [--defer-real-assets]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  let datasetRoot = path.resolve("model/datasets/nail-texture-v1");
  let manifestPath = path.resolve("public/models/nail-texture-seg/manifest.json");
  let packageJsonPath = path.resolve("package.json");
  let outputPath: string | undefined;
  let deferRealAssets = false;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--dataset-root") datasetRoot = path.resolve(argv[++index] ?? usage());
    else if (arg === "--manifest") manifestPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--package-json") packageJsonPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") outputPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--defer-real-assets") deferRealAssets = true;
    else usage();
  }

  return { datasetRoot, manifestPath, packageJsonPath, outputPath, deferRealAssets };
}

function quoteCommandPath(filePath: string): string {
  return `"${filePath.replaceAll("\\", "/")}"`;
}
async function readJsonIfExists<T>(filePath: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as T;
  } catch {
    return null;
  }
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
}

async function hashFileSha256(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function checkPhase1Dataset(datasetRoot: string): Promise<CheckResult> {
  const readinessPath = path.join(datasetRoot, "metadata", "phase1-readiness.json");
  const readiness = await readJsonIfExists<Phase1ReadinessReport>(readinessPath);
  const gates = readiness?.gates;
  const ok =
    gates?.imageCount?.ok === true &&
    gates.validMaskCount?.ok === true &&
    gates.labelAuditPass?.ok === true &&
    gates.testSplitHasNegative?.ok === true &&
    gates.testSplitHasComplexBackground?.ok === true &&
    (readiness?.splitCounts?.test ?? 0) > 0;

  return {
    name: "phase1_dataset",
    ok,
    summary: ok
      ? "Phase 1 dataset readiness evidence satisfies the MVP dataset gate."
      : "Phase 1 dataset is not yet proven ready for MVP training.",
    evidence: {
      readinessPath,
      reportFound: readiness !== null,
      totals: readiness?.totals ?? null,
      splitCounts: readiness?.splitCounts ?? null,
      gates: gates ?? null,
    },
    nextSteps: ok
      ? []
      : [
          "Import/review enough authorized images to reach at least 200 images and 800 valid nail masks.",
          "Regenerate split.json and rerun audit-phase1-readiness until negative and complex-background test coverage pass.",
        ],
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts",
          "node --no-warnings --experimental-strip-types model/training/plan-phase1-collection.ts",
          `node --no-warnings --experimental-strip-types model/training/generate-first-batch-checklist.ts --dataset-root ${quoteCommandPath(datasetRoot)}`,
        ],
  };
}

async function checkTrainingSourceAuthorization(datasetRoot: string): Promise<CheckResult> {
  const readinessPath = path.join(datasetRoot, "metadata", "training-dataset-readiness-release.json");
  const readiness = await readJsonIfExists<TrainingDatasetReadinessReport>(readinessPath);
  const sourceAuthorization = readiness?.artifacts?.sourceAuthorization ?? null;
  const errorIssues =
    sourceAuthorization?.issues?.filter((issue) => issue.severity === "error") ?? [];
  const ok =
    readiness?.ok === true &&
    readiness.authorizationMode === "release" &&
    sourceAuthorization?.ok === true &&
    sourceAuthorization.mode === "release" &&
    errorIssues.length === 0;

  return {
    name: "training_source_authorization",
    ok,
    summary: ok
      ? "Release-mode source authorization evidence proves the dataset can be used for training."
      : "Release-mode source authorization evidence is missing or not passing.",
    evidence: {
      readinessPath,
      reportFound: readiness !== null,
      authorizationMode: readiness?.authorizationMode ?? null,
      artifactPaths: readiness?.artifactPaths ?? null,
      sourceAuthorization: sourceAuthorization
        ? {
            ok: sourceAuthorization.ok ?? null,
            mode: sourceAuthorization.mode ?? null,
            recordCount: sourceAuthorization.recordCount ?? null,
            errorIssueCount: errorIssues.length,
          }
        : null,
      steps: readiness?.steps ?? null,
    },
    nextSteps: ok
      ? []
      : [
          "Run model/training/verify-training-dataset-readiness.ts in release mode after sources.csv is populated.",
          "Fix source authorization errors before using the dataset for release training.",
        ],
    commands: ok
      ? []
      : [
          `node --no-warnings --experimental-strip-types model/training/verify-training-dataset-readiness.ts --dataset-root ${quoteCommandPath(datasetRoot)} --authorization-mode release`,
        ],
  };
}

async function checkTrainingToolchain(): Promise<CheckResult> {
  const requiredFiles = [
    "model/training/dataset.yaml",
    "model/training/train-yolo-seg.py",
    "model/training/evaluate.py",
    "model/training/export-onnx.py",
    "model/training/convert-annotations.ts",
    "model/training/audit-labels.ts",
    "scripts/run-training-release-pipeline.ts",
    "scripts/verify-training-release.ts",
  ];
  const fileResults = await Promise.all(
    requiredFiles.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
    }))
  );
  const missing = fileResults.filter((result) => !result.exists).map((result) => result.filePath);
  const ok = missing.length === 0;

  return {
    name: "training_toolchain",
    ok,
    summary: ok
      ? "Reproducible training, evaluation, export, conversion, audit, and release scripts are present."
      : "The reproducible training/export toolchain is incomplete.",
    evidence: { files: fileResults },
    nextSteps: missing.map((filePath) => `Add or restore ${filePath}.`),
    commands: [],
  };
}

async function checkBaselineFixtureToolchain(): Promise<CheckResult> {
  const requiredFiles = [
    "src/lib/nail-detection-fixture.ts",
    "model/fixtures/nail-detection-reference-5188.json",
    "scripts/build-nail-detection-fixture.ts",
    "scripts/verify-nail-detection.ts",
    "scripts/batch-verify-nail-detection.ts",
    "model/training/export-fallback-annotations.ts",
    "docs/fallback-batch-overlay-workflow.md",
    "docs/reference-image-nail-extraction-plan.md",
  ];
  const fileResults = await Promise.all(
    requiredFiles.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
    }))
  );
  const missing = fileResults.filter((result) => !result.exists).map((result) => result.filePath);
  const ok = missing.length === 0;

  return {
    name: "baseline_fixture_toolchain",
    ok,
    summary: ok
      ? "Reusable green-circle fixture, fallback overlay batch verification, and fallback annotation export tools are present."
      : "Baseline green-circle fixture or fallback overlay verification toolchain files are missing.",
    evidence: {
      files: fileResults,
      requiredFileCount: requiredFiles.length,
      missing,
    },
    nextSteps: missing.map((filePath) => `Add or restore ${filePath}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types scripts/build-nail-detection-fixture.ts --help",
          "node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --help",
          "node --no-warnings --experimental-strip-types model/training/export-fallback-annotations.ts --help",
        ],
  };
}
async function checkBrowserModel(manifestPath: string): Promise<CheckResult> {
  const manifest = await readJsonIfExists<ModelManifest>(manifestPath);
  const modelPath = manifest?.modelFile ? path.resolve(path.dirname(manifestPath), manifest.modelFile) : null;
  const modelExists = modelPath ? await exists(modelPath) : false;
  const modelSizeBytes = modelExists && modelPath ? (await stat(modelPath)).size : 0;
  const computedSha256 = modelExists && modelPath && isSha256(manifest?.sha256)
    ? await hashFileSha256(modelPath)
    : null;
  const minModelBytes = 256 * 1024;
  const idealModelBytes = 8 * 1024 * 1024;
  const maxModelBytes = 15 * 1024 * 1024;
  const sizeTier =
    !modelExists || modelSizeBytes === 0
      ? "missing"
      : modelSizeBytes < minModelBytes
        ? "placeholder"
        : modelSizeBytes <= idealModelBytes
          ? "ideal"
          : modelSizeBytes <= maxModelBytes
            ? "mvp"
            : "too_large";
  const manifestOk =
    manifest?.task === "segment" &&
    manifest.inputSize === 640 &&
    manifest.labels?.[0] === "nail_texture" &&
    Array.isArray(manifest.backendPreferences) &&
    manifest.backendPreferences.includes("wasm") &&
    typeof manifest.modelFile === "string" &&
    path.basename(manifest.modelFile) === manifest.modelFile &&
    path.extname(manifest.modelFile).toLowerCase() === ".onnx";
  const integrityOk =
    modelExists &&
    isSha256(manifest?.sha256) &&
    computedSha256?.toLowerCase() === manifest.sha256.toLowerCase() &&
    manifest.modelSizeBytes === modelSizeBytes;
  const artifactSizeOk = modelExists && modelSizeBytes >= minModelBytes && modelSizeBytes <= maxModelBytes;
  const ok = manifestOk && artifactSizeOk && integrityOk;

  return {
    name: "browser_model_asset",
    ok,
    summary: ok
      ? "A browser model manifest and credible ONNX asset satisfy the MVP browser model gate."
      : "The browser-loadable model asset is missing, unsafe, placeholder-sized, or above the MVP size limit.",
    evidence: {
      manifestPath,
      manifestFound: manifest !== null,
      manifest,
      manifestOk,
      modelPath,
      modelExists,
      modelSizeBytes,
      modelSizeMb: Number((modelSizeBytes / (1024 * 1024)).toFixed(4)),
      sizeTier,
      minModelKb: 256,
      idealModelMb: 8,
      maxModelMb: 15,
      artifactSizeOk,
    },
    nextSteps: ok
      ? sizeTier === "mvp"
        ? ["Model asset passes the required MVP size gate; consider optimizing below the ideal 8MB target if startup latency is high."]
        : []
      : [
          "Train/export a real ONNX segmentation model and place it at the path referenced by public/models/nail-texture-seg/manifest.json.",
          "Reject placeholder ONNX files below 256KB and release artifacts above 15MB; keep the ideal target below 8MB.",
          "Require manifest.sha256 and manifest.modelSizeBytes to match the exported ONNX file.",
          "Rerun verify-model-artifact and browser integration checks after the model file exists.",
        ],
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types scripts/run-training-release-pipeline.ts",
          `node --no-warnings --experimental-strip-types scripts/verify-model-artifact.ts ${quoteCommandPath(manifestPath)}`,
          `node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --manifest ${quoteCommandPath(manifestPath)}`,
        ],
  };
}

async function checkFeedbackLoopToolchain(): Promise<CheckResult> {
  const requiredFiles = [
    "src/lib/nail-texture-debug-sample.ts",
    "src/lib/nail-texture-debug-priority.ts",
    "src/lib/nail-texture-recognition/debug.ts",
    "src/lib/nail-texture-recognition/debug-artifacts.ts",
    "src/lib/nail-texture-recognition/debug-compare.ts",
    "model/training/import-debug-sample.ts",
    "model/training/prioritize-debug-samples.ts",
    "model/training/run-debug-sample-active-learning-pipeline.ts",
    "scripts/build-active-learning-release-trace-draft.ts",
    "scripts/build-debug-sample-active-learning-handoff.ts",
    "model/training/scaffold-seed-batch.ts",
    "model/training/bootstrap-seed-batch.ts",
    "model/training/build-reviewed-intake-batch.ts",
    "model/training/prepare-reviewed-annotations.ts",
    "model/training/import-reviewed-batch.ts",
    "model/training/run-reviewed-batch-import-pipeline.ts",
    "scripts/build-reviewed-batch-release-handoff.ts",
    "docs/debug-sample-active-learning-pipeline.md",
    "docs/debug-sample-prioritization.md",
    "docs/active-learning-trace-handoff.md",
    "docs/reviewed-batch-release-handoff.md",
    "docs/run-reviewed-batch-import-pipeline.md",
  ];
  const fileResults = await Promise.all(
    requiredFiles.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
    }))
  );
  const missing = fileResults.filter((result) => !result.exists).map((result) => result.filePath);
  const ok = missing.length === 0;

  return {
    name: "feedback_loop_toolchain",
    ok,
    summary: ok
      ? "User correction, debug-sample import, active-learning prioritization, reviewed-batch handoff, and dataset feedback-loop tools are present."
      : "User correction or active-learning feedback-loop toolchain files are missing.",
    evidence: {
      files: fileResults,
      requiredFileCount: requiredFiles.length,
      missing,
    },
    nextSteps: missing.map((filePath) => `Add or restore ${filePath}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types model/training/prioritize-debug-samples.ts --help",
          "node --no-warnings --experimental-strip-types model/training/run-debug-sample-active-learning-pipeline.ts --help",
          "node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --help",
        ],
  };
}
async function checkQualityPerformanceGates(): Promise<CheckResult> {
  const requiredFiles = [
    "scripts/verify-browser-integration.ts",
    "scripts/verify-recognition-performance.ts",
    "scripts/verify-texture-quality-gate.ts",
    "scripts/verify-real-model-readiness.ts",
    "scripts/verify-model-output-fixture.ts",
    "docs/browser-integration-verification.md",
    "docs/recognition-performance-gate.md",
    "docs/texture-quality-gate.md",
    "docs/transparent-mask-texture-verification.md",
  ];
  const fileResults = await Promise.all(
    requiredFiles.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
    }))
  );
  const missing = fileResults.filter((result) => !result.exists).map((result) => result.filePath);
  const ok = missing.length === 0;

  return {
    name: "quality_performance_gates",
    ok,
    summary: ok
      ? "Phase 3/4 browser integration, recognition performance, texture quality, and real-model readiness gates are present."
      : "Phase 3/4 quality or performance validation gate files are missing.",
    evidence: {
      files: fileResults,
      requiredFileCount: requiredFiles.length,
      missing,
    },
    nextSteps: missing.map((filePath) => `Add or restore ${filePath}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts --skip-model-artifact",
          "node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts --profile desktop --min-samples 1",
          "node --no-warnings --experimental-strip-types scripts/verify-texture-quality-gate.ts --annotation-dir model/datasets/nail-texture-v1/annotations/raw-json",
        ],
  };
}
async function checkReleaseGovernanceToolchain(): Promise<CheckResult> {
  const requiredFiles = [
    "scripts/compare-training-releases.ts",
    "scripts/build-release-decision-report.ts",
    "scripts/run-release-governance-pipeline.ts",
    "scripts/promote-approved-release.ts",
    "scripts/audit-release-rollback.ts",
    "scripts/build-release-trace-index.ts",
    "scripts/register-release-trace-index.ts",
    "scripts/build-release-history-manifest.ts",
    "scripts/register-model-release.ts",
    "scripts/switch-model-release.ts",
    "scripts/audit-failure-classification.ts",
    "scripts/summarize-failure-cases.ts",
    "docs/training-release-comparison.md",
    "docs/release-decision-report.md",
    "docs/release-governance-pipeline.md",
    "docs/model-release-registry.md",
    "docs/failure-classification-audit.md",
    "docs/failure-case-summary.md",
  ];
  const fileResults = await Promise.all(
    requiredFiles.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
    }))
  );
  const missing = fileResults.filter((result) => !result.exists).map((result) => result.filePath);
  const ok = missing.length === 0;

  return {
    name: "release_governance_toolchain",
    ok,
    summary: ok
      ? "Phase 5 release governance, rollback, trace/history, A/B comparison, and failure-taxonomy tools are present."
      : "Phase 5 release governance or failure-taxonomy toolchain files are missing.",
    evidence: {
      files: fileResults,
      requiredFileCount: requiredFiles.length,
      missing,
    },
    nextSteps: missing.map((filePath) => `Add or restore ${filePath}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types scripts/compare-training-releases.ts --help",
          "node --no-warnings --experimental-strip-types scripts/run-release-governance-pipeline.ts --help",
        ],
  };
}
async function checkBrowserIntegration(): Promise<CheckResult> {
  const files = [
    "src/lib/nail-texture-recognition/model-runtime.ts",
    "src/lib/nail-texture-recognition/client-worker.ts",
    "src/workers/nail-texture-recognition.worker.ts",
    "src/lib/nail-texture-recognition/fallback-adapter.ts",
    "src/components/NailArtPicker.tsx",
  ];
  const contents = await Promise.all(
    files.map(async (filePath) => ({
      filePath,
      exists: await exists(path.resolve(filePath)),
      text: await readFile(path.resolve(filePath), "utf8").catch(() => ""),
    }))
  );
  const markers = {
    modelRuntime: contents.some((item) => item.filePath.endsWith("model-runtime.ts") && item.text.includes("onnxruntime")),
    workerClient: contents.some((item) => item.filePath.endsWith("client-worker.ts") && item.text.includes("Worker")),
    workerEntrypoint: contents.some((item) => item.filePath.endsWith(".worker.ts") && item.text.includes("recognizeNailTextures")),
    fallbackAdapter: contents.some((item) => item.filePath.endsWith("fallback-adapter.ts") && item.text.includes("detectNailRegionsFromImageData")),
    pickerUsesRecognition: contents.some((item) => item.filePath.endsWith("NailArtPicker.tsx") && item.text.includes("recognizeNailTextures")),
  };
  const ok = Object.values(markers).every(Boolean);

  return {
    name: "browser_integration",
    ok,
    summary: ok
      ? "NailArtPicker is wired to the unified recognition service with worker/runtime/fallback code present."
      : "Browser integration markers are incomplete.",
    evidence: {
      files: contents.map(({ filePath, exists }) => ({ filePath, exists })),
      markers,
    },
    nextSteps: ok
      ? []
      : ["Complete the model runtime, worker, fallback adapter, and NailArtPicker recognition wiring."],
    commands: ok
      ? []
      : ["node --no-warnings --experimental-strip-types scripts/verify-browser-integration.ts"],
  };
}

async function checkReleaseHistoryEvidenceLedger(): Promise<CheckResult> {
  const markerFiles = [
    {
      filePath: "scripts/build-release-history-manifest.ts",
      markers: [
        "performanceTraceIndexes",
        "qualityTraceIndexes",
        "failureSummary",
        "activeLearningImportedSamples",
        "recognitionMaskEvidenceTraceIndexes",
      ],
    },
    {
      filePath: "tests/build-release-history-manifest.test.ts",
      markers: [
        "visualEvidenceTraceIndexes",
        "failureTraceIndexes",
        "failureCategoryTotal",
        "activeLearningImportedSamples",
        "recognitionMaskEvidenceTraceIndexes",
      ],
    },
    {
      filePath: "docs/release-governance-pipeline.md",
      markers: [
        "release-history performance summary",
        "release-history quality summary",
        "release-history failure summary",
        "First-run visual evidence in release history",
      ],
    },
  ];
  const fileResults = await Promise.all(
    markerFiles.map(async ({ filePath, markers }) => {
      const absolutePath = path.resolve(filePath);
      const text = await readFile(absolutePath, "utf8").catch(() => "");
      return {
        filePath,
        exists: await exists(absolutePath),
        markers: markers.map((marker) => ({ marker, found: text.includes(marker) })),
      };
    })
  );
  const missing = fileResults.flatMap((result) =>
    result.markers
      .filter((marker) => !marker.found)
      .map((marker) => `${result.filePath}: ${marker.marker}`)
  );
  const ok = fileResults.every((result) => result.exists) && missing.length === 0;

  return {
    name: "release_history_evidence_ledger",
    ok,
    summary: ok
      ? "Release history preserves performance, quality, failure, active-learning, and visual-evidence summaries across versions."
      : "Release history evidence ledger coverage is incomplete.",
    evidence: {
      files: fileResults,
      requiredMarkerCount: markerFiles.reduce((total, item) => total + item.markers.length, 0),
      missing,
    },
    nextSteps: missing.map((item) => `Restore release history evidence ledger marker: ${item}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types --test tests/build-release-history-manifest.test.ts",
        ],
  };
}

async function checkReleaseVisualEvidenceGovernance(): Promise<CheckResult> {
  const markerFiles = [
    {
      filePath: "scripts/compare-training-releases.ts",
      markers: ["buildVisualEvidenceSnapshot", "recognitionMaskEvidence"],
    },
    {
      filePath: "scripts/build-release-decision-report.ts",
      markers: ["candidate visual evidence decreased", "recognitionMaskEvidenceDelta"],
    },
    {
      filePath: "tests/run-release-governance-pipeline.test.ts",
      markers: [
        "keeps visual evidence reviews out of automatic promotion",
        "can promote visual evidence reviews when explicitly allowed",
      ],
    },
    {
      filePath: "tests/run-training-release-pipeline.test.ts",
      markers: ["can promote visual evidence manual reviews when explicitly allowed"],
    },
    {
      filePath: "docs/release-governance-pipeline.md",
      markers: ["Visual evidence manual_review", "Visual evidence manual_review acceptance"],
    },
    {
      filePath: "docs/training-release-pipeline.md",
      markers: ["Visual evidence manual review pass-through"],
    },
  ];
  const fileResults = await Promise.all(
    markerFiles.map(async ({ filePath, markers }) => {
      const absolutePath = path.resolve(filePath);
      const text = await readFile(absolutePath, "utf8").catch(() => "");
      return {
        filePath,
        exists: await exists(absolutePath),
        markers: markers.map((marker) => ({ marker, found: text.includes(marker) })),
      };
    })
  );
  const missing = fileResults.flatMap((result) =>
    result.markers
      .filter((marker) => !marker.found)
      .map((marker) => `${result.filePath}: ${marker.marker}`)
  );
  const ok = fileResults.every((result) => result.exists) && missing.length === 0;

  return {
    name: "release_visual_evidence_governance",
    ok,
    summary: ok
      ? "Release governance preserves first-run visual evidence risk from A/B comparison through manual-review promotion paths."
      : "Release governance visual-evidence manual-review coverage is incomplete.",
    evidence: {
      files: fileResults,
      requiredMarkerCount: markerFiles.reduce((total, item) => total + item.markers.length, 0),
      missing,
    },
    nextSteps: missing.map((item) => `Restore release visual-evidence governance marker: ${item}.`),
    commands: ok
      ? []
      : [
          "node --no-warnings --experimental-strip-types --test tests/run-release-governance-pipeline.test.ts tests/run-training-release-pipeline.test.ts",
        ],
  };
}
async function checkPackageValidation(packageJsonPath: string): Promise<CheckResult> {
  const pkg = await readJsonIfExists<{
    scripts?: Record<string, string>;
    dependencies?: Record<string, string>;
    devDependencies?: Record<string, string>;
  }>(packageJsonPath);
  const requiredScripts = [
    "test",
    "lint",
    "build",
    "audit:encoding",
    "audit:mvp-readiness",
    "audit:mvp-readiness:deferred",
    "audit:mvp-readiness:refresh",
  ];
  const missingScripts = requiredScripts.filter((scriptName) => !pkg?.scripts?.[scriptName]);
  const onnxRuntimeWebVersion =
    pkg?.dependencies?.["onnxruntime-web"] ?? pkg?.devDependencies?.["onnxruntime-web"] ?? null;
  const ok = missingScripts.length === 0 && Boolean(onnxRuntimeWebVersion);

  return {
    name: "validation_commands",
    ok,
    summary: ok
      ? "Required validation commands and browser runtime dependency are defined in package.json."
      : "Required validation commands or browser runtime dependency are missing from package.json.",
    evidence: {
      packageJsonPath,
      scripts: pkg?.scripts ?? null,
      requiredScripts,
      missingScripts,
      onnxRuntimeWebVersion,
    },
    nextSteps: [
      ...missingScripts.map((scriptName) => `Add package.json script: ${scriptName}.`),
      ...(!onnxRuntimeWebVersion ? ["Add onnxruntime-web to package.json dependencies."] : []),
    ],
    commands: ok
      ? []
      : ["npm.cmd install onnxruntime-web", "npm.cmd test", "npm.cmd run lint", "npm.cmd run build"],
  };
}

const DEFERRABLE_REAL_ASSET_CHECKS = new Set([
  "phase1_dataset",
  "training_source_authorization",
  "browser_model_asset",
]);

function applyRealAssetDeferral(checks: CheckResult[], enabled: boolean): CheckResult[] {
  if (!enabled) return checks;

  return checks.map((check) => {
    if (check.ok || !DEFERRABLE_REAL_ASSET_CHECKS.has(check.name)) return check;

    return {
      ...check,
      ok: true,
      deferred: true,
      summary: `${check.summary} Deferred by --defer-real-assets because real training data/model assets are intentionally out of scope for this validation run.`,
      evidence: {
        ...check.evidence,
        deferredBy: "--defer-real-assets",
        originalOk: false,
      },
      nextSteps: [],
      commands: [],
    };
  });
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const rawChecks = [
    await checkPhase1Dataset(options.datasetRoot),
    await checkTrainingSourceAuthorization(options.datasetRoot),
    await checkTrainingToolchain(),
    await checkBaselineFixtureToolchain(),
    await checkBrowserModel(options.manifestPath),
    await checkBrowserIntegration(),
    await checkFeedbackLoopToolchain(),
    await checkQualityPerformanceGates(),
    await checkReleaseGovernanceToolchain(),
    await checkReleaseHistoryEvidenceLedger(),
    await checkReleaseVisualEvidenceGovernance(),
    await checkPackageValidation(options.packageJsonPath),
  ];
  const checks = applyRealAssetDeferral(rawChecks, options.deferRealAssets);
  const ok = checks.every((check) => check.ok);
  const report = {
    ok,
    generatedAt: new Date().toISOString(),
    planPath: path.resolve("docs/nail-texture-recognition-model-plan.md"),
    inputs: options,
    summary: {
      total: checks.length,
      passed: checks.filter((check) => check.ok).length,
      failed: checks.filter((check) => !check.ok).length,
      deferred: checks.filter((check) => check.deferred).length,
    },
    checks,
    nextSteps: checks.flatMap((check) => check.nextSteps),
    nextCommands: [...new Set(checks.flatMap((check) => check.commands))],
  };

  if (options.outputPath) {
    await mkdir(path.dirname(options.outputPath), { recursive: true });
    await writeFile(options.outputPath, JSON.stringify(report, null, 2), "utf8");
  }

  console.log(JSON.stringify(report, null, 2));
  if (!ok) process.exitCode = 1;
}

await main();
