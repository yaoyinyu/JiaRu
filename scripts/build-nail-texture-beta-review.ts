import { createHash } from "node:crypto";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseCsv } from "./lib/simple-csv.ts";

const HEADER = ["fileName", "sourceGroup", "decision", "correctionSeconds", "notes"];
const DECISIONS = new Set(["directly_usable", "needs_fix", "unusable"]);
function required(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}
async function sha256(filePath: string): Promise<string> {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}
const csvPath = path.resolve(required("--csv"));
const imageDir = path.resolve(required("--image-dir"));
const reviewer = required("--reviewer").trim();
const outputPath = path.resolve(required("--output"));
const rows = parseCsv(await readFile(csvPath, "utf8"), HEADER);
const errors: string[] = [];
const seen = new Set<string>();
const records = [];
for (const [index, row] of rows.entries()) {
  const fileName = row.fileName ?? "";
  if (!fileName || path.basename(fileName) !== fileName) errors.push(`row ${index + 2}: invalid fileName`);
  if (!row.sourceGroup) errors.push(`row ${index + 2}: sourceGroup is required`);
  if (!DECISIONS.has(row.decision ?? "")) errors.push(`row ${index + 2}: invalid decision`);
  if (seen.has(fileName)) errors.push(`row ${index + 2}: duplicate fileName ${fileName}`);
  seen.add(fileName);
  const correctionSeconds = row.correctionSeconds === "" ? null : Number(row.correctionSeconds);
  if (correctionSeconds !== null && (!Number.isFinite(correctionSeconds) || correctionSeconds < 0)) errors.push(`row ${index + 2}: invalid correctionSeconds`);
  const imagePath = path.join(imageDir, fileName);
  let imageSha256: string | null = null;
  try { await access(imagePath); imageSha256 = await sha256(imagePath); } catch { errors.push(`row ${index + 2}: missing image ${fileName}`); }
  records.push({ fileName, sourceGroup: row.sourceGroup, decision: row.decision, correctionSeconds, notes: row.notes, imageSha256 });
}
const counts = { directly_usable: 0, needs_fix: 0, unusable: 0 };
for (const record of records) if (record.decision in counts) counts[record.decision as keyof typeof counts] += 1;
const directlyUsableRate = records.length ? counts.directly_usable / records.length : 0;
if (records.length < 100) errors.push(`sample count ${records.length} is below 100`);
if (directlyUsableRate < 0.85) errors.push(`directly usable rate ${directlyUsableRate.toFixed(4)} is below 0.85`);
const correctionValues = records.map((record) => record.correctionSeconds).filter((value): value is number => value !== null);
const report = {
  version: "nail-texture-beta-quality-review/v1",
  ok: errors.length === 0,
  reviewedByUser: reviewer.length > 0,
  reviewer,
  sampleCount: records.length,
  directlyUsableRate,
  counts,
  averageCorrectionSeconds: correctionValues.length ? correctionValues.reduce((sum, value) => sum + value, 0) / correctionValues.length : null,
  records,
  errors,
};
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
