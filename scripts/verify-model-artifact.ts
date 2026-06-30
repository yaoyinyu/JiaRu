import path from "node:path";
import process from "node:process";
import { access, readFile, stat } from "node:fs/promises";

interface ManifestLike {
  version: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  modelFile: string;
  labels: string[];
}

async function assertExists(filePath: string): Promise<void> {
  await access(filePath);
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-model-artifact.ts [manifest-path] [--max-model-mb 15]"
  );
}

const args = process.argv.slice(2);
let manifestPath = "public/models/nail-texture-seg/manifest.json";
let maxModelMb = 15;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--max-model-mb") {
    const value = Number(args[++index]);
    if (!Number.isFinite(value) || value <= 0) usage();
    maxModelMb = value;
    continue;
  }
  if (arg.startsWith("--")) usage();
  manifestPath = arg;
}

const absoluteManifestPath = path.resolve(manifestPath);
await assertExists(absoluteManifestPath);
const manifest = JSON.parse(
  await readFile(absoluteManifestPath, "utf8")
) as ManifestLike;

const errors: string[] = [];
if (!manifest.version) errors.push("manifest.version is required");
if (!Number.isFinite(manifest.inputSize) || manifest.inputSize <= 0) {
  errors.push("manifest.inputSize must be a positive number");
}
if (manifest.task !== "segment") errors.push("manifest.task must be 'segment'");
if (!Array.isArray(manifest.backendPreferences) || manifest.backendPreferences.length === 0) {
  errors.push("manifest.backendPreferences must be a non-empty array");
}
if (!manifest.modelFile) errors.push("manifest.modelFile is required");
if (!Array.isArray(manifest.labels) || manifest.labels.length === 0) {
  errors.push("manifest.labels must be a non-empty array");
}

const modelPath = path.resolve(path.dirname(absoluteManifestPath), manifest.modelFile ?? "");
let modelSizeBytes = 0;
let modelExists = false;
try {
  await assertExists(modelPath);
  modelExists = true;
  modelSizeBytes = (await stat(modelPath)).size;
} catch {
  errors.push(`model file is missing: ${modelPath}`);
}

const maxModelBytes = maxModelMb * 1024 * 1024;
if (modelExists && modelSizeBytes > maxModelBytes) {
  errors.push(
    `model file is too large: ${(modelSizeBytes / (1024 * 1024)).toFixed(2)}MB > ${maxModelMb}MB`
  );
}

const summary = {
  manifestPath: absoluteManifestPath,
  modelPath,
  version: manifest.version,
  inputSize: manifest.inputSize,
  task: manifest.task,
  backendPreferences: manifest.backendPreferences,
  labels: manifest.labels,
  modelExists,
  modelSizeBytes,
  modelSizeMb: Number((modelSizeBytes / (1024 * 1024)).toFixed(4)),
  maxModelMb,
  ok: errors.length === 0,
  errors,
};

console.log(JSON.stringify(summary, null, 2));
if (errors.length > 0) {
  process.exitCode = 1;
}
