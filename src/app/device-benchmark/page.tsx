"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { validateImageUpload } from "@/lib/image-upload-validation";
import {
  disposeNailTextureRecognitionWorker,
  recognizeNailTexturesInWorker,
} from "@/lib/nail-texture-recognition";
import {
  buildNailTextureDeviceSession,
  NAIL_TEXTURE_DEVICE_FAMILIES,
  type NailTextureDeviceBenchmarkSample,
  type NailTextureDeviceFamily,
} from "@/lib/nail-texture-device-benchmark";

const WARMUP_RUNS = 3;
const MEASURED_RUNS = 20;
const MAX_BENCHMARK_DIMENSION = 800;
const MANIFEST_URL = process.env.NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL?.trim() || undefined;

type MemoryPerformance = Performance & {
  memory?: { usedJSHeapSize?: number };
};

async function imageDataFromFile(file: File) {
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, MAX_BENCHMARK_DIMENSION / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("canvas_2d_unavailable");
    context.drawImage(bitmap, 0, 0, width, height);
    return {
      imageData: context.getImageData(0, 0, width, height),
      originalWidth: bitmap.width,
      originalHeight: bitmap.height,
    };
  } finally {
    bitmap.close();
  }
}

function downloadJson(payload: unknown, fileName: string) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

export default function DeviceBenchmarkPage() {
  const [deviceFamily, setDeviceFamily] = useState<NailTextureDeviceFamily>("android");
  const [file, setFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("请选择一张清晰的真实美甲图片。");
  const [session, setSession] = useState<ReturnType<typeof buildNailTextureDeviceSession> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => {
    abortRef.current?.abort();
    disposeNailTextureRecognitionWorker();
  }, []);

  const progress = useMemo(() => session?.samples.length ?? 0, [session]);

  async function runBenchmark() {
    if (!file || running) return;
    const validation = await validateImageUpload(file);
    if (!validation.ok) {
      setStatus(validation.message);
      return;
    }
    setRunning(true);
    setSession(null);
    const abort = new AbortController();
    abortRef.current = abort;
    try {
      setStatus("正在解码并准备基准输入……");
      const prepared = await imageDataFromFile(file);
      const sessionId = crypto.randomUUID();
      const samples: NailTextureDeviceBenchmarkSample[] = [];
      for (let index = 0; index < WARMUP_RUNS + MEASURED_RUNS; index += 1) {
        setStatus(index < WARMUP_RUNS
          ? `模型预热 ${index + 1}/${WARMUP_RUNS}`
          : `正式采样 ${index - WARMUP_RUNS + 1}/${MEASURED_RUNS}`);
        const result = await recognizeNailTexturesInWorker(prepared.imageData, {
          preferModel: true,
          manifestUrl: MANIFEST_URL,
          maxCandidates: 10,
          workerTimeoutMs: 30_000,
          signal: abort.signal,
        });
        if (index < WARMUP_RUNS) continue;
        const modelInfo = result.modelInfo;
        samples.push({
          iteration: samples.length + 1,
          recordedAt: new Date().toISOString(),
          sessionId,
          deviceFamily,
          elapsedMs: result.elapsedMs,
          workerElapsedMs: result.workerElapsedMs ?? null,
          backend: result.backend,
          backendName: modelInfo?.backend ?? "fallback",
          modelVersion: result.modelVersion ?? modelInfo?.version ?? "fallback-v0",
          inputSize: modelInfo?.inputSize ?? result.preprocess?.inputSize ?? 0,
          candidateCount: result.candidates.length,
          warnings: [...result.warnings],
          usedJSHeapBytes: Number.isFinite((performance as MemoryPerformance).memory?.usedJSHeapSize)
            ? Number((performance as MemoryPerformance).memory?.usedJSHeapSize)
            : null,
        });
      }
      const navigatorWithMemory = navigator as Navigator & { deviceMemory?: number };
      const document = buildNailTextureDeviceSession({
        sessionId,
        deviceFamily,
        warmupRuns: WARMUP_RUNS,
        samples,
        image: {
          name: file.name,
          type: file.type,
          sizeBytes: file.size,
          width: prepared.originalWidth,
          height: prepared.originalHeight,
          benchmarkWidth: prepared.imageData.width,
          benchmarkHeight: prepared.imageData.height,
        },
        environment: {
          userAgent: navigator.userAgent,
          platform: navigator.platform,
          hardwareConcurrency: navigator.hardwareConcurrency || null,
          deviceMemoryGiB: navigatorWithMemory.deviceMemory ?? null,
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          screenWidth: window.screen.width,
          screenHeight: window.screen.height,
          devicePixelRatio: window.devicePixelRatio,
        },
      });
      setSession(document);
      setStatus(document.eligibleForPerformanceVerification
        ? "20 次性能样本已完成，可导出。移动端整体内存仍需 Android Profiler 或 iOS Instruments。"
        : `采集完成但不能用于验收：${document.errors.join("；")}`);
    } catch (error) {
      setStatus(abort.signal.aborted ? "采集已取消。" : `采集失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      abortRef.current = null;
      setRunning(false);
    }
  }

  return (
    <AppShell
      eyebrow="Device Benchmark"
      title="移动真机识别基准"
      description="在目标手机或平板浏览器中预热模型并连续采集 20 次端到端推理。图片和采样结果只保留在当前浏览器，导出由你主动触发。"
    >
      <div className="mx-auto grid max-w-3xl gap-5">
        <section className="rounded-[28px] border border-white/80 bg-white/70 p-5 shadow-[0_22px_65px_rgba(91,59,74,.09)] backdrop-blur-2xl">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              设备类别
              <select
                value={deviceFamily}
                disabled={running}
                onChange={(event) => setDeviceFamily(event.target.value as NailTextureDeviceFamily)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2"
              >
                {NAIL_TEXTURE_DEVICE_FAMILIES.map((family) => <option key={family}>{family}</option>)}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              测试图片
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={running}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setSession(null);
                }}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              />
            </label>
          </div>
          <div className="mt-5 rounded-2xl bg-slate-50 p-4 text-sm text-slate-600">
            <p>{status}</p>
            <p className="mt-1 text-xs">固定流程：3 次预热 + 20 次正式采样；fallback、混合后端、混合模型或不足 20 次都会被拒绝。</p>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={!file || running}
              onClick={() => void runBenchmark()}
              className="rounded-full bg-[#CF6F99] px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? "采集中…" : "开始真机基准"}
            </button>
            {running && (
              <button type="button" onClick={() => abortRef.current?.abort()} className="rounded-full border border-slate-300 px-5 py-2 text-sm text-slate-700">
                取消
              </button>
            )}
            <button
              type="button"
              disabled={!session}
              onClick={() => session && downloadJson(session, `nail-texture-device-session-${session.sessionId}.json`)}
              className="rounded-full border border-slate-300 px-5 py-2 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              导出会话 JSON
            </button>
          </div>
          {session && (
            <dl className="mt-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div><dt className="text-slate-400">正式样本</dt><dd className="font-semibold text-slate-800">{progress}/20</dd></div>
              <div><dt className="text-slate-400">后端</dt><dd className="font-semibold text-slate-800">{session.backend ?? "混合"}</dd></div>
              <div><dt className="text-slate-400">模型</dt><dd className="truncate font-semibold text-slate-800">{session.modelVersion ?? "混合"}</dd></div>
              <div><dt className="text-slate-400">输入尺寸</dt><dd className="font-semibold text-slate-800">{session.inputSize ?? "混合"}</dd></div>
            </dl>
          )}
        </section>
        <aside className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          浏览器 JS 堆内存只作诊断，不能冒充整机或浏览器进程峰值。Android 需另附 Profiler/系统采样，iPhone/iPad 需另附 Instruments 采样，之后再由设备验收构建器绑定两份证据。
        </aside>
      </div>
    </AppShell>
  );
}
