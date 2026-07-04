import path from "node:path";
import { copyFile, mkdir, writeFile } from "node:fs/promises";
import process from "node:process";
import sharp from "sharp";
import { recognizeNailTexturesWithFallback } from "../../src/lib/nail-texture-recognition/index.ts";
import {
  buildInitialAnnotationDocument,
  parseSourceRecords,
  stringifySourceRecords,
  upsertSourceRecord,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const sourcesCsvPath = path.join(datasetRoot, "metadata", "sources.csv");

interface CliOptions {
  copyImage: boolean;
  negative: boolean;
  sourceGroup?: string;
  outputDir: string;
  rawImageDir: string;
  originType: SourceRecord["originType"];
  originRef: string;
  license: string;
  notes: string;
  inputs: string[];
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    copyImage: false,
    negative: false,
    outputDir: path.join(datasetRoot, "annotations", "raw-json"),
    rawImageDir: path.join(datasetRoot, "images", "raw"),
    originType: "reference",
    originRef: "",
    license: "",
    notes: "",
    inputs: [],
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--copy-image") {
      options.copyImage = true;
      continue;
    }
    if (arg === "--negative") {
      options.negative = true;
      continue;
    }
    if (arg === "--source-group") {
      options.sourceGroup = argv[++i];
      continue;
    }
    if (arg === "--output-dir") {
      options.outputDir = path.resolve(argv[++i]);
      continue;
    }
    if (arg === "--raw-image-dir") {
      options.rawImageDir = path.resolve(argv[++i]);
      continue;
    }
    if (arg === "--origin-type") {
      options.originType = argv[++i] as SourceRecord["originType"];
      continue;
    }
    if (arg === "--origin-ref") {
      options.originRef = argv[++i];
      continue;
    }
    if (arg === "--license") {
      options.license = argv[++i];
      continue;
    }
    if (arg === "--notes") {
      options.notes = argv[++i];
      continue;
    }
    options.inputs.push(arg);
  }

  if (options.inputs.length === 0) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/export-fallback-annotations.ts [--copy-image] [--source-group <name>] [--origin-type <reference|web|user|merchant|negative|other>] [--origin-ref <text>] [--license <text>] [--notes <text>] <image> [more images...]"
    );
  }

  return options;
}

async function readExistingSourcesCsv(): Promise<SourceRecord[]> {
  try {
    const { readFile } = await import("node:fs/promises");
    return parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

async function exportSingleImage(
  inputPath: string,
  options: CliOptions
): Promise<{
  input: string;
  outputJson: string;
  copiedImage?: string;
  annotation: NailTextureAnnotationDocument;
  sourceRecord: SourceRecord;
}> {
  const absoluteInput = path.resolve(inputPath);
  const fileName = path.basename(absoluteInput);
  const imageId = fileName.replace(/\.[^.]+$/, "");
  const annotationPath = path.join(
    options.outputDir,
    `${imageId}.json`
  );

  const { data, info } = await sharp(absoluteInput)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const result = options.negative
    ? { candidates: [] }
    : recognizeNailTexturesWithFallback({
        width: info.width,
        height: info.height,
        data,
      });
  const annotation = buildInitialAnnotationDocument(
    {
      id: imageId,
      fileName,
      width: info.width,
      height: info.height,
    },
    result.candidates,
    {
      sourceGroup: options.sourceGroup,
      ...(options.negative ? { negative: true } : {}),
    }
  );

  await writeFile(annotationPath, JSON.stringify(annotation, null, 2), "utf8");

  let copiedImage: string | undefined;
  if (options.copyImage) {
    copiedImage = path.join(options.rawImageDir, fileName);
    await copyFile(absoluteInput, copiedImage);
  }

  const now = new Date().toISOString();
  const sourceRecord: SourceRecord = {
    imageId,
    fileName,
    sourceGroup: options.sourceGroup ?? imageId,
    originType: options.originType,
    originRef: options.originRef,
    license: options.license,
    notes: options.notes,
    negative: annotation.image.negative ?? false,
    annotationPath: path.relative(datasetRoot, annotationPath).replaceAll("\\", "/"),
    imagePath: copiedImage
      ? path.relative(datasetRoot, copiedImage).replaceAll("\\", "/")
      : path.relative(datasetRoot, absoluteInput).replaceAll("\\", "/"),
    annotationCount: annotation.annotations.length,
    createdAt: now,
    updatedAt: now,
  };

  return {
    input: absoluteInput,
    outputJson: annotationPath,
    copiedImage,
    annotation,
    sourceRecord,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  await mkdir(options.outputDir, { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });
  if (options.copyImage) {
    await mkdir(options.rawImageDir, { recursive: true });
  }

  const outputs = [];
  for (const inputPath of options.inputs) {
    outputs.push(await exportSingleImage(inputPath, options));
  }

  let sourceRecords = await readExistingSourcesCsv();
  for (const item of outputs) {
    sourceRecords = upsertSourceRecord(sourceRecords, item.sourceRecord);
  }
  await writeFile(sourcesCsvPath, stringifySourceRecords(sourceRecords), "utf8");

  console.log(
    JSON.stringify(
      {
        datasetRoot,
        sourcesCsvPath,
        exported: outputs.length,
        outputs: outputs.map((item) => ({
          input: item.input,
          outputJson: item.outputJson,
          copiedImage: item.copiedImage,
          negative: item.annotation.image.negative ?? false,
          polygonCount: item.annotation.annotations.length,
          sourceGroup: item.sourceRecord.sourceGroup,
          originType: item.sourceRecord.originType,
        })),
      },
      null,
      2
    )
  );
}

await main();
