import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function writeManifest(modelDir: string, overrides: Record<string, unknown> = {}) {
  await writeFile(
    path.join(modelDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        scoreThreshold: 0.25,
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
        ...overrides,
      },
      null,
      2
    ),
    "utf8"
  );
}

test("verify-model-artifact validates manifest and model size", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeManifest(modelDir);
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const { stdout } = await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "scripts/verify-model-artifact.ts", path.join(modelDir, "manifest.json")],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    modelExists: boolean;
    modelSizeBytes: number;
    sizeTier: string;
    minModelKb: number;
    idealModelMb: number;
    maxModelMb: number;
    errors: string[];
    warnings: string[];
    scoreThreshold: number;
    nextSteps: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.modelExists, true);
  assert.equal(summary.modelSizeBytes, 300 * 1024);
  assert.equal(summary.sizeTier, "ideal");
  assert.equal(summary.minModelKb, 256);
  assert.equal(summary.idealModelMb, 8);
  assert.equal(summary.maxModelMb, 15);
  assert.deepEqual(summary.errors, []);
  assert.deepEqual(summary.warnings, []);
  assert.equal(summary.scoreThreshold, 0.25);
  assert.ok(summary.nextSteps.some((item) => item.includes("passes required MVP")));
});

test("verify-model-artifact rejects unsafe or incompatible manifest fields", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-invalid-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeManifest(modelDir, {
    backendPreferences: ["webgpu", "webnn"],
    modelFile: "nested/model.bin",
    labels: ["background", "nail_texture"],
    scoreThreshold: 1.2,
  });

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-model-artifact.ts",
        path.join(modelDir, "manifest.json"),
      ],
      {
        cwd: path.resolve("."),
      }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("unsupported backend")));
      assert.ok(summary.errors.some((item) => item.includes("file name in the manifest directory")));
      assert.ok(summary.errors.some((item) => item.includes(".onnx")));
      assert.ok(summary.errors.some((item) => item.includes("labels[0]")));
      assert.ok(summary.errors.some((item) => item.includes("scoreThreshold")));
      return true;
    }
  );
});

test("verify-model-artifact rejects tiny placeholder ONNX files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-placeholder-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeManifest(modelDir);
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-model-artifact.ts",
        path.join(modelDir, "manifest.json"),
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        sizeTier: string;
        errors: string[];
        nextSteps: string[];
      };
      assert.equal(summary.ok, false);
      assert.equal(summary.sizeTier, "placeholder");
      assert.ok(summary.errors.some((item) => item.includes("too small")));
      assert.ok(summary.nextSteps.some((item) => item.includes("real ONNX segmentation model")));
      return true;
    }
  );
});

test("verify-model-artifact warns when model passes MVP size but exceeds ideal target", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-size-warning-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeManifest(modelDir, {
    modelSizeBytes: 9 * 1024 * 1024,
    sha256: "d2ee4703cd9698945ca7b9fe1689ea3095597eac1a0afd8dba00cac7894fdc43",
  });
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(9 * 1024 * 1024), "binary");

  const { stdout } = await execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "scripts/verify-model-artifact.ts", path.join(modelDir, "manifest.json")],
    { cwd: path.resolve(".") }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    sizeTier: string;
    errors: string[];
    warnings: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.sizeTier, "mvp");
  assert.deepEqual(summary.errors, []);
  assert.ok(summary.warnings.some((item) => item.includes("above the ideal target")));
});
test("verify-model-artifact rejects manifest integrity mismatches", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-integrity-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeManifest(modelDir, {
    modelSizeBytes: 123,
    sha256: "0".repeat(64),
  });
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  await assert.rejects(
    execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-model-artifact.ts",
        path.join(modelDir, "manifest.json"),
        "--require-integrity",
      ],
      { cwd: path.resolve(".") }
    ),
    (error: Error & { stdout?: string }) => {
      const summary = JSON.parse(error.stdout ?? "{}") as {
        ok: boolean;
        errors: string[];
        computedSha256: string | null;
      };
      assert.equal(summary.ok, false);
      assert.ok(summary.errors.some((item) => item.includes("modelSizeBytes")));
      assert.ok(summary.errors.some((item) => item.includes("sha256 does not match")));
      assert.equal(summary.computedSha256, "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf");
      return true;
    }
  );
});
