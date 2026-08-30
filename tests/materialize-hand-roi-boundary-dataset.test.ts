import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("hand ROI materializer preserves every polygon and leaves val/test unchanged", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-hand-roi-"));
  const input = path.join(root, "input");
  const output = path.join(root, "output");
  for (const split of ["train", "val", "test"]) {
    await mkdir(path.join(input, "images", split), { recursive: true });
    await mkdir(path.join(input, "labels", split), { recursive: true });
  }
  await mkdir(path.join(input, "metadata"), { recursive: true });
  const makeImage = [
    "from PIL import Image",
    "import sys",
    "Image.new('RGB', (100, 100), (220, 180, 160)).save(sys.argv[1])",
  ].join("; ");
  await execFileAsync("python", ["-c", makeImage, path.join(input, "images", "train", "positive.jpg")]);
  await execFileAsync("python", ["-c", makeImage, path.join(input, "images", "train", "negative.jpg")]);
  await execFileAsync("python", ["-c", makeImage, path.join(input, "images", "val", "validation.jpg")]);
  await writeFile(
    path.join(input, "labels", "train", "positive.txt"),
    "0 0.30 0.30 0.70 0.30 0.70 0.70 0.30 0.70\n",
    "utf8",
  );
  await writeFile(path.join(input, "labels", "train", "negative.txt"), "", "utf8");
  await writeFile(
    path.join(input, "labels", "val", "validation.txt"),
    "0 0.20 0.20 0.40 0.20 0.40 0.40 0.20 0.40\n",
    "utf8",
  );
  await writeFile(
    path.join(input, "dataset.yaml"),
    [
      "path: .",
      "train: images/train",
      "val: images/val",
      "test: images/test",
      "",
      "names:",
      "  0: nail_texture",
      "",
      "task: segment",
      "class_count: 1",
      "image_size: 640",
      "",
      "metadata:",
      "  dataset_version: canonical-candidate-training-dataset/v1",
      "",
    ].join("\n"),
    "utf8",
  );
  const audit = path.join(root, "input-audit.json");
  await writeFile(
    audit,
    JSON.stringify({
      decision: "approved_candidate_training_input",
      outputDir: path.resolve(input),
      datasetFilesSha256: "0".repeat(64),
    }),
    "utf8",
  );

  const { stdout } = await execFileAsync(
    "python",
    [
      "model/training/materialize-hand-roi-boundary-dataset.py",
      "--input-dataset", input,
      "--input-audit", audit,
      "--output-dir", output,
      "--padding-ratio", "0.2",
      "--maximum-crop-area-ratio", "0.85",
      "--minimum-polygon-margin", "2",
    ],
    { cwd: path.resolve(".") },
  );
  const summary = JSON.parse(stdout) as { created: number; skipped: number };
  assert.deepEqual(summary, { output: path.resolve(output), created: 1, skipped: 1 });
  const report = JSON.parse(
    await readFile(path.join(output, "candidate30-hand-roi-materialization-v1.json"), "utf8"),
  ) as {
    decision: string;
    counts: { parentTrainImages: number; createdRoiImages: number; outputTrainImages: number; validationImages: number; testImages: number };
  };
  assert.equal(report.decision, "candidate_hand_roi_dataset_materialized_pending_independent_audit");
  assert.deepEqual(report.counts, {
    parentTrainImages: 2,
    createdRoiImages: 1,
    skippedTrainImages: 1,
    selectionSkippedTrainImages: 0,
    geometrySkippedTrainImages: 1,
    outputTrainImages: 3,
    validationImages: 1,
    testImages: 0,
  });
  const roiLabel = (await readFile(path.join(output, "labels", "train", "positive__handroi_v1.txt"), "utf8")).trim();
  const values = roiLabel.split(/\s+/).slice(1).map(Number);
  assert.equal(values.length, 8);
  assert.ok(values.every((value) => value > 0 && value < 1));
  assert.equal(await readFile(path.join(output, "labels", "train", "positive.txt"), "utf8"), "0 0.30 0.30 0.70 0.30 0.70 0.70 0.30 0.70\n");
  assert.equal(await readFile(path.join(output, "labels", "val", "validation.txt"), "utf8"), "0 0.20 0.20 0.40 0.20 0.40 0.40 0.20 0.40\n");
  assert.match(await readFile(path.join(output, "dataset.yaml"), "utf8"), /canonical-hand-roi-candidate-training-dataset\/v1/);
});
