import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import {
  DEFAULT_DATASET_ROOT,
  buildPhase1ReadinessReport,
} from "./phase1-readiness-report.ts";

const COLLECTION_BATCH_SIZE = 50;
const FALLBACK_MASKS_PER_IMAGE = 4;

interface CollectionPriority {
  id: string;
  status: "pending" | "done";
  title: string;
  reason: string;
  target: string;
  acceptanceHint: string;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

async function main() {
  const datasetRoot = path.resolve(process.env.DATASET_ROOT ?? DEFAULT_DATASET_ROOT);
  const readiness = await buildPhase1ReadinessReport(datasetRoot);
  const reportPath = path.join(datasetRoot, "metadata", "phase1-collection-plan.json");

  const missingImages = Math.max(
    0,
    readiness.gates.imageCount.required - readiness.gates.imageCount.actual
  );
  const missingMasks = Math.max(
    0,
    readiness.gates.validMaskCount.required - readiness.gates.validMaskCount.actual
  );
  const avgValidMasksPerImage =
    readiness.totals.images > 0
      ? readiness.totals.validMasks / readiness.totals.images
      : FALLBACK_MASKS_PER_IMAGE;
  const additionalImagesNeededForMasks =
    missingMasks > 0 ? Math.ceil(missingMasks / Math.max(1, avgValidMasksPerImage)) : 0;
  const collectionDemand = Math.max(missingImages, additionalImagesNeededForMasks);
  const estimatedBatchesRemaining =
    collectionDemand > 0 ? Math.ceil(collectionDemand / COLLECTION_BATCH_SIZE) : 0;
  const nextBatchTargetImages =
    collectionDemand > 0 ? clamp(collectionDemand, 20, COLLECTION_BATCH_SIZE) : 0;

  const priorities: CollectionPriority[] = [];

  if (!readiness.gates.labelAuditPass.ok) {
    priorities.push({
      id: "fix-label-errors",
      status: "pending",
      title: "先修掉现有标注错误，再继续扩批",
      reason: `当前还有 ${readiness.totals.filesWithErrors} 个文件存在 error 级标注问题，直接扩批会把问题带进后续训练集。`,
      target: `修完这 ${readiness.totals.filesWithErrors} 个错误文件，并重新通过 audit-labels`,
      acceptanceHint: "重新运行 audit-phase1-readiness.ts 后，labelAuditPass.ok 必须为 true",
    });
  }

  if (!readiness.gates.testSplitHasNegative.ok) {
    priorities.push({
      id: "add-negative-test-sample",
      status: "pending",
      title: "补一批负样本，并至少留 1 张进 test split",
      reason: "Phase 1 gate 要求测试集必须包含 negative 样本，否则后面无法验证误检控制。",
      target:
        "下一批至少加入 1 张 originType=negative 或 negative=true 的样本，并标记 targetSplitHint=test",
      acceptanceHint:
        "重新运行 audit-phase1-readiness.ts 后，testSplitHasNegative.ok 必须为 true",
    });
  }

  if (!readiness.gates.testSplitHasComplexBackground.ok) {
    priorities.push({
      id: "add-complex-background-test-sample",
      status: "pending",
      title: "补复杂背景测试样本",
      reason:
        "当前 test split 缺少复杂背景覆盖，无法验证强反光、深色或混合背景下的表现。",
      target:
        "下一批至少留 1 张带 background=dark/mixed 或 reason=complex_background 的样本进 test split",
      acceptanceHint:
        "重新运行 audit-phase1-readiness.ts 后，testSplitHasComplexBackground.ok 必须为 true",
    });
  }

  if (collectionDemand > 0) {
    priorities.push({
      id: "expand-positive-dataset",
      status: "pending",
      title: "继续扩充 Phase 1 正样本种子集",
      reason: `当前还差 ${missingImages} 张图、${missingMasks} 个有效 mask；按现有平均每图 ${avgValidMasksPerImage.toFixed(2)} 个有效指甲估算，还需要约 ${collectionDemand} 张图。`,
      target: `优先准备下一批约 ${nextBatchTargetImages} 张图片，预计还需 ${estimatedBatchesRemaining} 个 50 图以内批次`,
      acceptanceHint:
        "每导入一批后重新运行 audit-phase1-readiness.ts，直到 imageCount 和 validMaskCount 都通过",
    });
  }

  if (priorities.length === 0) {
    priorities.push({
      id: "phase1-ready",
      status: "done",
      title: "Phase 1 数据集门槛已满足",
      reason: "当前数据量、有效 mask、测试集覆盖和标注质量 gate 都已通过。",
      target: "可以进入第一版模型训练与导出阶段",
      acceptanceHint: "继续执行 train-yolo-seg.py / evaluate.py / export-onnx.py",
    });
  }

  const suggestedCommands = [
    `node --no-warnings --experimental-strip-types model/training/bootstrap-seed-batch.ts --source-dir "C:/path/to/local-images" --root-dir "C:/tmp/seed-batch-next" --source-group seed-batch-next --origin-type web --default-origin-ref "manual sourcing 2026-07-01"`,
    `node --no-warnings --experimental-strip-types scripts/batch-verify-nail-detection.ts --image-dir "C:/tmp/seed-batch-next/images" --output-dir "C:/tmp/seed-batch-next/debug" --prefix seed-batch-next`,
    `node --no-warnings --experimental-strip-types model/training/run-seed-batch-prep-pipeline.ts --root-dir "C:/tmp/seed-batch-next"`,
    `node --no-warnings --experimental-strip-types model/training/run-reviewed-batch-import-pipeline.ts --root-dir "C:/tmp/seed-batch-next"`,
    `node --no-warnings --experimental-strip-types model/training/audit-phase1-readiness.ts`,
  ];

  const report = {
    ok: readiness.ok,
    datasetRoot,
    reportPath,
    readinessReportPath: readiness.reportPath,
    currentTotals: {
      images: readiness.totals.images,
      validMasks: readiness.totals.validMasks,
      testNegatives: readiness.testCoverage.negatives,
      testComplexBackground: readiness.testCoverage.complexBackground,
    },
    remaining: {
      images: missingImages,
      validMasks: missingMasks,
    },
    derived: {
      averageValidMasksPerImage: Number(avgValidMasksPerImage.toFixed(2)),
      additionalImagesNeededForMasks,
      estimatedBatchesRemaining,
      nextBatchTargetImages,
      collectionBatchSize: COLLECTION_BATCH_SIZE,
    },
    priorities,
    suggestedReviewTags: [
      "sample=reference|merchant|negative",
      "background=light|dark|mixed",
      "reason=complex_background|background_confusion",
      "effects=highlight|gold_line|glitter|cat_eye",
      "targetSplitHint=train|val|test",
    ],
    suggestedCommands,
  };

  await mkdir(path.dirname(reportPath), { recursive: true });
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify(report, null, 2));

  if (!report.ok) {
    process.exitCode = 1;
  }
}

await main();
