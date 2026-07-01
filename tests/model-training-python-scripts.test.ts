import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function runPython(script: string, args: string[] = []) {
  const { stdout } = await execFileAsync(
    "python",
    [script, ...args],
    {
      cwd: path.resolve("."),
    }
  );
  return JSON.parse(stdout) as Record<string, unknown>;
}

test("dataset yaml exists and contains expected paths", async () => {
  const fs = await import("node:fs/promises");
  const yaml = await fs.readFile("model/training/dataset.yaml", "utf8");
  assert.match(yaml, /^path: \.\.\/datasets\/nail-texture-v1/m);
  assert.match(yaml, /^train: images\/train/m);
  assert.match(yaml, /^val: images\/val/m);
  assert.match(yaml, /^test: images\/test/m);
});

test("train script dry-run resolves dataset and hyperparameters", async () => {
  const result = await runPython("model/training/train-yolo-seg.py", ["--dry-run"]);
  assert.equal(result.task, "segment");
  assert.equal(result.class_count, 1);
  assert.equal(result.imgsz, 640);
  assert.match(String(result.best_weights_path), /model[\\/]+exports[\\/]+nail-texture-seg-v1[\\/]+nail-texture-seg-v1[\\/]+weights[\\/]+best\.pt$/);
  assert.equal(result.dry_run, true);
});

test("evaluate script dry-run prints resolved config", async () => {
  const result = await runPython("model/training/evaluate.py", ["--dry-run"]);
  assert.equal(result.split, "test");
  assert.equal(result.imgsz, 640);
  assert.match(String(result.weights), /model[\\/]+exports[\\/]+nail-texture-seg-v1[\\/]+nail-texture-seg-v1[\\/]+weights[\\/]+best\.pt$/);
  assert.equal(result.dry_run, true);
});

test("export onnx script dry-run prints manifest target", async () => {
  const result = await runPython("model/training/export-onnx.py", ["--dry-run"]);
  assert.equal(result.model_version, "nail-texture-seg-v1");
  assert.equal(result.input_size, 640);
  assert.deepEqual(result.backend_preferences, ["webgpu", "wasm"]);
  assert.deepEqual(result.labels, ["nail_texture"]);
  assert.equal(result.dry_run, true);
  assert.match(String(result.manifest_path), /public[\\/]+models[\\/]+nail-texture-seg[\\/]+manifest\.json$/);
});
