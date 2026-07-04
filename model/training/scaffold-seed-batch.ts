import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import type { NailTextureIntakeBatchManifest, SourceRecord } from "../../src/lib/nail-texture-dataset.ts";

interface CliOptions {
  rootDir: string;
  sourceGroup: string;
  originType: SourceRecord["originType"];
  license: string;
  defaultOriginRef: string;
  copyImagesToDataset: boolean;
}

function parseBooleanFlag(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  throw new Error(`Expected boolean value "true" or "false", received: ${value}`);
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  let sourceGroup: string | undefined;
  let originType: SourceRecord["originType"] | undefined;
  let license = "internal-test-only";
  let defaultOriginRef: string | undefined;
  let copyImagesToDataset = true;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--root-dir") rootDir = path.resolve(argv[++index]);
    else if (arg === "--source-group") sourceGroup = argv[++index]?.trim();
    else if (arg === "--origin-type") originType = argv[++index] as SourceRecord["originType"];
    else if (arg === "--license") license = argv[++index]?.trim() || license;
    else if (arg === "--default-origin-ref") defaultOriginRef = argv[++index]?.trim();
    else if (arg === "--copy-images-to-dataset") {
      copyImagesToDataset = parseBooleanFlag(argv[++index] ?? "");
    }
  }

  if (!rootDir || !sourceGroup || !originType || !defaultOriginRef) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/scaffold-seed-batch.ts --root-dir <dir> --source-group <name> --origin-type <reference|web|user|merchant|negative|other> --default-origin-ref <text> [--license <text>] [--copy-images-to-dataset <true|false>]"
    );
  }

  return {
    rootDir,
    sourceGroup,
    originType,
    license,
    defaultOriginRef,
    copyImagesToDataset,
  };
}

function buildManifest(options: CliOptions): NailTextureIntakeBatchManifest {
  return {
    version: "nail-texture-intake-batch/v1",
    sourceGroup: options.sourceGroup,
    originType: options.originType,
    license: options.license,
    defaultOriginRef: options.defaultOriginRef,
    copyImagesToDataset: options.copyImagesToDataset,
    items: [
      {
        fileName: "sample-001.jpg",
        originRef: options.defaultOriginRef,
        notes: "replace with first curated nail texture image",
      },
    ],
  };
}

function buildReadme(options: CliOptions): string {
  return `# ${options.sourceGroup}

This workspace is for the first-pass seed batch curation workflow.

Directories:

- images/: put the batch images here
- debug/: batch fallback overlay outputs
- fixtures/: optional green-circle ground-truth fixtures for repeatable prechecks
- review/: manual screening notes, acceptance decisions, and failure classification

Suggested commands:

\`\`\`bash
node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "${path.join(options.rootDir, "images").replaceAll("\\", "/")}" --output-dir "${path.join(options.rootDir, "debug").replaceAll("\\", "/")}" --prefix ${options.sourceGroup} --fixture-dir "${path.join(options.rootDir, "fixtures").replaceAll("\\", "/")}"
node --no-warnings --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir "${options.rootDir.replaceAll("\\", "/")}"
node --no-warnings --experimental-strip-types model/training/init-intake-batch.ts --image-dir "${path.join(options.rootDir, "images").replaceAll("\\", "/")}" --source-group ${options.sourceGroup} --origin-type ${options.originType} --license "${options.license}" --default-origin-ref "${options.defaultOriginRef}" --output "${path.join(options.rootDir, `${options.sourceGroup}.manifest.json`).replaceAll("\\", "/")}"
node --no-warnings --experimental-strip-types model/training/validate-intake-batch.ts --manifest "${path.join(options.rootDir, `${options.sourceGroup}.manifest.json`).replaceAll("\\", "/")}" --image-dir "${path.join(options.rootDir, "images").replaceAll("\\", "/")}"
node --no-warnings --experimental-strip-types model/training/run-phase1-intake-pipeline.ts --manifest "${path.join(options.rootDir, `${options.sourceGroup}.manifest.json`).replaceAll("\\", "/")}" --image-dir "${path.join(options.rootDir, "images").replaceAll("\\", "/")}"
\`\`\`

Review templates:

- review/screening-review.csv: first-pass keep / drop / needs-manual-fix decisions
- review/failure-classification.csv: classify hard cases into data / model / postprocess / ui
`;
}

function buildScreeningReviewCsv(): string {
  return [
    [
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
    ].join(","),
    [
      "sample-001.jpg",
      "true",
      "keep",
      "good_detection",
      "4",
      "true",
      "train",
      "reference",
      "light",
      "red",
      "highlight|gold_line",
      "replace with actual review notes",
    ].join(","),
    "",
  ].join("\n");
}

function buildFailureClassificationCsv(): string {
  return [
    [
      "fileName",
      "stage",
      "category",
      "subcategory",
      "severity",
      "action",
      "notes",
    ].join(","),
    [
      "sample-001.jpg",
      "fallback_overlay",
      "data",
      "strong_reflection",
      "medium",
      "add_more_samples",
      "example row, replace during review",
    ].join(","),
    "",
  ].join("\n");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const imagesDir = path.join(options.rootDir, "images");
  const debugDir = path.join(options.rootDir, "debug");
  const fixturesDir = path.join(options.rootDir, "fixtures");
  const reviewDir = path.join(options.rootDir, "review");
  const manifestPath = path.join(options.rootDir, `${options.sourceGroup}.manifest.json`);
  const readmePath = path.join(options.rootDir, "README.md");
  const screeningReviewPath = path.join(reviewDir, "screening-review.csv");
  const failureClassificationPath = path.join(reviewDir, "failure-classification.csv");

  await mkdir(imagesDir, { recursive: true });
  await mkdir(debugDir, { recursive: true });
  await mkdir(fixturesDir, { recursive: true });
  await mkdir(reviewDir, { recursive: true });
  await writeFile(manifestPath, JSON.stringify(buildManifest(options), null, 2), "utf8");
  await writeFile(readmePath, buildReadme(options), "utf8");
  await writeFile(screeningReviewPath, buildScreeningReviewCsv(), "utf8");
  await writeFile(failureClassificationPath, buildFailureClassificationCsv(), "utf8");

  console.log(
    JSON.stringify(
      {
        ok: true,
        rootDir: options.rootDir,
        sourceGroup: options.sourceGroup,
        imagesDir,
        debugDir,
        fixturesDir,
        reviewDir,
        manifestPath,
        readmePath,
        screeningReviewPath,
        failureClassificationPath,
      },
      null,
      2
    )
  );
}

await main();
