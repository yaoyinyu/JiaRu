import { runStageACoarse } from "@/lib/nail-texture-recognition/stage-a-coarse";
import type {
  ArSegKeyframeRequest,
  ArSegKeyframeResponse,
} from "@/lib/nail-texture-recognition/stage-a-coarse";

async function imageBitmapToImageData(imageBitmap: ImageBitmap): Promise<ImageData> {
  const canvas = new OffscreenCanvas(imageBitmap.width, imageBitmap.height);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("worker_2d_context_unavailable");
  context.drawImage(imageBitmap, 0, 0);
  return context.getImageData(0, 0, imageBitmap.width, imageBitmap.height);
}

// M3 常驻粗分割 Worker：只跑 Stage A，关键帧 2–4fps，与主跟踪 Hands 实例隔离。
self.onmessage = async (event: MessageEvent<ArSegKeyframeRequest>) => {
  const request = event.data;
  try {
    let imageData: ImageData;
    try {
      imageData = await imageBitmapToImageData(request.imageBitmap);
    } finally {
      request.imageBitmap.close();
    }
    const result = await runStageACoarse({
      width: imageData.width,
      height: imageData.height,
      data: imageData.data,
    });
    const response: ArSegKeyframeResponse = {
      id: request.id,
      instances: result.instances,
      elapsedMs: result.elapsedMs,
      warnings: result.warnings,
    };
    self.postMessage(response);
  } catch (error) {
    const response: ArSegKeyframeResponse = {
      id: request.id,
      instances: [],
      elapsedMs: 0,
      warnings: [error instanceof Error ? `ar_seg_worker_error:${error.message}` : "ar_seg_worker_error"],
    };
    self.postMessage(response);
  }
};