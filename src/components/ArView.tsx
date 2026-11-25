"use client";
import { useRef, useEffect, useState } from "react";
import { dragNailFit, fitHandlePoints, mirroredCanvasPoint, type FitHandle } from "@/lib/ar-fit-drag";
import {
  adjustNailGeometry,
  computeNailGeometry,
  createNailAffineTransform,
  NAIL_DIPS,
  NAIL_PIPS,
  NAIL_TIPS,
  smoothNailGeometry,
  type NailGeometry,
} from "@/lib/nail-geometry";
import { resolveMediaPipeHandsAsset } from "@/lib/mediapipe-hands-assets";
import { createArCameraSession } from "@/lib/ar-camera-session";
import { createBackgroundWatchdog, AR_BACKGROUND_STALL_MS } from "@/lib/ar-background-watchdog";
import { createArWorkerTracker, type ArHandLandmark as Landmark } from "@/lib/ar-hand-tracker";
import { getCoherentPalmTranslation } from "@/lib/ar-palm-translation";
import { createArLightSampler, getArLightCrop, LIGHT_FRAME_HEIGHT, LIGHT_FRAME_TTL_MS, LIGHT_FRAME_WIDTH } from "@/lib/ar-light-sampler";
import {
  startArTrackFrameLoop,
  startArVideoFrameLoop,
  startCapturedArVideoFrameLoop,
  type ArCapturedFrame,
  type ArVideoFrame,
} from "@/lib/ar-video-frame-loop";
import { createArMaterialPainter, getTextureFrame, type ArMaterialParams, type Nail2DContext } from "@/lib/ar-material-painter";
import { createArMaterialJobs } from "@/lib/ar-material-jobs";
import { textureDrawRect, textureLayerSize } from "@/lib/ar-texture-fit";
import { Icon } from "@/components/Icon";
import {
  calculateCoverVideoLayout,
  calculateViewportAspectRatio,
} from "@/lib/ar-video-layout";
import {
  classifyHandOrientation,
  getHandOrientationPresentation,
  isPalmCenterOutOfFrame,
  type HandOrientationDecision,
  type HandOrientation,
} from "@/lib/ar-hand-orientation";
import {
  computeFingerNailOrientation,
  computeHandDorsumNormal,
  fingerJointPoints,
  CURL_GEOMETRY_THRESHOLD,
  type FingerNailOrientation,
  type Vec3,
} from "@/lib/ar-nail-orientation";
import {
  bboxFromLandmarks,
  expandRoi,
  remapLandmarks,
  roiSanity,
  segBootstrapBox,
  type RoiBox,
  type RoiCrop,
} from "@/lib/ar-roi-tracking";
import {
  assignSegSlots,
  shouldScheduleKeyframe,
  updateSegHits,
  type SegFingerHit,
  type TipPoint,
} from "@/lib/ar-seg-keyframe";
import type {
  ArSegKeyframeRequest,
  ArSegKeyframeResponse,
} from "@/lib/nail-texture-recognition/stage-a-coarse";
import {
  computeTextureRenderPlan,
  getNailShapeProfile,
  glossToRenderFactor,
  type NailRenderStyle,
} from "@/lib/ar-nail-shape";

// MediaPipe 手部关键点索引
const TIPS = NAIL_TIPS;
const DIPS = NAIL_DIPS;
const PIPS = NAIL_PIPS;

// 指数移动平均平滑因子
const EMA_ALPHA = 0.66;
const EMA_ALPHA_PALM = 0.3; // 朝向深度差平滑（更保守）

const ORIENTATION_STABLE_FRAMES = 3;

// 逐指指甲可见性阈值
// 手心侧：TIP.z - DIP.z > 此值 = 指甲被遮挡 → 不渲染
const NAIL_PALM_Z_THRESHOLD = 0.002;
// 信号 B 阈值：TIP.z - PIP.z > 此值 → 手心侧（更宽松，用于印证）
const NAIL_PALM_Z_THRESHOLD_B = 0.004;
// 透视缩短比阈值：len2D/len3D < 此值 → 手指指向镜头 → 手心侧
const FORESHORTEN_THRESHOLD = 0.55;
// 可见性状态帧间平滑因子
const VISIBILITY_EMA_ALPHA = 0.3;
// 可见性平滑阈值（< 此值视为不可见）
const VISIBILITY_SMOOTH_THRESHOLD = 0.5;
// 手指伸展角阈值（弧度）：PIP→DIP 与 DIP→TIP 夹角 > 此值 = 弯折 = 指甲不可见
const EXTENSION_ANGLE_THRESHOLD = 0.6; // ≈ 35°

// 手势贴合先验 rollout 开关：默认 off，验收通过后开启（M1）
const GESTURE_PRIOR_ENABLED = process.env.NEXT_PUBLIC_AR_GESTURE_PRIOR === "1";
// ROI 丢手兜底 rollout 开关（M2）
const ROI_TRACKING_ENABLED = process.env.NEXT_PUBLIC_AR_ROI_TRACKING === "1";
// 双手按钮 rollout 开关（M2）：默认单手，用户按钮开启双手
const TWO_HAND_ENABLED = process.env.NEXT_PUBLIC_AR_TWO_HAND === "1";
const SEG_FUSION_ENABLED = process.env.NEXT_PUBLIC_AR_SEG_FUSION === "1";
const SEG_KEYFRAME_INTERVAL_MS = 400;
const SEG_KEYFRAME_MAX_EDGE = 512;
const SEG_ASSOC_RADIUS = 0.06;
const SEG_HOLD_FRAMES = 3;

// 4 指投票索引（排除拇指，拇指结构特殊 z 不稳定）
const VOTE_FINGERS = [1, 2, 3, 4];

const INFERENCE_INTERVAL_MS = 1000 / 24;
const WORKER_OVERLAY_MAX_AGE_MS = 150;

// 环境光采样：整帧缩略一次读取，供五指共享（逐指 getImageData 会触发 GL 同步回读）
const LIGHT_FRAME_PATCH_RADIUS = 2;
const NEUTRAL_ENV_LIGHT = { brightness: 1, r: 1, g: 1, b: 1 };
type LightFrame = { data: Uint8ClampedArray; width: number; height: number };

// 纹理合成层缓存：尺寸容差内的关键点抖动不重建离屏层
// （上屏按当前几何等比缩放，容差只影响纹理重采样锐度，不改变甲面大小）
const NAIL_LAYER_QUANTUM = 2;
const NAIL_LAYER_SIZE_TOLERANCE = 0.15;
const NAIL_LAYER_MIN_REBUILD_MS = 100;
// 环境光亮度差超过该阈值才重建（层内亮度是烘焙结果，读数抖动不触发重绘）
const NAIL_LAYER_LIGHT_TOLERANCE = 0.12;
// 单帧最多重建的合成层数量，避免五指同帧重建造成整帧卡顿
const NAIL_LAYER_REBUILDS_PER_FRAME = 1;

// MediaPipe 全局类型声明（CDN 注入）
interface Handedness {
  label: "Left" | "Right" | null;
  score: number;
}

interface HandResults {
  multiHandLandmarks?: Landmark[][];
  multiHandedness?: Handedness[];
}

interface HandsInstance {
  setOptions: (opts: {
    maxNumHands: number;
    modelComplexity: number;
    minDetectionConfidence: number;
    minTrackingConfidence: number;
  }) => void;
  onResults: (cb: (res: HandResults) => void) => void;
  close: () => void;
  send: (data: { image: HTMLVideoElement }) => Promise<void>;
}

interface HandsConstructor {
  new (config: { locateFile: (f: string) => string }): HandsInstance;
}

// MediaPipe Camera Utils 已弃用，改用原生 getUserMedia + RAF 驱动

declare global {
  interface Window {
    Hands?: HandsConstructor;
  }
}

/** 逐指纹理合成层缓存：签名不变时复用离屏合成结果。 */
interface NailLayerSlot {
  canvas: OffscreenCanvas;
  ctx: OffscreenCanvasRenderingContext2D;
  bitmap?: ImageBitmap;
  preferReadback: boolean;
  signature: string;
  /** 构建时使用的甲面渲染尺寸；上屏按当前尺寸等比缩放，甲面大小始终跟随几何。 */
  drawnWidth: number;
  drawnLength: number;
  /** 构建时烘焙进去的环境光亮度。 */
  drawnBrightness: number;
  /** 上次构建时间（ms），用于限制重建频率。 */
  builtAt: number;
}

interface Props {
  nailColors: string[];
  /** 每指独立纹理（null = 该指使用纯色） */
  nailTextures?: (ImageBitmap | null)[];
  /** 渲染模式：color | texture */
  mode?: "color" | "texture";
  /** 甲面整体缩放，1为校准后的默认尺寸。 */
  nailScale?: number;
  /** 沿甲面长轴移动；正值向指根，单位为默认甲面长度。 */
  nailOffset?: number;
  /** 可选的逐指校准；存在时覆盖对应的全局缩放与偏移。 */
  nailAdjustments?: readonly NailFitAdjustment[];
  /** 可选的逐指甲渲染样式（甲型模板 + 光泽系数）；null/缺省 = 维持 round 历史默认。 */
  nailStyles?: readonly (NailRenderStyle | null)[];
  /** 当前校准中的手指索引（0—4）；开启辅助线时显示该指的甲根位置。 */
  activeFinger?: number | null;
  /** 校准时显示甲根标尺；常规试戴保持关闭。 */
  showFitGuides?: boolean;
  onFitChange?: (finger: number, fit: NailFitAdjustment) => void;
  /** 用户在连续失败覆盖层选择「改用上传照片试色」时回调（摄像头由组件自行停止）。 */
  onSuggestUpload?: () => void;
  /** 摄像头会话就绪/停止时回调（true=会话运行中，false=已停止），用于页面顶部步骤状态。 */
  onCameraActiveChange?: (active: boolean) => void;
  /** 来源选择信号：数值递增时在未启动状态下触发一次摄像头启动流程（§7.1 Step 1「开启实时摄像头」）。 */
  startSignal?: number;
}

export interface NailFitAdjustment {
  lengthScale: number;
  widthScale: number;
  rootOffset: number;
  sideOffset?: number;
  /** 弧度；围绕甲根旋转。 */
  rotationOffset?: number;
}

export function ArView({
  nailColors,
  nailTextures,
  mode = "color",
  nailScale = 1,
  nailOffset = 0,
  nailAdjustments,
  nailStyles,
  activeFinger = null,
  showFitGuides = false,
  onFitChange,
  onSuggestUpload,
  onCameraActiveChange,
  startSignal = 0,
}: Props) {
  const vref = useRef<HTMLVideoElement>(null);
  const cref = useRef<HTMLCanvasElement>(null);
  const colRef = useRef(nailColors);
  const texRef = useRef(nailTextures);
  const modeRef = useRef(mode);
  const nailScaleRef = useRef(nailScale);
  const nailOffsetRef = useRef(nailOffset);
  const nailAdjustmentsRef = useRef(nailAdjustments);
  const nailStylesRef = useRef<readonly (NailRenderStyle | null)[]>([]);
  const activeFingerRef = useRef<number | null>(activeFinger);
  const showFitGuidesRef = useRef(showFitGuides);
  const fitGuideRef = useRef<{ finger: number; raw: NailGeometry; rendered: NailGeometry;
    fit: NailFitAdjustment; time: number } | null>(null);
  const fitDragRef = useRef<{ pointer: number; x: number; y: number; handle: FitHandle;
    guide: NonNullable<typeof fitGuideRef.current> } | null>(null);
  // 「关闭摄像头」按钮桥：teardownToInit 定义在主 effect 闭包内，
  // 通过 ref 暴露给渲染层的按钮与覆盖层调用。
  const teardownRef = useRef<(() => void) | null>(null);
  // 摄像头会话状态回调桥（保持 ref，避免主 effect 因回调身份重建）。
  const cameraActiveChangeRef = useRef(onCameraActiveChange);
  // 来源选择信号去重：同一信号值只消费一次。
  const lastStartSignalRef = useRef(0);
  const [recognitionFailed, setRecognitionFailed] = useState(false);
  const [status, setStatus] = useState("init"); // init|loading|ready|error
  const [statusMsg, setStatusMsg] = useState("初始化…");
  const [handCnt, setHandCnt] = useState(-1); // -1=未检测, 0=无手, N=有手
  const [diag, setDiag] = useState<string[]>([]);
  const [frameAspectRatio, setFrameAspectRatio] = useState(16 / 9);

  // 时序平滑状态：每指存储 smoothedTip/smoothedDip/smoothedPip
  // 用 NaN 标记"未初始化"，首次检测到手指时直接采用原始值
  const smoothRef = useRef<{
    tip: { x: number; y: number; z: number };
    dip: { x: number; y: number; z: number };
    pip: { x: number; y: number; z: number };
  }[]>(
    Array.from({ length: 5 }, () => ({
      tip: { x: NaN, y: NaN, z: NaN },
      dip: { x: NaN, y: NaN, z: NaN },
      pip: { x: NaN, y: NaN, z: NaN },
    }))
  );

  // 朝向检测：平滑后的深度差（palmZ - knuckleZ）
  const palmDepthSmoothRef = useRef<number>(NaN);
  // 逐指可见性平滑状态（5 指，0=不可见, 1=可见）
  const visibleSmoothRef = useRef<number[]>([1, 1, 1, 1, 1]);
  const geometrySmoothRef = useRef<(NailGeometry | null)[]>(
    Array.from({ length: 5 }, () => null)
  );
  // 朝向状态（用于 UI 显示）
  const [orientation, setOrientation] = useState<HandOrientation>("none");
  const orientationRef = useRef<HandOrientation>("none");
  const orientationCandidateRef = useRef<{
    orientation: Exclude<HandOrientation, "none">;
    frames: number;
  }>({ orientation: "ambiguous", frames: 0 });
  // 左右标识（用于 UI 显示）
  const [handLabel, setHandLabel] = useState<"左手" | "右手" | null>(null);
  // UI 状态去抖：逐帧推理结果只在真正变化时写入 React 状态。
  const handCntUiRef = useRef(-1);
  const handLabelUiRef = useRef<"左手" | "右手" | null>(null);
  // 左右手反转开关（用于前置摄像头镜像补偿）
  // 用 useRef 确保 onResults 闭包始终读取最新值
  const [handFlip, setHandFlip] = useState(false);
  const handFlipRef = useRef(false);
  // M2 双手开关（默认单手；flag 开启时显示按钮）
  const [twoHand, setTwoHand] = useState(false);
  const twoHandRef = useRef(false);
  const trackerRef = useRef<HandsInstance | null>(null);
  // M2 ROI 丢手兜底
  const lastHandBboxRef = useRef<RoiBox | null>(null);
  const emptyStreakRef = useRef(0);
  const roiTrackerRef = useRef<HandsInstance | null>(null);
  const roiCropRef = useRef<RoiCrop | null>(null);
  const roiCanvasRef = useRef<HTMLCanvasElement | null>(null);
  // M3 关键帧 Stage-A 分割融合
  const segWorkerRef = useRef<Worker | null>(null);
  const segHitsRef = useRef<Record<number, SegFingerHit>>({});
  const segInstancesRef = useRef<readonly { cx: number; cy: number; w: number; h: number; angle: number; score: number }[]>([]);
  const segTipsRef = useRef<Record<number, TipPoint>>({});
  const segLastKeyframeRef = useRef(0);
  const segBusyRef = useRef(false);
  const segCanvasRef = useRef<HTMLCanvasElement | null>(null);
  // 逐指可见性 UI 状态（true=可见，false=隐藏）
  const [fingerVisible, setFingerVisible] = useState<boolean[]>([true, true, true, true, true]);
  const fingerVisibleUiRef = useRef<boolean[]>([true, true, true, true, true]);
  const [materialPainter] = useState(() => createArMaterialPainter());
  const { drawNailShape, drawPhotoTexture, drawMaterialDetails, drawSpecularHighlight } = materialPainter;
  // 环境光共享缩略帧（每帧至多一次 GL 回读，五指复用同一份像素）
  const lightFrameCanvasRef = useRef<OffscreenCanvas | null>(null);
  const lightFrameCtxRef = useRef<OffscreenCanvasRenderingContext2D | null>(null);
  const lightFrameStateRef = useRef<(LightFrame & {
    viewWidth: number;
    viewHeight: number;
    at: number;
  }) | null>(null);
  // 纹理合成层（纹理 + 材质先在离屏合成，source-atop 限制在纹理 alpha 内，再整体上屏）
  // 按指独立缓存：层内容只取决于纹理、甲面尺寸、光照与光泽，几何位移由画布变换承担，
  // 因此签名不变时可直接复用上一帧的合成结果，省去重绘与逐指像素回读。
  const nailLayerSlotsRef = useRef<Array<NailLayerSlot | null>>([null, null, null, null, null]);
  const materialPipelineRef = useRef<{
    jobs: ReturnType<typeof createArMaterialJobs>;
    epoch: number;
    visible: boolean[];
  } | null>(null);
  const nailLayerTextureIdRef = useRef(new WeakMap<ImageBitmap, number>());
  const nailLayerTextureSeqRef = useRef(0);
  // 单帧合成层重建预算（每次 paintNails 重置）
  const layerRebuildBudgetRef = useRef(0);
  // V7 甲根颜色保护的工作层：绘制 1px/2px 内缩源并读取其 alpha。
  // V7 运行时回退只提示一次，避免逐帧告警刷屏。

  const log = (m: string) => {
    console.log("[AR]", m);
    setDiag((p) => [...p.slice(-8), m]);
  };

  function updateStableOrientation(next: Exclude<HandOrientation, "none">): HandOrientation {
    const candidate = orientationCandidateRef.current;
    if (candidate.orientation === next) {
      candidate.frames += 1;
    } else {
      candidate.orientation = next;
      candidate.frames = 1;
    }

    const requiredFrames = next === "ambiguous" ? ORIENTATION_STABLE_FRAMES + 2 : ORIENTATION_STABLE_FRAMES;
    if (candidate.frames >= requiredFrames && orientationRef.current !== next) {
      orientationRef.current = next;
      setOrientation(next);
    }
    return orientationRef.current;
  }

  /** 指数移动平均平滑（NaN 安全：首次值直接采用） */
  function ema(prev: number, curr: number, alpha: number = EMA_ALPHA): number {
    if (isNaN(prev)) return curr;
    return prev + alpha * (curr - prev);
  }

  /** 纹理实例 id：WeakMap 递增编号，用于合成层签名比较。 */
  function textureLayerId(tex: ImageBitmap): number {
    const ids = nailLayerTextureIdRef.current;
    const existing = ids.get(tex);
    if (existing !== undefined) return existing;
    nailLayerTextureSeqRef.current += 1;
    ids.set(tex, nailLayerTextureSeqRef.current);
    return nailLayerTextureSeqRef.current;
  }

  /** 取逐指合成层（尺寸按 2px 量化复用；返回 null 表示上下文不可用）。 */
  function acquireNailLayerCanvas(
    finger: number,
    width: number,
    height: number,
    preferReadback: boolean,
  ): NailLayerSlot | null {
    const qw = Math.max(1, Math.ceil(width / NAIL_LAYER_QUANTUM) * NAIL_LAYER_QUANTUM);
    const qh = Math.max(1, Math.ceil(height / NAIL_LAYER_QUANTUM) * NAIL_LAYER_QUANTUM);
    const slots = nailLayerSlotsRef.current;
    let slot = slots[finger] ?? null;
    if (!slot || slot.preferReadback !== preferReadback || slot.canvas.width < qw || slot.canvas.height < qh) {
      const canvas = new OffscreenCanvas(qw, qh);
      const ctx = canvas.getContext("2d", preferReadback ? { willReadFrequently: true } : undefined);
      if (!ctx) return null;
      slot?.bitmap?.close();
      slot = { canvas, ctx, preferReadback, signature: "", drawnWidth: 0, drawnLength: 0, drawnBrightness: 0, builtAt: 0 };
      slots[finger] = slot;
    }
    return slot;
  }

  /** 应用长轴与横轴独立的仿射变换，支持侧转甲面的透视剪切。 */
  function applyNailGeometryTransform(
    ctx: Nail2DContext,
    geometry: NailGeometry,
  ) {
    const matrix = createNailAffineTransform(geometry);
    ctx.transform(
      matrix.a,
      matrix.b,
      matrix.c,
      matrix.d,
      matrix.e,
      matrix.f,
    );
  }

  /**
   * 读取环境光共享缩略帧。
   *
   * 逐指调用 getImageData 会让每次采样都等待一次 GL→CPU 同步回读（真机单次约 4ms），
   * 五指叠加即吃掉整帧预算。这里改为把摄影画面按 cover 布局缩略绘制一次，
   * 在时间窗内复用同一份像素，五指只做数组邻域平均。
   */
  function readEnvLightFrame(
    video: HTMLVideoElement,
    w: number,
    h: number,
  ): LightFrame | null {
    const now = performance.now();
    const cached = lightFrameStateRef.current;
    if (
      cached &&
      cached.viewWidth === w &&
      cached.viewHeight === h &&
      now - cached.at < LIGHT_FRAME_TTL_MS
    ) {
      return cached;
    }
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (vw <= 0 || vh <= 0 || w <= 0 || h <= 0) return cached;

    let canvas = lightFrameCanvasRef.current;
    if (!canvas) {
      canvas = new OffscreenCanvas(LIGHT_FRAME_WIDTH, LIGHT_FRAME_HEIGHT);
      lightFrameCanvasRef.current = canvas;
      lightFrameCtxRef.current = null;
    }
    let ctx = lightFrameCtxRef.current;
    if (!ctx) {
      ctx = canvas.getContext("2d", { willReadFrequently: true });
      lightFrameCtxRef.current = ctx;
    }
    if (!ctx) return cached;

    // 与展示层一致的 object-cover 取景，保证缩略像素与画面几何对位。
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    ctx.drawImage(video, ...getArLightCrop(vw, vh, w, h), 0, 0, LIGHT_FRAME_WIDTH, LIGHT_FRAME_HEIGHT);
    const pixels = ctx.getImageData(0, 0, LIGHT_FRAME_WIDTH, LIGHT_FRAME_HEIGHT).data;
    const next = {
      data: pixels,
      width: LIGHT_FRAME_WIDTH,
      height: LIGHT_FRAME_HEIGHT,
      viewWidth: w,
      viewHeight: h,
      at: now,
    };
    lightFrameStateRef.current = next;
    return next;
  }

  /** 在缩略帧上取指甲中心邻域的平均色与感知亮度。 */
  function sampleEnvLight(
    frame: LightFrame,
    cx: number,
    cy: number,
    w: number,
    h: number,
  ): { brightness: number; r: number; g: number; b: number } {
    const px = Math.round((cx / w) * frame.width);
    const py = Math.round((cy / h) * frame.height);
    let sumR = 0, sumG = 0, sumB = 0, count = 0;
    for (let y = py - LIGHT_FRAME_PATCH_RADIUS; y <= py + LIGHT_FRAME_PATCH_RADIUS; y++) {
      if (y < 0 || y >= frame.height) continue;
      for (let x = px - LIGHT_FRAME_PATCH_RADIUS; x <= px + LIGHT_FRAME_PATCH_RADIUS; x++) {
        if (x < 0 || x >= frame.width) continue;
        const i = (y * frame.width + x) * 4;
        sumR += frame.data[i];
        sumG += frame.data[i + 1];
        sumB += frame.data[i + 2];
        count++;
      }
    }
    if (count === 0) return NEUTRAL_ENV_LIGHT;

    const avgR = sumR / count / 255;
    const avgG = sumG / count / 255;
    const avgB = sumB / count / 255;
    // 感知亮度（人眼对绿色最敏感）
    const brightness = avgR * 0.299 + avgG * 0.587 + avgB * 0.114;

    return { brightness, r: avgR, g: avgG, b: avgB };
  }

  /**
   * 手心/手背朝向检测
   *
   * 方案 B（主）：手掌中心 z vs 指关节区 z 的深度差
   * 方案 C（辅）：4 指投票（排除拇指）
   *
   * 返回：是否应该渲染美甲 + 置信度 + 原因
   */
  function shouldRenderNails(
    lm: Landmark[],
    smoothDepthDiff: number,
    handedness: "Left" | "Right" | null,
  ): HandOrientationDecision {
    // 边界检查：仅掌部中心离开可见画面才判出画。
    // 近景整手在画面时手腕贴边不再硬停，逐指显隐由可见性判定自行决定。
    const outOfFrame = isPalmCenterOutOfFrame(lm[5], lm[9], lm[17]);
    if (outOfFrame) {
      return {
        orientation: "ambiguous",
        render: false,
        confidence: "none",
        reason: "手部出画面",
        palmScore: 0,
        dorsumScore: 0,
      };
    }

    const fingerDepthDiffs = VOTE_FINGERS.map(
      (finger) => lm[TIPS[finger]].z - lm[PIPS[finger]].z,
    );
    const wrist = lm[0];
    const indexMcp = lm[5];
    const pinkyMcp = lm[17];
    const palmCrossZ =
      (indexMcp.x - wrist.x) * (pinkyMcp.y - wrist.y) -
      (indexMcp.y - wrist.y) * (pinkyMcp.x - wrist.x);

    return classifyHandOrientation({
      palmDepthDiff: smoothDepthDiff,
      fingerDepthDiffs,
      palmCrossZ,
      handedness,
    });
  }

  /**
   * 计算手指伸展角（PIP→DIP 与 DIP→TIP 在画面上的夹角）
   *
   * 原理：手指伸直时 PIP→DIP 和 DIP→TIP 在同一直线，夹角 ≈ 0°
   *       手指弯折时 DIP→TIP 偏离 PIP→DIP 方向，夹角增大
   *       手指弯折 → 指甲朝下/朝侧 → 不可见
   *
   * 只用 x/y 坐标（MediaPipe 精度最高），不受 z 噪声影响
   *
   * @returns 弧度角 (0 = 完全伸直, PI/2 ≈ 90°弯折)
   */
  function computeFingerExtensionAngle(
    pip: { x: number; y: number },
    dip: { x: number; y: number },
    tip: { x: number; y: number }
  ): number {
    const v1x = dip.x - pip.x;  // 中段指骨 (PIP→DIP)
    const v1y = dip.y - pip.y;
    const v2x = tip.x - dip.x;  // 远端指骨 (DIP→TIP)
    const v2y = tip.y - dip.y;

    const dot = v1x * v2x + v1y * v2y;
    const cross = v1x * v2y - v1y * v2x;
    return Math.abs(Math.atan2(cross, dot));
  }

  /**
   * 四信号融合逐指指甲可见性判定
   *
   * 使用四个独立信号并投票决定手指指甲是否可见：
   *   信号 A — TIP.z vs DIP.z（z 深度差）
   *   信号 B — TIP.z vs PIP.z（不同关节参考，印证 A）
   *   信号 C — 透视缩短比 len2D/len3D（基于 x/y 几何）
   *   信号 D — 手指伸展角 ★（PIP→DIP vs DIP→TIP 夹角，x/y 几何）
   *
   * 信号 D 解决手势兼容问题：比耶/握拳/点赞等非全开手势下，
   *   弯折手指的指甲朝下/朝侧，不应渲染。
   */
  function computeFingerVisibility(
    lm: Landmark[],
    fingerIdx: number,
    s: {
      tip: { x: number; y: number; z: number };
      dip: { x: number; y: number; z: number };
      pip: { x: number; y: number; z: number };
    },
    fo: FingerNailOrientation | null,
  ): boolean {
    // ── 信号 A：TIP.z - DIP.z（使用平滑后的 z 值） ──
    // 手心侧：TIP 比 DIP 更远离镜头 → TIP.z - DIP.z > 0
    // 手背侧：TIP 比 DIP 更接近镜头 → TIP.z - DIP.z < 0 或接近 0
    const tipDipDiff = s.tip.z - s.dip.z;
    const sigA = tipDipDiff <= NAIL_PALM_Z_THRESHOLD;

    // ── 信号 B：TIP.z - PIP.z（印证信号 A，使用不同关节） ──
    // PIP 比 DIP 更靠近指根，受远端弯曲影响更小
    const tipPipDiff = s.tip.z - s.pip.z;
    const sigB = tipPipDiff <= NAIL_PALM_Z_THRESHOLD_B;

    // ── 信号 C：透视缩短比（基于 x/y 几何，精度最高） ──
    // 手背朝镜头：手指与镜头平面平行 → 2D 投影 ≈ 3D 长度 → ratio ≈ 1
    // 手心朝镜头：手指指向镜头 → 2D 投影显著缩短 → ratio < 0.65
    const dx = s.tip.x - s.pip.x;
    const dy = s.tip.y - s.pip.y;
    const dz = s.tip.z - s.pip.z;
    const len2D = Math.sqrt(dx * dx + dy * dy);
    const len3D = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const foreshortenRatio = len3D > 0.0001 ? len2D / len3D : 1;
    const sigC = foreshortenRatio > FORESHORTEN_THRESHOLD;

    // ── 信号 D：手指伸展角（基于 x/y 几何，不受 z 噪声影响）──
    // 新增：解决手势兼容问题（比耶/握拳/点赞等）
    // 弯折的手指指甲朝下或朝侧，不应渲染
    const extensionAngle = computeFingerExtensionAngle(s.pip, s.dip, s.tip);
    const sigD = extensionAngle < EXTENSION_ANGLE_THRESHOLD;

    // ── 多数投票：≥ 2 信号认可 → 可见（4 信号中 2 个通过）──
    const votes = [sigA, sigB, sigC, sigD].filter(Boolean).length;

    // ── 手势先验（M1）：甲板朝镜头即渲染，取代伸展角一票否决 ──
    // 蜷曲但甲面朝镜头（握拳/钩指/掌面回蜷）→ 渲染；
    // 侧缘（edge-on）用旧四信号佐证；甲板背向镜头 → 隐藏。
    if (GESTURE_PRIOR_ENABLED && fo) {
      if (fo.facingCamera) return true;
      if (fo.edgeOn) {
        // M3 分割融合：侧缘且粗分割命中 → 补召回几何先验漏判的甲面。
        if (SEG_FUSION_ENABLED && segHitsRef.current[fingerIdx]?.hit) return true;
        return votes >= 2;
      }
      return false;
    }

    // ── 强否定：四信号全部否定 → 不可见 ──
    if (!sigA && !sigB && !sigC && !sigD) return false;
    return votes >= 2;
  }

  // 分割驱动兜底贴合：掌检测冷启动丢手（握拳等）时，用粗分割甲实例直接放置贴图/纯色。
  function paintSegFallback(
    ctx: CanvasRenderingContext2D,
    instances: readonly { cx: number; cy: number; w: number; h: number; angle: number; score: number }[],
    colors: string[],
    textures: (ImageBitmap | null)[] | undefined,
    currentMode: string,
    vw: number,
    vh: number,
    scale: number,
    tx2px: (n: number) => number,
    ty2py: (n: number) => number,
  ): boolean[] {
    const vis = [false, false, false, false, false];
    for (const { slot, instance } of assignSegSlots(instances)) {
      const pw = instance.w * vw * scale;
      const ph = instance.h * vh * scale;
      if (pw < 4 || ph < 4) continue;
      ctx.save();
      ctx.translate(tx2px(instance.cx), ty2py(instance.cy));
      ctx.rotate(instance.angle);
      ctx.globalAlpha = 0.92;
      const tex = currentMode === "texture" ? textures?.[slot] : null;
      if (tex) {
        ctx.drawImage(tex, -pw / 2, -ph / 2, pw, ph);
      } else {
        ctx.fillStyle = colors[slot] ?? "#f472b6";
        ctx.beginPath();
        ctx.roundRect(-pw / 2, -ph / 2, pw, ph, Math.min(pw, ph) * 0.3);
        ctx.fill();
      }
      ctx.restore();
      vis[slot] = true;
    }
    return vis;
  }

  // 指甲绘制函数
  function paintNails(
    ctx: CanvasRenderingContext2D,
    lm: Landmark[],
    colors: string[],
    textures: (ImageBitmap | null)[] | undefined,
    currentMode: string,
    w: number,
    h: number,
    lightFrame: LightFrame | null,
    zScale: number,
    dorsumNormal: Vec3 | null,
    visibilityScores: number[],
    preferLayerReadback: boolean,
    translation?: { x: number; y: number },
  ) {
    // 合成层重建预算：单帧最多重建一指，把像素回读尖峰摊到后续帧，
    // 未重建的指继续用旧层按时序缩放上屏（甲面大小保持正确）。
    layerRebuildBudgetRef.current = NAIL_LAYER_REBUILDS_PER_FRAME;
    const materialPipeline = preferLayerReadback ? materialPipelineRef.current : null;
    materialPipeline?.visible.fill(false);
    for (let f = 0; f < 5; f++) {
      const rawTip = lm[TIPS[f]];
      const rawDip = lm[DIPS[f]];
      const rawPip = lm[PIPS[f]];
      const color = colors[f] || "#E8A0BF";
      if (!rawTip || !rawDip) continue;

      // ── 时序平滑（先平滑关键点，再用平滑值做可见性判定）──
      const s = smoothRef.current[f];
      if (translation) {
        for (const point of [s.tip, s.dip, s.pip]) {
          point.x += translation.x / w;
          point.y += translation.y / h;
        }
      }
      s.tip.x = ema(s.tip.x, rawTip.x);
      s.tip.y = ema(s.tip.y, rawTip.y);
      s.tip.z = ema(s.tip.z, rawTip.z);
      s.dip.x = ema(s.dip.x, rawDip.x);
      s.dip.y = ema(s.dip.y, rawDip.y);
      s.dip.z = ema(s.dip.z, rawDip.z);
      if (rawPip) {
        s.pip.x = ema(s.pip.x, rawPip.x);
        s.pip.y = ema(s.pip.y, rawPip.y);
        s.pip.z = ema(s.pip.z, rawPip.z);
      }

      // ── 四信号融合可见性判定（使用平滑后的值）──
      // 手心侧的手指不贴图；逐指独立判定支持混合态
      const fo = GESTURE_PRIOR_ENABLED && dorsumNormal
        ? computeFingerNailOrientation(fingerJointPoints(lm, f, s), dorsumNormal, zScale)
        : null;
      const rawVis = computeFingerVisibility(lm, f, s, fo);
      visibilityScores[f] = ema(
        visibilityScores[f],
        rawVis ? 1 : 0,
        VISIBILITY_EMA_ALPHA
      );
      if (visibilityScores[f] < VISIBILITY_SMOOTH_THRESHOLD) continue;

      // ── 共享几何模型 + 几何级时序平滑 ──
      const geometryLandmarks = [...lm];
      geometryLandmarks[TIPS[f]] = s.tip;
      geometryLandmarks[DIPS[f]] = s.dip;
      if (rawPip) geometryLandmarks[PIPS[f]] = s.pip;
      const rawGeometry = computeNailGeometry(
        geometryLandmarks,
        f,
        w,
        h,
        {
          zScale,
          ...(fo && fo.curl > CURL_GEOMETRY_THRESHOLD
            ? { curled: { curl: fo.curl, facingFactor: Math.abs(fo.nailNormal.z) } }
            : {}),
        },
      );
      if (!rawGeometry) continue;
      const fingerAdjustment = nailAdjustmentsRef.current?.[f];
      const measured = adjustNailGeometry(
        rawGeometry,
        fingerAdjustment?.lengthScale ?? nailScaleRef.current,
        fingerAdjustment?.rootOffset ?? nailOffsetRef.current,
        fingerAdjustment?.widthScale ?? nailScaleRef.current,
        fingerAdjustment?.sideOffset ?? 0,
        fingerAdjustment?.rotationOffset ?? 0,
      );

      const previousGeometry = geometrySmoothRef.current[f];
      const previous = translation && previousGeometry ? {
        ...previousGeometry,
        cx: previousGeometry.cx + translation.x,
        cy: previousGeometry.cy + translation.y,
      } : previousGeometry;
      const movement = previous
        ? Math.hypot(measured.cx - previous.cx, measured.cy - previous.cy)
        : Number.POSITIVE_INFINITY;
      const alpha = movement > measured.width * 0.22 ? 0.82 : 0.55;
      const geometry = previous
        ? smoothNailGeometry(previous, measured, alpha)
        : measured;
      geometrySmoothRef.current[f] = geometry;

      const { cx, cy, length: nl, width: nw } = geometry;

      // ── 逐指甲渲染样式（甲型模板 + 光泽系数）──
      // 未配置 nailStyles 时为 null → round 历史参数、gloss 系数 1，渲染与旧版一致
      const style = nailStylesRef.current?.[f] ?? null;
      const shapeProfile = getNailShapeProfile(style?.shape ?? null, f);
      const glossFactor = glossToRenderFactor(style?.gloss ?? null);

      // ── 环境光照采样（共享缩略帧邻域均值）──
      const env = lightFrame
        ? sampleEnvLight(lightFrame, cx, cy, w, h)
        : NEUTRAL_ENV_LIGHT;

      // ── 纹理模式渲染计划：长宽比保真（原封不动贴回）──
      // 宽度对齐真实甲面（含宽度滑杆），渲染长度 = 宽度 × 纹理自身长宽比，
      // 甲根边缘锚定在估算甲面的甲根边缘，延长部分向甲尖自然伸出。
      const tex = currentMode === "texture" ? textures?.[f] : null;
      const frame = tex ? getTextureFrame(tex) : null;
      const alphaShaped = frame?.shaped ?? false;
      let renderGeometry = geometry;
      let renderLength = nl;
      if (tex && frame && tex.width > 0 && tex.height > 0) {
        const plan = computeTextureRenderPlan(geometry, frame.height / frame.bodyWidth, 3,
          fingerAdjustment?.lengthScale ?? nailScaleRef.current,
          fingerAdjustment?.widthScale ?? nailScaleRef.current);
        renderLength = plan.length;
        renderGeometry = { ...geometry, cx: plan.cx, cy: plan.cy, length: plan.length };
      }

      const layerSize = tex && frame && alphaShaped
        ? textureLayerSize(textureDrawRect(frame, tex.width, tex.height, nw, renderLength), nw, renderLength)
        : null;
      const layer = layerSize
        ? acquireNailLayerCanvas(f, layerSize.width, layerSize.height, preferLayerReadback)
        : null;

      if (tex && frame && alphaShaped && layer) {
        if (materialPipeline) materialPipeline.visible[f] = true;
        // 自带 alpha 轮廓的提取产物：纹理 + 材质在离屏合成，
        // source-atop 把材质层限制在纹理 alpha 内（不越出提取轮廓），
        // 再按延长后的渲染几何整体上屏。
        const { canvas: layerCanvas, ctx: lctx } = layer;
        // 合成层内容只依赖纹理、甲面档位尺寸、光照与光泽；位移与旋转由画布变换承担。
        // 命中缓存时复用上一帧结果，省掉重绘与逐指像素回读（真机单帧约 20ms）。
        const layerSignature = [
          textureLayerId(tex),
          f,
          Math.round(glossFactor * 10),
          style?.shape ?? "",
        ].join("|");

        const nowMs = performance.now();
        const layerReady = layer.drawnWidth > 0 && layer.drawnLength > 0 &&
          (!materialPipeline || layer.signature === layerSignature);
        // 尺寸只在相对变化超过容差时重建：上屏会按当前几何等比缩放，
        // 容差内的尺寸差不会体现为甲面大小偏差，只影响纹理重采样锐度。
        const sizeDelta = layerReady
          ? Math.max(
              Math.abs(nw - layer.drawnWidth) / Math.max(1, layer.drawnWidth),
              Math.abs(renderLength - layer.drawnLength) / Math.max(1, layer.drawnLength),
            )
          : 1;
        // 环境光只在亮度差超过阈值时重建：层内亮度是烘焙结果，读数抖动不触发重绘。
        const lightDelta = layerReady ? Math.abs(env.brightness - layer.drawnBrightness) : 1;
        const rebuildWanted =
          !layerReady ||
          ((layer.signature !== layerSignature ||
            sizeDelta >= NAIL_LAYER_SIZE_TOLERANCE ||
            lightDelta >= NAIL_LAYER_LIGHT_TOLERANCE) &&
            nowMs - layer.builtAt >= NAIL_LAYER_MIN_REBUILD_MS);
        // 单帧重建预算：把像素回读尖峰摊到后续帧，未重建的指继续用旧层缩放上屏。
        const rebuildDue = rebuildWanted && (layerRebuildBudgetRef.current > 0 || !layerReady);

        if (rebuildDue) {
          const material: ArMaterialParams = {
            width: nw, length: renderLength, brightness: env.brightness, finger: f,
            gloss: glossFactor, shape: shapeProfile, geometry: renderGeometry,
            pixelRatio: window.devicePixelRatio || 1, preferReadback: preferLayerReadback,
          };
          const commit = (bitmap?: ImageBitmap) => {
            layer.bitmap?.close();
            layer.bitmap = bitmap;
            layer.signature = layerSignature;
            layer.drawnWidth = nw;
            layer.drawnLength = renderLength;
            layer.drawnBrightness = env.brightness;
            layer.builtAt = performance.now();
          };
          if (materialPipeline && !materialPipeline.jobs.closed && layerReady) {
            const epoch = materialPipeline.epoch;
            const liveTextureIds = (textures ?? []).flatMap(texture => texture ? [textureLayerId(texture)] : []);
            const accepted = materialPipeline.jobs.submit(tex, {
              textureId: textureLayerId(tex),
              canvasWidth: layerCanvas.width,
              canvasHeight: layerCanvas.height,
              material,
            }, liveTextureIds, result => {
              if ("error" in result) {
                console.warn("[AR] 材质 Worker 回退到主线程", result.error);
                return;
              }
              if (materialPipelineRef.current !== materialPipeline ||
                  materialPipeline.epoch !== epoch || !materialPipeline.visible[f] ||
                  modeRef.current !== "texture" || texRef.current?.[f] !== tex ||
                  (nailStylesRef.current?.[f] ?? null) !== style ||
                  nailLayerSlotsRef.current[f] !== layer || layer.signature !== layerSignature) {
                result.bitmap.close();
                return;
              }
              commit(result.bitmap);
            });
            if (accepted) layerRebuildBudgetRef.current -= 1;
          } else {
            layerRebuildBudgetRef.current -= 1;
            materialPainter.buildLayer(lctx, layerCanvas, tex, material);
            commit();
          }
        }

        // 缓存层按构建时的档位尺寸绘制；上屏时按当前尺寸等比缩放，
        // 甲面大小始终跟随几何，档位差不会变成尺寸偏差。
        const drawW = layer.drawnWidth > 0 ? (layerCanvas.width * nw) / layer.drawnWidth : layerCanvas.width;
        const drawH = layer.drawnLength > 0 ? (layerCanvas.height * renderLength) / layer.drawnLength : layerCanvas.height;
        ctx.save();
        applyNailGeometryTransform(ctx, renderGeometry);
        ctx.drawImage(layer.bitmap ?? layerCanvas, -drawW * 0.5, -drawH * 0.5, drawW, drawH);
        ctx.restore();
      } else {
        // ── 第一层：底色/纹理（连续采样）──
        ctx.save();
        applyNailGeometryTransform(ctx, renderGeometry);

        if (tex) {
          // 纹理模式（不透明位图或合成层不可用）：贝塞尔形状裁剪 + 连续摄影纹理采样
          drawNailShape(ctx, renderLength, nw, f, shapeProfile);
          ctx.clip();
          drawPhotoTexture(ctx, tex, renderLength, nw);
        } else {
          // 纯色模式：填充指甲形状（使用逐指形状参数）
          drawNailShape(ctx, nl, nw, f, shapeProfile);
          ctx.fillStyle = color;
          ctx.globalAlpha = 0.85;
          ctx.fill();
        }

        ctx.restore();

        // ── 第二层：材质细节（菲涅尔 + 颗粒 + 暗角）──
        ctx.save();
        applyNailGeometryTransform(ctx, renderGeometry);
        drawMaterialDetails(ctx, renderLength, nw, env.brightness, f, glossFactor * (tex ? .12 : 1), shapeProfile);
        ctx.restore();

        // ── 第三层：镜面高光 ──
        ctx.save();
        applyNailGeometryTransform(ctx, renderGeometry);
        drawSpecularHighlight(ctx, renderLength, nw, env.brightness, f, glossFactor * (tex ? .12 : 1), shapeProfile);
        ctx.restore();
      }

      // ── 当前校准指甲根标尺（仅用户开启时显示）──
      if (showFitGuidesRef.current && f === activeFingerRef.current) {
        fitGuideRef.current = { finger: f, raw: rawGeometry, rendered: renderGeometry,
          fit: { lengthScale: fingerAdjustment?.lengthScale ?? nailScaleRef.current,
            widthScale: fingerAdjustment?.widthScale ?? nailScaleRef.current,
            rootOffset: fingerAdjustment?.rootOffset ?? nailOffsetRef.current,
            sideOffset: fingerAdjustment?.sideOffset ?? 0, rotationOffset: fingerAdjustment?.rotationOffset ?? 0 },
          time: performance.now() };
        ctx.save();
        applyNailGeometryTransform(ctx, renderGeometry);
        ctx.beginPath();
        ctx.moveTo(-nw / 2, (tex ? renderLength : nl) / 2);
        ctx.lineTo(nw / 2, (tex ? renderLength : nl) / 2);
        ctx.lineWidth = Math.max(2, nw * 0.08);
        ctx.strokeStyle = "#ff8a73";
        ctx.stroke();
        ctx.restore();
        const handles = fitHandlePoints(renderGeometry);
        ctx.save();
        ctx.fillStyle = "#ff8a73";
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        for (const p of Object.values(handles)) {
          ctx.beginPath(); ctx.arc(p.x, p.y, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
        ctx.restore();
      }
    }
  }

  useEffect(() => {
    // 同步 nailColors 到 ref（在 effect 内更新 ref 是安全的）
    colRef.current = nailColors;
  }, [nailColors]);

  // 自动启动改为手动启动（移动端需要用户手势触发摄像头权限）
  const [userStarted, setUserStarted] = useState(false);
  const startBtnRef = useRef<HTMLButtonElement>(null);

  const handleStartCamera = () => {
    console.log("[AR] Start button clicked");
    setStatus("loading");
    setStatusMsg("正在准备摄像头…");
    setDiag([]);
    setRecognitionFailed(false);
    setUserStarted(true);
  };

  const resetCameraStart = () => {
    setStatus("init");
    setStatusMsg("请点击按钮启动摄像头");
    setHandCnt(-1);
    setDiag([]);
    setRecognitionFailed(false);
    setUserStarted(false);
  };

  // 用原生 DOM 事件启动，绕过 React 合成事件在移动端可能的延迟/不触发问题
  useEffect(() => {
    const btn = startBtnRef.current;
    if (!btn) return;
    const handler = (e: Event) => {
      e.preventDefault();
      e.stopPropagation();
      console.log("[AR] Start button clicked via native event");
      setUserStarted(true);
    };
    btn.addEventListener("click", handler);
    btn.addEventListener("touchend", handler, { passive: false });
    return () => {
      btn.removeEventListener("click", handler);
      btn.removeEventListener("touchend", handler);
    };
  }, []);

  useEffect(() => {
    texRef.current = nailTextures;
  }, [nailTextures]);

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    nailScaleRef.current = nailScale;
  }, [nailScale]);

  useEffect(() => {
    nailOffsetRef.current = nailOffset;
  }, [nailOffset]);

  useEffect(() => {
    nailAdjustmentsRef.current = nailAdjustments;
  }, [nailAdjustments]);

  useEffect(() => {
    nailStylesRef.current = nailStyles ?? [];
  }, [nailStyles]);

  useEffect(() => {
    showFitGuidesRef.current = showFitGuides;
  }, [showFitGuides]);

  useEffect(() => {
    activeFingerRef.current = activeFinger ?? null;
  }, [activeFinger]);

  useEffect(() => {
    cameraActiveChangeRef.current = onCameraActiveChange;
  }, [onCameraActiveChange]);

  // §7.1 Step 1「开启实时摄像头」：页面来源卡片递增 startSignal 时代为触发一次启动。
  // userStarted 刻意不进依赖：信号只在未启动状态下消费，启动中的重复信号忽略。
  // 启动经微任务触发：effect 同步路径不调用含 setState 的启动函数。
  useEffect(() => {
    if (startSignal <= 0) return;
    if (lastStartSignalRef.current === startSignal) return;
    lastStartSignalRef.current = startSignal;
    if (!userStarted) queueMicrotask(() => handleStartCamera());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startSignal]);

  useEffect(() => {
    const viewport = window.visualViewport;
    const updateFrameRatio = () => {
      const width = viewport?.width ?? window.innerWidth;
      const height = viewport?.height ?? window.innerHeight;
      if (width <= 0 || height <= 0) return;

      const nextRatio = calculateViewportAspectRatio(width, height);
      setFrameAspectRatio((current) =>
        Math.abs(current - nextRatio) < 0.001 ? current : nextRatio,
      );
    };

    updateFrameRatio();
    window.addEventListener("resize", updateFrameRatio);
    window.addEventListener("orientationchange", updateFrameRatio);
    viewport?.addEventListener("resize", updateFrameRatio);

    return () => {
      window.removeEventListener("resize", updateFrameRatio);
      window.removeEventListener("orientationchange", updateFrameRatio);
      viewport?.removeEventListener("resize", updateFrameRatio);
    };
  }, []);

  useEffect(() => {
    if (!userStarted) return; // 等待用户点击按钮
    const videoElement = vref.current;
    if (!videoElement) return;
    const video = videoElement;
    const session = createArCameraSession(video);
    const { signal } = session;
    const probeParameters = process.env.NODE_ENV === "development" && window.location.hostname === "localhost"
      ? new URLSearchParams(window.location.search)
      : undefined;
    const traceFrame = probeParameters?.get("arTrace") === "1";
    const useWorkerCandidate = process.env.NEXT_PUBLIC_AR_WORKER_CANDIDATE === "1";
    const useWorkerTracking = useWorkerCandidate || probeParameters?.get("arTracker") === "worker";
    const splitPalmMotion = probeParameters?.get("arPose") === "translation";
    const preferLayerReadback = useWorkerCandidate || probeParameters?.get("arLayers") === "readback";
    let previousPalmFrame: {
      points: { x: number; y: number }[];
      mediaTime: number;
      layout: string;
      hand: Handedness["label"];
    } | undefined;
    let lightSampler: ReturnType<typeof createArLightSampler> | undefined;
    function closeMaterialPipeline() {
      materialPipelineRef.current?.jobs.close();
      materialPipelineRef.current = null;
      for (const layer of nailLayerSlotsRef.current) {
        if (!layer?.bitmap) continue;
        layer.bitmap.close();
        layer.bitmap = undefined;
        layer.drawnWidth = 0;
      }
    }
    const canvas = cref.current;
    let workerOverlayPainted = false;
    // 首个有效姿态直接建立逐指可见性，连续姿态才使用迟滞。
    const workerVisibilityScores = Array<number>(5).fill(NaN);
    session.own(() => {
      closeMaterialPipeline();
      fitGuideRef.current = null;
      fitDragRef.current = null;
      if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    });

    function resetTrackingGeometry() {
      previousPalmFrame = undefined;
      const materialPipeline = materialPipelineRef.current;
      if (materialPipeline) {
        materialPipeline.epoch++;
        materialPipeline.visible.fill(false);
      }
      workerVisibilityScores.fill(NaN);
      palmDepthSmoothRef.current = NaN;
      geometrySmoothRef.current = Array.from({ length: 5 }, () => null);
      smoothRef.current = Array.from({ length: 5 }, () => ({
        tip: { x: NaN, y: NaN, z: NaN },
        dip: { x: NaN, y: NaN, z: NaN },
        pip: { x: NaN, y: NaN, z: NaN },
      }));
      fitGuideRef.current = null;
      fitDragRef.current = null;
    }

    // 用户离开当前画面（切换标签页/应用、最小化窗口、离开站点）时立即停用摄像头，
    // 与“画面仅在内存中处理”的隐私约定一致；返回页面后需重新点击开启。
    function teardownToInit() {
      session.close();
      cameraActiveChangeRef.current?.(false);
      setStatus("init");
      setStatusMsg("请点击按钮启动摄像头");
      handCntUiRef.current = -1;
      handLabelUiRef.current = null;
      setHandCnt(-1);
      setHandLabel(null);
      setOrientation("none");
      setDiag([]);
      setRecognitionFailed(false);
      orientationRef.current = "none";
      orientationCandidateRef.current = { orientation: "ambiguous", frames: 0 };
      resetTrackingGeometry();
      updateFingerVisibility([false, false, false, false, false]);
      setUserStarted(false);
    }
    // 暴露给渲染层「关闭摄像头」按钮；effect 重启时覆盖，卸载时清理。
    teardownRef.current = teardownToInit;

    function handleVisibilityChange() {
      if (document.visibilityState === "hidden") teardownToInit();
    }

    function handlePageHide() {
      teardownToInit();
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pagehide", handlePageHide);
    // 兜底：部分安卓浏览器切后台不派发 visibilitychange（页面仍报告 visible、
    // 定时器照常），但视频帧呈现停摆、跟踪冻结；距最近一次跟踪结果超过阈值时
    // 同样立即停用摄像头。
    let lastFrameActivity = performance.now();
    let hadFrameActivity = false;
    const stopBackgroundWatchdog = createBackgroundWatchdog({
      onStall: teardownToInit,
      lastActivity: () => lastFrameActivity,
    });
    session.own(() => {
      stopBackgroundWatchdog();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", handlePageHide);
    });

    function updateFingerVisibility(next: boolean[]) {
      const current = fingerVisibleUiRef.current;
      if (current.length === next.length && current.every((value, index) => value === next[index])) {
        return;
      }
      fingerVisibleUiRef.current = next;
      setFingerVisible(next);
    }

    function failSession(error: unknown) {
      if (signal.aborted) return;
      const message = error instanceof Error ? error.message : String(error);
      log("× " + message);
      session.close();
      cameraActiveChangeRef.current?.(false);
      setStatus("error");
      setStatusMsg(message.includes("permission") || message.includes("权限") ? "摄像头权限被拒绝" : message.slice(0, 60));
    }

    async function start() {
      try {
        // ── 步骤0: 检查浏览器能力 ──
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setStatus("error");
          setStatusMsg("浏览器不支持摄像头 API，请使用 Chrome 或 Safari");
          log("× navigator.mediaDevices 不可用");
          return;
        }
        if (!window.isSecureContext) {
          setStatus("error");
          setStatusMsg("摄像头需要 localhost 或 HTTPS 环境，请使用 http://localhost:3000/ar-tryon 打开");
          log("× 当前页面不是安全上下文");
          return;
        }
        try {
          const permission = await navigator.permissions?.query?.({ name: "camera" as PermissionName });
          if (signal.aborted) return;
          if (permission?.state === "denied") {
            setStatus("error");
            setStatusMsg("摄像头权限被拒绝；请在地址栏权限图标中允许后刷新。");
            log("× 浏览器摄像头权限状态为 denied");
            return;
          }
        } catch {
          // Safari/部分浏览器不支持 camera permission query，继续走 getUserMedia。
        }
        if (signal.aborted) return;

        setStatus("loading");

        // ── 步骤1: 先请求摄像头权限 ──
        // 必须先于 MediaPipe CDN 加载请求，否则网络慢时会表现为“点了按钮但摄像头没反应”。
        setStatusMsg("请求摄像头权限…");
        log("1/7 请求摄像头权限...");

        // 优先获取高清标准比例画面；比例不一致时由展示层等比缩放并居中裁切。
        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              facingMode: { ideal: "user" },
              width: { ideal: 1920 },
              height: { ideal: 1080 },
              frameRate: { ideal: 30, max: 30 },
            },
            audio: false,
          });
        } catch (camErr) {
          if (signal.aborted) return;
          // 降级：不指定 facingMode
          log("  首次尝试失败，降级尝试..." + (camErr instanceof Error ? ": " + camErr.message : ""));
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                frameRate: { ideal: 30, max: 30 },
              },
              audio: false,
            });
          } catch (camErr2) {
            if (signal.aborted) return;
            // 再降级：完全无约束
            log("  二次降级尝试..." + (camErr2 instanceof Error ? ": " + camErr2.message : ""));
            try {
              stream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: false,
              });
            } catch (camErr3) {
              if (signal.aborted) return;
              const msg = camErr3 instanceof Error ? camErr3.message : String(camErr3);
              log("× 摄像头获取失败: " + msg);
              setStatus("error");
              if (msg.includes("Permission") || msg.includes("permission") || msg.includes("denied") || msg.includes("NotAllowed")) {
                setStatusMsg("摄像头权限被拒绝；请在浏览器设置中允许后重试");
              } else if (msg.includes("NotFound") || msg.includes("device")) {
                setStatusMsg("未找到摄像头设备");
              } else if (msg.includes("NotReadable") || msg.includes("busy")) {
                setStatusMsg("摄像头被占用，请关闭后重试");
              } else {
                setStatusMsg("摄像头不可用: " + msg.slice(0, 50));
              }
              return;
            }
          }
        }
        session.attachStream(stream);
        log("  摄像头获取成功 √");

        log("  等待视频就绪...");
        await session.waitForVideo("loadedmetadata", 1, 10000);
        if (signal.aborted) return;
        log("  视频就绪 " + video.videoWidth + "x" + video.videoHeight + " √");
        await video.play().catch((e) => {
          if (!signal.aborted) log("  ! video.play() 警告: " + (e instanceof Error ? e.message : String(e)));
        });
        // 额外等待一帧确保 video 真正开始播放
        await session.waitForVideo("canplay", 3, 2000, true);
        if (signal.aborted) return;
        log("  视频播放中 readyState=" + video.readyState + " √");

        // camera_utils.js 不再需要（改用原生 getUserMedia + RAF）
        // ── 步骤4: 摄像头成功后再加载 MediaPipe ──
        setStatusMsg("摄像头已启动，正在加载手部识别…");

        const scriptTimeout = 15000;
        function loadScript(src: string, name: string): Promise<void> {
          return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = src;
            script.crossOrigin = "anonymous";
            function cleanup() {
              clearTimeout(timer);
              script.onload = null;
              script.onerror = null;
              signal.removeEventListener("abort", abort);
            }
            function fail(error: unknown) {
              cleanup();
              script.remove();
              reject(error);
            }
            function abort() {
              fail(signal.reason);
            }
            const timer = setTimeout(() => fail(new Error(name + " 加载超时（15s），请检查网络")), scriptTimeout);
            script.onload = () => {
              cleanup();
              log("  " + name + " 加载完成 √");
              resolve();
            };
            script.onerror = () => fail(new Error(name + " 加载失败，可能是网络问题"));
            signal.addEventListener("abort", abort, { once: true });
            document.head.appendChild(script);
          });
        }

        async function loadLegacyTracker() {
          if (!window.Hands) await loadScript(resolveMediaPipeHandsAsset("hands.js"), "hands.js");
          if (signal.aborted) throw signal.reason;
          if (!window.Hands) throw new Error("手部识别模块加载失败，请检查网络后重试。");
          setStatusMsg("初始化手部识别…");
          const tracker = new window.Hands({ locateFile: resolveMediaPipeHandsAsset });
          session.own(() => tracker.close());
          tracker.setOptions({
            maxNumHands: twoHandRef.current ? 2 : 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5,
          });
          return tracker;
        }

        function applyResults(res: HandResults, frame?: ArVideoFrame) {
          if (signal.aborted) return;
          const activityNow = performance.now();
          // 后台期间定时器若被节流，看门狗 tick 可能迟于恢复；首帧恢复时
          // 活动间隔已超阈值同样立即停用，避免用陈旧会话继续贴图。
          if (hadFrameActivity && activityNow - lastFrameActivity > AR_BACKGROUND_STALL_MS) {
            teardownToInit();
            return;
          }
          hadFrameActivity = true;
          lastFrameActivity = activityNow;
          const cvs = cref.current;
          if (!cvs) return;
          const ctx = cvs.getContext("2d") as CanvasRenderingContext2D;
          if (!ctx) return;
          // canvas 内部尺寸与 video 元素的 CSS 显示尺寸对齐
          // (不是 video.videoWidth/videoHeight，因为 object-cover 会裁剪视频)
          const rect = video.getBoundingClientRect();
          const cw = Math.round(rect.width);
          const ch = Math.round(rect.height);
          if (cw > 0 && ch > 0 && (cvs.width !== cw || cvs.height !== ch)) {
            cvs.width = cw;
            cvs.height = ch;
          }
          if (!frame || workerOverlayPainted) ctx.clearRect(0, 0, cvs.width, cvs.height);
          const replacedWorkerOverlay = workerOverlayPainted;
          workerOverlayPainted = false;

          // ── object-cover 坐标变换 ──
          // video 元素用 object-cover 显示，会裁剪视频以填充容器
          // landmarks 是基于原始视频帧的归一化坐标 [0,1]
          // 需要变换到 canvas 显示坐标
          const vw = frame?.width ?? video.videoWidth;
          const vh = frame?.height ?? video.videoHeight;
          if (vw <= 0 || vh <= 0 || cvs.width <= 0 || cvs.height <= 0) return;
          const { scale, offsetX, offsetY } = calculateCoverVideoLayout(
            vw,
            vh,
            cvs.width,
            cvs.height,
          );
          // 变换函数：归一化坐标 → canvas 像素坐标
          const tx2px = (nx: number) => nx * vw * scale + offsetX;
          const ty2py = (ny: number) => ny * vh * scale + offsetY;

          if (res.multiHandLandmarks?.length) {
            emptyStreakRef.current = 0;
            lastHandBboxRef.current = bboxFromLandmarks(res.multiHandLandmarks[0]) ?? lastHandBboxRef.current;
            if (SEG_FUSION_ENABLED) {
              const tips: Record<number, TipPoint> = {};
              const hand0 = res.multiHandLandmarks[0];
              for (const fi of VOTE_FINGERS) tips[fi] = { x: hand0[fi * 4 + 3].x, y: hand0[fi * 4 + 3].y };
              segTipsRef.current = tips;
            }
            // 只在数值变化时触发 React 更新，避免逐帧重渲染整棵页面树。
            if (handCntUiRef.current !== res.multiHandLandmarks.length) {
              handCntUiRef.current = res.multiHandLandmarks.length;
              setHandCnt(res.multiHandLandmarks.length);
            }
            for (let h = 0; h < res.multiHandLandmarks.length; h++) {
              const lmRaw = res.multiHandLandmarks[h];
              const rawHandedness: "Left" | "Right" | null =
                res.multiHandedness?.[h]?.label ?? null;

              // 有效 handedness：根据 handFlip 开关决定是否反转
              // 前置摄像头镜像差异导致部分设备 handedness 与实际相反
              // 使用 ref 确保 onResults 闭包始终读取最新 flip 状态
              const effectiveHandedness: "Left" | "Right" | null = handFlipRef.current
                ? (rawHandedness === "Left" ? "Right" : rawHandedness === "Right" ? "Left" : null)
                : rawHandedness;

              // 同步左右手标识到 UI（使用有效 handedness；仅在变化时触发渲染）
              const nextHandLabel: "左手" | "右手" | null =
                effectiveHandedness === "Right" ? "右手" : effectiveHandedness === "Left" ? "左手" : null;
              if (handLabelUiRef.current !== nextHandLabel) {
                handLabelUiRef.current = nextHandLabel;
                setHandLabel(nextHandLabel);
              }

              // 变换 landmarks 到 canvas 坐标系
              const lm = lmRaw.map((p: { x: number; y: number; z: number }) => ({
                x: tx2px(p.x) / cvs.width,  // 重新归一化
                y: ty2py(p.y) / cvs.height,
                z: p.z,
              })) as Landmark[];

              // 全局朝向检测（4 传感器融合判定）
              // 手心朝镜头 → 不渲染（手心没有指甲）
              // 手背/侧手/模糊态 → 进入 paintNails，内部再用 isNailVisible 逐指过滤
              const palmZ = (lm[0].z + lm[5].z + lm[9].z + lm[17].z) / 4;
              const knuckleZ = (lm[2].z + lm[6].z + lm[10].z + lm[14].z + lm[18].z) / 5;
              const rawDepthDiff = palmZ - knuckleZ;
              palmDepthSmoothRef.current = ema(
                palmDepthSmoothRef.current,
                rawDepthDiff,
                EMA_ALPHA_PALM
              );
              const smoothDepthDiff = palmDepthSmoothRef.current;

              // 朝向拓扑基于推理帧几何，必须使用 MediaPipe 原始 handedness。
              // handFlip 只修正镜像后的用户可见左右手标签，不能影响朝向。
              const decision = shouldRenderNails(lm, smoothDepthDiff, rawHandedness);
              const stableOrientation = updateStableOrientation(decision.orientation);
              // M1 先验开启时：palm 不再整帧硬拒，改由逐指甲板朝向门控；
              // 仅掌部中心出画仍整帧停贴。flag off 保持历史行为。
              const dorsumNormal = GESTURE_PRIOR_ENABLED
                ? computeHandDorsumNormal(lm, decision.orientation, smoothDepthDiff, vw * scale)
                : null;
              const renderNails = GESTURE_PRIOR_ENABLED
                ? decision.reason !== "手部出画面"
                : (decision.render && stableOrientation !== "palm");
              let translation: ReturnType<typeof getCoherentPalmTranslation>;
              if (splitPalmMotion) {
                if (frame && rawHandedness && renderNails &&
                  decision.orientation === "dorsum" && stableOrientation === "dorsum") {
                  const layout = `${cvs.width}:${cvs.height}:${vw}:${vh}`;
                  const points = lm.map(point => ({ x: point.x * cvs.width, y: point.y * cvs.height }));
                  const previous = previousPalmFrame;
                  if (previous?.layout === layout && previous.hand === rawHandedness &&
                    frame.mediaTime > previous.mediaTime && frame.mediaTime - previous.mediaTime <= 0.1) {
                    translation = getCoherentPalmTranslation(previous.points, points);
                  }
                  previousPalmFrame = { points, layout, mediaTime: frame.mediaTime, hand: rawHandedness };
                } else {
                  previousPalmFrame = undefined;
                }
              }
              if (traceFrame) {
                window.dispatchEvent(new CustomEvent("jiaru:ar-orientation", {
                  detail: { renderNails, stableOrientation, reason: decision.reason, frameSequence: frame?.sequence, translation },
                }));
              }

              // 全局渲染门控：手心朝镜头时完全跳过贴图
              // 只有手背/侧手/模糊态时才进入 paintNails 做逐指精细可见性判定
              const visibilityScores = frame ? workerVisibilityScores : visibleSmoothRef.current;
              if (renderNails) {
                const lightFrame = lightSampler?.read(video, cvs.width, cvs.height)
                  ?? readEnvLightFrame(video, cvs.width, cvs.height);
                paintNails(
                  ctx, lm, colRef.current, texRef.current,
                  modeRef.current, cvs.width, cvs.height, lightFrame,
                  vw * scale, dorsumNormal, visibilityScores, Boolean(frame && preferLayerReadback), translation,
                );
                if (frame) workerOverlayPainted = true;
              }

              // 同步逐指可见性到 UI（从平滑值读取，阈值 0.5 判定显隐）
              if (renderNails) {
                const vis: boolean[] = [];
                for (let fi = 0; fi < 5; fi++) {
                  vis.push(visibilityScores[fi] >= VISIBILITY_SMOOTH_THRESHOLD);
                }
                updateFingerVisibility(vis);
              } else {
                updateFingerVisibility([false, false, false, false, false]);
              }
            }
          } else {
            emptyStreakRef.current += 1;
            if (handCntUiRef.current !== 0) {
              handCntUiRef.current = 0;
              setHandCnt(0);
            }
            orientationCandidateRef.current = { orientation: "ambiguous", frames: 0 };
            if (!frame || replacedWorkerOverlay) resetTrackingGeometry();
            if (orientationRef.current !== "none") {
              orientationRef.current = "none";
              setOrientation("none");
            }
            updateFingerVisibility(
              SEG_FUSION_ENABLED && segInstancesRef.current.length
                ? paintSegFallback(ctx, segInstancesRef.current, colRef.current, texRef.current, modeRef.current, vw, vh, scale, tx2px, ty2py)
                : [false, false, false, false, false],
            );
          }
          if (frame && replacedWorkerOverlay && !workerOverlayPainted && res.multiHandLandmarks?.length) {
            resetTrackingGeometry();
          }
        }

        let consecutiveErrors = 0;
        function onTrackingError() {
          if (signal.aborted) return;
          consecutiveErrors += 1;
          if (consecutiveErrors === 30) {
            log("× 连续 30 帧推理失败，手部识别暂时不可用");
            setRecognitionFailed(true);
          }
        }

        async function startLegacyTracking() {
          const tracker = await loadLegacyTracker();
          if (signal.aborted) return;
          trackerRef.current = tracker;
          session.own(() => { trackerRef.current = null; });
          tracker.onResults(result => applyResults(result));

          // M3 常驻粗分割 Worker + 关键帧调度（2–4fps，与主跟踪隔离）。
          if (SEG_FUSION_ENABLED && typeof Worker !== "undefined") {
            const segWorker = new Worker(
              new URL("../workers/ar-nail-seg.worker.ts", import.meta.url),
              { type: "module" },
            );
            segWorker.onmessage = (event: MessageEvent<ArSegKeyframeResponse>) => {
              segBusyRef.current = false;
              segInstancesRef.current = event.data.instances;
              segHitsRef.current = updateSegHits(
                segHitsRef.current,
                segTipsRef.current,
                event.data.instances,
                SEG_ASSOC_RADIUS,
                SEG_HOLD_FRAMES,
              );
            };
            segWorker.onerror = () => { segBusyRef.current = false; };
            session.own(() => { segWorker.terminate(); segWorkerRef.current = null; });
            segWorkerRef.current = segWorker;
          }
          async function sendSegKeyframe() {
            const worker = segWorkerRef.current;
            if (!worker || video.readyState < 2) return;
            const vw = video.videoWidth, vh = video.videoHeight;
            if (!vw || !vh) return;
            const scale = Math.min(1, SEG_KEYFRAME_MAX_EDGE / Math.max(vw, vh));
            let canvas = segCanvasRef.current;
            if (!canvas) { canvas = document.createElement("canvas"); segCanvasRef.current = canvas; }
            canvas.width = Math.max(8, Math.round(vw * scale));
            canvas.height = Math.max(8, Math.round(vh * scale));
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const bitmap = await createImageBitmap(imageData);
            const request: ArSegKeyframeRequest = { id: `seg-${Date.now()}`, imageBitmap: bitmap };
            segBusyRef.current = true;
            segLastKeyframeRef.current = performance.now();
            worker.postMessage(request, [bitmap]);
          }

          // M2 ROI 丢手兜底：主跟踪连续丢手时，用上一帧包围盒裁剪窗复跑 Hands，
          // 恢复关键点映射回全帧并经漂移守卫后喂入同一 applyResults。
          async function sendRoiFallback() {
            const bootstrap = lastHandBboxRef.current == null;
            const box = lastHandBboxRef.current ?? segBootstrapBox(segInstancesRef.current);
            if (!box || !window.Hands) return;
            const vw = video.videoWidth, vh = video.videoHeight;
            const crop = expandRoi(box, vw, vh, bootstrap ? 2.2 : 1.35);
            if (!crop) return;
            if (!roiTrackerRef.current) {
              const rt = new window.Hands({ locateFile: resolveMediaPipeHandsAsset });
              session.own(() => rt.close());
              rt.setOptions({ maxNumHands: 1, modelComplexity: 1, minDetectionConfidence: 0.5, minTrackingConfidence: 0.5 });
              rt.onResults(r => {
                const c = roiCropRef.current;
                if (!c || !r.multiHandLandmarks?.length) return;
                const remapped = r.multiHandLandmarks.map(hand => remapLandmarks(hand, c, vw, vh));
                if (!roiSanity(remapped[0], box)) return;
                applyResults({ multiHandLandmarks: remapped, multiHandedness: r.multiHandedness });
              });
              roiTrackerRef.current = rt;
            }
            let canvas = roiCanvasRef.current;
            if (!canvas) { canvas = document.createElement("canvas"); roiCanvasRef.current = canvas; }
            canvas.width = Math.max(8, Math.round(crop.sw));
            canvas.height = Math.max(8, Math.round(crop.sh));
            const ctx = canvas.getContext("2d");
            if (!ctx) return;
            ctx.drawImage(video, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, canvas.width, canvas.height);
            roiCropRef.current = crop;
            try {
              await roiTrackerRef.current.send({ image: canvas as unknown as HTMLVideoElement });
            } catch { /* ROI 兜底失败保留主路径空态 */ }
          }

          async function sendFrame() {
            if (signal.aborted) return;
            try {
              await tracker.send({ image: video });
              consecutiveErrors = 0;
              if (ROI_TRACKING_ENABLED && emptyStreakRef.current >= 3 && (lastHandBboxRef.current || segInstancesRef.current.length)) {
                await sendRoiFallback();
              }
              if (SEG_FUSION_ENABLED && shouldScheduleKeyframe(performance.now(), segLastKeyframeRef.current, SEG_KEYFRAME_INTERVAL_MS, segBusyRef.current)) {
                await sendSegKeyframe();
              }
            } catch {
              onTrackingError();
            }
          }
          if (probeParameters?.get("arScheduler") === "video-frame") {
            session.own(startArVideoFrameLoop(video, sendFrame));
          } else {
            let lastInferenceAt = Number.NEGATIVE_INFINITY;
            async function loop(timestamp: number) {
              if (signal.aborted) return;
              if (video.readyState >= 2 && timestamp - lastInferenceAt >= INFERENCE_INTERVAL_MS) {
                lastInferenceAt = timestamp;
                await sendFrame();
              }
              if (!signal.aborted) rafLoop = requestAnimationFrame(loop);
            }
            let rafLoop = requestAnimationFrame(loop);
            session.own(() => cancelAnimationFrame(rafLoop));
          }
        }

        let workerTracker: ReturnType<typeof createArWorkerTracker> | undefined;
        if (useWorkerTracking && typeof VideoFrame === "function" && typeof Worker === "function") {
          try {
            workerTracker = createArWorkerTracker();
            session.own(workerTracker.close);
            await workerTracker.initialize();
          } catch (error) {
            workerTracker?.close();
            workerTracker = undefined;
            if (!signal.aborted) log("Worker 初始化失败，切换 Hands：" + String(error));
          }
        }
        if (signal.aborted) return;

        if (workerTracker) {
          const tracker = workerTracker;
          if (useWorkerCandidate) {
            try {
              materialPipelineRef.current = {
                jobs: createArMaterialJobs(materialPainter.getGrainData),
                epoch: 0, visible: Array<boolean>(5).fill(false),
              };
            } catch (error) {
              console.warn("[AR] 材质 Worker 初始化失败，使用主线程", error);
            }
          }
          if (useWorkerCandidate || probeParameters?.get("arLighting") === "worker") {
            try {
              lightSampler = createArLightSampler();
              session.own(lightSampler.close);
            } catch (error) {
              if (traceFrame) log("环境光 Worker 初始化失败：" + String(error));
            }
          }
          let overlayTimer: ReturnType<typeof setTimeout> | undefined;
          let captureSource: "track" | "video-frame" = "video-frame";
          let workerActive = true;
          let workerErrors = 0;
          session.own(() => clearTimeout(overlayTimer));
          function expireOverlay() {
            if (signal.aborted || !workerOverlayPainted) return;
            workerOverlayPainted = false;
            if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
            resetTrackingGeometry();
            updateFingerVisibility([false, false, false, false, false]);
          }

          function onWorkerError(error: unknown) {
            if (signal.aborted || !workerActive) return;
            workerErrors += 1;
            if (!tracker.closed && workerErrors < 3) return;
            workerActive = false;
            stopWorkerFrames();
            tracker.close();
            lightSampler?.close();
            lightSampler = undefined;
            closeMaterialPipeline();
            clearTimeout(overlayTimer);
            expireOverlay();
            resetTrackingGeometry();
            orientationRef.current = "none";
            orientationCandidateRef.current = { orientation: "ambiguous", frames: 0 };
            setOrientation("none");
            consecutiveErrors = 0;
            log("Worker 取帧或推理失败，切换 Hands：" + String(error));
            void startLegacyTracking().catch(failSession);
          }

          log("Worker 跟踪器就绪");
          async function trackFrame(frame: ArCapturedFrame) {
            let result: Awaited<ReturnType<typeof tracker.track>>;
            try {
              result = await tracker.track(frame);
            } catch (error) {
              onWorkerError(error);
              return;
            }
            if (signal.aborted || !workerActive) return;
            workerErrors = 0;
            try {
              const deadline = frame.observedAt + WORKER_OVERLAY_MAX_AGE_MS;
              const fresh = performance.now() < deadline;
              if (fresh) {
                // 将 Tasks 左右手标签转换为渲染器沿用的 Hands 约定。
                const labels = result.handedness.map(label => ({
                  label: label === "Left" ? "Right" as const : label === "Right" ? "Left" as const : null,
                  score: 0,
                }));
                applyResults({
                  multiHandLandmarks: result.landmarks,
                  multiHandedness: labels,
                }, frame);
                clearTimeout(overlayTimer);
                if (workerOverlayPainted) overlayTimer = setTimeout(expireOverlay, Math.max(0, deadline - performance.now()));
              } else {
                expireOverlay();
              }
              consecutiveErrors = 0;
              if (traceFrame) {
                window.dispatchEvent(new CustomEvent("jiaru:ar-tracked-frame", {
                  detail: { sequence: result.sequence, computeMs: result.computeMs, ageMs: performance.now() - frame.observedAt, fresh, captureSource },
                }));
              }
            } catch (error) {
              if (traceFrame && consecutiveErrors === 0) log("Worker 结果绘制失败：" + String(error));
              onTrackingError();
            }
          }
          const videoTrack = stream.getVideoTracks()[0];
          const stopRawFrames = probeParameters?.get("arCapture") === "track" && videoTrack
            ? startArTrackFrameLoop(videoTrack, trackFrame, onWorkerError)
            : undefined;
          if (stopRawFrames) captureSource = "track";
          const stopWorkerFrames = stopRawFrames ?? startCapturedArVideoFrameLoop(video, trackFrame, onWorkerError);
          session.own(stopWorkerFrames);
        } else {
          await startLegacyTracking();
          if (signal.aborted) return;
        }

        // ── 步骤7: 就绪 ──
        setStatus("ready");
        setStatusMsg("就绪");
        log("系统就绪 √");
        cameraActiveChangeRef.current?.(true);
      } catch (err) {
        failSession(err);
      }
    }

    start();
    return () => {
      session.close();
      teardownRef.current = null;
      cameraActiveChangeRef.current?.(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userStarted]);

  const orientationPresentation = getHandOrientationPresentation(orientation);

  return (
    <div
      className="relative mx-auto w-full overflow-hidden rounded-[24px] bg-black shadow-[var(--neu-out-md)]"
      style={{ aspectRatio: frameAspectRatio }}
    >
      <video
        ref={vref}
        playsInline
        muted
        className="absolute inset-0 h-full w-full object-cover object-center"
        style={{
          objectPosition: "50% 50%",
          transform: "scaleX(-1)",
          transformOrigin: "50% 50%",
        }}
      />
      <canvas
        ref={cref}
        aria-label="甲面贴合校准：拖动根部、甲尖或侧边圆点；也可使用右侧校准滑杆"
        className={`absolute inset-0 w-full h-full ${showFitGuides && onFitChange ? "cursor-crosshair" : "pointer-events-none"}`}
        style={{ transform: "scaleX(-1)", transformOrigin: "50% 50%", touchAction: showFitGuides && onFitChange ? "none" : "auto" }}
        onPointerDown={event => {
          const guide = fitGuideRef.current;
          if (!showFitGuides || !onFitChange || !guide || guide.finger !== activeFinger
            || performance.now() - guide.time > 250 || event.button !== 0 || fitDragRef.current) return;
          const canvas = event.currentTarget, bounds = canvas.getBoundingClientRect();
          const p = mirroredCanvasPoint(event.clientX, event.clientY, bounds, canvas.width, canvas.height);
          const ranked = (Object.entries(fitHandlePoints(guide.rendered)) as [FitHandle, { x: number; y: number }][])
            .map(([handle, q]) => ({ handle, distance: Math.hypot((p.x - q.x) * bounds.width / canvas.width,
              (p.y - q.y) * bounds.height / canvas.height) })).sort((a, b) => a.distance - b.distance);
          if (ranked[0].distance > 24) return;
          fitDragRef.current = { pointer: event.pointerId, x: p.x, y: p.y, handle: ranked[0].handle, guide };
          canvas.setPointerCapture(event.pointerId);
          event.preventDefault();
        }}
        onPointerMove={event => {
          const drag = fitDragRef.current;
          if (!drag || drag.pointer !== event.pointerId) return;
          if (!showFitGuides || drag.guide.finger !== activeFinger || !fitGuideRef.current
            || performance.now() - fitGuideRef.current.time > 250) { fitDragRef.current = null; return; }
          const canvas = event.currentTarget;
          const p = mirroredCanvasPoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), canvas.width, canvas.height);
          onFitChange?.(drag.guide.finger, dragNailFit(drag.handle, p.x - drag.x, p.y - drag.y,
            drag.guide.raw, drag.guide.rendered, drag.guide.fit));
        }}
        onPointerUp={() => { fitDragRef.current = null; }}
        onPointerCancel={() => { fitDragRef.current = null; }}
        onLostPointerCapture={() => { fitDragRef.current = null; }}
      />

      {/* 未启动时显示开始按钮 */}
      {!userStarted && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-black/80 text-white">
          <button
            ref={startBtnRef}
            type="button"
            onClick={handleStartCamera}
            className="px-8 py-4 bg-[var(--coral)] rounded-full text-lg font-bold shadow-lg active:scale-95 transition-transform"
            style={{ touchAction: "manipulation", minHeight: "60px" }}
          >
            <span className="inline-flex items-center gap-2"><Icon name="camera" className="h-5 w-5" />开启摄像头</span>
          </button>
          <p className="text-xs text-white/85 mt-4 px-6 text-center max-w-xs">
            点击后浏览器会请求摄像头权限，请允许
          </p>
          {diag.length > 0 && (
            <details className="mt-4 w-full max-w-xs rounded-lg border border-pink-500/20 bg-black/60 p-2">
              <summary className="cursor-pointer select-none px-1 text-[11px] text-gray-300">
                技术详情
              </summary>
              <div className="mt-1 max-h-20 overflow-y-auto">
                {diag.map((d, i) => (
                  <p key={i} className="text-[11px] font-mono leading-tight mb-0.5 text-gray-300">{d}</p>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* 诊断面板 — 逐步摄像头日志收进「技术详情」折叠区（§7.6，默认收起） */}
      {userStarted && status !== "ready" && (
        <div className="absolute top-1 left-1 right-1 z-20 bg-black/80 rounded-lg p-2 border border-pink-500/30">
          <details>
            <summary className="cursor-pointer select-none px-1 py-0.5 text-[12px] text-gray-300">
              技术详情
            </summary>
            <div className="mt-1 max-h-40 overflow-y-auto">
              {diag.map((d, i) => (
                <p
                  key={i}
                  className={`text-[11px] font-mono leading-tight mb-0.5 ${
                    d.includes("×")
                      ? "text-red-300"
                      : d.includes("√")
                        ? "text-green-300"
                        : d.includes("首次")
                          ? "text-yellow-200"
                          : "text-gray-300"
                  }`}
                >
                  {d}
                </p>
              ))}
            </div>
          </details>
        </div>
      )}

      {/* 非 ready 遮罩 */}
      {userStarted && status !== "ready" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/70 text-white">
          <span className="mb-3 inline-block h-10 w-10 animate-spin rounded-full border-4 border-white/25 border-t-white" aria-hidden="true" />
          <p className="text-sm px-6 text-center">{statusMsg}</p>
          {status === "error" && (
            <div className="mt-4 flex flex-col items-center gap-2 px-6 text-center">
              <p className="max-w-xs text-xs leading-5 text-white/85">
                如果浏览器已拒绝摄像头，请在地址栏权限图标中允许，然后刷新或点击下方按钮重试。
              </p>
              <button
                type="button"
                onClick={resetCameraStart}
                className="rounded-full bg-[var(--surface)] px-4 py-2 text-xs font-semibold text-[#ac5145] shadow-sm active:scale-95"
              >
                我已允许，重新尝试
              </button>
            </div>
          )}
          <div className="mt-4 w-32 h-1 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full w-3/5 bg-[#ac5145] rounded-full animate-pulse" />
          </div>
        </div>
      )}

      {/* 连续推理失败覆盖层：不再静默吞错，给用户明确出路 */}
      {userStarted && status === "ready" && recognitionFailed && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 bg-black/70 px-6 text-center text-white">
          <p className="text-sm font-medium">手部识别暂时失败</p>
          <p className="text-xs leading-5 text-white/85">
            连续多帧推理未成功。可以重试，或改用上传照片试色。
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={resetCameraStart}
              className="rounded-full bg-[var(--surface)] px-4 py-2 text-xs font-semibold text-[#ac5145] shadow-sm active:scale-95"
            >
              重试
            </button>
            <button
              type="button"
              onClick={() => {
                teardownRef.current?.();
                onSuggestUpload?.();
              }}
              className="rounded-full border border-white/30 px-4 py-2 text-xs font-medium text-white/90 transition-colors hover:bg-white/10"
            >
              改用上传照片试色
            </button>
          </div>
        </div>
      )}

      {/* 反转手 / 关闭摄像头 — 运行中控制按钮 */}
      {userStarted && status === "ready" && (
        <div className="absolute top-3 right-3 z-20 flex flex-col items-end gap-2">
          {TWO_HAND_ENABLED && (
            <button
              type="button"
              aria-pressed={twoHand}
              onClick={() => {
                setTwoHand((v) => {
                  const next = !v;
                  twoHandRef.current = next;
                  trackerRef.current?.setOptions({
                    maxNumHands: next ? 2 : 1,
                    modelComplexity: 1,
                    minDetectionConfidence: 0.5,
                    minTrackingConfidence: 0.5,
                  });
                  return next;
                });
              }}
              className={`px-2.5 py-1 min-h-11 text-[12px] rounded-full border transition-[transform,background-color,border-color,box-shadow,color]
                ${twoHand
                  ? "bg-pink-500/60 text-white border-pink-400/60 shadow-sm shadow-pink-500/20"
                  : "bg-black/40 text-white/85 border-white/20 hover:bg-black/50"
                }`}
            >
              <span className="inline-flex items-center gap-1">{twoHand ? "双手开" : "双手"}</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              setHandFlip((v) => {
                const next = !v;
                handFlipRef.current = next; // 同步到 ref（闭包安全）
                return next;
              });
            }}
            className={`px-2.5 py-1 text-[12px] rounded-full border transition-[transform,background-color,border-color,box-shadow,color]
              ${handFlip
                ? "bg-pink-500/60 text-white border-pink-400/60 shadow-sm shadow-pink-500/20"
                : "bg-black/40 text-white/85 border-white/20 hover:bg-black/50"
              }`}
          >
            <span className="inline-flex items-center gap-1"><Icon name="refresh" className="h-3.5 w-3.5" />{handFlip ? "已反转" : "反转手"}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              teardownRef.current?.();
              // 焦点返回「开启摄像头」按钮：等 init 态按钮重新挂载后聚焦
              window.setTimeout(() => startBtnRef.current?.focus(), 80);
            }}
            className="px-2.5 py-1 text-[12px] rounded-full border bg-black/40 text-white/85 border-white/20 hover:bg-black/50 transition-[transform,background-color,border-color,box-shadow,color]"
          >
            <span className="inline-flex items-center gap-1"><Icon name="x" className="h-3.5 w-3.5" />关闭摄像头</span>
          </button>
        </div>
      )}

      {/* 手部状态 + 朝向指示 + 逐指可见性 */}
      {status === "ready" && (
        <div className="absolute bottom-0 left-0 right-0 pb-3 text-center pointer-events-none z-10 flex flex-col items-center gap-1">
          {handCnt > 0 && orientation !== "none" && (
            <>
              {/* 朝向 + 左右手 */}
              <span
                className={`inline-block text-xs px-3 py-1 rounded-full ${
                  orientationPresentation.tone === "dorsum"
                    ? "text-green-300 bg-green-900/40"
                    : orientationPresentation.tone === "palm"
                      ? "text-orange-300 bg-orange-900/40"
                      : "text-gray-300 bg-gray-800/40"
                }`}
              >
                <Icon name="hand" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
                {handLabel ? handLabel + " · " : ""}
                {orientationPresentation.label}
              </span>

              {/* 逐指可见性指示器 */}
              <div className="flex items-center gap-2 text-xs">
                {["拇","食","中","无","小"].map((name, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full ${
                      fingerVisible[i]
                        ? "text-green-300 bg-green-900/40"
                        : "text-gray-500 bg-gray-800/30"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      fingerVisible[i] ? "bg-green-400" : "bg-gray-600"
                    }`} />
                    {name}
                  </span>
                ))}
              </div>
            </>
          )}
          <span className="inline-block text-xs text-white/85 bg-black/30 px-3 py-1 rounded-full ">
            {handCnt > 0
              ? "检测到 " + handCnt + " 只手"
              : handCnt === 0
                ? "请将手放在摄像头前"
                : "等待检测…"}
          </span>
        </div>
      )}
    </div>
  );
}
