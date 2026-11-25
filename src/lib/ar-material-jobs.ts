import type { ArMaterialParams } from "./ar-material-painter";

export interface MaterialJob {
  textureId: number;
  canvasWidth: number;
  canvasHeight: number;
  material: ArMaterialParams;
}

export type MaterialResult = { bitmap: ImageBitmap } | { error: string };

export interface MaterialRequest extends MaterialJob {
  copy?: ImageBitmap;
  grain?: ImageData;
  retire: number[];
}

export function createArMaterialJobs(getGrainData: () => ImageData) {
  const worker = new Worker(new URL("../workers/ar-material.worker.ts", import.meta.url), {
    type: "module",
    name: "ar-material",
  });
  const registered = new Set<number>();
  let closed = false;
  let initialized = false;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  let finish: ((result: MaterialResult) => void) | undefined;

  function close() {
    if (closed) return;
    closed = true;
    clearTimeout(timeout);
    worker.terminate();
    finish = undefined;
    registered.clear();
  }

  function fail(err: unknown) {
    const reject = finish;
    close();
    reject?.({ error: String(err) });
  }

  worker.onerror = event => {
    event.preventDefault();
    fail(event.message);
  };
  worker.onmessageerror = () => fail("material result decoding failed");
  worker.onmessage = ({ data }: MessageEvent<MaterialResult>) => {
    const callback = finish;
    finish = undefined;
    clearTimeout(timeout);
    if ("error" in data) {
      close();
      callback?.(data);
    } else if (callback) callback(data);
    else data.bitmap.close();
  };

  function submit(
    texture: ImageBitmap,
    job: MaterialJob,
    liveTextures: readonly number[],
    callback: (result: MaterialResult) => void,
  ) {
    if (closed || finish) return false;
    finish = callback;
    timeout = setTimeout(() => fail("material worker timeout"), 2000);
    void (async () => {
      let copy: ImageBitmap | undefined;
      try {
        if (!registered.has(job.textureId)) copy = await createImageBitmap(texture);
        if (closed) {
          copy?.close();
          return;
        }
        const retire = [...registered].filter(id => !liveTextures.includes(id));
        const request: MaterialRequest = { ...job, copy, retire, grain: initialized ? undefined : getGrainData() };
        worker.postMessage(request, copy ? [copy] : []);
        initialized = true;
        for (const id of retire) registered.delete(id);
        registered.add(job.textureId);
      } catch (err) {
        copy?.close();
        fail(err);
      }
    })();
    return true;
  }

  return { submit, close, get closed() { return closed; } };
}
