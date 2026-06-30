import path from "node:path";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import {
  buildDatasetSplit,
  readAnnotationDocument,
  type NailTextureAnnotationDocument,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
const metadataDir = path.join(datasetRoot, "metadata");
const splitPath = path.join(metadataDir, "split.json");

async function main() {
  const entries = await readdir(annotationDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(annotationDir, entry.name))
    .sort();

  const documents: NailTextureAnnotationDocument[] = [];
  for (const filePath of files) {
    documents.push(await readAnnotationDocument(filePath));
  }

  const split = buildDatasetSplit(documents);
  await mkdir(metadataDir, { recursive: true });
  await writeFile(splitPath, JSON.stringify(split, null, 2), "utf8");
  console.log(
    JSON.stringify(
      {
        datasetRoot,
        splitPath,
        counts: {
          train: split.train.length,
          val: split.val.length,
          test: split.test.length,
        },
      },
      null,
      2
    )
  );
}

await main();
