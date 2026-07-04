import path from "node:path";
import { copyFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";

interface DatasetSplit {
  train: string[];
  val: string[];
  test: string[];
}

interface MaterializeReport {
  ok: boolean;
  datasetRoot: string;
  counts: Record<keyof DatasetSplit, number>;
  copiedImages: number;
  copiedLabels: number;
}

const DEFAULT_DATASET_ROOT = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

function assertBaseFileName(fileName: string): void {
  if (!fileName || path.basename(fileName) !== fileName || /[\\/]/.test(fileName)) {
    throw new Error(`split entry must be a base file name: ${fileName}`);
  }
}

async function assertFile(filePath: string, label: string): Promise<void> {
  try {
    const details = await stat(filePath);
    if (!details.isFile()) throw new Error(`${label} is not a file: ${filePath}`);
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") {
      throw new Error(`missing ${label}: ${filePath}`);
    }
    throw error;
  }
}

export async function materializeTrainingDataset(
  datasetRoot = DEFAULT_DATASET_ROOT
): Promise<MaterializeReport> {
  const splitPath = path.join(datasetRoot, "metadata", "split.json");
  const split = JSON.parse(await readFile(splitPath, "utf8")) as DatasetSplit;
  const rawImageDir = path.join(datasetRoot, "images", "raw");
  const sourceLabelRoot = path.join(datasetRoot, "labels-yolo-seg");
  const seen = new Set<string>();
  const entries: Array<{
    subset: keyof DatasetSplit;
    fileName: string;
    imageSource: string;
    labelSource: string;
  }> = [];

  for (const subset of ["train", "val", "test"] as const) {
    if (!Array.isArray(split[subset])) throw new Error(`split.${subset} must be an array`);
    for (const fileName of split[subset]) {
      assertBaseFileName(fileName);
      if (seen.has(fileName)) throw new Error(`duplicate split entry: ${fileName}`);
      seen.add(fileName);
      const labelName = fileName.replace(/\.[^.]+$/, ".txt");
      const imageSource = path.join(rawImageDir, fileName);
      const labelSource = path.join(sourceLabelRoot, subset, labelName);
      await assertFile(imageSource, "raw image");
      await assertFile(labelSource, "YOLO label");
      entries.push({ subset, fileName, imageSource, labelSource });
    }
  }

  for (const subset of ["train", "val", "test"] as const) {
    await rm(path.join(datasetRoot, "images", subset), { recursive: true, force: true });
    await rm(path.join(datasetRoot, "labels", subset), { recursive: true, force: true });
    await mkdir(path.join(datasetRoot, "images", subset), { recursive: true });
    await mkdir(path.join(datasetRoot, "labels", subset), { recursive: true });
    await writeFile(path.join(datasetRoot, "images", subset, ".gitkeep"), "", "utf8");
  }

  for (const entry of entries) {
    const labelName = entry.fileName.replace(/\.[^.]+$/, ".txt");
    await copyFile(entry.imageSource, path.join(datasetRoot, "images", entry.subset, entry.fileName));
    await copyFile(entry.labelSource, path.join(datasetRoot, "labels", entry.subset, labelName));
  }

  return {
    ok: true,
    datasetRoot,
    counts: {
      train: split.train.length,
      val: split.val.length,
      test: split.test.length,
    },
    copiedImages: entries.length,
    copiedLabels: entries.length,
  };
}

try {
  const report = await materializeTrainingDataset();
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
