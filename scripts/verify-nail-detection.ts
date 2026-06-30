import path from "node:path";
import process from "node:process";
import { mkdir, writeFile } from "node:fs/promises";
import sharp from "sharp";
import {
  createNailDetectionMasks,
} from "../src/lib/nail-image-detection.ts";
import {
  buildNailDebugArtifactPaths,
  recognizeNailTextures,
} from "../src/lib/nail-texture-recognition/index.ts";

const input = process.argv[2];
const maybeAnnotation = process.argv[3];
const annotation = maybeAnnotation && !maybeAnnotation.startsWith("--")
  ? maybeAnnotation
  : undefined;
const extraArgs = process.argv.slice(annotation ? 4 : 3);
if (!input) {
  throw new Error("Usage: node --experimental-strip-types scripts/verify-nail-detection.ts <image> [green-annotation-image] [--output-dir <dir>] [--prefix <name>]");
}

let outputDir: string | undefined;
let prefix: string | undefined;
for (let index = 0; index < extraArgs.length; index++) {
  const arg = extraArgs[index];
  if (arg === "--output-dir") {
    outputDir = path.resolve(extraArgs[++index]);
    continue;
  }
  if (arg === "--prefix") {
    prefix = extraArgs[++index];
    continue;
  }
  throw new Error(
    "Usage: node --experimental-strip-types scripts/verify-nail-detection.ts <image> [green-annotation-image] [--output-dir <dir>] [--prefix <name>]"
  );
}

const absoluteInput = path.resolve(input);
const absoluteAnnotation = annotation ? path.resolve(annotation) : null;
const { data, info } = await sharp(absoluteInput)
  .ensureAlpha()
  .raw()
  .toBuffer({ resolveWithObject: true });
const recognition = await recognizeNailTextures({
  width: info.width,
  height: info.height,
  data,
}, {
  preferModel: true,
  debugOutputs: true,
  debugRawModelOutputs: true,
});
const regions = recognition.candidates.map((candidate) => ({
  cx: candidate.cx,
  cy: candidate.cy,
  angle: candidate.angle,
  length: candidate.length,
  width: candidate.width,
  confidence: candidate.confidence === "high" ? "high" as const : "low" as const,
  score: candidate.score,
}));
const masks = createNailDetectionMasks({
  width: info.width,
  height: info.height,
  data,
});

const overlay = `
<svg width="${info.width}" height="${info.height}" xmlns="http://www.w3.org/2000/svg">
  ${regions.map((region, index) => `
    <g transform="translate(${region.cx} ${region.cy}) rotate(${region.angle * 180 / Math.PI})">
      <rect x="${-region.width / 2}" y="${-region.length / 2}"
        width="${region.width}" height="${region.length}"
        fill="none" stroke="#00ff88" stroke-width="4"/>
      <text x="0" y="0" fill="#ffffff" stroke="#000000" stroke-width="1"
        text-anchor="middle" font-size="22">${index + 1}</text>
    </g>
  `).join("")}
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
}).linear(255).png().toFile(candidateMaskOutput);
await sharp(Buffer.from(masks.skin), {
  raw: { width: masks.width, height: masks.height, channels: 1 },
}).linear(255).png().toFile(skinMaskOutput);

interface GroundTruthRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  area: number;
  cx: number;
  cy: number;
}

interface MatchResult {
  predictedIndex: number;
  truthIndex: number;
  distance: number;
}

function findGreenComponents(
  pixels: Buffer,
  width: number,
  height: number
): GroundTruthRegion[] {
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < width * height; index++) {
    const r = pixels[index * 4];
    const g = pixels[index * 4 + 1];
    const b = pixels[index * 4 + 2];
    mask[index] = g > 180 && g > r * 1.5 && g > b * 1.5 ? 1 : 0;
  }

  const seen = new Uint8Array(mask.length);
  const components: GroundTruthRegion[] = [];
  const queue = new Int32Array(mask.length);

  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || seen[start]) continue;

    let head = 0;
    let tail = 0;
    queue[tail++] = start;
    seen[start] = 1;

    let minX = width;
    let minY = height;
    let maxX = 0;
    let maxY = 0;
    let area = 0;
    let sumX = 0;
    let sumY = 0;

    while (head < tail) {
      const current = queue[head++];
      const x = current % width;
      const y = Math.floor(current / width);
      area++;
      sumX += x;
      sumY += y;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);

      for (let ny = y - 1; ny <= y + 1; ny++) {
        for (let nx = x - 1; nx <= x + 1; nx++) {
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const next = ny * width + nx;
          if (!mask[next] || seen[next]) continue;
          seen[next] = 1;
          queue[tail++] = next;
        }
      }
    }

    if (area >= 200) {
      components.push({
        x: minX,
        y: minY,
        width: maxX - minX + 1,
        height: maxY - minY + 1,
        area,
        cx: sumX / area,
        cy: sumY / area,
      });
    }
  }

  return components.sort((a, b) => a.cx - b.cx);
}

async function readGroundTruth(): Promise<GroundTruthRegion[] | null> {
  if (!absoluteAnnotation) return null;
  const annotationImage = await sharp(absoluteAnnotation)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  if (
    annotationImage.info.width !== info.width ||
    annotationImage.info.height !== info.height
  ) {
    throw new Error(
      `Annotation size ${annotationImage.info.width}x${annotationImage.info.height} does not match input ${info.width}x${info.height}`
    );
  }
  return findGreenComponents(
    annotationImage.data,
    annotationImage.info.width,
    annotationImage.info.height
  );
}

const groundTruth = await readGroundTruth();
const matches: MatchResult[] = [];
let maxCenterError = 0;
if (groundTruth) {
  const used = new Set<number>();
  for (let truthIndex = 0; truthIndex < groundTruth.length; truthIndex++) {
    const truth = groundTruth[truthIndex];
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let predictedIndex = 0; predictedIndex < regions.length; predictedIndex++) {
      if (used.has(predictedIndex)) continue;
      const region = regions[predictedIndex];
      const distance = Math.hypot(region.cx - truth.cx, region.cy - truth.cy);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = predictedIndex;
      }
    }
    if (bestIndex >= 0) {
      used.add(bestIndex);
      matches.push({ predictedIndex: bestIndex, truthIndex, distance: bestDistance });
      maxCenterError = Math.max(maxCenterError, bestDistance);
    }
  }
}

const debugPayload = {
  input: absoluteInput,
  annotation: absoluteAnnotation,
  output,
  candidateMaskOutput,
  skinMaskOutput,
  debugJsonOutput,
  width: info.width,
  height: info.height,
  count: regions.length,
  backend: recognition.backend,
  modelVersion: recognition.modelVersion,
  modelInfo: recognition.modelInfo,
  warnings: recognition.warnings,
  debugOutputs: recognition.debugOutputs,
  rawModelOutputs: recognition.rawModelOutputs,
  preprocess: recognition.preprocess,
  modelOutputDumpPath: recognition.rawModelOutputs ? modelOutputDumpPath : null,
  regions,
  groundTruth,
  matches,
  maxCenterError,
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
  const maxAllowedCenterError = 45;
  if (groundTruth.length < 4) {
    console.error("Expected at least four green annotation components.");
    process.exitCode = 1;
  }
  if (matches.length < groundTruth.length || maxCenterError > maxAllowedCenterError) {
    console.error(
      `Predictions did not match annotation: matches=${matches.length}/${groundTruth.length}, maxCenterError=${maxCenterError.toFixed(2)}`
    );
    process.exitCode = 1;
  }
}
