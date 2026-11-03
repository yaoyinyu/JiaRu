"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppDialog } from "@/components/ui/AppDialog";
import styles from "./NailArtPicker.module.css";
import {
  analyzeNailTextureProfile,
  detectNailsWithMatte,
  extractNormalizedNailTexture,
  fetchNailMatteAvailability,
  inferSuggestedFingers,
  refineCandidateMasksWithMatte,
  type NailTextureCandidate,
  type NailTextureCandidateConfidence,
  type NailTextureProfile,
  type TextureExtractionDiagnostics,
} from "@/lib/nail-texture-recognition";
import {
  MAX_DETECTION_DIM,
  NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
  computeImageDetectedNailRegions,
  isPartialCloseupInfrastructureWarning,
  type DetectionSummary,
  type NailDetectionRegion,
} from "@/lib/nail-detection-cascade";
import NailMattePanel, {
  NAIL_MATTE_NOTICE_STORAGE_KEY,
  type NailMatteAvailability,
  type NailMattePanelStatus,
} from "@/components/NailMattePanel";
import { NailDetectModeSwitch } from "@/components/NailDetectModeSwitch";
import { autoAssignNailRegionFingers } from "@/lib/nail-auto-flow";
import { decideNailDetectRun, type NailDetectMode } from "@/lib/nail-detect-mode";
import {
  cloudDetectMessageFromReason,
  detectNailsWithArk,
  detectNailsWithCloudMatte,
} from "@/lib/nail-cloud-detect";
import { useNailDetectMode } from "@/lib/use-nail-detect-mode";
import { calculateDetectionInputGeometry } from "@/lib/nail-texture-recognition/input-scaling";
import {
  createLocalNailDebugSample,
  createNailDebugSampleFilename,
} from "@/lib/nail-texture-debug-sample";
import {
  auxiliaryDetectionNotice,
  presentRecognitionWarning,
  regionNeedsReview,
  summarizeExtractionDiagnostics,
  summarizeRegionQuality,
} from "@/components/nail-art-picker-quality";

export interface NailAssignment {
  texture: ImageBitmap;
  diagnostics?: TextureExtractionDiagnostics;
  finger: number;
  profile?: NailTextureProfile;
  /** 来源区域置信度；auto 流程据此在界面上提示「建议复核」数量 */
  confidence?: NailTextureCandidateConfidence;
}

export interface NailPickerConfirmOptions {
  /** true 表示来自自动流程（识别→抠图→提取→分析→上屏一条龙） */
  auto?: boolean;
}

/** 选择器内的编辑态区域：识别级联的基础字段 + 本地提取诊断。 */
interface NailRegion extends NailDetectionRegion {
  extractionDiagnostics?: TextureExtractionDiagnostics;
}

interface NailArtPickerProps {
  imageUrl: string;
  onConfirm: (assignments: NailAssignment[], options?: NailPickerConfirmOptions) => void;
  onCancel: () => void;
  /**
   * 覆盖前复核的「继续调整」重开模式：只做自动识别与手动微调，
   * 不再自动执行「精细抠图→提取→分析→上屏」一条龙（§7.2，避免复核循环）。
   */
  suppressAutoFlow?: boolean;
}

const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];
const BACKEND_LABELS: Record<DetectionSummary["backend"], string> = {
  model: "模型识别",
  fallback: "安全降级",
};
const MODEL_BACKEND_LABELS: Record<NonNullable<DetectionSummary["modelBackend"]>, string> = {
  webgpu: "WebGPU",
  wasm: "WASM",
  fallback: "手动定位",
};
const CONFIDENCE_LABELS: Record<NonNullable<NailRegion["confidence"]>, string> = {
  high: "高置信",
  medium: "中置信",
  low: "需复核",
};
const SOURCE_LABELS: Record<NonNullable<NailRegion["source"]>, string> = {
  model: "模型候选",
  saliency: "规则候选",
  manual: "手动添加",
  mediapipe: "手部几何",
  "partial-closeup": "局部近景",
  "vlm-matte": "本机精细抠图",
  "cloud-ark": "云端视觉",
  "cloud-matte": "云端抠图",
};
const MAX_CANVAS_DIM = 800;
const MIN_NAIL_SIZE = 15;
const BORDER_COLOR = "#22c55e";
const SELECTED_COLOR = "#ac5145";
const HANDLE_BG = "#ffffff";

function nextId(): string {
  return `nail-${Math.random().toString(36).slice(2, 10)}`;
}

function fitScale(iw: number, ih: number) {
  if (iw <= 0 || ih <= 0) return 1;
  return Math.min(1, MAX_CANVAS_DIM / Math.max(iw, ih));
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function normalizeAngle(angle: number): number {
  let result = angle;
  while (result > Math.PI) result -= Math.PI * 2;
  while (result <= -Math.PI) result += Math.PI * 2;
  return result;
}

function isPointInsideRegion(x: number, y: number, region: NailRegion): boolean {
  const dx = x - region.cx;
  const dy = y - region.cy;
  const cos = Math.cos(-region.angle);
  const sin = Math.sin(-region.angle);
  const lx = dx * cos - dy * sin;
  const ly = dx * sin + dy * cos;
  const rx = region.nw / 2;
  const ry = region.nl / 2;
  if (rx <= 0 || ry <= 0) return false;
  return (lx * lx) / (rx * rx) + (ly * ly) / (ry * ry) <= 1;
}

function toCanvasPoint(event: React.PointerEvent<HTMLCanvasElement>, scale: number) {
  const rect = event.currentTarget.getBoundingClientRect();
  const x = (event.clientX - rect.left) / scale;
  const y = (event.clientY - rect.top) / scale;
  return { x, y };
}

function drawRegion(
  ctx: CanvasRenderingContext2D,
  region: NailRegion,
  selected: boolean,
  scale: number,
  label: string
) {
  ctx.save();
  ctx.translate(region.cx * scale, region.cy * scale);
  ctx.rotate(region.angle);
  ctx.beginPath();
  ctx.ellipse(0, 0, (region.nw * scale) / 2, (region.nl * scale) / 2, 0, 0, Math.PI * 2);
  ctx.strokeStyle = selected ? SELECTED_COLOR : BORDER_COLOR;
  ctx.lineWidth = selected ? 3 : 2;
  ctx.stroke();

  if (selected) {
    const handleY = -((region.nl * scale) / 2 + 16);
    ctx.beginPath();
    ctx.arc(0, handleY, 6, 0, Math.PI * 2);
    ctx.fillStyle = HANDLE_BG;
    ctx.fill();
    ctx.strokeStyle = SELECTED_COLOR;
    ctx.stroke();
  }
  ctx.restore();

  ctx.save();
  ctx.font = "12px sans-serif";
  ctx.textBaseline = "top";
  const text = label;
  const metrics = ctx.measureText(text);
  const boxW = metrics.width + 10;
  const boxH = 20;
  const x = region.cx * scale - boxW / 2;
  const y = region.cy * scale - (region.nl * scale) / 2 - 28;
  ctx.fillStyle = selected ? SELECTED_COLOR : "rgba(34, 197, 94, 0.95)";
  ctx.fillRect(x, y, boxW, boxH);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(text, x + 5, y + 4);
  ctx.restore();
}

async function cropTextureFromRegion(
  image: HTMLImageElement,
  region: NailRegion,
  maxTextureSize: number = 256
): Promise<ImageBitmap> {
  const cropW = Math.max(32, Math.round(region.nw * 1.35));
  const cropH = Math.max(32, Math.round(region.nl * 1.2));
  const outputScale = Math.min(1, maxTextureSize / Math.max(cropW, cropH));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(cropW * outputScale));
  canvas.height = Math.max(1, Math.round(cropH * outputScale));

  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas_2d_unavailable");

  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.scale(outputScale, outputScale);
  ctx.beginPath();
  ctx.ellipse(0, 0, region.nw / 2, region.nl / 2, 0, 0, Math.PI * 2);
  ctx.clip();
  ctx.rotate(-region.angle);
  ctx.drawImage(image, -region.cx, -region.cy);
  return createImageBitmap(canvas);
}

export default function NailArtPicker({
  imageUrl,
  onConfirm,
  onCancel,
  suppressAutoFlow = false,
}: NailArtPickerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const detectionAbortRef = useRef<AbortController | null>(null);
  const matteAbortRef = useRef<AbortController | null>(null);
  // §7.5：弹层关闭（含提取中 Escape / 取消）一律视为取消，提取结果不再应用。
  const closeCancelledRef = useRef(false);
  const dragRef = useRef<{
    pointerId: number;
    regionIndex: number;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  const [imgLoaded, setImgLoaded] = useState(false);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [viewScale, setViewScale] = useState(1);
  const [detecting, setDetecting] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detectionSummary, setDetectionSummary] = useState<DetectionSummary | null>(null);
  const [originalRegions, setOriginalRegions] = useState<NailRegion[]>([]);
  const [regions, setRegions] = useState<NailRegion[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [addingRegion, setAddingRegion] = useState(false);
  const [matteAvailability, setMatteAvailability] = useState<NailMatteAvailability | null>(null);
  const [matteStatus, setMatteStatus] = useState<NailMattePanelStatus>("idle");
  const [matteMessage, setMatteMessage] = useState<string | null>(null);
  const [matteMatchedCount, setMatteMatchedCount] = useState<number | null>(null);
  const [matteStartedAt, setMatteStartedAt] = useState<number | null>(null);
  const [matteElapsedMs, setMatteElapsedMs] = useState(0);
  const [autoStatus, setAutoStatus] = useState<string | null>(null);

  // 自动流程（识别完成后一条龙：精细抠图→指位→提取→分析→上屏）。
  const regionsRef = useRef<NailRegion[]>([]);
  useEffect(() => {
    regionsRef.current = regions;
  }, [regions]);
  const autoFlowForRef = useRef<string | null>(null);
  const autoFlowCancelledRef = useRef(false);
  const detectionCancelledRef = useRef(false);
  const matteAvailabilityRef = useRef<NailMatteAvailability | null>(null);
  const matteAvailabilityPromiseRef = useRef<Promise<NailMatteAvailability | null> | null>(
    null
  );

  // 识别模式（v1.2.216）：本地 | 云端，会话级默认本地；云端需一次性隐私确认。
  const detectMode = useNailDetectMode();
  // 识别 effect 不得依赖模式状态（否则切模式会重触发识别），经 ref 读取最新值。
  const detectModeRef = useRef(detectMode);
  useEffect(() => {
    detectModeRef.current = detectMode;
  }, [detectMode]);
  const cloudAbortRef = useRef<AbortController | null>(null);
  const runCloudDetectRef = useRef<((options: { signal?: AbortSignal }) => Promise<void>) | null>(
    null
  );

  const selectedRegion = selectedIdx !== null ? regions[selectedIdx] ?? null : null;
  const selectedQualitySummary = selectedRegion ? summarizeRegionQuality(selectedRegion) : null;
  const selectedExtractionSummary = summarizeExtractionDiagnostics(
    selectedRegion?.extractionDiagnostics
  );
  const detectionWarningMessages = useMemo(
    () => [
      ...new Set(
        (detectionSummary?.warnings ?? [])
          .filter(
            (warning) =>
              !detectionSummary?.assistedByPartialCloseup ||
              !isPartialCloseupInfrastructureWarning(warning)
          )
          .map(presentRecognitionWarning)
      ),
    ],
    [detectionSummary]
  );
  const hasRegionsNeedingReview = regions.some((region) => regionNeedsReview(region));
  const auxiliaryNotice = auxiliaryDetectionNotice(
    detectionSummary?.backend, detectionSummary?.warnings ?? [], regions.length
  );

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const image = imgRef.current;
    if (!canvas || !image || !imgLoaded) return;

    const scale = fitScale(image.naturalWidth, image.naturalHeight);
    const width = Math.max(1, Math.round(image.naturalWidth * scale));
    const height = Math.max(1, Math.round(image.naturalHeight * scale));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0, width, height);

    regions.forEach((region, index) => {
      const label = region.assignedFinger !== null ? FINGER_NAMES[region.assignedFinger] : `${index + 1}`;
      drawRegion(ctx, region, index === selectedIdx, scale, label);
    });
  }, [imgLoaded, regions, selectedIdx]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  useEffect(() => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      imgRef.current = image;
      setImgLoaded(true);
      setImageSize({ width: image.naturalWidth, height: image.naturalHeight });
      setViewScale(fitScale(image.naturalWidth, image.naturalHeight));
      setError(null);
    };
    image.onerror = () => {
      imgRef.current = null;
      setImgLoaded(false);
      setError("图片加载失败，请重新选择。");
    };
    image.src = imageUrl;

    return () => {
      detectionAbortRef.current?.abort();
      detectionAbortRef.current = null;
      // 换图 / 卸载时同步中止进行中的云端识别请求。
      cloudAbortRef.current?.abort();
      cloudAbortRef.current = null;
    };
  }, [imageUrl]);

  useEffect(() => {
    if (!imgLoaded || !imgRef.current) return;

    let active = true;
    const controller = new AbortController();
    detectionAbortRef.current = controller;
    detectionCancelledRef.current = false;
    setDetecting(true);
    setDetectionSummary(null);
    setOriginalRegions([]);
    setRegions([]);
    setSelectedIdx(null);
    setAddingRegion(false);
    setMatteStatus("idle");
    setMatteMessage(null);
    setMatteMatchedCount(null);
    setMatteStartedAt(null);
    setError(null);

    const run = async () => {
      try {
        const image = imgRef.current;
        if (!image) return;
        // 云端模式（v1.2.216）：跳过浏览器级联，直接云端识别；判决、提示与
        // 候选替换由 runCloudDetect 处理。模式经 ref 读取，不进 effect 依赖。
        if (detectModeRef.current.mode === "cloud") {
          await runCloudDetectRef.current?.({ signal: controller.signal });
          return;
        }
        const detectionStartedAt = performance.now();
        const geometry = calculateDetectionInputGeometry(
          image.naturalWidth,
          image.naturalHeight,
          MAX_DETECTION_DIM
        );
        const canvas = document.createElement("canvas");
        canvas.width = geometry.width;
        canvas.height = geometry.height;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("canvas_2d_unavailable");
        ctx.drawImage(image, 0, 0, geometry.width, geometry.height);
        const imageData = ctx.getImageData(0, 0, geometry.width, geometry.height);
        const detected = await computeImageDetectedNailRegions(
          image,
          imageData,
          image.naturalWidth,
          image.naturalHeight,
          controller.signal
        );
        detected.summary.elapsedMs = Math.max(
          detected.summary.elapsedMs,
          performance.now() - detectionStartedAt
        );
        if (!active || controller.signal.aborted) return;
        setOriginalRegions(detected.originalRegions);
        setRegions(detected.regions);
        setDetectionSummary(detected.summary);
        setSelectedIdx(detected.regions.length > 0 ? 0 : null);
        setAddingRegion(detected.regions.length === 0);
      } catch (reason) {
        const error = reason instanceof Error ? reason : new Error(String(reason));
        if (error.name === "AbortError") {
          if (active) {
            detectionCancelledRef.current = true;
            setDetectionSummary((current) =>
              current ?? {
                backend: "fallback",
                elapsedMs: 0,
                maxCandidates: 10,
                workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
                warnings: ["recognition_cancelled_by_user"],
              }
            );
          }
          return;
        }
        if (active) {
          setAddingRegion(true);
          setError(error.message || "自动识别失败，可手动添加甲面。");
        }
      } finally {
        if (active) setDetecting(false);
        if (detectionAbortRef.current === controller) {
          detectionAbortRef.current = null;
        }
      }
    };

    void run();

    return () => {
      active = false;
      controller.abort();
      if (detectionAbortRef.current === controller) {
        detectionAbortRef.current = null;
      }
    };
  }, [imgLoaded, imageUrl]);

  // ── 本机精细抠图（辅助路径，不参与自动识别流程）──
  useEffect(() => {
    const promise = fetchNailMatteAvailability()
      .then((availability) => availability as NailMatteAvailability | null)
      .catch(() => null);
    matteAvailabilityPromiseRef.current = promise;
    let active = true;
    void promise.then((availability) => {
      if (!active) return;
      matteAvailabilityRef.current = availability;
      setMatteAvailability(availability);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      matteAbortRef.current?.abort();
      matteAbortRef.current = null;
    };
  }, []);

  // 计时只在 interval 回调里推进，避免在 effect 内同步 setState。
  useEffect(() => {
    if (matteStartedAt == null) return;
    const timer = window.setInterval(() => {
      setMatteElapsedMs(Date.now() - matteStartedAt);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [matteStartedAt]);

  const toMatteCandidate = useCallback(
    (region: NailRegion): NailTextureCandidate => ({
      id: region.id,
      cx: region.cx,
      cy: region.cy,
      length: region.nl,
      width: region.nw,
      angle: region.angle,
      score: 1,
      confidence: region.confidence ?? "low",
      source: region.source ?? "manual",
      mask: region.mask,
      suggestedFinger: region.assignedFinger,
    }),
    []
  );

  /**
   * 对给定区域列表执行一次本机精细抠图（合同：只替换 mask，不增删候选、不改指位）。
   * 返回替换后的区域列表；降级/错误/中止返回 null（界面状态照常更新，本地结果保留）。
   */
  const refineMasks = useCallback(
    async (sourceRegions: NailRegion[]): Promise<NailRegion[] | null> => {
      const image = imgRef.current;
      if (!image || sourceRegions.length === 0) return null;
      matteAbortRef.current?.abort();
      const controller = new AbortController();
      matteAbortRef.current = controller;
      setMatteStatus("running");
      setMatteStartedAt(Date.now());
      setMatteElapsedMs(0);
      setMatteMessage(null);
      setMatteMatchedCount(null);
      try {
        const outcome = await refineCandidateMasksWithMatte({
          image,
          imageWidth: image.naturalWidth,
          imageHeight: image.naturalHeight,
          candidates: sourceRegions.map(toMatteCandidate),
          signal: controller.signal,
        });
        if (controller.signal.aborted) return null;
        if (outcome.status === "degraded") {
          setMatteStatus("degraded");
          setMatteMessage(outcome.message);
          return null;
        }
        if (outcome.status === "error") {
          setMatteStatus("error");
          setMatteMessage(outcome.message);
          return null;
        }
        const byId = new Map(
          outcome.masks.map((item) => [item.candidateId, item.mask])
        );
        const replace = (list: NailRegion[]) =>
          list.map((region) =>
            byId.has(region.id)
              ? { ...region, mask: byId.get(region.id), extractionDiagnostics: undefined }
              : region
          );
        setRegions(replace);
        setOriginalRegions(replace);
        setMatteStatus("done");
        setMatteMatchedCount(outcome.matchedCount);
        setMatteMessage(
          outcome.matchedCount > 0
            ? "已替换为更精细的软边蒙版。"
            : "未匹配到可替换的甲面，已保留本地结果。"
        );
        return replace(sourceRegions);
      } catch {
        if (controller.signal.aborted) return null;
        setMatteStatus("error");
        setMatteMessage("精细抠图失败，已保留本地结果。");
        return null;
      } finally {
        if (matteAbortRef.current === controller) matteAbortRef.current = null;
        setMatteStartedAt(null);
      }
    },
    [toMatteCandidate]
  );

  const runMatteRefine = useCallback(async () => {
    await refineMasks(regionsRef.current);
  }, [refineMasks]);

  /**
   * 兜底识别：本地 0 候选时由本机精细抠图直接找甲面（合同：结果固定 confidence:"low"）。
   * 返回识别出的区域列表；降级/错误/中止/0 实例返回 null（界面状态照常更新）。
   */
  const detectMasks = useCallback(async (): Promise<NailRegion[] | null> => {
    const image = imgRef.current;
    if (!image) return null;
    matteAbortRef.current?.abort();
    const controller = new AbortController();
    matteAbortRef.current = controller;
    setMatteStatus("running");
    setMatteStartedAt(Date.now());
    setMatteElapsedMs(0);
    setMatteMessage(null);
    setMatteMatchedCount(null);
    try {
      const outcome = await detectNailsWithMatte({
        image,
        imageWidth: image.naturalWidth,
        imageHeight: image.naturalHeight,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return null;
      if (outcome.status === "degraded") {
        setMatteStatus("degraded");
        setMatteMessage(outcome.message);
        return null;
      }
      if (outcome.status === "error") {
        setMatteStatus("error");
        setMatteMessage(outcome.message);
        return null;
      }
      if (outcome.candidates.length === 0) {
        setMatteStatus("done");
        setMatteMessage("未返回可用甲面，已保留当前结果。");
        return null;
      }
      const fingers = inferSuggestedFingers(outcome.candidates.length);
      const detected: NailRegion[] = outcome.candidates.map((candidate, index) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        angle: candidate.angle,
        nl: candidate.length,
        nw: candidate.width,
        assignedFinger: fingers[index] ?? null,
        confidence: "low",
        source: "vlm-matte",
        mask: candidate.mask,
        warnings: [...(candidate.warnings ?? [])],
      }));
      setRegions(detected);
      setOriginalRegions(detected);
      setSelectedIdx(0);
      setAddingRegion(false);
      setMatteStatus("done");
      setMatteMatchedCount(detected.length);
      setMatteMessage("已返回候选，请逐指核对后再提取。");
      return detected;
    } catch {
      if (controller.signal.aborted) return null;
      setMatteStatus("error");
      setMatteMessage("兜底识别失败，已保留当前结果。");
      return null;
    } finally {
      if (matteAbortRef.current === controller) matteAbortRef.current = null;
      setMatteStartedAt(null);
    }
  }, []);

  const runMatteDetect = useCallback(async () => {
    await detectMasks();
  }, [detectMasks]);

  const cancelMatte = useCallback(() => {
    matteAbortRef.current?.abort();
    matteAbortRef.current = null;
    setMatteStatus("idle");
    setMatteStartedAt(null);
    setMatteMessage(null);
  }, []);

  /**
   * 云端识别（v1.2.216）：按所选云端后端请求甲面候选，结果固定低置信。
   * 判决（可用性/同意）不通过时提示并保留当前结果；0 候选不做静默二次兜底。
   * 降级 / 错误 / 中止一律保留当前候选；有候选时整体替换候选集（与级联语义一致，
   * 本文件无快照机制）。低置信候选由 AR 覆盖前复核门（decideArReview）自然接管。
   */
  const runCloudDetect = useCallback(async (options: { signal?: AbortSignal } = {}) => {
    const image = imgRef.current;
    if (!image) return;
    const modeState = detectModeRef.current;
    const decision = decideNailDetectRun({
      mode: "cloud",
      backend: modeState.backend,
      availability: modeState.availability,
      consentGiven: modeState.consentGiven,
    });
    if (decision.action !== "run") {
      // unavailable 与 need-consent（正常经切换器把关不会出现）都提示后保留现状。
      setError(decision.message);
      return;
    }
    cloudAbortRef.current?.abort();
    const controller = new AbortController();
    const propagate = () => controller.abort();
    options.signal?.addEventListener("abort", propagate);
    cloudAbortRef.current = controller;
    setDetecting(true);
    setError(null);
    try {
      const outcome =
        modeState.backend === "ark"
          ? await detectNailsWithArk({
              image,
              imageWidth: image.naturalWidth,
              imageHeight: image.naturalHeight,
              signal: controller.signal,
            })
          : await detectNailsWithCloudMatte({
              image,
              imageWidth: image.naturalWidth,
              imageHeight: image.naturalHeight,
              signal: controller.signal,
            });
      if (controller.signal.aborted) return;
      if (outcome.status === "degraded") {
        setError(cloudDetectMessageFromReason(outcome.reason, outcome.message));
        return;
      }
      if (outcome.status === "error") {
        setError(outcome.message);
        return;
      }
      if (outcome.candidates.length === 0) {
        setError("云端未识别到甲面，已保留当前结果；可切换本地或手动添加。");
        return;
      }
      const fingers = inferSuggestedFingers(outcome.candidates.length);
      const detected: NailRegion[] = outcome.candidates.map((candidate, index) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        angle: candidate.angle,
        nl: candidate.length,
        nw: candidate.width,
        assignedFinger: fingers[index] ?? null,
        confidence: "low",
        source: candidate.source,
        mask: candidate.mask,
        warnings: [...(candidate.warnings ?? [])],
      }));
      // 换用云端结果后旧级联汇总不再代表当前候选，清空避免状态区误导。
      setDetectionSummary(null);
      setOriginalRegions(detected);
      setRegions(detected);
      setSelectedIdx(0);
      setAddingRegion(false);
    } catch {
      if (!controller.signal.aborted) setError("云端识别失败，已保留当前结果");
    } finally {
      options.signal?.removeEventListener("abort", propagate);
      if (cloudAbortRef.current === controller) cloudAbortRef.current = null;
      setDetecting(false);
    }
  }, []);
  // 上传自动识别 effect 经 ref 调用，避免把模式状态并入 effect 依赖（与编辑器同口径）。
  useEffect(() => {
    runCloudDetectRef.current = runCloudDetect;
  }, [runCloudDetect]);

  // 切换模式：云端时立即识别一次（含同意弹层完成后的 onModeChange 回调）。
  // 同意链在同一事件内同步触发，hook 状态尚未来得及经 effect 同步 ref，这里手动补同步，
  // 避免 runCloudDetect 判决读到过期 mode/consentGiven；云端就绪后废弃进行中的本机抠图。
  const handleDetectModeChange = useCallback(
    (mode: NailDetectMode) => {
      detectMode.setMode(mode);
      detectModeRef.current = { ...detectModeRef.current, mode };
      if (mode === "cloud") {
        matteAbortRef.current?.abort();
        matteAbortRef.current = null;
        void runCloudDetect();
      }
    },
    [detectMode, runCloudDetect]
  );

  const handleCloudConsentGranted = useCallback(() => {
    detectMode.acknowledgeCloudConsent();
    detectModeRef.current = { ...detectModeRef.current, consentGiven: true };
  }, [detectMode]);

  // AppDialog 面板宽度放宽标记（见 NailArtPicker.module.css 头注）。
  useEffect(() => {
    document.body.dataset.arPickerOpen = "true";
    return () => {
      delete document.body.dataset.arPickerOpen;
    };
  }, []);

  const closePicker = useCallback(() => {
    // 关闭即取消：自动流程与提取结果都不再应用（§7.5）。
    closeCancelledRef.current = true;
    autoFlowCancelledRef.current = true;
    detectionAbortRef.current?.abort();
    detectionAbortRef.current = null;
    onCancel();
  }, [onCancel]);

  const cancelDetection = useCallback(() => {
    detectionAbortRef.current?.abort();
    // 云端模式下「跳过自动识别」同时中止云端请求（与本地级联同语义）。
    cloudAbortRef.current?.abort();
    cloudAbortRef.current = null;
    detectionCancelledRef.current = true;
    setDetecting(false);
    setAddingRegion(true);
    setDetectionSummary((current) =>
      current ?? {
        backend: "fallback",
        elapsedMs: 0,
        maxCandidates: 10,
        workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
        warnings: ["recognition_cancelled_by_user"],
      }
    );
  }, []);

  const findRegionAtPoint = useCallback(
    (x: number, y: number) => {
      for (let index = regions.length - 1; index >= 0; index -= 1) {
        if (isPointInsideRegion(x, y, regions[index])) {
          return index;
        }
      }
      return -1;
    },
    [regions]
  );

  const createManualRegion = useCallback((x: number, y: number) => {
    const image = imgRef.current;
    if (!image) return;
    const maxDimension = Math.max(image.naturalWidth, image.naturalHeight);
    const nailLength = clamp(Math.round(maxDimension * 0.1), 42, 120);
    const nailWidth = clamp(Math.round(nailLength * 0.58), 28, 72);
    const assignedFingers = new Set(
      regions
        .map((region) => region.assignedFinger)
        .filter((finger): finger is number => finger !== null)
    );
    const nextFinger = FINGER_NAMES.findIndex((_, finger) => !assignedFingers.has(finger));
    const next: NailRegion = {
      id: nextId(),
      cx: clamp(x, nailWidth / 2, image.naturalWidth - nailWidth / 2),
      cy: clamp(y, nailLength / 2, image.naturalHeight - nailLength / 2),
      angle: 0,
      nl: nailLength,
      nw: nailWidth,
      assignedFinger: nextFinger >= 0 ? nextFinger : null,
      confidence: "low",
      source: "manual",
      warnings: [],
    };
    setRegions((prev) => [...prev, next]);
    setSelectedIdx(regions.length);
    setError(null);
  }, [regions]);

  const handleCanvasPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      if (!imgLoaded || detecting) return;
      const { x, y } = toCanvasPoint(event, viewScale);
      const regionIndex = findRegionAtPoint(x, y);

      if (regionIndex >= 0) {
        const region = regions[regionIndex];
        setSelectedIdx(regionIndex);
        dragRef.current = {
          pointerId: event.pointerId,
          regionIndex,
          offsetX: x - region.cx,
          offsetY: y - region.cy,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
        event.preventDefault();
        return;
      }

      if (addingRegion) {
        createManualRegion(x, y);
        event.preventDefault();
        return;
      }

      setSelectedIdx(null);
    },
    [addingRegion, createManualRegion, detecting, findRegionAtPoint, imgLoaded, regions, viewScale]
  );

  const handleCanvasPointerMove = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      const drag = dragRef.current;
      const image = imgRef.current;
      if (!drag || drag.pointerId !== event.pointerId || !image) return;
      const { x, y } = toCanvasPoint(event, viewScale);

      setRegions((prev) =>
        prev.map((region, index) => {
          if (index !== drag.regionIndex) return region;
          const angleCos = Math.abs(Math.cos(region.angle));
          const angleSin = Math.abs(Math.sin(region.angle));
          const radiusX = (region.nw * angleCos + region.nl * angleSin) / 2;
          const radiusY = (region.nw * angleSin + region.nl * angleCos) / 2;
          return {
            ...region,
            cx: clamp(x - drag.offsetX, radiusX, image.naturalWidth - radiusX),
            cy: clamp(y - drag.offsetY, radiusY, image.naturalHeight - radiusY),
            extractionDiagnostics: undefined,
          };
        })
      );
      event.preventDefault();
    },
    [viewScale]
  );

  const finishCanvasDrag = useCallback((event: React.PointerEvent<HTMLCanvasElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const updateSelectedRegion = useCallback(
    (updater: (region: NailRegion) => NailRegion) => {
      if (selectedIdx === null) return;
      setRegions((prev) =>
        prev.map((region, index) =>
          index === selectedIdx
            ? {
                ...updater(region),
                extractionDiagnostics: undefined,
              }
            : region
        )
      );
    },
    [selectedIdx]
  );

  const nudgeSelected = useCallback(
    (dx: number, dy: number) => {
      const image = imgRef.current;
      if (!image) return;
      updateSelectedRegion((region) => ({
        ...region,
        cx: clamp(region.cx + dx, 0, image.naturalWidth),
        cy: clamp(region.cy + dy, 0, image.naturalHeight),
      }));
    },
    [updateSelectedRegion]
  );

  const resizeSelected = useCallback(
    (deltaLength: number, deltaWidth: number) => {
      updateSelectedRegion((region) => ({
        ...region,
        nl: Math.max(MIN_NAIL_SIZE, region.nl + deltaLength),
        nw: Math.max(MIN_NAIL_SIZE, region.nw + deltaWidth),
      }));
    },
    [updateSelectedRegion]
  );

  const rotateSelected = useCallback(
    (deltaDeg: number) => {
      updateSelectedRegion((region) => ({
        ...region,
        angle: normalizeAngle(region.angle + (deltaDeg * Math.PI) / 180),
      }));
    },
    [updateSelectedRegion]
  );

  const removeSelected = useCallback(() => {
    if (selectedIdx === null) return;
    setRegions((prev) => prev.filter((_, index) => index !== selectedIdx));
    setSelectedIdx((current) => {
      if (current === null) return null;
      if (regions.length <= 1) return null;
      return Math.max(0, current - 1);
    });
  }, [regions.length, selectedIdx]);

  const assignFinger = useCallback(
    (finger: number) => {
      if (selectedIdx === null) return;
      setRegions((prev) =>
        prev.map((region, index) => {
          if (index === selectedIdx) {
            return { ...region, assignedFinger: finger };
          }
          if (region.assignedFinger === finger) {
            return { ...region, assignedFinger: null };
          }
          return region;
        })
      );
    },
    [selectedIdx]
  );

  const exportDebugSample = useCallback(() => {
    const image = imgRef.current;
    if (!image) return;
    const record = createLocalNailDebugSample({
      imageUrl,
      imageWidth: image.naturalWidth,
      imageHeight: image.naturalHeight,
      detectionSummary,
      originalRegions,
      correctedRegions: regions,
    });
    const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = createNailDebugSampleFilename(record);
    link.click();
    URL.revokeObjectURL(url);
  }, [detectionSummary, imageUrl, originalRegions, regions]);

  /**
   * 提取核心：对给定区域列表逐个提取纹理并分析参数（颜色/图案/光泽/甲型）。
   * auto 模式失败时不弹错误覆盖成功路径，返回 null 交由调用方处理。
   */
  const extractAssignments = useCallback(
    async (
      sourceRegions: NailRegion[],
      options: { auto?: boolean } = {}
    ): Promise<NailAssignment[] | null> => {
      const image = imgRef.current;
      if (!image) return null;
      const assigned = sourceRegions.filter((region) => region.assignedFinger !== null);
      if (assigned.length === 0) {
        if (!options.auto) setError("请先为甲面区域选择手指。");
        return null;
      }

      setExtracting(true);
      setError(null);

      try {
        const results: NailAssignment[] = [];
        const diagnosticsById = new Map<string, TextureExtractionDiagnostics>();

        for (const region of assigned) {
          // 弹层已关闭 / 自动流程已取消：停止继续提取，返回的部分结果由调用方释放。
          if (closeCancelledRef.current || autoFlowCancelledRef.current) break;
          if (results.some((item) => item.finger === region.assignedFinger)) continue;

          let texture: ImageBitmap;
          let diagnostics: TextureExtractionDiagnostics | undefined;
          if (region.mask) {
            // 归一化提取：掩膜主轴摆正 + referenceAngle（区域角）消歧甲尖方向，
            // 输出「正立、甲尖朝上、甲面充满位图」，与实时渲染约定一致。
            const extracted = await extractNormalizedNailTexture(
              image,
              image.naturalWidth,
              image.naturalHeight,
              region.mask,
              { referenceAngle: region.angle }
            );
            texture = extracted.texture;
            diagnostics = extracted.diagnostics;
            diagnosticsById.set(region.id, extracted.diagnostics);
          } else {
            texture = await cropTextureFromRegion(image, region);
          }

          // 参数分析失败不阻断提取主流程，profile 留空即按默认渲染。
          let profile: NailTextureProfile | undefined;
          try {
            profile = await analyzeNailTextureProfile(texture, {
              highlightRatioHint: diagnostics?.highlightRepair.highlightRatio ?? null,
            });
          } catch {
            profile = undefined;
          }

          results.push({
            texture,
            finger: region.assignedFinger!,
            diagnostics,
            profile,
            confidence: region.confidence,
          });
        }

        if (diagnosticsById.size > 0) {
          setRegions((prev) =>
            prev.map((region) => {
              const diagnostics = diagnosticsById.get(region.id);
              return diagnostics ? { ...region, extractionDiagnostics: diagnostics } : region;
            })
          );
        }

        return results;
      } catch (reason) {
        const error = reason instanceof Error ? reason : new Error(String(reason));
        if (options.auto) {
          setError("提取失败，可调整区域后重试。");
        } else {
          setError(error.message || "纹理提取失败，请调整区域后重试。");
        }
        return null;
      } finally {
        setExtracting(false);
      }
    },
    []
  );

  const handleConfirm = useCallback(async () => {
    const results = await extractAssignments(regionsRef.current);
    // 提取中关闭弹层视为取消：结果一律不再应用，已提取位图直接释放（§7.5）。
    if (closeCancelledRef.current) {
      for (const item of results ?? []) item.texture.close();
      return;
    }
    if (results && results.length > 0) {
      onConfirm(results);
    }
  }, [extractAssignments, onConfirm]);

  // ── 自动流程：识别完成后自动「精细抠图→指位→提取→分析→上屏」──
  const readMatteNoticeAccepted = useCallback(() => {
    try {
      return window.localStorage.getItem(NAIL_MATTE_NOTICE_STORAGE_KEY) === "1";
    } catch {
      return false;
    }
  }, []);

  const runAutoFlow = useCallback(async () => {
    autoFlowCancelledRef.current = false;
    let working = regionsRef.current;
    const availability =
      matteAvailabilityRef.current ??
      (await matteAvailabilityPromiseRef.current?.catch(() => null)) ??
      null;
    if (autoFlowCancelledRef.current) return;
    const matteAutoAllowed =
      readMatteNoticeAccepted() && availability?.ready === true && !availability.busy;

    // 0) 本地识别 0 候选（局部特写/多手图片）：已记住隐私确认且服务就绪时
    //    自动执行一次兜底识别；否则保持手动模式，不阻塞、不发送任何图片。
    //    云端模式（v1.2.216）不做本机兜底：0 候选保持手动模式，提示由云端识别给出。
    let fromDetect = false;
    if (working.length === 0) {
      if (detectModeRef.current.mode !== "local") return;
      if (!matteAutoAllowed) return;
      setAutoStatus("本地未识别到甲面，正在兜底识别…");
      const detected = await detectMasks();
      if (autoFlowCancelledRef.current) return;
      if (!detected || detected.length === 0) {
        setAutoStatus(null);
        return;
      }
      working = detected;
      fromDetect = true;
    }

    // 1) 已记住隐私确认且服务就绪时，自动执行一次本机精细抠图；
    //    兜底识别的结果本身已带精细 mask，不再重复消耗一次处理。
    //    云端模式跳过本机精细抠图：云端候选如需精化，切回本地后再执行。
    if (matteAutoAllowed && !fromDetect && detectModeRef.current.mode === "local") {
      setAutoStatus("正在精细处理甲面蒙版…");
      const refined = await refineMasks(working);
      if (autoFlowCancelledRef.current) return;
      if (refined) working = refined;
    }

    // 2) 自动指位分配：识别阶段已给的保持不变；缺失的按画面 x 序推断（可手动修正）。
    const assigned = autoAssignNailRegionFingers(working);
    if (assigned.guessedCount > 0) {
      working = assigned.regions;
      setRegions(assigned.regions);
      setOriginalRegions((prev) => autoAssignNailRegionFingers(prev).regions);
    }

    // 3) 提取 + 参数分析后交由页面裁决（§7.2 覆盖前复核：自动应用或进入复核态由页面决定）。
    setAutoStatus("正在提取纹理并分析参数…");
    const results = await extractAssignments(working, { auto: true });
    if (autoFlowCancelledRef.current || closeCancelledRef.current) {
      // 弹层已关闭：提取结果不再应用，已提取位图直接释放（§7.5）。
      for (const item of results ?? []) item.texture.close();
      return;
    }
    setAutoStatus(null);
    if (!results || results.length === 0) return;
    onConfirm(results, { auto: true });
  }, [detectMasks, extractAssignments, onConfirm, readMatteNoticeAccepted, refineMasks]);

  // 识别完成后触发一次（含 0 候选的兜底识别路径）；同一张图只跑一轮，用户取消识别则不跑。
  // suppressAutoFlow（覆盖前复核的「继续调整」重开）时只保留识别与手动提取。
  useEffect(() => {
    if (suppressAutoFlow) return;
    if (detecting || extracting) return;
    if (detectionCancelledRef.current) return;
    if (autoFlowForRef.current === imageUrl) return;
    autoFlowForRef.current = imageUrl;
    void runAutoFlow();
  }, [detecting, extracting, imageUrl, runAutoFlow, suppressAutoFlow]);

  const assignedCount = regions.filter((region) => region.assignedFinger !== null).length;

  return (
    <AppDialog
      open
      onClose={closePicker}
      title="美甲纹理提取"
      description="优先自动定位五个甲面；如少数边界有偏差，可直接拖动或微调。"
      // 误触背景遮罩会丢掉全部调整：只保留 Escape 与「取消」按钮关闭（§7.5）。
      closeOnOutside={false}
      footer={
        <>
          <button
            type="button"
            data-autofocus="cancel"
            onClick={closePicker}
            className="min-h-11 flex-1 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50 lg:flex-none"
          >
            取消
          </button>
          <button
            type="button"
            data-autofocus="confirm"
            onClick={() => void handleConfirm()}
            disabled={extracting || assignedCount === 0}
            className="min-h-11 flex-1 rounded-2xl bg-pink-500 px-4 py-3 text-sm font-medium text-white hover:bg-pink-600 disabled:cursor-not-allowed disabled:opacity-50 lg:flex-none"
          >
            {extracting ? "正在提取…" : "提取所选纹理"}
          </button>
        </>
      }
    >
      <div className={styles.workspace}>
        <div className={styles.canvasPane}>
          <div className="relative max-h-full max-w-full overflow-auto rounded-2xl bg-black">
            <canvas
              ref={canvasRef}
              onPointerDown={handleCanvasPointerDown}
              onPointerMove={handleCanvasPointerMove}
              onPointerUp={finishCanvasDrag}
              onPointerCancel={finishCanvasDrag}
              className={`block max-w-full rounded-2xl ${
                addingRegion ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"
              }`}
              style={{
                width: imageSize.width ? imageSize.width * viewScale : undefined,
                touchAction: "none",
              }}
              aria-label="美甲甲面区域编辑画布"
            />
            {detecting && (
              <div className="absolute inset-x-3 top-3 flex items-center justify-between rounded-2xl bg-black/70 px-4 py-3 text-sm text-white">
                <span>正在识别美甲甲面…</span>
                <button
                  onClick={cancelDetection}
                  className="rounded-full border border-white/30 px-3 py-1 text-xs hover:bg-white/10"
                >
                  跳过自动识别
                </button>
              </div>
            )}
            {!detecting && autoStatus && (
              <div className="absolute inset-x-3 top-3 rounded-2xl bg-black/70 px-4 py-3 text-sm text-white">
                <span role="status">{autoStatus}</span>
              </div>
            )}
            {!detecting && addingRegion && (
              <div className="pointer-events-none absolute inset-x-3 top-3 rounded-2xl bg-pink-600/90 px-4 py-3 text-center text-sm text-white shadow-lg">
                添加模式已开启：请在图片中逐个点击完整甲面
              </div>
            )}
          </div>
        </div>

        <div className={styles.sidePane}>
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm">
            <div className="flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-[var(--surface)] px-2 py-1">区域：{regions.length}</span>
              <span className="rounded-full bg-[var(--surface)] px-2 py-1">已分配：{assignedCount}</span>
              {detectionSummary && (
                <span className="rounded-full bg-[var(--surface)] px-2 py-1">
                  {detectionSummary.assistedByHandGeometry
                    ? "手部自动定位"
                    : detectionSummary.assistedByPartialCloseup
                      ? "局部近景自动定位"
                    : BACKEND_LABELS[detectionSummary.backend]}
                  {detectionSummary.modelBackend
                    ? ` / ${MODEL_BACKEND_LABELS[detectionSummary.modelBackend]}`
                    : ""}
                </span>
              )}
            </div>
            {(detectionSummary || regions.length > 0) && (
              <details className="text-xs text-slate-600">
                <summary className="cursor-pointer select-none font-medium text-slate-600">
                  技术详情
                </summary>
                <div className="mt-2 space-y-2">
                  {detectionSummary && (
                    <div>
                      <div>总耗时：{Math.round(detectionSummary.elapsedMs)} 毫秒</div>
                      {detectionSummary.workerElapsedMs != null && (
                        <div>后台线程：{Math.round(detectionSummary.workerElapsedMs)} 毫秒</div>
                      )}
                      {detectionSummary.modelVersion && <div>模型：{detectionSummary.modelVersion}</div>}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={exportDebugSample}
                    disabled={regions.length === 0}
                    className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    导出诊断 JSON
                  </button>
                </div>
              </details>
            )}
            {detectionWarningMessages.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-xs text-amber-700">
                {detectionWarningMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
            {auxiliaryNotice ? (
              <div role="status" className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {auxiliaryNotice}
              </div>
            ) : hasRegionsNeedingReview ? (
              <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                部分区域需要检查位置、角度或大小后再提取。
              </div>
            ) : null}
            {error && (
              <div className="rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</div>
            )}
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => setAddingRegion((current) => !current)}
              className={`rounded-full px-3 py-2 text-sm font-medium text-white ${
                addingRegion
                  ? "bg-amber-500 hover:bg-amber-600"
                  : "bg-emerald-500 hover:bg-emerald-600"
              }`}
            >
              {addingRegion ? "结束添加" : "在图片上添加甲面"}
            </button>
          </div>

          <div className="mt-5 space-y-4">
            <div>
              <div className="mb-2 text-sm font-medium text-slate-900">甲面区域</div>
              <div className="max-h-48 space-y-2 overflow-auto">
                {regions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
                    暂无可用区域。请在左侧图片中逐个点击完整甲面。
                  </div>
                ) : (
                  regions.map((region, index) => {
                    const active = selectedIdx === index;
                    const regionSummary = summarizeRegionQuality(region);
                    return (
                      <button
                        key={region.id}
                        onClick={() => setSelectedIdx(index)}
                        className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                          active
                            ? "border-pink-400 bg-pink-50"
                            : "border-slate-200 bg-[var(--surface)] hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-sm font-medium text-slate-900">
                            区域 {index + 1}
                            {region.assignedFinger !== null ? ` · ${FINGER_NAMES[region.assignedFinger]}` : ""}
                          </div>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] ${
                              regionSummary.severity === "review"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-emerald-100 text-emerald-700"
                            }`}
                          >
                            {region.source === "partial-closeup"
                              ? "已定位"
                              : region.confidence
                                ? CONFIDENCE_LABELS[region.confidence]
                                : "手动"}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          来源：{region.source ? SOURCE_LABELS[region.source] : "手动添加"}
                        </div>
                        {regionSummary.messages[0] && (
                          <div className="mt-2 text-xs text-slate-600">{regionSummary.messages[0]}</div>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* 识别模式（v1.2.216）：本地 | 云端；云端切换含一次性隐私确认，
                同意后立即以云端模式识别一次；识别/提取进行中禁止切换。 */}
            <NailDetectModeSwitch
              mode={detectMode.mode}
              onModeChange={handleDetectModeChange}
              backend={detectMode.backend}
              onBackendChange={detectMode.setBackend}
              availability={detectMode.availability}
              availabilityLoaded={detectMode.availabilityLoaded}
              consentGiven={detectMode.consentGiven}
              onConsentGranted={handleCloudConsentGranted}
              disabled={detecting || extracting}
            />

            {detectMode.mode === "cloud" && (
              <p className="text-xs text-slate-500">
                云端模式下本机精细抠图不可用；云端候选可切回本地后精细处理。
              </p>
            )}

            <NailMattePanel
              availability={matteAvailability}
              candidateCount={regions.length}
              status={matteStatus}
              message={matteMessage}
              matchedCount={matteMatchedCount}
              elapsedMs={matteStartedAt == null ? 0 : matteElapsedMs}
              disabled={detecting || extracting || detectMode.mode === "cloud"}
              onRefine={() => {
                void runMatteRefine();
              }}
              onDetect={() => {
                void runMatteDetect();
              }}
              onCancel={cancelMatte}
            />

            {selectedRegion && (
              <>
                <div>
                  <div className="mb-2 text-sm font-medium text-slate-900">调整所选区域</div>
                  <div className="grid grid-cols-3 gap-2 text-sm">
                    <button onClick={() => nudgeSelected(0, -8)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">上移</button>
                    <button onClick={() => rotateSelected(-8)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">逆时针</button>
                    <button onClick={() => resizeSelected(8, 0)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">加长</button>
                    <button onClick={() => nudgeSelected(-8, 0)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">左移</button>
                    <button onClick={() => nudgeSelected(0, 8)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">下移</button>
                    <button onClick={() => nudgeSelected(8, 0)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">右移</button>
                    <button onClick={() => rotateSelected(8)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">顺时针</button>
                    <button onClick={() => resizeSelected(-8, 0)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">缩短</button>
                    <button onClick={() => resizeSelected(0, 6)} className="rounded-xl border border-slate-200 px-3 py-2 hover:bg-slate-50">加宽</button>
                  </div>
                  <div className="mt-2 flex gap-2">
                    <button onClick={() => rotateSelected(180)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">旋转180°</button>
                    <button onClick={() => resizeSelected(0, -6)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">缩窄</button>
                    <button onClick={removeSelected} className="rounded-xl border border-rose-200 px-3 py-2 text-sm text-rose-600 hover:bg-rose-50">删除</button>
                  </div>
                </div>

                <div>
                  <div className="mb-2 text-sm font-medium text-slate-900">分配到手指</div>
                  <div className="grid grid-cols-2 gap-2">
                    {FINGER_NAMES.map((label, finger) => {
                      const taken = regions.some(
                        (region, index) => region.assignedFinger === finger && index !== selectedIdx
                      );
                      const active = selectedRegion.assignedFinger === finger;
                      return (
                        <button
                          key={label}
                          onClick={() => assignFinger(finger)}
                          className={`rounded-xl border px-3 py-2 text-sm transition ${
                            active
                              ? "border-pink-400 bg-pink-50 text-pink-700"
                              : taken
                                ? "border-slate-200 bg-slate-100 text-slate-400"
                                : "border-slate-200 hover:bg-slate-50"
                          }`}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
                  <div className="font-medium text-slate-900">质量检查</div>
                  <div>{selectedQualitySummary?.title}</div>
                  {selectedQualitySummary?.messages.length ? (
                    <ul className="list-disc space-y-1 pl-5">
                      {selectedQualitySummary.messages.map((message) => (
                        <li key={message}>{message}</li>
                      ))}
                    </ul>
                  ) : (
                    <div>当前区域未发现明显问题。</div>
                  )}
                  {selectedExtractionSummary && (
                    <details className="pt-2">
                      <summary className="cursor-pointer select-none font-medium text-slate-900">
                        最近一次提取诊断（技术详情）
                      </summary>
                      <div className="mt-1">{selectedExtractionSummary.title}</div>
                      <ul className="list-disc space-y-1 pl-5">
                        {selectedExtractionSummary.stats.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                        {selectedExtractionSummary.messages.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="mt-4 text-xs text-slate-500">
            {suppressAutoFlow
              ? "已回到手动调整：确认甲面位置与指位后点击「提取所选纹理」应用；取消则不改变当前试戴。"
              : detectMode.mode === "cloud"
                ? "提示：云端模式自动完成识别、提取与参数分析；候选固定低置信，应用前会提示复核。"
                : "提示：上传后自动完成识别、精细处理（首次需确认隐私提示）、提取与参数分析；应用前会按置信度提示复核。"}
          </div>
        </div>
      </div>
    </AppDialog>
  );
}
