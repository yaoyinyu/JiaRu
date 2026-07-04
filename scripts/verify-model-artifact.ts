import { createHash } from "node:crypto";
import path from "node:path";
import process from "node:process";
import { access, readFile, stat } from "node:fs/promises";

interface ManifestLike {
  version: string;
  inputSize: number;
  task: string;
  backendPreferences: string[];
  modelFile: string;
  modelSizeBytes?: number;
  sha256?: string;
  labels: string[];
}

const allowedBackends = new Set(["webgpu", "wasm"]);

async function assertExists(filePath: string): Promise<void> {
  await access(filePath);
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-model-artifact.ts [manifest-path] [--max-model-mb 15] [--ideal-model-mb 8] [--min-model-kb 256] [--require-integrity]"
  );
}

function isBaseFileName(fileName: string): boolean {
  return Boolean(fileName) && path.basename(fileName) === fileName && !/[\\/]/.test(fileName);
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/i.test(value);
}

async function hashFileSha256(filePath: string): Promise<string> {
  const buffer = await readFile(filePath);
  return createHash("sha256").update(buffer).digest("hex");
}

const args = process.argv.slice(2);
let manifestPath = "public/models/nail-texture-seg/manifest.json";
let maxModelMb = 15;
let idealModelMb = 8;
let minModelKb = 256;
let requireIntegrity = false;

for (let index = 0; index < args.length; index++) {
  const arg = args[index];
  if (arg === "--max-model-mb") {
    const value = Number(args[++index]);
    if (!Number.isFinite(value) || value <= 0) usage();
    maxModelMb = value;
    continue;
  }
  if (arg === "--ideal-model-mb") {
    const value = Number(args[++index]);
    if (!Number.isFinite(value) || value <= 0) usage();
    idealModelMb = value;
    continue;
  }
  if (arg === "--min-model-kb") {
    const value = Number(args[++index]);
    if (!Number.isFinite(value) || value <= 0) usage();
    minModelKb = value;
    continue;
  }
  if (arg === "--require-integrity") {
    requireIntegrity = true;
    continue;
  }
  if (arg.startsWith("--")) usage();
  manifestPath = arg;
}

const absoluteManifestPath = path.resolve(manifestPath);
await assertExists(absoluteManifestPath);
const manifest = JSON.parse(await readFile(absoluteManifestPath, "utf8")) as ManifestLike;

const errors: string[] = [];
const warnings: string[] = [];
if (!manifest.version) errors.push("manifest.version is required");
if (!Number.isFinite(manifest.inputSize) || manifest.inputSize <= 0) {
  errors.push("manifest.inputSize must be a positive number");
}
if (manifest.task !== "segment") errors.push("manifest.task must be 'segment'");
if (!Array.isArray(manifest.backendPreferences) || manifest.backendPreferences.length === 0) {
  errors.push("manifest.backendPreferences must be a non-empty array");
} else {
  const invalidBackends = manifest.backendPreferences.filter((backend) => !allowedBackends.has(backend));
  if (invalidBackends.length > 0) {
    errors.push(`manifest.backendPreferences contains unsupported backend(s): ${invalidBackends.join(", ")}`);
  }
}
if (!manifest.modelFile) {
  errors.push("manifest.modelFile is required");
} else {
  if (!isBaseFileName(manifest.modelFile)) {
    errors.push("manifest.modelFile must be a file name in the manifest directory, not a nested or absolute path");
  }
  if (path.extname(manifest.modelFile).toLowerCase() !== ".onnx") {
    errors.push("manifest.modelFile must point to an .onnx file");
  }
}
if (!Array.isArray(manifest.labels) || manifest.labels.length === 0) {
  errors.push("manifest.labels must be a non-empty array");
} else {
  if (!manifest.labels.includes("nail_texture")) {
    errors.push("manifest.labels must include nail_texture");
  }
  if (manifest.labels[0] !== "nail_texture") {
    errors.push("manifest.labels[0] must be nail_texture for class-index compatibility");
  }
}

const modelPath = path.resolve(path.dirname(absoluteManifestPath), manifest.modelFile ?? "");
let modelSizeBytes = 0;
let modelExists = false;
let computedSha256: string | null = null;
try {
  if (manifest.modelFile && isBaseFileName(manifest.modelFile)) {
    await assertExists(modelPath);
    modelExists = true;
    modelSizeBytes = (await stat(modelPath)).size;
  } else {
    errors.push(`model file is missing or unsafe to resolve: ${modelPath}`);
  }
} catch {
  errors.push(`model file is missing: ${modelPath}`);
}

const manifestSha256 = manifest.sha256 ?? null;
const manifestModelSizeBytes = manifest.modelSizeBytes ?? null;
if (requireIntegrity && !isSha256(manifestSha256)) {
  errors.push("manifest.sha256 is required for release integrity verification");
}
if (manifestSha256 != null && !isSha256(manifestSha256)) {
  errors.push("manifest.sha256 must be a 64-character hex SHA-256 digest");
}
if (manifestModelSizeBytes != null && (!Number.isInteger(manifestModelSizeBytes) || manifestModelSizeBytes <= 0)) {
  errors.push("manifest.modelSizeBytes must be a positive integer when present");
}
if (modelExists) {
  if (manifestModelSizeBytes != null && manifestModelSizeBytes !== modelSizeBytes) {
    errors.push(`manifest.modelSizeBytes ${manifestModelSizeBytes} does not match actual model size ${modelSizeBytes}`);
  }
  if (isSha256(manifestSha256)) {
    computedSha256 = await hashFileSha256(modelPath);
    if (computedSha256.toLowerCase() !== manifestSha256.toLowerCase()) {
      errors.push("manifest.sha256 does not match the referenced model file");
    }
  } else if (!requireIntegrity) {
    warnings.push("manifest.sha256 is missing; release verification should require integrity metadata.");
  }
}

const maxModelBytes = maxModelMb * 1024 * 1024;
const idealModelBytes = idealModelMb * 1024 * 1024;
const minModelBytes = minModelKb * 1024;

if (modelExists && modelSizeBytes > maxModelBytes) {
  errors.push(`model file is too large: ${(modelSizeBytes / (1024 * 1024)).toFixed(2)}MB > ${maxModelMb}MB`);
}
if (modelExists && modelSizeBytes < minModelBytes) {
  errors.push(
    `model file is too small to be a credible exported segmentation model: ${modelSizeBytes} bytes < ${minModelKb}KB`
  );
}

if (modelExists && modelSizeBytes > idealModelBytes && modelSizeBytes <= maxModelBytes) {
  warnings.push(
    `model file passes the MVP size gate but is above the ideal target: ${(modelSizeBytes / (1024 * 1024)).toFixed(2)}MB > ${idealModelMb}MB`
  );
}

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
  manifestModelSizeBytes,
  modelSizeMb: Number((modelSizeBytes / (1024 * 1024)).toFixed(4)),
  sizeTier,
  minModelKb,
  idealModelMb,
  maxModelMb,
  sha256: manifestSha256,
  computedSha256,
  integrityRequired: requireIntegrity,
  integrityOk:
    modelExists && isSha256(manifestSha256) && computedSha256?.toLowerCase() === manifestSha256.toLowerCase(),
  ok: errors.length === 0,
  errors,
  warnings,
  nextSteps:
    errors.length === 0
      ? warnings.length > 0
        ? ["Model artifact passes required gates; resolve warnings before release if this is a promotion candidate."]
        : ["Model artifact passes required MVP size, integrity, and manifest gates."]
      : [
          "Export a real ONNX segmentation model referenced by the manifest.",
          "Keep the release model under 15MB, with an ideal target under 8MB.",
          "Ensure manifest.sha256 and manifest.modelSizeBytes are generated from the exported ONNX file.",
          "Rerun browser integration and real-model readiness checks after replacing the artifact.",
        ],
};

console.log(JSON.stringify(summary, null, 2));
if (errors.length > 0) {
  process.exitCode = 1;
}