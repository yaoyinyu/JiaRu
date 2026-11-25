import assert from "node:assert/strict";
import test from "node:test";
import { createArCameraSession } from "../src/lib/ar-camera-session.ts";

class TestVideo extends EventTarget {
  readyState = 0;
  srcObject: MediaStream | null = null;
}

function testStream(stop: () => void): MediaStream {
  return { getTracks: () => [{ stop }] } as MediaStream;
}

test("closing aborts readiness, then releases the loop, tracker and stream once", async () => {
  const video = new TestVideo();
  const session = createArCameraSession(video as unknown as HTMLVideoElement);
  const released: string[] = [];
  session.attachStream(testStream(() => released.push("stream")));
  session.own(() => {
    released.push("tracker");
    throw new Error("tracker failed to close");
  });
  session.own(() => { released.push("loop"); });
  const waiting = session.waitForVideo("loadedmetadata", 1, 10_000);

  session.close();
  session.close();

  await assert.rejects(waiting, { name: "AbortError" });
  assert.equal(video.srcObject, null);
  assert.deepEqual(released, ["loop", "tracker", "stream"]);
});

test("a camera granted after cancellation is stopped without replacing the active stream", () => {
  const video = new TestVideo();
  const previous = createArCameraSession(video as unknown as HTMLVideoElement);
  const current = createArCameraSession(video as unknown as HTMLVideoElement);
  const stream = testStream(() => {});
  let lateStops = 0;

  previous.close();
  current.attachStream(stream);
  assert.throws(() => previous.attachStream(testStream(() => { lateStops++; })), {
    name: "AbortError",
  });

  assert.equal(lateStops, 1);
  assert.equal(video.srcObject, stream);
  current.close();
});

test("readiness accepts existing metadata and rejects video errors during playback startup", async () => {
  const video = new TestVideo();
  const session = createArCameraSession(video as unknown as HTMLVideoElement);
  video.readyState = 1;
  await session.waitForVideo("loadedmetadata", 1, 10_000);

  const waiting = session.waitForVideo("canplay", 3, 10_000, true);
  video.dispatchEvent(new Event("error"));

  await assert.rejects(waiting, /视频加载失败/);
  session.close();
});

test("releasing an old stream leaves the currently attached stream intact", () => {
  const video = new TestVideo();
  const previous = createArCameraSession(video as unknown as HTMLVideoElement);
  const current = createArCameraSession(video as unknown as HTMLVideoElement);
  let oldStops = 0;
  const stream = testStream(() => {});
  previous.attachStream(testStream(() => { oldStops++; }));
  current.attachStream(stream);

  previous.close();

  assert.equal(oldStops, 1);
  assert.equal(video.srcObject, stream);
  current.close();
});
