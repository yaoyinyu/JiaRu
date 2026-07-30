"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  extractTextureFromMaskDetailed,
  recognizeNailTexturesInWorker,
  type NailMask,
  type NailTextureCandidateConfidence,
  type NailTextureCandidateSource,
  type TextureExtractionDiagnostics,
} from "@/lib/nail-texture-recognition";
import {
  calculateDetectionInputGeometry,
  remapNailTextureCandidatesToOriginal,
} from "@/lib/nail-texture-recognition/input-scaling";
import { detectNailsFromHandImage } from "@/lib/nail-hand-geometry-detection";
import { detectPartialCloseupNailCandidates } from "@/lib/nail-partial-closeup-detection";
import {
  createLocalNailDebugSample,
  createNailDebugSampleFilename,
} from "@/lib/nail-texture-debug-sample";
import {
  presentRecognitionWarning,
  regionNeedsReview,
  summarizeExtractionDiagnostics,
  summarizeRegionQuality,
} from "@/components/nail-art-picker-quality";

export interface NailAssignment {
  texture: ImageBitmap;
  diagnostics?: TextureExtractionDiagnostics;
  finger: number;
}

interface NailRegion {
  id: string;
  cx: number;
  cy: number;
  angle: number;
  nl: number;
  nw: number;
  assignedFinger: number | null;
  confidence?: NailTextureCandidateConfidence;
  source?: NailTextureCandidateSource;
  mask?: NailMask;
  warnings?: string[];
  extractionDiagnostics?: TextureExtractionDiagnostics;
}

interface DetectionSummary {
  backend: "model" | "fallback";
  assistedByHandGeometry?: boolean;
  assistedByPartialCloseup?: boolean;
  modelVersion?: string;
  modelBackend?: "webgpu" | "wasm" | "fallback";
  elapsedMs: number;
  workerElapsedMs?: number;
  maxCandidates: number;
  workerTimeoutMs: number;
  warnings: string[];
}

interface NailArtPickerProps {
  imageUrl: string;
  onConfirm: (assignments: NailAssignment[]) => void;
  onCancel: () => void;
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
};
const MAX_CANVAS_DIM = 800;
const MAX_DETECTION_DIM = 800;
const NAIL_RECOGNITION_WORKER_TIMEOUT_MS = 15_000;
const NAIL_TEXTURE_MODEL_MANIFEST_URL =
  process.env.NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL?.trim() || undefined;
const MIN_NAIL_SIZE = 15;
const BORDER_COLOR = "#22c55e";
const SELECTED_COLOR = "#ec4899";
const HANDLE_BG = "#ffffff";

const PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES = new Set([
  "worker_unavailable_used_main_thread",
  "worker_timeout_used_main_thread",
  "model_runtime_unavailable_on_server",
  "no_supported_model_backend",
  "onnx_runtime_not_loaded",
  "onnx_session_init_failed",
  "onnx_session_or_tensor_unavailable",
  "model_outputs_empty_used_fallback",
  "model_unavailable_used_partial_closeup",
  "mediapipe_no_hand_detected",
  "mediapipe_no_nail_geometry",
  "mediapipe_hand_detection_failed",
]);

function isPartialCloseupInfrastructureWarning(warning: string): boolean {
  if (PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES.has(warning)) return true;
  return ["model_manifest_error", "model_inference_error", "onnx_session_init_failed"].some(
    (prefix) => warning.startsWith(prefix)
  );
}

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

async function computeImageDetectedNailRegions(
  image: HTMLImageElement,
  imageData: ImageData,
  originalWidth: number,
  originalHeight: number,
  signal?: AbortSignal
): Promise<{
  regions: NailRegion[];
  originalRegions: NailRegion[];
  summary: DetectionSummary;
}> {
  const result = await recognizeNailTexturesInWorker(imageData, {
    preferModel: true,
    manifestUrl: NAIL_TEXTURE_MODEL_MANIFEST_URL,
    maxCandidates: 10,
    workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
    signal,
  });

  const candidates = remapNailTextureCandidatesToOriginal(
    result.candidates,
    {
      scaleX: imageData.width / originalWidth,
      scaleY: imageData.height / originalHeight,
    },
    originalWidth,
    originalHeight
  );

  const modelOrRuleRegions = candidates.map((candidate) => ({
      id: candidate.id,
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      nl: candidate.length,
      nw: candidate.width,
      assignedFinger: candidate.suggestedFinger,
      confidence: candidate.confidence,
      source: candidate.source,
      mask: candidate.mask,
      warnings: [...(candidate.warnings ?? [])],
  }));
  const fallbackUsed = result.backend === "fallback";
  const detectionWarnings = [...result.warnings];
  let handGeometryRegions: NailRegion[] = [];
  let partialCloseupRegions: NailRegion[] = [];
  if (fallbackUsed) {
    try {
      const handDetection = await detectNailsFromHandImage(image, { signal });
      detectionWarnings.push(...handDetection.warnings);
      handGeometryRegions = handDetection.candidates.map((candidate) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        angle: candidate.angle,
        nl: candidate.length,
        nw: candidate.width,
        assignedFinger: candidate.suggestedFinger,
        confidence: candidate.confidence,
        source: candidate.source,
        warnings: [...(candidate.warnings ?? [])],
      }));
    } catch (reason) {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      if (error.name === "AbortError") throw error;
      detectionWarnings.push("mediapipe_hand_detection_failed");
    }
  }
  if (fallbackUsed && handGeometryRegions.length === 0) {
    const partialCandidates = remapNailTextureCandidatesToOriginal(
      detectPartialCloseupNailCandidates(imageData),
      {
        scaleX: imageData.width / originalWidth,
        scaleY: imageData.height / originalHeight,
      },
      originalWidth,
      originalHeight
    );
    partialCloseupRegions = partialCandidates.map((candidate) => ({
      id: candidate.id,
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      nl: candidate.length,
      nw: candidate.width,
      assignedFinger: candidate.suggestedFinger,
      confidence: candidate.confidence,
      source: candidate.source,
      warnings: [...(candidate.warnings ?? [])],
    }));
    if (partialCloseupRegions.length > 0) {
      const obsoleteWarnings = new Set([
        "mediapipe_no_hand_detected",
        "mediapipe_no_nail_geometry",
      ]);
      for (let index = detectionWarnings.length - 1; index >= 0; index -= 1) {
        if (obsoleteWarnings.has(detectionWarnings[index])) detectionWarnings.splice(index, 1);
      }
      detectionWarnings.push("model_unavailable_used_partial_closeup");
    } else {
      detectionWarnings.push("fallback_candidates_hidden_manual_selection_required");
    }
  }

  const assistedRegions =
    handGeometryRegions.length > 0 ? handGeometryRegions : partialCloseupRegions;
  const regions = fallbackUsed ? assistedRegions : modelOrRuleRegions;
  const originalRegions = fallbackUsed
    ? [...modelOrRuleRegions, ...assistedRegions]
    : modelOrRuleRegions;

  return {
    regions,
    originalRegions,
    summary: {
      backend: result.backend,
      assistedByHandGeometry: fallbackUsed && handGeometryRegions.length > 0,
      assistedByPartialCloseup: fallbackUsed && partialCloseupRegions.length > 0,
      modelVersion: result.modelVersion,
      modelBackend: result.modelInfo?.backend,
      elapsedMs: result.elapsedMs,
      workerElapsedMs: result.workerElapsedMs,
      maxCandidates: 10,
      workerTimeoutMs: NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
      warnings: detectionWarnings,
    },
  };
}

export default function NailArtPicker({ imageUrl, onConfirm, onCancel }: NailArtPickerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const detectionAbortRef = useRef<AbortController | null>(null);
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
      setError("参考图片加载失败，请重新选择图片。");
    };
    image.src = imageUrl;

    return () => {
      detectionAbortRef.current?.abort();
      detectionAbortRef.current = null;
    };
  }, [imageUrl]);

  useEffect(() => {
    if (!imgLoaded || !imgRef.current) return;

    let active = true;
    const controller = new AbortController();
    detectionAbortRef.current = controller;
    setDetecting(true);
    setDetectionSummary(null);
    setOriginalRegions([]);
    setRegions([]);
    setSelectedIdx(null);
    setAddingRegion(false);
    setError(null);

    const run = async () => {
      try {
        const image = imgRef.current;
        if (!image) return;
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
          setError(error.message || "自动识别失败，请在图片上手动添加甲面区域。");
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

  const closePicker = useCallback(() => {
    detectionAbortRef.current?.abort();
    detectionAbortRef.current = null;
    onCancel();
  }, [onCancel]);

  const cancelDetection = useCallback(() => {
    detectionAbortRef.current?.abort();
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

  const handleConfirm = useCallback(async () => {
    const image = imgRef.current;
    if (!image) return;
    const assigned = regions.filter((region) => region.assignedFinger !== null);
    if (assigned.length === 0) {
      setError("请先为至少一个甲面区域选择对应手指。");
      return;
    }

    setExtracting(true);
    setError(null);

    try {
      const results: NailAssignment[] = [];
      const diagnosticsById = new Map<string, TextureExtractionDiagnostics>();

      for (const region of assigned) {
        if (results.some((item) => item.finger === region.assignedFinger)) continue;

        if (region.mask) {
          const extracted = await extractTextureFromMaskDetailed(
            image,
            image.naturalWidth,
            image.naturalHeight,
            region.mask
          );
          diagnosticsById.set(region.id, extracted.diagnostics);
          results.push({
            texture: extracted.texture,
            finger: region.assignedFinger!,
            diagnostics: extracted.diagnostics,
          });
        } else {
          const texture = await cropTextureFromRegion(image, region);
          results.push({ texture, finger: region.assignedFinger! });
        }
      }

      if (diagnosticsById.size > 0) {
        setRegions((prev) =>
          prev.map((region) => {
            const diagnostics = diagnosticsById.get(region.id);
            return diagnostics ? { ...region, extractionDiagnostics: diagnostics } : region;
          })
        );
      }

      onConfirm(results);
    } catch (reason) {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      setError(error.message || "纹理提取失败，请调整甲面区域后重试。");
    } finally {
      setExtracting(false);
    }
  }, [onConfirm, regions]);

  const assignedCount = regions.filter((region) => region.assignedFinger !== null).length;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-7xl flex-col p-4 lg:flex-row lg:gap-4">
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-3xl bg-neutral-950 p-3">
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
            {!detecting && addingRegion && (
              <div className="pointer-events-none absolute inset-x-3 top-3 rounded-2xl bg-pink-600/90 px-4 py-3 text-center text-sm text-white shadow-lg">
                添加模式已开启：请在图片中逐个点击完整甲面
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 w-full shrink-0 overflow-auto rounded-3xl bg-white p-4 shadow-xl lg:mt-0 lg:w-[380px]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900">美甲纹理提取</h2>
              <p className="mt-1 text-sm text-slate-500">
                优先自动定位五个甲面；如少数边界有偏差，可直接拖动或微调。
              </p>
            </div>
            <button
              onClick={closePicker}
              className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              关闭
            </button>
          </div>

          <div className="mt-4 space-y-3 rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm">
            <div className="flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-white px-2 py-1">区域：{regions.length}</span>
              <span className="rounded-full bg-white px-2 py-1">已分配：{assignedCount}</span>
              {detectionSummary && (
                <span className="rounded-full bg-white px-2 py-1">
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
            {detectionSummary && (
              <div className="text-xs text-slate-600">
                <div>总耗时：{Math.round(detectionSummary.elapsedMs)} 毫秒</div>
                {detectionSummary.workerElapsedMs != null && (
                  <div>后台线程：{Math.round(detectionSummary.workerElapsedMs)} 毫秒</div>
                )}
                {detectionSummary.modelVersion && <div>模型：{detectionSummary.modelVersion}</div>}
              </div>
            )}
            {detectionWarningMessages.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-xs text-amber-700">
                {detectionWarningMessages.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
            {detectionSummary?.assistedByPartialCloseup ? (
              regions.length >= 4 ? (
                <div className="rounded-xl bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                  已自动定位 {regions.length} 个甲面，可直接提取；如边界有偏差可点击调整。
                </div>
              ) : (
                <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  已自动定位 {regions.length} 个甲面；如照片中还有未框选甲面，请点击图片补充。
                </div>
              )
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
            <button
              onClick={exportDebugSample}
              disabled={regions.length === 0}
              className="rounded-full border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              导出诊断 JSON
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
                            : "border-slate-200 bg-white hover:border-slate-300"
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
                    <>
                      <div className="pt-2 font-medium text-slate-900">最近一次提取诊断</div>
                      <div>{selectedExtractionSummary.title}</div>
                      <ul className="list-disc space-y-1 pl-5">
                        {selectedExtractionSummary.stats.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                        {selectedExtractionSummary.messages.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={closePicker}
              className="flex-1 rounded-2xl border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              onClick={() => void handleConfirm()}
              disabled={extracting || assignedCount === 0}
              className="flex-1 rounded-2xl bg-pink-500 px-4 py-3 text-sm font-medium text-white hover:bg-pink-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {extracting ? "正在提取…" : "提取所选纹理"}
            </button>
          </div>

          <div className="mt-3 text-xs text-slate-500">
            提示：点击并拖动图片中的区域可直接调整位置；也可使用右侧按钮微调大小和角度。
          </div>
        </div>
      </div>
    </div>
  );
}
