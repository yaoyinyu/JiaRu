import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { verifyApprovedDeviceAcceptanceReport } from "../scripts/lib/nail-texture-device-acceptance.ts";

function run(script: string, args: string[]) {
  return spawnSync("node", ["--no-warnings", "--experimental-strip-types", script, ...args], { encoding: "utf8" });
}

async function prepareDeviceEvidence(
  root: string,
  options: { samples?: number; sessionId?: string; memorySessionId?: string; deviceFamily?: string; backend?: string } = {},
) {
  const samples = options.samples ?? 20;
  const sessionId = options.sessionId ?? "device-session-1";
  const memorySessionId = options.memorySessionId ?? sessionId;
  const deviceFamily = options.deviceFamily ?? "android";
  const backend = options.backend ?? "wasm";
  const rawPerformance = path.join(root, "raw-performance.json");
  const performance = path.join(root, "performance.json");
  const rawMemory = path.join(root, "raw-memory.json");
  const memory = path.join(root, "memory.json");
  await writeFile(rawPerformance, JSON.stringify({
    version: "nail-texture-device-session/v1",
    sessionId,
    deviceFamily,
    samples: Array.from({ length: samples }, (_, index) => ({
      imageId: `sample-${index + 1}`,
      sessionId,
      deviceFamily,
      backend: "model",
      backendName: backend,
      modelVersion: "nail-texture-seg-candidate",
      inputSize: 512,
      elapsedMs: 700 + index,
      workerElapsedMs: 650 + index,
    })),
  }), "utf8");
  run("scripts/verify-recognition-performance.ts", [
    "--profile", "mobile", "--min-samples", "20", "--output", performance, rawPerformance,
  ]);
  const memorySamples = Array.from({ length: 20 }, (_, index) => ({
    iteration: index + 1,
    usedJSHeapBytes: 20 * 1024 * 1024 + (index % 3) * 1024,
    browserPrivateBytes: 120 * 1024 * 1024 + (index % 3) * 1024,
    browserWorkingSetBytes: 100 * 1024 * 1024,
    browserProcessCount: 1,
  }));
  await writeFile(rawMemory, JSON.stringify({
    version: "nail-texture-recognition-memory/v1",
    profile: deviceFamily,
    sessionId: memorySessionId,
    deviceFamily,
    backend,
    modelVersion: "nail-texture-seg-candidate",
    inputSize: 512,
    sampleCount: memorySamples.length,
    samples: memorySamples,
  }), "utf8");
  const memoryResult = run("scripts/verify-recognition-memory.ts", ["--input", rawMemory, "--output", memory]);
  assert.equal(memoryResult.status, 0, memoryResult.stderr);
  return { performance, memory, rawPerformance, rawMemory };
}

test("device acceptance builder combines passing performance and memory evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-acceptance-"));
  const { performance, memory } = await prepareDeviceEvidence(root);
  const output = path.join(root, "device.json");
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "android", "--device-name", "Phone", "--os", "Android 16",
    "--browser", "Chrome", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, true);
  assert.equal(report.version, "nail-texture-device-acceptance/v2");
  assert.equal(report.performance.sampleCount, 20);
  assert.equal(report.memory.sampleCount, 20);
  assert.match(report.evidence.performance.sha256, /^[a-f0-9]{64}$/);
  assert.match(report.evidence.memory.rawReportSha256, /^[a-f0-9]{64}$/);
  const replay = await verifyApprovedDeviceAcceptanceReport(output, "android");
  assert.equal(replay.ok, true, replay.errors.join("\n"));
});

test("device acceptance builder rejects undersized raw evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-reject-"));
  const { performance, memory } = await prepareDeviceEvidence(root, { samples: 19, deviceFamily: "iphone" });
  const output = path.join(root, "device.json");
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "iphone", "--device-name", "Phone", "--os", "iOS",
    "--browser", "Safari", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.match(report.errors.join(" "), /below 20/);
});

test("device acceptance builder rejects forged outer PASS evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-forged-"));
  const performance = path.join(root, "performance.json");
  const memory = path.join(root, "memory.json");
  const output = path.join(root, "device.json");
  await writeFile(performance, JSON.stringify({ ok: true, profile: "mobile", totals: { samples: 20 } }), "utf8");
  await writeFile(memory, JSON.stringify({ ok: true, totals: { samples: 20 } }), "utf8");
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "android", "--device-name", "Phone", "--os", "Android",
    "--browser", "Chrome", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.ok, false);
  assert.match(report.errors.join(" "), /samples|inputPath|identity/);
});

test("device acceptance builder rejects cross-session evidence", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-cross-session-"));
  const { performance, memory } = await prepareDeviceEvidence(root, { memorySessionId: "other-session" });
  const output = path.join(root, "device.json");
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "android", "--device-name", "Phone", "--os", "Android",
    "--browser", "Chrome", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 1);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.match(report.errors.join(" "), /sessionId do not match/);
});

test("approved device report replay rejects source drift", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "nail-device-drift-"));
  const { performance, memory } = await prepareDeviceEvidence(root);
  const output = path.join(root, "device.json");
  const result = run("scripts/build-nail-texture-device-acceptance.ts", [
    "--device-family", "android", "--device-name", "Phone", "--os", "Android",
    "--browser", "Chrome", "--backend", "wasm", "--performance", performance,
    "--memory", memory, "--output", output,
  ]);
  assert.equal(result.status, 0, result.stderr);
  const document = JSON.parse(await readFile(performance, "utf8"));
  document.samples[0].elapsedMs += 1;
  await writeFile(performance, JSON.stringify(document), "utf8");
  const replay = await verifyApprovedDeviceAcceptanceReport(output, "android");
  assert.equal(replay.ok, false);
  assert.ok(replay.errors.some((error) => /SHA-256|p95Ms/.test(error)));
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
