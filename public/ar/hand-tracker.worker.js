let tracker;

self.onmessage = async ({ data }) => {
  if (data.kind === "start") {
    try {
      const assetRoot = new URL("/vendor/mediapipe/hand-landmarker/", self.location.origin);
      const { FilesetResolver, HandLandmarker } = await import(new URL("vision_bundle.mjs", assetRoot).href);
      const assets = await FilesetResolver.forVisionTasks(new URL("wasm", assetRoot).href);
      tracker = await HandLandmarker.createFromOptions(assets, {
        canvas: new OffscreenCanvas(1, 1),
        baseOptions: {
          delegate: "GPU",
          modelAssetPath: new URL("hand_landmarker-v1.task", assetRoot).href,
        },
        runningMode: "VIDEO",
        numHands: 1,
      });
      self.postMessage({ kind: "ready" });
    } catch (error) {
      self.postMessage({ kind: "error", message: String(error) });
    }
    return;
  }

  const { image, mediaTime, sequence } = data;
  try {
    const start = performance.now();
    const result = tracker.detectForVideo(image, mediaTime * 1000);
    self.postMessage({
      kind: "result",
      sequence,
      computeMs: performance.now() - start,
      landmarks: result.landmarks,
      handedness: result.handedness.map(hand => hand[0]?.categoryName ?? null),
    });
  } catch (error) {
    self.postMessage({ kind: "error", message: String(error) });
  } finally {
    image.close();
  }
};
