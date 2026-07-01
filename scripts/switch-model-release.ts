import path from "node:path";
import process from "node:process";
import { access, copyFile, readFile, writeFile } from "node:fs/promises";

interface ReleaseRegistryEntry {
  version: string;
  manifestSnapshotPath: string;
  modelFile: string;
  modelPath: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  labels: string[];
  modelSizeMb: number;
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

await access(entry.manifestSnapshotPath);
await access(entry.modelPath);
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
    },
    null,
    2
  )
);
