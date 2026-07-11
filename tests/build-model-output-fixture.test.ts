import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("build-model-output-fixture converts rawModelOutputs dump into fixture", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "nail-model-output-fixture-"));
  const inputPath = path.join(root, "dump.json");
  const outputPath = path.join(root, "fixture.json");

  await writeFile(
    inputPath,
    JSON.stringify(
      {
        preprocess: {
          inputSize: 4,
          originalWidth: 80,
          originalHeight: 80,
          scaleX: 20,
          scaleY: 20,
        },
        rawModelOutputs: {
          boxes: {
            dims: [1, 1, 6],
            data: [2, 2, 0.5, 0.5, 0.9, 5],
          },
          proto: {
            dims: [1, 1, 2, 2],
            data: [1, -1, 1, -1],
          },
        },
        expect: {
          candidateCount: 1,
          requireMasks: true,
        },
        pythonReference: [{
          cx: 2,
          cy: 2,
          width: 0.5,
          length: 0.5,
          score: 0.9,
          maskForegroundPixels: 1,
        }],
      },
      null,
      2
    ),
    "utf8"
  );

  const { stdout } = await execFileAsync(process.execPath, [
    "--no-warnings",
    "--experimental-strip-types",
    "scripts/build-model-output-fixture.ts",
    inputPath,
    outputPath,
  ], {
    cwd: path.resolve("."),
  });

  const summary = JSON.parse(stdout) as {
    inputPath: string;
    outputPath: string;
    tensorNames: string[];
  };
  assert.equal(summary.inputPath, inputPath);
  assert.equal(summary.outputPath, outputPath);
  assert.deepEqual(summary.tensorNames.sort(), ["boxes", "proto"]);

  const fixture = JSON.parse(await readFile(outputPath, "utf8")) as {
    preprocess: { inputSize: number };
    outputs: Record<string, { dims: number[]; data: number[] }>;
    expect: { candidateCount: number };
    pythonReference: Array<{ maskForegroundPixels: number }>;
  };
  assert.equal(fixture.preprocess.inputSize, 4);
  assert.deepEqual(fixture.outputs.boxes.dims, [1, 1, 6]);
  assert.equal(fixture.outputs.boxes.data.length, 6);
  assert.equal(fixture.expect.candidateCount, 1);
  assert.equal(fixture.pythonReference[0]?.maskForegroundPixels, 1);
});
