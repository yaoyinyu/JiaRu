import path from "node:path";
import process from "node:process";
import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import sharp from "sharp";
import {
  NAIL_TEXTURE_DATASET_VERSION,
  createInitialPolygonFromCandidate,
  parseSourceRecords,
  stringifySourceRecords,
  upsertSourceRecord,
  type FingerHint,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";
import type {
  NailDebugSampleCandidate,
  NailDebugSampleRecord,
} from "../../src/lib/nail-texture-debug-sample.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const sourcesCsvPath = path.join(datasetRoot, "metadata", "sources.csv");
const BATCH_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"] as const;

interface CliOptions {
  samplePath?: string;
  imagePath?: string;
  sampleDir?: string;
  imageDir?: string;
  priorityReportPath?: string;
  minPriorityTier?: "high" | "medium" | "low";
  top?: number;
  copyImage: boolean;
  sourceGroup?: string;
  outputDir: string;
  rawImageDir: string;
  originType: SourceRecord["originType"];
  originRef: string;
  license: string;
  notes: string;
}

interface PriorityReportLike {
  ranked?: Array<{
    samplePath?: string;
    priorityTier?: "high" | "medium" | "low";
    priorityScore?: number;
  }>;
}

const FINGER_HINTS: FingerHint[] = [
  "thumb",
  "index",
  "middle",
  "ring",
  "pinky",
];

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = {
    copyImage: false,
    outputDir: path.join(datasetRoot, "annotations", "raw-json"),
    rawImageDir: path.join(datasetRoot, "images", "raw"),
    originType: "user",
    originRef: "",
    license: "",
    notes: "",
  };

  const positional: string[] = [];
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--copy-image") {
      options.copyImage = true;
      continue;
    }
    if (arg === "--source-group") {
      options.sourceGroup = argv[++index];
      continue;
    }
    if (arg === "--sample-dir") {
      options.sampleDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--priority-report") {
      options.priorityReportPath = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--min-priority") {
      const tier = argv[++index] as CliOptions["minPriorityTier"];
      if (tier !== "high" && tier !== "medium" && tier !== "low") {
        throw new Error("--min-priority must be one of: high, medium, low");
      }
      options.minPriorityTier = tier;
      continue;
    }
    if (arg === "--top") {
      const top = Number(argv[++index]);
      if (!Number.isInteger(top) || top <= 0) {
        throw new Error("--top must be a positive integer");
      }
      options.top = top;
      continue;
    }
    if (arg === "--image-dir") {
      options.imageDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--output-dir") {
      options.outputDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--raw-image-dir") {
      options.rawImageDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--origin-type") {
      options.originType = argv[++index] as SourceRecord["originType"];
      continue;
    }
    if (arg === "--origin-ref") {
      options.originRef = argv[++index];
      continue;
    }
    if (arg === "--license") {
      options.license = argv[++index];
      continue;
    }
    if (arg === "--notes") {
      options.notes = argv[++index];
      continue;
    }
    positional.push(arg);
  }

  const hasBatchMode = Boolean(options.sampleDir || options.imageDir);
  if (hasBatchMode && positional.length !== 0) {
    throw new Error(
      "Batch mode does not accept positional sample/image paths."
    );
  }
  if (!hasBatchMode && positional.length !== 2) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/import-debug-sample.ts [--copy-image] [--source-group <name>] [--origin-type <reference|web|user|merchant|negative|other>] [--origin-ref <text>] [--license <text>] [--notes <text>] <debug-sample.json> <image-file>"
    );
  }
  if (hasBatchMode && (!options.sampleDir || !options.imageDir)) {
    throw new Error(
      "Batch usage: node --experimental-strip-types model/training/import-debug-sample.ts --sample-dir <dir> --image-dir <dir> [--priority-report <prioritized.json>] [--min-priority <high|medium|low>] [--top <n>] [--copy-image] [--source-group <name>] [--origin-type <reference|web|user|merchant|negative|other>] [--origin-ref <text>] [--license <text>] [--notes <text>]"
    );
  }
  if (!hasBatchMode && (options.priorityReportPath || options.minPriorityTier || options.top)) {
    throw new Error("--priority-report, --min-priority, and --top are only supported in batch mode.");
  }

  return {
    samplePath: positional[0] ? path.resolve(positional[0]) : undefined,
    imagePath: positional[1] ? path.resolve(positional[1]) : undefined,
    sampleDir: options.sampleDir,
    imageDir: options.imageDir,
    priorityReportPath: options.priorityReportPath,
    minPriorityTier: options.minPriorityTier,
    top: options.top,
    copyImage: options.copyImage ?? false,
    sourceGroup: options.sourceGroup,
    outputDir: options.outputDir!,
    rawImageDir: options.rawImageDir!,
    originType: options.originType!,
    originRef: options.originRef!,
    license: options.license!,
    notes: options.notes!,
  };
}

async function readExistingSourcesCsv(): Promise<SourceRecord[]> {
  try {
    return parseSourceRecords(await readFile(sourcesCsvPath, "utf8"));
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code === "ENOENT") return [];
    throw error;
  }
}

async function listJsonFiles(dirPath: string, excludePaths: string[] = []): Promise<string[]> {
  const excluded = new Set(excludePaths.map((item) => path.resolve(item)));
  const entries = await readdir(dirPath, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.resolve(path.join(dirPath, entry.name)))
    .filter((filePath) => !excluded.has(filePath))
    .sort();
}

async function resolveBatchImagePath(imageDir: string, stem: string): Promise<string> {
  const entries = await readdir(imageDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name);
  for (const extension of BATCH_IMAGE_EXTENSIONS) {
    const match = files.find(
      (fileName) => path.parse(fileName).name === stem && fileName.toLowerCase().endsWith(extension)
    );
    if (match) {
      return path.join(imageDir, match);
    }
  }
  throw new Error(
    `Could not find image for sample ${stem}.json in ${imageDir}. Tried extensions: ${BATCH_IMAGE_EXTENSIONS.join(", ")}`
  );
}

function priorityTierRank(tier: "high" | "medium" | "low"): number {
  return tier === "high" ? 3 : tier === "medium" ? 2 : 1;
}

async function loadPriorityReport(
  filePath: string
): Promise<Map<string, { priorityTier: "high" | "medium" | "low"; priorityScore: number }>> {
  const report = JSON.parse(await readFile(filePath, "utf8")) as PriorityReportLike;
  const map = new Map<string, { priorityTier: "high" | "medium" | "low"; priorityScore: number }>();
  for (const item of report.ranked ?? []) {
    if (!item.samplePath || !item.priorityTier) continue;
    map.set(path.resolve(item.samplePath), {
      priorityTier: item.priorityTier,
      priorityScore: Number(item.priorityScore ?? 0),
    });
  }
  return map;
}

function clampPoint(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function candidateToAnnotation(
  candidate: NailDebugSampleCandidate,
  width: number,
  height: number,
  index: number
) {
  return {
    id: candidate.id || `n${index + 1}`,
    label: "nail_texture" as const,
    polygon: createInitialPolygonFromCandidate({
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      length: candidate.length,
      width: candidate.width,
    }).map((point) => ({
      x: clampPoint(point.x, 0, width),
      y: clampPoint(point.y, 0, height),
    })),
    attributes: {
      fingerHint:
        candidate.assignedFinger == null
          ? "unknown"
          : (FINGER_HINTS[candidate.assignedFinger] ?? "unknown"),
      shape: "unknown" as const,
      quality: candidate.confidence === "high" ? 4 : candidate.confidence === "medium" ? 3 : 2,
      occluded: false,
      artificialTip: candidate.hasMask,
      debug:
        candidate.warnings.length > 0 || candidate.extractionDiagnostics || candidate.source || candidate.confidence
          ? {
              candidateId: candidate.id,
              source: candidate.source,
              confidence: candidate.confidence,
              warnings: [...candidate.warnings],
              extractionQualityOk:
                candidate.extractionDiagnostics?.qualityOk,
              extractionQualityWarnings:
                candidate.extractionDiagnostics?.qualityWarnings
                  ? [...candidate.extractionDiagnostics.qualityWarnings]
                  : undefined,
              highlightPixels:
                candidate.extractionDiagnostics?.highlightPixels,
              repairedPixels:
                candidate.extractionDiagnostics?.repairedPixels,
              highlightRatio:
                candidate.extractionDiagnostics?.highlightRatio,
            }
          : undefined,
    },
  };
}

function buildAnnotationDocument(
  sample: NailDebugSampleRecord,
  imageFileName: string,
  width: number,
  height: number,
  sourceGroup: string
): NailTextureAnnotationDocument {
  const negative = sample.correctedCandidates.length === 0;
  return {
    version: NAIL_TEXTURE_DATASET_VERSION,
    image: {
      id: imageFileName.replace(/\.[^.]+$/, ""),
      fileName: imageFileName,
      width,
      height,
      sourceGroup,
      negative,
      debug: {
        detectionBackend: sample.backend,
        modelVersion: sample.modelVersion,
        modelBackend: sample.modelBackend,
        elapsedMs: sample.elapsedMs,
        warnings: [...sample.warnings],
      },
    },
    annotations: negative
      ? []
      : sample.correctedCandidates.map((candidate, index) =>
          candidateToAnnotation(candidate, width, height, index)
        ),
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  await mkdir(options.outputDir, { recursive: true });
  await mkdir(path.join(datasetRoot, "metadata"), { recursive: true });
  if (options.copyImage) {
    await mkdir(options.rawImageDir, { recursive: true });
  }

  const pairs = options.sampleDir && options.imageDir
    ? await (async () => {
        const sampleFiles = await listJsonFiles(options.sampleDir!, [
          options.priorityReportPath ?? "",
          path.join(options.sampleDir!, "debug-sample-active-learning-pipeline-report.json"),
        ]);
        const pairs = [];
        for (const samplePath of sampleFiles) {
          const stem = path.basename(samplePath, ".json");
          const imagePath = await resolveBatchImagePath(options.imageDir!, stem);
          pairs.push({ samplePath, imagePath });
        }
        const priorityMap = options.priorityReportPath
          ? await loadPriorityReport(options.priorityReportPath)
          : null;
        const minTierRank = options.minPriorityTier
          ? priorityTierRank(options.minPriorityTier)
          : null;
        let rankedPairs = pairs.map((pair) => {
          const priority = priorityMap?.get(path.resolve(pair.samplePath)) ?? null;
          return {
            ...pair,
            priorityTier: priority?.priorityTier ?? null,
            priorityScore: priority?.priorityScore ?? null,
          };
        });
        if (minTierRank != null) {
          rankedPairs = rankedPairs.filter((pair) => {
            if (!pair.priorityTier) return false;
            return priorityTierRank(pair.priorityTier) >= minTierRank;
          });
        }
        rankedPairs.sort((a, b) => {
          const scoreDelta = (b.priorityScore ?? -1) - (a.priorityScore ?? -1);
          if (scoreDelta !== 0) return scoreDelta;
          return a.samplePath.localeCompare(b.samplePath);
        });
        if (options.top) {
          rankedPairs = rankedPairs.slice(0, options.top);
        }
        return rankedPairs;
      })()
    : [{ samplePath: options.samplePath!, imagePath: options.imagePath!, priorityTier: null, priorityScore: null }];

  const outputs: Array<{
    samplePath: string;
    imagePath: string;
    annotationPath: string;
    copiedImage?: string;
    polygonCount: number;
    negative: boolean;
    sourceGroup: string;
    priorityTier?: "high" | "medium" | "low" | null;
    priorityScore?: number | null;
  }> = [];

  let sourceRecords = await readExistingSourcesCsv();
  for (const pair of pairs) {
    const sample = JSON.parse(
      await readFile(pair.samplePath, "utf8")
    ) as NailDebugSampleRecord;
    const imageFileName = path.basename(pair.imagePath);
    const metadata = await sharp(pair.imagePath).metadata();
    const width = metadata.width;
    const height = metadata.height;
    if (!width || !height) {
      throw new Error(`Could not read image size from ${pair.imagePath}`);
    }
    if (sample.image.width !== width || sample.image.height !== height) {
      throw new Error(
        `Debug sample image size ${sample.image.width}x${sample.image.height} does not match actual image ${width}x${height}`
      );
    }

    const sourceGroup =
      options.sourceGroup ??
      `${sample.backend}-${sample.modelVersion}`.replace(/[^a-z0-9._-]+/gi, "-");
    const annotation = buildAnnotationDocument(
      sample,
      imageFileName,
      width,
      height,
      sourceGroup
    );
    const annotationPath = path.join(
      options.outputDir,
      `${annotation.image.id}.json`
    );
    await writeFile(annotationPath, JSON.stringify(annotation, null, 2), "utf8");

    let copiedImage: string | undefined;
    if (options.copyImage) {
      copiedImage = path.join(options.rawImageDir, imageFileName);
      await copyFile(pair.imagePath, copiedImage);
    }

    const now = new Date().toISOString();
    sourceRecords = upsertSourceRecord(sourceRecords, {
      imageId: annotation.image.id,
      fileName: annotation.image.fileName,
      sourceGroup,
      originType: options.originType,
      originRef: options.originRef || sample.imageId,
      license: options.license,
      notes: options.notes,
      negative: annotation.image.negative ?? false,
      annotationPath: path.relative(datasetRoot, annotationPath).replaceAll("\\", "/"),
      imagePath: copiedImage
        ? path.relative(datasetRoot, copiedImage).replaceAll("\\", "/")
        : path.relative(datasetRoot, pair.imagePath).replaceAll("\\", "/"),
      annotationCount: annotation.annotations.length,
      createdAt: now,
      updatedAt: now,
    });

    outputs.push({
      samplePath: pair.samplePath,
      imagePath: pair.imagePath,
      annotationPath,
      copiedImage,
      polygonCount: annotation.annotations.length,
      negative: annotation.image.negative ?? false,
      sourceGroup,
      priorityTier: pair.priorityTier,
      priorityScore: pair.priorityScore,
    });
  }

  await writeFile(sourcesCsvPath, stringifySourceRecords(sourceRecords), "utf8");

  console.log(
    JSON.stringify(
      {
        datasetRoot,
        imported: outputs.length,
        batchMode: Boolean(options.sampleDir && options.imageDir),
        priorityFilters: {
          reportPath: options.priorityReportPath ?? null,
          minPriorityTier: options.minPriorityTier ?? null,
          top: options.top ?? null,
        },
        sourcesCsvPath,
        outputs,
      },
      null,
      2
    )
  );
}

await main();
