import assert from "node:assert/strict";
import test from "node:test";
import { createArWorkerTracker } from "../src/lib/ar-hand-tracker.ts";

test("worker tracker transfers its selected snapshot and rejects a result for another frame", async () => {
  let transferred: Transferable[] | undefined;
  let terminated = false;
  let receive: ((event: { data: unknown }) => void) | undefined;
  class TestWorker {
    set onmessage(handler: (event: { data: unknown }) => void) {
      receive = handler;
    }
    postMessage(_message: object, transfer: Transferable[]) {
      transferred = transfer;
    }
    terminate() {
      terminated = true;
    }
  }

  const original = Object.getOwnPropertyDescriptor(globalThis, "Worker");
  Object.defineProperty(globalThis, "Worker", { configurable: true, value: TestWorker });
  const tracker = createArWorkerTracker();
  try {
    const setup = tracker.initialize();
    receive?.({ data: { kind: "ready" } });
    await setup;

    const image = {} as VideoFrame;
    const tracked = tracker.track({ sequence: 7, mediaTime: 2, observedAt: 10, width: 640, height: 480, image });
    assert.deepEqual(transferred, [image]);
    receive?.({ data: { kind: "result", sequence: 8, landmarks: [], handedness: [], computeMs: 10 } });

    await assert.rejects(tracked, /输入帧不匹配/);
    assert.equal(terminated, true);
    assert.equal(tracker.closed, true);
    await assert.rejects(tracker.track({ sequence: 9, mediaTime: 3, observedAt: 20, width: 640, height: 480, image }), /输入帧不匹配/);
  } finally {
    tracker.close();
    if (original) Object.defineProperty(globalThis, "Worker", original);
    else Reflect.deleteProperty(globalThis, "Worker");
  }
});
