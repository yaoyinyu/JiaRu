import path from "node:path";
import process from "node:process";
import { copyFile, mkdir, readFile, stat, writeFile } from "node:fs/promises";

interface ManifestLike {
  version: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  modelFile: string;
  labels: string[];
}

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
    "Usage: node --experimental-strip-types scripts/register-model-release.ts [--manifest <manifest.json>] [--registry <registry.json>] [--set-current true|false]"
  );
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  usage();
}

const args = process.argv.slice(2);
let manifestPath = path.resolve("public/models/nail-texture-seg/manifest.json");
let registryPath = path.resolve("public/models/nail-texture-seg/release-registry.json");
let setCurrent = true;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--manifest") manifestPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--registry") registryPath = path.resolve(args[++index] ?? usage());
  else if (arg === "--set-current") setCurrent = parseBoolean(args[++index] ?? usage());
  else usage();
}

async function readRegistry(filePath: string): Promise<ReleaseRegistry> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as ReleaseRegistry;
  } catch {
    return { currentVersion: null, releases: [] };
  }
}

const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as ManifestLike;
const manifestDir = path.dirname(manifestPath);
const modelPath = path.resolve(manifestDir, manifest.modelFile);
const modelStats = await stat(modelPath);
const registry = await readRegistry(registryPath);
const snapshotPath = path.join(manifestDir, `manifest.${manifest.version}.json`);

await mkdir(path.dirname(registryPath), { recursive: true });
await copyFile(manifestPath, snapshotPath);

const entry: ReleaseRegistryEntry = {
  version: manifest.version,
  manifestSnapshotPath: snapshotPath,
  modelFile: manifest.modelFile,
  modelPath,
  inputSize: manifest.inputSize,
  task: manifest.task,
  backendPreferences: manifest.backendPreferences,
  labels: manifest.labels,
  modelSizeMb: Number((modelStats.size / (1024 * 1024)).toFixed(4)),
  registeredAt: new Date().toISOString(),
};

const releases = registry.releases.filter((item) => item.version !== entry.version);
releases.push(entry);
releases.sort((a, b) => a.version.localeCompare(b.version));

const nextRegistry: ReleaseRegistry = {
  currentVersion: setCurrent ? entry.version : registry.currentVersion,
  releases,
};

await writeFile(registryPath, JSON.stringify(nextRegistry, null, 2), "utf8");

console.log(
  JSON.stringify(
    {
      ok: true,
      manifestPath,
      registryPath,
      snapshotPath,
      currentVersion: nextRegistry.currentVersion,
      releaseCount: nextRegistry.releases.length,
      registeredVersion: entry.version,
    },
    null,
    2
  )
);
