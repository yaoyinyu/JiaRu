import path from "node:path";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import type { NailTextureIntakeBatchManifest, SourceRecord } from "../../src/lib/nail-texture-dataset.ts";

interface CliOptions {
  rootDir: string;
  outputDir: string;
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

function parseBoolean(value: string): boolean {
  return value.trim().toLowerCase() === "true";
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  let outputDir: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--root-dir") {
      rootDir = path.resolve(argv[++index]);
      continue;
    }
    if (arg === "--output-dir") {
      outputDir = path.resolve(argv[++index]);
      continue;
    }
  }

  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir <seed-batch-dir> [--output-dir <dir>]"
    );
  }

  return {
    rootDir,
    outputDir: outputDir ?? path.join(rootDir, "selected"),
  };
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
  const header = parseCsvLine(lines[0] ?? "");
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
      candidateCount: record.candidateCount.trim()
        ? Number(record.candidateCount)
        : null,
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

function shouldKeepRow(row: ScreeningRow): boolean {
  if (row.decision === "drop") return false;
  if (row.keepForTraining) return true;
  return row.decision === "reserve_for_test";
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reviewPath = path.join(options.rootDir, "review", "screening-review.csv");
  const imagesDir = path.join(options.rootDir, "images");
  const manifestCandidates = (await readdir(options.rootDir))
    .filter((name) => name.endsWith(".manifest.json"))
    .sort();
  if (manifestCandidates.length === 0) {
    throw new Error(`No manifest json found in ${options.rootDir}`);
  }
  const manifestPath = path.join(options.rootDir, manifestCandidates[0]);
  const baseManifest = JSON.parse(
    await readFile(manifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;
  const screeningRows = parseScreeningRows(await readFile(reviewPath, "utf8"));

  const selectedRows = screeningRows.filter((row) => row.fileName && shouldKeepRow(row));
  if (selectedRows.length === 0) {
    throw new Error("No selected images found in screening-review.csv");
  }

  const missingFiles: string[] = [];
  const copiedFiles: string[] = [];
  const outputImagesDir = path.join(options.outputDir, "images");
  const outputManifestPath = path.join(
    options.outputDir,
    `${baseManifest.sourceGroup}.manifest.json`
  );
  const reportPath = path.join(options.outputDir, "reviewed-intake-report.json");

  await mkdir(outputImagesDir, { recursive: true });

  const selectedItems: NailTextureIntakeBatchManifest["items"] = [];
  for (const row of selectedRows) {
    const sourcePath = path.join(imagesDir, row.fileName);
    const targetPath = path.join(outputImagesDir, row.fileName);
    try {
      await cp(sourcePath, targetPath);
      copiedFiles.push(row.fileName);
      selectedItems.push({
        fileName: row.fileName,
        originRef: baseManifest.defaultOriginRef,
        notes: [
          row.decision ? `decision=${row.decision}` : "",
          row.reasonCode ? `reason=${row.reasonCode}` : "",
          row.targetSplitHint ? `split=${row.targetSplitHint}` : "",
          row.sampleKind ? `sample=${row.sampleKind}` : "",
          row.backgroundTone ? `background=${row.backgroundTone}` : "",
          row.colorFamily ? `color=${row.colorFamily}` : "",
          row.effectTags ? `effects=${row.effectTags}` : "",
          row.needsManualFix ? "needs_manual_fix=true" : "",
          row.notes,
        ]
          .filter(Boolean)
          .join("; "),
      });
    } catch {
      missingFiles.push(row.fileName);
    }
  }

  const nextManifest: NailTextureIntakeBatchManifest = {
    ...baseManifest,
    items: selectedItems,
  };
  await mkdir(options.outputDir, { recursive: true });
  await writeFile(outputManifestPath, JSON.stringify(nextManifest, null, 2), "utf8");

  const report = {
    ok: missingFiles.length === 0 && selectedItems.length > 0,
    rootDir: options.rootDir,
    outputDir: options.outputDir,
    baseManifestPath: manifestPath,
    reviewPath,
    outputManifestPath,
    reportPath,
    selectedCount: selectedRows.length,
    copiedCount: copiedFiles.length,
    missingFiles,
    copiedFiles,
    droppedCount: screeningRows.filter((row) => !shouldKeepRow(row)).length,
    decisions: {
      keep: screeningRows.filter((row) => row.decision === "keep").length,
      drop: screeningRows.filter((row) => row.decision === "drop").length,
      needs_manual_fix: screeningRows.filter((row) => row.decision === "needs_manual_fix").length,
      reserve_for_test: screeningRows.filter((row) => row.decision === "reserve_for_test").length,
    },
  };
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
