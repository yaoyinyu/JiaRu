import path from "node:path";
import process from "node:process";
import { readFile } from "node:fs/promises";
import {
  compareNailDebugPayloads,
  type NailDetectionDebugPayload,
} from "../src/lib/nail-texture-recognition/index.ts";

const baselineArg = process.argv[2];
const candidateArg = process.argv[3];

if (!baselineArg || !candidateArg) {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/compare-nail-debug.ts <baseline-debug.json> <candidate-debug.json>"
  );
}

const baselinePath = path.resolve(baselineArg);
const candidatePath = path.resolve(candidateArg);

const [baselineRaw, candidateRaw] = await Promise.all([
  readFile(baselinePath, "utf8"),
  readFile(candidatePath, "utf8"),
]);

const baseline = JSON.parse(baselineRaw) as NailDetectionDebugPayload;
const candidate = JSON.parse(candidateRaw) as NailDetectionDebugPayload;

const comparison = compareNailDebugPayloads(baseline, candidate);
console.log(
  JSON.stringify(
    {
      baselinePath,
      candidatePath,
      ...comparison,
    },
    null,
    2
  )
);

if (!comparison.ok) {
  process.exitCode = 1;
}
