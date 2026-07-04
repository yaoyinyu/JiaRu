import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

async function runMaterialize(datasetRoot: string) {
  return execFileAsync(
    process.execPath,
    ["--no-warnings", "--experimental-strip-types", "model/training/materialize-training-dataset.ts"],
    { cwd: path.resolve("."), env: { ...process.env, DATASET_ROOT: datasetRoot } }
  );
}

test("materialize-training-dataset creates Ultralytics image and label splits", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-materialize-training-"));
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });
  for (const subset of ["train", "val", "test"]) {
    await mkdir(path.join(datasetRoot, "labels-yolo-seg", subset), { recursive: true });
  }

  const split = {
    train: ["train.jpg"],
    val: ["val.png"],
    test: ["negative.webp"],
  };
  await writeFile(path.join(datasetRoot, "metadata", "split.json"), JSON.stringify(split), "utf8");
  for (const fileName of [...split.train, ...split.val, ...split.test]) {
    await writeFile(path.join(datasetRoot, "images", "raw", fileName), `image:${fileName}`, "utf8");
  }
  await writeFile(path.join(datasetRoot, "labels-yolo-seg", "train", "train.txt"), "0 0.1 0.1 0.2 0.2", "utf8");
  await writeFile(path.join(datasetRoot, "labels-yolo-seg", "val", "val.txt"), "0 0.2 0.2 0.3 0.3", "utf8");
  await writeFile(path.join(datasetRoot, "labels-yolo-seg", "test", "negative.txt"), "", "utf8");

  const { stdout } = await runMaterialize(datasetRoot);
  const report = JSON.parse(stdout) as { ok: boolean; copiedImages: number; copiedLabels: number };
  assert.equal(report.ok, true);
  assert.equal(report.copiedImages, 3);
  assert.equal(report.copiedLabels, 3);
  assert.equal(await readFile(path.join(datasetRoot, "images", "val", "val.png"), "utf8"), "image:val.png");
  assert.equal(await readFile(path.join(datasetRoot, "labels", "train", "train.txt"), "utf8"), "0 0.1 0.1 0.2 0.2");
  assert.equal(await readFile(path.join(datasetRoot, "labels", "test", "negative.txt"), "utf8"), "");
});

test("materialize-training-dataset fails before replacing outputs when an input is missing", async () => {
  const datasetRoot = await mkdtemp(path.join(os.tmpdir(), "nail-materialize-missing-"));
  await mkdir(path.join(datasetRoot, "images", "raw"), { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });
  await mkdir(path.join(datasetRoot, "labels-yolo-seg", "train"), { recursive: true });
  await mkdir(path.join(datasetRoot, "images", "train"), { recursive: true });
  await writeFile(
    path.join(datasetRoot, "metadata", "split.json"),
    JSON.stringify({ train: ["missing.jpg"], val: [], test: [] }),
    "utf8"
  );
  await writeFile(path.join(datasetRoot, "images", "train", "sentinel.txt"), "keep", "utf8");

  await assert.rejects(runMaterialize(datasetRoot), /missing raw image/);
  assert.equal(await readFile(path.join(datasetRoot, "images", "train", "sentinel.txt"), "utf8"), "keep");
});
