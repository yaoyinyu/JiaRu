import { createHash } from "node:crypto";
import { access, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";

interface Options {
  specPath: string;
  progressPath: string;
  datasetReadinessPath: string;
  candidateReviewPath: string;
  bestMetricsPath: string;
  productionManifestPath: string;
  desktopPerformancePath: string;
  desktopMemoryPath: string;
  betaReviewPath: string;
  failureCasesPath: string;
  mobileReports: Array<{ device: string; filePath: string }>;
  outputPath?: string;
}

interface ChecklistItem {
  checked: boolean;
  text: string;
}

interface DatasetReadiness {
  ok?: boolean;
  authorizationMode?: string;
  artifacts?: {
    sourceAuthorization?: { recordCount?: number };
    phase1Readiness?: { totals?: { images?: number; validMasks?: number }; splitCounts?: Record<string, number> };
  };
  steps?: Array<{ name?: string; ok?: boolean }>;
}

interface CandidateReview { dataset?: { testImages?: number } }
interface MetricsReport { box_map50?: number; seg_map50?: number }
interface PerformanceReport { ok?: boolean; totals?: { samples?: number } }
interface MemoryReport { ok?: boolean; sampleCount?: number }
interface BetaReview { version?: string; ok?: boolean; reviewedByUser?: boolean; sampleCount?: number; directlyUsableRate?: number }
interface FailureCases { version?: string; ok?: boolean; sampleCount?: number }
interface DeviceReport {
  version?: string;
  deviceFamily?: string;
  ok?: boolean;
  decision?: string;
  performance?: { ok?: boolean; sampleCount?: number };
  memory?: { ok?: boolean };
}
interface ProductionManifest { modelFile?: string; sha256?: string; modelSizeBytes?: number; [key: string]: unknown }

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-nail-texture-local-inference-completion.ts " +
      "[--spec <md>] [--progress <md>] [--dataset-readiness <json>] [--candidate-review <json>] " +
      "[--best-metrics <json>] [--production-manifest <json>] [--desktop-performance <json>] " +
      "[--desktop-memory <json>] [--mobile-report <device=json>] [--beta-review <json>] " +
      "[--failure-cases <json>] [--output <json>]"
  );
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    specPath: path.resolve("docs/nail-texture-local-inference-implementation-spec.md"),
    progressPath: path.resolve("docs/nail-texture-local-inference-implementation-progress.md"),
    datasetReadinessPath: path.resolve("model/datasets/nail-texture-v1/metadata/training-dataset-readiness-release.json"),
    candidateReviewPath: path.resolve("model/reports/nail-texture-seg-real-candidate-v9-review.json"),
    bestMetricsPath: path.resolve("model/exports/nail-texture-seg-real-candidate-v6/test-metrics.512.json"),
    productionManifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    desktopPerformancePath: path.resolve("model/exports/nail-texture-seg-real-candidate-v6/browser-performance-report.json"),
    desktopMemoryPath: path.resolve("model/reports/nail-texture-seg-real-candidate-v6-desktop-memory.json"),
    betaReviewPath: path.resolve("model/reports/nail-texture-beta-quality-review.json"),
    failureCasesPath: path.resolve("model/reports/nail-texture-user-failure-cases.json"),
    mobileReports: [
      { device: "android", filePath: path.resolve("model/reports/nail-texture-device-android.json") },
      { device: "android-tablet", filePath: path.resolve("model/reports/nail-texture-device-android-tablet.json") },
      { device: "iphone", filePath: path.resolve("model/reports/nail-texture-device-iphone.json") },
      { device: "ipad", filePath: path.resolve("model/reports/nail-texture-device-ipad.json") },
    ],
  };
  let customMobileReports = false;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]!;
    const value = argv[++index];
    if (!value) usage();
    if (arg === "--spec") options.specPath = path.resolve(value);
    else if (arg === "--progress") options.progressPath = path.resolve(value);
    else if (arg === "--dataset-readiness") options.datasetReadinessPath = path.resolve(value);
    else if (arg === "--candidate-review") options.candidateReviewPath = path.resolve(value);
    else if (arg === "--best-metrics") options.bestMetricsPath = path.resolve(value);
    else if (arg === "--production-manifest") options.productionManifestPath = path.resolve(value);
    else if (arg === "--desktop-performance") options.desktopPerformancePath = path.resolve(value);
    else if (arg === "--desktop-memory") options.desktopMemoryPath = path.resolve(value);
    else if (arg === "--beta-review") options.betaReviewPath = path.resolve(value);
    else if (arg === "--failure-cases") options.failureCasesPath = path.resolve(value);
    else if (arg === "--output") options.outputPath = path.resolve(value);
    else if (arg === "--mobile-report") {
      const [device, rawPath] = value.split("=", 2);
      if (!device || !rawPath) usage();
      if (!customMobileReports) options.mobileReports = [];
      customMobileReports = true;
      options.mobileReports.push({ device, filePath: path.resolve(rawPath) });
    } else usage();
  }
  return options;
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readJson<T extends object = Record<string, unknown>>(filePath: string): Promise<T | null> {
  try {
    const value = JSON.parse(await readFile(filePath, "utf8"));
    return value && typeof value === "object" && !Array.isArray(value) ? value as T : null;
  } catch {
    return null;
  }
}

function section(text: string, start: string, end: string): string {
  const startIndex = text.indexOf(start);
  const endIndex = text.indexOf(end, startIndex + start.length);
  if (startIndex < 0 || endIndex < 0) return "";
  return text.slice(startIndex, endIndex);
}

function checklist(text: string): ChecklistItem[] {
  return [...text.matchAll(/^- \[([ xX])\] (.+)$/gm)].map((match) => ({
    checked: match[1]!.toLowerCase() === "x",
    text: match[2]!.trim(),
  }));
}

function progressMarkers(text: string) {
  return [...text.matchAll(/^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$/gm)].map((match) => ({
    id: match[1]!.trim(),
    task: match[2]!.trim(),
    status: match[3]!.trim(),
    evidence: match[4]!.trim(),
  }));
}

async function productionAsset(manifestPath: string) {
  const manifest = await readJson<ProductionManifest>(manifestPath);
  const modelFile = typeof manifest?.modelFile === "string" ? manifest.modelFile : null;
  const safeName = modelFile !== null && path.basename(modelFile) === modelFile && modelFile.toLowerCase().endsWith(".onnx");
  const modelPath = safeName ? path.resolve(path.dirname(manifestPath), modelFile!) : null;
  const modelExists = modelPath ? await exists(modelPath) : false;
  const modelSizeBytes = modelExists && modelPath ? (await stat(modelPath)).size : 0;
  const actualSha256 = modelExists && modelPath
    ? createHash("sha256").update(await readFile(modelPath)).digest("hex")
    : null;
  const integrityOk =
    modelExists &&
    typeof manifest?.sha256 === "string" &&
    manifest.sha256.toLowerCase() === actualSha256 &&
    manifest.modelSizeBytes === modelSizeBytes;
  return { ok: Boolean(safeName && integrityOk), manifestPath, manifest, modelPath, modelExists, modelSizeBytes, actualSha256, integrityOk };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const [specText, progressText] = await Promise.all([
    readFile(options.specPath, "utf8"),
    readFile(options.progressPath, "utf8"),
  ]);
  const userChecklist = checklist(section(specText, "### 16.1 用户需要完成", "### 16.2 工程侧需要完成"));
  const engineeringChecklist = checklist(section(specText, "### 16.2 工程侧需要完成", "## 17. 推荐执行顺序"));
  const markers = progressMarkers(progressText);

  const datasetReadiness = await readJson<DatasetReadiness>(options.datasetReadinessPath);
  const candidateReview = await readJson<CandidateReview>(options.candidateReviewPath);
  const bestMetrics = await readJson<MetricsReport>(options.bestMetricsPath);
  const desktopPerformance = await readJson<PerformanceReport>(options.desktopPerformancePath);
  const desktopMemory = await readJson<MemoryReport>(options.desktopMemoryPath);
  const betaReview = await readJson<BetaReview>(options.betaReviewPath);
  const failureCases = await readJson<FailureCases>(options.failureCasesPath);
  const production = await productionAsset(options.productionManifestPath);

  const releaseTestImages = Number(candidateReview?.dataset?.testImages ?? 0);
  const releaseTestGate = { ok: releaseTestImages >= 100, actual: releaseTestImages, required: 100, recommendedMaximum: 200 };
  const bestMetricsGate = {
    ok: Number(bestMetrics?.box_map50 ?? 0) >= 0.85 && Number(bestMetrics?.seg_map50 ?? 0) >= 0.75,
    boxMap50: bestMetrics?.box_map50 ?? null,
    maskMap50: bestMetrics?.seg_map50 ?? null,
    minimumBoxMap50: 0.85,
    minimumMaskMap50: 0.75,
  };
  const desktopGate = {
    ok: desktopPerformance?.ok === true && desktopMemory?.ok === true,
    performancePath: options.desktopPerformancePath,
    performanceOk: desktopPerformance?.ok === true,
    performanceSamples: desktopPerformance?.totals?.samples ?? null,
    memoryPath: options.desktopMemoryPath,
    memoryOk: desktopMemory?.ok === true,
    memorySamples: desktopMemory?.sampleCount ?? null,
  };
  const mobileGates = await Promise.all(options.mobileReports.map(async ({ device, filePath }) => {
    const report = await readJson<DeviceReport>(filePath);
    const ok =
      report?.version === "nail-texture-device-acceptance/v1" &&
      report.deviceFamily === device &&
      report.ok === true &&
      report.performance?.ok === true &&
      Number(report.performance?.sampleCount ?? 0) >= 20 &&
      report.memory?.ok === true;
    return {
      device,
      filePath,
      found: report !== null,
      ok,
      evidence: report ? {
        version: report.version ?? null,
        deviceFamily: report.deviceFamily ?? null,
        decision: report.decision ?? null,
        performanceOk: report.performance?.ok ?? null,
        performanceSamples: report.performance?.sampleCount ?? null,
        memoryOk: report.memory?.ok ?? null,
      } : null,
    };
  }));
  const requiredMobileDevices = ["android", "android-tablet", "iphone", "ipad"];
  const mobileGate = {
    ok:
      requiredMobileDevices.every((device) => mobileGates.some((gate) => gate.device === device && gate.ok)) &&
      new Set(mobileGates.map((gate) => gate.device)).size === mobileGates.length,
    requiredDevices: requiredMobileDevices,
    devices: mobileGates,
  };
  const betaGate = {
    ok:
      betaReview?.version === "nail-texture-beta-quality-review/v1" &&
      betaReview.ok === true &&
      betaReview.reviewedByUser === true &&
      Number(betaReview.sampleCount ?? 0) >= 100 &&
      Number(betaReview.directlyUsableRate ?? 0) >= 0.85,
    filePath: options.betaReviewPath,
    found: betaReview !== null,
    evidence: betaReview ? {
      version: betaReview.version ?? null,
      ok: betaReview.ok ?? null,
      reviewedByUser: betaReview.reviewedByUser ?? null,
      sampleCount: betaReview.sampleCount ?? null,
      directlyUsableRate: betaReview.directlyUsableRate ?? null,
    } : null,
  };
  const failureCaseGate = {
    ok:
      failureCases?.version === "nail-texture-user-failure-cases/v1" &&
      failureCases.ok === true &&
      Number(failureCases.sampleCount ?? 0) > 0,
    filePath: options.failureCasesPath,
    found: failureCases !== null,
    evidence: failureCases ? {
      version: failureCases.version ?? null,
      ok: failureCases.ok ?? null,
      sampleCount: failureCases.sampleCount ?? null,
    } : null,
  };
  const datasetGate = {
    ok: datasetReadiness?.ok === true,
    filePath: options.datasetReadinessPath,
    evidence: datasetReadiness ? {
      authorizationMode: datasetReadiness.authorizationMode ?? null,
      sourceRecordCount: datasetReadiness.artifacts?.sourceAuthorization?.recordCount ?? null,
      imageCount: datasetReadiness.artifacts?.phase1Readiness?.totals?.images ?? null,
      validMaskCount: datasetReadiness.artifacts?.phase1Readiness?.totals?.validMasks ?? null,
      splitCounts: datasetReadiness.artifacts?.phase1Readiness?.splitCounts ?? null,
      steps: Array.isArray(datasetReadiness.steps)
        ? datasetReadiness.steps.map((step) => ({ name: step.name ?? null, ok: step.ok === true }))
        : [],
    } : null,
  };
  const userChecklistGate = { ok: userChecklist.length > 0 && userChecklist.every((item) => item.checked), items: userChecklist };
  const engineeringChecklistGate = { ok: engineeringChecklist.length > 0 && engineeringChecklist.every((item) => item.checked), items: engineeringChecklist };

  const blockingInputs = [
    ...(!failureCaseGate.ok ? [{ code: "USER_FAILURE_CASES", owner: "user", summary: "Provide representative real-world failure images and an approved failure-case report." }] : []),
    ...(!releaseTestGate.ok ? [{ code: "REPRESENTATIVE_RELEASE_TESTSET", owner: "user+engineering", summary: `Provide and review at least ${releaseTestGate.required - releaseTestGate.actual} more source-isolated real release-test images.` }] : []),
    ...(!mobileGate.ok ? [{ code: "MOBILE_DEVICE_ACCEPTANCE", owner: "user+engineering", summary: "Run performance and memory acceptance on Android phone/tablet, iPhone, and iPad physical devices." }] : []),
    ...(!betaGate.ok ? [{ code: "USER_BETA_QUALITY_REVIEW", owner: "user", summary: "Complete the directly-usable / needs-fix / unusable Beta review on at least 100 representative images." }] : []),
  ];

  const gates = {
    userChecklist: userChecklistGate,
    engineeringChecklist: engineeringChecklistGate,
    datasetReadiness: datasetGate,
    bestCandidateMetrics: bestMetricsGate,
    representativeReleaseTest: releaseTestGate,
    desktopAcceptance: desktopGate,
    mobileAcceptance: mobileGate,
    failureCases: failureCaseGate,
    betaQualityReview: betaGate,
    productionModelAsset: production,
  };
  const ok = Object.values(gates).every((gate) => gate.ok === true);
  const report = {
    ok,
    version: "nail-texture-local-inference-completion-audit/v1",
    generatedAt: new Date().toISOString(),
    decision: ok ? "complete" : "hold",
    inputs: options,
    summary: {
      gateCount: Object.keys(gates).length,
      passedGates: Object.values(gates).filter((gate) => gate.ok === true).length,
      failedGates: Object.values(gates).filter((gate) => gate.ok !== true).length,
      progressMarkerCount: markers.length,
      passMarkerCount: markers.filter((marker) => marker.status.includes("PASS")).length,
      incompleteProgressMarkers: markers.filter((marker) => !marker.status.includes("PASS")),
    },
    gates,
    blockingInputs,
    nextAction: blockingInputs.length > 0
      ? "Collect external/user evidence without promoting the production model."
      : !production.ok
        ? "Run the approved promotion pipeline and rerun this audit."
        : "All implementation-spec completion gates are proven.",
  };
  if (options.outputPath) {
    await mkdir(path.dirname(options.outputPath), { recursive: true });
    await writeFile(options.outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  }
  console.log(JSON.stringify(report, null, 2));
  if (!ok) process.exitCode = 1;
}

await main();
