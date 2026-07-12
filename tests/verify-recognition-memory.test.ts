import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const execFileAsync = promisify(execFile);

function report(jsStep: number, privateStep: number) {
  const samples = Array.from({ length: 20 }, (_, index) => ({
    iteration: index + 1,
    usedJSHeapBytes: 50 * 1024 * 1024 + index * jsStep,
    browserPrivateBytes: 300 * 1024 * 1024 + index * privateStep,
    browserWorkingSetBytes: 250 * 1024 * 1024,
    browserProcessCount: 4,
  }));
  return { version: "nail-texture-recognition-memory/v1", profile: "desktop-chromium", sampleCount: 20, samples };
}

test("recognition memory verifier accepts bounded repeated-run memory", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-memory-pass-"));
  const input = path.join(root, "input.json");
  const output = path.join(root, "output.json");
  const document = report(0, 0);
  document.samples[5]!.usedJSHeapBytes -= 1024;
  document.samples[5]!.browserPrivateBytes -= 1024;
  await writeFile(input, JSON.stringify(document), "utf8");
  await execFileAsync(process.execPath, [
    "--no-warnings", "--experimental-strip-types", "scripts/verify-recognition-memory.ts",
    "--input", input, "--output", output,
  ], { cwd: path.resolve(".") });
  const result = JSON.parse(await readFile(output, "utf8")) as { ok: boolean };
  assert.equal(result.ok, true);
});

test("recognition memory verifier rejects sustained growth", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-memory-fail-"));
  const input = path.join(root, "input.json");
  await writeFile(input, JSON.stringify(report(3 * 1024 * 1024, 10 * 1024 * 1024)), "utf8");
  await assert.rejects(execFileAsync(process.execPath, [
    "--no-warnings", "--experimental-strip-types", "scripts/verify-recognition-memory.ts",
    "--input", input,
  ], { cwd: path.resolve(".") }));
});
