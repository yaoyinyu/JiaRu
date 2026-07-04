import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, unlink, writeFile } from "node:fs/promises";
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
        modelSizeBytes: sizeBytes,
        sha256: sha256Buffer(modelBuffer),
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, modelFile), modelBuffer, "binary");
  return { manifestPath, modelPath: path.join(modelDir, modelFile) };
}

async function registerRelease(manifestPath: string, registryPath: string) {
  await execFileAsync(
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

async function runAudit(registryPath: string, manifestPath: string, outputPath?: string) {
  const args = [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/audit-release-rollback.ts",
    "--registry",
    registryPath,
    "--manifest",
    manifestPath,
  ];
  if (outputPath) args.push("--output", outputPath);

  return execFileAsync(process.execPath, args, { cwd: path.resolve(".") });
}

test("audit-release-rollback passes when current and rollback releases are complete", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-pass-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const outputPath = path.join(root, "rollback-audit.json");

  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  const { stdout } = await runAudit(registryPath, activeManifestPath, outputPath);
  const summary = JSON.parse(stdout) as {
    ok: boolean;
    currentVersion: string;
    releaseCount: number;
    rollbackCandidateCount: number;
    rollbackCandidates: string[];
    errors: string[];
    releases: Array<{ integrityOk: boolean; modelSizeBytes: number; actualModelSizeBytes: number; sha256: string; actualSha256: string }>;
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.currentVersion, "nail-texture-seg-v2");
  assert.equal(summary.releaseCount, 2);
  assert.equal(summary.rollbackCandidateCount, 1);
  assert.deepEqual(summary.rollbackCandidates, ["nail-texture-seg-v1"]);
  assert.deepEqual(summary.errors, []);
  assert.equal(summary.releases.length, 2);
  for (const release of summary.releases) {
    assert.equal(release.integrityOk, true);
    assert.equal(release.modelSizeBytes, release.actualModelSizeBytes);
    assert.equal(release.sha256, release.actualSha256);
  }

  const persisted = JSON.parse(await readFile(outputPath, "utf8")) as { ok: boolean };
  assert.equal(persisted.ok, true);
});

test("audit-release-rollback fails when no rollback candidate exists", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-single-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const manifestPath = (await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath;
  await registerRelease(manifestPath, registryPath);

  await assert.rejects(
    runAudit(registryPath, manifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        rollbackCandidateCount: number;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.rollbackCandidateCount, 0);
      assert.ok(summary.errors.some((item) => item.includes("at least one non-current release")));
      return true;
    }
  );
});

test("audit-release-rollback fails when a snapshot or model file is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-missing-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  await registerRelease((await createManifest(modelDir, "nail-texture-seg-v1")).manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  const registry = JSON.parse(await readFile(registryPath, "utf8")) as {
    releases: Array<{ version: string; manifestSnapshotPath: string; modelPath: string }>;
  };
  const oldRelease = registry.releases.find((release) => release.version === "nail-texture-seg-v1");
  assert.ok(oldRelease);
  await unlink(oldRelease.modelPath);

  await assert.rejects(
    runAudit(registryPath, activeManifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("model file is missing")));
      return true;
    }
  );
});

test("audit-release-rollback fails when a registered model file is modified after release", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-release-rollback-corrupt-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });
  const registryPath = path.join(modelDir, "release-registry.json");
  const v1 = await createManifest(modelDir, "nail-texture-seg-v1", 1024);
  await registerRelease(v1.manifestPath, registryPath);
  const activeManifestPath = (await createManifest(modelDir, "nail-texture-seg-v2", 2048)).manifestPath;
  await registerRelease(activeManifestPath, registryPath);

  await writeFile(v1.modelPath, Buffer.from("corrupted-model"), "binary");

  await assert.rejects(
    runAudit(registryPath, activeManifestPath),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        releases: Array<{ version: string; integrityOk: boolean }>;
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("modelSizeBytes") || item.includes("sha256")));
      assert.equal(summary.releases.find((release) => release.version === "nail-texture-seg-v1")?.integrityOk, false);
      return true;
    }
  );
});