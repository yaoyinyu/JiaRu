"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { NailAnalysisForm } from "@/components/NailAnalysisForm";
import { NailAnalysisResult } from "@/components/NailAnalysisResult";
import { NailDetectModeSwitch } from "@/components/NailDetectModeSwitch";
import { UploadButton } from "@/components/UploadButton";
import {
  cloudDetectMessageFromReason,
  detectNailsWithArk,
  detectNailsWithCloudMatte,
} from "@/lib/nail-cloud-detect";
import { decideNailDetectRun, type NailDetectMode } from "@/lib/nail-detect-mode";
import { validateImageUpload } from "@/lib/image-upload-validation";
import { analyzeNailPersonalization } from "@/lib/nail-personalization";
import { useNailDetectMode } from "@/lib/use-nail-detect-mode";
import {
  disposeNailTextureRecognitionWorker,
  recognizeNailTexturesInWorker,
} from "@/lib/nail-texture-recognition";
import { remapNailTextureCandidatesToOriginal } from "@/lib/nail-texture-recognition/input-scaling";
import type { NailTextureCandidate } from "@/lib/nail-texture-recognition/types.ts";
import type { OriginalImagePixels, UserScenario } from "@/lib/nail-personalization/types.ts";

/**
 * 与 NailArtPicker 一致的识别输入上限，保证候选几何与既有链路可比。
 * 本页自持一份精简编排（本地：识别 → remap → 分析；云端 v1.2.216：识别（候选
 * 已是原图坐标，免 remap）→ 分析，与本地路径共用 capture/analyze 后处理），
 * 是 NailArtPicker 的只读副本：琥珀辅助定位提示的判定与文案由
 * `nail-personalization/present.ts` 统一提供，同步责任人＝本功能维护者。
 */
const MAX_DETECTION_DIM = 800;
const RECOGNITION_TIMEOUT_MS = 30_000;
const EXPECTED_CANDIDATES = 5;
/** 与 NailArtPicker / device-benchmark 一致：manifest 地址可被部署环境覆盖，缺省走运行时默认值。 */
const MANIFEST_URL = process.env.NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL?.trim() || undefined;

/** 空态提示：默认本地、不上传；云端仅在被显式选择时作为辅助通道启用。 */
const IDLE_STATUS =
  "上传一张五指清晰的手背照片；默认本地分析，照片不上传。";

/** 云端 0 候选提示：与「0 候选不产出任何推荐」口径一致，保留空态。 */
const CLOUD_ZERO_CANDIDATE_MESSAGE =
  "云端未识别到甲面，未产出推荐；可更换照片或改用本地重试。";

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
  const [status, setStatus] = useState(IDLE_STATUS);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [scenario, setScenario] = useState<UserScenario>(DEFAULT_SCENARIO);
  const abortRef = useRef<AbortController | null>(null);
  // 识别模式（v1.2.216）：本地 | 云端，会话级默认本地；云端需一次性隐私确认。
  // 本页识别只由上传事件触发，runAnalysis/runCloudDetect 直接闭包读取最新
  // detectMode（事件回调每次渲染重建，无过期闭包问题），不经 effect 依赖。
  const detectMode = useNailDetectMode();

  /**
   * 云端识别（v1.2.216）：按所选云端后端请求甲面候选。判决（可用性/同意）不通过
   * 或降级 / 错误 / 0 候选 / 中止时提示并保留空态（不产出推荐）；成功候选固定
   * 低置信 + needs_review，capture.backend 走 "fallback" 与本地辅助候选同口径
   * （琥珀辅助声明页面级常显）。云端候选已是原图像素坐标，无需 remap。
   */
  const runCloudDetect = useCallback(
    async (options: {
      bitmap: ImageBitmap;
      signal: AbortSignal;
    }): Promise<NailTextureCandidate[] | null> => {
      const decision = decideNailDetectRun({
        mode: detectMode.mode,
        backend: detectMode.backend,
        availability: detectMode.availability,
        consentGiven: detectMode.consentGiven,
      });
      if (decision.action !== "run") {
        setStage("idle");
        setError(decision.message);
        setStatus(decision.message);
        return null;
      }
      const detectInput = {
        image: options.bitmap,
        imageWidth: options.bitmap.width,
        imageHeight: options.bitmap.height,
        signal: options.signal,
      };
      const outcome =
        detectMode.backend === "ark"
          ? await detectNailsWithArk(detectInput)
          : await detectNailsWithCloudMatte(detectInput);
      if (options.signal.aborted) return null;
      if (outcome.status === "degraded") {
        const message = cloudDetectMessageFromReason(outcome.reason, outcome.message);
        setStage("idle");
        setError(message);
        setStatus(message);
        return null;
      }
      if (outcome.status === "error") {
        setStage("idle");
        setError(outcome.message);
        setStatus(outcome.message);
        return null;
      }
      if (outcome.candidates.length === 0) {
        setStage("idle");
        setStatus(CLOUD_ZERO_CANDIDATE_MESSAGE);
        return null;
      }
      return outcome.candidates;
    },
    [detectMode]
  );

  /** 切换识别模式；已有分析结果时提示云端模式对下一次上传生效。 */
  function handleDetectModeChange(next: NailDetectMode) {
    detectMode.setMode(next);
    if (next === "cloud" && capture) {
      setStatus("已切换云端识别，重新上传后生效。");
    }
  }

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

    const cloudMode = detectMode.mode === "cloud";
    setStage("analyzing");
      setStatus(cloudMode ? "正在上传并请求云端识别…" : "正在识别甲面…");
    const abort = new AbortController();
    abortRef.current = abort;

    let bitmap: ImageBitmap | null = null;
    try {
      bitmap = await createImageBitmap(file);

      let candidates: NailTextureCandidate[];
      let backend: Capture["backend"] = "fallback";
      if (cloudMode) {
        // 云端路径（v1.2.216）：候选已是原图像素坐标，不再 remap；
        // 判决 / 降级 / 错误 / 0 候选已在 runCloudDetect 内提示并保留空态。
        const cloudCandidates = await runCloudDetect({ bitmap, signal: abort.signal });
        if (!cloudCandidates) return;
        candidates = cloudCandidates;
      } else {
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

        candidates = remapNailTextureCandidatesToOriginal(
          recognition.candidates,
          {
            scaleX: detectionWidth / bitmap.width,
            scaleY: detectionHeight / bitmap.height,
          },
          bitmap.width,
          bitmap.height
        );
        backend = recognition.backend;
      }

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
        backend,
      });
      setPreviewUrl(URL.createObjectURL(file));
      setStage("ready");
      setStatus(
        cloudMode
          ? `云端识别返回 ${candidates.length} 个候选，已按辅助定位处理，结果仅供参考。`
          : backend === "fallback"
            ? "已按辅助定位完成分析，结果仅供参考。"
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
    setStatus(IDLE_STATUS);
  }

  return (
    <AppShell
      shiftUp
      eyebrow="Personalization Studio"
      title="根据你的手型与肤色，给出可解释的美甲建议"
      description="照片默认本地分析；仅显式切换云端识别时上传，且只用于本次定位。结果为启发式建议，非医疗结论。"
    >
      <div className="grid gap-5 md:grid-cols-[1.05fr_.95fr]">
        <section className="rounded-[28px] bg-[var(--surface)] p-3 shadow-[var(--neu-out-md)]  sm:p-5">
          <div className="pb-2">
            <NailDetectModeSwitch
              mode={detectMode.mode}
              onModeChange={handleDetectModeChange}
              backend={detectMode.backend}
              onBackendChange={detectMode.setBackend}
              availability={detectMode.availability}
              availabilityLoaded={detectMode.availabilityLoaded}
              consentGiven={detectMode.consentGiven}
              onConsentGranted={detectMode.acknowledgeCloudConsent}
              disabled={stage === "analyzing"}
            />
          </div>
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
          <p className="px-3 pb-2 pt-3 text-center text-xs text-[#67685f]">{status}</p>
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
            <p className="mt-1 text-xs text-[#67685f]">未填写的项按「未知」处理，不会被当作否定值。</p>
          </div>
          <NailAnalysisForm value={scenario} onChange={setScenario} disabled={stage === "analyzing"} />
        </section>
      </div>

      {analysis ? (
        <section className="mt-5 rounded-[28px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-5">
          <NailAnalysisResult result={analysis} />
        </section>
      ) : stage === "analyzing" ? (
        <p className="mt-5 text-center text-sm text-[#67685f]">正在分析中…</p>
      ) : null}
    </AppShell>
  );
}
