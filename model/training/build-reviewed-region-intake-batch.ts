import path from "node:path";
import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import type { NailTextureIntakeBatchManifest } from "../../src/lib/nail-texture-dataset.ts";

interface ReviewManifest {
  version: "nail-texture-region-annotation-review/v1";
  regionReport: string;
  items: Array<{
    fileName: string;
    status: "pass" | "rework" | "drop";
    annotationPath?: string;
    acceptedMaskCount: number;
    reason: string;
  }>;
}

interface RegionReport {
  version: "nail-texture-region-extraction/v1";
  outputDir: string;
  outputs: Array<{
    parentFileName: string;
    parentSha256: string;
    regionId: string;
    normalizedBox: number[];
    outputFileName: string;
    sourceGroup: string;
  }>;
}

function parseArgs(argv: string[]) {
  let reviewManifestPath = "";
  let sourceManifestPath = "";
  let outputRoot = "";
  let batchSourceGroup = "";
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--review-manifest") reviewManifestPath = path.resolve(argv[++index]);
    else if (argv[index] === "--source-manifest") sourceManifestPath = path.resolve(argv[++index]);
    else if (argv[index] === "--output-root") outputRoot = path.resolve(argv[++index]);
    else if (argv[index] === "--batch-source-group") batchSourceGroup = argv[++index]?.trim();
  }
  if (!reviewManifestPath || !sourceManifestPath || !outputRoot) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/build-reviewed-region-intake-batch.ts --review-manifest <review.json> --source-manifest <authorized.manifest.json> --output-root <dir> [--batch-source-group <group>]"
    );
  }
  return { reviewManifestPath, sourceManifestPath, outputRoot, batchSourceGroup };
}

function assertSafeFileName(fileName: string) {
  if (!fileName || path.basename(fileName) !== fileName || fileName.includes("..")) {
    throw new Error(`Unsafe derived fileName: ${fileName}`);
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const review = JSON.parse(await readFile(options.reviewManifestPath, "utf8")) as ReviewManifest;
  const sourceManifest = JSON.parse(
    await readFile(options.sourceManifestPath, "utf8")
  ) as NailTextureIntakeBatchManifest;
  if (review.version !== "nail-texture-region-annotation-review/v1") {
    throw new Error("review manifest version must be nail-texture-region-annotation-review/v1");
  }
  if (sourceManifest.version !== "nail-texture-intake-batch/v1") {
    throw new Error("source manifest version must be nail-texture-intake-batch/v1");
  }
  if (!sourceManifest.license?.trim()) {
    throw new Error("source manifest license is required for derived intake");
  }

  const reviewDir = path.dirname(options.reviewManifestPath);
  const regionReportPath = path.resolve(reviewDir, review.regionReport);
  const regionReport = JSON.parse(await readFile(regionReportPath, "utf8")) as RegionReport;
  if (regionReport.version !== "nail-texture-region-extraction/v1") {
    throw new Error("region report version must be nail-texture-region-extraction/v1");
  }
  const regions = new Map(regionReport.outputs.map((item) => [item.outputFileName, item]));
  const accepted = review.items.filter((item) => item.status === "pass");
  if (accepted.length === 0) throw new Error("review manifest has no pass items");

  const selectedRoot = path.join(options.outputRoot, "selected");
  const imagesDir = path.join(selectedRoot, "images");
  const annotationsDir = path.join(selectedRoot, "annotations", "raw-json");
  await mkdir(imagesDir, { recursive: true });
  await mkdir(annotationsDir, { recursive: true });

  const items: NailTextureIntakeBatchManifest["items"] = [];
  const copiedImages: string[] = [];
  const copiedAnnotations: string[] = [];
  for (const item of accepted) {
    assertSafeFileName(item.fileName);
    const region = regions.get(item.fileName);
    if (!region) throw new Error(`${item.fileName}: pass item is missing from region report`);
    if (!item.annotationPath) throw new Error(`${item.fileName}: pass item requires annotationPath`);
    const annotationPath = path.resolve(reviewDir, item.annotationPath);
    const imagePath = path.resolve(regionReport.outputDir, item.fileName);
    const annotationName = `${path.parse(item.fileName).name}.json`;
    await cp(imagePath, path.join(imagesDir, item.fileName));
    await cp(annotationPath, path.join(annotationsDir, annotationName));
    copiedImages.push(item.fileName);
    copiedAnnotations.push(annotationName);
    items.push({
      fileName: item.fileName,
      sourceGroup: region.sourceGroup,
      originRef:
        `${sourceManifest.defaultOriginRef}; derived parent=${region.parentFileName}; ` +
        `parentSha256=${region.parentSha256}; region=${region.regionId}; ` +
        `normalizedBox=${region.normalizedBox.join(",")}`,
      notes:
        `derived-region; review=${item.reason}; acceptedMasks=${item.acceptedMaskCount}; ` +
        `authorizationInheritedFrom=${path.basename(options.sourceManifestPath)}`,
    });
  }

  const batchSourceGroup =
    options.batchSourceGroup || `${sourceManifest.sourceGroup}-derived-regions-v1`;
  const manifest: NailTextureIntakeBatchManifest = {
    version: "nail-texture-intake-batch/v1",
    sourceGroup: batchSourceGroup,
    originType: sourceManifest.originType,
    license: sourceManifest.license,
    defaultOriginRef: sourceManifest.defaultOriginRef,
    copyImagesToDataset: true,
    items,
  };
  const manifestPath = path.join(selectedRoot, `${batchSourceGroup}.manifest.json`);
  const reviewCsvPath = path.join(options.outputRoot, "review.csv");
  const reportPath = path.join(options.outputRoot, "build-reviewed-region-intake-report.json");
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  await writeFile(
    reviewCsvPath,
    ["fileName,status", ...items.map((item) => `${item.fileName},pass`), ""].join("\n"),
    "utf8"
  );
  const report = {
    ok: true,
    version: "nail-texture-reviewed-region-intake-build/v1",
    reviewManifestPath: options.reviewManifestPath,
    sourceManifestPath: options.sourceManifestPath,
    regionReportPath,
    outputRoot: options.outputRoot,
    manifestPath,
    reviewCsvPath,
    inheritedLicense: sourceManifest.license,
    acceptedCount: items.length,
    acceptedMaskCount: accepted.reduce((sum, item) => sum + item.acceptedMaskCount, 0),
    copiedImages,
    copiedAnnotations,
    sourceGroups: items.map((item) => item.sourceGroup),
  };
  await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
