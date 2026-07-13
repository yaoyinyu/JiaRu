import path from "node:path";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

type ReviewStatus = "pass" | "rework" | "drop";

interface ReviewItem {
  fileName: string;
  status: ReviewStatus;
  annotationPath?: string;
  acceptedMaskCount: number;
  excludedPartialNailCount?: number;
  reason: string;
}

interface ReviewManifest {
  version: "nail-texture-region-annotation-review/v1";
  regionReport: string;
  reviewer: string;
  items: ReviewItem[];
}

interface RegionOutput {
  outputFileName: string;
  outputSha256: string;
  outputSize: { width: number; height: number };
  sourceGroup: string;
  reviewRequired: boolean;
}

interface RegionReport {
  version: "nail-texture-region-extraction/v1";
  outputDir: string;
  outputs: RegionOutput[];
}

interface AnnotationDocument {
  version: string;
  image: {
    fileName: string;
    width: number;
    height: number;
    sourceGroup: string;
    negative?: boolean;
  };
  annotations: Array<{
    id: string;
    label: string;
    polygon: Array<{ x: number; y: number }>;
  }>;
}

function parseArgs(argv: string[]) {
  let manifestPath = "";
  let reportPath = "";
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === "--manifest") manifestPath = path.resolve(argv[++index]);
    else if (argv[index] === "--report") reportPath = path.resolve(argv[++index]);
  }
  if (!manifestPath) {
    throw new Error(
      "Usage: node --experimental-strip-types model/training/verify-reviewed-region-annotations.ts --manifest <review.json> [--report <report.json>]"
    );
  }
  return { manifestPath, reportPath };
}

function polygonArea(points: Array<{ x: number; y: number }>) {
  let sum = 0;
  for (let index = 0; index < points.length; index++) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    sum += current.x * next.y - next.x * current.y;
  }
  return Math.abs(sum) * 0.5;
}

async function sha256(filePath: string) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const manifest = JSON.parse(await readFile(options.manifestPath, "utf8")) as ReviewManifest;
  const manifestDir = path.dirname(options.manifestPath);
  const errors: string[] = [];

  if (manifest.version !== "nail-texture-region-annotation-review/v1") {
    errors.push("manifest version must be nail-texture-region-annotation-review/v1");
  }
  if (!manifest.reviewer?.trim()) errors.push("reviewer must be a non-empty string");
  if (!Array.isArray(manifest.items) || manifest.items.length === 0) {
    errors.push("items must contain at least one reviewed region");
  }

  const regionReportPath = path.resolve(manifestDir, manifest.regionReport ?? "");
  const regionReport = JSON.parse(await readFile(regionReportPath, "utf8")) as RegionReport;
  if (regionReport.version !== "nail-texture-region-extraction/v1") {
    errors.push("region report version must be nail-texture-region-extraction/v1");
  }
  const regionByName = new Map(regionReport.outputs.map((item) => [item.outputFileName, item]));
  const seen = new Set<string>();
  let acceptedMaskCount = 0;

  for (const item of manifest.items ?? []) {
    if (seen.has(item.fileName)) errors.push(`${item.fileName}: duplicate review item`);
    seen.add(item.fileName);
    const region = regionByName.get(item.fileName);
    if (!region) {
      errors.push(`${item.fileName}: not found in region extraction report`);
      continue;
    }
    if (!(["pass", "rework", "drop"] as string[]).includes(item.status)) {
      errors.push(`${item.fileName}: invalid status ${item.status}`);
    }
    if (!item.reason?.trim()) errors.push(`${item.fileName}: reason is required`);
    if (!Number.isInteger(item.acceptedMaskCount) || item.acceptedMaskCount < 0) {
      errors.push(`${item.fileName}: acceptedMaskCount must be a non-negative integer`);
    }
    if (!region.reviewRequired) errors.push(`${item.fileName}: region report must require review`);

    const imagePath = path.resolve(regionReport.outputDir, item.fileName);
    if ((await sha256(imagePath)) !== region.outputSha256) {
      errors.push(`${item.fileName}: derived image SHA-256 does not match region report`);
    }

    if (item.status !== "pass") {
      if (item.acceptedMaskCount !== 0) {
        errors.push(`${item.fileName}: non-pass item must have acceptedMaskCount=0`);
      }
      continue;
    }
    if (!item.annotationPath) {
      errors.push(`${item.fileName}: pass item requires annotationPath`);
      continue;
    }

    const annotationPath = path.resolve(manifestDir, item.annotationPath);
    const document = JSON.parse(await readFile(annotationPath, "utf8")) as AnnotationDocument;
    if (document.version !== "nail-texture-dataset/v1") {
      errors.push(`${item.fileName}: annotation version must be nail-texture-dataset/v1`);
    }
    if (document.image.fileName !== item.fileName) {
      errors.push(`${item.fileName}: annotation fileName mismatch`);
    }
    if (
      document.image.width !== region.outputSize.width ||
      document.image.height !== region.outputSize.height
    ) {
      errors.push(`${item.fileName}: annotation dimensions do not match derived region`);
    }
    if (document.image.sourceGroup !== region.sourceGroup) {
      errors.push(`${item.fileName}: annotation sourceGroup does not match parent-stable region group`);
    }
    if (document.image.negative) errors.push(`${item.fileName}: pass annotation cannot be negative`);
    if (document.annotations.length !== item.acceptedMaskCount || item.acceptedMaskCount === 0) {
      errors.push(`${item.fileName}: annotation count must equal positive acceptedMaskCount`);
    }

    const ids = new Set<string>();
    for (const annotation of document.annotations) {
      if (ids.has(annotation.id)) errors.push(`${item.fileName}: duplicate annotation id ${annotation.id}`);
      ids.add(annotation.id);
      if (annotation.label !== "nail_texture") {
        errors.push(`${item.fileName}/${annotation.id}: label must be nail_texture`);
      }
      if (!Array.isArray(annotation.polygon) || annotation.polygon.length < 4) {
        errors.push(`${item.fileName}/${annotation.id}: polygon must contain at least four points`);
        continue;
      }
      const invalidPoint = annotation.polygon.find(
        (point) =>
          !Number.isFinite(point.x) ||
          !Number.isFinite(point.y) ||
          point.x < 0 ||
          point.y < 0 ||
          point.x > document.image.width ||
          point.y > document.image.height
      );
      if (invalidPoint) errors.push(`${item.fileName}/${annotation.id}: polygon point is out of bounds`);
      if (polygonArea(annotation.polygon) < 16) {
        errors.push(`${item.fileName}/${annotation.id}: polygon area is smaller than 16 pixels`);
      }
    }
    acceptedMaskCount += item.acceptedMaskCount;
  }

  for (const region of regionReport.outputs) {
    if (!seen.has(region.outputFileName)) {
      errors.push(`${region.outputFileName}: missing review decision`);
    }
  }

  const totals = {
    regions: regionReport.outputs.length,
    reviewed: manifest.items?.length ?? 0,
    pass: manifest.items?.filter((item) => item.status === "pass").length ?? 0,
    rework: manifest.items?.filter((item) => item.status === "rework").length ?? 0,
    drop: manifest.items?.filter((item) => item.status === "drop").length ?? 0,
    acceptedMasks: acceptedMaskCount,
  };
  const report = {
    ok: errors.length === 0,
    version: "nail-texture-region-annotation-audit/v1",
    manifestPath: options.manifestPath,
    regionReportPath,
    totals,
    errors,
  };
  if (options.reportPath) {
    await writeFile(options.reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  }
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
