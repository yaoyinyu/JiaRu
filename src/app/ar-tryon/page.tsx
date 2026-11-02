"use client";

import { Suspense, useState, useCallback, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { AppShell } from "@/components/AppShell";
import { Icon } from "@/components/Icon";
import { ArView, type NailFitAdjustment } from "@/components/ArView";
import { type NailRenderStyle } from "@/lib/ar-nail-shape";
import { PRESET_COLORS } from "@/lib/utils";
import { disposeAllTextures } from "@/lib/texture";
import type { NailAssignment } from "@/components/NailArtPicker";
import type { NailTextureProfile } from "@/lib/nail-texture-recognition";
import { validateImageUpload } from "@/lib/image-upload-validation";
import { loadReferenceFromParams } from "@/lib/gallery-bridge";
import { loadWorkItemReference } from "@/lib/work-bridge";
import { releaseRemovedBitmaps } from "@/lib/ar-texture-release";
import {
  decideArReview,
  formatArApplyNotice,
  formatArReviewSummary,
  summarizeArReview,
  type ArReviewAction,
} from "@/lib/ar-review-flow";
import {
  formatArReviewAppliedNotice,
  resolveArStepProgress,
} from "@/lib/ar-step-flow";
import { AppDialog } from "@/components/ui/AppDialog";
import { StatusRegion } from "@/components/ui/StatusRegion";
import { UploadTrigger } from "@/components/ui/UploadTrigger";

const TextureCropper = dynamic(() => import("@/components/TextureCropper"), {
  ssr: false,
});

const NailArtPicker = dynamic(() => import("@/components/NailArtPicker"), {
  ssr: false,
});

const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];
const DEFAULT_NAIL_FIT: NailFitAdjustment = {
  lengthScale: 1,
  widthScale: 1,
  rootOffset: 0,
};

const SHAPE_LABELS: Record<string, string> = {
  round: "圆形",
  square: "方形",
  almond: "杏仁",
  stiletto: "尖形",
};
const PATTERN_LABELS: Record<string, string> = {
  solid: "纯色",
  gradient: "渐变",
  french: "法式",
  glitter: "亮片",
  pattern: "花纹",
};

function describeGlossLevel(gloss: number): string {
  if (gloss < 0.33) return "哑光";
  if (gloss < 0.66) return "缎光";
  return "高光";
}

function createEmptyStyles(): (NailRenderStyle | null)[] {
  return [null, null, null, null, null];
}

function createEmptyProfiles(): (NailTextureProfile | null)[] {
  return [null, null, null, null, null];
}

function createDefaultNailFits(): NailFitAdjustment[] {
  return Array.from({ length: 5 }, () => ({ ...DEFAULT_NAIL_FIT }));
}

/** 覆盖前复核的待应用集合（§7.2）：提取结果尚未上屏，等待用户裁决。 */
interface PendingTextureReview {
  assignments: NailAssignment[];
  summary: ReturnType<typeof summarizeArReview>;
  action: Exclude<ArReviewAction, "apply" | "apply_with_notice">;
}

/** 撤销点：应用前一刻的完整试戴状态。 */
interface ApplyUndoState {
  textures: (ImageBitmap | null)[];
  styles: (NailRenderStyle | null)[];
  profiles: (NailTextureProfile | null)[];
}

const REVIEW_DIALOG_COPY: Record<
  PendingTextureReview["action"],
  { title: string; description: string }
> = {
  review: {
    title: "复核提取结果",
    description: "部分甲面识别置信度较低，应用前请确认，或先继续调整。",
  },
  replace_preview: {
    title: "替换现有纹理",
    description: "提取完成。确认后，下列纹理将替换当前试戴中的旧纹理。",
  },
  confirm: {
    title: "确认替换纹理",
    description: "当前已有试戴纹理，且新提取结果建议复核；确认后才会替换。",
  },
};

const reviewPrimaryButtonClass =
  "min-h-11 rounded-xl bg-[var(--coral)] px-6 py-2.5 text-sm font-semibold text-white shadow-[var(--neu-out-sm)] transition hover:opacity-90";

const reviewSecondaryButtonClass =
  "min-h-11 rounded-xl border border-[var(--coral-soft)] bg-[var(--surface)] px-5 py-2.5 text-sm font-medium text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:opacity-90";

export default function ArTryonPage() {
  // useSearchParams 在静态渲染的客户端组件中必须包 Suspense（与 /editor 同一约定）。
  return (
    <Suspense fallback={null}>
      <ArTryonPageInner />
    </Suspense>
  );
}

function ArTryonPageInner() {
  const searchParams = useSearchParams();
  const workParam = searchParams.get("work");
  const galleryParam = searchParams.get("gallery");
  const collectParam = searchParams.get("collect");
  return (
    <ArTryonPageBody
      workParam={workParam}
      galleryParam={galleryParam}
      collectParam={collectParam}
    />
  );
}

function ArTryonPageBody({
  workParam,
  galleryParam,
  collectParam,
}: {
  workParam: string | null;
  galleryParam: string | null;
  collectParam: string | null;
}) {
  const [nailColors, setNailColors] = useState([
    "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF", "#E8A0BF",
  ]);
  const [nailTextures, setNailTextures] = useState<(ImageBitmap | null)[]>([
    null, null, null, null, null,
  ]);
  const [activeFinger, setActiveFinger] = useState(0);
  const [mode, setMode] = useState<"color" | "texture">("color");
  const [nailFits, setNailFits] = useState<NailFitAdjustment[]>(createDefaultNailFits);
  const [nailStyles, setNailStyles] = useState<(NailRenderStyle | null)[]>(createEmptyStyles);
  const [textureProfiles, setTextureProfiles] = useState<(NailTextureProfile | null)[]>(
    createEmptyProfiles
  );
  const [showCropper, setShowCropper] = useState(false);
  const [showNailPicker, setShowNailPicker] = useState(false);
  const [uploadedPhotoUrl, setUploadedPhotoUrl] = useState<string | null>(null);
  // §7.1 步骤状态：摄像头会话是否运行中 + 来源卡片触发的启动信号。
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraStartSignal, setCameraStartSignal] = useState(0);
  // §7.2 覆盖前复核：待应用集合 + 应用反馈（含撤销）。
  const [pendingReview, setPendingReview] = useState<PendingTextureReview | null>(null);
  const [applyFeedback, setApplyFeedback] = useState<{
    message: string;
    canUndo: boolean;
  } | null>(null);
  // 「继续调整」重开选择器时只保留识别与手动提取，不重跑自动一条龙。
  const [pickerSuppressAuto, setPickerSuppressAuto] = useState(false);

  // 用 ref 跟踪最新纹理和图片 URL，确保组件卸载时正确释放资源。
  const texturesRef = useRef(nailTextures);
  const photoUrlRef = useRef(uploadedPhotoUrl);
  // 撤销点只被事件处理器消费（可见性由 applyFeedback.canUndo 驱动），用 ref 持有即可。
  const undoStateRef = useRef<ApplyUndoState | null>(null);
  const pendingReviewRef = useRef<PendingTextureReview | null>(null);

  useEffect(() => {
    texturesRef.current = nailTextures;
  }, [nailTextures]);

  useEffect(() => {
    photoUrlRef.current = uploadedPhotoUrl;
  }, [uploadedPhotoUrl]);

  const hasAnyTexture = nailTextures.some((texture) => texture != null);
  const activeNailFit = nailFits[activeFinger] ?? DEFAULT_NAIL_FIT;
  // 已做逐指校准的手指数（与默认值任一字段不同即计为已调整）。
  const adjustedFingerCount = nailFits.filter(
    (fit) =>
      fit.lengthScale !== DEFAULT_NAIL_FIT.lengthScale ||
      fit.widthScale !== DEFAULT_NAIL_FIT.widthScale ||
      fit.rootOffset !== DEFAULT_NAIL_FIT.rootOffset
  ).length;

  // §7.1 顶部步骤状态：提取弹层 / 复核界面打开时处于 Step 2。
  const stepProgress = resolveArStepProgress({
    hasAnyTexture,
    extractionActive: showCropper || showNailPicker || pendingReview !== null,
    cameraActive,
  });

  /** 丢弃未应用的复核集合：释放其中尚未上屏的提取位图。 */
  const discardAssignments = (assignments: NailAssignment[]) => {
    for (const assignment of assignments) assignment.texture.close();
  };

  const clearPendingReview = useCallback(() => {
    const pending = pendingReviewRef.current;
    if (!pending) return;
    pendingReviewRef.current = null;
    setPendingReview(null);
    discardAssignments(pending.assignments);
  }, []);

  /** 手动编辑使旧撤销点失效：按新数组释放旧快照中不再保留的位图。 */
  const clearUndoSnapshot = useCallback(
    (nextTextures: (ImageBitmap | null)[]) => {
      const snapshot = undoStateRef.current;
      if (!snapshot) return;
      releaseRemovedBitmaps(snapshot.textures, nextTextures);
      undoStateRef.current = null;
    },
    []
  );

  useEffect(() => {
    return () => {
      disposeAllTextures(texturesRef.current);
      // 释放撤销快照中已不在当前数组里的旧位图，避免撤销挂起的位图泄漏。
      const snapshot = undoStateRef.current;
      if (snapshot) releaseRemovedBitmaps(snapshot.textures, texturesRef.current);
      const pending = pendingReviewRef.current;
      if (pending) discardAssignments(pending.assignments);
      const url = photoUrlRef.current;
      if (url) URL.revokeObjectURL(url);
    };
  }, []);

  const updateActiveNailFit = (patch: Partial<NailFitAdjustment>) => {
    setNailFits((current) => current.map((fit, index) => (
      index === activeFinger ? { ...fit, ...patch } : fit
    )));
  };

  const resetAllNailFits = () => {
    setNailFits(createDefaultNailFits());
  };

  const changeColor = (color: string) => {
    const updated = [...nailColors];
    updated[activeFinger] = color;
    setNailColors(updated);
  };

  const applyToAll = () => {
    setNailColors(Array(5).fill(nailColors[activeFinger]));
  };

  const prepareUploadUrl = useCallback((file: File) => {
    const previous = photoUrlRef.current;
    if (previous) URL.revokeObjectURL(previous);
    const url = URL.createObjectURL(file);
    photoUrlRef.current = url;
    return url;
  }, []);

  // Step 1 来源一：上传参考图 → 多指纹理提取选择器。
  const openReferencePicker = useCallback(
    async (file: File) => {
      const validation = await validateImageUpload(file);
      if (!validation.ok) {
        alert(validation.message);
        return;
      }
      clearPendingReview();
      const url = prepareUploadUrl(file);
      setUploadedPhotoUrl(url);
      setPickerSuppressAuto(false);
      setShowNailPicker(true);
    },
    [clearPendingReview, prepareUploadUrl]
  );

  // Step 1 来源二：上传单纹理 → 手动裁剪。
  const openSingleTextureCropper = useCallback(
    async (file: File) => {
      const validation = await validateImageUpload(file);
      if (!validation.ok) {
        alert(validation.message);
        return;
      }
      clearPendingReview();
      const url = prepareUploadUrl(file);
      setUploadedPhotoUrl(url);
      setShowCropper(true);
    },
    [clearPendingReview, prepareUploadUrl]
  );

  // Step 1 来源三：开启实时摄像头（ArView 内部保持唯一「开启摄像头」按钮语义，
  // 这里递增启动信号代为触发，并滚动到摄像头画面）。
  const startLiveCamera = useCallback(() => {
    clearPendingReview();
    setCameraStartSignal((signal) => signal + 1);
    document
      .getElementById("ar-camera-frame")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [clearPendingReview]);

  const handleCameraActiveChange = useCallback((active: boolean) => {
    setCameraActive((current) => (current === active ? current : active));
  }, []);

  // 跨页参考图带入（?work= 优先于 ?gallery=/?collect=，方案 §9.4 优先级）：
  // 加载后走与手动上传完全一致的校验与 objectURL 管线，直接打开多指指甲选取器；
  // 任何失败静默降级，不阻塞手动上传主流程。ref 防止 React StrictMode 下重复执行。
  const galleryRefLoadStarted = useRef(false);
  useEffect(() => {
    if (galleryRefLoadStarted.current) return;
    if (!workParam && !galleryParam && !collectParam) return;
    galleryRefLoadStarted.current = true;
    (async () => {
      let file: File | null = null;
      if (workParam) {
        file = await loadWorkItemReference(workParam);
      }
      if (!file && (galleryParam || collectParam)) {
        const ref = await loadReferenceFromParams({ gallery: galleryParam, collect: collectParam });
        file = ref?.file ?? null;
      }
      if (!file) return;
      await openReferencePicker(file);
    })();
  }, [workParam, galleryParam, collectParam, openReferencePicker]);

  const handleCropConfirm = useCallback(
    (bitmap: ImageBitmap) => {
      const old = nailTextures[activeFinger];
      const updated = [...nailTextures];
      updated[activeFinger] = bitmap;

      // 手动替换使旧撤销点失效：先按新数组释放旧快照中不再保留的位图。
      clearUndoSnapshot(updated);

      // 仅当旧纹理没有被其他手指复用时才释放（close 幂等，重复调用安全）。
      if (old && !updated.some((texture) => texture === old)) {
        old.close();
      }

      setNailTextures(updated);
      // 手动裁剪路径没有掩膜分析，清空该指的样式与分析结果，按默认渲染。
      setNailStyles((current) => current.map((style, index) => (index === activeFinger ? null : style)));
      setTextureProfiles((current) => current.map((profile, index) => (index === activeFinger ? null : profile)));
      setShowCropper(false);
      setMode("texture");
    },
    [activeFinger, nailTextures, clearUndoSnapshot]
  );

  const handleCropCancel = useCallback(() => {
    setShowCropper(false);
  }, []);

  /**
   * 应用一批纹理分配并管理撤销点。
   * undoable=true（自动/复核路径）：旧位图保留在撤销快照中，释放延迟到
   * 撤销 / 下一次应用覆盖 / 卸载时机；undoable=false（手动路径）：立即释放。
   */
  const commitAssignments = useCallback(
    (assignments: NailAssignment[], opts: { undoable: boolean }) => {
      const previousTextures = nailTextures;
      const previousStyles = nailStyles;
      const previousProfiles = textureProfiles;
      const updated = [...previousTextures];
      const nextStyles = [...previousStyles];
      const nextProfiles = [...previousProfiles];

      for (const assignment of assignments) {
        updated[assignment.finger] = assignment.texture;
        const profile = assignment.profile ?? null;
        nextStyles[assignment.finger] = profile
          ? { shape: profile.shape, gloss: profile.gloss }
          : null;
        nextProfiles[assignment.finger] = profile;
      }

      if (opts.undoable) {
        // 新应用覆盖旧撤销点：释放旧快照中不再被新数组保留的位图。
        const staleUndo = undoStateRef.current;
        if (staleUndo) releaseRemovedBitmaps(staleUndo.textures, updated);
      } else {
        releaseRemovedBitmaps(previousTextures, updated);
        clearUndoSnapshot(updated);
      }

      setNailTextures(updated);
      setNailStyles(nextStyles);
      setTextureProfiles(nextProfiles);
      setMode("texture");
      setShowNailPicker(false);

      if (opts.undoable) {
        const snapshot: ApplyUndoState = {
          textures: previousTextures,
          styles: previousStyles,
          profiles: previousProfiles,
        };
        undoStateRef.current = snapshot;
      } else {
        undoStateRef.current = null;
      }
    },
    [nailTextures, nailStyles, textureProfiles, clearUndoSnapshot]
  );

  const handlePickingConfirm = useCallback(
    (assignments: NailAssignment[], options?: { auto?: boolean }) => {
      // 新结果到达时，旧的未应用复核集合一并丢弃。
      clearPendingReview();

      if (options?.auto) {
        // §7.2 覆盖前复核：按有无旧纹理 + 整批最低置信档决定动作。
        const confidences = assignments.map(
          (assignment) => assignment.confidence ?? "low"
        );
        const summary = summarizeArReview(confidences);
        const action = decideArReview({
          hasExistingTexture: nailTextures.some((texture) => texture != null),
          lowestConfidence: summary.lowest ?? "low",
        });

        if (action === "apply" || action === "apply_with_notice") {
          commitAssignments(assignments, { undoable: true });
          setApplyFeedback({
            message: formatArApplyNotice({
              appliedCount: assignments.length,
              reviewCount: summary.reviewCount,
            }),
            canUndo: true,
          });
          return;
        }

        // 低置信复核 / 替换预览 / 必须确认：先不应用，等待复核界面裁决。
        setShowNailPicker(false);
        const pending: PendingTextureReview = { assignments, summary, action };
        pendingReviewRef.current = pending;
        setPendingReview(pending);
        return;
      }

      // 手动路径：用户已在选择器内逐甲确认，直接应用。
      commitAssignments(assignments, { undoable: false });
    },
    [nailTextures, clearPendingReview, commitAssignments]
  );

  const handlePickingCancel = useCallback(() => {
    setShowNailPicker(false);
  }, []);

  // §7.2 复核界面三键：应用 / 继续调整 / 取消。
  const applyPendingReview = useCallback(() => {
    const pending = pendingReviewRef.current;
    if (!pending) return;
    commitAssignments(pending.assignments, { undoable: true });
    pendingReviewRef.current = null;
    setPendingReview(null);
    setApplyFeedback({
      message: formatArReviewAppliedNotice({
        appliedCount: pending.assignments.length,
        reviewCount: pending.summary.reviewCount,
      }),
      canUndo: true,
    });
  }, [commitAssignments]);

  const continueAdjusting = useCallback(() => {
    // 回到选择器手动微调：丢弃待应用集合（不改变当前试戴配置），
    // 重开时关闭自动一条龙，由用户手动提取。
    clearPendingReview();
    setPickerSuppressAuto(true);
    setShowNailPicker(true);
  }, [clearPendingReview]);

  const cancelPendingReview = useCallback(() => {
    clearPendingReview();
  }, [clearPendingReview]);

  const undoLastApply = useCallback(() => {
    const snapshot = undoStateRef.current;
    if (!snapshot) return;
    // 恢复快照；本次应用引入、恢复后不再被引用的位图直接释放。
    releaseRemovedBitmaps(texturesRef.current, snapshot.textures);
    setNailTextures(snapshot.textures);
    setNailStyles(snapshot.styles);
    setTextureProfiles(snapshot.profiles);
    undoStateRef.current = null;
    setApplyFeedback({ message: "已撤销本次应用，恢复之前的纹理。", canUndo: false });
  }, []);

  const applyTextureToAll = () => {
    const activeTexture = nailTextures[activeFinger];
    if (!activeTexture) {
      alert("当前手指还没有设置纹理");
      return;
    }

    const updated = nailTextures.map(() => activeTexture);
    clearUndoSnapshot(updated);

    // 释放不再保留的资源：比较更新前后仍在使用的唯一 bitmap 集合。
    // 旧实现逐项检查"其他手指是否还有共享引用"——A 被多指共享时每个槽
    // 都能看到另一个 A 而全部跳过 close（评审复现：A 四指共享、第五指 B
    // 应用全部后 A 无槽位引用但 close 0 次）。
    releaseRemovedBitmaps(nailTextures, updated);

    setNailTextures(updated);
  };

  const removeTexture = (fingerIndex: number) => {
    const texture = nailTextures[fingerIndex];
    const updated = [...nailTextures];
    updated[fingerIndex] = null;
    clearUndoSnapshot(updated);

    if (texture && !updated.some((item) => item === texture)) {
      texture.close();
    }

    setNailTextures(updated);
    setNailStyles((current) => current.map((style, index) => (index === fingerIndex ? null : style)));
    setTextureProfiles((current) =>
      current.map((profile, index) => (index === fingerIndex ? null : profile))
    );
  };

  return (
    <AppShell
      wide
      shiftUp
      eyebrow="实时试戴"
      title="让每一次抬手，都提前看见效果"
      description="实时追踪手部动作，让颜色与纹理自然贴合指甲。所有摄像头画面都只在本地内存中处理。"
    >
      {/* §7.1 顶部步骤状态：选择来源 → 提取与复核 → 试戴与校准 */}
      <nav
        aria-label="试戴步骤"
        className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl bg-[var(--surface)] px-4 py-3 text-xs shadow-[var(--neu-out-md)]"
      >
        {stepProgress.steps.map((step, index) => (
          <span
            key={step.id}
            className="flex items-center gap-2"
            aria-current={step.status === "active" ? "step" : undefined}
          >
            {index > 0 && (
              <span aria-hidden="true" className="h-px w-6 bg-[var(--line)]" />
            )}
            <span
              aria-hidden="true"
              className={`flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ${
                step.status === "active"
                  ? "bg-[var(--coral)] text-white"
                  : step.status === "done"
                    ? "bg-[var(--sage)] text-[#884338]"
                    : "bg-pink-50 text-gray-400"
              }`}
            >
              {step.status === "done" ? "✓" : index + 1}
            </span>
            <span
              className={
                step.status === "active"
                  ? "font-medium text-[#292a27]"
                  : "text-[#6f7066]"
              }
            >
              {step.label}
            </span>
          </span>
        ))}
      </nav>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section id="ar-camera-frame" className="overflow-hidden rounded-[30px] bg-[var(--surface)] p-3 shadow-[var(--neu-out-md)]  sm:p-5">
          <ArView
            nailColors={nailColors}
            nailTextures={nailTextures}
            nailStyles={nailStyles}
            mode={mode}
            nailAdjustments={nailFits}
            activeFinger={activeFinger}
            onCameraActiveChange={handleCameraActiveChange}
            startSignal={cameraStartSignal}
            onSuggestUpload={() => {
              // 用户在连续失败覆盖层选择「改用上传照片试色」：
              // 摄像头由 ArView 自行停止，这里回到页面上方的上传入口。
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </section>
        <aside className="rounded-[28px] bg-[var(--surface)] p-5 shadow-[var(--neu-out-md)]  xl:sticky xl:top-24">
          <div className="mb-5">
            <h2 className="text-lg font-semibold text-[#292a27]">试戴设置</h2>
          </div>
        <div className="w-full">
          {/* §7.1 Step 1 选择来源：上传参考图 / 上传单纹理 / 开启实时摄像头 */}
          <div className="mb-4 rounded-2xl border border-pink-100 p-3">
            <div className="mb-2 text-xs font-medium text-[#67685f]">
              第一步 · 选择来源
            </div>
            <div className="flex flex-wrap gap-2">
              <UploadTrigger
                accept="image/png,image/jpeg,image/webp"
                aria-label="上传参考图，自动提取多指纹理"
                onFiles={(files) => {
                  const file = files[0];
                  if (file) void openReferencePicker(file);
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="sparkles" className="h-4 w-4" />
                  上传参考图
                </span>
              </UploadTrigger>
              <UploadTrigger
                accept="image/png,image/jpeg,image/webp"
                aria-label="上传单张纹理并手动裁剪"
                onFiles={(files) => {
                  const file = files[0];
                  if (file) void openSingleTextureCropper(file);
                }}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="image" className="h-4 w-4" />
                  上传单纹理
                </span>
              </UploadTrigger>
              <button
                type="button"
                onClick={startLiveCamera}
                className="inline-flex min-h-11 items-center rounded-[18px] bg-pink-50 px-5 text-sm font-semibold text-[#a34b3f] transition-colors hover:bg-pink-100"
              >
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="camera" className="h-4 w-4" />
                  开启实时摄像头
                </span>
              </button>
            </div>
          </div>

          <div className="mb-3 flex gap-1 rounded-xl bg-pink-50 p-1">
            <button
              onClick={() => setMode("color")}
              className={`flex-1 rounded-lg min-h-11 py-1.5 text-xs transition-[transform,background-color,border-color,box-shadow,color] ${
                mode === "color"
                  ? "bg-[var(--surface)] text-[#ac5145] font-medium shadow-sm"
                  : "text-gray-400"
              }`}
            >
              <span className="inline-flex items-center justify-center gap-1.5"><Icon name="palette" className="h-4 w-4" />纯色</span>
            </button>
            <button
              onClick={() => setMode("texture")}
              className={`flex-1 rounded-lg min-h-11 py-1.5 text-xs transition-[transform,background-color,border-color,box-shadow,color] ${
                mode === "texture"
                  ? "bg-[var(--surface)] text-[#ac5145] font-medium shadow-sm"
                  : "text-gray-400"
              }`}
            >
              <span className="inline-flex items-center justify-center gap-1.5"><Icon name="image" className="h-4 w-4" />纹理</span>
            </button>
          </div>

          {applyFeedback && (
            <div className="mb-3">
              <StatusRegion status="success" message={applyFeedback.message} />
              {applyFeedback.canUndo && (
                <button
                  type="button"
                  onClick={undoLastApply}
                  className="mt-1 inline-flex min-h-11 items-center gap-1 text-xs text-[#a34b3f] underline"
                >
                  <Icon name="undo" className="h-3.5 w-3.5" />
                  撤销本次应用
                </button>
              )}
            </div>
          )}

          {mode === "texture" && textureProfiles[activeFinger] && (
            <div className="mb-3 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-xl bg-pink-50/60 px-3 py-2 text-[11px] text-gray-500">
              <span>
                甲型 {SHAPE_LABELS[textureProfiles[activeFinger]!.shape] ?? textureProfiles[activeFinger]!.shape}
              </span>
              <span>·</span>
              <span>
                图案 {PATTERN_LABELS[textureProfiles[activeFinger]!.pattern] ?? textureProfiles[activeFinger]!.pattern}
              </span>
              <span>·</span>
              <span>光泽 {describeGlossLevel(textureProfiles[activeFinger]!.gloss)}</span>
              {textureProfiles[activeFinger]!.dominantColors.slice(0, 3).map((color) => (
                <span
                  key={color.hex}
                  title={`${color.hex}（占比 ${Math.round(color.ratio * 100)}%）`}
                  className="inline-block h-3 w-3 rounded-full border border-gray-200 align-middle"
                  style={{ backgroundColor: color.hex }}
                />
              ))}
            </div>
          )}

          <div className="mb-4 rounded-2xl border border-pink-100 bg-[var(--surface)] p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-[#67685f]">
                逐指校准 · {FINGER_NAMES[activeFinger]}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => updateActiveNailFit(DEFAULT_NAIL_FIT)}
                  className="-my-2.5 inline-flex min-h-11 items-center px-1 text-[11px] text-[#ac5145] hover:text-[#ac5145]"
                >
                  重置本指
                </button>
                <button
                  type="button"
                  onClick={resetAllNailFits}
                  className="-my-2.5 inline-flex min-h-11 items-center px-1 text-[11px] text-gray-400 hover:text-gray-600"
                >
                  重置全部
                </button>
              </div>
            </div>
            <p className="mb-2 text-[11px] leading-5 text-gray-400">
              请展示手背并张开五指；画布中当前手指以珊瑚描边高亮，拖动滑杆调整长度与宽度。
              已调整 {adjustedFingerCount}/5 指。
            </p>
            <label className="grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">              <span>长度</span>
              <input
                aria-label={`${FINGER_NAMES[activeFinger]}甲面长度`}
                type="range"
                min="75"
                max="140"
                step="1"
                value={Math.round(activeNailFit.lengthScale * 100)}
                onChange={(event) => updateActiveNailFit({
                  lengthScale: Number(event.target.value) / 100,
                })}
                className="h-11 w-full accent-[#ac5145]"
              />
              <span className="text-right">{Math.round(activeNailFit.lengthScale * 100)}%</span>
            </label>
            <label className="mt-2 grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">
              <span>宽度</span>
              <input
                aria-label={`${FINGER_NAMES[activeFinger]}甲面宽度`}
                type="range"
                min="70"
                max="145"
                step="1"
                value={Math.round(activeNailFit.widthScale * 100)}
                onChange={(event) => updateActiveNailFit({
                  widthScale: Number(event.target.value) / 100,
                })}
                className="h-11 w-full accent-[#ac5145]"
              />
              <span className="text-right">{Math.round(activeNailFit.widthScale * 100)}%</span>
            </label>
            <label className="mt-2 grid grid-cols-[42px_1fr_42px] items-center gap-2 text-[11px] text-gray-500">
              <span>位置</span>
              <input
                aria-label="甲面位置"
                type="range"
                min="-20"
                max="20"
                step="1"
                value={Math.round(activeNailFit.rootOffset * 100)}
                onChange={(event) => updateActiveNailFit({
                  rootOffset: Number(event.target.value) / 100,
                })}
                className="h-11 w-full accent-[#ac5145]"
              />
              <span className="text-right">
                {activeNailFit.rootOffset === 0
                  ? "居中"
                  : activeNailFit.rootOffset > 0
                    ? `指根${Math.round(activeNailFit.rootOffset * 100)}`
                    : `甲尖${Math.round(-activeNailFit.rootOffset * 100)}`}
              </span>
            </label>
          </div>

          <div className="mb-3 flex justify-center gap-2">
            {FINGER_NAMES.map((name, index) => (
              <button
                key={index}
                onClick={() => setActiveFinger(index)}
                className={`relative min-h-11 rounded-full px-3 py-1.5 text-xs transition-[transform,background-color,border-color,box-shadow,color] ${
                  activeFinger === index
                    ? "bg-[#ac5145] text-white shadow-sm"
                    : "bg-pink-50 text-gray-400 hover:bg-pink-100"
                }`}
              >
                {name}
                {nailTextures[index] && (
                  <span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full border border-white bg-green-400" />
                )}
              </button>
            ))}
          </div>

          {mode === "texture" && (
            <div className="mb-3 text-center">
              {nailTextures[activeFinger] ? (
                <div className="mb-2 flex items-center justify-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-xl border-2 border-pink-300 bg-pink-50">
                    <TextureThumb bitmap={nailTextures[activeFinger]!} size={48} />
                  </div>
                  <div className="text-left">
                    <p className="text-xs font-medium">{FINGER_NAMES[activeFinger]}纹理</p>
                    <button
                      onClick={() => removeTexture(activeFinger)}
                      className="text-xs text-red-400 hover:text-red-500"
                    >
                      移除
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mb-2 text-xs text-gray-400">
                  {FINGER_NAMES[activeFinger]}暂未设置纹理
                </p>
              )}

              {hasAnyTexture && (
                <button
                  onClick={applyTextureToAll}
                  className="inline-flex min-h-11 items-center rounded-full bg-pink-50 px-3 text-xs text-[#ac5145] transition-colors hover:bg-pink-100"
                >
                  应用到全部
                </button>
              )}
            </div>
          )}

          {mode === "color" && (
            <>
              <div className="mb-3 flex items-center justify-center gap-3">
                <div
                  className="h-8 w-8 rounded-full border-2 border-gray-100 shadow-sm"
                  style={{ backgroundColor: nailColors[activeFinger] }}
                />
                <span className="text-xs text-gray-400">{FINGER_NAMES[activeFinger]}颜色</span>
                <button
                  onClick={applyToAll}
                  className="inline-flex min-h-11 items-center px-1 text-xs text-[#ac5145] underline hover:text-[#ac5145]"
                >
                  应用到全部
                </button>
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                {PRESET_COLORS.filter((_, index) => index < 12).map((item) => (
                  <button
                    key={item.name}
                    title={item.name}
                    onClick={() => changeColor(item.color)}
                    className={`h-11 w-11 rounded-full border-2 shadow-sm transition-[transform,background-color,border-color,box-shadow,color] hover:scale-110 ${
                      nailColors[activeFinger] === item.color
                        ? "scale-110 ring-2 ring-pink-400 ring-offset-2"
                        : ""
                    } ${
                      item.color === "#FFFFFF" || item.name === "透明"
                        ? "border-gray-200"
                        : "border-transparent"
                    }`}
                    style={{ backgroundColor: item.color }}
                  />
                ))}
              </div>

              <div className="mt-3 flex items-center justify-center gap-2">
                <span className="text-xs text-gray-400">自定义</span>
                <input
                  type="color"
                  value={nailColors[activeFinger]}
                  onChange={(e) => changeColor(e.target.value)}
                  className="h-11 w-11 cursor-pointer rounded-full border-0 p-0"
                />
              </div>
            </>
          )}
        </div>
        </aside>
      </div>

        {showCropper && uploadedPhotoUrl && (
          <TextureCropper
            imageUrl={uploadedPhotoUrl}
            onConfirm={handleCropConfirm}
            onCancel={handleCropCancel}
          />
        )}

        {showNailPicker && uploadedPhotoUrl && (
          <NailArtPicker
            imageUrl={uploadedPhotoUrl}
            onConfirm={handlePickingConfirm}
            onCancel={handlePickingCancel}
            suppressAutoFlow={pickerSuppressAuto}
          />
        )}

        {/* §7.2 覆盖前复核界面（渲染在选择器之后，保证同层弹层置顶） */}
        {pendingReview && (
          <ArReviewDialog
            review={pendingReview}
            currentTextures={nailTextures}
            onApply={applyPendingReview}
            onContinue={continueAdjusting}
            onCancel={cancelPendingReview}
          />
        )}

        <div className="mx-auto mt-5 grid w-full max-w-3xl gap-3 text-center sm:grid-cols-2">
          <div className="rounded-2xl bg-[var(--surface)] p-4 text-xs leading-5 text-[#6f7066] "><Icon name="lock" className="mr-1.5 inline h-4 w-4 align-[-3px]" />摄像头画面默认仅在内存中处理，不录制；「用户改进计划」可在隐私页关闭</div>
          <div className="rounded-2xl bg-[var(--surface)] p-4 text-xs leading-5 text-[#6f7066] "><Icon name="lightbulb" className="mr-1.5 inline h-4 w-4 align-[-3px]" />首次加载大约需要 5-10 秒，建议在光线充足的环境使用。</div>
        </div>
    </AppShell>
  );
}

/** §7.2 覆盖前复核界面：摘要文案来自 ar-review-flow 的格式化函数。 */
function ArReviewDialog({
  review,
  currentTextures,
  onApply,
  onContinue,
  onCancel,
}: {
  review: PendingTextureReview;
  currentTextures: (ImageBitmap | null)[];
  onApply: () => void;
  onContinue: () => void;
  onCancel: () => void;
}) {
  const copy = REVIEW_DIALOG_COPY[review.action];
  return (
    <AppDialog
      open
      onClose={onCancel}
      title={copy.title}
      description={copy.description}
      closeOnOutside={false}
      initialFocus={review.action === "confirm" ? "cancel" : "confirm"}
      footer={
        <>
          <button
            type="button"
            data-autofocus="confirm"
            onClick={onApply}
            className={reviewPrimaryButtonClass}
          >
            应用到试戴
          </button>
          <button
            type="button"
            onClick={onContinue}
            className={reviewSecondaryButtonClass}
          >
            继续调整
          </button>
          <button
            type="button"
            data-autofocus="cancel"
            onClick={onCancel}
            className={reviewSecondaryButtonClass}
          >
            取消
          </button>
        </>
      }
    >
      <p
        role="status"
        className="rounded-xl bg-pink-50 px-3 py-2 text-sm text-[#884338]"
      >
        {formatArReviewSummary(review.summary)}
      </p>
      <ul className="mt-3 space-y-2">
        {review.assignments.map((assignment, index) => {
          const needsReview = review.summary.reviewIndices.includes(index);
          const replacesOld = currentTextures[assignment.finger] != null;
          return (
            <li
              key={`${assignment.finger}-${index}`}
              className="flex items-center gap-3 rounded-xl border border-[var(--line)] px-3 py-2"
            >
              <span className="flex h-10 w-10 flex-none items-center justify-center overflow-hidden rounded-lg border border-pink-200 bg-pink-50">
                <TextureThumb bitmap={assignment.texture} size={40} />
              </span>
              <span className="text-sm text-[#292a27]">
                {FINGER_NAMES[assignment.finger] ?? `手指 ${assignment.finger + 1}`}纹理
              </span>
              <span className="ml-auto flex flex-wrap justify-end gap-1.5">
                {replacesOld && (
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
                    替换原纹理
                  </span>
                )}
                {needsReview && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] text-amber-800">
                    建议复核
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </AppDialog>
  );
}

function TextureThumb({
  bitmap,
  size,
}: {
  bitmap: ImageBitmap;
  size: number;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const scale = Math.min(size / bitmap.width, size / bitmap.height);
    const dw = bitmap.width * scale;
    const dh = bitmap.height * scale;
    const dx = (size - dw) / 2;
    const dy = (size - dh) / 2;

    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(bitmap, dx, dy, dw, dh);
  }, [bitmap, size]);

  return (
    <canvas
      ref={ref}
      width={size}
      height={size}
      className="h-full w-full object-contain"
    />
  );
}
