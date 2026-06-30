import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("verify-model-artifact validates manifest and model size", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-artifact-"));
  const modelDir = path.join(root, "public", "models", "nail-texture-seg");
  await mkdir(modelDir, { recursive: true });

  await writeFile(
    path.join(modelDir, "manifest.json"),
    JSON.stringify(
      {
        version: "nail-texture-seg-v1",
        inputSize: 640,
        task: "segment",
        backendPreferences: ["webgpu", "wasm"],
        modelFile: "nail-texture-seg-v1.onnx",
        labels: ["nail_texture"],
      },
      null,
      2
    ),
    "utf8"
  );
  await writeFile(path.join(modelDir, "nail-texture-seg-v1.onnx"), Buffer.alloc(1024), "binary");

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
    errors: string[];
  };
  assert.equal(summary.ok, true);
  assert.equal(summary.modelExists, true);
  assert.equal(summary.modelSizeBytes, 1024);
  assert.deepEqual(summary.errors, []);
});
