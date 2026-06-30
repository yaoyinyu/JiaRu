import path from "node:path";
import { readFile, writeFile } from "node:fs/promises";
import {
  auditSourceRecords,
  parseSourceRecords,
} from "../../src/lib/nail-texture-dataset.ts";

const datasetRoot = path.resolve(
  process.env.DATASET_ROOT ?? "model/datasets/nail-texture-v1"
);
const metadataDir = path.join(datasetRoot, "metadata");
const sourcesCsvPath = path.join(metadataDir, "sources.csv");
const reportPath = path.join(metadataDir, "sources-audit.json");

async function main() {
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

  const report = {
    datasetRoot,
    sourcesCsvPath,
    reportPath,
    recordCount: records.length,
    ok: audit.ok,
    issues: audit.issues,
  };

  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!audit.ok) {
    process.exitCode = 1;
  }
}

await main();
