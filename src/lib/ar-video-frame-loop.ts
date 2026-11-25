export interface ArVideoFrame {
  sequence: number;
  mediaTime: number;
  observedAt: number;
  width: number;
  height: number;
}

export function startArVideoFrameLoop(
  video: HTMLVideoElement,
  processFrame: (frame: ArVideoFrame) => Promise<void>,
): () => void {
  return startFrameQueue(video, frame => frame, processFrame, () => {});
}

export interface ArCapturedFrame extends ArVideoFrame {
  image: VideoFrame;
}

export function startCapturedArVideoFrameLoop(
  video: HTMLVideoElement,
  processFrame: (frame: ArCapturedFrame) => Promise<void>,
  onCaptureError: (error: unknown) => void,
): () => void {
  return startFrameQueue(video, frame => {
    try {
      const image = new VideoFrame(video, { timestamp: Math.round(frame.mediaTime * 1_000_000) });
      return { ...frame, width: image.displayWidth, height: image.displayHeight, image };
    } catch (error) {
      onCaptureError(error);
      return undefined;
    }
  }, processFrame, frame => frame.image.close());
}

function createLatestFrameQueue<T>(processFrame: (frame: T) => Promise<void>, release: (frame: T) => void) {
  let stopped = false;
  let pending: T | undefined;
  let busy = false;

  async function processPending() {
    busy = true;
    try {
      while (pending !== undefined) {
        const frame = pending;
        pending = undefined;
        try {
          await processFrame(frame);
        } finally {
          release(frame);
        }
      }
    } finally {
      busy = false;
    }
  }

  function offer(frame: T) {
    if (stopped) {
      release(frame);
      return;
    }
    if (pending !== undefined) release(pending);
    pending = frame;
    if (!busy) void processPending();
  }

  function close() {
    stopped = true;
    if (pending !== undefined) release(pending);
    pending = undefined;
  }

  return { offer, close };
}

function startFrameQueue<T>(
  video: HTMLVideoElement,
  capture: (frame: ArVideoFrame) => T | undefined,
  processFrame: (frame: T) => Promise<void>,
  release: (frame: T) => void,
): () => void {
  const queue = createLatestFrameQueue(processFrame, release);
  let stopped = false;
  let sequence = 0;
  let lastMediaTime: number | undefined;
  let requestId: number;
  const useVideoCallback = typeof video.requestVideoFrameCallback === "function";

  function observeFrame(now: number, metadata?: VideoFrameCallbackMetadata) {
    if (stopped) return;
    requestId = useVideoCallback
      ? video.requestVideoFrameCallback(observeFrame)
      : requestAnimationFrame(observeFrame);
    if (video.readyState < 2) return;

    const mediaTime = metadata?.mediaTime ?? video.currentTime;
    if (mediaTime === lastMediaTime) return;
    lastMediaTime = mediaTime;
    const frame = capture({
      sequence: ++sequence,
      mediaTime,
      observedAt: now,
      width: video.videoWidth,
      height: video.videoHeight,
    });
    if (frame !== undefined) queue.offer(frame);
  }

  requestId = useVideoCallback
    ? video.requestVideoFrameCallback(observeFrame)
    : requestAnimationFrame(observeFrame);

  return () => {
    if (stopped) return;
    stopped = true;
    queue.close();
    if (useVideoCallback) video.cancelVideoFrameCallback(requestId);
    else cancelAnimationFrame(requestId);
  };
}

type TrackProcessor = new (options: { track: MediaStreamTrack; maxBufferSize: number }) => {
  readable: ReadableStream<VideoFrame>;
};

export function startArTrackFrameLoop(
  track: MediaStreamTrack,
  processFrame: (frame: ArCapturedFrame) => Promise<void>,
  onError: (error: unknown) => void,
): (() => void) | undefined {
  const { MediaStreamTrackProcessor } = globalThis as typeof globalThis & {
    MediaStreamTrackProcessor?: TrackProcessor;
  };
  if (!MediaStreamTrackProcessor) return;

  const source = track.clone();
  let reader: ReadableStreamDefaultReader<VideoFrame>;
  try {
    reader = new MediaStreamTrackProcessor({ track: source, maxBufferSize: 1 }).readable.getReader();
  } catch (error) {
    source.stop();
    onError(error);
    return;
  }

  const queue = createLatestFrameQueue(processFrame, frame => frame.image.close());
  let closed = false;

  function close() {
    if (closed) return;
    closed = true;
    queue.close();
    source.stop();
    void reader.cancel().catch(() => {});
  }

  async function readFrames() {
    let sequence = 0;
    let previousTimestamp = -Infinity;
    try {
      while (!closed) {
        const { value: image, done } = await reader.read();
        if (done) break;
        if (closed || image.timestamp <= previousTimestamp) {
          image.close();
          continue;
        }
        previousTimestamp = image.timestamp;
        queue.offer({
          sequence: ++sequence,
          mediaTime: image.timestamp / 1_000_000,
          observedAt: performance.now(),
          width: image.displayWidth,
          height: image.displayHeight,
          image,
        });
      }
    } catch (error) {
      if (!closed) onError(error);
    } finally {
      close();
      reader.releaseLock();
    }
  }

  void readFrames();
  return close;
}
