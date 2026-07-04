import { createHash } from "node:crypto";
import path from "node:path";
import process from "node:process";
import { access, readFile, stat, writeFile } from "node:fs/promises";

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

interface ReleaseRegistryEntry {
  version?: unknown;
  manifestSnapshotPath?: unknown;
  modelFile?: unknown;
  modelPath?: unknown;
  inputSize?: unknown;
  task?: unknown;
  backendPreferences?: unknown;
  labels?: unknown;
  modelSizeBytes?: unknown;
  modelSizeMb?: unknown;
  sha256?: unknown;
  registeredAt?: unknown;
}

interface ReleaseRegistry {
  currentVersion?: unknown;
  releases?: unknown;
}

interface CliOptions {
  registryPath: string;
  manifestPath: string;
  outputPath?: string;
  requireRollbackCandidate: boolean;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-release-rollback.ts [--registry <release-registry.json>] [--manifest <manifest.json>] [--output <report.json>] [--require-rollback-candidate true|false]"
  );
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  usage();
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    registryPath: path.resolve("public/models/nail-texture-seg/release-registry.json"),
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    requireRollbackCandidate: true,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--registry") options.registryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--manifest") options.manifestPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--require-rollback-candidate") {
      options.requireRollbackCandidate = parseBoolean(argv[++index] ?? usage());
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

async function hashFileSha256(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function arraysEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
}

const options = parseArgs(process.argv.slice(2));
const registry = JSON.parse(await readFile(options.registryPath, "utf8")) as ReleaseRegistry;
const currentManifest = JSON.parse(await readFile(options.manifestPath, "utf8")) as ManifestLike;

const errors: string[] = [];
const warnings: string[] = [];

const releases = Array.isArray(registry.releases)
  ? (registry.releases as ReleaseRegistryEntry[])
  : [];
const currentVersion = typeof registry.currentVersion === "string" ? registry.currentVersion : null;

if (!Array.isArray(registry.releases)) errors.push("registry.releases must be an array");
if (!currentVersion) errors.push("registry.currentVersion must be set before rollback can be audited");
if (releases.length === 0) errors.push("registry does not contain any releases");

const versionCounts = new Map<string, number>();
for (const release of releases) {
  if (typeof release.version === "string") {
    versionCounts.set(release.version, (versionCounts.get(release.version) ?? 0) + 1);
  }
}
for (const [version, count] of versionCounts) {
  if (count > 1) errors.push(`duplicate release version in registry: ${version}`);
}

const currentEntry = releases.find((release) => release.version === currentVersion) ?? null;
if (currentVersion && !currentEntry) {
  errors.push(`currentVersion is not present in releases: ${currentVersion}`);
}

const rollbackCandidates = releases.filter((release) => release.version !== currentVersion);
if (options.requireRollbackCandidate && rollbackCandidates.length === 0) {
  errors.push("registry must contain at least one non-current release for rollback");
}

const releaseSummaries = [];
for (const release of releases) {
  const version = typeof release.version === "string" ? release.version : "";
  const snapshotPath =
    typeof release.manifestSnapshotPath === "string" ? path.resolve(release.manifestSnapshotPath) : "";
  const modelPath = typeof release.modelPath === "string" ? path.resolve(release.modelPath) : "";
  const modelFile = typeof release.modelFile === "string" ? release.modelFile : "";
  const entryErrors: string[] = [];

  if (!version) entryErrors.push("version must be a string");
  if (!snapshotPath) entryErrors.push("manifestSnapshotPath must be a string");
  if (!modelPath) entryErrors.push("modelPath must be a string");
  if (!modelFile) entryErrors.push("modelFile must be a string");
  if (!isPositiveInteger(release.modelSizeBytes)) {
    entryErrors.push("modelSizeBytes must be a positive integer");
  }
  if (typeof release.modelSizeMb !== "number" || release.modelSizeMb <= 0) {
    entryErrors.push("modelSizeMb must be a positive number");
  }
  if (!isSha256(release.sha256)) {
    entryErrors.push("sha256 must be a 64-character hex string");
  }
  if (typeof release.registeredAt !== "string" || !release.registeredAt) {
    warnings.push(`release ${version || "(unknown)"} is missing registeredAt`);
  }

  const snapshotExists = snapshotPath ? await exists(snapshotPath) : false;
  const modelExists = modelPath ? await exists(modelPath) : false;
  if (!snapshotExists) entryErrors.push(`manifest snapshot is missing: ${snapshotPath}`);
  if (!modelExists) entryErrors.push(`model file is missing: ${modelPath}`);

  let actualModelSizeBytes: number | null = null;
  let actualSha256: string | null = null;
  if (modelExists) {
    actualModelSizeBytes = (await stat(modelPath)).size;
    actualSha256 = await hashFileSha256(modelPath);
    if (isPositiveInteger(release.modelSizeBytes) && release.modelSizeBytes !== actualModelSizeBytes) {
      entryErrors.push(
        `modelSizeBytes ${release.modelSizeBytes} does not match actual model size ${actualModelSizeBytes}`
      );
    }
    if (isSha256(release.sha256) && release.sha256.toLowerCase() !== actualSha256) {
      entryErrors.push(`sha256 ${release.sha256} does not match actual model sha256 ${actualSha256}`);
    }
  }

  let snapshotManifest: ManifestLike | null = null;
  if (snapshotExists) {
    snapshotManifest = JSON.parse(await readFile(snapshotPath, "utf8")) as ManifestLike;
    if (snapshotManifest.version !== version) {
      entryErrors.push(`snapshot version ${String(snapshotManifest.version)} does not match registry version ${version}`);
    }
    if (snapshotManifest.modelFile !== modelFile) {
      entryErrors.push(`snapshot modelFile ${String(snapshotManifest.modelFile)} does not match registry modelFile ${modelFile}`);
    }
    if (snapshotManifest.inputSize !== release.inputSize) {
      entryErrors.push("snapshot inputSize does not match registry entry");
    }
    if (snapshotManifest.task !== release.task) {
      entryErrors.push("snapshot task does not match registry entry");
    }
    if (
      !isStringArray(snapshotManifest.backendPreferences) ||
      !isStringArray(release.backendPreferences) ||
      !arraysEqual(snapshotManifest.backendPreferences, release.backendPreferences)
    ) {
      entryErrors.push("snapshot backendPreferences do not match registry entry");
    }
    if (
      !isStringArray(snapshotManifest.labels) ||
      !isStringArray(release.labels) ||
      !arraysEqual(snapshotManifest.labels, release.labels)
    ) {
      entryErrors.push("snapshot labels do not match registry entry");
    }
    if (
      typeof snapshotManifest.modelSizeBytes === "number" &&
      isPositiveInteger(release.modelSizeBytes) &&
      snapshotManifest.modelSizeBytes !== release.modelSizeBytes
    ) {
      entryErrors.push("snapshot modelSizeBytes does not match registry entry");
    }
    if (typeof snapshotManifest.sha256 === "string" && isSha256(release.sha256)) {
      if (snapshotManifest.sha256.toLowerCase() !== release.sha256.toLowerCase()) {
        entryErrors.push("snapshot sha256 does not match registry entry");
      }
    }
  }

  errors.push(...entryErrors.map((message) => `release ${version || "(unknown)"}: ${message}`));
  releaseSummaries.push({
    version: version || null,
    isCurrent: version === currentVersion,
    snapshotPath: snapshotPath || null,
    modelPath: modelPath || null,
    snapshotExists,
    modelExists,
    modelSizeBytes: isPositiveInteger(release.modelSizeBytes) ? release.modelSizeBytes : null,
    actualModelSizeBytes,
    sha256: isSha256(release.sha256) ? release.sha256.toLowerCase() : null,
    actualSha256,
    integrityOk:
      modelExists &&
      isPositiveInteger(release.modelSizeBytes) &&
      isSha256(release.sha256) &&
      release.modelSizeBytes === actualModelSizeBytes &&
      release.sha256.toLowerCase() === actualSha256,
    ok: entryErrors.length === 0,
    errors: entryErrors,
  });
}

if (currentEntry && currentManifest.version !== currentVersion) {
  errors.push(
    `active manifest version ${String(currentManifest.version)} does not match registry currentVersion ${currentVersion}`
  );
}

const summary = {
  ok: errors.length === 0,
  registryPath: options.registryPath,
  manifestPath: options.manifestPath,
  currentVersion,
  releaseCount: releases.length,
  rollbackCandidateCount: rollbackCandidates.length,
  rollbackCandidates: rollbackCandidates
    .map((release) => (typeof release.version === "string" ? release.version : null))
    .filter(Boolean),
  releases: releaseSummaries,
  errors,
  warnings,
  nextSteps:
    errors.length === 0
      ? ["Release registry has a current version, verified model integrity, and at least one rollback candidate."]
      : ["Fix missing registry entries, snapshots, model files, or model integrity mismatches, then rerun audit-release-rollback.ts."],
};

if (options.outputPath) {
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
}

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) {
  process.exitCode = 1;
}