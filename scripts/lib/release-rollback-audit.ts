import { createHash } from "node:crypto";
import { access, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { validateNailTextureModelManifest } from "../../src/lib/nail-texture-recognition/model-runtime.ts";

export const RELEASE_ROLLBACK_AUDIT_VERSION = "nail-texture-release-rollback-audit/v2";

interface ManifestLike {
  version?: unknown;
  inputSize?: unknown;
  task?: unknown;
  backendPreferences?: unknown;
  modelFile?: unknown;
  modelSizeBytes?: unknown;
  sha256?: unknown;
  labels?: unknown;
}

interface ReleaseRegistryEntry extends ManifestLike {
  manifestSnapshotPath?: unknown;
  modelPath?: unknown;
  modelSizeMb?: unknown;
  registeredAt?: unknown;
}

interface ReleaseRegistry {
  currentVersion?: unknown;
  releases?: unknown;
}

export interface ReleaseRollbackAuditOptions {
  registryPath: string;
  manifestPath: string;
  requireRollbackCandidate?: boolean;
}

export interface ReleaseRollbackAuditReport {
  version: typeof RELEASE_ROLLBACK_AUDIT_VERSION;
  ok: boolean;
  decision: "approved_release_rollback_audit" | "hold_release_rollback_audit";
  inputs: {
    registry: { path: string; sha256: string };
    activeManifest: { path: string; sha256: string };
    requireRollbackCandidate: boolean;
  };
  currentVersion: string | null;
  releaseCount: number;
  rollbackCandidateCount: number;
  rollbackCandidates: string[];
  releases: Array<Record<string, unknown>>;
  activeRelease: Record<string, unknown> | null;
  errors: string[];
  warnings: string[];
  nextSteps: string[];
}

export interface VerifiedReleaseRollbackReport {
  found: boolean;
  ok: boolean;
  errors: string[];
  report: ReleaseRollbackAuditReport | null;
  replay: ReleaseRollbackAuditReport | null;
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function sha256File(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string" && item.length > 0);
}

function arraysEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
}

function safeModelFile(value: unknown): value is string {
  return typeof value === "string" && path.basename(value) === value && value.toLowerCase().endsWith(".onnx");
}

function normalizedRollbackPath(value: string): string {
  const resolved = path.resolve(value).replaceAll("\\", "/");
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function samePath(left: string, right: string): boolean {
  return normalizedRollbackPath(left) === normalizedRollbackPath(right);
}

export async function collectReleaseRollbackEvidencePaths(
  registryPath: string,
  manifestPath: string,
): Promise<string[]> {
  const resolvedRegistryPath = path.resolve(registryPath);
  const resolvedManifestPath = path.resolve(manifestPath);
  const [registry, activeManifest] = await Promise.all([
    readObject<ReleaseRegistry>(resolvedRegistryPath),
    readObject<ManifestLike>(resolvedManifestPath),
  ]);
  const evidencePaths = [resolvedRegistryPath, resolvedManifestPath];
  if (Array.isArray(registry.releases)) {
    for (const release of registry.releases as ReleaseRegistryEntry[]) {
      if (typeof release.manifestSnapshotPath === "string" && release.manifestSnapshotPath) {
        evidencePaths.push(path.resolve(release.manifestSnapshotPath));
      }
      if (typeof release.modelPath === "string" && release.modelPath) {
        evidencePaths.push(path.resolve(release.modelPath));
      }
    }
  }
  if (typeof activeManifest.modelFile === "string" && activeManifest.modelFile) {
    evidencePaths.push(path.resolve(path.dirname(resolvedManifestPath), activeManifest.modelFile));
  }
  return [...new Map(evidencePaths.map((filePath) => [
    normalizedRollbackPath(filePath),
    path.resolve(filePath),
  ])).values()];
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function readObject<T>(filePath: string): Promise<T> {
  const value = JSON.parse(await readFile(filePath, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`expected a JSON object: ${filePath}`);
  }
  return value as T;
}

function compareManifest(
  manifest: ManifestLike,
  release: ReleaseRegistryEntry,
  label: string,
  errors: string[],
) {
  if (manifest.version !== release.version) errors.push(`${label} version does not match registry entry`);
  if (manifest.modelFile !== release.modelFile) errors.push(`${label} modelFile does not match registry entry`);
  if (manifest.inputSize !== release.inputSize) errors.push(`${label} inputSize does not match registry entry`);
  if (manifest.task !== release.task) errors.push(`${label} task does not match registry entry`);
  if (
    !isStringArray(manifest.backendPreferences) ||
    !isStringArray(release.backendPreferences) ||
    !arraysEqual(manifest.backendPreferences, release.backendPreferences)
  ) {
    errors.push(`${label} backendPreferences do not match registry entry`);
  }
  if (!isStringArray(manifest.labels) || !isStringArray(release.labels) || !arraysEqual(manifest.labels, release.labels)) {
    errors.push(`${label} labels do not match registry entry`);
  }
  if (!isPositiveInteger(manifest.modelSizeBytes) || manifest.modelSizeBytes !== release.modelSizeBytes) {
    errors.push(`${label} modelSizeBytes does not match registry entry`);
  }
  if (!isSha256(manifest.sha256) || !isSha256(release.sha256) || manifest.sha256.toLowerCase() !== release.sha256.toLowerCase()) {
    errors.push(`${label} sha256 does not match registry entry`);
  }
}

export async function auditReleaseRollbackEvidence(
  rawOptions: ReleaseRollbackAuditOptions,
): Promise<ReleaseRollbackAuditReport> {
  const options = {
    registryPath: path.resolve(rawOptions.registryPath),
    manifestPath: path.resolve(rawOptions.manifestPath),
    requireRollbackCandidate: rawOptions.requireRollbackCandidate ?? true,
  };
  const [registry, currentManifest, registrySha256, manifestSha256] = await Promise.all([
    readObject<ReleaseRegistry>(options.registryPath),
    readObject<ManifestLike>(options.manifestPath),
    sha256File(options.registryPath),
    sha256File(options.manifestPath),
  ]);
  const errors: string[] = [];
  const warnings: string[] = [];
  const releases = Array.isArray(registry.releases) ? registry.releases as ReleaseRegistryEntry[] : [];
  const currentVersion = typeof registry.currentVersion === "string" && registry.currentVersion.trim()
    ? registry.currentVersion
    : null;

  if (!Array.isArray(registry.releases)) errors.push("registry.releases must be an array");
  if (!currentVersion) errors.push("registry.currentVersion must be set before rollback can be audited");
  if (releases.length === 0) errors.push("registry does not contain any releases");

  const versionCounts = new Map<string, number>();
  for (const release of releases) {
    if (typeof release.version === "string" && release.version) {
      versionCounts.set(release.version, (versionCounts.get(release.version) ?? 0) + 1);
    }
  }
  for (const [version, count] of versionCounts) {
    if (count > 1) errors.push(`duplicate release version in registry: ${version}`);
  }

  const currentEntry = releases.find((release) => release.version === currentVersion) ?? null;
  if (currentVersion && !currentEntry) errors.push(`currentVersion is not present in releases: ${currentVersion}`);
  const rollbackEntries = releases.filter((release) => release.version !== currentVersion);
  if (options.requireRollbackCandidate && rollbackEntries.length === 0) {
    errors.push("registry must contain at least one non-current release for rollback");
  }

  const releaseSummaries: Array<Record<string, unknown>> = [];
  const snapshotManifests = new Map<string, ManifestLike>();
  for (const release of releases) {
    const version = typeof release.version === "string" ? release.version : "";
    const snapshotPath = typeof release.manifestSnapshotPath === "string" ? path.resolve(release.manifestSnapshotPath) : "";
    const modelPath = typeof release.modelPath === "string" ? path.resolve(release.modelPath) : "";
    const modelFile = safeModelFile(release.modelFile) ? release.modelFile : "";
    const entryErrors: string[] = [];
    if (!version) entryErrors.push("version must be a non-empty string");
    if (!snapshotPath) entryErrors.push("manifestSnapshotPath must be a string");
    if (!modelPath) entryErrors.push("modelPath must be a string");
    if (!modelFile) entryErrors.push("modelFile must be a safe ONNX basename");
    if (
      snapshotPath &&
      modelPath &&
      modelFile &&
      !samePath(modelPath, path.resolve(path.dirname(snapshotPath), modelFile))
    ) {
      entryErrors.push("modelPath must resolve to modelFile beside the manifest snapshot");
    }
    if (!isPositiveInteger(release.inputSize)) entryErrors.push("inputSize must be a positive integer");
    if (release.task !== "segment") entryErrors.push("task must be segment");
    if (!isStringArray(release.backendPreferences)) entryErrors.push("backendPreferences must be a non-empty string array");
    if (!isStringArray(release.labels)) entryErrors.push("labels must be a non-empty string array");
    if (!isPositiveInteger(release.modelSizeBytes)) entryErrors.push("modelSizeBytes must be a positive integer");
    if (!isPositiveNumber(release.modelSizeMb)) entryErrors.push("modelSizeMb must be a positive number");
    if (!isSha256(release.sha256)) entryErrors.push("sha256 must be a 64-character hex string");
    if (typeof release.registeredAt !== "string" || !release.registeredAt) {
      warnings.push(`release ${version || "(unknown)"} is missing registeredAt`);
    }

    const [snapshotExists, modelExists] = await Promise.all([
      snapshotPath ? exists(snapshotPath) : false,
      modelPath ? exists(modelPath) : false,
    ]);
    if (!snapshotExists) entryErrors.push(`manifest snapshot is missing: ${snapshotPath}`);
    if (!modelExists) entryErrors.push(`model file is missing: ${modelPath}`);

    let snapshotSha256: string | null = null;
    let actualModelSizeBytes: number | null = null;
    let actualModelSizeMb: number | null = null;
    let actualSha256: string | null = null;
    if (snapshotExists) {
      snapshotSha256 = await sha256File(snapshotPath);
      try {
        const snapshotManifest = await readObject<ManifestLike>(snapshotPath);
        for (const error of validateNailTextureModelManifest(snapshotManifest)) {
          entryErrors.push(`snapshot runtime contract is invalid: ${error}`);
        }
        compareManifest(snapshotManifest, release, "snapshot", entryErrors);
        if (version) snapshotManifests.set(version, snapshotManifest);
      } catch (error) {
        entryErrors.push(`manifest snapshot is invalid JSON: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    if (modelExists) {
      actualModelSizeBytes = (await stat(modelPath)).size;
      actualModelSizeMb = Number((actualModelSizeBytes / (1024 * 1024)).toFixed(4));
      actualSha256 = await sha256File(modelPath);
      if (isPositiveInteger(release.modelSizeBytes) && release.modelSizeBytes !== actualModelSizeBytes) {
        entryErrors.push(`modelSizeBytes ${release.modelSizeBytes} does not match actual model size ${actualModelSizeBytes}`);
      }
      if (isSha256(release.sha256) && release.sha256.toLowerCase() !== actualSha256) {
        entryErrors.push(`sha256 ${release.sha256} does not match actual model sha256 ${actualSha256}`);
      }
      if (isPositiveNumber(release.modelSizeMb) && release.modelSizeMb !== actualModelSizeMb) {
        entryErrors.push(`modelSizeMb ${release.modelSizeMb} does not match actual model size ${actualModelSizeMb} MB`);
      }
    }
    errors.push(...entryErrors.map((message) => `release ${version || "(unknown)"}: ${message}`));
    releaseSummaries.push({
      version: version || null,
      isCurrent: version === currentVersion,
      snapshotPath: snapshotPath || null,
      snapshotSha256,
      modelPath: modelPath || null,
      snapshotExists,
      modelExists,
      modelSizeBytes: isPositiveInteger(release.modelSizeBytes) ? release.modelSizeBytes : null,
      actualModelSizeBytes,
      modelSizeMb: isPositiveNumber(release.modelSizeMb) ? release.modelSizeMb : null,
      actualModelSizeMb,
      sha256: isSha256(release.sha256) ? release.sha256.toLowerCase() : null,
      actualSha256,
      integrityOk:
        snapshotExists &&
        modelExists &&
        isPositiveInteger(release.modelSizeBytes) &&
        isSha256(release.sha256) &&
        release.modelSizeBytes === actualModelSizeBytes &&
        release.sha256.toLowerCase() === actualSha256,
      ok: entryErrors.length === 0,
      errors: entryErrors,
    });
  }

  let activeRelease: Record<string, unknown> | null = null;
  if (currentEntry) {
    const activeErrors: string[] = [];
    for (const error of validateNailTextureModelManifest(currentManifest)) {
      activeErrors.push(`active manifest runtime contract is invalid: ${error}`);
    }
    compareManifest(currentManifest, currentEntry, "active manifest", activeErrors);
    const currentSnapshotManifest = currentVersion ? snapshotManifests.get(currentVersion) : null;
    if (
      currentSnapshotManifest &&
      canonicalJson(currentManifest) !== canonicalJson(currentSnapshotManifest)
    ) {
      activeErrors.push("active manifest does not exactly match the registered current manifest snapshot");
    }
    const activeModelPath = safeModelFile(currentManifest.modelFile)
      ? path.resolve(path.dirname(options.manifestPath), currentManifest.modelFile)
      : "";
    if (!activeModelPath) activeErrors.push("active manifest modelFile must be a safe ONNX basename");
    if (activeModelPath && typeof currentEntry.modelPath === "string" && !samePath(activeModelPath, currentEntry.modelPath)) {
      activeErrors.push("active manifest model path does not match current registry modelPath");
    }
    const activeModelExists = activeModelPath ? await exists(activeModelPath) : false;
    if (!activeModelExists) activeErrors.push(`active model file is missing: ${activeModelPath}`);
    let actualModelSizeBytes: number | null = null;
    let actualSha256: string | null = null;
    if (activeModelExists) {
      actualModelSizeBytes = (await stat(activeModelPath)).size;
      actualSha256 = await sha256File(activeModelPath);
      if (!isPositiveInteger(currentManifest.modelSizeBytes) || currentManifest.modelSizeBytes !== actualModelSizeBytes) {
        activeErrors.push("active manifest modelSizeBytes does not match current model file");
      }
      if (!isSha256(currentManifest.sha256) || currentManifest.sha256.toLowerCase() !== actualSha256) {
        activeErrors.push("active manifest sha256 does not match current model file");
      }
    }
    errors.push(...activeErrors);
    activeRelease = {
      version: currentVersion,
      manifestPath: options.manifestPath,
      manifestSha256,
      modelPath: activeModelPath || null,
      modelExists: activeModelExists,
      actualModelSizeBytes,
      actualSha256,
      ok: activeErrors.length === 0,
      errors: activeErrors,
    };
  }

  const rollbackCandidates = rollbackEntries
    .map((release) => typeof release.version === "string" ? release.version : null)
    .filter((version): version is string => Boolean(version));
  const ok = errors.length === 0;
  return {
    version: RELEASE_ROLLBACK_AUDIT_VERSION,
    ok,
    decision: ok ? "approved_release_rollback_audit" : "hold_release_rollback_audit",
    inputs: {
      registry: { path: options.registryPath, sha256: registrySha256 },
      activeManifest: { path: options.manifestPath, sha256: manifestSha256 },
      requireRollbackCandidate: options.requireRollbackCandidate,
    },
    currentVersion,
    releaseCount: releases.length,
    rollbackCandidateCount: rollbackEntries.length,
    rollbackCandidates,
    releases: releaseSummaries,
    activeRelease,
    errors,
    warnings,
    nextSteps: ok
      ? ["Release registry, active manifest, manifest snapshots, and current model bytes are integrity-verified with at least one rollback candidate."]
      : ["Fix registry, active manifest, snapshots, model files, or integrity mismatches, then rerun the rollback audit."],
  };
}

export async function verifyApprovedReleaseRollbackReport(
  reportPath: string,
  expectedRegistryPath: string,
  expectedManifestPath: string,
): Promise<VerifiedReleaseRollbackReport> {
  const resolvedReport = path.resolve(reportPath);
  let report: ReleaseRollbackAuditReport;
  try {
    report = await readObject<ReleaseRollbackAuditReport>(resolvedReport);
  } catch (error) {
    return {
      found: false,
      ok: false,
      errors: [`cannot read rollback audit report: ${error instanceof Error ? error.message : String(error)}`],
      report: null,
      replay: null,
    };
  }
  const errors: string[] = [];
  const registryPath = path.resolve(expectedRegistryPath);
  const manifestPath = path.resolve(expectedManifestPath);
  if (report.version !== RELEASE_ROLLBACK_AUDIT_VERSION) errors.push("unsupported rollback audit report version");
  if (report.ok !== true || report.decision !== "approved_release_rollback_audit") {
    errors.push("rollback audit report is not an approved PASS");
  }
  if (!samePath(report.inputs?.registry?.path ?? "", registryPath)) errors.push("rollback registry path binding mismatch");
  if (!samePath(report.inputs?.activeManifest?.path ?? "", manifestPath)) errors.push("rollback active manifest path binding mismatch");
  if (report.inputs?.requireRollbackCandidate !== true) errors.push("formal rollback audit must require a rollback candidate");

  let replay: ReleaseRollbackAuditReport | null = null;
  try {
    replay = await auditReleaseRollbackEvidence({
      registryPath,
      manifestPath,
      requireRollbackCandidate: true,
    });
    if (!replay.ok) errors.push(...replay.errors.map((error) => `rollback replay: ${error}`));
    if (canonicalJson(report) !== canonicalJson(replay)) {
      errors.push("stored rollback audit report differs from current-state replay");
    }
  } catch (error) {
    errors.push(`cannot replay rollback evidence: ${error instanceof Error ? error.message : String(error)}`);
  }
  return { found: true, ok: errors.length === 0, errors, report, replay };
}
