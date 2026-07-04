import path from "node:path";
import process from "node:process";
import { writeFile } from "node:fs/promises";
import sharp from "sharp";
import {
  NAIL_DETECTION_FIXTURE_VERSION,
  findGreenAnnotationComponents,
} from "../src/lib/nail-detection-fixture.ts";

const [imagePathArg, annotationPathArg, outputPathArg] = process.argv.slice(2);

if (!imagePathArg || !annotationPathArg || !outputPathArg) {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/build-nail-detection-fixture.ts <image> <green-annotation-image> <output>"
  );
}

const imagePath = path.resolve(imagePathArg);
const annotationPath = path.resolve(annotationPathArg);
const outputPath = path.resolve(outputPathArg);

const image = await sharp(imagePath).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
const annotation = await sharp(annotationPath).ensureAlpha().raw().toBuffer({ resolveWithObject: true });

if (image.info.width !== annotation.info.width || image.info.height !== annotation.info.height) {
  throw new Error(
    `Annotation size ${annotation.info.width}x${annotation.info.height} does not match image ${image.info.width}x${image.info.height}`
  );
}

const truthRegions = findGreenAnnotationComponents(
  annotation.data,
  annotation.info.width,
  annotation.info.height
);

const fixture = {
  version: NAIL_DETECTION_FIXTURE_VERSION,
  id: path.basename(outputPath, path.extname(outputPath)),
  imagePath: path.relative(process.cwd(), imagePath).replaceAll("\\", "/"),
  annotationPath: path.relative(process.cwd(), annotationPath).replaceAll("\\", "/"),
  expected: {
    candidateCount: truthRegions.length,
    maxCenterError: 45,
  },
  truthRegions,
};

await writeFile(outputPath, JSON.stringify(fixture, null, 2), "utf8");
console.log(JSON.stringify(fixture, null, 2));
