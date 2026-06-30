import path from "node:path";
import process from "node:process";
import { readFile } from "node:fs/promises";
import {
  postprocessNailTextureDetections,
  summarizeModelOutputs,
  type ModelTensorLike,
} from "../src/lib/nail-texture-recognition/index.ts";

interface ModelOutputFixture {
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

const fixtureArg =
  process.argv[2] ?? "model/fixtures/nail-texture-model-output-sample.json";
const fixturePath = path.resolve(fixtureArg);

const fixture = JSON.parse(
  await readFile(fixturePath, "utf8")
) as ModelOutputFixture;

const outputs = Object.fromEntries(
  Object.entries(fixture.outputs).map(([name, tensor]) => [
    name,
    {
      dims: tensor.dims,
      data: new Float32Array(tensor.data),
    } satisfies ModelTensorLike,
  ])
) as Record<string, ModelTensorLike>;

const preprocess = {
  inputSize: fixture.preprocess.inputSize,
  originalWidth: fixture.preprocess.originalWidth,
  originalHeight: fixture.preprocess.originalHeight,
  scaleX: fixture.preprocess.scaleX,
  scaleY: fixture.preprocess.scaleY,
  tensorData: new Float32Array(),
  tensorShape: [1, 3, fixture.preprocess.inputSize, fixture.preprocess.inputSize] as [
    1,
    3,
    number,
    number,
  ],
};

const candidates = postprocessNailTextureDetections(outputs, preprocess);
const debugOutputs = summarizeModelOutputs(outputs);
const expectations = fixture.expect ?? {};
const failures: string[] = [];

if (
  expectations.candidateCount != null &&
  candidates.length !== expectations.candidateCount
) {
  failures.push(
    `candidate_count_mismatch:${candidates.length}!==${expectations.candidateCount}`
  );
}
if (
  expectations.minScore != null &&
  candidates.some((candidate) => candidate.score < expectations.minScore!)
) {
  failures.push(`score_below_min:${expectations.minScore}`);
}
if (
  expectations.firstSuggestedFinger !== undefined &&
  (candidates[0]?.suggestedFinger ?? null) !== expectations.firstSuggestedFinger
) {
  failures.push(
    `first_suggested_finger_mismatch:${candidates[0]?.suggestedFinger ?? null}!==${expectations.firstSuggestedFinger}`
  );
}
if (
  expectations.requireMasks &&
  candidates.some((candidate) => !candidate.mask)
) {
  failures.push("missing_candidate_masks");
}

console.log(
  JSON.stringify(
    {
      fixturePath,
      ok: failures.length === 0,
      failures,
      candidateCount: candidates.length,
      candidates: candidates.map((candidate) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        width: candidate.width,
        length: candidate.length,
        score: candidate.score,
        confidence: candidate.confidence,
        suggestedFinger: candidate.suggestedFinger,
        hasMask: Boolean(candidate.mask),
      })),
      debugOutputs,
    },
    null,
    2
  )
);

if (failures.length > 0) {
  process.exitCode = 1;
}
