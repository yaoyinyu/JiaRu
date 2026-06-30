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

function firstInputName(session: SessionLike): string {
  return session.inputNames?.[0] ?? "images";
}

export async function recognizeNailTextures(
  source: ImagePixels,
  options: RecognizeNailTexturesOptions = {}
): Promise<NailTextureRecognitionResult> {
  const fallback = recognizeNailTexturesWithFallback(source);
  if (!options.preferModel) {
    return fallback;
  }

  try {
    const runtime = await getNailTextureModelRuntime(options.manifestUrl);
    if (!runtime.available || !runtime.info) {
      return {
        ...fallback,
        warnings: [...fallback.warnings, ...runtime.warnings],
      };
    }

    if (!runtime.session || !runtime.ort?.Tensor) {
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
      preprocess
    );

    if (candidates.length === 0) {
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
      elapsedMs: fallback.elapsedMs,
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
    return {
      ...fallback,
      warnings: [
        ...fallback.warnings,
        error instanceof Error ? `model_manifest_error:${error.message}` : "model_manifest_error",
      ],
    };
  }
}
