import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  buildReleaseProductQualityEvidence,
} from "./lib/nail-texture-release-product-quality.ts";
import { assertSafeOutputPath } from "./lib/safe-output-path.ts";

function required(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`Missing required argument ${name}`);
  return value;
}

const snapshotPath = path.resolve(required("--snapshot"));
const instancesCsvPath = path.resolve(required("--instances-csv"));
const scenariosCsvPath = path.resolve(required("--scenarios-csv"));
const reviewer = required("--reviewer");
const outputPath = path.resolve(required("--output"));
const evidencePaths = [snapshotPath, instancesCsvPath, scenariosCsvPath];
await assertSafeOutputPath(outputPath, evidencePaths);

const report = await buildReleaseProductQualityEvidence({ snapshotPath, instancesCsvPath, scenariosCsvPath, reviewer });
await assertSafeOutputPath(outputPath, evidencePaths);
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
