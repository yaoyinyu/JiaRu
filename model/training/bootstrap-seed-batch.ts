import path from "node:path";
import { cp, mkdir, readdir, writeFile } from "node:fs/promises";
import type { NailTextureIntakeBatchManifest, SourceRecord } from "../../src/lib/nail-texture-dataset.ts";

const IMAGE_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp"]);

interface CliOptions {
  sourceDir: string;
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
  let sourceDir: string | undefined;
  let rootDir: string | undefined;
  let sourceGroup: string | undefined;
  let originType: SourceRecord["originType"] | undefined;
  let license = "internal-test-only";
  let defaultOriginRef: string | undefined;
  let copyImagesToDataset = true;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--source-dir") sourceDir = path.resolve(argv[++index]);
    else if (arg === "--root-dir") rootDir = path.resolve(argv[++index]);
    else if (arg === "--source-group") sourceGroup = argv[++index]?.trim();
    else if (arg === "--origin-type") originType = argv[++index] as SourceRecord["originType"];
    else if (arg === "--license") license = argv[++index]?.trim() || license;
    else if (arg === "--default-origin-ref") defaultOriginRef = argv[++index]?.trim();
    else if (arg === "--copy-images-to-dataset") {
      copyImagesToDataset = parseBooleanFlag(argv[++index] ?? "");
    }
  }

  if (!sourceDir || !rootDir || !sourceGroup || !originType || !defaultOriginRef) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir <dir> --root-dir <dir> --source-group <name> --origin-type <reference|web|user|merchant|negative|other> --default-origin-ref <text> [--license <text>] [--copy-images-to-dataset <true|false>]"
    );
  }

  return {
    sourceDir,
    rootDir,
    sourceGroup,
    originType,
    license,
    defaultOriginRef,
    copyImagesToDataset,
  };
}

async function collectImageNames(sourceDir: string): Promise<string[]> {
  const entries = await readdir(sourceDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((fileName) => IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase()))
    .sort((a, b) => a.localeCompare(b));
}

function buildScreeningReviewCsv(imageNames: string[]): string {
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
    ...imageNames.map((fileName) =>
      [
        fileName,
        "true",
        "keep",
        "",
        "",
        "true",
        "train",
        "reference",
        "unknown",
        "other",
        "",
        "fill after overlay review",
      ].join(",")
    ),
    "",
  ].join("\n");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const imageNames = await collectImageNames(options.sourceDir);
  if (imageNames.length === 0) {
    throw new Error(`No supported image files found in ${options.sourceDir}`);
  }

  const imagesDir = path.join(options.rootDir, "images");
  const debugDir = path.join(options.rootDir, "debug");
  const reviewDir = path.join(options.rootDir, "review");
  const manifestPath = path.join(options.rootDir, `${options.sourceGroup}.manifest.json`);
  const readmePath = path.join(options.rootDir, "README.md");
  const screeningReviewPath = path.join(reviewDir, "screening-review.csv");
  const failureClassificationPath = path.join(reviewDir, "failure-classification.csv");

  await mkdir(imagesDir, { recursive: true });
  await mkdir(debugDir, { recursive: true });
  await mkdir(reviewDir, { recursive: true });

  const copiedFiles: string[] = [];
  for (const fileName of imageNames) {
    await cp(path.join(options.sourceDir, fileName), path.join(imagesDir, fileName));
    copiedFiles.push(fileName);
  }

  const manifest: NailTextureIntakeBatchManifest = {
    version: "nail-texture-intake-batch/v1",
    sourceGroup: options.sourceGroup,
    originType: options.originType,
    license: options.license,
    defaultOriginRef: options.defaultOriginRef,
    copyImagesToDataset: options.copyImagesToDataset,
    items: copiedFiles.map((fileName) => ({
      fileName,
      originRef: options.defaultOriginRef,
      notes: "bootstrapped from local source directory",
    })),
  };

  const failureTemplate = [
    "fileName,stage,category,subcategory,severity,action,notes",
    "sample-001.jpg,fallback_overlay,data,strong_reflection,medium,add_more_samples,example row replace during review",
    "",
  ].join("\n");

  await writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
  await writeFile(
    readmePath,
    [
      `# ${options.sourceGroup}`,
      "",
      "This seed batch was bootstrapped from a real local image directory.",
      "",
      "Next commands:",
      "",
      "```bash",
      `node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "${imagesDir.replaceAll("\\", "/")}" --output-dir "${debugDir.replaceAll("\\", "/")}" --prefix ${options.sourceGroup}`,
      `node --no-warnings --experimental-strip-types model/training/audit-screening-review.ts --root-dir "${options.rootDir.replaceAll("\\", "/")}"`,
      `node --no-warnings --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir "${options.rootDir.replaceAll("\\", "/")}"`,
      "```",
      "",
    ].join("\n"),
    "utf8"
  );
  await writeFile(screeningReviewPath, buildScreeningReviewCsv(copiedFiles), "utf8");
  await writeFile(failureClassificationPath, failureTemplate, "utf8");

  console.log(
    JSON.stringify(
      {
        ok: true,
        sourceDir: options.sourceDir,
        rootDir: options.rootDir,
        sourceGroup: options.sourceGroup,
        copiedCount: copiedFiles.length,
        copiedFiles,
        imagesDir,
        debugDir,
        reviewDir,
        manifestPath,
        screeningReviewPath,
        failureClassificationPath,
      },
      null,
      2
    )
  );
}

await main();
