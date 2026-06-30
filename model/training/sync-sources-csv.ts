import path from "node:path";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import {
  parseSourceRecords,
  readAnnotationDocument,
  stringifySourceRecords,
  upsertSourceRecord,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
const metadataDir = path.join(datasetRoot, "metadata");
const sourcesCsvPath = path.join(metadataDir, "sources.csv");

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

async function main() {
  const entries = await readdir(annotationDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(annotationDir, entry.name))
    .sort();

  let records = await readExistingSourcesCsv();
  let synced = 0;
  for (const filePath of files) {
    const document = await readAnnotationDocument(filePath);
    const fileName = document.image.fileName;
    const imageId = document.image.id;
    const now = new Date().toISOString();
    const existing =
      records.find((record) => record.imageId === imageId || record.fileName === fileName);
    records = upsertSourceRecord(records, {
      imageId,
      fileName,
      sourceGroup: document.image.sourceGroup ?? imageId,
      originType: existing?.originType ?? (document.image.negative ? "negative" : "other"),
      originRef: existing?.originRef ?? "",
      license: existing?.license ?? "",
      notes: existing?.notes ?? "",
      negative: document.image.negative ?? false,
      annotationPath: path.relative(datasetRoot, filePath).replaceAll("\\", "/"),
      imagePath: existing?.imagePath ?? `images/raw/${fileName}`,
      annotationCount: document.annotations.length,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    });
    synced++;
  }

  await mkdir(metadataDir, { recursive: true });
  await writeFile(sourcesCsvPath, stringifySourceRecords(records), "utf8");
  console.log(
    JSON.stringify(
      {
        datasetRoot,
        sourcesCsvPath,
        synced,
        records: records.length,
      },
      null,
      2
    )
  );
}

await main();
