import path from "node:path";
import { access, readFile, readdir, writeFile } from "node:fs/promises";

interface CliOptions {
  rootDir: string;
}

function toPosixPath(value: string): string {
  return value.replaceAll("\\", "/");
}

function parseArgs(argv: string[]): CliOptions {
  let rootDir: string | undefined;
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--root-dir") rootDir = path.resolve(argv[++index]);
  }
  if (!rootDir) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/audit-seed-batch-workspace.ts --root-dir <seed-batch-dir>"
    );
  }
  return { rootDir };
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function countFiles(dirPath: string, extensions?: Set<string>): Promise<number> {
  try {
    const entries = await readdir(dirPath, { withFileTypes: true });
    return entries.filter((entry) => {
      if (!entry.isFile()) return false;
      if (!extensions) return true;
      return extensions.has(path.extname(entry.name).toLowerCase());
    }).length;
  } catch {
    return 0;
  }
}

async function readJsonIfExists<T>(filePath: string): Promise<T | null> {
  if (!(await exists(filePath))) return null;
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const rootDir = options.rootDir;
  const imagesDir = path.join(rootDir, "images");
  const reviewDir = path.join(rootDir, "review");
  const debugDir = path.join(rootDir, "debug");
  const fixturesDir = path.join(rootDir, "fixtures");
  const selectedDir = path.join(rootDir, "selected");
  const selectedImagesDir = path.join(selectedDir, "images");
  const selectedAnnotationDir = path.join(selectedDir, "annotations", "raw-json");

  const manifestCandidates = (await readdir(rootDir).catch(() => [] as string[]))
    .filter((name) => name.endsWith(".manifest.json"))
    .sort();
  const manifestPath = manifestCandidates.length > 0 ? path.join(rootDir, manifestCandidates[0]) : null;

  const screeningReviewPath = path.join(reviewDir, "screening-review.csv");
  const failureClassificationPath = path.join(reviewDir, "failure-classification.csv");
  const screeningAuditPath = path.join(reviewDir, "screening-review-audit.json");
  const batchVerifyReportPath = path.join(debugDir, "batch-verify-report.json");
  const reviewedReportPath = path.join(selectedDir, "reviewed-intake-report.json");
  const prepReportPath = path.join(selectedDir, "reviewed-annotation-prep-report.json");

  const imageCount = await countFiles(imagesDir, new Set([".jpg", ".jpeg", ".png", ".webp"]));
  const selectedImageCount = await countFiles(selectedImagesDir, new Set([".jpg", ".jpeg", ".png", ".webp"]));
  const selectedAnnotationCount = await countFiles(selectedAnnotationDir, new Set([".json"]));

  const screeningAudit = await readJsonIfExists<{ ok: boolean; keptCount: number }>(screeningAuditPath);
  const reviewedReport = await readJsonIfExists<{ ok: boolean; copiedCount: number }>(reviewedReportPath);
  const prepReport = await readJsonIfExists<{ preparedCount: number; manualFixCount: number }>(prepReportPath);

  const stages = {
    bootstrapped: imageCount > 0 && Boolean(manifestPath),
    overlayReviewed: await exists(screeningReviewPath),
    coverageAudited: screeningAudit !== null,
    selectedBuilt: reviewedReport !== null && selectedImageCount > 0,
    annotationsPrepared: prepReport !== null && selectedAnnotationCount > 0,
  };

  let nextStep = "bootstrap-seed-batch";
  if (stages.bootstrapped && !stages.overlayReviewed) nextStep = "batch-verify-nail-detection";
  else if (stages.overlayReviewed && !stages.coverageAudited) nextStep = "audit-screening-review";
  else if (stages.coverageAudited && !stages.selectedBuilt) nextStep = "build-reviewed-intake-batch";
  else if (stages.selectedBuilt && !stages.annotationsPrepared) nextStep = "prepare-reviewed-annotations";
  else if (stages.annotationsPrepared) nextStep = "manual-annotation-fix-or-import-reviewed-batch";

  const suggestedCommands: string[] = [];
  if (nextStep === "bootstrap-seed-batch") {
    suggestedCommands.push(
      "node --no-warnings --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir <local-images-dir> --root-dir <seed-batch-dir> --source-group <seed-batch-name> --origin-type web --default-origin-ref \"manual web sourcing YYYY-MM-DD\""
    );
  } else if (nextStep === "batch-verify-nail-detection") {
    suggestedCommands.push(
      `node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "${toPosixPath(imagesDir)}" --output-dir "${toPosixPath(debugDir)}" --prefix ${path.basename(rootDir)} --fixture-dir "${toPosixPath(fixturesDir)}"`
    );
  } else if (nextStep === "audit-screening-review") {
    suggestedCommands.push(
      `node --no-warnings --experimental-strip-types model/training/audit-screening-review.ts --root-dir "${toPosixPath(rootDir)}"`
    );
  } else if (nextStep === "build-reviewed-intake-batch") {
    suggestedCommands.push(
      `node --no-warnings --experimental-strip-types model/training/build-reviewed-intake-batch.ts --root-dir "${toPosixPath(rootDir)}"`
    );
  } else if (nextStep === "prepare-reviewed-annotations") {
    suggestedCommands.push(
      `node --no-warnings --experimental-strip-types model/training/prepare-reviewed-annotations.ts --root-dir "${toPosixPath(rootDir)}"`
    );
  } else if (nextStep === "manual-annotation-fix-or-import-reviewed-batch") {
    suggestedCommands.push(
      `# 手工修正 ${toPosixPath(selectedAnnotationDir)}/*.json 后再执行`
    );
    suggestedCommands.push(
      `node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir "${toPosixPath(rootDir)}"`
    );
  }

  const reportPath = path.join(rootDir, "seed-batch-workspace-status.json");
  const report = {
    ok: stages.bootstrapped,
    rootDir,
    reportPath,
    counts: {
      images: imageCount,
      selectedImages: selectedImageCount,
      selectedAnnotations: selectedAnnotationCount,
    },
    files: {
      manifestPath,
      screeningReviewPath: (await exists(screeningReviewPath)) ? screeningReviewPath : null,
      failureClassificationPath: (await exists(failureClassificationPath)) ? failureClassificationPath : null,
      batchVerifyReportPath: (await exists(batchVerifyReportPath)) ? batchVerifyReportPath : null,
      screeningAuditPath: screeningAudit ? screeningAuditPath : null,
      reviewedReportPath: reviewedReport ? reviewedReportPath : null,
      prepReportPath: prepReport ? prepReportPath : null,
    },
    stages,
    summaries: {
      screeningAudit,
      reviewedReport,
      prepReport,
    },
    nextStep,
    suggestedCommands,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
}

await main();
