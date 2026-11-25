export const LIGHT_FRAME_WIDTH = 96;
export const LIGHT_FRAME_HEIGHT = 54;
export const LIGHT_FRAME_TTL_MS = 320;

export function getArLightCrop(vw: number, vh: number, width: number, height: number) {
  const scale = Math.max(width / vw, height / vh);
  const sw = Math.min(vw, width / scale);
  const sh = Math.min(vh, height / scale);
  return [(vw - sw) / 2, (vh - sh) / 2, sw, sh] as const;
}

export function createArLightSampler() {
  const worker = new Worker("/ar/light-sampler.worker.js");
  let closed = false;
  let pending: { width: number; height: number; vw: number; vh: number; at: number } | undefined;
  let cached: (NonNullable<typeof pending> & { pixels: ImageData }) | undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;

  function close() {
    if (closed) return;
    closed = true;
    clearTimeout(timeout);
    pending = cached = undefined;
    worker.terminate();
  }

  worker.onerror = worker.onmessageerror = close;
  worker.onmessage = ({ data }: MessageEvent<ImageData | null>) => {
    if (closed || !pending) return;
    if (!data || data.width !== LIGHT_FRAME_WIDTH || data.height !== LIGHT_FRAME_HEIGHT) {
      close();
      return;
    }
    clearTimeout(timeout);
    cached = { ...pending, pixels: data };
    pending = undefined;
  };

  function read(video: HTMLVideoElement, width: number, height: number): ImageData | undefined {
    if (closed || video.readyState < 2 || width <= 0 || height <= 0) return;
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return;

    const at = performance.now();
    const previous = cached?.width === width && cached.height === height && cached.vw === vw && cached.vh === vh
      ? cached
      : undefined;
    if (!pending && (!previous || at - previous.at >= LIGHT_FRAME_TTL_MS)) {
      let frame: VideoFrame | undefined;
      try {
        frame = new VideoFrame(video, { timestamp: Math.round(video.currentTime * 1_000_000) });
        pending = { width, height, vw, vh, at };
        worker.postMessage({ frame, crop: getArLightCrop(vw, vh, width, height) }, [frame]);
        timeout = setTimeout(close, 1_000);
      } catch {
        frame?.close();
        close();
        return;
      }
    }
    if (previous && at - previous.at <= 2 * LIGHT_FRAME_TTL_MS) return previous.pixels;
  }

  return { read, close };
}
