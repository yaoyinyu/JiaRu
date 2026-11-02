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
import {
  EditorObjectPanel,
  type EditorObjectListItem,
  type EditorObjectSelection,
} from "@/components/EditorObjectPanel";
import { GalleryInspirationCard } from "@/components/GalleryInspiration";
import { loadWorkItemReference } from "@/lib/work-bridge";
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
  clampToImageBounds,
  DEFAULT_PLACEMENT_ADJUST,
  loadTextureAspect,
  type NailPlacement,
  type PlacementAdjust,
  type PlacementFrameInput,
} from "@/lib/canvas/placements";
import { closestTextureSet, NAIL_TEXTURE_SETS } from "@/lib/nail-texture-sets";
import {
  applyRefinedFrameMasks,
  applySetToFrames,
  buildManualFrame,
  firstUnoccupiedFinger,
  frameToMatteCandidate,
  parsePinnedTextureKey,
  pushEditorSnapshot,
  replacePlacementForFrame,
  resolveActiveTexture,
  shouldCoalesceHistory,
  textureKeyFor,
  undoEditorSnapshot,
  type EditorSnapshot,
} from "@/lib/editor-texture-state";
import {
  clearEditorDraft,
  loadEditorDraft,
  saveEditorDraft,
  type EditorDraft,
} from "@/lib/editor-draft";

/** 手动加框的 id 前缀（与识别候选 id 区分）。 */
const MANUAL_FRAME_ID_PREFIX = "manual-";
/** 微调滑杆区锚点元素 id（对象面板「微调」按钮的滚动/聚焦目标）。 */
const ADJUST_PANEL_ID = "editor-adjust-panel";
/** 草稿写入防抖时长。 */
const DRAFT_SAVE_DEBOUNCE_MS = 500;
/** 更换照片两步确认的 armed 等待时长。 */
const CHANGE_PHOTO_ARMED_MS = 5000;

const BACKEND_LABELS: Record<DetectionSummary["backend"], string> = {
  model: "模型识别",
  fallback: "辅助定位",
};

/** 对象名：有指位用指名（如「食指甲面」），否则用「甲面框 N」（frames 中的序号）。 */
function frameObjectLabel(
  frame: PlacementFrameInput | null,
  frames: readonly PlacementFrameInput[]
): string {
  if (!frame) return "甲面";
  if (frame.assignedFinger !== null) {
    return `${FINGER_NAMES[frame.assignedFinger] ?? `指${frame.assignedFinger + 1}`}甲面`;
  }
  const index = frames.findIndex((item) => item.id === frame.id);
  return index >= 0 ? `甲面框 ${index + 1}` : "甲面框";
}

/** 贴合纹理描述：「套装名 / 指名」；键无法解析时回退「自定义纹理」。 */
function textureLabelOf(textureKey: string): string {
  const parsed = parsePinnedTextureKey(textureKey);
  if (!parsed) return "自定义纹理";
  const setName =
    NAIL_TEXTURE_SETS.find((set) => set.id === parsed.setId)?.name ?? parsed.setId;
  return `${setName} / ${FINGER_NAMES[parsed.finger] ?? `指${parsed.finger + 1}`}`;
}

function readMatteNoticeAccepted(): boolean {
  try {
    return window.localStorage.getItem(NAIL_MATTE_NOTICE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** sessionStorage 注入式访问：隐私模式下可能抛错，统一降级为 null。 */
function getSessionStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
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
  const workParam = searchParams.get("work");
  const look =
    GALLERY_IMAGES.find((item) => String(item.id) === galleryParam) ?? null;
  // ?preset=（来自 /nail-analysis）与 ?gallery= 同时传入时 gallery 优先，
  // preset 被忽略，避免改动现有图库链路。
  const presetFromAnalysis = galleryParam
    ? null
    : PRESET_COLORS.find((item) => item.name === presetParam) ?? null;
  return (
    <EditorPageBody
      look={look}
      presetFromAnalysis={presetFromAnalysis}
      workParam={workParam}
    />
  );
}

function EditorPageBody({
  look,
  presetFromAnalysis,
  workParam,
}: {
  look: (typeof GALLERY_IMAGES)[number] | null;
  presetFromAnalysis: { name: string; color: string } | null;
  workParam: string | null;
}) {
  // ?work=（本地作品）优先于 ?gallery=/?preset= 作为灵感参考（方案 §9.4/§9.5）：
  // 读取 WorkItem 预览展示为灵感卡，不自动装载照片；灵感卡确立后与 ?gallery=
  // 相同——用户上传照片识别出甲面后自动贴合一次（见 applyInspirationSet）。
  const [workPreview, setWorkPreview] = useState<{
    url: string;
    name: string;
  } | null>(null);
  useEffect(() => {
    if (!workParam) return;
    let disposed = false;
    let createdUrl: string | null = null;
    (async () => {
      const file = await loadWorkItemReference(workParam);
      if (!file || disposed) return;
      createdUrl = URL.createObjectURL(file);
      setWorkPreview({ url: createdUrl, name: "本地作品" });
    })();
    return () => {
      disposed = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [workParam]);
  // ?preset= → 最接近主色的纹理套装（仅预选、不参与灵感自动贴合；无匹配则忽略并提示）。
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
  const [history, setHistory] = useState<EditorSnapshot[]>([]);
  const [selectedPlacementId, setSelectedPlacementId] = useState<string | null>(null);
  const [selectedFrameId, setSelectedFrameId] = useState<string | null>(null);
  const [adjust, setAdjust] = useState<PlacementAdjust>(DEFAULT_PLACEMENT_ADJUST);
  // 上次编辑恢复提示（§5.7.3）：挂载时有草稿且无图时显示，上传成功后自动恢复。
  const [showRestoreBanner, setShowRestoreBanner] = useState(false);
  // 「更换照片」两步确认 armed 态（§5.7.1）。
  const [changePhotoArmed, setChangePhotoArmed] = useState(false);

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
  const framesRef = useRef<NailDetectionRegion[]>([]);
  const historyRef = useRef<EditorSnapshot[]>([]);
  const matteAvailabilityRef = useRef<NailMatteAvailability | null>(null);
  const matteAvailabilityPromiseRef = useRef<Promise<NailMatteAvailability | null> | null>(null);
  const aspectRequestedRef = useRef(new Set<string>());
  const [textureAspects, setTextureAspects] = useState<Map<string, number>>(new Map());
  const lastHistoryKeyRef = useRef<string | null>(null);
  const lastHistoryAtRef = useRef(0);
  /** 挂载时读到的恢复草稿；上传成功后按尺寸比对消费。 */
  const restorableDraftRef = useRef<EditorDraft | null>(null);
  /** 本次上传已消费过恢复草稿（成功或忽略）：跳过自动识别，避免覆盖恢复结果。 */
  const restoredForImageRef = useRef(false);
  /** 有未导出编辑时为 true（beforeunload 守卫；导出成功后复位）。 */
  const dirtyRef = useRef(false);
  const changePhotoArmedTimerRef = useRef<number | null>(null);
  // 灵感款自动贴合（2026-11-03 用户指示）：灵感色映射到的相近纹理套装 +
  // 来源名；applied 标记保证每次上传至多自动贴合一次。
  const inspirationAutoRef = useRef<{ name: string; setId: string } | null>(null);
  const inspirationAppliedRef = useRef(false);

  useEffect(() => {
    placementsRef.current = placements;
  }, [placements]);
  useEffect(() => {
    framesRef.current = frames;
  }, [frames]);
  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  // 挂载时读取会话草稿（无图时展示恢复提示条）；经微任务读取避免
  // react-hooks/set-state-in-effect（与既有预取模式一致）。
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      const draft = loadEditorDraft(getSessionStorage());
      if (draft) {
        restorableDraftRef.current = draft;
        setShowRestoreBanner(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  // 卸载时中止进行中的本机抠图请求并清理更换照片 armed 计时器。
  useEffect(
    () => () => {
      matteAbortRef.current?.abort();
      matteAbortRef.current = null;
      if (changePhotoArmedTimerRef.current !== null) {
        window.clearTimeout(changePhotoArmedTimerRef.current);
      }
    },
    []
  );

  // 对象 URL 生命周期：更换或卸载时释放。
  useEffect(() => () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  // ── 撤销栈（§5.6）：完整编辑快照（frames + placements）变更前 push；
  // 800ms 内同操作键合并（拖动/滑杆/键盘微调不刷栈），undo 弹栈同时恢复两者。
  // 覆盖操作键：识别替换 frames(detect/matte-detect/matte-refine)、手动加框(frame-add)、
  // 手动框修改(frame-move:/frame-remove:/frame-finger:)、贴合(place:)/替换贴合、
  // 拖动提交与微调(move:/adjust:)、删除贴合(remove:)、重置(reset)、应用全部(apply-all) ──
  const pushHistoryCoalesced = useCallback((key: string) => {
    const now = Date.now();
    if (
      shouldCoalesceHistory(lastHistoryKeyRef.current, lastHistoryAtRef.current, key, now)
    ) {
      lastHistoryAtRef.current = now;
      return;
    }
    lastHistoryKeyRef.current = key;
    lastHistoryAtRef.current = now;
    dirtyRef.current = true;
    setHistory((prev) =>
      pushEditorSnapshot(prev, {
        frames: framesRef.current,
        placements: placementsRef.current,
      })
    );
  }, []);

  const handleUndo = useCallback(() => {
    const result = undoEditorSnapshot(historyRef.current);
    if (!result) return;
    lastHistoryKeyRef.current = null;
    setFrames(result.snapshot.frames);
    framesRef.current = result.snapshot.frames;
    setPlacements(result.snapshot.placements);
    placementsRef.current = result.snapshot.placements;
    setHistory(result.history);
    if (
      selectedPlacementId &&
      !result.snapshot.placements.some((item) => item.id === selectedPlacementId)
    ) {
      setSelectedPlacementId(null);
      setAdjust(DEFAULT_PLACEMENT_ADJUST);
    }
    if (
      selectedFrameId &&
      !result.snapshot.frames.some((item) => item.id === selectedFrameId)
    ) {
      setSelectedFrameId(null);
    }
  }, [selectedFrameId, selectedPlacementId]);

  // Ctrl+Z / Cmd+Z 撤销（§5.5）：输入框聚焦时跳过。
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "z") return;
      if (event.shiftKey) return;
      if (!(event.ctrlKey || event.metaKey)) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      handleUndo();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleUndo]);

  const handleReset = useCallback(() => {
    if (placementsRef.current.length === 0) return;
    pushHistoryCoalesced("reset");
    setPlacements([]);
    placementsRef.current = [];
    setSelectedPlacementId(null);
    setSelectedFrameId(null);
    setAdjust(DEFAULT_PLACEMENT_ADJUST);
  }, [pushHistoryCoalesced]);

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

  // 「更换照片」两步确认（§5.7.1）：首次点击进入 armed 态（按钮文字变化），
  // 5 秒内再次点击执行；超时/失焦/Esc 取消，不使用浏览器原生确认弹窗。
  const disarmChangePhoto = useCallback(() => {
    setChangePhotoArmed(false);
    if (changePhotoArmedTimerRef.current !== null) {
      window.clearTimeout(changePhotoArmedTimerRef.current);
      changePhotoArmedTimerRef.current = null;
    }
  }, []);

  const armChangePhoto = useCallback(() => {
    setChangePhotoArmed(true);
    if (changePhotoArmedTimerRef.current !== null) {
      window.clearTimeout(changePhotoArmedTimerRef.current);
    }
    changePhotoArmedTimerRef.current = window.setTimeout(() => {
      changePhotoArmedTimerRef.current = null;
      setChangePhotoArmed(false);
    }, CHANGE_PHOTO_ARMED_MS);
  }, []);

  // 更换照片 / 首次上传前重置编辑态（纹理选择保留；恢复草稿保留到新图解码后消费）；
  // 仅由上传事件触发，不放在 effect 中（react-hooks/set-state-in-effect）。
  const resetEditState = useCallback(() => {
    setFrames([]);
    framesRef.current = [];
    setOriginalRegions([]);
    setDetectionSummary(null);
    setPlacements([]);
    placementsRef.current = [];
    setHistory([]);
    historyRef.current = [];
    setSelectedPlacementId(null);
    setSelectedFrameId(null);
    setAdjust(DEFAULT_PLACEMENT_ADJUST);
    setExpandedSetId(null);
    setAddingFrame(false);
    setNotice(null);
    setMatteStatus("idle");
    setMatteMessage(null);
    // 新照片重新允许灵感款自动贴合一次。
    inspirationAppliedRef.current = false;
    setMatteMatchedCount(null);
    setMatteStartedAt(null);
    setImageReady(false);
    imageRef.current = null;
    lastHistoryKeyRef.current = null;
    dirtyRef.current = false;
    restoredForImageRef.current = false;
    disarmChangePhoto();
  }, [disarmChangePhoto]);

  /** 执行更换照片：清除草稿并回到上传态（armed 确认通过后调用）。 */
  const handleChangePhoto = useCallback(() => {
    const hasEdits = framesRef.current.length > 0 || placementsRef.current.length > 0;
    if (hasEdits && !changePhotoArmed) {
      armChangePhoto();
      return;
    }
    disarmChangePhoto();
    clearEditorDraft(getSessionStorage());
    resetEditState();
    setImageUrl(null);
  }, [armChangePhoto, changePhotoArmed, disarmChangePhoto, resetEditState]);

  /**
   * 草稿恢复（§5.7.3）：上传成功且原图解码后按尺寸比对消费恢复草稿。
   * 尺寸一致 → 恢复 frames/placements 与纹理选择；不一致 → 丢弃并提示。
   * 仅由 image.onload（异步回调）触发，不在 effect 体内同步执行。
   */
  const restoreFromDraftIfCompatible = useCallback((image: HTMLImageElement) => {
    const draft = restorableDraftRef.current;
    restorableDraftRef.current = null;
    setShowRestoreBanner(false);
    if (!draft) return;
    // 本次上传消费过恢复草稿：无论尺寸是否一致都跳过自动识别，
    // 避免识别结果覆盖恢复出的甲面框/提示（不一致时用户可手动重新识别）。
    restoredForImageRef.current = true;
    const sizeMatches =
      draft.imageWidth === image.naturalWidth && draft.imageHeight === image.naturalHeight;
    if (!sizeMatches) {
      clearEditorDraft(getSessionStorage());
      setNotice("原图与草稿尺寸不一致，已忽略草稿。");
      return;
    }
    setFrames(draft.frames);
    framesRef.current = draft.frames;
    setPlacements(draft.placements);
    placementsRef.current = draft.placements;
    if (draft.activeSetId) setActiveSetId(draft.activeSetId);
    setPinnedTextureKey(draft.pinnedTextureKey);
    dirtyRef.current = true;
    setNotice(
      `已恢复上次编辑：${draft.frames.length} 个甲面框、${draft.placements.length} 处贴合。`
    );
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
      restoreFromDraftIfCompatible(image);
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
  }, [imageUrl, restoreFromDraftIfCompatible]);

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
      // 兜底识别替换 frames：先入撤销栈（快照 = 替换前）。
      pushHistoryCoalesced("matte-detect");
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
  }, [pushHistoryCoalesced]);

  /**
   * 灵感款自动贴合（2026-11-03 用户指示）：把灵感色映射到的相近纹理套装
   * 按指位自动贴合到甲面框。每次上传至多执行一次；用户已有贴合或草稿恢复
   * 时不覆盖；甲面框未就绪时保留待识别完成后重试。贴合结果可逐指调整、
   * 撤销或更换，不改变「辅助定位、非正式识别」的产品口径。
   */
  const applyInspirationSet = useCallback(
    (source: { name: string; setId: string }, framesNow: PlacementFrameInput[]) => {
      if (inspirationAppliedRef.current) return;
      if (restoredForImageRef.current) {
        inspirationAppliedRef.current = true;
        return;
      }
      if (framesNow.length === 0) return;
      if (placementsRef.current.length > 0) {
        inspirationAppliedRef.current = true;
        return;
      }
      const set = NAIL_TEXTURE_SETS.find((item) => item.id === source.setId);
      if (!set) return;
      const result = applySetToFrames({
        set,
        frames: framesNow,
        placements: placementsRef.current,
        aspectOf,
      });
      inspirationAppliedRef.current = true;
      if (result.applied === 0) {
        setNotice(
          `已为灵感「${source.name}」选中相近纹理套装「${set.name}」，但没有可匹配指位的甲面框；可在对象面板确认指位后手动贴合。`
        );
        return;
      }
      pushHistoryCoalesced("inspiration-apply");
      setPlacements(result.placements);
      placementsRef.current = result.placements;
      const skippedText =
        result.skipped > 0 ? `，跳过 ${result.skipped} 个未匹配指位的框` : "";
      setNotice(
        `已按灵感「${source.name}」自动贴合相近纹理套装「${set.name}」到 ${result.applied} 个甲面框${skippedText}；甲面框为辅助定位结果，可逐指调整或撤销。`
      );
    },
    [aspectOf, pushHistoryCoalesced]
  );

  // 上传成功后自动识别（AbortController 管理；跳过 / 更换照片 / 卸载均中止）。
  useEffect(() => {
    if (!imageReady || !imageUrl) return;
    const image = imageRef.current;
    if (!image) return;
    // 本次上传已消费恢复草稿（恢复或忽略）：跳过自动识别，
    // 保留恢复出的甲面框与恢复/忽略提示；需要时可从精细抠图面板手动重跑。
    if (restoredForImageRef.current) return;
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
        // 识别替换 frames：先入撤销栈（快照 = 识别前的空/旧 frames）。
        pushHistoryCoalesced("detect");
        setFrames(regions);
        framesRef.current = regions;
        setDetectionSummary({
          ...detected.summary,
          elapsedMs: Math.max(detected.summary.elapsedMs, performance.now() - startedAt),
        });
        // 灵感款自动贴合：识别出甲面框且灵感色已映射到相近纹理套装时自动应用。
        if (regions.length > 0 && inspirationAutoRef.current) {
          applyInspirationSet(inspirationAutoRef.current, regions);
        }
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
  }, [imageReady, imageUrl, runMatteDetect, pushHistoryCoalesced, applyInspirationSet]);

  const deletePlacementById = useCallback(
    (id: string) => {
      const target = placementsRef.current.find((item) => item.id === id);
      if (!target) return;
      pushHistoryCoalesced(`remove:${id}`);
      setPlacements((prev) => prev.filter((item) => item.id !== id));
      placementsRef.current = placementsRef.current.filter((item) => item.id !== id);
      if (selectedPlacementId === id) {
        setSelectedPlacementId(null);
        setAdjust(DEFAULT_PLACEMENT_ADJUST);
      }
      // 保留其甲面框选中（对象面板转为「未贴合」，可直接重贴）。
    },
    [pushHistoryCoalesced, selectedPlacementId]
  );

  // 键盘微调（§5.5）：位移已由画布换算（2px / Shift 8px），这里钳制画布范围后提交。
  const handlePlacementNudge = useCallback(
    (id: string, dx: number, dy: number) => {
      const image = imageRef.current;
      if (!image) return;
      pushHistoryCoalesced(`move:${id}`);
      const move = (item: NailPlacement): NailPlacement => {
        if (item.id !== id) return item;
        const next = clampToImageBounds(
          item.cx + dx,
          item.cy + dy,
          image.naturalWidth,
          image.naturalHeight
        );
        return { ...item, cx: next.x, cy: next.y };
      };
      setPlacements((prev) => prev.map(move));
      placementsRef.current = placementsRef.current.map(move);
    },
    [pushHistoryCoalesced]
  );

  const handleFrameNudge = useCallback(
    (id: string, dx: number, dy: number) => {
      const image = imageRef.current;
      if (!image) return;
      pushHistoryCoalesced(`frame-move:${id}`);
      const move = (item: NailDetectionRegion): NailDetectionRegion => {
        if (item.id !== id) return item;
        const next = clampToImageBounds(
          item.cx + dx,
          item.cy + dy,
          image.naturalWidth,
          image.naturalHeight
        );
        return { ...item, cx: next.x, cy: next.y };
      };
      setFrames((prev) => prev.map(move));
      framesRef.current = framesRef.current.map(move);
    },
    [pushHistoryCoalesced]
  );

  /** 删除手动甲面框（连同其贴合）；识别框不支持删除并提示。 */
  const handleFrameDelete = useCallback(
    (id: string) => {
      const frame = framesRef.current.find((item) => item.id === id);
      if (!frame) return;
      if (!id.startsWith(MANUAL_FRAME_ID_PREFIX)) {
        setNotice("识别得到的甲面框暂不支持删除；可更换照片或重新识别。");
        return;
      }
      pushHistoryCoalesced(`frame-remove:${id}`);
      setFrames((prev) => prev.filter((item) => item.id !== id));
      framesRef.current = framesRef.current.filter((item) => item.id !== id);
      const removedPlacementIds = new Set(
        placementsRef.current
          .filter((item) => item.frameId === id)
          .map((item) => item.id)
      );
      if (removedPlacementIds.size > 0) {
        setPlacements((prev) => prev.filter((item) => !removedPlacementIds.has(item.id)));
        placementsRef.current = placementsRef.current.filter(
          (item) => !removedPlacementIds.has(item.id)
        );
      }
      if (selectedFrameId === id) setSelectedFrameId(null);
      if (selectedPlacementId && removedPlacementIds.has(selectedPlacementId)) {
        setSelectedPlacementId(null);
        setAdjust(DEFAULT_PLACEMENT_ADJUST);
      }
    },
    [pushHistoryCoalesced, selectedPlacementId, selectedFrameId]
  );

  /** 应用全部（§5.4.4）：当前套装按指位贴合全部甲面框（编辑器侧执行替换）。 */
  const handleApplyAll = useCallback(
    (setId: string) => {
      const set = NAIL_TEXTURE_SETS.find((item) => item.id === setId);
      if (!set || detecting) return;
      if (framesRef.current.length === 0) {
        setNotice("暂无甲面框可贴合；先识别或手动添加甲面框。");
        return;
      }
      const result = applySetToFrames({
        set,
        frames: framesRef.current,
        placements: placementsRef.current,
        aspectOf,
      });
      if (result.applied === 0) {
        setNotice(
          "当前套装没有可匹配指位的纹理；请先在对象面板确认甲面框指位，或钉选单张纹理。"
        );
        return;
      }
      pushHistoryCoalesced("apply-all");
      setPlacements(result.placements);
      placementsRef.current = result.placements;
      const skippedText =
        result.skipped > 0 ? `，跳过 ${result.skipped} 个未匹配指位的甲面框` : "";
      setNotice(`已将「${set.name}」应用到 ${result.applied} 个甲面框${skippedText}。`);
    },
    [aspectOf, detecting, pushHistoryCoalesced]
  );

  // 导出成功（完整或跳过失败贴合）：清草稿、清除未保存标记（beforeunload 随之豁免）。
  const handleExported = useCallback(({ skipped }: { skipped: number }) => {
    dirtyRef.current = false;
    clearEditorDraft(getSessionStorage());
    if (skipped > 0) {
      setNotice(`已导出，但跳过 ${skipped} 处无法加载的贴合纹理。`);
    }
  }, []);

  /** 对象面板「微调」：滚动并聚焦微调滑杆区。 */
  const focusAdjustPanel = useCallback(() => {
    const anchor = document.getElementById(ADJUST_PANEL_ID);
    if (!anchor) return;
    const reduceMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    anchor.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    anchor.focus({ preventScroll: true });
  }, []);

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
    // 灵感色 → 最接近主色的套装；识别出甲面框后自动贴合一次（可撤销）。
    setPinnedTextureKey(null);
    const set = closestTextureSet(preset.color);
    setActiveSetId(set?.id ?? null);
    if (set) {
      inspirationAutoRef.current = { name: preset.name, setId: set.id };
      applyInspirationSet({ name: preset.name, setId: set.id }, framesRef.current);
    }
  }, [applyInspirationSet]);

  const handleBannerPresetColor = useCallback(
    (preset: { name: string; color: string } | null) => {
      if (!preset) return;
      const set = closestTextureSet(preset.color);
      if (set) {
        setActiveSetId(set.id);
        setPinnedTextureKey(null);
        // 记录灵感来源并尝试自动贴合：甲面框未就绪时保留待识别完成后重试。
        inspirationAutoRef.current = { name: preset.name, setId: set.id };
        applyInspirationSet({ name: preset.name, setId: set.id }, framesRef.current);
      } else {
        setNotice(`未找到与「${preset.name}」相近的纹理套装，可在侧栏手动选择。`);
      }
    },
    [applyInspirationSet]
  );

  // ── 贴合：点甲面框 / 手动加框 / 替换为当前纹理 ──
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
        // 未贴合：保留甲面框选中，对象面板显示「未贴合」与贴合动作。
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
      placementsRef.current = replacePlacementForFrame(placementsRef.current, placement);
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
      // 手动加框先入撤销栈（快照 = 加框前状态）；随后贴合命中再入一条。
      pushHistoryCoalesced("frame-add");
      const nextFrames = [...framesRef.current, { ...frame }];
      framesRef.current = nextFrames;
      setFrames(nextFrames);
      setSelectedFrameId(frame.id);
      void handleFrameClick(frame);
    },
    [addingFrame, frames, handleFrameClick, pushHistoryCoalesced]
  );

  const handlePlacementSelect = useCallback((id: string | null) => {
    if (!id) {
      // 取消选中（预览模式/编辑模式点空白）：贴合与甲面框一并取消。
      setSelectedPlacementId(null);
      setSelectedFrameId(null);
      return;
    }
    setSelectedPlacementId(id);
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
      placementsRef.current = placementsRef.current.map((item) =>
        item.id === id ? { ...item, cx, cy } : item
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
      placementsRef.current = placementsRef.current.map((item) =>
        item.id === updated.id ? updated : item
      );
      setAdjust(next);
    },
    [pushHistoryCoalesced, selectedPlacementId]
  );

  const handleDeletePlacement = useCallback(() => {
    if (!selectedPlacementId) return;
    deletePlacementById(selectedPlacementId);
  }, [deletePlacementById, selectedPlacementId]);

  const handleAssignFrameFinger = useCallback(
    (finger: number) => {
      if (!selectedFrameId) return;
      // 指位修改（手动框/识别框通用）：先入撤销栈（快照 = 修改前）。
      pushHistoryCoalesced(`frame-finger:${selectedFrameId}`);
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
    [pushHistoryCoalesced, selectedFrameId]
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
      // 精细抠图替换 mask 与帧几何：先入撤销栈（快照 = 精细处理前）。
      pushHistoryCoalesced("matte-refine");
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
  }, [frames, pushHistoryCoalesced]);

  // ── 会话草稿（§5.7.3）：编辑态变更防抖写入；导出成功/更换照片时清除 ──
  useEffect(() => {
    if (!imageUrl || !imageReady) return;
    const image = imageRef.current;
    if (!image) return;
    const timer = window.setTimeout(() => {
      const storage = getSessionStorage();
      if (framesRef.current.length === 0 && placementsRef.current.length === 0) {
        clearEditorDraft(storage);
        return;
      }
      saveEditorDraft(storage, {
        frames: framesRef.current,
        placements: placementsRef.current,
        activeSetId,
        pinnedTextureKey,
        imageWidth: image.naturalWidth,
        imageHeight: image.naturalHeight,
        savedAt: Date.now(),
      });
    }, DRAFT_SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [imageUrl, imageReady, frames, placements, activeSetId, pinnedTextureKey]);

  // beforeunload 守卫（§5.7.2）：导出后又有未保存编辑（贴合或手动框非空）时提示；
  // dirtyRef 在导出成功时复位，天然实现「导出后豁免、继续编辑重新生效」。
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      if (!imageRef.current) return;
      const hasEdits =
        placementsRef.current.length > 0 ||
        framesRef.current.some((item) => item.id.startsWith(MANUAL_FRAME_ID_PREFIX));
      if (!hasEdits) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

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

  // ── 对象面板（§5.3）：贴合优先于甲面框；全部标签由页面派生，面板纯展示 ──
  const panelSelection = useMemo<EditorObjectSelection | null>(() => {
    if (selectedPlacement) {
      const frame = frames.find((item) => item.id === selectedPlacement.frameId) ?? null;
      return {
        kind: "placement",
        objectLabel: frameObjectLabel(frame, frames),
        statusLine: `已贴合「${textureLabelOf(selectedPlacement.textureKey)}」`,
      };
    }
    if (selectedFrame) {
      return {
        kind: "frame",
        objectLabel: frameObjectLabel(selectedFrame, frames),
        statusLine: "未贴合",
      };
    }
    return null;
  }, [selectedPlacement, selectedFrame, frames]);

  const objectItems = useMemo<EditorObjectListItem[]>(
    () =>
      frames.map((frame) => {
        const placement =
          placements.find((item) => item.frameId === frame.id) ?? null;
        return {
          frameId: frame.id,
          label: frameObjectLabel(frame, frames),
          placed: placement !== null,
          placementLabel: placement ? textureLabelOf(placement.textureKey) : null,
          manual: frame.id.startsWith(MANUAL_FRAME_ID_PREFIX),
        };
      }),
    [frames, placements]
  );

  /** 对象列表行点击：已贴合 → 选中贴合；未贴合 → 选中甲面框并贴合（无纹理时提示）。 */
  const handleSelectObjectItem = useCallback(
    (frameId: string) => {
      const frame = framesRef.current.find((item) => item.id === frameId);
      if (!frame) return;
      const placement = placementsRef.current.find(
        (item) => item.frameId === frameId
      );
      if (placement) {
        setSelectedPlacementId(placement.id);
        setSelectedFrameId(frameId);
        setAdjust(placement.adjust);
        return;
      }
      setSelectedPlacementId(null);
      void handleFrameClick(frame);
    },
    [handleFrameClick]
  );

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
            {showRestoreBanner && (
              <div
                role="status"
                className="mb-5 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-pink-100 bg-[var(--coral-soft)] px-4 py-3 text-sm text-[#a34b3f]"
              >
                <span>上次编辑未保存。重新上传原图后可恢复贴合。</span>
                <button
                  type="button"
                  onClick={() => {
                    restorableDraftRef.current = null;
                    clearEditorDraft(getSessionStorage());
                    setShowRestoreBanner(false);
                  }}
                  className="rounded-xl border border-pink-200 bg-[var(--surface)] px-3 py-1.5 text-xs font-medium text-[#6f7066] transition hover:text-[#ac5145]"
                >
                  忽略并清除
                </button>
              </div>
            )}
            {workPreview ? (
              <div className="mb-5">
                <GalleryInspirationCard
                  src={workPreview.url}
                  name={workPreview.name}
                  onPresetColor={handleBannerPresetColor}
                />
              </div>
            ) : look ? (
              <div className="mb-5">
                <GalleryInspirationCard
                  src={look.src}
                  name={look.name}
                  onPresetColor={handleBannerPresetColor}
                />
              </div>
            ) : null}
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
                <ul className="mt-4 space-y-3 text-sm leading-6 text-[#6f7066]">
                  <li className="flex gap-3"><span className="text-[#ac5145]">01</span><span>选择光线均匀、五指清晰的正面手部照片</span></li>
                  <li className="flex gap-3"><span className="text-[#ac5145]">02</span><span>上传后系统辅助定位甲面，位置可手动调整</span></li>
                  <li className="flex gap-3"><span className="text-[#ac5145]">03</span><span>选择纹理套装点选贴合，或钉选单张纹理逐指搭配</span></li>
                </ul>
                <div className="mt-6 rounded-2xl border border-pink-100/70 bg-pink-50/55 px-4 py-3 text-xs leading-5 text-[#6f7066]"><Icon name="lock" className="mr-1.5 inline h-4 w-4 align-[-3px]" />本地优先：照片默认不会上传；「用户改进计划」可在隐私页关闭</div>
              </aside>
            </div>
          </>
        ) : (
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            {/* 左列：画布 + 对象面板（移动端面板转为固定底部抽屉，不占网格位） */}
            <div className="flex min-w-0 flex-col gap-5">
            <section className="rounded-[30px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-[#6f7066]">
                  {showFrames ? "显示甲面框中" : "甲面框已隐藏"} · 贴合 {placements.length} 处
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowFrames((value) => !value)}
                    className={`rounded-xl border px-3 py-1.5 text-xs transition ${
                      showFrames
                        ? "border-pink-200 bg-[var(--coral-soft)] text-[#a34b3f]"
                        : "border-pink-100 bg-[var(--surface)] text-[#6f7066] hover:text-[#ac5145]"
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
                  selectedFrameId={selectedFrameId}
                  showFrames={showFrames}
                  addingFrame={addingFrame}
                  canUndo={history.length > 0}
                  onFrameClick={(frame) => void handleFrameClick(frame)}
                  onPlacementSelect={handlePlacementSelect}
                  onPlacementMove={handlePlacementMove}
                  onEmptyClick={handleEmptyClick}
                  onPlacementNudge={handlePlacementNudge}
                  onPlacementDelete={deletePlacementById}
                  onFrameNudge={handleFrameNudge}
                  onFrameDelete={handleFrameDelete}
                  onExported={handleExported}
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

            <EditorObjectPanel
              selection={panelSelection}
              items={objectItems}
              selectedFrameId={selectedFrameId}
              onReplace={() => {
                if (!selectedPlacement) return;
                const frame = frames.find((item) => item.id === selectedPlacement.frameId);
                if (!frame) {
                  setNotice("未找到该贴合的甲面框；请直接点击甲面框重新贴合。");
                  return;
                }
                void handleFrameClick(frame);
              }}
              onAdjust={focusAdjustPanel}
              onRemove={handleDeletePlacement}
              onApplyToFrame={() => {
                if (!selectedFrame) return;
                void handleFrameClick(selectedFrame);
              }}
              onSelectItem={handleSelectObjectItem}
              onAssignFinger={handleAssignFrameFinger}
              frameFinger={selectedFrame?.assignedFinger ?? null}
              frameDeletable={selectedFrame?.id.startsWith(MANUAL_FRAME_ID_PREFIX) ?? false}
              onDeleteFrame={() => {
                if (selectedFrame) handleFrameDelete(selectedFrame.id);
              }}
            />
            </div>

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
                {/* 更换照片两步确认（§5.7.1）：无可丢弃编辑时直接更换。 */}
                <button
                  type="button"
                  onClick={handleChangePhoto}
                  onBlur={changePhotoArmed ? disarmChangePhoto : undefined}
                  onKeyDown={(event) => {
                    if (event.key === "Escape" && changePhotoArmed) {
                      event.preventDefault();
                      disarmChangePhoto();
                    }
                  }}
                  className={`max-w-[240px] truncate rounded-xl px-3 py-2 text-xs transition ${
                    changePhotoArmed
                      ? "bg-[#a34b3f] font-medium text-white shadow-[var(--neu-out-sm)]"
                      : "border border-pink-100 bg-[var(--surface)] text-[#6f7066] hover:border-pink-200 hover:text-[#ac5145]"
                  }`}
                >
                  {changePhotoArmed
                    ? `确认更换（将丢弃 ${frames.length} 个甲面框与 ${placements.length} 处贴合）`
                    : "更换照片"}
                </button>
              </div>
              {changePhotoArmed && (
                <p role="status" className="mb-4 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  将丢弃当前 {frames.length} 个甲面框与 {placements.length} 处贴合；5 秒内再次点击确认执行，超时、移开焦点或按 Esc 取消。
                </p>
              )}

              {workPreview ? (
                <div className="mb-4">
                  <GalleryInspirationCard
                    src={workPreview.url}
                    name={workPreview.name}
                    variant="mini"
                    onApplyPreset={handleApplyPreset}
                  />
                </div>
              ) : look ? (
                <div className="mb-4">
                  <GalleryInspirationCard
                    src={look.src}
                    name={look.name}
                    variant="mini"
                    onApplyPreset={handleApplyPreset}
                  />
                </div>
              ) : null}

              <TextureSetPicker
                sets={NAIL_TEXTURE_SETS}
                activeSetId={activeSetId}
                pinnedTextureKey={pinnedTextureKey}
                frameCount={frames.length}
                placementCount={placements.length}
                onApplySet={handleApplySet}
                onPinTexture={handlePinTexture}
                onApplyAll={handleApplyAll}
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
                  <p className="text-xs text-[#6f7066]">当前选择</p>
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
                <div className="mb-4 space-y-2 rounded-2xl border border-pink-100/70 bg-pink-50/50 p-3 text-xs text-[#67685f]">
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
                <div
                  id={ADJUST_PANEL_ID}
                  tabIndex={-1}
                  className="mt-4 rounded-2xl border border-pink-100/70 bg-pink-50/40 p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--coral)]"
                >
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

              <p className="mt-5 text-center text-xs leading-5 text-[#67685f]">
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
      <span className="flex items-center justify-between text-xs text-[#67685f]">
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
