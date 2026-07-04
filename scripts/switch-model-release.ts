import { createHash } from "node:crypto";
import path from "node:path";
import process from "node:process";
import { access, copyFile, readFile, stat, writeFile } from "node:fs/promises";

interface ReleaseRegistryEntry {
  version: string;
  manifestSnapshotPath: string;
  modelFile: string;
  modelPath: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  labels: string[];
  modelSizeBytes: number;
  modelSizeMb: number;
  sha256: string;
  registeredAt: string;
}

interface ReleaseRegistry {
  currentVersion: string | null;
  releases: ReleaseRegistryEntry[];
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/switch-model-release.ts --version <version> [--registry <registry.json>] [--manifest <manifest.json>]"
  );
}

async function hashFileSha256(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function assertIntegrityMetadata(entry: ReleaseRegistryEntry): void {
  if (!Number.isInteger(entry.modelSizeBytes) || entry.modelSizeBytes <= 0) {
    throw new Error(`release ${entry.version} is missing positive modelSizeBytes`);
  }
  if (!/^[a-f0-9]{64}$/i.test(entry.sha256)) {
    throw new Error(`release ${entry.version} is missing a valid sha256`);
  }
}

const args = process.argv.slice(2);
let version = "";
let registryPath = path.resolve("public/models/nail-texture-seg/release-registry.json");
let manifestPath = path.resolve("public/models/nail-texture-seg/manifest.json");

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--version") version = args[++index] ?? usage();
  else if (arg === "--registry") registryPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--manifest") manifestPath = path.resolve(args[++index] ?? usage());
  else usage();
}

if (!version) usage();

const registry = JSON.parse(await readFile(registryPath, "utf8")) as ReleaseRegistry;
const entry = registry.releases.find((item) => item.version === version);
if (!entry) {
  throw new Error(`version not found in registry: ${version}`);
}

assertIntegrityMetadata(entry);
await access(entry.manifestSnapshotPath);
await access(entry.modelPath);

const actualModelSizeBytes = (await stat(entry.modelPath)).size;
const actualSha256 = await hashFileSha256(entry.modelPath);
if (actualModelSizeBytes !== entry.modelSizeBytes) {
  throw new Error(
    `release ${version} model size mismatch: registry=${entry.modelSizeBytes}, actual=${actualModelSizeBytes}`
  );
}
if (actualSha256 !== entry.sha256.toLowerCase()) {
  throw new Error(`release ${version} model sha256 mismatch: registry=${entry.sha256}, actual=${actualSha256}`);
}

await copyFile(entry.manifestSnapshotPath, manifestPath);

const nextRegistry: ReleaseRegistry = {
  currentVersion: version,
  releases: registry.releases,
};

await writeFile(registryPath, JSON.stringify(nextRegistry, null, 2), "utf8");

console.log(
  JSON.stringify(
    {
      ok: true,
      registryPath,
      manifestPath,
      currentVersion: version,
      modelPath: entry.modelPath,
      snapshotPath: entry.manifestSnapshotPath,
      modelSizeBytes: entry.modelSizeBytes,
      sha256: entry.sha256.toLowerCase(),
    },
    null,
    2
  )
);