/**
 * 几何64轮浏览器发布的 mask 替换型 Stage B 组合（radial-refine）。
 *
 * 与本机业务服务（model/training/serve-nail-candidate.py predict）同构的推理链：
 * Stage A 原始 seg 输出 → NMS(conf/iou/max 经 manifest 与 options) → scale_boxes 原图域
 * （round±0.1 填充技巧 + clip）→ 原型 logits 逐通道点积 → 裁边双线性上采样到原图 →
 * gt(0) + 框内半开裁剪（process_mask_native 语义）→ square_context_035 ROI →
 * 前景均值 center → 径向场拟合 → 5 通道条带 → Stage B(radius/presence) →
 * presence 门 → radius[bins]−distance ≥ 0 解码 alpha mask（整图域嵌入）。
 *
 * 与服务端的已记录差异：presence 拒识、非有限输出与空 mask 在服务端为整请求失败，
 * 浏览器端按实例丢弃并给出 warning（优雅降级）；center 均值用顺序求和，
 * np.mean 的成对求和差异约 1e-12（float64 内不可见）。
 */
import type { ImagePixels } from "../nail-image-detection.ts";
import {
  computeRadialLattice,
  cropSquareContext035,
  fitRadialRadius,
  radialMaskLogits,
  roundHalfEven,
} from "./radial-field.ts";
import { radialCoverageAlpha } from "./edge-refine.ts";
import { buildRadialStrip } from "./radial-strip.ts";
import { estimateMaskPrincipalAngle } from "./mask-orientation.ts";
import { inferSuggestedFingers } from "./finger-assignment.ts";
import { rankNailTextureCandidates } from "./quality.ts";
import {
  decodePrototypeShape,
  flattenDetectionRows,
  selectDetectionTensor,
  selectPrototypeTensor,
  stabilizeNailTextureCandidateAngles,
  suppressRawCandidates,
  scoreToConfidence,
  type ModelTensorLike,
} from "./postprocess.ts";
import type { NailTexturePreprocessResult } from "./preprocess.ts";
import type {
  NailMask,
  NailTextureCandidate,
  NailTextureStage2Manifest,
} from "./types.ts";

export interface RadialRefineStage2Runner {
  /** ORT 会话（recognize 侧为 unknown 宽类型，此处收窄为可运行的会话形态）。 */
  session: unknown;
  ort: {
    Tensor: new (
      type: string,
      data: Float32Array,
      dims: readonly number[]
    ) => unknown;
  };
  inputSize?: number;
}

interface RadialRefineSession {
  inputNames?: string[];
  outputNames?: string[];
  run: (feeds: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

export interface RadialRefineDiagnostics {
  mode: "radial-refine";
  evaluatedProposals: number;
  refinedInstances: number;
  presenceRejected: number;
  droppedRoi: number;
  droppedEmptyMask: number;
  stage2ModelVersion: string;
}

export interface RadialRefineOutcome {
  candidates: NailTextureCandidate[];
  warnings: string[];
  diagnostics: RadialRefineDiagnostics;
}

/** parity/调试用逐实例快照：presence 门通过、mask 已解码后触发。 */
export interface RadialRefineInstanceDebug {
  /** scale_boxes 后的原生域 float 框。 */
  box: { x0: number; y0: number; x1: number; y1: number };
  roi: { left: number; top: number; side: number };
  center: [number, number];
  /** ROI 局部二值粗 mask（side×side 行主序）。 */
  coarse: Uint8Array;
  /** fit_radius 输出（angularSamples 长度 float32）。 */
  radii: Float32Array;
  presence: number;
  /** 解码后的整图域二值 mask（width×height 行主序）。 */
  refinedMask: Uint8Array;
  score: number;
}

interface RadialDetectionRow {
  id: string;
  cx: number;
  cy: number;
  width: number;
  length: number;
  score: number;
  coefficients: number[];
}

/** ops.scale_boxes 语义：letterbox xywh → 原图 xyxy（round±0.1 填充技巧 + clip_boxes）。 */
export function scaleBoxesToNativeBox(
  box: { cx: number; cy: number; width: number; length: number },
  inputSize: number,
  originalWidth: number,
  originalHeight: number
): { x0: number; y0: number; x1: number; y1: number } {
  const gain = Math.min(inputSize / originalHeight, inputSize / originalWidth);
  const padX = roundHalfEven((inputSize - originalWidth * gain) / 2 - 0.1);
  const padY = roundHalfEven((inputSize - originalHeight * gain) / 2 - 0.1);
  const clip = (value: number, max: number) => Math.max(0, Math.min(max, value));
  return {
    x0: clip((box.cx - box.width / 2 - padX) / gain, originalWidth),
    y0: clip((box.cy - box.length / 2 - padY) / gain, originalHeight),
    x1: clip((box.cx + box.width / 2 - padX) / gain, originalWidth),
    y1: clip((box.cy + box.length / 2 - padY) / gain, originalHeight),
  };
}

/** ops.process_mask_native 的原型域裁边（round±0.1 技巧）；裁剪区域退化时返回 null。 */
export function computePrototypeCropRegion(
  protoWidth: number,
  protoHeight: number,
  nativeWidth: number,
  nativeHeight: number
): { left: number; top: number; right: number; bottom: number } | null {
  const gain = Math.min(protoHeight / nativeHeight, protoWidth / nativeWidth);
  const padW = (protoWidth - roundHalfEven(nativeWidth * gain)) / 2;
  const padH = (protoHeight - roundHalfEven(nativeHeight * gain)) / 2;
  const top = roundHalfEven(padH - 0.1);
  const left = roundHalfEven(padW - 0.1);
  const bottom = protoHeight - roundHalfEven(padH + 0.1);
  const right = protoWidth - roundHalfEven(padW + 0.1);
  if (bottom - top < 1 || right - left < 1) return null;
  return { left, top, right, bottom };
}

/**
 * torch F.interpolate bilinear（align_corners=false，CPU double 累积、存储 cast float32）
 * 在单个目标像素上的取值；map 为裁剪后的 logit 图。
 */
function sampleBilinearLogit(
  map: Float32Array,
  mapWidth: number,
  mapHeight: number,
  scaleX: number,
  scaleY: number,
  targetX: number,
  targetY: number
): number {
  let sx = scaleX * (targetX + 0.5) - 0.5;
  if (sx < 0) sx = 0;
  let sy = scaleY * (targetY + 0.5) - 0.5;
  if (sy < 0) sy = 0;
  const x0 = Math.floor(sx);
  const y0 = Math.floor(sy);
  const x1 = Math.min(x0 + 1, mapWidth - 1);
  const y1 = Math.min(y0 + 1, mapHeight - 1);
  const wx = sx - x0;
  const wy = sy - y0;
  const v00 = map[y0 * mapWidth + x0];
  const v01 = map[y0 * mapWidth + x1];
  const v10 = map[y1 * mapWidth + x0];
  const v11 = map[y1 * mapWidth + x1];
  const top = v00 * (1 - wx) + v01 * wx;
  const bottom = v10 * (1 - wx) + v11 * wx;
  return Math.fround(top * (1 - wy) + bottom * wy);
}

export async function runRadialRefineComposition(input: {
  source: ImagePixels;
  stage1Outputs: Record<string, ModelTensorLike>;
  preprocess: NailTexturePreprocessResult;
  stage2: RadialRefineStage2Runner | null;
  stage2Config: NailTextureStage2Manifest;
  maxCandidates: number;
  includeLowConfidenceCandidates?: boolean;
  scoreThreshold: number;
  /** parity/调试：每保留一个精修实例回调一次（在 candidates.push 前触发）。 */
  debugOnInstance?: (debug: RadialRefineInstanceDebug) => void;
}): Promise<RadialRefineOutcome> {
  const warnings: string[] = [];
  const emptyDiagnostics: RadialRefineDiagnostics = {
    mode: "radial-refine",
    evaluatedProposals: 0,
    refinedInstances: 0,
    presenceRejected: 0,
    droppedRoi: 0,
    droppedEmptyMask: 0,
    stage2ModelVersion: input.stage2Config.modelFile,
  };
  if (!input.stage2) {
    warnings.push("stage2_not_configured");
    return { candidates: [], warnings, diagnostics: emptyDiagnostics };
  }

  const detectionTensor = selectDetectionTensor(input.stage1Outputs);
  const prototypeTensor = selectPrototypeTensor(input.stage1Outputs, detectionTensor);
  if (!detectionTensor || !prototypeTensor) {
    warnings.push("model_outputs_missing_tensors");
    return { candidates: [], warnings, diagnostics: emptyDiagnostics };
  }
  const protoShape = decodePrototypeShape(prototypeTensor);
  if (!protoShape || protoShape.height < 2 || protoShape.width < 2) {
    warnings.push("stage_b_proto_shape_unsupported");
    return { candidates: [], warnings, diagnostics: emptyDiagnostics };
  }
  const protoChannels = protoShape.channels;
  const protoHeight = protoShape.height;
  const protoWidth = protoShape.width;

  const cropRegion = computePrototypeCropRegion(
    protoWidth,
    protoHeight,
    input.source.width,
    input.source.height
  );
  if (!cropRegion) {
    warnings.push("stage_b_proto_crop_region_degenerate");
    return { candidates: [], warnings, diagnostics: emptyDiagnostics };
  }
  const cropWidth = cropRegion.right - cropRegion.left;
  const cropHeight = cropRegion.bottom - cropRegion.top;
  // torch F.interpolate 的 scale = 输入尺寸/输出尺寸（CPU double 除法）。
  const sampleScaleX = cropWidth / input.source.width;
  const sampleScaleY = cropHeight / input.source.height;

  const angularSamples = input.stage2Config.angularSamples ?? 2048;
  const presenceThreshold = input.stage2Config.presenceThreshold ?? 0;
  const nmsThreshold = input.stage2Config.nmsIoUThreshold ?? 0.7;
  const scoreThreshold = input.includeLowConfidenceCandidates ? 0 : input.scoreThreshold;
  const maxCandidates = input.maxCandidates;

  const rows: RadialDetectionRow[] = flattenDetectionRows(detectionTensor)
    .map((row, rowIndex) => {
      const [cx, cy, width, length, score] = row;
      return {
        id: `raw-${rowIndex}`,
        cx: Number(cx) || 0,
        cy: Number(cy) || 0,
        width: Number(width) || 0,
        length: Number(length) || 0,
        score: Number(score) || 0,
        coefficients: row.slice(5).map((value) => Number(value) || 0),
      };
    })
    .filter(
      (row) =>
        Number.isFinite(row.cx) &&
        Number.isFinite(row.cy) &&
        Number.isFinite(row.score) &&
        row.width > 0 &&
        row.length > 0 &&
        row.score >= scoreThreshold
    )
    .sort((left, right) => right.score - left.score)
    .slice(0, 100);

  const selected = suppressRawCandidates(rows, nmsThreshold, maxCandidates);
  const evaluatedProposals = selected.length;

  const session = input.stage2.session as RadialRefineSession;
  const inputNames = session.inputNames ?? ["strip", "coarse_radii"];
  const stripInputName = inputNames[0] ?? "strip";
  const radiiInputName = inputNames[1] ?? "coarse_radii";

  const candidates: NailTextureCandidate[] = [];
  const angleEvidence = new Map<string, { reliable: boolean }>();
  let refinedInstances = 0;
  let presenceRejected = 0;
  let droppedRoi = 0;
  let droppedEmptyMask = 0;

  for (const raw of selected) {
    const nativeBox = scaleBoxesToNativeBox(
      raw,
      input.preprocess.inputSize,
      input.source.width,
      input.source.height
    );
    let roi: { left: number; top: number; side: number } | null = null;
    try {
      roi = cropSquareContext035(nativeBox, input.source.width, input.source.height);
    } catch {
      roi = null;
    }
    if (!roi) {
      droppedRoi += 1;
      continue;
    }
    const roiSide = roi.side;

    // 原型 logits 逐通道点积，仅在裁剪区域内展开（未裁剪像素的求和可安全跳过）。
    const protoData = prototypeTensor.data;
    const protoPlane = protoWidth * protoHeight;
    const logitMap = new Float32Array(cropWidth * cropHeight);
    for (let channel = 0; channel < protoChannels; channel++) {
      const coefficient = raw.coefficients[channel] ?? 0;
      if (coefficient === 0) continue;
      const channelOffset = channel * protoPlane;
      for (let y = 0; y < cropHeight; y++) {
        const sourceRow = channelOffset + (cropRegion.top + y) * protoWidth + cropRegion.left;
        const targetRow = y * cropWidth;
        for (let x = 0; x < cropWidth; x++) {
          logitMap[targetRow + x] = Math.fround(
            logitMap[targetRow + x] +
              Math.fround(coefficient * (Number(protoData[sourceRow + x]) || 0))
          );
        }
      }
    }

    // 双线性上采样到原图尺寸后 gt(0)，再按半开区间框内裁剪（crop_mask 语义）。
    const coarse = new Uint8Array(roiSide * roiSide);
    let coarseForeground = 0;
    for (let roiY = 0; roiY < roiSide; roiY++) {
      const nativeY = roi.top + roiY;
      if (nativeY < nativeBox.y0 || nativeY >= nativeBox.y1) continue;
      for (let roiX = 0; roiX < roiSide; roiX++) {
        const nativeX = roi.left + roiX;
        if (nativeX < nativeBox.x0 || nativeX >= nativeBox.x1) continue;
        const logit = sampleBilinearLogit(
          logitMap,
          cropWidth,
          cropHeight,
          sampleScaleX,
          sampleScaleY,
          nativeX,
          nativeY
        );
        if (logit > 0) {
          coarse[roiY * roiSide + roiX] = 1;
          coarseForeground += 1;
        }
      }
    }
    if (coarseForeground === 0) {
      // 服务端 keep = masks.amax > 0 与 coarse.any() 的等效丢弃。
      droppedEmptyMask += 1;
      continue;
    }

    // center = ROI 内粗 mask 前景坐标均值（float64；np.mean 成对求和差异约 1e-12）。
    let sumX = 0;
    let sumY = 0;
    for (let roiY = 0; roiY < roiSide; roiY++) {
      for (let roiX = 0; roiX < roiSide; roiX++) {
        if (coarse[roiY * roiSide + roiX]) {
          sumX += roiX;
          sumY += roiY;
        }
      }
    }
    const centerX = sumX / coarseForeground;
    const centerY = sumY / coarseForeground;

    const lattice = computeRadialLattice(
      roiSide,
      roiSide,
      centerX,
      centerY,
      angularSamples
    );
    const radii = fitRadialRadius(
      coarse,
      lattice.bins,
      lattice.distance,
      roiSide,
      roiSide,
      angularSamples
    );
    if (!radii) {
      droppedEmptyMask += 1;
      continue;
    }

    const strip = buildRadialStrip(
      input.source,
      { x0: roi.left, y0: roi.top, side: roiSide },
      coarse,
      centerX,
      centerY,
      radii,
      angularSamples
    );
    const stripTensor = new input.stage2.ort.Tensor(
      "float32",
      strip,
      [1, 5, angularSamples, 129]
    );
    const radiiTensor = new input.stage2.ort.Tensor(
      "float32",
      radii,
      [1, angularSamples]
    );
    const stageOutputs = await session.run({
      [stripInputName]: stripTensor,
      [radiiInputName]: radiiTensor,
    });
    let radiusTensor: ModelTensorLike | null = null;
    let presenceTensor: ModelTensorLike | null = null;
    for (const value of Object.values(stageOutputs)) {
      const tensor = value as ModelTensorLike;
      const dims = tensor.dims ? Array.from(tensor.dims) : [];
      if (dims.length === 2 && dims[0] === 1 && dims[1] === angularSamples) {
        radiusTensor = tensor;
      } else if (dims.length === 2 && dims[0] === 1 && dims[1] === 1) {
        presenceTensor = tensor;
      }
    }
    if (!radiusTensor || !presenceTensor) {
      warnings.push("stage_b_output_shape_unexpected");
      continue;
    }
    const presenceValue = Number(presenceTensor.data[0]);
    const radiusValues = Float32Array.from(radiusTensor.data, (value) => Number(value) || 0);
    let nonFinite = false;
    for (let index = 0; index < radiusValues.length; index++) {
      if (!Number.isFinite(radiusValues[index])) {
        nonFinite = true;
        break;
      }
    }
    if (nonFinite || !Number.isFinite(presenceValue)) {
      warnings.push("stage_b_nonfinite_output");
      continue;
    }
    if (presenceValue < presenceThreshold) {
      // 服务端口径：presence 拒识实例直接丢弃。
      presenceRejected += 1;
      continue;
    }

    const logits = radialMaskLogits(radiusValues, lattice.bins, lattice.distance);
    // alpha 嵌入整图域（识别输入域，origin 0,0），与候选 mask 既有约定一致。
    const fullMask = new Uint8Array(input.source.width * input.source.height);
    const roiGrid = new Uint8Array(roiSide * roiSide);
    let minX = -1;
    let minY = -1;
    let maxX = -1;
    let maxY = -1;
    for (let roiY = 0; roiY < roiSide; roiY++) {
      for (let roiX = 0; roiX < roiSide; roiX++) {
        if (logits[roiY * roiSide + roiX] >= 0) {
          roiGrid[roiY * roiSide + roiX] = 1;
          const nativeX = roi.left + roiX;
          const nativeY = roi.top + roiY;
          fullMask[nativeY * input.source.width + nativeX] = 1;
          if (minX < 0 || nativeX < minX) minX = nativeX;
          if (nativeX > maxX) maxX = nativeX;
          if (minY < 0 || nativeY < minY) minY = nativeY;
          if (nativeY > maxY) maxY = nativeY;
        }
      }
    }
    if (minX < 0) {
      droppedEmptyMask += 1;
      continue;
    }

    // bounds 与服务端一致：[minX, minY, maxX+1, maxY+1]（末像素含入）。
    const candidateId = `model-raw-${candidates.length + 1}`;
    const roiMask: NailMask = {
      width: roiSide,
      height: roiSide,
      data: roiGrid,
      originX: roi.left,
      originY: roi.top,
      scale: 1,
    };
    const estimatedAngle = estimateMaskPrincipalAngle(roiMask);
    input.debugOnInstance?.({
      box: nativeBox,
      roi: { left: roi.left, top: roi.top, side: roiSide },
      center: [centerX, centerY],
      coarse,
      radii,
      presence: presenceValue,
      refinedMask: fullMask,
      score: raw.score,
    });
    let coverageAlpha: Uint8ClampedArray | undefined;
    if (input.stage2Config.edgeRefinement?.mode === "radial-coverage-v1") {
      const localAlpha = radialCoverageAlpha(radiusValues, centerX, centerY, roiGrid, roiSide, roiSide, input.stage2Config.edgeRefinement.samples);
      coverageAlpha = new Uint8ClampedArray(fullMask.length);
      for (let row = 0; row < roiSide; row++) {
        coverageAlpha.set(localAlpha.subarray(row * roiSide, (row + 1) * roiSide), (roi.top + row) * input.source.width + roi.left);
      }
    }
    refinedInstances += 1;
    candidates.push({
      id: candidateId,
      cx: (minX + maxX + 1) / 2,
      cy: (minY + maxY + 1) / 2,
      width: maxX - minX + 1,
      length: maxY - minY + 1,
      angle: estimatedAngle ?? 0,
      score: raw.score,
      confidence: scoreToConfidence(raw.score),
      source: "model",
      mask: {
        width: input.source.width,
        height: input.source.height,
        data: fullMask,
        ...(coverageAlpha ? { coverageAlpha } : {}),
        originX: 0,
        originY: 0,
        scale: 1,
      },
      warnings: [],
      suggestedFinger: null,
    });
    angleEvidence.set(candidateId, { reliable: estimatedAngle != null });
  }

  const ranked = rankNailTextureCandidates(candidates, {
    imageWidth: input.source.width,
    imageHeight: input.source.height,
    maxCandidates,
    includeLowConfidenceCandidates: input.includeLowConfidenceCandidates,
    scoreThreshold,
  });
  const stabilized = stabilizeNailTextureCandidateAngles(
    ranked,
    ranked.map((candidate) => angleEvidence.get(candidate.id) ?? { reliable: false })
  );
  const suggestedFingers = inferSuggestedFingers(stabilized.length);

  return {
    candidates: stabilized.map((candidate, index) => ({
      ...candidate,
      id: `model-${index + 1}`,
      suggestedFinger: suggestedFingers[index] ?? null,
    })),
    warnings,
    diagnostics: {
      mode: "radial-refine",
      evaluatedProposals,
      refinedInstances,
      presenceRejected,
      droppedRoi,
      droppedEmptyMask,
      stage2ModelVersion: input.stage2Config.modelFile,
    },
  };
}
