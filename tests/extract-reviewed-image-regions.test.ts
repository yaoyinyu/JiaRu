import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const script = path.resolve("model/training/extract-reviewed-image-regions.py");

function python(...args: string[]) {
  return spawnSync("python", args, { encoding: "utf8" });
}

test("reviewed region extraction preserves parent provenance and deterministic split group", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-region-extract-"));
  const images = path.join(root, "images");
  const output = path.join(root, "output");
  const manifest = path.join(root, "manifest.json");
  const report = path.join(root, "report.json");
  await mkdir(images);
  const imagePath = path.join(images, "sample.jpg");
  const create = python(
    "-c",
    "from PIL import Image; Image.new('RGB', (400, 300), (210, 170, 140)).save(r'" +
      imagePath.replaceAll("'", "''") +
      "')",
  );
  assert.equal(create.status, 0, create.stderr);
  await writeFile(
    manifest,
    JSON.stringify({
      version: "nail-texture-region-extraction/v1",
      sourceGroupPrefix: "reviewed-crops",
      regions: [
        { parentFileName: "sample.jpg", regionId: "main-photo", box: [0.1, 0.2, 0.9, 0.8] },
      ],
    }),
  );

  const result = python(
    script,
    "--manifest",
    manifest,
    "--image-dir",
    images,
    "--output-dir",
    output,
    "--report",
    report,
    "--min-side",
    "100",
  );
  assert.equal(result.status, 0, result.stderr);
  const summary = JSON.parse(await readFile(report, "utf8"));
  assert.equal(summary.ok, true);
  assert.equal(summary.completedCount, 1);
  assert.deepEqual(summary.outputs[0].pixelBox, [40, 60, 360, 240]);
  assert.deepEqual(summary.outputs[0].outputSize, { width: 320, height: 180 });
  assert.match(summary.outputs[0].sourceGroup, /^reviewed-crops:parent-[a-f0-9]{12}$/);
  assert.equal(summary.outputs[0].reviewRequired, true);
  assert.match(summary.outputs[0].parentSha256, /^[a-f0-9]{64}$/);
  assert.match(summary.outputs[0].outputSha256, /^[a-f0-9]{64}$/);
});

test("reviewed region extraction rejects unsafe boxes without silently accepting the batch", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-region-invalid-"));
  const images = path.join(root, "images");
  const output = path.join(root, "output");
  const manifest = path.join(root, "manifest.json");
  const report = path.join(root, "report.json");
  await mkdir(images);
  await writeFile(
    manifest,
    JSON.stringify({
      version: "nail-texture-region-extraction/v1",
      sourceGroupPrefix: "reviewed-crops",
      regions: [
        { parentFileName: "../escape.jpg", regionId: "main-photo", box: [0, 0, 1.2, 1] },
      ],
    }),
  );
  const result = python(
    script,
    "--manifest",
    manifest,
    "--image-dir",
    images,
    "--output-dir",
    output,
    "--report",
    report,
  );
  assert.notEqual(result.status, 0);
  const summary = JSON.parse(await readFile(report, "utf8"));
  assert.equal(summary.ok, false);
  assert.equal(summary.completedCount, 0);
  assert.match(summary.errors[0].message, /box must satisfy/);
});

test("reviewed region extraction prints non-ASCII parent names safely on Windows code pages", async () => {
  const source = await readFile(script, "utf8");
  assert.match(source, /print\(json\.dumps\(report, ensure_ascii=True/);
  assert.match(source, /write_text\(json\.dumps\(report, ensure_ascii=False/);
});
