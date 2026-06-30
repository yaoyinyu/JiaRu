import path from "node:path";
import { mkdir, readdir, writeFile } from "node:fs/promises";
import {
  auditAnnotationDocument,
  readAnnotationDocument,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const annotationDir = path.join(datasetRoot, "annotations", "raw-json");
const metadataDir = path.join(datasetRoot, "metadata");
const auditCsvPath = path.join(metadataDir, "label-audit.csv");

function toCsvCell(value: string | number | boolean): string {
  const text = String(value);
  return /[,"\n]/.test(text) ? `"${text.replaceAll("\"", "\"\"")}"` : text;
}

async function main() {
  const entries = await readdir(annotationDir, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name)
    .sort();

  const rows = [
    [
      "fileName",
      "ok",
      "polygonCount",
      "severity",
      "code",
      "annotationId",
      "message",
    ].join(","),
  ];

  let errorCount = 0;
  let warningCount = 0;
  for (const fileName of files) {
    const document = await readAnnotationDocument(path.join(annotationDir, fileName));
    const result = auditAnnotationDocument(document);
    if (result.issues.length === 0) {
      rows.push(
        [
          fileName,
          "true",
          result.polygonCount,
          "",
          "",
          "",
          "",
        ]
          .map(toCsvCell)
          .join(",")
      );
      continue;
    }

    for (const issue of result.issues) {
      if (issue.severity === "error") errorCount++;
      if (issue.severity === "warning") warningCount++;
      rows.push(
        [
          fileName,
          String(result.ok),
          result.polygonCount,
          issue.severity,
          issue.code,
          issue.annotationId ?? "",
          issue.message,
        ]
          .map(toCsvCell)
          .join(",")
      );
    }
  }

  await mkdir(metadataDir, { recursive: true });
  await writeFile(auditCsvPath, rows.join("\n"), "utf8");
  console.log(
    JSON.stringify(
      {
        datasetRoot,
        files: files.length,
        auditCsvPath,
        errorCount,
        warningCount,
      },
      null,
      2
    )
  );

  if (errorCount > 0) {
    process.exitCode = 1;
  }
}

await main();
