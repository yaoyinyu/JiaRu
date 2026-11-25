import assert from "node:assert/strict";
import test from "node:test";
import { startArTrackFrameLoop, startArVideoFrameLoop, startCapturedArVideoFrameLoop, type ArCapturedFrame, type ArVideoFrame } from "../src/lib/ar-video-frame-loop.ts";

test("video scheduler serializes work, replaces pending frames and cancels safely", async () => {
  let callback: VideoFrameRequestCallback;
  let requested = 0;
  let cancelled: number | undefined;
  const video = {
    readyState: 2,
    videoWidth: 640,
    videoHeight: 480,
    requestVideoFrameCallback(cb: VideoFrameRequestCallback) {
      callback = cb;
      return ++requested;
    },
    cancelVideoFrameCallback(id: number) { cancelled = id; },
  } as HTMLVideoElement;
  const frames: ArVideoFrame[] = [];
  let finish: () => void;
  const stop = startArVideoFrameLoop(video, frame => {
    frames.push(frame);
    return new Promise<void>(resolve => { finish = resolve; });
  });
  const tick = (mediaTime: number) => callback(mediaTime * 1000, { mediaTime } as VideoFrameCallbackMetadata);
  tick(1);
  tick(1);
  tick(2);
  tick(3);
  assert.deepEqual(frames.map(frame => frame.sequence), [1]);
  finish!();
  await Promise.resolve();
  assert.deepEqual(frames.map(frame => [frame.sequence, frame.mediaTime]), [[1, 1], [3, 3]]);
  tick(4);
  stop();
  stop();
  finish!();
  await Promise.resolve();
  tick(5);
  assert.equal(frames.length, 2);
  assert.equal(cancelled, requested);
});

test("captured frames retain their own pixels and release replaced snapshots and the in-flight frame", async () => {
  let callback: VideoFrameRequestCallback;
  const video = {
    readyState: 2,
    videoWidth: 640,
    videoHeight: 480,
    currentTime: 0,
    requestVideoFrameCallback(cb: VideoFrameRequestCallback) {
      callback = cb;
      return 1;
    },
    cancelVideoFrameCallback() {},
  } as unknown as HTMLVideoElement;
  const snapshots: TestFrame[] = [];
  class TestFrame {
    displayWidth = 640;
    displayHeight = 480;
    closed = false;
    timestamp: number | undefined;

    constructor(_source: HTMLVideoElement, options: VideoFrameInit) {
      this.timestamp = options.timestamp;
      snapshots.push(this);
    }

    close() {
      this.closed = true;
    }
  }

  const original = Object.getOwnPropertyDescriptor(globalThis, "VideoFrame");
  Object.defineProperty(globalThis, "VideoFrame", { configurable: true, value: TestFrame });
  const processed: ArCapturedFrame[] = [];
  let finish: () => void;
  const stop = startCapturedArVideoFrameLoop(video, frame => {
    processed.push(frame);
    return new Promise(resolve => { finish = resolve; });
  }, error => { throw error; });
  try {
    const tick = (mediaTime: number) => callback(mediaTime * 1000, { mediaTime } as VideoFrameCallbackMetadata);
    tick(1);
    tick(2);
    tick(3);
    assert.deepEqual(snapshots.map(frame => frame.timestamp), [1e6, 2e6, 3e6]);
    assert.equal(snapshots[1].closed, true);
    assert.deepEqual(processed.map(frame => frame.sequence), [1]);
    finish!();
    await Promise.resolve();
    assert.equal(processed[1].image, snapshots[2]);
    tick(4);
    stop();
    assert.equal(snapshots[3].closed, true);
    finish!();
    await Promise.resolve();
    assert.ok(snapshots.every(frame => frame.closed));
    assert.deepEqual(processed.map(frame => frame.sequence), [1, 3]);
  } finally {
    stop();
    if (original) Object.defineProperty(globalThis, "VideoFrame", original);
    else Reflect.deleteProperty(globalThis, "VideoFrame");
  }
});

test("track frames keep source timestamps, release superseded frames and stop only the clone", async () => {
  let input: ReadableStreamDefaultController<VideoFrame>;
  let cancelled = false;
  const readable = new ReadableStream<VideoFrame>({
    start(controller) { input = controller; },
    cancel() { cancelled = true; },
  });
  let sourceStopped = false;
  const source = { stop() { sourceStopped = true; } };
  const original = { clone: () => source, stop: () => assert.fail("preview track stopped") };
  const old = Object.getOwnPropertyDescriptor(globalThis, "MediaStreamTrackProcessor");
  Object.defineProperty(globalThis, "MediaStreamTrackProcessor", {
    configurable: true,
    value: class {
      readable = readable;

      constructor(options: { track: MediaStreamTrack; maxBufferSize: number }) {
        assert.equal(options.track, source);
        assert.equal(options.maxBufferSize, 1);
      }
    },
  });

  const processed: ArCapturedFrame[] = [];
  let done: () => void;
  const stop = startArTrackFrameLoop(original as unknown as MediaStreamTrack, frame => {
    processed.push(frame);
    return new Promise(resolve => { done = resolve; });
  }, error => { throw error; });
  const released: number[] = [];
  function enqueue(timestamp: number) {
    input.enqueue({
      timestamp,
      displayWidth: 640,
      displayHeight: 480,
      close: () => released.push(timestamp),
    } as unknown as VideoFrame);
  }
  const drain = () => new Promise<void>(resolve => setImmediate(resolve));

  try {
    enqueue(1_000_000);
    await drain();
    enqueue(2_000_000);
    enqueue(2_000_000);
    enqueue(3_000_000);
    await drain();
    assert.deepEqual(processed.map(frame => frame.mediaTime), [1]);
    assert.deepEqual(released, [2_000_000, 2_000_000]);

    done!();
    await drain();
    assert.deepEqual(processed.map(frame => frame.mediaTime), [1, 3]);
    stop!();
    done!();
    await drain();
    assert.equal(sourceStopped, true);
    assert.equal(cancelled, true);
    assert.deepEqual(released, [2_000_000, 2_000_000, 1_000_000, 3_000_000]);
  } finally {
    stop?.();
    if (old) Object.defineProperty(globalThis, "MediaStreamTrackProcessor", old);
    else Reflect.deleteProperty(globalThis, "MediaStreamTrackProcessor");
  }
});
