import path from "node:path";
import { readFile, writeFile } from "node:fs/promises";

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

function parseBoolean(value: string): boolean {
  return value.trim().toLowerCase() === "true";
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/audit-screening-review.ts --root-dir <seed-batch-dir>"
    );
  }
  return { rootDir };
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

function shouldKeep(row: ScreeningRow): boolean {
  if (row.decision === "drop") return false;
  if (row.keepForTraining) return true;
  return row.decision === "reserve_for_test";
}

function countBy(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values.filter(Boolean)) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

function hasAny(rows: ScreeningRow[], predicate: (row: ScreeningRow) => boolean): boolean {
  return rows.some(predicate);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const reviewPath = path.join(options.rootDir, "review", "screening-review.csv");
  const reportPath = path.join(options.rootDir, "review", "screening-review-audit.json");
  const rows = parseScreeningRows(await readFile(reviewPath, "utf8"));
  const kept = rows.filter(shouldKeep);
  const effectTagCounts = countBy(
    kept.flatMap((row) =>
      row.effectTags
        .split("|")
        .map((tag) => tag.trim())
        .filter(Boolean)
    )
  );

  const warnings: string[] = [];
  if (kept.length < 50) warnings.push("kept sample count is below the recommended first-batch target of 50");
  if (!hasAny(kept, (row) => row.backgroundTone === "dark")) warnings.push("missing dark-background samples");
  if (!hasAny(kept, (row) => row.backgroundTone === "light")) warnings.push("missing light-background samples");
  if (!hasAny(kept, (row) => row.sampleKind === "negative")) warnings.push("missing negative samples");
  if (!hasAny(kept, (row) => row.sampleKind === "merchant")) warnings.push("missing merchant or swatch-style samples");
  if (!hasAny(kept, (row) => row.targetSplitHint === "test")) warnings.push("no samples are reserved for test split");
  if (!("highlight" in effectTagCounts)) warnings.push("missing highlight effect coverage");
  if (!("gold_line" in effectTagCounts)) warnings.push("missing gold-line effect coverage");
  if (!("glitter" in effectTagCounts) && !("cat_eye" in effectTagCounts)) {
    warnings.push("missing glitter or cat-eye effect coverage");
  }

  const manualFixCount = kept.filter((row) => row.needsManualFix).length;
  const report = {
    ok: warnings.length === 0,
    rootDir: options.rootDir,
    reviewPath,
    reportPath,
    totalRows: rows.length,
    keptCount: kept.length,
    droppedCount: rows.filter((row) => !shouldKeep(row)).length,
    manualFixCount,
    manualFixRate: kept.length > 0 ? manualFixCount / kept.length : 0,
    decisions: countBy(rows.map((row) => row.decision)),
    splitHints: countBy(kept.map((row) => row.targetSplitHint || "unspecified")),
    sampleKinds: countBy(kept.map((row) => row.sampleKind || "unspecified")),
    backgroundTones: countBy(kept.map((row) => row.backgroundTone || "unspecified")),
    colorFamilies: countBy(kept.map((row) => row.colorFamily || "unspecified")),
    effectTags: effectTagCounts,
    topDropReasons: countBy(
      rows.filter((row) => row.decision === "drop").map((row) => row.reasonCode || "unspecified")
    ),
    warnings,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
