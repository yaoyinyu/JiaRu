type ReleaseResource = () => void | Promise<void>;

export function createArCameraSession(video: HTMLVideoElement) {
  const lifetime = new AbortController();
  const { signal } = lifetime;
  const releases: ReleaseResource[] = [];

  function release(resource: ReleaseResource) {
    try {
      void Promise.resolve(resource()).catch(() => {});
    } catch {
      // 其余资源仍须释放。
    }
  }

  function own(resource: ReleaseResource) {
    if (signal.aborted) release(resource);
    else releases.push(resource);
  }

  function attachStream(stream: MediaStream) {
    own(() => {
      for (const track of stream.getTracks()) release(() => track.stop());
      if (video.srcObject === stream) video.srcObject = null;
    });
    if (signal.aborted) throw signal.reason;
    video.srcObject = stream;
  }

  function waitForVideo(
    event: "loadedmetadata" | "canplay",
    readyState: number,
    timeoutMs: number,
    allowTimeout = false,
  ): Promise<void> {
    if (signal.aborted) throw signal.reason;
    if (video.readyState >= readyState) return Promise.resolve();

    return new Promise((resolve, reject) => {
      function cleanup() {
        clearTimeout(timer);
        video.removeEventListener(event, onReady);
        video.removeEventListener("error", onError);
        signal.removeEventListener("abort", onAbort);
      }

      function onReady() {
        cleanup();
        resolve();
      }

      function onError() {
        cleanup();
        reject(new Error("视频加载失败"));
      }

      function onAbort() {
        cleanup();
        reject(signal.reason);
      }

      const timer = setTimeout(() => {
        cleanup();
        if (allowTimeout) resolve();
        else reject(new Error("视频加载超时"));
      }, timeoutMs);
      video.addEventListener(event, onReady, { once: true });
      video.addEventListener("error", onError, { once: true });
      signal.addEventListener("abort", onAbort, { once: true });
    });
  }

  function close() {
    if (signal.aborted) return;
    lifetime.abort();
    while (releases.length) release(releases.pop()!);
  }

  return { signal, own, attachStream, waitForVideo, close };
}
