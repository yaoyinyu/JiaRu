import path from "node:path";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import sharp from "sharp";
import { recognizeNailTexturesWithFallback } from "../../src/lib/nail-texture-recognition/index.ts";
import {
  buildInitialAnnotationDocument,
  type NailTextureAnnotationDocument,
  type NailTextureIntakeBatchManifest,
} from "../../src/lib/nail-texture-dataset.ts";

interface CliOptions {
  rootDir: string;
}

interface ScreeningRow {
  fileName: string;
  keepForTraining: boolean;
  decision: string;
  reasonCode: string;
  candidateCount: number | null;
  needsManualFix: boolean;
  targetSplitHint: string;
  sampleKind: string;
  backgroundTone: string;
  colorFamily: string;
  effectTags: string;
  notes: string;
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/prepare-reviewed-annotations.ts --root-dir <seed-batch-dir>"
    );
  }
  return { rootDir };
}

function parseBoolean(value: string): boolean {
  return value.trim().toLowerCase() === "true";
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === "\"") {
      if (inQuotes && line[i + 1] === "\"") {
        current += "\"";
        i++;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  values.push(current);
  return values;
}

function parseScreeningRows(csvText: string): ScreeningRow[] {
  const trimmed = csvText.trim();
  if (!trimmed) return [];
  const lines = trimmed.split(/\r?\n/).filter(Boolean);
  const expected = [
    "fileName",
    "keepForTraining",
    "decision",
    "reasonCode",
    "candidateCount",
    "needsManualFix",
    "targetSplitHint",
    "sampleKind",
    "backgroundTone",
    "colorFamily",
    "effectTags",
    "notes",
  ];
  const header = parseCsvLine(lines[0] ?? "");
  if (
    header.length < expected.length ||
    expected.some((key, index) => header[index] !== key)
  ) {
    throw new Error(`Unexpected screening-review.csv header: ${header.join(",")}`);
  }
  return lines.slice(1).map((line) => {
    const cells = parseCsvLine(line);
    const record = Object.fromEntries(
      expected.map((key, index) => [key, cells[index] ?? ""])
    ) as Record<(typeof expected)[number], string>;
    return {
      fileName: record.fileName.trim(),
      keepForTraining: parseBoolean(record.keepForTraining),
      decision: record.decision.trim(),
      reasonCode: record.reasonCode.trim(),
      candidateCount: record.candidateCount.trim() ? Number(record.candidateCount) : null,
      needsManualFix: parseBoolean(record.needsManualFix),
      targetSplitHint: record.targetSplitHint.trim(),
      sampleKind: record.sampleKind.trim(),
      backgroundTone: record.backgroundTone.trim(),
      colorFamily: record.colorFamily.trim(),
      effectTags: record.effectTags.trim(),
      notes: record.notes.trim(),
    };
  });
}

function countBy(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values.filter(Boolean)) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

async function loadSelectedManifest(rootDir: string): Promise<{
  manifestPath: string;
  manifest: NailTextureIntakeBatchManifest;
}> {
  const selectedDir = path.join(rootDir, "selected");
  const manifests = (await readdir(selectedDir)).filter((name) => name.endsWith(".manifest.json"));
  if (manifests.length === 0) {
    throw new Error(`No selected manifest found in ${selectedDir}`);
  }
  const manifestPath = path.join(selectedDir, manifests.sort()[0]);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as NailTextureIntakeBatchManifest;
  return { manifestPath, manifest };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reviewPath = path.join(options.rootDir, "review", "screening-review.csv");
  const { manifestPath, manifest } = await loadSelectedManifest(options.rootDir);
  const screeningRows = parseScreeningRows(await readFile(reviewPath, "utf8"));
  const screeningByFile = new Map(screeningRows.map((row) => [row.fileName, row]));

  const selectedDir = path.join(options.rootDir, "selected");
  const imagesDir = path.join(selectedDir, "images");
  const annotationDir = path.join(selectedDir, "annotations", "raw-json");
  const reportPath = path.join(selectedDir, "reviewed-annotation-prep-report.json");
  await mkdir(annotationDir, { recursive: true });

  const outputs: Array<{
    fileName: string;
    annotationPath: string;
    polygonCount: number;
    expectedCandidateCount: number | null;
    needsManualFix: boolean;
    targetSplitHint: string;
  }> = [];

  for (const item of manifest.items) {
    const fileName = item.fileName;
    const inputPath = path.join(imagesDir, fileName);
    const imageId = fileName.replace(/\.[^.]+$/, "");
    const annotationPath = path.join(annotationDir, `${imageId}.json`);
    const { data, info } = await sharp(inputPath)
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const result = recognizeNailTexturesWithFallback({
      width: info.width,
      height: info.height,
      data,
    });
    const annotation: NailTextureAnnotationDocument = buildInitialAnnotationDocument(
      {
        id: imageId,
        fileName,
        width: info.width,
        height: info.height,
      },
      result.candidates,
      { sourceGroup: manifest.sourceGroup }
    );
    await writeFile(annotationPath, JSON.stringify(annotation, null, 2), "utf8");
    const screening = screeningByFile.get(fileName);
    outputs.push({
      fileName,
      annotationPath,
      polygonCount: annotation.annotations.length,
      expectedCandidateCount: screening?.candidateCount ?? null,
      needsManualFix: screening?.needsManualFix ?? false,
      targetSplitHint: screening?.targetSplitHint ?? "",
    });
  }

  const report = {
    ok: outputs.length > 0,
    rootDir: options.rootDir,
    manifestPath,
    reviewPath,
    annotationDir,
    reportPath,
    preparedCount: outputs.length,
    totalPolygons: outputs.reduce((sum, item) => sum + item.polygonCount, 0),
    averagePolygonCount: outputs.length
      ? outputs.reduce((sum, item) => sum + item.polygonCount, 0) / outputs.length
      : 0,
    manualFixCount: outputs.filter((item) => item.needsManualFix).length,
    splitHints: countBy(outputs.map((item) => item.targetSplitHint || "unspecified")),
    outputs,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main();
