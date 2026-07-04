import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const REFERENCE_IMAGE = path.resolve("model/5188.jpg_wh860.jpg");

test("verify-real-model-readiness runs artifact and fixture verification together", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-real-model-readiness-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const dumpPath = path.join(root, "nail-model-output-dump.json");
  await writeFile(
    dumpPath,
    JSON.stringify(
      {
        preprocess: {
          inputSize: 4,
          originalWidth: 80,
          originalHeight: 80,
          scaleX: 20,
          scaleY: 20,
        },
        rawModelOutputs: {
          boxes: {
            dims: [1, 1, 6],
            data: [2, 2, 0.5, 0.5, 0.9, 5],
          },
          proto: {
            dims: [1, 1, 2, 2],
            data: [1, -1, 1, -1],
          },
        },
        expect: {
          candidateCount: 1,
          requireMasks: true,
        },
      },
      null,
      2
    ),
    "utf8"
  );

  const fixtureOut = path.join(root, "fixture.json");
  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-real-model-readiness.ts",
      "--manifest",
      manifestPath,
      "--dump",
      dumpPath,
      "--fixture-out",
      fixtureOut,
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    manifestPath: string;
    dumpPath: string;
    fixturePath: string;
    artifact: { ok: boolean };
    fixtureVerify: { ok: boolean };
  };

  assert.equal(summary.ok, true);
  assert.equal(summary.manifestPath, manifestPath);
  assert.equal(summary.dumpPath, dumpPath);
  assert.equal(summary.fixturePath, fixtureOut);
  assert.equal(summary.artifact.ok, true);
  assert.equal(summary.fixtureVerify.ok, true);
});

test("verify-real-model-readiness reports missing model artifact as structured failure", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-real-model-missing-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );

  let stdout = "";
  try {
    await execFileAsync(
      process.execPath,
      [
        "--no-warnings",
        "--experimental-strip-types",
        "scripts/verify-real-model-readiness.ts",
        "--manifest",
        manifestPath,
      ],
      {
        cwd: path.resolve("."),
      }
    );
    assert.fail("expected readiness script to exit non-zero when model file is missing");
  } catch (error) {
    const execError = error as { stdout?: string };
    stdout = execError.stdout ?? "";
  }

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    artifact: { ok: boolean; errors: string[] };
    fixtureBuild: null;
    fixtureVerify: null;
    nextSteps: string[];
  };
  assert.equal(summary.ok, false);
  assert.equal(summary.artifact.ok, false);
  assert.match(summary.artifact.errors[0], /model file is missing/i);
  assert.equal(summary.fixtureBuild, null);
  assert.equal(summary.fixtureVerify, null);
  assert.ok(summary.nextSteps[0].includes("Fix the model artifact"));
});

test("verify-real-model-readiness can include single-image verification when artifact is present", async (t) => {
  if (!existsSync(REFERENCE_IMAGE)) {
    t.skip("reference image is not available");
    return;
  }

  const root = await mkdtemp(path.join(os.tmpdir(), "nail-real-model-image-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  const debugDir = path.join(root, "debug-output");
  await mkdir(modelDir, { recursive: true });
  await mkdir(debugDir, { recursive: true });

  const manifestPath = path.join(modelDir, "manifest.json");
  await writeFile(
    manifestPath,
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        modelSizeBytes: 307200,
        sha256: "7818f5542a0404157573be6cffc0e0c8e68ce3c0f5d17d07ccdd9313fb700baf",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(300 * 1024), "binary");

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-real-model-readiness.ts",
      "--manifest",
      manifestPath,
      "--image",
      REFERENCE_IMAGE,
      "--debug-output-dir",
      debugDir,
      "--debug-prefix",
      "readiness-run",
    ],
    {
      cwd: path.resolve("."),
    }
  );

  const summary = JSON.parse(stdout) as {
    ok: boolean;
    artifact: { ok: boolean };
    imageVerify: {
      count: number;
      debugJsonOutput: string;
    } | null;
    nextSteps: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.artifact.ok, true);
  assert.ok(summary.imageVerify);
  assert.ok((summary.imageVerify?.count ?? 0) >= 4);
  assert.match(summary.imageVerify?.debugJsonOutput ?? "", /readiness-run-5188\.jpg_wh860-detection-debug\.json$/);
  assert.ok(summary.nextSteps[0].includes("/ar-tryon"));
});
