import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function createManifest(modelDir: string, version: string, sizeBytes = 1024) {
  const manifestPath = path.join(modelDir, "manifest.json");
  const modelFile = `${version}.onnx`;
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version,
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile,
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, modelFile), Buffer.alloc(sizeBytes), "binary");
  return manifestPath;
}

test("register-model-release snapshots manifest and updates registry current version", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-registry-register-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const manifestPath = await createManifest(modelDir, "nail-texture-seg-v1");
  const registryPath = path.join(modelDir, "release-registry.json");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-model-release.ts",
      "--manifest",
      manifestPath,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as { ok: boolean; currentVersion: string; snapshotPath: string };
  assert.equal(summary.ok, true);
  assert.equal(summary.currentVersion, "nail-texture-seg-v1");
  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    currentVersion: string;
    releases: Array<{ version: string; manifestSnapshotPath: string }>;
  };
  assert.equal(registry.currentVersion, "nail-texture-seg-v1");
  assert.equal(registry.releases.length, 1);
  assert.equal(registry.releases[0]?.manifestSnapshotPath, summary.snapshotPath);
});

test("switch-model-release restores an older manifest snapshot and updates current version", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-registry-switch-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");

  const manifestV1 = await createManifest(modelDir, "nail-texture-seg-v1", 1024);
  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-model-release.ts",
      "--manifest",
      manifestV1,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  const manifestV2 = await createManifest(modelDir, "nail-texture-seg-v2", 2048);
  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/register-model-release.ts",
      "--manifest",
      manifestV2,
      "--registry",
      registryPath,
    ],
    { cwd: path.resolve(".") }
  );

  await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/switch-model-release.ts",
      "--version",
      "nail-texture-seg-v1",
      "--registry",
      registryPath,
      "--manifest",
      manifestV2,
    ],
    { cwd: path.resolve(".") }
  );

  const currentManifest = JSON.parse(await readFile(manifestV2, "utf8")) as { version: string; modelFile: string };
  assert.equal(currentManifest.version, "nail-texture-seg-v1");
  assert.equal(currentManifest.modelFile, "nail-texture-seg-v1.onnx");

  const registry = JSON.parse(await readFile(registryPath, "utf8")) as { currentVersion: string };
  assert.equal(registry.currentVersion, "nail-texture-seg-v1");
});
