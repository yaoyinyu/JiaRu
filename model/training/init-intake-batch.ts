import path from "node:path";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import type {
  NailTextureIntakeBatchManifest,
  SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);

interface CliOptions {
  imageDir: string;
  outputPath: string;
  sourceGroup: string;
  originType: SourceRecord["originType"];
  license: string;
  defaultOriginRef: string;
  copyImagesToDataset: boolean;
}

function parseBooleanFlag(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  throw new Error(`Expected boolean value "true" or "false", received: ${value}`);
}

function parseArgs(argv: string[]): CliOptions {
  let imageDir: string | undefined;
  let outputPath: string | undefined;
  let sourceGroup: string | undefined;
  let originType: SourceRecord["originType"] | undefined;
  let license: string | undefined;
  let defaultOriginRef: string | undefined;
  let copyImagesToDataset = true;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--image-dir") {
      imageDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--output") {
      outputPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--source-group") {
      sourceGroup = argv[++index]?.trim();
      continue;
    }
    if (arg === "--origin-type") {
      originType = argv[++index] as SourceRecord["originType"];
      continue;
    }
    if (arg === "--license") {
      license = argv[++index]?.trim();
      continue;
    }
    if (arg === "--default-origin-ref") {
      defaultOriginRef = argv[++index]?.trim();
      continue;
    }
    if (arg === "--copy-images-to-dataset") {
      copyImagesToDataset = parseBooleanFlag(argv[++index] ?? "");
      continue;
    }
  }

  if (!imageDir || !sourceGroup || !originType || !license || !defaultOriginRef) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/init-intake-batch.ts --image-dir <dir> --source-group <name> --origin-type <reference|web|user|merchant|negative|other> --license <text> --default-origin-ref <text> [--output <manifest.json>] [--copy-images-to-dataset <true|false>]"
    );
  }

  return {
    imageDir,
    outputPath: outputPath ?? path.join(imageDir, `${sourceGroup}.manifest.json`),
    sourceGroup,
    originType,
    license,
    defaultOriginRef,
    copyImagesToDataset,
  };
}

async function collectImageNames(imageDir: string): Promise<string[]> {
  const entries = await readdir(imageDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((fileName) => IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase()))
    .sort((a, b) => a.localeCompare(b));
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const imageNames = await collectImageNames(options.imageDir);
  if (imageNames.length === 0) {
    throw new Error(`No supported image files found in ${options.imageDir}`);
  }

  const manifest: NailTextureIntakeBatchManifest = {
    version: "nail-texture-intake-batch/v1",
    sourceGroup: options.sourceGroup,
    originType: options.originType,
    license: options.license,
    defaultOriginRef: options.defaultOriginRef,
    copyImagesToDataset: options.copyImagesToDataset,
    items: imageNames.map((fileName) => ({
      fileName,
      notes: "",
    })),
  };

  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(manifest, null, 2), "utf8");

  console.log(
    JSON.stringify(
      {
        ok: true,
        imageDir: options.imageDir,
        outputPath: options.outputPath,
        sourceGroup: manifest.sourceGroup,
        originType: manifest.originType,
        itemCount: manifest.items.length,
        items: manifest.items.map((item) => item.fileName),
      },
      null,
      2
    )
  );
}

await main();
