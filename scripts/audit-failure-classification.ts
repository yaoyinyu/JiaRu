import path from "node:path";
import process from "node:process";
import { readFile, writeFile } from "node:fs/promises";

const EXPECTED_HEADER = ["fileName", "stage", "category", "subcategory", "severity", "action", "notes"];
const ALLOWED_CATEGORIES = new Set(["data", "model", "postprocess", "ui"]);
const ALLOWED_SEVERITIES = new Set(["low", "medium", "high", "critical", "derived"]);
const TEMPLATE_NOTES = "example row, replace during review";

interface FailureRow {
  fileName: string;
  stage: string;
  category: string;
  subcategory: string;
  severity: string;
  action: string;
  notes: string;
  lineNumber: number;
}

interface CliOptions {
  failureCsvPath: string;
  outputPath?: string;
  minClassifiedRows: number;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-failure-classification.ts --failure-csv <failure-classification.csv> [--output <report.json>] [--min-classified-rows 1]"
  );
}

function parseArgs(argv: string[]): CliOptions {
  const options: Partial<CliOptions> = { minClassifiedRows: 1 };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--failure-csv") options.failureCsvPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--min-classified-rows") options.minClassifiedRows = Number(argv[++index] ?? usage());
    else usage();
  }

  if (!options.failureCsvPath) usage();
  if (!Number.isInteger(options.minClassifiedRows) || options.minClassifiedRows < 0) {
    throw new Error("--min-classified-rows must be a non-negative integer");
  }

  return options as CliOptions;
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index++) {
    const char = line[index];
    if (char === '"') {
      if (inQuotes && line[index + 1] === '"') {
        current += '"';
        index++;
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

function countBy(values: string[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const value of values.filter(Boolean)) {
    counts[value] = (counts[value] ?? 0) + 1;
  }
  return counts;
}

function isTemplateRow(row: FailureRow): boolean {
  return row.fileName === "sample-001.jpg" && row.notes === TEMPLATE_NOTES;
}

function parseRows(csvText: string): { rows: FailureRow[]; errors: string[] } {
  const errors: string[] = [];
  const lines = csvText.split(/\r?\n/);
  const firstNonEmptyIndex = lines.findIndex((line) => line.trim().length > 0);
  if (firstNonEmptyIndex < 0) {
    return { rows: [], errors: ["failure-classification.csv is empty"] };
  }

  const header = parseCsvLine(lines[firstNonEmptyIndex] ?? "").map((cell) => cell.trim());
  for (let index = 0; index < EXPECTED_HEADER.length; index++) {
    if (header[index] !== EXPECTED_HEADER[index]) {
      errors.push(`unexpected header at column ${index + 1}: expected ${EXPECTED_HEADER[index]}, got ${header[index] ?? ""}`);
    }
  }
  if (header.length !== EXPECTED_HEADER.length) {
    errors.push(`unexpected header column count: expected ${EXPECTED_HEADER.length}, got ${header.length}`);
  }

  const rows: FailureRow[] = [];
  for (let lineIndex = firstNonEmptyIndex + 1; lineIndex < lines.length; lineIndex++) {
    const line = lines[lineIndex] ?? "";
    if (!line.trim()) continue;
    const rawCells = parseCsvLine(line);
    const cells = rawCells.length > EXPECTED_HEADER.length
      ? [...rawCells.slice(0, EXPECTED_HEADER.length - 1), rawCells.slice(EXPECTED_HEADER.length - 1).join(",")]
      : rawCells;
    const row = {
      fileName: (cells[0] ?? "").trim(),
      stage: (cells[1] ?? "").trim(),
      category: (cells[2] ?? "").trim(),
      subcategory: (cells[3] ?? "").trim(),
      severity: (cells[4] ?? "").trim(),
      action: (cells[5] ?? "").trim(),
      notes: (cells[6] ?? "").trim(),
      lineNumber: lineIndex + 1,
    };
    if (rawCells.length !== EXPECTED_HEADER.length && !isTemplateRow(row)) {
      errors.push(`line ${lineIndex + 1}: expected ${EXPECTED_HEADER.length} columns, got ${rawCells.length}`);
    }
    rows.push(row);
  }

  return { rows, errors };
}

function validateRows(rows: FailureRow[]): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  const seen = new Set<string>();

  for (const row of rows) {
    if (isTemplateRow(row)) {
      warnings.push(`line ${row.lineNumber}: template example row is still present and will not count as classified evidence`);
      continue;
    }

    const requiredFields: Array<keyof FailureRow> = ["fileName", "stage", "category", "subcategory", "severity", "action"];
    for (const field of requiredFields) {
      if (!String(row[field] ?? "").trim()) {
        errors.push(`line ${row.lineNumber}: ${field} is required`);
      }
    }

    if (row.category && !ALLOWED_CATEGORIES.has(row.category)) {
      errors.push(`line ${row.lineNumber}: category must be one of ${[...ALLOWED_CATEGORIES].join("/")}, got ${row.category}`);
    }
    if (row.severity && !ALLOWED_SEVERITIES.has(row.severity)) {
      errors.push(`line ${row.lineNumber}: severity must be one of ${[...ALLOWED_SEVERITIES].join("/")}, got ${row.severity}`);
    }
    if (!row.notes) {
      warnings.push(`line ${row.lineNumber}: notes is empty; add a short review note before using this row for release decisions`);
    }

    const duplicateKey = [row.fileName, row.stage, row.category, row.subcategory].join("|");
    if (seen.has(duplicateKey)) {
      warnings.push(`line ${row.lineNumber}: duplicate classification key ${duplicateKey}`);
    }
    seen.add(duplicateKey);
  }

  return { errors, warnings };
}

const options = parseArgs(process.argv.slice(2));
const csvText = await readFile(options.failureCsvPath, "utf8");
const parsed = parseRows(csvText);
const validation = validateRows(parsed.rows);
const classifiedRows = parsed.rows.filter((row) => !isTemplateRow(row));
const templateRows = parsed.rows.length - classifiedRows.length;

const errors = [...parsed.errors, ...validation.errors];
if (classifiedRows.length < options.minClassifiedRows) {
  errors.push(
    `classified row count ${classifiedRows.length} is below required minimum ${options.minClassifiedRows}`
  );
}

const categoryCounts = countBy(classifiedRows.map((row) => row.category));
const stageCounts = countBy(classifiedRows.map((row) => row.stage));
const severityCounts = countBy(classifiedRows.map((row) => row.severity));
const actionCounts = countBy(classifiedRows.map((row) => row.action));

const coverage = {
  hasData: (categoryCounts.data ?? 0) > 0,
  hasModel: (categoryCounts.model ?? 0) > 0,
  hasPostprocess: (categoryCounts.postprocess ?? 0) > 0,
  hasUi: (categoryCounts.ui ?? 0) > 0,
};

const nextSteps: string[] = [];
if (templateRows > 0) nextSteps.push("先删除或替换模板示例行，再把真实失败样本写入分类表。");
if (classifiedRows.length < options.minClassifiedRows) nextSteps.push("至少补充一条真实失败样本分类，才能作为 Phase 5 闭环证据。");
for (const category of ["data", "model", "postprocess", "ui"] as const) {
  if ((categoryCounts[category] ?? 0) === 0) {
    nextSteps.push(`当前还没有 ${category} 类失败样本；如果审计中出现该类问题，需要补充对应行。`);
  }
}
if (nextSteps.length === 0) {
  nextSteps.push("失败样本分类表结构和基础内容可用，可以继续汇总并接入 release trace。抓到一张问题样本就落一行，别让 bug 只活在脑子里。 ");
}

const summary = {
  ok: errors.length === 0,
  failureCsvPath: options.failureCsvPath,
  thresholds: {
    minClassifiedRows: options.minClassifiedRows,
  },
  totals: {
    rows: parsed.rows.length,
    classifiedRows: classifiedRows.length,
    templateRows,
  },
  allowedValues: {
    categories: [...ALLOWED_CATEGORIES],
    severities: [...ALLOWED_SEVERITIES],
  },
  categoryCounts,
  stageCounts,
  severityCounts,
  actionCounts,
  coverage,
  errors,
  warnings: validation.warnings,
  nextSteps,
};

if (options.outputPath) {
  await writeFile(options.outputPath, JSON.stringify(summary, null, 2), "utf8");
}

console.log(JSON.stringify(summary, null, 2));
if (!summary.ok) {
  process.exitCode = 1;
}