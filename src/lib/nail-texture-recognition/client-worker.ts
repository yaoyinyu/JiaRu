import type { ImagePixels } from "../nail-image-detection.ts";
import { recognizeNailTextures } from "./recognize.ts";
import type {
  RecognizeNailTextureRequest,
  RecognizeNailTextureResponse,
  RecognizeNailTexturesOptions,
  NailTextureRecognitionResult,
} from "./types.ts";

type PendingRequest = {
  resolve: (value: NailTextureRecognitionResult) => void;
  reject: (reason?: unknown) => void;
};

let workerInstance: Worker | null = null;
const pendingRequests = new Map<string, PendingRequest>();

function isWorkerRecognitionSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof Worker !== "undefined" &&
    typeof createImageBitmap !== "undefined"
  );
}

function createRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `nail-texture-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getWorkerInstance(): Worker {
  if (!workerInstance) {
    workerInstance = new Worker(
      new URL("../../workers/nail-texture-recognition.worker.ts", import.meta.url),
      { type: "module" }
    );
    workerInstance.onmessage = (
      event: MessageEvent<RecognizeNailTextureResponse>
    ) => {
      const response = event.data;
      const pending = pendingRequests.get(response.id);
      if (!pending) return;
      pendingRequests.delete(response.id);
      pending.resolve({
        candidates: response.candidates,
        backend: response.backend,
        elapsedMs: response.elapsedMs,
        warnings: response.warnings,
        modelVersion: response.modelVersion,
      });
    };
    workerInstance.onerror = (event) => {
      const error = event.error ?? new Error(event.message || "worker_error");
      for (const [id, pending] of pendingRequests) {
        pendingRequests.delete(id);
        pending.reject(error);
      }
    };
  }
  return workerInstance;
}

async function sourceToImageBitmap(source: ImagePixels): Promise<ImageBitmap> {
  const pixels = new Uint8ClampedArray(source.width * source.height * 4);
  pixels.set(Array.from(source.data));
  const imageData = new ImageData(pixels, source.width, source.height);
  return createImageBitmap(imageData);
}

export async function recognizeNailTexturesInWorker(
  source: ImagePixels,
  options: RecognizeNailTexturesOptions = {}
): Promise<NailTextureRecognitionResult> {
  if (!isWorkerRecognitionSupported()) {
    const result = await recognizeNailTextures(source, options);
    return {
      ...result,
      warnings: [...result.warnings, "worker_unavailable_used_main_thread"],
    };
  }

  const id = createRequestId();
  const imageBitmap = await sourceToImageBitmap(source);

  return await new Promise<NailTextureRecognitionResult>((resolve, reject) => {
    const worker = getWorkerInstance();
    pendingRequests.set(id, { resolve, reject });

    const request: RecognizeNailTextureRequest = {
      id,
      imageBitmap,
      maxCandidates: 5,
      preferModel: options.preferModel ?? true,
      manifestUrl: options.manifestUrl,
    };

    worker.postMessage(request, [imageBitmap]);
  });
}

export function disposeNailTextureRecognitionWorker(): void {
  if (workerInstance) {
    workerInstance.terminate();
    workerInstance = null;
  }
  pendingRequests.clear();
}
