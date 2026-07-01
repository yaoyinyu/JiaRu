import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { DEFAULT_DATASET_ROOT, buildPhase1ReadinessReport } from "./phase1-readiness-report.ts";

interface CliOptions {
  datasetRoot: string;
  sourceDir: string;
  rootDir: string;
  sourceGroup: string;
  originType: "reference" | "web" | "user" | "merchant" | "negative" | "other";
  license: string;
  defaultOriginRef: string;
}

interface CollectionPlanLike {
  derived?: {
    nextBatchTargetImages?: number;
    estimatedBatchesRemaining?: number;
    collectionBatchSize?: number;
  };
  priorities?: Array<{
    id: string;
    status: "pending" | "done";
    title: string;
    target: string;
    acceptanceHint: string;
  }>;
}

function parseArgs(argv: string[]): CliOptions {
  const defaults: CliOptions = {
    datasetRoot: path.resolve(process.env.DATASET_ROOT ?? DEFAULT_DATASET_ROOT),
    sourceDir: "C:/path/to/local-images",
    rootDir: "C:/tmp/seed-batch-001",
    sourceGroup: "seed-batch-001",
    originType: "web",
    license: "internal-test-only",
    defaultOriginRef: "manual sourcing 2026-07-01",
  };

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index];
    if (arg === "--dataset-root") defaults.datasetRoot = path.resolve(argv[++index]);
    else if (arg === "--source-dir") defaults.sourceDir = argv[++index] ?? defaults.sourceDir;
    else if (arg === "--root-dir") defaults.rootDir = argv[++index] ?? defaults.rootDir;
    else if (arg === "--source-group") defaults.sourceGroup = argv[++index] ?? defaults.sourceGroup;
    else if (arg === "--origin-type") defaults.originType = (argv[++index] as CliOptions["originType"]) ?? defaults.originType;
    else if (arg === "--license") defaults.license = argv[++index] ?? defaults.license;
    else if (arg === "--default-origin-ref") defaults.defaultOriginRef = argv[++index] ?? defaults.defaultOriginRef;
    else {
      throw new Error(
        "Usage: node --experimental-strip-types model/training/generate-first-batch-checklist.ts [--dataset-root <dir>] [--source-dir <dir>] [--root-dir <dir>] [--source-group <name>] [--origin-type <reference|web|user|merchant|negative|other>] [--license <text>] [--default-origin-ref <text>]"
      );
    }
  }

  return defaults;
}

async function readCollectionPlan(datasetRoot: string): Promise<CollectionPlanLike | null> {
  try {
    const planPath = path.join(datasetRoot, "metadata", "phase1-collection-plan.json");
    return JSON.parse(await readFile(planPath, "utf8")) as CollectionPlanLike;
  } catch {
    return null;
  }
}

function toPosix(input: string): string {
  return input.replaceAll("\\", "/");
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const readiness = await buildPhase1ReadinessReport(options.datasetRoot);
  const collectionPlan = await readCollectionPlan(options.datasetRoot);
  const checklistPath = path.join(options.datasetRoot, "metadata", "first-batch-execution-checklist.json");

  const targetImages =
    collectionPlan?.derived?.nextBatchTargetImages && collectionPlan.derived.nextBatchTargetImages > 0
      ? collectionPlan.derived.nextBatchTargetImages
      : Math.min(Math.max(readiness.gates.imageCount.required - readiness.gates.imageCount.actual, 20), 50);

  const priorities =
    collectionPlan?.priorities?.filter((item) => item.status === "pending").map((item) => ({
      id: item.id,
      title: item.title,
      target: item.target,
      acceptanceHint: item.acceptanceHint,
    })) ?? [];

  const commands = {
    bootstrap: `node --no-warnings --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir "${toPosix(options.sourceDir)}" --root-dir "${toPosix(options.rootDir)}" --source-group ${options.sourceGroup} --origin-type ${options.originType} --license "${options.license}" --default-origin-ref "${options.defaultOriginRef}"`,
    verifyOverlays: `node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "${toPosix(path.join(options.rootDir, "images"))}" --output-dir "${toPosix(path.join(options.rootDir, "debug"))}" --prefix ${options.sourceGroup}`,
    prepareSeedBatch: `node --no-warnings --experimental-strip-types model/training/run-seed-batch-prep-pipeline.ts --root-dir "${toPosix(options.rootDir)}"`,
    importReviewedBatch: `node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir "${toPosix(options.rootDir)}"`,
    readinessGate: "node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts",
    collectionPlan: "node --no-warnings --experimental-strip-types model/training/plan-phase1-collection.ts",
  };

  const report = {
    ok: readiness.ok,
    datasetRoot: options.datasetRoot,
    checklistPath,
    currentReadiness: {
      images: readiness.totals.images,
      validMasks: readiness.totals.validMasks,
      testNegatives: readiness.testCoverage.negatives,
      testComplexBackground: readiness.testCoverage.complexBackground,
    },
    firstBatchRecommendation: {
      targetImages,
      recommendedSourceMix: {
        referenceOrMerchant: Math.max(10, Math.round(targetImages * 0.7)),
        negative: Math.max(2, Math.round(targetImages * 0.15)),
        complexBackgroundReservedForTest: Math.max(2, Math.round(targetImages * 0.15)),
      },
      estimatedBatchesRemaining: collectionPlan?.derived?.estimatedBatchesRemaining ?? null,
    },
    sourceBatch: {
      sourceDir: options.sourceDir,
      rootDir: options.rootDir,
      sourceGroup: options.sourceGroup,
      originType: options.originType,
      license: options.license,
      defaultOriginRef: options.defaultOriginRef,
    },
    priorities,
    steps: [
      {
        id: "collect-images",
        title: "准备首批图片目录",
        action: `把约 ${targetImages} 张候选图片放进 ${options.sourceDir}`,
        acceptance: "目录里只保留本批要处理的 jpg/jpeg/png/webp 图片；至少包含负样本和复杂背景样本",
      },
      {
        id: "bootstrap-seed-batch",
        title: "生成种子批次工作区",
        command: commands.bootstrap,
        acceptance: `${toPosix(options.rootDir)}/images、debug、review 和 manifest 已生成`,
      },
      {
        id: "verify-overlays",
        title: "批量生成 fallback overlay 供筛选",
        command: commands.verifyOverlays,
        acceptance: `${toPosix(path.join(options.rootDir, "debug"))} 下已有 overlay/debug JSON，可开始人工筛图`,
      },
      {
        id: "review-and-prepare",
        title: "完成筛图并生成 reviewed annotations",
        command: commands.prepareSeedBatch,
        acceptance: `${toPosix(path.join(options.rootDir, "selected", "annotations", "raw-json"))} 已生成待修正 JSON`,
      },
      {
        id: "manual-fix",
        title: "手工修正 selected/annotations/raw-json/*.json",
        action: "把保留下来的正样本修成有效 nail mask，并确保至少预留 negative/test/complex-background 样本",
        acceptance: "修正后可直接执行导入流水线",
      },
      {
        id: "import-reviewed-batch",
        title: "导入正式数据集并触发 readiness/collection plan",
        command: commands.importReviewedBatch,
        acceptance: "正式数据集已更新，并重新生成 phase1-readiness.json 与 phase1-collection-plan.json",
      },
      {
        id: "recheck-gates",
        title: "复核 Phase 1 门禁",
        commands: [commands.readinessGate, commands.collectionPlan],
        acceptance: "确认本批是否补到了 negative、complex background，以及距离 200 / 800 还差多少",
      },
    ],
    nextCommands: Object.values(commands),
  };

  await mkdir(path.dirname(checklistPath), { recursive: true });
  await writeFile(checklistPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exitCode = 1;
}

await main();
