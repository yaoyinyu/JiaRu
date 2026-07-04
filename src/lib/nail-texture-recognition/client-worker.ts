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
  startedAt: number;
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

function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
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

function createWorkerResetError(): Error {
  return new Error("recognition_worker_reset_after_cancellation");
}

function createWorkerDisposedError(): Error {
  return new Error("recognition_worker_disposed");
}

function terminateWorkerAndRejectPending(
  reason: Error | ((id: string) => Error)
): void {
  const worker = workerInstance;
  workerInstance = null;
  worker?.terminate();
  for (const [id, pending] of pendingRequests) {
    pendingRequests.delete(id);
    pending.cleanupAbort?.();
    pending.reject(typeof reason === "function" ? reason(id) : reason);
  }
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
        elapsedMs: Math.max(response.elapsedMs, nowMs() - pending.startedAt),
        workerElapsedMs: response.elapsedMs,
        warnings: response.warnings,
        modelVersion: response.modelVersion,
        modelInfo: response.modelInfo,
      });
    };
    workerInstance.onerror = (event) => {
      const error = event.error ?? new Error(event.message || "worker_error");
      terminateWorkerAndRejectPending(error);
    };
  }
  return workerInstance;
}

export function prepareWorkerImagePixels(
  source: ImagePixels
): Uint8ClampedArray<ArrayBuffer> {
  const expectedLength = source.width * source.height * 4;
  if (source.data.length !== expectedLength) {
    throw new Error(
      `invalid_image_pixel_length:expected_${expectedLength}_actual_${source.data.length}`
    );
  }
  if (
    source.data instanceof Uint8ClampedArray &&
    source.data.buffer instanceof ArrayBuffer
  ) {
    return source.data as Uint8ClampedArray<ArrayBuffer>;
  }
  const pixels = new Uint8ClampedArray(expectedLength);
  pixels.set(source.data);
  return pixels;
}

async function sourceToImageBitmap(source: ImagePixels): Promise<ImageBitmap> {
  const imageData = new ImageData(
    prepareWorkerImagePixels(source),
    source.width,
    source.height
  );
  return createImageBitmap(imageData);
}

export async function recognizeNailTexturesInWorker(
  source: ImagePixels,
  options: RecognizeNailTexturesOptions = {}
): Promise<NailTextureRecognitionResult> {
  const startedAt = nowMs();
  throwIfAborted(options.signal);

  if (!isWorkerRecognitionSupported()) {
    const result = await recognizeNailTextures(source, options);
    return {
      ...result,
      elapsedMs: Math.max(result.elapsedMs, nowMs() - startedAt),
      workerElapsedMs: result.elapsedMs,
      warnings: [...result.warnings, "worker_unavailable_used_main_thread"],
    };
  }

  const id = createRequestId();
  const imageBitmap = await sourceToImageBitmap(source);
  if (options.signal?.aborted) {
    imageBitmap.close();
    throw createAbortError();
  }

  return await new Promise<NailTextureRecognitionResult>((resolve, reject) => {
    const worker = getWorkerInstance();
    const cleanupAbort = (() => {
      if (!options.signal) return undefined;
      const onAbort = () => {
        if (!pendingRequests.has(id)) return;
        terminateWorkerAndRejectPending((pendingId) =>
          pendingId === id ? createAbortError() : createWorkerResetError()
        );
      };
      options.signal.addEventListener("abort", onAbort, { once: true });
      return () => options.signal?.removeEventListener("abort", onAbort);
    })();

    pendingRequests.set(id, { resolve, reject, cleanupAbort, startedAt });

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
  terminateWorkerAndRejectPending(createWorkerDisposedError());
}
