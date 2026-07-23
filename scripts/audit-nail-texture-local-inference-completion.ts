import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { access, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { verifyApprovedDeviceAcceptanceReport } from "./lib/nail-texture-device-acceptance.ts";
import { verifyApprovedReleaseProductQualityReport } from "./lib/nail-texture-release-product-quality.ts";
import {
  collectReleaseRollbackEvidencePaths,
  verifyApprovedReleaseRollbackReport,
} from "./lib/release-rollback-audit.ts";
import { assertSafeOutputPath } from "./lib/safe-output-path.ts";

interface Options {
  specPath: string;
  progressPath: string;
  datasetReadinessPath: string;
  candidateReviewPath: string;
  releaseTestSnapshotPath: string;
  releaseTestQualityPath: string;
  hardNegativeAuditPath: string;
  bestMetricsPath: string;
  productionManifestPath: string;
  desktopPerformancePath: string;
  desktopMemoryPath: string;
  betaReviewPath: string;
  failureCasesPath: string;
  releaseProductQualityPath: string;
  releaseRegistryPath: string;
  rollbackAuditPath: string;
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
interface ReleaseTestSnapshot {
  snapshotId?: string;
  decision?: string;
  trainingUse?: string;
  counts?: { images?: number; masks?: number; coreImages?: number; stressImages?: number };
  representativeReleaseGate?: { ok?: boolean; actual?: number; required?: number; shortfall?: number };
  itemsSha256?: string;
  items?: Array<{ fileName?: string; lane?: string; imageSha256?: string; trainingUse?: string }>;
}
interface ReleaseTestQuality {
  schemaVersion?: number;
  ok?: boolean;
  decision?: string;
  qualityGatePassed?: boolean;
  trainingUse?: string;
  snapshot?: { itemsSha256?: string; counts?: { images?: number; masks?: number } };
  evaluations?: { full512?: { imgsz?: number; boxMap50?: number; maskMap50?: number; predictionLabels?: number } };
  inputs?: Record<string, string>;
}
interface HardNegativeAudit {
  schemaVersion?: number;
  ok?: boolean;
  status?: string;
  decision?: string;
  datasetRole?: string;
  releaseGeneralizationEligible?: boolean;
  inputs?: {
    weights?: { path?: string; sha256?: string };
    hardNegativeManifest?: { path?: string; sha256?: string; itemsSha256?: string };
  };
  configuration?: {
    maxFalsePositiveImages?: number;
    maxVariantDetectionDelta?: number;
  };
  counts?: { images?: number; variants?: number; inferenceViews?: number };
  deploymentThreshold?: Record<string, { falsePositiveImages?: number; detections?: number }>;
  variantDetectionDeltas?: Record<string, number>;
  records?: Array<{
    sourcePath?: string;
    variants?: Record<string, { path?: string }>;
  }>;
}
interface MetricsReport { box_map50?: number; seg_map50?: number }
interface PerformanceReport { ok?: boolean; totals?: { samples?: number } }
interface MemoryReport { ok?: boolean; sampleCount?: number }
interface BetaReview { version?: string; ok?: boolean; reviewedByUser?: boolean; sampleCount?: number; directlyUsableRate?: number }
interface FailureCases { version?: string; ok?: boolean; sampleCount?: number }
interface ProductionManifest { modelFile?: string; sha256?: string; modelSizeBytes?: number; [key: string]: unknown }

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-nail-texture-local-inference-completion.ts " +
      "[--spec <md>] [--progress <md>] [--dataset-readiness <json>] [--candidate-review <json>] " +
      "[--release-test-snapshot <json>] [--release-test-quality <json>] " +
      "[--hard-negative-audit <json>] " +
      "[--best-metrics <json>] [--production-manifest <json>] [--desktop-performance <json>] " +
      "[--desktop-memory <json>] [--mobile-report <device=json>] [--beta-review <json>] " +
      "[--failure-cases <json>] [--release-product-quality <json>] [--release-registry <json>] [--rollback-audit <json>] " +
      "[--output <json>]"
  );
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    specPath: path.resolve("docs/nail-texture-local-inference-implementation-spec.md"),
    progressPath: path.resolve("docs/nail-texture-local-inference-implementation-progress.md"),
    datasetReadinessPath: path.resolve("model/datasets/nail-texture-v1/metadata/training-dataset-readiness-release.json"),
    candidateReviewPath: path.resolve("model/reports/nail-texture-seg-real-candidate-v9-review.json"),
    releaseTestSnapshotPath: path.resolve("辅助材料/real-release-test-2026-07-13/frozen-reviewed-candidate-v1/manifest.json"),
    releaseTestQualityPath: path.resolve("model/reports/nail-texture-seg-real-candidate-v6-release-test-67-quality.json"),
    hardNegativeAuditPath: path.resolve("model/reports/nail-texture-hard-negative-watermark-audit.json"),
    bestMetricsPath: path.resolve("model/exports/nail-texture-seg-real-candidate-v6/test-metrics.512.json"),
    productionManifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    desktopPerformancePath: path.resolve("model/exports/nail-texture-seg-real-candidate-v6/browser-performance-report.json"),
    desktopMemoryPath: path.resolve("model/reports/nail-texture-seg-real-candidate-v6-desktop-memory.json"),
    betaReviewPath: path.resolve("model/reports/nail-texture-beta-quality-review.json"),
    failureCasesPath: path.resolve("model/reports/nail-texture-user-failure-cases.json"),
    releaseProductQualityPath: path.resolve("model/reports/nail-texture-release-product-quality.json"),
    releaseRegistryPath: path.resolve("public/models/nail-texture-seg/release-registry.json"),
    rollbackAuditPath: path.resolve("model/reports/nail-texture-release-rollback.json"),
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
    else if (arg === "--release-test-snapshot") options.releaseTestSnapshotPath = path.resolve(value);
    else if (arg === "--release-test-quality") options.releaseTestQualityPath = path.resolve(value);
    else if (arg === "--hard-negative-audit") options.hardNegativeAuditPath = path.resolve(value);
    else if (arg === "--best-metrics") options.bestMetricsPath = path.resolve(value);
    else if (arg === "--production-manifest") options.productionManifestPath = path.resolve(value);
    else if (arg === "--desktop-performance") options.desktopPerformancePath = path.resolve(value);
    else if (arg === "--desktop-memory") options.desktopMemoryPath = path.resolve(value);
    else if (arg === "--beta-review") options.betaReviewPath = path.resolve(value);
    else if (arg === "--failure-cases") options.failureCasesPath = path.resolve(value);
    else if (arg === "--release-product-quality") options.releaseProductQualityPath = path.resolve(value);
    else if (arg === "--release-registry") options.releaseRegistryPath = path.resolve(value);
    else if (arg === "--rollback-audit") options.rollbackAuditPath = path.resolve(value);
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

function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function evidencePath(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? path.resolve(value) : null;
}

function sameResolvedPath(left: string, right: string): boolean {
  return path.resolve(left).toLocaleLowerCase("en-US") === path.resolve(right).toLocaleLowerCase("en-US");
}

function verifyFrozenReleaseTestQuality(
  reportPath: string,
  expectedSnapshotPath: string,
  report: ReleaseTestQuality | null,
) {
  const transitivePaths = Object.values(report?.inputs ?? {})
    .map(evidencePath)
    .filter((value): value is string => value !== null);
  const errors: string[] = [];
  if (!report) errors.push("cannot read frozen release-test quality report");
  else if (report.schemaVersion !== 2) errors.push("frozen release-test quality report schemaVersion must be 2");
  const reportSnapshot = evidencePath(report?.inputs?.snapshot_manifest);
  if (!reportSnapshot || !sameResolvedPath(reportSnapshot, expectedSnapshotPath)) {
    errors.push("frozen release-test quality report is not bound to the requested snapshot path");
  }
  if (errors.length === 0) {
    const script = path.resolve("model/training/build-frozen-release-test-quality-report.py");
    const result = spawnSync("python", [script, "--verify-report", reportPath], {
      encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
    });
    if (result.status !== 0) {
      errors.push(`frozen release-test quality deep replay failed: ${(result.stderr || result.stdout).trim()}`);
    } else {
      try {
        const verification = JSON.parse(result.stdout) as { ok?: boolean; reportPath?: string; snapshotManifest?: string };
        if (
          verification.ok !== true ||
          !verification.reportPath ||
          !sameResolvedPath(verification.reportPath, reportPath) ||
          !verification.snapshotManifest ||
          !sameResolvedPath(verification.snapshotManifest, expectedSnapshotPath)
        ) {
          errors.push("frozen release-test quality verifier returned a mismatched identity");
        }
      } catch {
        errors.push("frozen release-test quality verifier returned invalid JSON");
      }
    }
  }
  return { ok: errors.length === 0, errors, transitivePaths };
}

function verifyHardNegativeWatermarkAudit(
  reportPath: string,
  report: HardNegativeAudit | null,
) {
  const errors: string[] = [];
  const transitivePaths: string[] = [];
  for (const value of [
    report?.inputs?.weights?.path,
    report?.inputs?.hardNegativeManifest?.path,
    ...(report?.records ?? []).flatMap((record) => [
      record.sourcePath,
      ...Object.values(record.variants ?? {}).map((variant) => variant.path),
    ]),
  ]) {
    const resolved = evidencePath(value);
    if (resolved) transitivePaths.push(resolved);
  }
  if (!report) errors.push("cannot read hard-negative watermark audit report");
  else if (report.schemaVersion !== 1) errors.push("hard-negative watermark audit schemaVersion must be 1");
  if (errors.length === 0) {
    const script = path.resolve("model/training/audit-hard-negative-watermark-shortcut.py");
    const result = spawnSync("python", [script, "--verify-report", reportPath], {
      encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
    });
    if (result.status !== 0) {
      errors.push(`hard-negative watermark audit deep verification failed: ${(result.stderr || result.stdout).trim()}`);
    } else {
      try {
        const verification = JSON.parse(result.stdout) as {
          ok?: boolean;
          reportPath?: string;
          datasetRole?: string;
          imageCount?: number;
          releaseGeneralizationEligible?: boolean;
        };
        if (
          verification.ok !== true ||
          !verification.reportPath ||
          !sameResolvedPath(verification.reportPath, reportPath) ||
          verification.datasetRole !== report?.datasetRole ||
          verification.imageCount !== report?.counts?.images ||
          verification.releaseGeneralizationEligible !== report?.releaseGeneralizationEligible
        ) {
          errors.push("hard-negative watermark verifier returned a mismatched identity");
        }
      } catch {
        errors.push("hard-negative watermark verifier returned invalid JSON");
      }
    }
  }
  return { ok: errors.length === 0, errors, transitivePaths };
}

function directInputPaths(options: Options): string[] {
  return [
    options.specPath,
    options.progressPath,
    options.datasetReadinessPath,
    options.candidateReviewPath,
    options.releaseTestSnapshotPath,
    options.releaseTestQualityPath,
    options.hardNegativeAuditPath,
    options.bestMetricsPath,
    options.productionManifestPath,
    options.desktopPerformancePath,
    options.desktopMemoryPath,
    options.betaReviewPath,
    options.failureCasesPath,
    options.releaseProductQualityPath,
    options.releaseRegistryPath,
    options.rollbackAuditPath,
    ...options.mobileReports.map((item) => item.filePath),
  ];
}

function productQualityInputPaths(
  verification: Awaited<ReturnType<typeof verifyApprovedReleaseProductQualityReport>>,
): string[] {
  const paths: string[] = [];
  const reportSnapshot = object(verification.report?.snapshot);
  const reportRaw = object(verification.report?.rawEvidence);
  const reportInstances = object(reportRaw?.instances);
  const reportScenarios = object(reportRaw?.scenarios);
  for (const value of [reportSnapshot?.path, reportInstances?.path, reportScenarios?.path]) {
    const resolved = evidencePath(value);
    if (resolved) paths.push(resolved);
  }
  if (verification.replay) {
    paths.push(
      verification.replay.snapshot.path,
      verification.replay.rawEvidence.instances.path,
      verification.replay.rawEvidence.scenarios.path,
    );
  }
  return paths;
}

function rollbackInputPaths(
  verification: Awaited<ReturnType<typeof verifyApprovedReleaseRollbackReport>>,
): string[] {
  const paths: string[] = [];
  for (const document of [verification.report, verification.replay]) {
    if (!document) continue;
    for (const value of [document.inputs?.registry?.path, document.inputs?.activeManifest?.path]) {
      const resolved = evidencePath(value);
      if (resolved) paths.push(resolved);
    }
    for (const release of document.releases ?? []) {
      for (const value of [release.snapshotPath, release.modelPath]) {
        const resolved = evidencePath(value);
        if (resolved) paths.push(resolved);
      }
    }
    for (const value of [document.activeRelease?.manifestPath, document.activeRelease?.modelPath]) {
      const resolved = evidencePath(value);
      if (resolved) paths.push(resolved);
    }
  }
  return paths;
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

function sectionLineOffset(text: string, heading: string): number {
  const index = text.indexOf(heading);
  return index < 0 ? 0 : (text.slice(0, index).match(/\n/g) ?? []).length;
}

function malformedChecklistRows(text: string, lineOffset = 0) {
  const validRow = /^- \[[ xX]\] .+$/;
  return text.split(/\r?\n/).flatMap((line, index) =>
    /^-\s*\[/.test(line) && !validRow.test(line)
      ? [{ lineNumber: lineOffset + index + 1, text: line }]
      : []
  );
}

function progressMarkers(text: string) {
  return [...text.matchAll(/^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$/gm)].map((match) => ({
    id: match[1]!.trim(),
    task: match[2]!.trim(),
    status: match[3]!.trim(),
    evidence: match[4]!.trim(),
  }));
}

function malformedProgressMarkerRows(text: string) {
  const validRow = /^\| `([^`]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$/;
  return text.split(/\r?\n/).flatMap((line, index) =>
    /^\|\s*`/.test(line) && !validRow.test(line)
      ? [{ lineNumber: index + 1, text: line }]
      : []
  );
}

function isPassMarker(status: string): boolean {
  return /^(?:✅\s*)?PASS(?:\s|（|\(|$)/i.test(status.trim());
}

function duplicateValues(values: string[]): string[] {
  const counts = new Map<string, number>();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return [...counts.entries()]
    .filter(([, count]) => count > 1)
    .map(([value]) => value)
    .sort((left, right) => left.localeCompare(right));
}

function releaseProductQualityGate(
  verification: Awaited<ReturnType<typeof verifyApprovedReleaseProductQualityReport>>,
  filePath: string,
  frozenSnapshotOk: boolean,
  expectedSnapshotPath: string,
) {
  const report = verification.report;
  const replay = verification.replay;
  const reportedSnapshot = report?.snapshot && typeof report.snapshot === "object" && !Array.isArray(report.snapshot)
    ? report.snapshot as Record<string, unknown>
    : null;
  const errors = [...verification.errors];
  if (!frozenSnapshotOk) errors.push("frozen release-test snapshot is not valid");

  return {
    ok: errors.length === 0,
    filePath,
    found: verification.found,
    evidence: report ? {
      version: report.version ?? null,
      outerOk: report.ok === true,
      reviewedByUser: report.reviewedByUser === true,
      trainingUse: report.trainingUse ?? null,
      expectedSnapshotPath,
      reportedSnapshotPath: reportedSnapshot?.path ?? null,
      snapshotItemsSha256: reportedSnapshot?.itemsSha256 ?? null,
      snapshotSha256: reportedSnapshot?.sha256 ?? null,
      instanceCsvSha256: replay?.rawEvidence.instances.sha256 ?? null,
      scenarioCsvSha256: replay?.rawEvidence.scenarios.sha256 ?? null,
      sampleImages: replay?.sampleImages ?? null,
      sampleInstances: replay?.sampleInstances ?? null,
      directlyUsableRate: replay?.directlyUsableRate ?? null,
      contaminationInstanceRate: replay?.contaminationInstanceRate ?? null,
      roughRectangleRate: replay?.roughRectangleRate ?? null,
      pixelLeakageRate: replay?.pixelLeakageRate ?? null,
      missingRate: replay?.missingRate ?? null,
      frozenMaximumMissingRate: replay?.frozenMaximumMissingRate ?? null,
      minimumAllowedDelta: replay?.minimumAllowedDelta ?? null,
      scenarioGroupCount: replay?.scenarioGroups.length ?? null,
      replayOk: replay?.ok === true,
    } : null,
    errors,
  };
}

function rollbackAuditGate(
  verification: Awaited<ReturnType<typeof verifyApprovedReleaseRollbackReport>>,
  filePath: string,
) {
  const report = verification.report;
  const replay = verification.replay;
  return {
    ok: verification.ok,
    filePath,
    found: verification.found,
    evidence: report ? {
      version: report.version,
      currentVersion: report.currentVersion ?? null,
      rollbackCandidateCount: report.rollbackCandidateCount,
      rollbackCandidates: report.rollbackCandidates,
      releaseCount: report.releaseCount,
      registryPath: report.inputs?.registry?.path ?? null,
      registrySha256: report.inputs?.registry?.sha256 ?? null,
      activeManifestPath: report.inputs?.activeManifest?.path ?? null,
      activeManifestSha256: report.inputs?.activeManifest?.sha256 ?? null,
      replayOk: replay?.ok === true,
    } : null,
    errors: verification.errors,
  };
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
  if (options.outputPath) await assertSafeOutputPath(options.outputPath, directInputPaths(options));
  const [specText, progressText] = await Promise.all([
    readFile(options.specPath, "utf8"),
    readFile(options.progressPath, "utf8"),
  ]);
  const userChecklistSection = section(specText, "### 16.1 用户需要完成", "### 16.2 工程侧需要完成");
  const engineeringChecklistSection = section(specText, "### 16.2 工程侧需要完成", "## 17. 推荐执行顺序");
  const userChecklist = checklist(userChecklistSection);
  const engineeringChecklist = checklist(engineeringChecklistSection);
  const malformedUserChecklistRows = malformedChecklistRows(
    userChecklistSection,
    sectionLineOffset(specText, "### 16.1 用户需要完成"),
  );
  const malformedEngineeringChecklistRows = malformedChecklistRows(
    engineeringChecklistSection,
    sectionLineOffset(specText, "### 16.2 工程侧需要完成"),
  );
  const markers = progressMarkers(progressText);
  const malformedMarkerRows = malformedProgressMarkerRows(progressText);

  const datasetReadiness = await readJson<DatasetReadiness>(options.datasetReadinessPath);
  const candidateReview = await readJson<CandidateReview>(options.candidateReviewPath);
  const releaseTestSnapshot = await readJson<ReleaseTestSnapshot>(options.releaseTestSnapshotPath);
  const releaseTestQuality = await readJson<ReleaseTestQuality>(options.releaseTestQualityPath);
  const releaseTestQualityVerification = verifyFrozenReleaseTestQuality(
    options.releaseTestQualityPath,
    options.releaseTestSnapshotPath,
    releaseTestQuality,
  );
  const hardNegativeAudit = await readJson<HardNegativeAudit>(options.hardNegativeAuditPath);
  const hardNegativeAuditVerification = verifyHardNegativeWatermarkAudit(
    options.hardNegativeAuditPath,
    hardNegativeAudit,
  );
  const bestMetrics = await readJson<MetricsReport>(options.bestMetricsPath);
  const desktopPerformance = await readJson<PerformanceReport>(options.desktopPerformancePath);
  const desktopMemory = await readJson<MemoryReport>(options.desktopMemoryPath);
  const betaReview = await readJson<BetaReview>(options.betaReviewPath);
  const failureCases = await readJson<FailureCases>(options.failureCasesPath);
  const production = await productionAsset(options.productionManifestPath);
  const productQualityVerification = await verifyApprovedReleaseProductQualityReport(
    options.releaseProductQualityPath,
    options.releaseTestSnapshotPath,
  );
  const rollbackVerification = await verifyApprovedReleaseRollbackReport(
    options.rollbackAuditPath,
    options.releaseRegistryPath,
    options.productionManifestPath,
  );
  let currentRollbackEvidencePaths: string[] = [];
  try {
    currentRollbackEvidencePaths = await collectReleaseRollbackEvidencePaths(
      options.releaseRegistryPath,
      options.productionManifestPath,
    );
  } catch {
    // The rollback gate reports unreadable registry/manifest evidence; direct inputs remain protected.
  }

  const evaluatedReleaseTestImages = Number(candidateReview?.dataset?.testImages ?? 0);
  const snapshotItems = Array.isArray(releaseTestSnapshot?.items) ? releaseTestSnapshot.items : [];
  const snapshotImages = Number(releaseTestSnapshot?.counts?.images ?? 0);
  const frozenSnapshotOk =
    releaseTestSnapshot?.decision === "frozen_reviewed_candidate_not_release_ready" &&
    releaseTestSnapshot.trainingUse === "prohibited" &&
    snapshotImages > 0 &&
    snapshotItems.length === snapshotImages &&
    new Set(snapshotItems.map((item) => `${item.lane}:${item.fileName}`)).size === snapshotImages &&
    snapshotItems.every((item) => typeof item.imageSha256 === "string" && /^[a-f0-9]{64}$/i.test(item.imageSha256)) &&
    new Set(snapshotItems.map((item) => item.imageSha256!.toLowerCase())).size === snapshotImages &&
    snapshotItems.every((item) => item.trainingUse === "prohibited") &&
    releaseTestSnapshot.representativeReleaseGate?.actual === snapshotImages &&
    releaseTestSnapshot.representativeReleaseGate?.required === 100 &&
    typeof releaseTestSnapshot.itemsSha256 === "string" &&
    /^[a-f0-9]{64}$/i.test(releaseTestSnapshot.itemsSha256);
  const releaseTestImages = frozenSnapshotOk ? snapshotImages : evaluatedReleaseTestImages;
  const frozenQuality = releaseTestQuality?.evaluations?.full512;
  const frozenQualityOk =
    frozenSnapshotOk &&
    releaseTestQualityVerification.ok &&
    releaseTestQuality?.ok === true &&
    releaseTestQuality.trainingUse === "prohibited" &&
    releaseTestQuality.snapshot?.itemsSha256 === releaseTestSnapshot?.itemsSha256 &&
    releaseTestQuality.snapshot?.counts?.images === snapshotImages &&
    frozenQuality?.imgsz === 512 &&
    frozenQuality.predictionLabels === snapshotImages &&
    Number.isFinite(Number(frozenQuality.boxMap50)) &&
    Number.isFinite(Number(frozenQuality.maskMap50));
  const releaseTestGate = {
    ok: releaseTestImages >= 100,
    actual: releaseTestImages,
    required: 100,
    recommendedMaximum: 200,
    evidenceScope: frozenSnapshotOk ? "frozen-reviewed-candidate" : "evaluated-model-test-split",
    snapshotPath: options.releaseTestSnapshotPath,
    snapshotOk: frozenSnapshotOk,
    snapshotMasks: frozenSnapshotOk ? releaseTestSnapshot?.counts?.masks ?? null : null,
    snapshotSourceHash: frozenSnapshotOk ? releaseTestSnapshot?.itemsSha256 ?? null : null,
    evaluatedModelTestImages: frozenQualityOk ? snapshotImages : evaluatedReleaseTestImages,
    historicalEvaluatedModelTestImages: evaluatedReleaseTestImages,
    note: frozenSnapshotOk && frozenQualityOk && releaseTestImages >= 100
      ? "The frozen reviewed candidate has deployment-resolution quality evidence and reaches the 100-image representative-size gate."
      : frozenSnapshotOk && frozenQualityOk
        ? "The frozen reviewed candidate has deployment-resolution quality evidence, but remains below the 100-image representative-size gate."
      : frozenSnapshotOk
        ? "Frozen reviewed candidates count toward dataset-size readiness only; no lineage-checked snapshot quality report was found."
        : "No valid frozen reviewed candidate snapshot was found; using the evaluated model test split count.",
  };
  const requiresBoundFrozenQuality = frozenSnapshotOk && snapshotImages >= 100;
  const selectedBoxMap50 = frozenQualityOk ? Number(frozenQuality?.boxMap50) : Number(bestMetrics?.box_map50 ?? 0);
  const selectedMaskMap50 = frozenQualityOk ? Number(frozenQuality?.maskMap50) : Number(bestMetrics?.seg_map50 ?? 0);
  const bestMetricsGate = {
    ok:
      selectedBoxMap50 >= 0.85 &&
      selectedMaskMap50 >= 0.75 &&
      (!requiresBoundFrozenQuality || (frozenQualityOk && releaseTestQuality?.qualityGatePassed === true)),
    boxMap50: selectedBoxMap50,
    maskMap50: selectedMaskMap50,
    minimumBoxMap50: 0.85,
    minimumMaskMap50: 0.75,
    evidenceScope: frozenQualityOk
      ? `frozen-reviewed-candidate-${snapshotImages}-deployment-512`
      : requiresBoundFrozenQuality
        ? `missing-or-invalid-frozen-reviewed-candidate-${snapshotImages}-deployment-512-quality`
        : "historical-evaluated-model-test-split-13",
    frozenQualityRequired: requiresBoundFrozenQuality,
    qualityReportPath: options.releaseTestQualityPath,
    qualityReportOk: frozenQualityOk,
    qualityReportDeepVerificationOk: releaseTestQualityVerification.ok,
    qualityReportVerificationErrors: releaseTestQualityVerification.errors,
    qualityDecision: frozenQualityOk ? releaseTestQuality?.decision ?? null : null,
    historical13: {
      boxMap50: bestMetrics?.box_map50 ?? null,
      maskMap50: bestMetrics?.seg_map50 ?? null,
    },
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
  const mobileResults = await Promise.all(options.mobileReports.map(async ({ device, filePath }) => {
    const verification = await verifyApprovedDeviceAcceptanceReport(filePath, device);
    const report = verification.report;
    const sourcePaths = object(report?.sourcePaths);
    const reportEvidence = object(report?.evidence);
    const performanceEvidence = object(reportEvidence?.performance);
    const memoryEvidence = object(reportEvidence?.memory);
    const performancePath = evidencePath(sourcePaths?.performance);
    const memoryPath = evidencePath(sourcePaths?.memory);
    const transitivePaths = [
      performancePath,
      memoryPath,
      evidencePath(performanceEvidence?.path),
      evidencePath(memoryEvidence?.verificationPath),
      evidencePath(memoryEvidence?.rawReportPath),
      verification.memory.rawReportPath,
    ]
      .filter((value): value is string => Boolean(value));
    for (const evidenceFile of [performancePath, memoryPath]) {
      if (!evidenceFile) continue;
      const evidenceDocument = await readJson<Record<string, unknown>>(evidenceFile);
      const rawInputPath = evidencePath(evidenceDocument?.inputPath);
      if (rawInputPath) transitivePaths.push(rawInputPath);
    }
    return { gate: {
      device,
      filePath,
      found: verification.found,
      ok: verification.ok,
      evidence: report ? {
        version: report.version ?? null,
        deviceFamily: report.deviceFamily ?? null,
        decision: report.decision ?? null,
        performanceOk: verification.performance.sampleCount >= 20 && verification.errors.every((error) => !error.startsWith("performance")),
        performanceSamples: verification.performance.sampleCount,
        performanceReportSha256: verification.performance.reportSha256 || null,
        memoryOk: verification.memory.sampleCount >= 20 && verification.errors.every((error) => !error.includes("memory")),
        memorySamples: verification.memory.sampleCount,
        memoryVerificationSha256: verification.memory.verificationSha256 || null,
        rawMemorySha256: verification.memory.rawReportSha256,
        replayErrors: verification.errors,
      } : null,
    }, transitivePaths };
  }));
  const mobileGates = mobileResults.map((item) => item.gate);
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
  const deploymentVariants = hardNegativeAudit?.deploymentThreshold ?? {};
  const hardNegativeWatermarkGate = {
    ok:
      hardNegativeAuditVerification.ok &&
      hardNegativeAudit?.ok === true &&
      hardNegativeAudit.status === "PASS" &&
      hardNegativeAudit.decision === "hard_negative_watermark_shortcut_stability_pass" &&
      hardNegativeAudit.datasetRole === "independent-holdout" &&
      hardNegativeAudit.releaseGeneralizationEligible === true &&
      Number(hardNegativeAudit.counts?.images ?? 0) >= 100 &&
      hardNegativeAudit.counts?.variants === 3 &&
      hardNegativeAudit.configuration?.maxFalsePositiveImages === 0 &&
      hardNegativeAudit.configuration?.maxVariantDetectionDelta === 0 &&
      ["original", "crop12", "blur_corner"].every(
        (variant) => deploymentVariants[variant]?.falsePositiveImages === 0,
      ) &&
      Object.values(hardNegativeAudit.variantDetectionDeltas ?? {}).every((delta) => delta === 0),
    filePath: options.hardNegativeAuditPath,
    found: hardNegativeAudit !== null,
    evidence: hardNegativeAudit ? {
      outerOk: hardNegativeAudit.ok === true,
      status: hardNegativeAudit.status ?? null,
      decision: hardNegativeAudit.decision ?? null,
      datasetRole: hardNegativeAudit.datasetRole ?? null,
      releaseGeneralizationEligible: hardNegativeAudit.releaseGeneralizationEligible === true,
      imageCount: hardNegativeAudit.counts?.images ?? null,
      maxFalsePositiveImages: hardNegativeAudit.configuration?.maxFalsePositiveImages ?? null,
      maxVariantDetectionDelta: hardNegativeAudit.configuration?.maxVariantDetectionDelta ?? null,
      deploymentFalsePositiveImages: Object.fromEntries(
        Object.entries(deploymentVariants).map(([variant, value]) => [variant, value.falsePositiveImages ?? null]),
      ),
      variantDetectionDeltas: hardNegativeAudit.variantDetectionDeltas ?? null,
      deepVerificationOk: hardNegativeAuditVerification.ok,
    } : null,
    errors: hardNegativeAuditVerification.errors,
  };
  const duplicateUserChecklistItems = duplicateValues(userChecklist.map((item) => item.text));
  const duplicateEngineeringChecklistItems = duplicateValues(engineeringChecklist.map((item) => item.text));
  const userChecklistGate = {
    ok:
      userChecklist.length > 0 &&
      malformedUserChecklistRows.length === 0 &&
      duplicateUserChecklistItems.length === 0 &&
      userChecklist.every((item) => item.checked),
    items: userChecklist,
    malformedRows: malformedUserChecklistRows,
    duplicateItems: duplicateUserChecklistItems,
  };
  const engineeringChecklistGate = {
    ok:
      engineeringChecklist.length > 0 &&
      malformedEngineeringChecklistRows.length === 0 &&
      duplicateEngineeringChecklistItems.length === 0 &&
      engineeringChecklist.every((item) => item.checked),
    items: engineeringChecklist,
    malformedRows: malformedEngineeringChecklistRows,
    duplicateItems: duplicateEngineeringChecklistItems,
  };
  const incompleteProgressMarkers = markers.filter((marker) => !isPassMarker(marker.status));
  const duplicateProgressMarkerIds = duplicateValues(markers.map((marker) => marker.id));
  const progressMarkersGate = {
    ok:
      markers.length > 0 &&
      malformedMarkerRows.length === 0 &&
      duplicateProgressMarkerIds.length === 0 &&
      incompleteProgressMarkers.length === 0,
    markerCount: markers.length,
    uniqueMarkerCount: new Set(markers.map((marker) => marker.id)).size,
    passMarkerCount: markers.length - incompleteProgressMarkers.length,
    malformedRows: malformedMarkerRows,
    duplicateMarkerIds: duplicateProgressMarkerIds,
    incompleteMarkers: incompleteProgressMarkers,
  };
  const productQualityGate = releaseProductQualityGate(
    productQualityVerification,
    options.releaseProductQualityPath,
    frozenSnapshotOk,
    options.releaseTestSnapshotPath,
  );
  const rollbackGate = rollbackAuditGate(rollbackVerification, options.rollbackAuditPath);
  if (options.outputPath) {
    await assertSafeOutputPath(options.outputPath, [
      ...directInputPaths(options),
      ...productQualityInputPaths(productQualityVerification),
      ...rollbackInputPaths(rollbackVerification),
      ...currentRollbackEvidencePaths,
      ...releaseTestQualityVerification.transitivePaths,
      ...hardNegativeAuditVerification.transitivePaths,
      ...mobileResults.flatMap((item) => item.transitivePaths),
      ...(production.modelPath ? [production.modelPath] : []),
    ]);
  }

  const blockingInputs = [
    ...(!userChecklistGate.ok ? [{
      code: "SPEC_USER_CHECKLIST",
      owner: "user",
      summary: [
        "Complete every explicit user checklist item in implementation spec section 16.1.",
        malformedUserChecklistRows.length > 0
          ? `Repair malformed user checklist rows: ${malformedUserChecklistRows.map((row) => row.lineNumber).join(", ")}.`
          : "",
        duplicateUserChecklistItems.length > 0
          ? `Remove duplicate user checklist items: ${duplicateUserChecklistItems.join("; ")}.`
          : "",
      ].filter(Boolean).join(" "),
    }] : []),
    ...(!engineeringChecklistGate.ok ? [{
      code: "SPEC_ENGINEERING_CHECKLIST",
      owner: "engineering",
      summary: [
        "Complete every explicit engineering checklist item in implementation spec section 16.2.",
        malformedEngineeringChecklistRows.length > 0
          ? `Repair malformed engineering checklist rows: ${malformedEngineeringChecklistRows.map((row) => row.lineNumber).join(", ")}.`
          : "",
        duplicateEngineeringChecklistItems.length > 0
          ? `Remove duplicate engineering checklist items: ${duplicateEngineeringChecklistItems.join("; ")}.`
          : "",
      ].filter(Boolean).join(" "),
    }] : []),
    ...(!progressMarkersGate.ok ? [{
      code: "INCOMPLETE_PROGRESS_MARKERS",
      owner: "user+engineering",
      summary: [
        markers.length === 0 ? "The progress table contains no parseable markers." : "",
        malformedMarkerRows.length > 0
          ? `Malformed progress marker rows must be repaired: ${malformedMarkerRows.map((row) => row.lineNumber).join(", ")}.`
          : "",
        duplicateProgressMarkerIds.length > 0
          ? `Duplicate progress marker IDs must be resolved: ${duplicateProgressMarkerIds.join(", ")}.`
          : "",
        incompleteProgressMarkers.length > 0
          ? `${incompleteProgressMarkers.length} progress marker(s) are not PASS: ${incompleteProgressMarkers.map((marker) => marker.id).join(", ")}.`
          : "",
      ].filter(Boolean).join(" "),
    }] : []),
    ...(!datasetGate.ok ? [{ code: "DATASET_READINESS", owner: "engineering", summary: "Restore approved release-mode dataset readiness evidence." }] : []),
    ...(!hardNegativeWatermarkGate.ok ? [{
      code: "INDEPENDENT_HARD_NEGATIVE_WATERMARK_AUDIT",
      owner: "user+engineering",
      summary: "Provide at least 100 source-isolated, original-resolution-reviewed independent hard negatives and pass the zero-false-positive / zero-variant-delta watermark shortcut audit.",
    }] : []),
    ...(!failureCaseGate.ok ? [{ code: "USER_FAILURE_CASES", owner: "user", summary: "Provide representative real-world failure images and an approved failure-case report." }] : []),
    ...(!bestMetricsGate.ok ? [{
      code: "MODEL_QUALITY_REGRESSION",
      owner: "engineering",
      summary: requiresBoundFrozenQuality && !frozenQualityOk
        ? `Provide a deep-verifiable deployment-512 quality report bound to the frozen ${snapshotImages}-image snapshot; historical small-test metrics cannot satisfy this gate.`
        : `Improve the deployment-resolution model: current box/mask mAP50 is ${bestMetricsGate.boxMap50.toFixed(4)}/${bestMetricsGate.maskMap50.toFixed(4)}.`,
    }] : []),
    ...(!releaseTestGate.ok ? [{ code: "REPRESENTATIVE_RELEASE_TESTSET", owner: "user+engineering", summary: `Provide and review at least ${releaseTestGate.required - releaseTestGate.actual} more source-isolated real release-test images.` }] : []),
    ...(!desktopGate.ok ? [{ code: "DESKTOP_ACCEPTANCE", owner: "engineering", summary: "Restore passing desktop performance and repeated-run memory evidence." }] : []),
    ...(!mobileGate.ok ? [{ code: "MOBILE_DEVICE_ACCEPTANCE", owner: "user+engineering", summary: "Run performance and memory acceptance on Android phone/tablet, iPhone, and iPad physical devices." }] : []),
    ...(!betaGate.ok ? [{ code: "USER_BETA_QUALITY_REVIEW", owner: "user", summary: "Complete the directly-usable / needs-fix / unusable Beta review on at least 100 representative images." }] : []),
    ...(!productQualityGate.ok ? [{ code: "RELEASE_PRODUCT_QUALITY_EVIDENCE", owner: "user+engineering", summary: "Provide a user-reviewed, frozen-snapshot-bound product quality report covering usability, contamination, leakage, rough rectangles, missing nails, and scenario regressions." }] : []),
    ...(!production.ok ? [{ code: "PRODUCTION_MODEL_ASSET", owner: "engineering", summary: "Publish an approved production ONNX whose size and SHA-256 match the production manifest." }] : []),
    ...(!rollbackGate.ok ? [{ code: "RELEASE_ROLLBACK_AUDIT", owner: "engineering", summary: "Provide a passing rollback audit with an integrity-verified current release and at least one rollback candidate." }] : []),
  ];

  const gates = {
    userChecklist: userChecklistGate,
    engineeringChecklist: engineeringChecklistGate,
    progressMarkers: progressMarkersGate,
    datasetReadiness: datasetGate,
    independentHardNegativeWatermark: hardNegativeWatermarkGate,
    bestCandidateMetrics: bestMetricsGate,
    representativeReleaseTest: releaseTestGate,
    desktopAcceptance: desktopGate,
    mobileAcceptance: mobileGate,
    failureCases: failureCaseGate,
    betaQualityReview: betaGate,
    releaseProductQuality: productQualityGate,
    productionModelAsset: production,
    releaseRollback: rollbackGate,
  };
  const ok = Object.values(gates).every((gate) => gate.ok === true);
  const report = {
    ok,
    version: "nail-texture-local-inference-completion-audit/v2",
    generatedAt: new Date().toISOString(),
    decision: ok ? "complete" : "hold",
    inputs: options,
    summary: {
      gateCount: Object.keys(gates).length,
      passedGates: Object.values(gates).filter((gate) => gate.ok === true).length,
      failedGates: Object.values(gates).filter((gate) => gate.ok !== true).length,
      progressMarkerCount: markers.length,
      passMarkerCount: progressMarkersGate.passMarkerCount,
      incompleteProgressMarkers,
    },
    gates,
    blockingInputs,
    nextAction: blockingInputs.length > 0
      ? "Resolve every failed completion gate without promoting the production model."
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
