import path from "node:path";
import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";
import {
  serializeModelOutputs,
  type ModelTensorLike,
} from "../src/lib/nail-texture-recognition/index.ts";

interface FixtureLike {
  preprocess: {
    inputSize: number;
    originalWidth: number;
    originalHeight: number;
    scaleX: number;
    scaleY: number;
  };
  outputs: Record<string, { dims?: number[]; data: number[] }>;
  expect?: {
    candidateCount?: number;
    minScore?: number;
    firstSuggestedFinger?: number | null;
    requireMasks?: boolean;
  };
}

interface DumpLike {
  preprocess?: FixtureLike["preprocess"];
  outputs?: Record<string, { dims?: number[]; data: number[] }>;
  rawModelOutputs?: Record<string, { dims?: number[]; data: number[] }>;
  expect?: FixtureLike["expect"];
}

const inputArg =
  process.argv[2] ?? "model/fixtures/nail-texture-model-output-dump-sample.json";
const outputArg = process.argv[3];
const inputPath = path.resolve(inputArg);
const outputPath = path.resolve(
  outputArg ?? inputPath.replace(/-dump-sample\.json$/i, "-sample.json")
);

const source = JSON.parse(await readFile(inputPath, "utf8")) as DumpLike;
const preprocess = source.preprocess;
if (!preprocess) {
  throw new Error("Missing preprocess block in model output dump");
}

const rawOutputs = source.outputs ?? source.rawModelOutputs;
if (!rawOutputs || Object.keys(rawOutputs).length === 0) {
  throw new Error("Missing outputs/rawModelOutputs block in model output dump");
}

const normalizedOutputs = Object.fromEntries(
  Object.entries(rawOutputs).map(([name, tensor]) => [
    name,
    {
      dims: tensor.dims,
      data: new Float32Array(tensor.data),
    } satisfies ModelTensorLike,
  ])
) as Record<string, ModelTensorLike>;

const fixture: FixtureLike = {
  preprocess,
  outputs: serializeModelOutputs(normalizedOutputs),
  expect: source.expect,
};

await writeFile(outputPath, JSON.stringify(fixture, null, 2), "utf8");
console.log(
  JSON.stringify(
    {
      inputPath,
      outputPath,
      tensorNames: Object.keys(fixture.outputs),
      expect: fixture.expect ?? null,
    },
    null,
    2
  )
);
