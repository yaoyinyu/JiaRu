import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = "model/training/extend-source-isolated-dataset.py";

async function fixture(newSplit: "train" | "test" = "train") {
  const root = await mkdtemp(path.join(tmpdir(), "nail-source-extension-"));
  const base = path.join(root, "base");
  const images = path.join(root, "formal-images");
  const annotations = path.join(root, "formal-annotations");
  const output = path.join(root, "output");
  for (const split of ["train", "val", "test"]) {
    await mkdir(path.join(base, "images", split), { recursive: true });
    await mkdir(path.join(base, "labels", split), { recursive: true });
    await writeFile(path.join(base, "images", split, `${split}.png`), `image-${split}`);
    await writeFile(path.join(base, "labels", split, `${split}.txt`), "0 0.1 0.1 0.9 0.1 0.9 0.9\n");
  }
  await writeFile(path.join(base, "dataset.yaml"), "path: old\n");
  await writeFile(path.join(base, "source-isolated-report.json"), JSON.stringify({
    ok: true,
    splitCounts: { train: 1, val: 1, test: 1 },
    maskCounts: { train: 1, val: 1, test: 1 },
  }));
  await mkdir(images, { recursive: true });
  await mkdir(annotations, { recursive: true });
  await writeFile(path.join(images, "new.png"), "new-image");
  await writeFile(path.join(annotations, "new.json"), JSON.stringify({
    version: "nail-texture-dataset/v1",
    image: { fileName: "new.png", width: 100, height: 80, sourceGroup: "parent:new" },
    annotations: [{ label: "nail_texture", polygon: [{ x: 10, y: 10 }, { x: 90, y: 10 }, { x: 80, y: 70 }] }],
  }));
  const splitJson = path.join(root, "split.json");
  await writeFile(splitJson, JSON.stringify({ train: newSplit === "train" ? ["new.png"] : [], val: [], test: newSplit === "test" ? ["new.png"] : [] }));
  const manifest = path.join(root, "manifest.json");
  await writeFile(manifest, JSON.stringify({
    version: "nail-texture-intake-batch/v1",
    license: "user-authorized-commercial-training-and-long-term-regression",
    items: [{ fileName: "new.png", sourceGroup: "parent:new" }],
  }));
  return { base, images, annotations, output, splitJson, manifest };
}

function run(paths: Awaited<ReturnType<typeof fixture>>) {
  return spawnSync("python", [
    script,
    "--base-dir", paths.base,
    "--dataset-images", paths.images,
    "--dataset-annotations", paths.annotations,
    "--split-json", paths.splitJson,
    "--intake-manifest", paths.manifest,
    "--output-dir", paths.output,
  ], { encoding: "utf8" });
}

test("extends train data while preserving the frozen test byte-for-byte", async () => {
  const paths = await fixture();
  const result = run(paths);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(path.join(paths.output, "source-isolated-extension-report.json"), "utf8"));
  assert.deepEqual(report.result.splitCounts, { train: 2, val: 1, test: 1 });
  assert.deepEqual(report.result.maskCounts, { train: 2, val: 1, test: 1 });
  assert.equal(report.frozenTest.imageCount, 1);
  assert.equal(report.invariants.testHashUnchanged, true);
  assert.equal(await readFile(path.join(paths.output, "images", "test", "test.png"), "utf8"), "image-test");
  assert.match(await readFile(path.join(paths.output, "dataset.yaml"), "utf8"), /output/);
});

test("rejects every new item assigned to the frozen test split", async () => {
  const paths = await fixture("test");
  const result = run(paths);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /cannot enter the frozen test split/);
});
