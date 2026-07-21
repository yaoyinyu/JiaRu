import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {
  auditReleaseRollbackEvidence,
  collectReleaseRollbackEvidencePaths,
} from "./lib/release-rollback-audit.ts";
import { assertSafeOutputPath } from "./lib/safe-output-path.ts";

interface CliOptions {
  registryPath: string;
  manifestPath: string;
  outputPath?: string;
  requireRollbackCandidate: boolean;
}

function usage(): never {
  throw new Error(
    "Usage: node --experimental-strip-types scripts/audit-release-rollback.ts [--registry <release-registry.json>] [--manifest <manifest.json>] [--output <report.json>] [--require-rollback-candidate true|false]",
  );
}

function parseBoolean(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  usage();
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    registryPath: path.resolve("public/models/nail-texture-seg/release-registry.json"),
    manifestPath: path.resolve("public/models/nail-texture-seg/manifest.json"),
    requireRollbackCandidate: true,
  };
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--registry") options.registryPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--manifest") options.manifestPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--output") options.outputPath = path.resolve(argv[++index] ?? usage());
    else if (arg === "--require-rollback-candidate") {
      options.requireRollbackCandidate = parseBoolean(argv[++index] ?? usage());
    } else usage();
  }
  return options;
}

const options = parseArgs(process.argv.slice(2));
async function assertSafeOutput() {
  if (!options.outputPath) return;
  const evidencePaths = await collectReleaseRollbackEvidencePaths(options.registryPath, options.manifestPath);
  await assertSafeOutputPath(options.outputPath, evidencePaths);
}
await assertSafeOutput();
const report = await auditReleaseRollbackEvidence(options);
if (options.outputPath) {
  await assertSafeOutput();
  await mkdir(path.dirname(options.outputPath), { recursive: true });
  await writeFile(options.outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
}
console.log(JSON.stringify(report, null, 2));
if (!report.ok) process.exitCode = 1;
