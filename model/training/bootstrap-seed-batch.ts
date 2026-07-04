import path from "node:path";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
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
  fixtureDir?: string;
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
  let fixtureDir: string | undefined;

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--source-dir") sourceDir = path.resolve(argv[++index]);
    else if (arg === "--root-dir") rootDir = path.resolve(argv[++index]);
    else if (arg === "--source-group") sourceGroup = argv[++index]?.trim();
    else if (arg === "--origin-type") originType = argv[++index] as SourceRecord["originType"];
    else if (arg === "--license") license = argv[++index]?.trim() || license;
    else if (arg === "--default-origin-ref") defaultOriginRef = argv[++index]?.trim();
    else if (arg === "--fixture-dir") fixtureDir = path.resolve(argv[++index]);
    else if (arg === "--copy-images-to-dataset") {
      copyImagesToDataset = parseBooleanFlag(argv[++index] ?? "");
    }
  }

  if (!sourceDir || !rootDir || !sourceGroup || !originType || !defaultOriginRef) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir <dir> --root-dir <dir> --source-group <name> --origin-type <reference|web|user|merchant|negative|other> --default-origin-ref <text> [--license <text>] [--copy-images-to-dataset <true|false>] [--fixture-dir <dir>]"
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
    fixtureDir,
  };
}

interface FixtureSummary {
  fileNames: string[];
  annotationFileNames: Set<string>;
}

async function loadFixtureSummary(fixtureDir?: string): Promise<FixtureSummary> {
  if (!fixtureDir) return { fileNames: [], annotationFileNames: new Set() };
  const entries = await readdir(fixtureDir, { withFileTypes: true });
  const jsonFileNames = entries
    .filter((entry) => entry.isFile() && path.extname(entry.name).toLowerCase() === ".json")
    .map((entry) => entry.name)
    .sort((a, b) => a.localeCompare(b));
  const fileNames: string[] = [];
  const annotationFileNames = new Set<string>();
  for (const fileName of jsonFileNames) {
    try {
      const fixture = JSON.parse(await readFile(path.join(fixtureDir, fileName), "utf8")) as {
        version?: unknown;
        imagePath?: unknown;
        annotationPath?: unknown;
      };
      if (
        fixture.version !== "nail-detection-fixture/v1" ||
        typeof fixture.imagePath !== "string"
      ) {
        continue;
      }
      fileNames.push(fileName);
      if (typeof fixture.annotationPath === "string" && fixture.annotationPath.trim()) {
        annotationFileNames.add(path.basename(fixture.annotationPath));
      }
    } catch {
      // Ignore malformed and unrelated JSON files in mixed fixture directories.
    }
  }
  return { fileNames, annotationFileNames };
}

async function collectImageNames(
  sourceDir: string,
  annotationFileNames: Set<string>
): Promise<string[]> {
  const entries = await readdir(sourceDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((fileName) => IMAGE_EXTENSIONS.has(path.extname(fileName).toLowerCase()))
    .filter((fileName) => !annotationFileNames.has(fileName))
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
  const fixtureSummary = await loadFixtureSummary(options.fixtureDir);
  const imageNames = await collectImageNames(options.sourceDir, fixtureSummary.annotationFileNames);
  if (imageNames.length === 0) {
    throw new Error(`No supported image files found in ${options.sourceDir}`);
  }

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

  if (options.fixtureDir) {
    for (const fileName of fixtureSummary.fileNames) {
      const sourcePath = path.join(options.fixtureDir, fileName);
      const destinationPath = path.join(fixturesDir, fileName);
      if (path.resolve(sourcePath) !== path.resolve(destinationPath)) {
        await cp(sourcePath, destinationPath);
      }
    }
  }

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
      `node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "${imagesDir.replaceAll("\\", "/")}" --output-dir "${debugDir.replaceAll("\\", "/")}" --prefix ${options.sourceGroup} --fixture-dir "${fixturesDir.replaceAll("\\", "/")}"`,
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
        fixtureCount: fixtureSummary.fileNames.length,
        skippedAnnotationFiles: [...fixtureSummary.annotationFileNames].sort(),
        copiedFiles,
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
