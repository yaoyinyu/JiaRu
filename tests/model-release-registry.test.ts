import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

function sha256Buffer(buffer: Buffer): string {
  return createHash("sha256").update(buffer).digest("hex");
}

async function createManifest(modelDir: string, version: string, sizeBytes = 1024) {
  const manifestPath = path.join(modelDir, "manifest.json");
  const modelFile = `${version}.onnx`;
  const modelBuffer = Buffer.alloc(sizeBytes);
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
  await writeFile(path.join(modelDir, modelFile), modelBuffer, "binary");
  return { manifestPath, modelFile, modelPath: path.join(modelDir, modelFile), sha256: sha256Buffer(modelBuffer), sizeBytes };
}

async function registerRelease(manifestPath: string, registryPath: string) {
  return execFileAsync(
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
}

test("register-model-release snapshots manifest and updates registry current version", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-registry-register-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const fixture = await createManifest(modelDir, "nail-texture-seg-v1");
  const registryPath = path.join(modelDir, "release-registry.json");

  const { stdout } = await registerRelease(fixture.manifestPath, registryPath);

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    currentVersion: string;
    snapshotPath: string;
    modelSizeBytes: number;
    sha256: string;
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.currentVersion, "nail-texture-seg-v1");
  assert.equal(summary.modelSizeBytes, fixture.sizeBytes);
  assert.equal(summary.sha256, fixture.sha256);

  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    currentVersion: string;
    releases: Array<{ version: string; manifestSnapshotPath: string; modelSizeBytes: number; sha256: string }>;
  };
  assert.equal(registry.currentVersion, "nail-texture-seg-v1");
  assert.equal(registry.releases.length, 1);
  assert.equal(registry.releases[0]?.manifestSnapshotPath, summary.snapshotPath);
  assert.equal(registry.releases[0]?.modelSizeBytes, fixture.sizeBytes);
  assert.equal(registry.releases[0]?.sha256, fixture.sha256);
});

test("switch-model-release restores an older manifest snapshot and updates current version", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-registry-switch-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");

  const v1 = await createManifest(modelDir, "nail-texture-seg-v1", 1024);
  await registerRelease(v1.manifestPath, registryPath);

  const v2 = await createManifest(modelDir, "nail-texture-seg-v2", 2048);
  await registerRelease(v2.manifestPath, registryPath);

  const { stdout } = await execFileAsync(
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
      v2.manifestPath,
    ],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as { ok: boolean; modelSizeBytes: number; sha256: string };
  assert.equal(summary.ok, true);
  assert.equal(summary.modelSizeBytes, v1.sizeBytes);
  assert.equal(summary.sha256, v1.sha256);

  const currentManifest = JSON.parse(await readFile(v2.manifestPath, "utf8")) as { version: string; modelFile: string };
  assert.equal(currentManifest.version, "nail-texture-seg-v1");
  assert.equal(currentManifest.modelFile, "nail-texture-seg-v1.onnx");

  const registry = JSON.parse(await readFile(registryPath, "utf8")) as { currentVersion: string };
  assert.equal(registry.currentVersion, "nail-texture-seg-v1");
});

test("switch-model-release rejects a target whose model file no longer matches registry integrity", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-registry-switch-corrupt-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");

  const v1 = await createManifest(modelDir, "nail-texture-seg-v1", 1024);
  await registerRelease(v1.manifestPath, registryPath);

  const v2 = await createManifest(modelDir, "nail-texture-seg-v2", 2048);
  await registerRelease(v2.manifestPath, registryPath);
  await writeFile(v1.modelPath, Buffer.from("corrupted-model"), "binary");

  await assert.rejects(
    execFileAsync(
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
        v2.manifestPath,
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stderr?: string }) => {
      assert.match(error.stderr ?? error.message, /model size mismatch|model sha256 mismatch/);
      return true;
    }
  );

  const currentManifest = JSON.parse(await readFile(v2.manifestPath, "utf8")) as { version: string };
  assert.equal(currentManifest.version, "nail-texture-seg-v2");
});