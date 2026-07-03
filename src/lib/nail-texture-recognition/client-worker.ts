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
  cleanupAbort?: () => void;
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

function createAbortError(): Error {
  const error = new Error("recognition_cancelled_by_user");
  error.name = "AbortError";
  return error;
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw createAbortError();
  }
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
      pending.cleanupAbort?.();
      pending.resolve({
        candidates: response.candidates,
        backend: response.backend,
        elapsedMs: response.elapsedMs,
        warnings: response.warnings,
        modelVersion: response.modelVersion,
        modelInfo: response.modelInfo,
      });
    };
    workerInstance.onerror = (event) => {
      const error = event.error ?? new Error(event.message || "worker_error");
      for (const [id, pending] of pendingRequests) {
        pendingRequests.delete(id);
        pending.cleanupAbort?.();
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
  throwIfAborted(options.signal);

  if (!isWorkerRecognitionSupported()) {
    const result = await recognizeNailTextures(source, options);
    return {
      ...result,
      warnings: [...result.warnings, "worker_unavailable_used_main_thread"],
    };
  }

  const id = createRequestId();
  const imageBitmap = await sourceToImageBitmap(source);
  throwIfAborted(options.signal);

  return await new Promise<NailTextureRecognitionResult>((resolve, reject) => {
    const worker = getWorkerInstance();
    const cleanupAbort = (() => {
      if (!options.signal) return undefined;
      const onAbort = () => {
        const pending = pendingRequests.get(id);
        if (!pending) return;
        pendingRequests.delete(id);
        pending.cleanupAbort?.();
        reject(createAbortError());
      };
      options.signal.addEventListener("abort", onAbort, { once: true });
      return () => options.signal?.removeEventListener("abort", onAbort);
    })();

    pendingRequests.set(id, { resolve, reject, cleanupAbort });

    if (options.signal?.aborted) {
      pendingRequests.delete(id);
      cleanupAbort?.();
      reject(createAbortError());
      return;
    }

    const request: RecognizeNailTextureRequest = {
      id,
      imageBitmap,
      maxCandidates: Math.max(1, options.maxCandidates ?? 10),
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