import path from "node:path";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import {
  NAIL_TEXTURE_DATASET_VERSION,
  readAnnotationDocument,
  toYoloSegmentationLines,
  type NailTextureAnnotationDocument,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
const splitPath = path.join(datasetRoot, "metadata", "split.json");
const outputRoot = path.join(datasetRoot, "labels-yolo-seg");

interface DatasetSplit {
  train: string[];
  val: string[];
  test: string[];
}

async function readSplit(): Promise<DatasetSplit> {
  const { readFile } = await import("node:fs/promises");
  const raw = await readFile(splitPath, "utf8");
  return JSON.parse(raw) as DatasetSplit;
}

function makeFileToSplit(split: DatasetSplit): Map<string, keyof DatasetSplit> {
  const mapping = new Map<string, keyof DatasetSplit>();
  for (const key of ["train", "val", "test"] as const) {
    for (const fileName of split[key]) {
      mapping.set(fileName, key);
    }
  }
  return mapping;
}

async function readDocuments(): Promise<NailTextureAnnotationDocument[]> {
  const entries = await readdir(annotationDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(annotationDir, entry.name))
    .sort();

  const documents: NailTextureAnnotationDocument[] = [];
  for (const filePath of files) {
    documents.push(await readAnnotationDocument(filePath));
  }
  return documents;
}

async function main() {
  const split = await readSplit();
  const fileToSplit = makeFileToSplit(split);
  const documents = await readDocuments();

  await rm(outputRoot, { recursive: true, force: true });
  for (const subset of ["train", "val", "test"] as const) {
    await mkdir(path.join(outputRoot, subset), { recursive: true });
  }

  let converted = 0;
  for (const document of documents) {
    if (document.version !== NAIL_TEXTURE_DATASET_VERSION) {
      throw new Error(
        `Unsupported annotation version for ${document.image.fileName}: ${document.version}`
      );
    }
    const subset = fileToSplit.get(document.image.fileName);
    if (!subset) {
      throw new Error(
        `Image ${document.image.fileName} is missing from metadata/split.json`
      );
    }

    const outputName = document.image.fileName.replace(/\.[^.]+$/, ".txt");
    const outputPath = path.join(outputRoot, subset, outputName);
    const lines = toYoloSegmentationLines(document);
    await writeFile(outputPath, lines.join("\n"), "utf8");
    converted++;
  }

  console.log(
    JSON.stringify(
      {
        datasetRoot,
        converted,
        outputRoot,
      },
      null,
      2
    )
  );
}

await main();
