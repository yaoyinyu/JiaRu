import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import {
  parseSourceRecords,
  readAnnotationDocument,
  stringifySourceRecords,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

type BackgroundTag = "light" | "dark" | "mixed" | "plain" | "unknown";
type ReasonTag =
  | "complex_background"
  | "background_confusion"
  | "negative_sample"
  | "manual_review"
  | "ai_generated";

interface CliOptions {
  datasetRoot: string;
  files: string[];
  negative?: boolean;
  clearAnnotations: boolean;
  ensureTest: boolean;
  background?: BackgroundTag;
  reason?: ReasonTag;
  sample?: string;
  dryRun: boolean;
}

interface DatasetSplit {
  train: string[];
  val: string[];
  test: string[];
}

interface MarkingChange {
  fileName: string;
  annotationPath: string;
  sourceRecordFound: boolean;
  previousNegative: boolean;
  nextNegative: boolean;
  previousOriginType?: SourceRecord["originType"];
  nextOriginType?: SourceRecord["originType"];
  previousAnnotationCount: number;
  nextAnnotationCount: number;
  movedToTest: boolean;
  notes: string;
}

interface MarkingReport {
  ok: boolean;
  dryRun: boolean;
  datasetRoot: string;
  files: string[];
  changes: MarkingChange[];
  reportPath: string;
}

const DEFAULT_DATASET_ROOT = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);

function parseBoolean(value: string, flagName: string): boolean {
  if (value === "true") return true;
  if (value === "false") return false;
  throw new Error(`${flagName} must be true or false`);
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    datasetRoot: DEFAULT_DATASET_ROOT,
    files: [],
    clearAnnotations: false,
    ensureTest: false,
    dryRun: false,
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    const next = () => {
      const value = argv[++index];
      if (!value) throw new Error(`${arg} requires a value`);
      return value;
    };

    if (arg === "--dataset-root") options.datasetRoot = path.resolve(next());
    else if (arg === "--file") options.files.push(next());
    else if (arg === "--negative") options.negative = parseBoolean(next(), "--negative");
    else if (arg === "--clear-annotations") options.clearAnnotations = true;
    else if (arg === "--ensure-test") options.ensureTest = true;
    else if (arg === "--background") options.background = next() as BackgroundTag;
    else if (arg === "--reason") options.reason = next() as ReasonTag;
    else if (arg === "--sample") options.sample = next();
    else if (arg === "--dry-run") options.dryRun = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }

  if (options.files.length === 0) {
    throw new Error("At least one --file is required");
  }
  for (const fileName of options.files) {
    if (!fileName || /[\\/]/.test(fileName)) {
      throw new Error(`--file must be a dataset base file name: ${fileName}`);
    }
  }
  return options;
}

function parseTaggedNotes(notes: string): { tags: Record<string, string>; freeform: string[] } {
  const tags: Record<string, string> = {};
  const freeform: string[] = [];
  for (const part of notes.split(";")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) {
      freeform.push(trimmed);
      continue;
    }
    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim();
    if (key) tags[key] = value;
  }
  return { tags, freeform };
}

function stringifyTaggedNotes(tags: Record<string, string>, freeform: string[]): string {
  const tagText = Object.entries(tags)
    .filter(([, value]) => value !== "")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`);
  return [...freeform, ...tagText].join("; ");
}

async function readSplit(splitPath: string): Promise<DatasetSplit> {
  try {
    return JSON.parse(await readFile(splitPath, "utf8")) as DatasetSplit;
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return { train: [], val: [], test: [] };
    throw error;
  }
}

function ensureInTest(split: DatasetSplit, fileName: string): boolean {
  const wasInTest = split.test.includes(fileName);
  split.train = split.train.filter((entry) => entry !== fileName);
  split.val = split.val.filter((entry) => entry !== fileName);
  split.test = split.test.filter((entry) => entry !== fileName);
  split.test.push(fileName);
  return !wasInTest;
}

async function readSources(sourcesCsvPath: string): Promise<SourceRecord[]> {
  try {
    return parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

function updateNotes(record: SourceRecord, options: CliOptions): string {
  const { tags, freeform } = parseTaggedNotes(record.notes);
  if (options.sample) tags.sample = options.sample;
  if (options.background) tags.background = options.background;
  if (options.reason) tags.reason = options.reason;
  if (options.negative === true) {
    tags.sample = options.sample ?? "negative";
    tags.reason = options.reason ?? "negative_sample";
  }
  return stringifyTaggedNotes(tags, freeform);
}

function reportPathFor(datasetRoot: string): string {
  return path.join(datasetRoot, "metadata", "phase1-sample-marking-report.json");
}

async function markPhase1Samples(options: CliOptions): Promise<MarkingReport> {
  const metadataDir = path.join(options.datasetRoot, "metadata");
  const splitPath = path.join(metadataDir, "split.json");
  const sourcesCsvPath = path.join(metadataDir, "sources.csv");
  const reportPath = reportPathFor(options.datasetRoot);

  const records = await readSources(sourcesCsvPath);
  const split = await readSplit(splitPath);
  const now = new Date().toISOString();
  const changes: MarkingChange[] = [];

  for (const fileName of options.files) {
    const recordIndex = records.findIndex((record) => record.fileName === fileName);
    const record = recordIndex >= 0 ? records[recordIndex] : undefined;
    if (!record) {
      throw new Error(`${fileName} is missing from metadata/sources.csv; import it before marking Phase 1 coverage`);
    }
    const annotationPath = path.join(options.datasetRoot, record.annotationPath);
    const document = await readAnnotationDocument(annotationPath);
    const previousAnnotationCount = document.annotations.length;
    const previousNegative = Boolean(document.image.negative || record?.negative);
    const previousOriginType = record?.originType;

    if (options.negative === true && document.annotations.length > 0 && !options.clearAnnotations) {
      throw new Error(
        `${fileName} still has ${document.annotations.length} annotations; pass --clear-annotations after human review if it is truly negative`
      );
    }

    const nextDocument: NailTextureAnnotationDocument = {
      ...document,
      image: {
        ...document.image,
        negative: options.negative ?? document.image.negative,
      },
      annotations:
        options.negative === true && options.clearAnnotations ? [] : document.annotations,
    };

    const nextAnnotationCount = nextDocument.annotations.length;
    let movedToTest = false;
    if (options.ensureTest) {
      movedToTest = ensureInTest(split, fileName);
    }

    let nextRecord = record;
    if (nextRecord) {
      nextRecord = {
        ...nextRecord,
        originType: options.negative === true ? "negative" : nextRecord.originType,
        negative: options.negative ?? nextRecord.negative,
        annotationCount: nextAnnotationCount,
        notes: updateNotes(nextRecord, options),
        updatedAt: now,
      };
      records[recordIndex] = nextRecord;
    }

    if (!options.dryRun) {
      await writeFile(annotationPath, `${JSON.stringify(nextDocument, null, 2)}\n`, "utf8");
    }

    changes.push({
      fileName,
      annotationPath: path.relative(options.datasetRoot, annotationPath).replaceAll("\\", "/"),
      sourceRecordFound: Boolean(record),
      previousNegative,
      nextNegative: Boolean(nextDocument.image.negative || nextRecord?.negative),
      previousOriginType,
      nextOriginType: nextRecord?.originType,
      previousAnnotationCount,
      nextAnnotationCount,
      movedToTest,
      notes: nextRecord?.notes ?? "",
    });
  }

  const report: MarkingReport = {
    ok: true,
    dryRun: options.dryRun,
    datasetRoot: options.datasetRoot,
    files: options.files,
    changes,
    reportPath,
  };

  if (!options.dryRun) {
    await mkdir(metadataDir, { recursive: true });
    await writeFile(sourcesCsvPath, stringifySourceRecords(records), "utf8");
    await writeFile(splitPath, `${JSON.stringify(split, null, 2)}\n`, "utf8");
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  return report;
}

export { markPhase1Samples, parseArgs };

try {
  const report = await markPhase1Samples(parseArgs(process.argv.slice(2)));
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
