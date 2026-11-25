import type { ArCapturedFrame } from "./ar-video-frame-loop";

export interface ArHandLandmark {
  x: number;
  y: number;
  z: number;
}

interface WorkerHandResult {
  kind: "result";
  sequence: number;
  landmarks: ArHandLandmark[][];
  handedness: (string | null)[];
  computeMs: number;
}

type WorkerReply = WorkerHandResult | { kind: "ready" } | { kind: "error"; message: string };

export function createArWorkerTracker() {
  const worker = new Worker("/ar/hand-tracker.worker.js");
  let closeReason: Error | undefined;
  let pending: {
    resolve(reply: WorkerReply): void;
    reject(error: Error): void;
  } | undefined;

  function exchange(message: object, timeoutMs: number, transfer: Transferable[] = []) {
    if (closeReason) return Promise.reject(closeReason);
    if (pending) return Promise.reject(new Error("跟踪器已有进行中的请求"));
    return new Promise<WorkerReply>((resolve, reject) => {
      function finish() {
        clearTimeout(timer);
        pending = undefined;
      }
      const timer = setTimeout(() => {
        close(new Error("跟踪器 Worker 响应超时"));
      }, timeoutMs);
      pending = {
        resolve(reply) { finish(); resolve(reply); },
        reject(error) { finish(); reject(error); },
      };
      try {
        worker.postMessage(message, transfer);
      } catch (error) {
        pending.reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  function close(reason = new Error("跟踪器已关闭")) {
    if (closeReason) return;
    closeReason = reason;
    pending?.reject(reason);
    worker.terminate();
  }

  worker.onmessage = ({ data }: MessageEvent<WorkerReply>) => {
    if (data.kind === "error") pending?.reject(new Error(data.message));
    else pending?.resolve(data);
  };
  worker.onerror = event => close(new Error(event.message || "跟踪器 Worker 运行失败"));
  worker.onmessageerror = () => close(new Error("跟踪器 Worker 响应无法读取"));

  async function initialize() {
    const reply = await exchange({ kind: "start" }, 15_000);
    if (reply.kind !== "ready") throw new Error("跟踪器 Worker 未就绪");
  }

  async function track(frame: ArCapturedFrame) {
    const { sequence, mediaTime, image } = frame;
    const reply = await exchange({ kind: "frame", sequence, mediaTime, image }, 2_000, [image]);
    if (reply.kind !== "result" || reply.sequence !== sequence) {
      const error = new Error("跟踪结果与输入帧不匹配");
      close(error);
      throw error;
    }
    if (reply.landmarks.some(hand => hand.length !== 21 || hand.some(point =>
      ![point.x, point.y, point.z].every(Number.isFinite),
    ))) throw new Error("跟踪结果包含无效关键点");
    return reply;
  }

  return { initialize, track, close, get closed() { return closeReason !== undefined; } };
}
