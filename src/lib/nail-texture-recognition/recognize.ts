import type { ImagePixels } from "../nail-image-detection.ts";
import { recognizeNailTexturesWithFallback } from "./fallback-adapter.ts";
import { getNailTextureModelRuntime } from "./model-runtime.ts";
import { serializeModelOutputs, summarizeModelOutputs } from "./debug.ts";
import {
  postprocessNailTextureDetections,
  type ModelTensorLike,
} from "./postprocess.ts";
import { preprocessNailTextureImage } from "./preprocess.ts";
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
    const candidates = postprocessNailTextureDetections(
      outputs as Record<string, ModelTensorLike>,
      preprocess,
      {
        maxCandidates: options.maxCandidates ?? 10,
        includeLowConfidenceCandidates: options.includeLowConfidenceCandidates,
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
