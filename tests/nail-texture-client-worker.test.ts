import assert from "node:assert/strict";
import test from "node:test";
import {
  disposeNailTextureRecognitionWorker,
  recognizeNailTexturesInWorker,
  type RecognizeNailTextureResponse,
} from "../src/lib/nail-texture-recognition/index.ts";
import { prepareWorkerImagePixels } from "../src/lib/nail-texture-recognition/client-worker.ts";

test("prepareWorkerImagePixels reuses clamped RGBA storage without copying", () => {
  const source = new Uint8ClampedArray(16).fill(127);
  const prepared = prepareWorkerImagePixels({ width: 2, height: 2, data: source });
  assert.equal(prepared, source);
});

test("prepareWorkerImagePixels copies generic array-like pixels with native typed-array set", () => {
  const source = new Uint8Array(16).fill(300);
  const prepared = prepareWorkerImagePixels({ width: 2, height: 2, data: source });
  assert.notEqual(prepared, source);
  assert.equal(prepared.length, 16);
  assert.equal(prepared[0], 44);
});

test("prepareWorkerImagePixels copies SharedArrayBuffer pixels for ImageData compatibility", () => {
  const source = new Uint8ClampedArray(new SharedArrayBuffer(16)).fill(91);
  const prepared = prepareWorkerImagePixels({ width: 2, height: 2, data: source });
  assert.notEqual(prepared, source);
  assert.ok(prepared.buffer instanceof ArrayBuffer);
  assert.equal(prepared[0], 91);
});
test("prepareWorkerImagePixels rejects malformed RGBA lengths", () => {
  assert.throws(
    () => prepareWorkerImagePixels({ width: 2, height: 2, data: new Uint8Array(15) }),
    /invalid_image_pixel_length:expected_16_actual_15/
  );
});
test("recognizeNailTexturesInWorker preserves modelInfo from worker response", async () => {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const workerDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Worker");
  const imageDataDescriptor = Object.getOwnPropertyDescriptor(globalThis, "ImageData");
  const createImageBitmapDescriptor = Object.getOwnPropertyDescriptor(globalThis, "createImageBitmap");
  const performanceDescriptor = Object.getOwnPropertyDescriptor(globalThis, "performance");

  class FakeImageData {
    data: Uint8ClampedArray;
    width: number;
    height: number;

    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data;
      this.width = width;
      this.height = height;
    }
  }

  const postedRequests: Array<{ id: string; maxCandidates: number }> = [];
  const sourcePixels = new Uint8ClampedArray(16).fill(255);
  let bitmapInputPixels: Uint8ClampedArray | null = null;

  class FakeWorker {
    static latestInstance: FakeWorker | null = null;
    onmessage: ((event: MessageEvent<RecognizeNailTextureResponse>) => void) | null = null;
    onerror: ((event: ErrorEvent) => void) | null = null;

    constructor() {}

    postMessage(message: { id: string; maxCandidates: number }) {
      postedRequests.push({ id: message.id, maxCandidates: message.maxCandidates });
      this.onmessage?.({
        data: {
          id: message.id,
          candidates: [],
          backend: "model",
          elapsedMs: 17,
          warnings: [],
          modelVersion: "nail-texture-seg-v7",
          modelInfo: {
            version: "nail-texture-seg-v7",
            backend: "webgpu",
            inputSize: 640,
            loadedAt: 123,
            modelUrl: "https://example.com/nail-texture-seg-v7.onnx",
            inputNames: ["images"],
            outputNames: ["output0"],
          },
        },
      } as MessageEvent<RecognizeNailTextureResponse>);
    }

    terminate() {}
  }

    let now = 100;
  Object.defineProperty(globalThis, "performance", {
    configurable: true,
    writable: true,
    value: {
      now: () => {
        const value = now;
        now += 50;
        return value;
      },
    },
  });
Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {},
  });
  Object.defineProperty(globalThis, "Worker", {
    configurable: true,
    writable: true,
    value: FakeWorker,
  });
  Object.defineProperty(globalThis, "ImageData", {
    configurable: true,
    writable: true,
    value: FakeImageData,
  });
  Object.defineProperty(globalThis, "createImageBitmap", {
    configurable: true,
    writable: true,
    value: async (imageData: FakeImageData) => {
      bitmapInputPixels = imageData.data;
      return { width: 2, height: 2 };
    },
  });

  try {
    const result = await recognizeNailTexturesInWorker(
      {
        width: 2,
        height: 2,
        data: sourcePixels,
      },
      {
        preferModel: true,
        manifestUrl: "https://example.com/models/nail-texture-seg/v7/manifest.json",
      }
    );

    assert.equal(result.backend, "model");
    assert.equal(result.elapsedMs, 50);
    assert.equal(result.workerElapsedMs, 17);
    assert.equal(result.modelVersion, "nail-texture-seg-v7");
    assert.equal(result.modelInfo?.backend, "webgpu");
    assert.equal(result.modelInfo?.inputSize, 640);
    assert.equal(postedRequests[0]?.maxCandidates, 10);
    assert.equal(bitmapInputPixels, sourcePixels);
  } finally {
    disposeNailTextureRecognitionWorker();
        if (performanceDescriptor) {
      Object.defineProperty(globalThis, "performance", performanceDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { performance?: unknown }).performance;
    }if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (workerDescriptor) {
      Object.defineProperty(globalThis, "Worker", workerDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { Worker?: unknown }).Worker;
    }
    if (imageDataDescriptor) {
      Object.defineProperty(globalThis, "ImageData", imageDataDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { ImageData?: unknown }).ImageData;
    }
    if (createImageBitmapDescriptor) {
      Object.defineProperty(globalThis, "createImageBitmap", createImageBitmapDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { createImageBitmap?: unknown }).createImageBitmap;
    }
  }
});

test("recognizeNailTexturesInWorker forwards explicit maxCandidates to worker", async () => {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const workerDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Worker");
  const imageDataDescriptor = Object.getOwnPropertyDescriptor(globalThis, "ImageData");
  const createImageBitmapDescriptor = Object.getOwnPropertyDescriptor(globalThis, "createImageBitmap");

  const postedRequests: Array<{ id: string; maxCandidates: number }> = [];

  class FakeImageData {
    data: Uint8ClampedArray;
    width: number;
    height: number;

    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data;
      this.width = width;
      this.height = height;
    }
  }

  class FakeWorker {
    static latestInstance: FakeWorker | null = null;
    onmessage: ((event: MessageEvent<RecognizeNailTextureResponse>) => void) | null = null;
    onerror: ((event: ErrorEvent) => void) | null = null;

    constructor() {}

    postMessage(message: { id: string; maxCandidates: number }) {
      postedRequests.push({ id: message.id, maxCandidates: message.maxCandidates });
      this.onmessage?.({
        data: {
          id: message.id,
          candidates: [],
          backend: "fallback",
          elapsedMs: 3,
          warnings: [],
        },
      } as MessageEvent<RecognizeNailTextureResponse>);
    }

    terminate() {}
  }

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {},
  });
  Object.defineProperty(globalThis, "Worker", {
    configurable: true,
    writable: true,
    value: FakeWorker,
  });
  Object.defineProperty(globalThis, "ImageData", {
    configurable: true,
    writable: true,
    value: FakeImageData,
  });
  Object.defineProperty(globalThis, "createImageBitmap", {
    configurable: true,
    writable: true,
    value: async () => ({ width: 2, height: 2 }),
  });

  try {
    await recognizeNailTexturesInWorker(
      {
        width: 2,
        height: 2,
        data: new Uint8ClampedArray(16).fill(255),
      },
      {
        preferModel: true,
        maxCandidates: 7,
      }
    );

    assert.equal(postedRequests[0]?.maxCandidates, 7);
  } finally {
    disposeNailTextureRecognitionWorker();
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (workerDescriptor) {
      Object.defineProperty(globalThis, "Worker", workerDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { Worker?: unknown }).Worker;
    }
    if (imageDataDescriptor) {
      Object.defineProperty(globalThis, "ImageData", imageDataDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { ImageData?: unknown }).ImageData;
    }
    if (createImageBitmapDescriptor) {
      Object.defineProperty(globalThis, "createImageBitmap", createImageBitmapDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { createImageBitmap?: unknown }).createImageBitmap;
    }
  }
});

test("recognizeNailTexturesInWorker rejects with AbortError when cancelled", async () => {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const workerDescriptor = Object.getOwnPropertyDescriptor(globalThis, "Worker");
  const imageDataDescriptor = Object.getOwnPropertyDescriptor(globalThis, "ImageData");
  const createImageBitmapDescriptor = Object.getOwnPropertyDescriptor(globalThis, "createImageBitmap");

  

  class FakeImageData {
    data: Uint8ClampedArray;
    width: number;
    height: number;

    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data;
      this.width = width;
      this.height = height;
    }
  }

  class FakeWorker {
    static latestInstance: FakeWorker | null = null;
    onmessage: ((event: MessageEvent<RecognizeNailTextureResponse>) => void) | null = null;
    onerror: ((event: ErrorEvent) => void) | null = null;
    postedIds: string[] = [];
    terminated = false;

    constructor() {
      FakeWorker.latestInstance = this;
    }

    postMessage(message: { id: string }) {
      this.postedIds.push(message.id);
    }

    terminate() {
      this.terminated = true;
    }
  }

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {},
  });
  Object.defineProperty(globalThis, "Worker", {
    configurable: true,
    writable: true,
    value: FakeWorker,
  });
  Object.defineProperty(globalThis, "ImageData", {
    configurable: true,
    writable: true,
    value: FakeImageData,
  });
  Object.defineProperty(globalThis, "createImageBitmap", {
    configurable: true,
    writable: true,
    value: async () => ({ width: 2, height: 2 }),
  });

  try {
    const controller = new AbortController();
    const pending = recognizeNailTexturesInWorker(
      {
        width: 2,
        height: 2,
        data: new Uint8ClampedArray(16).fill(255),
      },
      {
        preferModel: true,
        signal: controller.signal,
      }
    );

    while (!FakeWorker.latestInstance?.postedIds.length) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    controller.abort();

    await assert.rejects(
      pending,
      (error: Error) => error.name === "AbortError" && error.message === "recognition_cancelled_by_user"
    );

    assert.equal(FakeWorker.latestInstance?.terminated, true);

    const requestId = FakeWorker.latestInstance?.postedIds[0];
    if (requestId) {
      FakeWorker.latestInstance?.onmessage?.({
        data: {
          id: requestId,
          candidates: [],
          backend: "fallback",
          elapsedMs: 1,
          warnings: [],
        },
      } as MessageEvent<RecognizeNailTextureResponse>);
    }
  } finally {
    disposeNailTextureRecognitionWorker();
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { window?: unknown }).window;
    }
    if (workerDescriptor) {
      Object.defineProperty(globalThis, "Worker", workerDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { Worker?: unknown }).Worker;
    }
    if (imageDataDescriptor) {
      Object.defineProperty(globalThis, "ImageData", imageDataDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { ImageData?: unknown }).ImageData;
    }
    if (createImageBitmapDescriptor) {
      Object.defineProperty(globalThis, "createImageBitmap", createImageBitmapDescriptor);
    } else {
      delete (globalThis as typeof globalThis & { createImageBitmap?: unknown }).createImageBitmap;
    }
  }
});
