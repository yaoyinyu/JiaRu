import type { ImagePixels } from "../nail-image-detection.ts";
import { getNailTextureModelRuntime } from "./model-runtime.ts";
import { preprocessNailTextureImage } from "./preprocess.ts";
import { postprocessNailTextureDetections, type ModelTensorLike } from "./postprocess.ts";

/** Stage A 粗分割实例（归一化到源图 0–1）。仅粗遮罩几何，不含 Stage B 精修。 */
export interface NailCoarseInstance {
  cx: number;
  cy: number;
  w: number;
  h: number;
  angle: number;
  score: number;
}

export interface StageACoarseResult {
  instances: NailCoarseInstance[];
  elapsedMs: number;
  warnings: string[];
  available: boolean;
}

export interface ArSegKeyframeRequest {
  id: string;
  imageBitmap: ImageBitmap;
}

export interface ArSegKeyframeResponse {
  id: string;
  instances: NailCoarseInstance[];
  elapsedMs: number;
  warnings: string[];
}

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

/**
 * M3 关键帧粗分割：只跑已发布浏览器模型的 Stage A（512 letterbox、WASM 单后端），
 * 不跑 Stage B 逐 ROI 精修（完整提取链 P95 4.87s 不可实时）。返回粗实例供
 * `ar-seg-keyframe.ts` 做实例→手指关联与滞回，融合进实时可见性（覆盖分布外召回）。
 * 模型不可用/推理失败返回空实例，实时链路回退几何先验，不阻塞主跟踪。
 */
export async function runStageACoarse(
  source: ImagePixels,
  options: { manifestUrl?: string; maxCandidates?: number } = {},
): Promise<StageACoarseResult> {
  const startedAt = nowMs();
  let runtime: Awaited<ReturnType<typeof getNailTextureModelRuntime>>;
  try {
    runtime = await getNailTextureModelRuntime(options.manifestUrl);
  } catch {
    return { instances: [], elapsedMs: 0, warnings: ["stage_a_manifest_error"], available: false };
  }
  if (!runtime.available || !runtime.session || !runtime.ort?.Tensor || !runtime.info) {
    return { instances: [], elapsedMs: 0, warnings: [...runtime.warnings], available: false };
  }
  try {
    const preprocess = preprocessNailTextureImage(source, runtime.info.inputSize);
    const tensor = new runtime.ort.Tensor("float32", preprocess.tensorData, preprocess.tensorShape);
    const session = runtime.session as {
      inputNames?: string[];
      run: (feeds: Record<string, unknown>) => Promise<Record<string, unknown>>;
    };
    const outputs = await session.run({ [session.inputNames?.[0] ?? "images"]: tensor });
    const candidates = postprocessNailTextureDetections(
      outputs as Record<string, ModelTensorLike>,
      preprocess,
      {
        maxCandidates: options.maxCandidates ?? 10,
        scoreThreshold: runtime.info.scoreThreshold,
      },
    );
    const instances: NailCoarseInstance[] = candidates.map(c => ({
      cx: c.cx / source.width,
      cy: c.cy / source.height,
      w: c.width / source.width,
      h: c.length / source.height,
      angle: c.angle,
      score: c.score,
    }));
    return {
      instances,
      elapsedMs: nowMs() - startedAt,
      warnings: [...runtime.warnings],
      available: true,
    };
  } catch {
    return { instances: [], elapsedMs: 0, warnings: ["stage_a_inference_error"], available: false };
  }
}