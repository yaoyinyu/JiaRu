import type { ImagePixels } from "../nail-image-detection.ts";
import { readDetectionRows, type ModelTensorLike, type NailTextureDetectionRow } from "./postprocess.ts";
import { preprocessNailTextureImage, type NailTexturePreprocessResult } from "./preprocess.ts";
import type {
  NailTextureCandidate,
  NailTextureModelManifest,
} from "./types.ts";

/**
 * candidate57 两阶段运行时（测试专用）。
 *
 * 契约来源：model/training/candidate57-runtime-selection-lock-v1.json
 *   - stage1 为唯一 polygon 来源（selectedPolygon = stage1Polygon）
 *   - stage2 仅为 [promotionBandMinimum, acceptanceThreshold) 低置信带提供存在性提升分数
 *   - 晋级规则：stage2Score - stage1Score >= promotionMarginThreshold
 *
 * 实现要点：入选的 stage1 候选会被重新组装成一个检测张量后交给既有
 * postprocessNailTextureDetections，以复用 mask 解码、主角度估计、质量排序与指尖分配，
 * 避免两阶段路径与单模型路径出现行为分叉。
 */

export interface TwoStageCompositionDefaults {
  proposalThreshold: number;
  acceptanceThreshold: number;
  promotionBandMinimum: number;
  maximumProposalsPerImage: number;
  boxIouThreshold: number;
}

/** 与 candidate57 选择锁一致的默认组合参数。 */
export const CANDIDATE57_COMPOSITION: TwoStageCompositionDefaults = {
  proposalThreshold: 0.1,
  acceptanceThreshold: 0.4,
  promotionBandMinimum: 0.3,
  maximumProposalsPerImage: 10,
  boxIouThreshold: 0.55,
};

export interface Stage2ProposalEvaluation {
  stage1Score: number;
  stage2Score: number | null;
  accepted: boolean;
  acceptedBy: "primary" | "promotion" | "none";
}

export interface TwoStageRunResult {
  candidates: NailTextureCandidate[];
  evaluatedProposals: number;
  promotedProposals: number;
  acceptedByPrimaryRule: number;
  evaluations: Stage2ProposalEvaluation[];
  warnings: string[];
}

interface SessionLike {
  inputNames?: string[];
  run: (feeds: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

interface OrtLike {
  Tensor: new (type: string, data: Float32Array, dims: readonly number[]) => unknown;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function resolveComposition(
  manifest: NailTextureModelManifest
): TwoStageCompositionDefaults & { promotionMarginThreshold: number; cropContextRatio: number } {
  const composition = manifest.composition;
  return {
    proposalThreshold: composition?.proposalThreshold ?? CANDIDATE57_COMPOSITION.proposalThreshold,
    acceptanceThreshold: composition?.acceptanceThreshold ?? CANDIDATE57_COMPOSITION.acceptanceThreshold,
    promotionBandMinimum:
      composition?.promotionBandMinimum ?? CANDIDATE57_COMPOSITION.promotionBandMinimum,
    maximumProposalsPerImage:
      composition?.maximumProposalsPerImage ?? CANDIDATE57_COMPOSITION.maximumProposalsPerImage,
    boxIouThreshold: composition?.dedup.boxIouThreshold ?? CANDIDATE57_COMPOSITION.boxIouThreshold,
    promotionMarginThreshold: manifest.stage2?.promotionMarginThreshold ?? 0.55,
    cropContextRatio: manifest.stage2?.cropContextRatio ?? 0.35,
  };
}

function modelBoxToOriginalBox(
  row: { cx: number; cy: number; width: number; length: number },
  preprocess: NailTexturePreprocessResult
): { x0: number; y0: number; x1: number; y1: number } {
  const resizeScale = preprocess.resizeScale ?? 1 / preprocess.scaleX;
  const padLeft = preprocess.padLeft ?? 0;
  const padTop = preprocess.padTop ?? 0;
  const cx = (row.cx - padLeft) / resizeScale;
  const cy = (row.cy - padTop) / resizeScale;
  const width = row.width / resizeScale;
  const length = row.length / resizeScale;
  return {
    x0: cx - width / 2,
    y0: cy - length / 2,
    x1: cx + width / 2,
    y1: cy + length / 2,
  };
}

/**
 * 按 cropContextRatio 为候选框向外扩展上下文并裁出 ROI。
 * 扩展量按候选框最长边计算，四边等量外扩，随后裁剪到图像边界内。
 */
export function cropProposalRoi(
  source: ImagePixels,
  box: { x0: number; y0: number; x1: number; y1: number },
  cropContextRatio: number
): ImagePixels {
  const boxWidth = Math.max(1, box.x1 - box.x0);
  const boxHeight = Math.max(1, box.y1 - box.y0);
  const context = cropContextRatio * Math.max(boxWidth, boxHeight);

  const x0 = clamp(Math.floor(box.x0 - context), 0, source.width - 1);
  const y0 = clamp(Math.floor(box.y0 - context), 0, source.height - 1);
  const x1 = clamp(Math.ceil(box.x1 + context), x0 + 1, source.width);
  const y1 = clamp(Math.ceil(box.y1 + context), y0 + 1, source.height);

  const cropWidth = x1 - x0;
  const cropHeight = y1 - y0;
  const data = new Uint8ClampedArray(cropWidth * cropHeight * 4);

  for (let y = y0; y < y1; y++) {
    const sourceRowStart = y * source.width * 4;
    const targetRowStart = (y - y0) * cropWidth * 4;
    for (let x = x0; x < x1; x++) {
      const sourceIndex = sourceRowStart + x * 4;
      const targetIndex = targetRowStart + (x - x0) * 4;
      data[targetIndex] = Number(source.data[sourceIndex]) || 0;
      data[targetIndex + 1] = Number(source.data[sourceIndex + 1]) || 0;
      data[targetIndex + 2] = Number(source.data[sourceIndex + 2]) || 0;
      data[targetIndex + 3] = 255;
    }
  }

  return { width: cropWidth, height: cropHeight, data };
}

async function scoreProposalWithStage2(
  source: ImagePixels,
  row: { cx: number; cy: number; width: number; length: number },
  preprocess: NailTexturePreprocessResult,
  stage2: { session: unknown; ort: OrtLike; inputSize: number },
  cropContextRatio: number
): Promise<number | null> {
  const box = modelBoxToOriginalBox(row, preprocess);
  const roi = cropProposalRoi(source, box, cropContextRatio);
  const roiPreprocess = preprocessNailTextureImage(roi, stage2.inputSize);
  const tensor = new stage2.ort.Tensor(
    "float32",
    roiPreprocess.tensorData,
    roiPreprocess.tensorShape
  );
  const session = stage2.session as SessionLike;
  const inputName = session.inputNames?.[0] ?? "images";
  const outputs = (await session.run({ [inputName]: tensor })) as Record<string, ModelTensorLike>;

  const rows = readDetectionRows(outputs);
  if (rows.length === 0) return 0;
  let best = 0;
  for (const candidate of rows) {
    if (candidate.score > best) best = candidate.score;
  }
  return best;
}

export interface RunTwoStageOptions {
  source: ImagePixels;
  manifest: NailTextureModelManifest;
  stage1Outputs: Record<string, ModelTensorLike>;
  preprocess: NailTexturePreprocessResult;
  stage2: { session: unknown; ort: OrtLike; inputSize: number } | null;
  postprocess: (
    outputs: Record<string, ModelTensorLike>,
    preprocess: NailTexturePreprocessResult,
    options: {
      maxCandidates: number;
      scoreThreshold: number;
      nmsThreshold: number;
      includeLowConfidenceCandidates?: boolean;
      detectionRows?: NailTextureDetectionRow[];
    }
  ) => NailTextureCandidate[];
  maxCandidates: number;
  includeLowConfidenceCandidates?: boolean;
}

export async function runTwoStageComposition(
  options: RunTwoStageOptions
): Promise<TwoStageRunResult> {
  const {
    source,
    manifest,
    stage1Outputs,
    preprocess,
    stage2,
    postprocess,
    maxCandidates,
    includeLowConfidenceCandidates,
  } = options;

  const composition = resolveComposition(manifest);
  const warnings: string[] = [];

  const proposals = readDetectionRows(stage1Outputs)
    .filter((row) => row.score >= composition.proposalThreshold)
    .sort((left, right) => right.score - left.score)
    .slice(0, composition.maximumProposalsPerImage);

  if (proposals.length === 0) {
    return {
      candidates: [],
      evaluatedProposals: 0,
      promotedProposals: 0,
      acceptedByPrimaryRule: 0,
      evaluations: [],
      warnings,
    };
  }

  if (!stage2) {
    warnings.push("stage2_unavailable_only_primary_rule_applied");
  }

  const evaluations: Stage2ProposalEvaluation[] = [];
  for (const proposal of proposals) {
    const isPrimary = proposal.score >= composition.acceptanceThreshold;
    const inPromotionBand =
      proposal.score >= composition.promotionBandMinimum &&
      proposal.score < composition.acceptanceThreshold;

    let stage2Score: number | null = null;
    if (stage2 && inPromotionBand) {
      try {
        stage2Score = await scoreProposalWithStage2(
          source,
          proposal,
          preprocess,
          stage2,
          composition.cropContextRatio
        );
      } catch (error) {
        warnings.push(
          error instanceof Error
            ? `stage2_proposal_scoring_failed:${error.message}`
            : "stage2_proposal_scoring_failed"
        );
      }
    }

    const promoted =
      inPromotionBand &&
      stage2Score != null &&
      stage2Score - proposal.score >= composition.promotionMarginThreshold;

    evaluations.push({
      stage1Score: proposal.score,
      stage2Score,
      accepted: isPrimary || promoted,
      acceptedBy: isPrimary ? "primary" : promoted ? "promotion" : "none",
    });
  }

  // 直接把入选的 stage1 行交给后处理，避免重建张量触发布局启发式误判。
  const acceptedRows = proposals.filter((_, index) => evaluations[index]?.accepted);

  if (acceptedRows.length === 0) {
    return {
      candidates: [],
      evaluatedProposals: proposals.length,
      promotedProposals: evaluations.filter((item) => item.acceptedBy === "promotion").length,
      acceptedByPrimaryRule: evaluations.filter((item) => item.acceptedBy === "primary").length,
      evaluations,
      warnings,
    };
  }

  const candidates = postprocess(stage1Outputs, preprocess, {
    maxCandidates,
    scoreThreshold: 0, // 入选判定已在组合规则中完成，此处不再二次过滤
    nmsThreshold: composition.boxIouThreshold,
    includeLowConfidenceCandidates,
    detectionRows: acceptedRows,
  });

  return {
    candidates,
    evaluatedProposals: proposals.length,
    promotedProposals: evaluations.filter((item) => item.acceptedBy === "promotion").length,
    acceptedByPrimaryRule: evaluations.filter((item) => item.acceptedBy === "primary").length,
    evaluations,
    warnings,
  };
}
