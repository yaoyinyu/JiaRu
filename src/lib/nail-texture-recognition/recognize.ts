import type { ImagePixels } from "../nail-image-detection.ts";
import { recognizeNailTexturesWithFallback } from "./fallback-adapter.ts";
import {
  getNailTextureModelRuntime,
  getNailTextureStage2Runtime,
  loadNailTextureModelManifest,
} from "./model-runtime.ts";
import { serializeModelOutputs, summarizeModelOutputs } from "./debug.ts";
import {
  postprocessNailTextureDetections,
  type ModelTensorLike,
} from "./postprocess.ts";
import { preprocessNailTextureImage, type NailTexturePreprocessResult } from "./preprocess.ts";
import { runTwoStageComposition } from "./two-stage.ts";

function toPreprocessInfo(preprocess: NailTexturePreprocessResult) {
  return {
    inputSize: preprocess.inputSize,
    originalWidth: preprocess.originalWidth,
    originalHeight: preprocess.originalHeight,
    scaleX: preprocess.scaleX,
    scaleY: preprocess.scaleY,
    resizeScale: preprocess.resizeScale,
    resizedWidth: preprocess.resizedWidth,
    resizedHeight: preprocess.resizedHeight,
    padLeft: preprocess.padLeft,
    padTop: preprocess.padTop,
  };
}
import type {
  RecognizeNailTexturesOptions,
  NailTextureRecognitionResult,
} from "./types.ts";

interface SessionLike {
  inputNames?: string[];
  run: (feeds: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function firstInputName(session: SessionLike): string {
  return session.inputNames?.[0] ?? "images";
}

export async function recognizeNailTextures(
  source: ImagePixels,
  options: RecognizeNailTexturesOptions = {}
): Promise<NailTextureRecognitionResult> {
  let fallbackCache: NailTextureRecognitionResult | null = null;
  const getFallback = (): NailTextureRecognitionResult => {
    fallbackCache ??= recognizeNailTexturesWithFallback(source, {
      maxCandidates: options.maxCandidates,
    });
    return fallbackCache;
  };

  if (!options.preferModel) {
    return getFallback();
  }

  const startedAt = nowMs();
  let runtime: Awaited<ReturnType<typeof getNailTextureModelRuntime>>;
  try {
    runtime = await getNailTextureModelRuntime(options.manifestUrl);
  } catch (error) {
    const fallback = getFallback();
    return {
      ...fallback,
      warnings: [
        ...fallback.warnings,
        error instanceof Error ? `model_manifest_error:${error.message}` : "model_manifest_error",
      ],
    };
  }

  if (!runtime.available || !runtime.info) {
    const fallback = getFallback();
    return {
      ...fallback,
      warnings: [...fallback.warnings, ...runtime.warnings],
    };
  }

  try {
    if (!runtime.session || !runtime.ort?.Tensor) {
      const fallback = getFallback();
      return {
        ...fallback,
        warnings: [...fallback.warnings, ...runtime.warnings, "onnx_session_or_tensor_unavailable"],
      };
    }

    const preprocess = preprocessNailTextureImage(source, runtime.info.inputSize);
    const tensor = new runtime.ort.Tensor("float32", preprocess.tensorData, preprocess.tensorShape);
    const session = runtime.session as SessionLike;
    const outputs = await session.run({
      [firstInputName(session)]: tensor,
    });
    const debugOutputs = options.debugOutputs
      ? summarizeModelOutputs(outputs as Record<string, ModelTensorLike>)
      : undefined;
    const rawModelOutputs = options.debugRawModelOutputs
      ? serializeModelOutputs(outputs as Record<string, ModelTensorLike>)
      : undefined;
    const manifest = await loadNailTextureModelManifest(options.manifestUrl);

    // 两阶段组合运行时：仅当 manifest 显式声明 stage2 时启用，单模型路径完全不受影响。
    if (manifest.stage2) {
      const stage2Runtime = await getNailTextureStage2Runtime(manifest, options.manifestUrl);
      const stage2 =
        stage2Runtime.available && stage2Runtime.session && stage2Runtime.ort?.Tensor
          ? {
              session: stage2Runtime.session,
              ort: stage2Runtime.ort as unknown as {
                Tensor: new (
                  type: string,
                  data: Float32Array,
                  dims: readonly number[]
                ) => unknown;
              },
              inputSize: stage2Runtime.inputSize,
            }
          : null;

      const twoStage = await runTwoStageComposition({
        source,
        manifest,
        stage1Outputs: outputs as Record<string, ModelTensorLike>,
        preprocess,
        stage2,
        postprocess: (stageOutputs, stagePreprocess, stageOptions) =>
          postprocessNailTextureDetections(stageOutputs, stagePreprocess, stageOptions),
        maxCandidates: options.maxCandidates ?? 10,
        includeLowConfidenceCandidates: options.includeLowConfidenceCandidates,
      });

      const stage2Diagnostics = {
        evaluatedProposals: twoStage.evaluatedProposals,
        promotedProposals: twoStage.promotedProposals,
        acceptedByPrimaryRule: twoStage.acceptedByPrimaryRule,
        stage2ModelVersion: manifest.stage2.modelFile,
      };
      const twoStageWarnings = [
        ...runtime.warnings,
        ...stage2Runtime.warnings,
        ...twoStage.warnings,
        ...(manifest.testOnly ? ["test_only_manifest_not_production_identity"] : []),
      ];

      if (twoStage.candidates.length === 0) {
        const fallback = getFallback();
        return {
          ...fallback,
          debugOutputs,
          rawModelOutputs,
          stage2: stage2Diagnostics,
          preprocess: toPreprocessInfo(preprocess),
          warnings: [
            ...fallback.warnings,
            ...twoStageWarnings,
            "model_outputs_empty_used_fallback",
          ],
        };
      }

      return {
        candidates: twoStage.candidates,
        backend: "model",
        elapsedMs: nowMs() - startedAt,
        modelVersion: runtime.info.version,
        modelInfo: runtime.info,
        warnings: twoStageWarnings,
        debugOutputs,
        rawModelOutputs,
        stage2: stage2Diagnostics,
        preprocess: toPreprocessInfo(preprocess),
      };
    }

    const candidates = postprocessNailTextureDetections(
      outputs as Record<string, ModelTensorLike>,
      preprocess,
      {
        maxCandidates: options.maxCandidates ?? 10,
        includeLowConfidenceCandidates: options.includeLowConfidenceCandidates,
        scoreThreshold: runtime.info.scoreThreshold,
      }
    );

    if (candidates.length === 0) {
      const fallback = getFallback();
      return {
        ...fallback,
        debugOutputs,
        rawModelOutputs,
        preprocess: {
          inputSize: preprocess.inputSize,
          originalWidth: preprocess.originalWidth,
          originalHeight: preprocess.originalHeight,
          scaleX: preprocess.scaleX,
          scaleY: preprocess.scaleY,
          resizeScale: preprocess.resizeScale,
          resizedWidth: preprocess.resizedWidth,
          resizedHeight: preprocess.resizedHeight,
          padLeft: preprocess.padLeft,
          padTop: preprocess.padTop,
        },
        warnings: [...fallback.warnings, ...runtime.warnings, "model_outputs_empty_used_fallback"],
      };
    }

    return {
      candidates,
      backend: "model",
      elapsedMs: nowMs() - startedAt,
      modelVersion: runtime.info.version,
      modelInfo: runtime.info,
      warnings: runtime.warnings,
      debugOutputs,
      rawModelOutputs,
      preprocess: {
        inputSize: preprocess.inputSize,
        originalWidth: preprocess.originalWidth,
        originalHeight: preprocess.originalHeight,
        scaleX: preprocess.scaleX,
        scaleY: preprocess.scaleY,
        resizeScale: preprocess.resizeScale,
        resizedWidth: preprocess.resizedWidth,
        resizedHeight: preprocess.resizedHeight,
        padLeft: preprocess.padLeft,
        padTop: preprocess.padTop,
      },
      };
  } catch (error) {
    const fallback = getFallback();
    return {
      ...fallback,
      warnings: [
        ...fallback.warnings,
        error instanceof Error ? `model_inference_error:${error.message}` : "model_inference_error",
      ],
    };
  }
}
