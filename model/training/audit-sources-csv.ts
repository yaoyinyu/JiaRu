import path from "node:path";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import {
  auditSourceRecords,
  parseSourceRecords,
  type NailTextureAnnotationDocument,
  type SourceRecord,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const metadataDir = path.join(datasetRoot, "metadata");
const sourcesCsvPath = path.join(metadataDir, "sources.csv");
const reportPath = path.join(metadataDir, "sources-audit.json");

interface SourceDiskIssue {
  code:
    | "missing_source_image_file"
    | "missing_source_annotation_file"
    | "unreadable_source_annotation_file"
    | "annotation_count_mismatch";
  severity: "error";
  message: string;
  imageId?: string;
  fileName?: string;
  expected?: number;
  actual?: number;
  path?: string;
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function auditRecordDiskState(record: SourceRecord): Promise<SourceDiskIssue[]> {
  const issues: SourceDiskIssue[] = [];
  const imagePath = path.join(datasetRoot, record.imagePath);
  const annotationPath = path.join(datasetRoot, record.annotationPath);

  if (!(await fileExists(imagePath))) {
    issues.push({
      code: "missing_source_image_file",
      severity: "error",
      message: `imagePath points to a missing file: ${record.imagePath}`,
      imageId: record.imageId,
      fileName: record.fileName,
      path: record.imagePath,
    });
  }

  if (!(await fileExists(annotationPath))) {
    issues.push({
      code: "missing_source_annotation_file",
      severity: "error",
      message: `annotationPath points to a missing file: ${record.annotationPath}`,
      imageId: record.imageId,
      fileName: record.fileName,
      path: record.annotationPath,
    });
    return issues;
  }

  try {
    const annotation = JSON.parse(
      await readFile(annotationPath, "utf8")
    ) as NailTextureAnnotationDocument;
    const actual = Array.isArray(annotation.annotations)
      ? annotation.annotations.length
      : -1;
    if (actual !== record.annotationCount) {
      issues.push({
        code: "annotation_count_mismatch",
        severity: "error",
        message: `annotationCount is ${record.annotationCount}, but annotation JSON contains ${actual} annotations`,
        imageId: record.imageId,
        fileName: record.fileName,
        expected: record.annotationCount,
        actual,
        path: record.annotationPath,
      });
    }
  } catch (error) {
    issues.push({
      code: "unreadable_source_annotation_file",
      severity: "error",
      message: error instanceof Error ? error.message : "annotation JSON cannot be read",
      imageId: record.imageId,
      fileName: record.fileName,
      path: record.annotationPath,
    });
  }

  return issues;
}

async function main() {
  await mkdir(metadataDir, { recursive: true });

  let csv: string;
  try {
    csv = await readFile(sourcesCsvPath, "utf8");
  } catch (error) {
    const nodeError = error as NodeJS.ErrnoException;
    if (nodeError.code !== "ENOENT") {
      throw error;
    }

    const report = {
      datasetRoot,
      sourcesCsvPath,
      reportPath,
      recordCount: 0,
      ok: false,
      issues: [
        {
          code: "missing_sources_csv",
          severity: "error",
          message:
            "sources.csv does not exist yet. Run export-fallback-annotations.ts, import-debug-sample.ts, or sync-sources-csv.ts first.",
        },
      ],
    };
    await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const records = parseSourceRecords(csv);
const audit = auditSourceRecords(records);
  const emptyIssues = records.length === 0
    ? [
        {
          code: "empty_sources_csv",
          severity: "error" as const,
          message:
            "sources.csv contains no source records. Import or synchronize at least one reviewed sample before continuing.",
        },
      ]
    : [];
  const diskIssues = (
    await Promise.all(records.map((record) => auditRecordDiskState(record)))
  ).flat();
  const issues = [...emptyIssues, ...audit.issues, ...diskIssues];

  const report = {
    datasetRoot,
    sourcesCsvPath,
    reportPath,
    recordCount: records.length,
    ok: issues.every((issue) => issue.severity !== "error"),
    issues,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();