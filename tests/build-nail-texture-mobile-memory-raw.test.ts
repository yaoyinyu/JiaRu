import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

function run(args: string[]) {
  return spawnSync("node", ["--no-warnings", "--experimental-strip-types", "scripts/build-nail-texture-mobile-memory-raw.ts", ...args], { encoding: "utf8" });
}

function session() {
  return {
    version: "nail-texture-device-session/v1",
    eligibleForPerformanceVerification: true,
    sessionId: "session-1",
    deviceFamily: "iphone",
    modelVersion: "candidate-v1",
    backend: "wasm",
    inputSize: 512,
  };
}

function csv(count: number) {
  const lines = ["iteration,usedJSHeapMiB,browserPrivateMiB,browserWorkingSetMiB,browserProcessCount"];
  for (let index = 1; index <= count; index += 1) lines.push(`${index},0,120,100,1`);
  return `${lines.join("\n")}\n`;
}

test("mobile memory raw builder binds 20 profiler rows to one eligible device session", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mobile-memory-"));
  const sessionPath = path.join(root, "session.json");
  const csvPath = path.join(root, "memory.csv");
  const output = path.join(root, "raw-memory.json");
  await writeFile(sessionPath, JSON.stringify(session()), "utf8");
  await writeFile(csvPath, csv(20), "utf8");
  const result = run(["--session", sessionPath, "--csv", csvPath, "--output", output]);
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(await readFile(output, "utf8"));
  assert.equal(report.sampleCount, 20);
  assert.equal(report.deviceFamily, "iphone");
  assert.equal(report.samples[0].browserPrivateBytes, 120 * 1024 * 1024);
  assert.match(report.sourceEvidence.profilerCsvSha256, /^[a-f0-9]{64}$/);
});

test("mobile memory raw builder rejects undersized profiler evidence and output overwrite", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-mobile-memory-reject-"));
  const sessionPath = path.join(root, "session.json");
  const csvPath = path.join(root, "memory.csv");
  const output = path.join(root, "raw-memory.json");
  await writeFile(sessionPath, JSON.stringify(session()), "utf8");
  await writeFile(csvPath, csv(19), "utf8");
  const short = run(["--session", sessionPath, "--csv", csvPath, "--output", output]);
  assert.equal(short.status, 1);
  assert.match(short.stderr, /below 20/);
  const overwrite = run(["--session", sessionPath, "--csv", csvPath, "--output", csvPath]);
  assert.equal(overwrite.status, 1);
  assert.match(overwrite.stderr, /must not overwrite/);
});
