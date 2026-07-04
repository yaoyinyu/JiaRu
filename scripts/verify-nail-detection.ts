import path from "node:path";
import process from "node:process";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import sharp from "sharp";
import { createNailDetectionMasks } from "../src/lib/nail-image-detection.ts";
import {
  buildNailDebugArtifactPaths,
  recognizeNailTextures,
} from "../src/lib/nail-texture-recognition/index.ts";
import {
  compareDetectedRegionsToFixture,
  findGreenAnnotationComponents,
  type NailDetectionGroundTruthFixture,
  type NailDetectionGroundTruthRegion,
} from "../src/lib/nail-detection-fixture.ts";

const argv = process.argv.slice(2);
const input = argv[0];
if (!input) {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-nail-detection.ts <image> [green-annotation-image] [--fixture <path>] [--output-dir <dir>] [--prefix <name>]"
  );
}

let annotationArg: string | undefined;
let outputDir: string | undefined;
let prefix: string | undefined;
let fixturePath: string | undefined;

for (let index = 1; index < argv.length; index++) {
  const arg = argv[index];
  if (arg === "--output-dir") {
    outputDir = path.resolve(argv[++index]);
    continue;
  }
  if (arg === "--prefix") {
    prefix = argv[++index];
    continue;
  }
  if (arg === "--fixture") {
    fixturePath = path.resolve(argv[++index]);
    continue;
  }
  if (!annotationArg) {
    annotationArg = arg;
    continue;
  }
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-nail-detection.ts <image> [green-annotation-image] [--fixture <path>] [--output-dir <dir>] [--prefix <name>]"
  );
}

const absoluteInput = path.resolve(input);
const absoluteAnnotation = annotationArg ? path.resolve(annotationArg) : null;

async function loadFixture(): Promise<NailDetectionGroundTruthFixture | null> {
  if (!fixturePath) return null;
  return JSON.parse(await readFile(fixturePath, "utf8")) as NailDetectionGroundTruthFixture;
}

async function loadGroundTruth(
  imageWidth: number,
  imageHeight: number,
  fixture: NailDetectionGroundTruthFixture | null
): Promise<NailDetectionGroundTruthRegion[] | null> {
  if (fixture) {
    if (fixture.truthRegions.length !== fixture.expected.candidateCount) {
      throw new Error(
        `Fixture candidateCount ${fixture.expected.candidateCount} does not match truthRegions length ${fixture.truthRegions.length}`
      );
    }
    return fixture.truthRegions;
  }

  if (!absoluteAnnotation) return null;
  const annotationImage = await sharp(absoluteAnnotation)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (annotationImage.info.width !== imageWidth || annotationImage.info.height !== imageHeight) {
    throw new Error(
      `Annotation size ${annotationImage.info.width}x${annotationImage.info.height} does not match input ${imageWidth}x${imageHeight}`
    );
  }
  return findGreenAnnotationComponents(
    annotationImage.data,
    annotationImage.info.width,
    annotationImage.info.height
  );
}

const { data, info } = await sharp(absoluteInput)
  .ensureAlpha()
  .raw()
  .toBuffer({ resolveWithObject: true });
const recognition = await recognizeNailTextures(
  {
    width: info.width,
    height: info.height,
    data,
  },
  {
    preferModel: true,
    debugOutputs: true,
    debugRawModelOutputs: true,
  }
);
const regions = recognition.candidates.map((candidate) => ({
  cx: candidate.cx,
  cy: candidate.cy,
  angle: candidate.angle,
  length: candidate.length,
  width: candidate.width,
  confidence: candidate.confidence === "high" ? ("high" as const) : ("low" as const),
  score: candidate.score,
}));
const masks = createNailDetectionMasks({
  width: info.width,
  height: info.height,
  data,
});

const overlay = `
<svg width="${info.width}" height="${info.height}" xmlns="http://www.w3.org/2000/svg">
  ${regions
    .map(
      (region, index) => `
    <g transform="translate(${region.cx} ${region.cy}) rotate(${(region.angle * 180) / Math.PI})">
      <rect x="${-region.width / 2}" y="${-region.length / 2}"
        width="${region.width}" height="${region.length}"
        fill="none" stroke="#00ff88" stroke-width="4"/>
      <text x="0" y="0" fill="#ffffff" stroke="#000000" stroke-width="1"
        text-anchor="middle" font-size="22">${index + 1}</text>
    </g>
  `
    )
    .join("")}
</svg>`;
const {
  output,
  candidateMaskOutput,
  skinMaskOutput,
  debugJsonOutput,
  modelOutputDumpPath,
} = buildNailDebugArtifactPaths({
  inputPath: absoluteInput,
  outputDir,
  prefix,
});
await mkdir(path.dirname(output), { recursive: true });
await sharp(absoluteInput)
  .composite([{ input: Buffer.from(overlay) }])
  .png()
  .toFile(output);
await sharp(Buffer.from(masks.candidate), {
  raw: { width: masks.width, height: masks.height, channels: 1 },
})
  .linear(255)
  .png()
  .toFile(candidateMaskOutput);
await sharp(Buffer.from(masks.skin), {
  raw: { width: masks.width, height: masks.height, channels: 1 },
})
  .linear(255)
  .png()
  .toFile(skinMaskOutput);

const fixture = await loadFixture();
const groundTruth = await loadGroundTruth(info.width, info.height, fixture);
const comparison = groundTruth
  ? compareDetectedRegionsToFixture(recognition.candidates, groundTruth)
  : { matches: [], maxCenterError: 0, matchedTruthCount: 0 };
const maxAllowedCenterError = fixture?.expected.maxCenterError ?? 45;
const expectedCandidateCount = fixture?.expected.candidateCount ?? groundTruth?.length ?? null;

const debugPayload = {
  input: absoluteInput,
  annotation: absoluteAnnotation,
  fixturePath,
  output,
  candidateMaskOutput,
  skinMaskOutput,
  debugJsonOutput,
  width: info.width,
  height: info.height,
  count: regions.length,
  backend: recognition.backend,
  modelVersion: recognition.modelVersion,
  elapsedMs: recognition.elapsedMs,
  modelInfo: recognition.modelInfo,
  warnings: recognition.warnings,
  debugOutputs: recognition.debugOutputs,
  rawModelOutputs: recognition.rawModelOutputs,
  preprocess: recognition.preprocess,
  modelOutputDumpPath: recognition.rawModelOutputs ? modelOutputDumpPath : null,
  regions,
  groundTruth,
  expectedCandidateCount,
  matches: comparison.matches,
  maxCenterError: comparison.maxCenterError,
  maxAllowedCenterError,
};

await writeFile(debugJsonOutput, JSON.stringify(debugPayload, null, 2), "utf8");
if (recognition.rawModelOutputs && recognition.preprocess) {
  await writeFile(
    modelOutputDumpPath,
    JSON.stringify(
      {
        input: absoluteInput,
        preprocess: recognition.preprocess,
        rawModelOutputs: recognition.rawModelOutputs,
      },
      null,
      2
    ),
    "utf8"
  );
}
console.log(JSON.stringify(debugPayload, null, 2));

if (regions.length < 4) {
  process.exitCode = 1;
}
if (groundTruth) {
  if (expectedCandidateCount !== null && groundTruth.length !== expectedCandidateCount) {
    console.error(
      `Ground truth count ${groundTruth.length} does not match expected candidate count ${expectedCandidateCount}`
    );
    process.exitCode = 1;
  }
  if (
    comparison.matchedTruthCount < groundTruth.length ||
    comparison.maxCenterError > maxAllowedCenterError
  ) {
    console.error(
      `Predictions did not match annotation: matches=${comparison.matchedTruthCount}/${groundTruth.length}, maxCenterError=${comparison.maxCenterError.toFixed(2)}`
    );
    process.exitCode = 1;
  }
}
