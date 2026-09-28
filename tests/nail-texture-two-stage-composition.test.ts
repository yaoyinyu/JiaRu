import assert from "node:assert/strict";
import test from "node:test";

import type { ImagePixels } from "../src/lib/nail-image-detection.ts";
import type { NailTextureCandidate, NailTextureModelManifest } from "../src/lib/nail-texture-recognition/types.ts";
import type { NailTexturePreprocessResult } from "../src/lib/nail-texture-recognition/preprocess.ts";
import type { ModelTensorLike, NailTextureDetectionRow } from "../src/lib/nail-texture-recognition/postprocess.ts";
import {
  cropProposalRoi,
  runTwoStageComposition,
} from "../src/lib/nail-texture-recognition/two-stage.ts";
import {
  validateNailTextureModelManifest,
} from "../src/lib/nail-texture-recognition/model-runtime.ts";

const COEFFICIENT_COUNT = 32;

function makeSource(width = 200, height = 160): ImagePixels {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let index = 0; index < width * height; index++) {
    data[index * 4] = 10;
    data[index * 4 + 1] = 20;
    data[index * 4 + 2] = 30;
    data[index * 4 + 3] = 255;
  }
  return { width, height, data };
}

function makePreprocess(): NailTexturePreprocessResult {
  return {
    inputSize: 512,
    originalWidth: 1024,
    originalHeight: 1024,
    scaleX: 2,
    scaleY: 2,
    resizeScale: 0.5,
    resizedWidth: 512,
    resizedHeight: 512,
    padLeft: 0,
    padTop: 0,
    tensorData: new Float32Array(0),
    tensorShape: [1, 3, 512, 512],
  };
}

/**
 * 真实模型输出为 [1, 37, 5376]（stage2 为 [1, 37, 1344]），预测数远大于 256，
 * flattenDetectionRows 的 channel-major 判定依赖这一点。因此测试夹具必须把预测数
 * 填充到 256 以上，否则会走进与实际部署不符的分支。
 */
const PREDICTION_PADDING = 300;

/** 构造与原生 output0 同构的检测张量（channel-major，37 = 4框 + 1分数 + 32掩码系数）。 */
function makeDetectionTensor(
  rows: Array<{ cx: number; cy: number; width: number; length: number; score: number }>
): ModelTensorLike {
  const attributeCount = 5 + COEFFICIENT_COUNT;
  const predictionCount = Math.max(PREDICTION_PADDING, rows.length);
  const data = new Float32Array(attributeCount * predictionCount);
  rows.forEach((row, prediction) => {
    data[0 * predictionCount + prediction] = row.cx;
    data[1 * predictionCount + prediction] = row.cy;
    data[2 * predictionCount + prediction] = row.width;
    data[3 * predictionCount + prediction] = row.length;
    data[4 * predictionCount + prediction] = row.score;
    for (let index = 0; index < COEFFICIENT_COUNT; index++) {
      data[(5 + index) * predictionCount + prediction] = 0.01;
    }
  });
  return { data, dims: [1, attributeCount, predictionCount] };
}

function makePrototypeTensor(): ModelTensorLike {
  return {
    data: new Float32Array(1 * COEFFICIENT_COUNT * 128 * 128),
    dims: [1, COEFFICIENT_COUNT, 128, 128],
  };
}

function makeCandidate(id: string): NailTextureCandidate {
  return {
    id,
    cx: 10,
    cy: 10,
    length: 20,
    width: 12,
    angle: 0,
    score: 0.5,
    confidence: "medium",
    source: "model",
    suggestedFinger: null,
  };
}

function makeManifest(): NailTextureModelManifest {
  return {
    version: "nail-texture-seg-candidate57-test-v1",
    inputSize: 512,
    task: "segment",
    backendPreferences: ["webgpu", "wasm"],
    modelFile: "candidate57-stage1-512-fp16.onnx",
    labels: ["nail_texture"],
    outputContract: "ultralytics-seg-raw-v1",
    resizeMode: "letterbox",
    testOnly: true,
    stage2: {
      modelFile: "candidate57-stage2-256-fp16.onnx",
      inputSize: 256,
      cropContextRatio: 0.35,
      promotionMarginThreshold: 0.55,
    },
    composition: {
      proposalThreshold: 0.1,
      acceptanceThreshold: 0.4,
      promotionBandMinimum: 0.3,
      maximumProposalsPerImage: 10,
      dedup: {
        maskIouThreshold: 0.6,
        maskContainmentThreshold: 0.85,
        maskScoreTolerance: 0.12,
        boxIouThreshold: 0.55,
      },
    },
  };
}

interface Stage2StubOptions {
  score: number;
  onRun?: () => void;
}

function makeStage2(options: Stage2StubOptions) {
  // 不使用构造函数参数属性（Node --experimental-strip-types 不支持该 TS 语法）
  const FakeTensor = function (
    type: string,
    data: Float32Array,
    dims: readonly number[]
  ) {
    return { type, data, dims };
  } as unknown as new (
    type: string,
    data: Float32Array,
    dims: readonly number[]
  ) => unknown;

  let runCount = 0;
  const session = {
    inputNames: ["images"],
    run: async () => {
      runCount++;
      options.onRun?.();
      return {
        output0: makeDetectionTensor([
          { cx: 128, cy: 128, width: 64, length: 64, score: options.score },
        ]),
        output1: { data: new Float32Array(COEFFICIENT_COUNT * 64 * 64), dims: [1, COEFFICIENT_COUNT, 64, 64] },
      } as unknown as Record<string, ModelTensorLike>;
    },
  };

  return {
    stage2: {
      session: session as unknown,
      ort: { Tensor: FakeTensor } as unknown as {
        Tensor: new (type: string, data: Float32Array, dims: readonly number[]) => unknown;
      },
      inputSize: 256,
    },
    getRunCount: () => runCount,
  };
}

function makePostprocess() {
  return (
    _outputs: Record<string, ModelTensorLike>,
    _preprocess: NailTexturePreprocessResult,
    options: {
      maxCandidates: number;
      scoreThreshold: number;
      nmsThreshold: number;
      includeLowConfidenceCandidates?: boolean;
      detectionRows?: NailTextureDetectionRow[];
    }
  ): NailTextureCandidate[] => {
    // 两阶段路径必须走 detectionRows 入口，而非重建张量
    const count = options.detectionRows?.length ?? 0;
    return Array.from({ length: count }, (_, index) => makeCandidate(`candidate-${index + 1}`));
  };
}

test("cropProposalRoi 按上下文比例外扩并裁剪到图像边界内", () => {
  const source = makeSource(200, 160);
  const roi = cropProposalRoi(source, { x0: 80, y0: 60, x1: 100, y1: 80 }, 0.35);

  // 框 20x20，最长边 20，上下文 = 0.35 * 20 = 7，四边各外扩 7
  assert.equal(roi.width, 34);
  assert.equal(roi.height, 34);
  assert.equal(roi.data.length, 34 * 34 * 4);
  // 左上角像素应取自原图 (73,53)
  assert.equal(roi.data[0], 10);
  assert.equal(roi.data[1], 20);
  assert.equal(roi.data[2], 30);
  assert.equal(roi.data[3], 255);
});

test("cropProposalRoi 越界时夹紧到图像范围", () => {
  const source = makeSource(50, 50);
  // 框 10x10 -> 上下文 3.5，左侧外扩到 36 有效，右侧 50+3.5 被夹到 50
  const roi = cropProposalRoi(source, { x0: 40, y0: 40, x1: 50, y1: 50 }, 0.35);
  assert.equal(roi.width, 14);
  assert.equal(roi.height, 14);

  // 完全越界的框仍必须落在图像内
  const clamped = cropProposalRoi(source, { x0: 49, y0: 49, x1: 60, y1: 60 }, 0.35);
  assert.ok(clamped.width <= 50 && clamped.height <= 50);
  assert.equal(clamped.data.length, clamped.width * clamped.height * 4);
});

test("主规则：stage1 分数达到接受阈值时不调用 stage2", async () => {
  const { stage2, getRunCount } = makeStage2({ score: 0.99 });
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: {
      output0: makeDetectionTensor([
        { cx: 256, cy: 256, width: 60, length: 80, score: 0.72 },
      ]),
      output1: makePrototypeTensor(),
    },
    preprocess: makePreprocess(),
    stage2,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(getRunCount(), 0, "主规则入选的候选不应触发 stage2 推理");
  assert.equal(result.evaluatedProposals, 1);
  assert.equal(result.acceptedByPrimaryRule, 1);
  assert.equal(result.promotedProposals, 0);
  assert.equal(result.candidates.length, 1);
});

test("晋级规则：低置信带内 stage2 分差达标才入选", async () => {
  const { stage2 } = makeStage2({ score: 0.9 });
  // stage1 = 0.32，stage2 = 0.90，分差 0.58 >= 0.55 → 晋级
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: {
      output0: makeDetectionTensor([
        { cx: 256, cy: 256, width: 60, length: 80, score: 0.32 },
      ]),
      output1: makePrototypeTensor(),
    },
    preprocess: makePreprocess(),
    stage2,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(result.evaluatedProposals, 1);
  assert.equal(result.promotedProposals, 1);
  assert.equal(result.acceptedByPrimaryRule, 0);
  assert.equal(result.candidates.length, 1);
  // 分数经 Float32Array 往返，需按浮点容差比较
  assert.ok(Math.abs((result.evaluations[0]?.stage2Score ?? 0) - 0.9) < 1e-6);
});

test("晋级规则：分差不足时不入选", async () => {
  const { stage2 } = makeStage2({ score: 0.8 });
  // stage1 = 0.32，stage2 = 0.80，分差 0.48 < 0.55 → 淘汰
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: {
      output0: makeDetectionTensor([
        { cx: 256, cy: 256, width: 60, length: 80, score: 0.32 },
      ]),
      output1: makePrototypeTensor(),
    },
    preprocess: makePreprocess(),
    stage2,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(result.evaluatedProposals, 1);
  assert.equal(result.promotedProposals, 0);
  assert.equal(result.candidates.length, 0);
});

test("低于晋级带下限的候选既不调用 stage2 也不入选", async () => {
  const { stage2, getRunCount } = makeStage2({ score: 0.99 });
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: {
      output0: makeDetectionTensor([
        { cx: 256, cy: 256, width: 60, length: 80, score: 0.2 },
      ]),
      output1: makePrototypeTensor(),
    },
    preprocess: makePreprocess(),
    stage2,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(getRunCount(), 0);
  assert.equal(result.candidates.length, 0);
  assert.equal(result.evaluations[0]?.acceptedBy, "none");
});

test("stage2 不可用时仅主规则生效并留下告警", async () => {
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: {
      output0: makeDetectionTensor([
        { cx: 256, cy: 256, width: 60, length: 80, score: 0.72 },
        { cx: 300, cy: 300, width: 60, length: 80, score: 0.33 },
      ]),
      output1: makePrototypeTensor(),
    },
    preprocess: makePreprocess(),
    stage2: null,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(result.acceptedByPrimaryRule, 1);
  assert.equal(result.promotedProposals, 0);
  assert.equal(result.candidates.length, 1);
  assert.ok(result.warnings.includes("stage2_unavailable_only_primary_rule_applied"));
});

test("提案数量受 maximumProposalsPerImage 限制", async () => {
  const { stage2 } = makeStage2({ score: 0.99 });
  const rows = Array.from({ length: 25 }, (_, index) => ({
    cx: 200 + index,
    cy: 200,
    width: 40,
    length: 50,
    score: 0.5 + index * 0.001,
  }));
  const result = await runTwoStageComposition({
    source: makeSource(),
    manifest: makeManifest(),
    stage1Outputs: { output0: makeDetectionTensor(rows), output1: makePrototypeTensor() },
    preprocess: makePreprocess(),
    stage2,
    postprocess: makePostprocess(),
    maxCandidates: 10,
  });

  assert.equal(result.evaluatedProposals, 10);
});

test("manifest 校验接受合法的 stage2 与组合字段", () => {
  assert.deepEqual(validateNailTextureModelManifest(makeManifest()), []);
});

test("manifest 校验拒绝非法的 stage2 字段", () => {
  const manifest = makeManifest();
  manifest.stage2 = {
    modelFile: "../escape.onnx",
    inputSize: 0,
    cropContextRatio: -1,
    promotionMarginThreshold: Number.NaN,
  };
  const errors = validateNailTextureModelManifest(manifest);
  assert.ok(errors.includes("manifest_stage2_model_file_must_be_safe_onnx_basename"));
  assert.ok(errors.includes("manifest_stage2_input_size_must_be_positive_integer"));
  assert.ok(errors.includes("manifest_stage2_crop_context_ratio_must_be_non_negative_number"));
  assert.ok(errors.includes("manifest_stage2_promotion_margin_must_be_number"));
});
