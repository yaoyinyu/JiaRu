"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NailAnalysisForm } from "@/components/NailAnalysisForm";
import { NailAnalysisResult } from "@/components/NailAnalysisResult";
import { UploadButton } from "@/components/UploadButton";
import { validateImageUpload } from "@/lib/image-upload-validation";
import { analyzeNailPersonalization } from "@/lib/nail-personalization";
import {
  disposeNailTextureRecognitionWorker,
  recognizeNailTexturesInWorker,
} from "@/lib/nail-texture-recognition";
import { remapNailTextureCandidatesToOriginal } from "@/lib/nail-texture-recognition/input-scaling";
import type { NailTextureCandidate } from "@/lib/nail-texture-recognition/types.ts";
import type { OriginalImagePixels, UserScenario } from "@/lib/nail-personalization/types.ts";

/**
 * 与 NailArtPicker 一致的识别输入上限，保证候选几何与既有链路可比。
 * 本页自持一份精简编排（识别 → remap → 分析），是 NailArtPicker 的只读副本：
 * 琥珀辅助定位提示的判定与文案由 `nail-personalization/present.ts` 统一提供，
 * 同步责任人＝本功能维护者。
 */
const MAX_DETECTION_DIM = 800;
const RECOGNITION_TIMEOUT_MS = 30_000;
const EXPECTED_CANDIDATES = 5;
/** 与 NailArtPicker / device-benchmark 一致：manifest 地址可被部署环境覆盖，缺省走运行时默认值。 */
const MANIFEST_URL = process.env.NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL?.trim() || undefined;

type Stage = "idle" | "analyzing" | "ready";

interface Capture {
  image: OriginalImagePixels;
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
}

const DEFAULT_SCENARIO: UserScenario = { occasion: "daily" };

function readCanvas(width: number, height: number): CanvasRenderingContext2D {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("canvas_2d_unavailable");
  return context;
}

export default function NailAnalysisPage() {
  const [stage, setStage] = useState<Stage>("idle");
  const [status, setStatus] = useState("上传一张五指清晰的手背照片，本地完成分析，不会上传。");
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [scenario, setScenario] = useState<UserScenario>(DEFAULT_SCENARIO);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => {
    abortRef.current?.abort();
    disposeNailTextureRecognitionWorker();
  }, []);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const analysis = useMemo(
    () =>
      capture
        ? analyzeNailPersonalization({
            image: capture.image,
            candidates: capture.candidates,
            backend: capture.backend,
            scenario,
            maxCandidates: EXPECTED_CANDIDATES,
          })
        : null,
    [capture, scenario]
  );

  async function runAnalysis(file: File) {
    setError(null);
    const validation = await validateImageUpload(file);
    if (!validation.ok) {
      setStatus(validation.message);
      setError(validation.message);
      return;
    }

    setStage("analyzing");
    setStatus("正在解码并识别甲面……");
    const abort = new AbortController();
    abortRef.current = abort;

    let bitmap: ImageBitmap | null = null;
    try {
      bitmap = await createImageBitmap(file);
      const detectionScale = Math.min(1, MAX_DETECTION_DIM / Math.max(bitmap.width, bitmap.height));
      const detectionWidth = Math.max(1, Math.round(bitmap.width * detectionScale));
      const detectionHeight = Math.max(1, Math.round(bitmap.height * detectionScale));

      const detectionContext = readCanvas(detectionWidth, detectionHeight);
      detectionContext.drawImage(bitmap, 0, 0, detectionWidth, detectionHeight);
      const detectionPixels = detectionContext.getImageData(0, 0, detectionWidth, detectionHeight);

      const recognition = await recognizeNailTexturesInWorker(detectionPixels, {
        preferModel: true,
        manifestUrl: MANIFEST_URL,
        maxCandidates: 10,
        workerTimeoutMs: RECOGNITION_TIMEOUT_MS,
        signal: abort.signal,
      });

      const candidates = remapNailTextureCandidatesToOriginal(
        recognition.candidates,
        {
          scaleX: detectionWidth / bitmap.width,
          scaleY: detectionHeight / bitmap.height,
        },
        bitmap.width,
        bitmap.height
      );

      const originalContext = readCanvas(bitmap.width, bitmap.height);
      originalContext.drawImage(bitmap, 0, 0, bitmap.width, bitmap.height);
      const originalPixels = originalContext.getImageData(0, 0, bitmap.width, bitmap.height);

      setCapture({
        image: {
          width: originalPixels.width,
          height: originalPixels.height,
          data: originalPixels.data,
          pixelSource: "original",
        },
        candidates,
        backend: recognition.backend,
      });
      setPreviewUrl(URL.createObjectURL(file));
      setStage("ready");
      setStatus(
        recognition.backend === "fallback"
          ? "已完成辅助定位分析，结果仅供参考，请结合实物效果判断。"
          : "已完成分析，可调整下方问卷重新计算推荐。"
      );
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "分析失败，请重试。";
      setStage("idle");
      setStatus(message === "canvas_2d_unavailable" ? "当前浏览器不支持 2D 画布，无法分析。" : "识别失败，请重新选择照片。");
      setError(message);
    } finally {
      bitmap?.close();
    }
  }

  function reset() {
    abortRef.current?.abort();
    setCapture(null);
    setPreviewUrl(null);
    setStage("idle");
    setStatus("上传一张五指清晰的手背照片，本地完成分析，不会上传。");
  }

  return (
    <AppShell
      shiftUp
      eyebrow="Personalization Studio"
      title="根据你的手型与肤色，给出可解释的美甲建议"
      description="照片只在你的浏览器中处理。分析基于甲面候选与场景问卷，属于启发式建议，不构成医疗或诊断结论。"
    >
      <div className="grid gap-5 md:grid-cols-[1.05fr_.95fr]">
        <section className="rounded-[28px] bg-[var(--surface)] p-3 shadow-[var(--neu-out-md)]  sm:p-5">
          {!previewUrl ? (
            <UploadButton onUpload={runAnalysis} />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={previewUrl}
              alt="已上传的手部照片"
              className="w-full rounded-[24px] border border-[var(--line)] object-contain"
            />
          )}
          {error ? (
            <p role="alert" className="px-3 pb-2 pt-3 text-center text-sm text-red-600">{error}</p>
          ) : null}
          <p className="px-3 pb-2 pt-3 text-center text-xs text-[#75766c]">{status}</p>
          {previewUrl ? (
            <div className="flex justify-center pb-1">
              <button
                type="button"
                onClick={reset}
                className="rounded-full border border-pink-100 bg-[var(--surface)] px-4 py-2 text-xs font-medium text-[#ac5145] shadow-sm"
              >
                重新上传
              </button>
            </div>
          ) : null}
        </section>

        <section className="space-y-4 rounded-[28px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-5">
          <div>
            <h2 className="text-sm font-semibold text-[#292a27]">场景问卷</h2>
            <p className="mt-1 text-xs text-[#75766c]">未填写的项按「未知」处理，不会被当作否定值。</p>
          </div>
          <NailAnalysisForm value={scenario} onChange={setScenario} disabled={stage === "analyzing"} />
        </section>
      </div>

      {analysis ? (
        <section className="mt-5 rounded-[28px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-5">
          <NailAnalysisResult result={analysis} />
        </section>
      ) : stage === "analyzing" ? (
        <p className="mt-5 text-center text-sm text-[#75766c]">正在分析中……</p>
      ) : null}
    </AppShell>
  );
}
