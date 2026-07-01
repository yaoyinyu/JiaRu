import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import {
  DEFAULT_DATASET_ROOT,
  buildPhase1ReadinessReport,
  phase1ReadinessPaths,
} from "./phase1-readiness-report.ts";

async function main() {
  const datasetRoot = path.resolve(process.env.DATASET_ROOT ?? DEFAULT_DATASET_ROOT);
  const report = await buildPhase1ReadinessReport(datasetRoot);
  const { metadataDir, reportPath } = phase1ReadinessPaths(datasetRoot);

  await mkdir(metadataDir, { recursive: true });
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
