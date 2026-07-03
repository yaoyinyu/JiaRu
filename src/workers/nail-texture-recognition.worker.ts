import { recognizeNailTextures } from "@/lib/nail-texture-recognition";
import type {
  RecognizeNailTextureRequest,
  RecognizeNailTextureResponse,
} from "@/lib/nail-texture-recognition";

async function imageBitmapToImageData(imageBitmap: ImageBitmap): Promise<ImageData> {
  const canvas = new OffscreenCanvas(imageBitmap.width, imageBitmap.height);
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("worker_2d_context_unavailable");
  }
  context.drawImage(imageBitmap, 0, 0);
  return context.getImageData(0, 0, imageBitmap.width, imageBitmap.height);
}

self.onmessage = async (event: MessageEvent<RecognizeNailTextureRequest>) => {
  const request = event.data;

  try {
    const imageData = await imageBitmapToImageData(request.imageBitmap);
    const result = await recognizeNailTextures(
      {
        width: imageData.width,
        height: imageData.height,
        data: imageData.data,
      },
      {
        preferModel: request.preferModel,
        manifestUrl: request.manifestUrl,
        maxCandidates: request.maxCandidates,
      }
    );

    const response: RecognizeNailTextureResponse = {
      id: request.id,
      candidates: result.candidates.slice(0, request.maxCandidates),
      backend: result.backend,
      elapsedMs: result.elapsedMs,
      warnings: result.warnings,
      modelVersion: result.modelVersion,
      modelInfo: result.modelInfo,
    };
    self.postMessage(response);
  } catch (error) {
    const response: RecognizeNailTextureResponse = {
      id: request.id,
      candidates: [],
      backend: "fallback",
      elapsedMs: 0,
      warnings: [
        error instanceof Error ? `worker_recognition_error:${error.message}` : "worker_recognition_error",
      ],
    };
    self.postMessage(response);
  }
};
