import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("verify-nail-detection exports recognition mask overlay evidence", async () => {
  const outputDir = await mkdtemp(path.join(os.tmpdir(), "verify-nail-detection-mask-"));

  const { stdout } = await execFileAsync(
    process.execPath,
    [
      "--no-warnings",
      "--experimental-strip-types",
      "scripts/verify-nail-detection.ts",
      path.resolve("model/5188.jpg_wh860.jpg"),
      "--fixture",
      path.resolve("model/fixtures/nail-detection-reference-5188.json"),
      "--output-dir",
      outputDir,
      "--prefix",
      "verify-mask",
    ],
    { cwd: path.resolve("."), maxBuffer: 10 * 1024 * 1024 }
  );

  const report = JSON.parse(stdout) as {
    recognitionMaskOutput: string;
    recognitionMaskOverlay: { maskCandidateCount: number; coveredPixels: number };
    debugJsonOutput: string;
  };

  assert.match(report.recognitionMaskOutput, /verify-mask-5188\.jpg_wh860-recognition-mask-overlay\.png$/);
  assert.equal(report.recognitionMaskOverlay.maskCandidateCount, 0);
  assert.equal(report.recognitionMaskOverlay.coveredPixels, 0);
  assert.ok(await readFile(report.recognitionMaskOutput));

  const persisted = JSON.parse(await readFile(report.debugJsonOutput, "utf8")) as {
    recognitionMaskOutput: string;
  };
  assert.equal(persisted.recognitionMaskOutput, report.recognitionMaskOutput);
});