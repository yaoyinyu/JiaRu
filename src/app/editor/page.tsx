"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import NextImage from "next/image";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/Icon";
import { UploadButton } from "@/components/UploadButton";
import { NailCanvas } from "@/components/NailCanvas";
import NailMattePanel, {
  NAIL_MATTE_NOTICE_STORAGE_KEY,
  type NailMatteAvailability,
  type NailMattePanelStatus,
} from "@/components/NailMattePanel";
import { TextureSetPicker } from "@/components/TextureSetPicker";
import { GalleryInspirationCard } from "@/components/GalleryInspiration";
import { auxiliaryDetectionNotice, presentRecognitionWarning } from "@/components/nail-art-picker-quality";
import { FINGER_NAMES, GALLERY_IMAGES, PRESET_COLORS } from "@/lib/utils";
import { validateImageUpload } from "@/lib/image-upload-validation";
import { AUTO_FINGER_GUESS_WARNING, autoAssignNailRegionFingers } from "@/lib/nail-auto-flow";
import {
  detectNailsWithMatte,
  fetchNailMatteAvailability,
  refineCandidateMasksWithMatte,
} from "@/lib/nail-texture-recognition";
import { calculateDetectionInputGeometry } from "@/lib/nail-texture-recognition/input-scaling";
import {
  computeImageDetectedNailRegions,
  frameGeometryFromMask,
  MAX_DETECTION_DIM,
  NAIL_RECOGNITION_WORKER_TIMEOUT_MS,
  PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES,
  type DetectionSummary,
  type NailDetectionRegion,
} from "@/lib/nail-detection-cascade";
import {
  applyPlacementAdjust,
  buildPlacementFromFrame,
  DEFAULT_PLACEMENT_ADJUST,
  loadTextureAspect,
  type NailPlacement,
  type PlacementAdjust,
  type PlacementFrameInput,
} from "@/lib/canvas/placements";
import { closestTextureSet, NAIL_TEXTURE_SETS } from "@/lib/nail-texture-sets";
import {
  applyRefinedFrameMasks,
  buildManualFrame,
  firstUnoccupiedFinger,
  frameToMatteCandidate,
  parsePinnedTextureKey,
  pushPlacementHistory,
  replacePlacementForFrame,
  resolveActiveTexture,
  textureKeyFor,
  undoPlacementHistory,
} from "@/lib/editor-texture-state";

/** 手动加框的 id 前缀（与识别候选 id 区分）。 */
const MANUAL_FRAME_ID_PREFIX = "manual-";

const BACKEND_LABELS: Record<DetectionSummary["backend"], string> = {
  model: "模型识别",
  fallback: "辅助定位",
};

function readMatteNoticeAccepted(): boolean {
  try {
    return window.localStorage.getItem(NAIL_MATTE_NOTICE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export default function EditorPage() {
  // useSearchParams 在静态渲染的客户端组件中必须包 Suspense，
  // 否则生产构建直接失败（Next.js 16 文档 useSearchParams → Prerendering）。
  return (
    <Suspense fallback={null}>
      <EditorPageInner />
    </Suspense>
  );
}

function EditorPageInner() {
  const searchParams = useSearchParams();
  const galleryParam = searchParams.get("gallery");
  const presetParam = searchParams.get("preset");
  const look =
    GALLERY_IMAGES.find((item) => String(item.id) === galleryParam) ?? null;
  // ?preset=（来自 /nail-analysis）与 ?gallery= 同时传入时 gallery 优先，
  // preset 被忽略，避免改动现有图库链路。
  const presetFromAnalysis = galleryParam
    ? null
    : PRESET_COLORS.find((item) => item.name === presetParam) ?? null;
  return (
    <EditorPageBody look={look} presetFromAnalysis={presetFromAnalysis} />
  );
}

function EditorPageBody({
  look,
  presetFromAnalysis,
}: {
  look: (typeof GALLERY_IMAGES)[number] | null;
  presetFromAnalysis: { name: string; color: string } | null;
}) {
  // ?preset= → 最接近主色的纹理套装（不自动贴合；无匹配则忽略并提示）。
  // closestTextureSet 为纯函数，SSR 与客户端结果一致，可安全用于惰性初始值。
  const initialPresetSet = presetFromAnalysis
    ? closestTextureSet(presetFromAnalysis.color)
    : null;
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [imageReady, setImageReady] = useState(false);

  // 识别状态
  const [detecting, setDetecting] = useState(false);
  const [frames, setFrames] = useState<NailDetectionRegion[]>([]);
  // 诊断用原始候选（含被辅助路径替换前的结果）；当前界面不展示。
  const [, setOriginalRegions] = useState<NailDetectionRegion[]>([]);
  const [detectionSummary, setDetectionSummary] = useState<DetectionSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(
    presetFromAnalysis && !initialPresetSet
      ? `未找到与「${presetFromAnalysis.name}」相近的纹理套装，可在侧栏手动选择。`
      : null
  );

  // 贴合状态
  const [placements, setPlacements] = useState<NailPlacement[]>([]);
  const [history, setHistory] = useState<NailPlacement[][]>([]);
  const [selectedPlacementId, setSelectedPlacementId] = useState<string | null>(null);
  const [selectedFrameId, setSelectedFrameId] = useState<string | null>(null);
  const [adjust, setAdjust] = useState<PlacementAdjust>(DEFAULT_PLACEMENT_ADJUST);

  // 纹理选择状态（activeSetId 由 ?preset= 惰性初始化）
  const [activeSetId, setActiveSetId] = useState<string | null>(
    initialPresetSet?.id ?? null
  );
  const [pinnedTextureKey, setPinnedTextureKey] = useState<string | null>(null);
  const [expandedSetId, setExpandedSetId] = useState<string | null>(null);
  const [showFrames, setShowFrames] = useState(true);
  const [addingFrame, setAddingFrame] = useState(false);

  // 本机精细抠图（辅助路径）状态
  const [matteAvailability, setMatteAvailability] = useState<NailMatteAvailability | null>(null);
  const [matteStatus, setMatteStatus] = useState<NailMattePanelStatus>("idle");
  const [matteMessage, setMatteMessage] = useState<string | null>(null);
  const [matteMatchedCount, setMatteMatchedCount] = useState<number | null>(null);
  const [matteStartedAt, setMatteStartedAt] = useState<number | null>(null);
  const [matteElapsedMs, setMatteElapsedMs] = useState(0);

  const imageRef = useRef<HTMLImageElement | null>(null);
  const detectionAbortRef = useRef<AbortController | null>(null);
  const matteAbortRef = useRef<AbortController | null>(null);
  const placementsRef = useRef<NailPlacement[]>([]);
  const historyRef = useRef<NailPlacement[][]>([]);
  const matteAvailabilityRef = useRef<NailMatteAvailability | null>(null);
  const matteAvailabilityPromiseRef = useRef<Promise<NailMatteAvailability | null> | null>(null);
  const aspectRequestedRef = useRef(new Set<string>());
  const [textureAspects, setTextureAspects] = useState<Map<string, number>>(new Map());
  const lastHistoryKeyRef = useRef<string | null>(null);
  const lastHistoryAtRef = useRef(0);

  useEffect(() => {
    placementsRef.current = placements;
  }, [placements]);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  // 卸载时中止进行中的本机抠图请求。
  useEffect(
    () => () => {
      matteAbortRef.current?.abort();
      matteAbortRef.current = null;
    },
    []
  );

  // 对象 URL 生命周期：更换或卸载时释放。
  useEffect(() => () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  // 预取纹理长宽比（失败回退 1，loadTextureAspect 内部已兜底）。
  useEffect(() => {
    let active = true;
    for (const set of NAIL_TEXTURE_SETS) {
      for (const texture of set.textures) {
        if (aspectRequestedRef.current.has(texture.src)) continue;
        aspectRequestedRef.current.add(texture.src);
        void loadTextureAspect(texture.src).then((aspect) => {
          if (!active) return;
          setTextureAspects((prev) => new Map(prev).set(texture.src, aspect));
        });
      }
    }
    return () => {
      active = false;
    };
  }, []);

  const aspectOf = useCallback(
    (src: string) => textureAspects.get(src) ?? 1,
    [textureAspects]
  );

  // 更换照片 / 首次上传前重置编辑态（纹理选择保留）；仅由上传事件触发，
  // 不放在 effect 中（react-hooks/set-state-in-effect）。
  const resetEditState = useCallback(() => {
    setFrames([]);
    setOriginalRegions([]);
    setDetectionSummary(null);
    setPlacements([]);
    setHistory([]);
    setSelectedPlacementId(null);
    setSelectedFrameId(null);
    setAdjust(DEFAULT_PLACEMENT_ADJUST);
    setExpandedSetId(null);
    setAddingFrame(false);
    setNotice(null);
    setMatteStatus("idle");
    setMatteMessage(null);
    setMatteMatchedCount(null);
    setMatteStartedAt(null);
    setImageReady(false);
    imageRef.current = null;
    lastHistoryKeyRef.current = null;
  }, []);

  // 加载原图（识别与精细抠图都直接消费该元素）。
  useEffect(() => {
    if (!imageUrl) return;
    let active = true;
    const controller = new AbortController();
    detectionAbortRef.current = controller;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      if (!active) return;
      imageRef.current = image;
      setImageReady(true);
    };
    image.onerror = () => {
      if (!active) return;
      setUploadError("照片加载失败，请重新选择完整的 JPG、PNG 或 WebP 文件。");
      setImageUrl(null);
    };
    image.src = imageUrl;
    return () => {
      active = false;
      controller.abort();
      if (detectionAbortRef.current === controller) detectionAbortRef.current = null;
      // 更换照片 / 卸载时同时中止进行中的本机抠图请求。
      matteAbortRef.current?.abort();
      matteAbortRef.current = null;
      imageRef.current = null;
    };
  }, [imageUrl]);

  // 编辑态可用性预取（GET 不触发推理）。
  useEffect(() => {
    if (!imageUrl) return;
    let active = true;
    const promise = fetchNailMatteAvailability().catch(() => null);
    matteAvailabilityPromiseRef.current = promise;
    void promise.then((availability) => {
      if (!active) return;
      matteAvailabilityRef.current = availability;
      setMatteAvailability(availability);
    });
    return () => {
      active = false;
    };
  }, [imageUrl]);

  // 抠图耗时按秒推进（本组件不持有时钟的展示交给 NailMattePanel）。
  useEffect(() => {
    if (matteStartedAt == null) return;
    const timer = window.setInterval(() => {
      setMatteElapsedMs(Date.now() - matteStartedAt);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [matteStartedAt]);

  /**
   * 兜底识别：本机精细抠图直接找甲面（结果固定低置信，须逐指核对）。
   * 降级 / 错误 / 中止一律保留本地 frames。
   */
  const runMatteDetect = useCallback(async (options: { signal?: AbortSignal } = {}) => {
    const image = imageRef.current;
    if (!image) return;
    matteAbortRef.current?.abort();
    const controller = new AbortController();
    const propagate = () => controller.abort();
    options.signal?.addEventListener("abort", propagate);
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
      if (controller.signal.aborted) return;
      if (outcome.status === "degraded") {
        setMatteStatus("degraded");
        setMatteMessage(outcome.message);
        return;
      }
      if (outcome.status === "error") {
        setMatteStatus("error");
        setMatteMessage(outcome.message);
        return;
      }
      if (outcome.candidates.length === 0) {
        setMatteStatus("done");
        setMatteMessage("未返回可用甲面，已保留当前结果。");
        return;
      }
      let detected: NailDetectionRegion[] = outcome.candidates.map((candidate) => ({
        id: candidate.id,
        cx: candidate.cx,
        cy: candidate.cy,
        angle: candidate.angle,
        nl: candidate.length,
        nw: candidate.width,
        assignedFinger: candidate.suggestedFinger,
        confidence: "low" as const,
        source: candidate.source,
        mask: candidate.mask,
        warnings: [...(candidate.warnings ?? [])],
      }));
      detected = autoAssignNailRegionFingers(detected).regions;
      setFrames(detected);
      setAddingFrame(false);
      setMatteStatus("done");
      setMatteMatchedCount(detected.length);
      setMatteMessage("已返回低置信候选，请逐指核对甲面与指位后再贴合。");
    } catch {
      if (controller.signal.aborted) return;
      setMatteStatus("error");
      setMatteMessage("兜底识别失败，已保留当前结果。");
    } finally {
      options.signal?.removeEventListener("abort", propagate);
      if (matteAbortRef.current === controller) matteAbortRef.current = null;
      // 中止（跳过识别 / 更换照片）时不得停留在「处理中」。
      if (controller.signal.aborted) setMatteStatus("idle");
      setMatteStartedAt(null);
    }
  }, []);

  // 上传成功后自动识别（AbortController 管理；跳过 / 更换照片 / 卸载均中止）。
  useEffect(() => {
    if (!imageReady || !imageUrl) return;
    const image = imageRef.current;
    if (!image) return;
    let cancelled = false;
    const controller = new AbortController();
    detectionAbortRef.current = controller;
    setDetecting(true);
    setNotice(null);

    const run = async () => {
      try {
        const startedAt = performance.now();
        const geometry = calculateDetectionInputGeometry(
          image.naturalWidth,
          image.naturalHeight,
          MAX_DETECTION_DIM
        );
        const canvas = document.createElement("canvas");
        canvas.width = geometry.width;
        canvas.height = geometry.height;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("canvas_2d_unavailable");
        context.drawImage(image, 0, 0, geometry.width, geometry.height);
        const imageData = context.getImageData(0, 0, geometry.width, geometry.height);
        const detected = await computeImageDetectedNailRegions(
          image,
          imageData,
          image.naturalWidth,
          image.naturalHeight,
          controller.signal
        );
        if (cancelled || controller.signal.aborted) return;
        let regions = detected.regions;
        if (regions.length > 0) {
          regions = autoAssignNailRegionFingers(regions).regions;
        }
        setOriginalRegions(detected.originalRegions);
        setFrames(regions);
        setDetectionSummary({
          ...detected.summary,
          elapsedMs: Math.max(detected.summary.elapsedMs, performance.now() - startedAt),
        });
        if (regions.length === 0) {
          // 0 候选且已记住隐私确认、服务就绪 → 自动兜底一次；否则进入手动提示。
          const availability =
            matteAvailabilityRef.current ??
            (await matteAvailabilityPromiseRef.current?.catch(() => null)) ??
            null;
          if (cancelled || controller.signal.aborted) return;
          if (readMatteNoticeAccepted() && availability?.ready && !availability.busy) {
            await runMatteDetect({ signal: controller.signal });
          } else {
            setAddingFrame(true);
          }
        }
      } catch (reason) {
        const error = reason instanceof Error ? reason : new Error(String(reason));
        if (error.name === "AbortError") {
          if (!cancelled) {
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
        if (!cancelled) {
          setAddingFrame(true);
          setNotice(error.message || "辅助定位失败，可开启「添加甲面」手动逐个点击后贴合纹理。");
        }
      } finally {
        if (!cancelled) setDetecting(false);
        if (detectionAbortRef.current === controller) detectionAbortRef.current = null;
      }
    };

    void run();

    return () => {
      cancelled = true;
      controller.abort();
      if (detectionAbortRef.current === controller) detectionAbortRef.current = null;
    };
  }, [imageReady, imageUrl, runMatteDetect]);

  // ── 撤销栈：变更前 push（800ms 内同键合并，避免拖动/滑杆刷栈），undo 弹栈 ──
  const pushHistoryCoalesced = useCallback((key: string) => {
    const now = Date.now();
    if (lastHistoryKeyRef.current === key && now - lastHistoryAtRef.current < 800) {
      lastHistoryAtRef.current = now;
      return;
    }
    lastHistoryKeyRef.current = key;
    lastHistoryAtRef.current = now;
    setHistory((prev) => pushPlacementHistory(prev, placementsRef.current));
  }, []);

  const handleUndo = useCallback(() => {
    const result = undoPlacementHistory(historyRef.current);
    if (!result) return;
    lastHistoryKeyRef.current = null;
    setPlacements(result.placements);
    setHistory(result.history);
    if (
      selectedPlacementId &&
      !result.placements.some((item) => item.id === selectedPlacementId)
    ) {
      setSelectedPlacementId(null);
      setAdjust(DEFAULT_PLACEMENT_ADJUST);
    }
  }, [selectedPlacementId]);

  const handleReset = useCallback(() => {
    if (placementsRef.current.length === 0) return;
    pushHistoryCoalesced("reset");
    setPlacements([]);
    setSelectedPlacementId(null);
    setSelectedFrameId(null);
    setAdjust(DEFAULT_PLACEMENT_ADJUST);
  }, [pushHistoryCoalesced]);

  // ── 纹理选择 ──
  const handleApplySet = useCallback((setId: string) => {
    setActiveSetId(setId);
    setPinnedTextureKey(null);
    setNotice(null);
  }, []);

  const handlePinTexture = useCallback((setId: string, finger: number) => {
    setPinnedTextureKey(textureKeyFor(setId, finger));
    setNotice(null);
  }, []);

  const handleClearSelection = useCallback(() => {
    setActiveSetId(null);
    setPinnedTextureKey(null);
    setExpandedSetId(null);
  }, []);

  const handleApplyPreset = useCallback((preset: { name: string; color: string }) => {
    // 灵感色 → 最接近主色的套装；不自动贴合。
    setPinnedTextureKey(null);
    setActiveSetId(closestTextureSet(preset.color)?.id ?? null);
  }, []);

  const handleBannerPresetColor = useCallback(
    (preset: { name: string; color: string } | null) => {
      if (!preset) return;
      const set = closestTextureSet(preset.color);
      if (set) {
        setActiveSetId(set.id);
        setPinnedTextureKey(null);
      } else {
        setNotice(`未找到与「${preset.name}」相近的纹理套装，可在侧栏手动选择。`);
      }
    },
    []
  );

  // ── 贴合：点甲面框 / 手动加框 ──
  const handleFrameClick = useCallback(
    async (frame: PlacementFrameInput) => {
      if (detecting) return;
      setSelectedFrameId(frame.id);
      const resolution = resolveActiveTexture({
        sets: NAIL_TEXTURE_SETS,
        pinnedTextureKey,
        activeSetId,
        finger: frame.assignedFinger,
      });
      if (!resolution.texture) {
        setNotice(resolution.message);
        return;
      }
      setNotice(null);
      const aspect = await loadTextureAspect(resolution.texture.src);
      const placement = buildPlacementFromFrame(frame, {
        key: resolution.texture.key,
        src: resolution.texture.src,
        aspect,
      });
      pushHistoryCoalesced(`place:${frame.id}`);
      setPlacements((prev) => replacePlacementForFrame(prev, placement));
      setSelectedPlacementId(placement.id);
      setAdjust(placement.adjust);
    },
    [detecting, activeSetId, pinnedTextureKey, pushHistoryCoalesced]
  );

  const handleEmptyClick = useCallback(
    (x: number, y: number) => {
      if (!addingFrame) return;
      const image = imageRef.current;
      if (!image) return;
      const frame = buildManualFrame({
        id: `${MANUAL_FRAME_ID_PREFIX}${Date.now()}`,
        x,
        y,
        imageWidth: image.naturalWidth,
        imageHeight: image.naturalHeight,
        occupiedFingers: frames.map((item) => item.assignedFinger),
      });
      setFrames((prev) => [...prev, { ...frame }]);
      setSelectedFrameId(frame.id);
      void handleFrameClick(frame);
    },
    [addingFrame, frames, handleFrameClick]
  );

  const handlePlacementSelect = useCallback((id: string | null) => {
    setSelectedPlacementId(id);
    if (!id) return;
    const placement = placementsRef.current.find((item) => item.id === id);
    if (!placement) return;
    setAdjust(placement.adjust);
    if (placement.frameId) setSelectedFrameId(placement.frameId);
  }, []);

  // 拖动结束提交（拖动中 NailCanvas 仅本地预览）。
  const handlePlacementMove = useCallback(
    (id: string, cx: number, cy: number) => {
      pushHistoryCoalesced(`move:${id}`);
      setPlacements((prev) =>
        prev.map((item) => (item.id === id ? { ...item, cx, cy } : item))
      );
    },
    [pushHistoryCoalesced]
  );

  const handleAdjustChange = useCallback(
    (partial: Partial<PlacementAdjust>) => {
      if (!selectedPlacementId) return;
      const current = placementsRef.current.find((item) => item.id === selectedPlacementId);
      if (!current) return;
      const next: PlacementAdjust = { ...current.adjust, ...partial };
      pushHistoryCoalesced(`adjust:${selectedPlacementId}`);
      const updated = applyPlacementAdjust(current, next);
      setPlacements((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      setAdjust(next);
    },
    [pushHistoryCoalesced, selectedPlacementId]
  );

  const handleDeletePlacement = useCallback(() => {
    if (!selectedPlacementId) return;
    pushHistoryCoalesced(`remove:${selectedPlacementId}`);
    const frameId =
      placementsRef.current.find((item) => item.id === selectedPlacementId)?.frameId ?? null;
    setPlacements((prev) => prev.filter((item) => item.id !== selectedPlacementId));
    setSelectedPlacementId(null);
    setAdjust(DEFAULT_PLACEMENT_ADJUST);
    if (frameId === null) setSelectedFrameId(null);
  }, [pushHistoryCoalesced, selectedPlacementId]);

  const handleAssignFrameFinger = useCallback(
    (finger: number) => {
      if (!selectedFrameId) return;
      setFrames((prev) =>
        prev.map((item) => {
          if (item.id === selectedFrameId) {
            return {
              ...item,
              assignedFinger: finger,
              warnings: (item.warnings ?? []).filter(
                (warning) => warning !== AUTO_FINGER_GUESS_WARNING
              ),
            };
          }
          if (item.assignedFinger === finger) {
            return { ...item, assignedFinger: null };
          }
          return item;
        })
      );
    },
    [selectedFrameId]
  );

  const skipDetection = useCallback(() => {
    detectionAbortRef.current?.abort();
    detectionAbortRef.current = null;
    setDetecting(false);
    setAddingFrame(true);
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

  const cancelMatte = useCallback(() => {
    matteAbortRef.current?.abort();
    matteAbortRef.current = null;
    setMatteStatus("idle");
    setMatteStartedAt(null);
    setMatteMessage(null);
  }, []);

  // 精细抠图：只替换 mask 并按 mask 重算帧几何，不增删候选、不改指位。
  const runMatteRefine = useCallback(async () => {
    const image = imageRef.current;
    if (!image || frames.length === 0) return;
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
        candidates: frames.map(frameToMatteCandidate),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (outcome.status === "degraded") {
        setMatteStatus("degraded");
        setMatteMessage(outcome.message);
        return;
      }
      if (outcome.status === "error") {
        setMatteStatus("error");
        setMatteMessage(outcome.message);
        return;
      }
      const masksById = new Map(
        outcome.masks.map((item) => [item.candidateId, item.mask])
      );
      setFrames((prev) =>
        applyRefinedFrameMasks(prev, masksById, (frame) => {
          const mask = masksById.get(frame.id);
          return mask
            ? frameGeometryFromMask(mask, image.naturalWidth, image.naturalHeight)
            : null;
        })
      );
      setMatteStatus("done");
      setMatteMatchedCount(outcome.matchedCount);
      setMatteMessage(
        outcome.matchedCount > 0
          ? "已替换为更精细的软边蒙版。"
          : "未匹配到可替换的甲面，已保留本地结果。"
      );
    } catch {
      if (controller.signal.aborted) return;
      setMatteStatus("error");
      setMatteMessage("精细抠图失败，已保留本地结果。");
    } finally {
      if (matteAbortRef.current === controller) matteAbortRef.current = null;
      if (controller.signal.aborted) setMatteStatus("idle");
      setMatteStartedAt(null);
    }
  }, [frames]);

  // ── 派生展示状态 ──
  const selectedPlacement = useMemo(
    () => placements.find((item) => item.id === selectedPlacementId) ?? null,
    [placements, selectedPlacementId]
  );
  const selectedFrame = useMemo(
    () => frames.find((item) => item.id === selectedFrameId) ?? null,
    [frames, selectedFrameId]
  );
  // 滑杆值：以所选贴合记录的微调为准；未选中时回落到页面级 adjust 状态。
  const activeAdjust = selectedPlacement?.adjust ?? adjust;

  // 画布线索纹理：钉选优先；套装模式取首个空闲指位的纹理（仅作视觉提示）。
  const canvasActiveTexture = useMemo(() => {
    const resolution = resolveActiveTexture({
      sets: NAIL_TEXTURE_SETS,
      pinnedTextureKey,
      activeSetId,
      finger: firstUnoccupiedFinger(frames.map((item) => item.assignedFinger)),
    });
    if (!resolution.texture) return null;
    return {
      key: resolution.texture.key,
      src: resolution.texture.src,
      aspect: aspectOf(resolution.texture.src),
    };
  }, [pinnedTextureKey, activeSetId, frames, aspectOf]);

  const auxiliaryNotice = auxiliaryDetectionNotice(
    detectionSummary?.backend,
    detectionSummary?.warnings ?? [],
    frames.length
  );
  const detectionWarningMessages = useMemo(() => {
    const warnings = detectionSummary?.warnings ?? [];
    if (detectionSummary?.assistedByPartialCloseup) {
      return [
        ...new Set(
          warnings
            .filter((warning) => !PARTIAL_CLOSEUP_HIDDEN_WARNING_CODES.has(warning))
            .map(presentRecognitionWarning)
        ),
      ];
    }
    return [...new Set(warnings.map(presentRecognitionWarning))];
  }, [detectionSummary]);
  const hasLowConfidenceFrames = frames.some((item) => item.confidence === "low");

  const pinned = parsePinnedTextureKey(pinnedTextureKey);
  const pinnedSet = pinned
    ? NAIL_TEXTURE_SETS.find((set) => set.id === pinned.setId) ?? null
    : null;
  const pinnedTexture =
    pinnedSet && pinned
      ? pinnedSet.textures.find((item) => item.finger === pinned.finger) ?? null
      : null;
  const activeSet = activeSetId
    ? NAIL_TEXTURE_SETS.find((set) => set.id === activeSetId) ?? null
    : null;
  const currentSelectionLabel = pinnedSet && pinned
    ? `钉选纹理 · ${pinnedSet.name} ${FINGER_NAMES[pinned.finger]}`
    : activeSet
      ? `套装 · ${activeSet.name}`
      : "未选择";

  const handleUpload = async (file: File) => {
    setUploadError(null);
    const validation = await validateImageUpload(file);
    if (!validation.ok) {
      setUploadError(validation.message);
      return;
    }
    resetEditState();
    setImageUrl(URL.createObjectURL(file));
  };

  return (
    <>
      <AppShell
        shiftUp
        eyebrow={look ? "Inspiration Studio" : "Texture Studio"}
        title={
          imageUrl
            ? "在照片上试戴美甲纹理"
            : look
              ? `以「${look.name}」为灵感，试戴相近的美甲纹理`
              : "上传一张手部照片，点选贴合美甲纹理"
        }
        description={
          imageUrl
            ? "选择纹理套装后点击甲面框贴合，或钉选单张纹理逐指搭配；照片只在你的浏览器中处理。"
            : look
              ? "照片只在你的浏览器中处理。上传后系统辅助定位甲面，结果可随时手动调整。"
              : "照片只在你的浏览器中处理。上传后系统辅助定位甲面，识别结果可随时手动调整。"
        }
      >
        {!imageUrl ? (
          <>
            {look && (
              <div className="mb-5">
                <GalleryInspirationCard
                  src={look.src}
                  name={look.name}
                  onPresetColor={handleBannerPresetColor}
                />
              </div>
            )}
            <div className="grid gap-5 md:grid-cols-[1.25fr_.75fr]">
              <section className="rounded-[28px] bg-[var(--surface)] p-3 shadow-[var(--neu-out-md)]  sm:p-5">
                <UploadButton onUpload={handleUpload} />
                {uploadError && (
                  <p role="alert" className="px-3 pb-2 pt-3 text-center text-sm text-red-600">
                    {uploadError}
                  </p>
                )}
              </section>
              <aside className="rounded-[28px] bg-[var(--surface)] p-6 shadow-[var(--neu-out-md)] ">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--coral-soft)]"><Icon name="sparkles" className="h-5 w-5 text-[#a34b3f]" /></span>
                <h2 className="mt-5 text-lg font-semibold text-[#292a27]">获得更自然的效果</h2>
                <ul className="mt-4 space-y-3 text-sm leading-6 text-[#8a8b81]">
                  <li className="flex gap-3"><span className="text-[#ac5145]">01</span><span>选择光线均匀、五指清晰的正面手部照片</span></li>
                  <li className="flex gap-3"><span className="text-[#ac5145]">02</span><span>上传后系统辅助定位甲面，位置可手动调整</span></li>
                  <li className="flex gap-3"><span className="text-[#ac5145]">03</span><span>选择纹理套装点选贴合，或钉选单张纹理逐指搭配</span></li>
                </ul>
                <div className="mt-6 rounded-2xl border border-pink-100/70 bg-pink-50/55 px-4 py-3 text-xs leading-5 text-[#8a8b81]"><Icon name="lock" className="mr-1.5 inline h-4 w-4 align-[-3px]" />本地优先：照片默认不会上传；「用户改进计划」可在隐私页关闭</div>
              </aside>
            </div>
          </>
        ) : (
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <section className="rounded-[30px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-[#8a8b81]">
                  {showFrames ? "显示甲面框中" : "甲面框已隐藏"} · 贴合 {placements.length} 处
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowFrames((value) => !value)}
                    className={`rounded-xl border px-3 py-1.5 text-xs transition ${
                      showFrames
                        ? "border-pink-200 bg-[var(--coral-soft)] text-[#a34b3f]"
                        : "border-pink-100 bg-[var(--surface)] text-[#8a8b81] hover:text-[#ac5145]"
                    }`}
                  >
                    {showFrames ? "隐藏甲面框" : "显示甲面框"}
                  </button>
                  <button
                    onClick={() => setAddingFrame((value) => !value)}
                    className={`rounded-xl px-3 py-1.5 text-xs font-medium text-white shadow-[var(--neu-out-sm)] transition hover:-translate-y-0.5 active:scale-95 ${
                      addingFrame ? "bg-[#a34b3f]" : "bg-[var(--coral)]"
                    }`}
                  >
                    {addingFrame ? "结束添加" : "添加甲面"}
                  </button>
                </div>
              </div>
              <div className="relative">
                <NailCanvas
                  imageUrl={imageUrl}
                  frames={frames}
                  placements={placements}
                  activeTexture={canvasActiveTexture}
                  selectedId={selectedPlacementId}
                  showFrames={showFrames}
                  addingFrame={addingFrame}
                  canUndo={history.length > 0}
                  onFrameClick={(frame) => void handleFrameClick(frame)}
                  onPlacementSelect={handlePlacementSelect}
                  onPlacementMove={handlePlacementMove}
                  onEmptyClick={handleEmptyClick}
                  onUndo={handleUndo}
                  onReset={handleReset}
                />
                {detecting && (
                  <div className="absolute inset-x-3 top-3 flex items-center justify-between gap-3 rounded-2xl bg-[#292a27]/85 px-4 py-3 text-sm text-white">
                    <span role="status">正在识别甲面…</span>
                    <button
                      onClick={skipDetection}
                      className="rounded-full border border-white/40 px-3 py-1 text-xs transition hover:bg-white/10"
                    >
                      跳过
                    </button>
                  </div>
                )}
                {!detecting && addingFrame && (
                  <div className="pointer-events-none absolute inset-x-3 top-3 rounded-2xl bg-[var(--coral)]/90 px-4 py-3 text-center text-sm text-white shadow-lg">
                    添加模式：在空白处点击即可新建甲面框并贴合当前纹理
                  </div>
                )}
              </div>
              {notice && (
                <p role="status" className="mt-3 rounded-2xl bg-amber-50 px-4 py-3 text-sm leading-5 text-amber-800">
                  {notice}
                </p>
              )}
            </section>

            <aside
              className={`rounded-[28px] bg-[var(--surface)] p-5 shadow-[var(--neu-out-md)]  lg:sticky lg:top-24 ${
                expandedSetId !== null ? "relative z-40" : ""
              }`}
            >
              <div className="mb-5 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#ac5145]">Texture Lab</p>
                  <h2 className="mt-1 text-lg font-semibold text-[#292a27]">纹理实验室</h2>
                </div>
                <button onClick={() => setImageUrl(null)} className="rounded-xl border border-pink-100 bg-[var(--surface)] px-3 py-2 text-xs text-[#8a8b81] transition hover:border-pink-200 hover:text-[#ac5145]">更换照片</button>
              </div>

              {look && (
                <div className="mb-4">
                  <GalleryInspirationCard
                    src={look.src}
                    name={look.name}
                    variant="mini"
                    onApplyPreset={handleApplyPreset}
                  />
                </div>
              )}

              <TextureSetPicker
                sets={NAIL_TEXTURE_SETS}
                activeSetId={activeSetId}
                pinnedTextureKey={pinnedTextureKey}
                onApplySet={handleApplySet}
                onPinTexture={handlePinTexture}
                onExpandedChange={setExpandedSetId}
              />

              <div className="my-4 flex items-center gap-3 rounded-2xl border border-pink-100/70 bg-[var(--surface)] p-3">
                {pinnedTexture ? (
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-[var(--line)] bg-pink-50/70">
                    <NextImage src={pinnedTexture.src} alt="钉选纹理" width={36} height={36} className="h-9 w-9 object-contain" />
                  </span>
                ) : (
                  <span
                    className="h-9 w-9 shrink-0 rounded-full border-2 border-white shadow-[var(--neu-out-sm)]"
                    style={{ backgroundColor: activeSet?.dominantColor ?? "#f0e2db" }}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-[#8a8b81]">当前选择</p>
                  <p className="truncate text-sm font-medium text-[#292a27]">{currentSelectionLabel}</p>
                </div>
                <button
                  onClick={handleClearSelection}
                  disabled={!pinnedTextureKey && !activeSetId}
                  className="shrink-0 text-xs font-medium text-[#ac5145] transition hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  清除选择
                </button>
              </div>

              {detectionSummary && (
                <div className="mb-4 space-y-2 rounded-2xl border border-pink-100/70 bg-pink-50/50 p-3 text-xs text-[#75766c]">
                  <div className="flex flex-wrap gap-1.5">
                    <span className="rounded-full bg-[var(--surface)] px-2 py-1 shadow-sm">
                      {detectionSummary.assistedByHandGeometry
                        ? "手部几何辅助定位"
                        : detectionSummary.assistedByPartialCloseup
                          ? "局部近景辅助定位"
                          : BACKEND_LABELS[detectionSummary.backend]}
                    </span>
                    <span className="rounded-full bg-[var(--surface)] px-2 py-1 shadow-sm">甲面框：{frames.length}</span>
                    <span className="rounded-full bg-[var(--surface)] px-2 py-1 shadow-sm">耗时 {Math.round(detectionSummary.elapsedMs)} 毫秒</span>
                  </div>
                  {auxiliaryNotice && (
                    <div role="status" className="rounded-xl bg-amber-50 px-3 py-2 leading-5 text-amber-800">
                      {auxiliaryNotice}
                    </div>
                  )}
                  {hasLowConfidenceFrames && (
                    <div className="rounded-xl bg-amber-50/70 px-3 py-2 leading-5 text-amber-800">
                      部分甲面框为低置信候选，请逐个核对位置与指位后再保存。
                    </div>
                  )}
                  {detectionWarningMessages.length > 0 && (
                    <ul className="list-disc space-y-1 pl-5 text-amber-700">
                      {detectionWarningMessages.map((message) => (
                        <li key={message}>{message}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <NailMattePanel
                availability={matteAvailability}
                candidateCount={frames.length}
                status={matteStatus}
                message={matteMessage}
                matchedCount={matteMatchedCount}
                elapsedMs={matteStartedAt == null ? 0 : matteElapsedMs}
                disabled={detecting}
                onRefine={() => void runMatteRefine()}
                onDetect={() => void runMatteDetect()}
                onCancel={cancelMatte}
              />

              {selectedPlacement && (
                <div className="mt-4 rounded-2xl border border-pink-100/70 bg-pink-50/40 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-[#292a27]">微调所选贴合</p>
                    <button
                      onClick={handleDeletePlacement}
                      className="text-xs text-red-600 transition hover:opacity-80"
                    >
                      删除贴合
                    </button>
                  </div>
                  <AdjustSlider
                    label="长度"
                    min={75}
                    max={140}
                    value={Math.round(activeAdjust.lengthScale * 100)}
                    suffix="%"
                    onChange={(value) => handleAdjustChange({ lengthScale: value / 100 })}
                  />
                  <AdjustSlider
                    label="宽度"
                    min={70}
                    max={145}
                    value={Math.round(activeAdjust.widthScale * 100)}
                    suffix="%"
                    onChange={(value) => handleAdjustChange({ widthScale: value / 100 })}
                  />
                  <AdjustSlider
                    label="位置（负值向甲尖 / 正值向指根）"
                    min={-20}
                    max={20}
                    value={Math.round(activeAdjust.rootOffset * 100)}
                    suffix="%"
                    onChange={(value) => handleAdjustChange({ rootOffset: value / 100 })}
                  />
                  <button
                    onClick={() => handleAdjustChange(DEFAULT_PLACEMENT_ADJUST)}
                    className="mt-3 w-full rounded-xl border border-pink-100 bg-[var(--surface)] px-3 py-2 text-xs text-[#67685f] transition hover:text-[#ac5145]"
                  >
                    重置微调
                  </button>
                </div>
              )}

              {selectedFrame && (
                <div className="mt-4">
                  <p className="mb-2 text-sm font-medium text-[#292a27]">甲面框指位</p>
                  <div className="grid grid-cols-5 gap-1.5 rounded-2xl bg-pink-50/60 p-1.5">
                    {FINGER_NAMES.map((name, finger) => {
                      const active = selectedFrame.assignedFinger === finger;
                      return (
                        <button
                          key={name}
                          onClick={() => handleAssignFrameFinger(finger)}
                          className={`rounded-xl px-1 py-2 text-[11px] transition ${
                            active
                              ? "bg-[var(--surface)] font-medium text-[#ac5145] shadow-sm"
                              : "text-[#8a8b81] hover:bg-[var(--surface)]"
                          }`}
                        >
                          {name}
                        </button>
                      );
                    })}
                  </div>
                  <p className="mt-2 text-xs leading-5 text-[#8a8b81]">
                    指位决定套装模式下点击贴合时使用的纹理；改动后可重新点击甲面框刷新贴合。
                  </p>
                </div>
              )}

              <p className="mt-5 text-center text-xs leading-5 text-[#75766c]">
                选择纹理套装后，点击画面中的指甲框即可贴合；可拖动调整位置
              </p>
            </aside>
          </div>
        )}
      </AppShell>
      {expandedSetId !== null && (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-30 bg-[#f7f4ee]/30 backdrop-blur-[6px]" />
      )}
    </>
  );
}

function AdjustSlider({
  label,
  min,
  max,
  value,
  suffix,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  value: number;
  suffix: string;
  onChange(value: number): void;
}) {
  return (
    <label className="mt-3 block">
      <span className="flex items-center justify-between text-xs text-[#75766c]">
        <span>{label}</span>
        <span className="tabular-nums">{value}{suffix}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1 w-full accent-[var(--coral)]"
      />
    </label>
  );
}
