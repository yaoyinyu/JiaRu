import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

function run(script: string, args: string[]) {
  return spawnSync("node", ["--no-warnings", "--experimental-strip-types", script, ...args], { encoding: "utf8" });
}

test("device acceptance builder combines passing performance and memory evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-acceptance-"));
  const performance = path.join(root, "performance.json");
  const memory = path.join(root, "memory.json");
  const output = path.join(root, "device.json");
  await writeFile(performance, JSON.stringify({ ok: true, totals: { samples: 20 }, thresholds: {}, stats: { p95Ms: 900 } }));
  await writeFile(memory, JSON.stringify({ ok: true, totals: { samples: 20 }, thresholds: {}, stats: { peak: 10 } }));
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "android", "--device-name", "Phone", "--os", "Android 16",
    "--browser", "Chrome", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.performance.sampleCount, 20);
  assert.equal(report.memory.sampleCount, 20);
});

test("device acceptance builder rejects undersized raw evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-reject-"));
  const performance = path.join(root, "performance.json");
  const memory = path.join(root, "memory.json");
  const output = path.join(root, "device.json");
  await writeFile(performance, JSON.stringify({ ok: true, totals: { samples: 19 } }));
  await writeFile(memory, JSON.stringify({ ok: true, totals: { samples: 20 } }));
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "iphone", "--device-name", "Phone", "--os", "iOS",
    "--browser", "Safari", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.match(report.errors.join(" "), /below 20/);
});

test("failure-case builder validates images and persists SHA-256 evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-failure-evidence-"));
  const images = path.join(root, "images");
  await mkdir(images);
  await writeFile(path.join(images, "failure.jpg"), "failure-image");
  const csv = path.join(root, "failure.csv");
  const output = path.join(root, "failure.json");
  await writeFile(csv, "fileName,sourceGroup,category,severity,notes\nfailure.jpg,session-1,glare,high,strong reflection\n");
  const result = run("scripts/build-nail-texture-user-failure-cases.ts", ["--csv", csv, "--image-dir", images, "--output", output]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, true);
  assert.match(report.records[0].imageSha256, /^[a-f0-9]{64}$/);
});

test("failure-case builder rejects categories outside the fixed taxonomy", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-failure-reject-"));
  const images = path.join(root, "images");
  await mkdir(images);
  await writeFile(path.join(images, "failure.jpg"), "failure-image");
  const csv = path.join(root, "failure.csv");
  const output = path.join(root, "failure.json");
  await writeFile(csv, "fileName,sourceGroup,category,severity,notes\nfailure.jpg,session-1,unknown_kind,high,note\n");
  const result = run("scripts/build-nail-texture-user-failure-cases.ts", ["--csv", csv, "--image-dir", images, "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.match(report.errors.join(" "), /invalid category/);
});

test("Beta review builder enforces 100 reviewed images and the usable-rate gate", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-beta-evidence-"));
  const images = path.join(root, "images");
  await mkdir(images);
  const rows = ["fileName,sourceGroup,decision,correctionSeconds,notes"];
  for (let index = 0; index < 100; index += 1) {
    const fileName = `sample-${index}.jpg`;
    await writeFile(path.join(images, fileName), `image-${index}`);
    const decision = index < 85 ? "directly_usable" : index < 95 ? "needs_fix" : "unusable";
    rows.push(`${fileName},session-${Math.floor(index / 5)},${decision},${decision === "needs_fix" ? 20 : 0},reviewed`);
  }
  const csv = path.join(root, "beta.csv");
  const output = path.join(root, "beta.json");
  await writeFile(csv, `${rows.join("\n")}\n`);
  const result = run("scripts/build-nail-texture-beta-review.ts", [
    "--csv", csv, "--image-dir", images, "--reviewer", "user", "--output", output,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.sampleCount, 100);
  assert.equal(report.directlyUsableRate, 0.85);
  assert.equal(report.counts.needs_fix, 10);
});

test("Beta review builder rejects a template-sized review", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-beta-reject-"));
  const images = path.join(root, "images");
  await mkdir(images);
  await writeFile(path.join(images, "sample.jpg"), "image");
  const csv = path.join(root, "beta.csv");
  const output = path.join(root, "beta.json");
  await writeFile(csv, "fileName,sourceGroup,decision,correctionSeconds,notes\nsample.jpg,session,directly_usable,0,reviewed\n");
  const result = run("scripts/build-nail-texture-beta-review.ts", ["--csv", csv, "--image-dir", images, "--reviewer", "user", "--output", output]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.match(report.errors.join(" "), /below 100/);
});
