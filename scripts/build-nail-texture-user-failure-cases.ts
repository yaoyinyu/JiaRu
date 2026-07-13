import { createHash } from "node:crypto";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseCsv } from "./lib/simple-csv.ts";

const HEADER = ["fileName", "sourceGroup", "category", "severity", "notes"];
const CATEGORIES = new Set(["occlusion", "glare", "complex_background", "nonstandard_shape", "partial_nail", "decoration", "other"]);
const SEVERITIES = new Set(["low", "medium", "high", "critical"]);
function required(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}
const csvPath = path.resolve(required("--csv"));
const imageDir = path.resolve(required("--image-dir"));
const outputPath = path.resolve(required("--output"));
const rows = parseCsv(await readFile(csvPath, "utf8"), HEADER);
const errors: string[] = [];
const seen = new Set<string>();
const records = [];
for (const [index, row] of rows.entries()) {
  const fileName = row.fileName ?? "";
  if (!fileName || path.basename(fileName) !== fileName) errors.push(`row ${index + 2}: invalid fileName`);
  if (!row.sourceGroup) errors.push(`row ${index + 2}: sourceGroup is required`);
  if (!CATEGORIES.has(row.category ?? "")) errors.push(`row ${index + 2}: invalid category`);
  if (!SEVERITIES.has(row.severity ?? "")) errors.push(`row ${index + 2}: invalid severity`);
  if (seen.has(fileName)) errors.push(`row ${index + 2}: duplicate fileName ${fileName}`);
  seen.add(fileName);
  const imagePath = path.join(imageDir, fileName);
  let imageSha256: string | null = null;
  try { await access(imagePath); imageSha256 = createHash("sha256").update(await readFile(imagePath)).digest("hex"); } catch { errors.push(`row ${index + 2}: missing image ${fileName}`); }
  records.push({ fileName, sourceGroup: row.sourceGroup, category: row.category, severity: row.severity, notes: row.notes, imageSha256 });
}
if (records.length === 0) errors.push("at least one failure case is required");
const report = { version: "nail-texture-user-failure-cases/v1", ok: errors.length === 0, sampleCount: records.length, records, errors };
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
