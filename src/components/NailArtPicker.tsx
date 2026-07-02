"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  computeNailGeometry,
  mapGeometryScale,
  type NailLandmark,
} from "@/lib/nail-geometry";
import {
  extractTextureFromMaskDetailed,
  recognizeNailTexturesInWorker,
  type NailMask,
  type TextureExtractionDiagnostics,
} from "@/lib/nail-texture-recognition";
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

// ─── 类型定义 ──────────────────────────────────────────────

export interface NailAssignment {
  texture: ImageBitmap;
  diagnostics?: TextureExtractionDiagnostics;
  finger: number; // 0=拇 1=食 2=中 3=无 4=小
}

interface NailRegion {
  id: string;
  cx: number; cy: number;
  angle: number; // 弧度
  nl: number;    // 指甲长度（canvas 像素）
  nw: number;    // 指甲宽度（canvas 像素）
  assignedFinger: number | null;
  confidence?: "high" | "low";
  mask?: NailMask;
  warnings?: string[];
  extractionDiagnostics?: TextureExtractionDiagnostics;
}

interface DetectionSummary {
  backend: "model" | "fallback";
  modelVersion?: string;
  warnings: string[];
}

interface NailArtPickerProps {
  imageUrl: string;
  onConfirm: (assignments: NailAssignment[]) => void;
  onCancel: () => void;
}

// ─── UI 常量 ──────────────────────────────────────────────

const FINGER_NAMES = ["拇", "食", "中", "无", "小"];
const FINGER_FULL = ["拇指", "食指", "中指", "无名指", "小指"];
const MAX_CANVAS_DIM = 800;
const BORDER_COLOR = "#E8A0BF";
const HANDLE_COLOR = "#D4749D";
const MIN_NAIL_SIZE = 15;
const CDN_HANDS_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/hands.js";
const CDN_BASE = "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/";
const DETECT_TIMEOUT = 30000;

// ─── Landmark 类型 ────────────────────────────────────────

interface LmPt { x: number; y: number; z: number; }
interface HandsResults { multiHandLandmarks?: LmPt[][]; }
interface HandsCtor {
  new (c: { locateFile: (f: string) => string }): {
    setOptions: (o: Record<string, unknown>) => void;
    onResults: (cb: (r: HandsResults) => void) => void;
    close: () => void;
    send: (d: { image: HTMLCanvasElement | HTMLVideoElement }) => Promise<void>;
  };
}

// MediaPipe Hands 全局变量声明（Window.Hands 在 ArView.tsx 中已声明为 HandsConstructor 类型，
// 此处不重复声明 global，使用时通过类型断言）

// ─── 贝塞尔指甲路径（与 ArView 一致的形状） ──────────────

function drawNailPath(
  ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D,
  nl: number, nw: number
) {
  const hw = nw * 0.5;
  const hl = nl * 0.5;
  const fn = 0.08 * nw;   // tipNarrow（通用）
  const cp = hl * 0.55;   // cpLen（通用）

  ctx.beginPath();
  ctx.moveTo(hw - fn, -hl);
  ctx.quadraticCurveTo(0, -hl - hl * 0.15, -(hw - fn), -hl);
  ctx.bezierCurveTo(-(hw + cp * 0.3), -hl * 0.6, -(hw + cp * 0.3), hl * 0.3, -hw, hl);
  ctx.quadraticCurveTo(0, hl + hl * 0.08, hw, hl);
  ctx.bezierCurveTo(hw + cp * 0.3, hl * 0.3, hw + cp * 0.3, -hl * 0.6, hw - fn, -hl);
  ctx.closePath();
}

// ─── 核心：从 MediaPipe 关键点计算指甲区域 ──────────────

let regionIdCounter = 0;
function nextId(): string {
  return `n${++regionIdCounter}`;
}

function computeNailRegions(
  lm: NailLandmark[],
  cw: number, ch: number
): NailRegion[] {
  const regions: NailRegion[] = [];
  for (let f = 0; f < 5; f++) {
    const geometry = computeNailGeometry(lm, f, cw, ch);
    if (!geometry) continue;

    regions.push({
      id: nextId(),
      cx: geometry.cx,
      cy: geometry.cy,
      angle: geometry.angle,
      nl: geometry.length,
      nw: geometry.width,
      assignedFinger: f, // ← 自动分配对应手指
    });
  }
  return regions;
}

async function computeImageDetectedNailRegions(
  imageData: ImageData
): Promise<{ regions: NailRegion[]; summary: DetectionSummary }> {
  const result = await recognizeNailTexturesInWorker({
    width: imageData.width,
    height: imageData.height,
    data: imageData.data,
  }, {
    preferModel: true,
  });
  return {
    regions: result.candidates.map((candidate) => ({
      id: nextId(),
      cx: candidate.cx,
      cy: candidate.cy,
      angle: candidate.angle,
      nl: candidate.length,
      nw: candidate.width,
      assignedFinger: candidate.suggestedFinger,
      confidence: candidate.confidence === "medium" ? "low" : candidate.confidence,
      mask: candidate.mask,
      warnings: candidate.warnings,
    })),
    summary: {
      backend: result.backend,
      modelVersion: result.modelVersion,
      warnings: result.warnings,
    },
  };
}

interface Rgb {
  r: number;
  g: number;
  b: number;
}

function sampleMean(
  data: ImageData,
  region: NailRegion,
  points: readonly [number, number][]
): Rgb {
  const c = Math.cos(region.angle);
  const s = Math.sin(region.angle);
  let r = 0, g = 0, b = 0, count = 0;
  for (const [nx, ny] of points) {
    const lx = nx * region.nw;
    const ly = ny * region.nl;
    const x = Math.round(region.cx + lx * c - ly * s);
    const y = Math.round(region.cy + lx * s + ly * c);
    if (x < 0 || y < 0 || x >= data.width || y >= data.height) continue;
    const i = (y * data.width + x) * 4;
    r += data.data[i];
    g += data.data[i + 1];
    b += data.data[i + 2];
    count++;
  }
  return count ? { r: r / count, g: g / count, b: b / count } : { r: 0, g: 0, b: 0 };
}

const INNER_SAMPLES: readonly [number, number][] = [
  [-0.25, -0.3], [0, -0.35], [0.25, -0.3],
  [-0.3, 0], [0, 0], [0.3, 0],
  [-0.22, 0.3], [0, 0.35], [0.22, 0.3],
];
const RING_SAMPLES: readonly [number, number][] = [
  [-0.72, -0.25], [-0.72, 0.1], [-0.65, 0.45],
  [0.72, -0.25], [0.72, 0.1], [0.65, 0.45],
  [-0.4, 0.68], [0, 0.72], [0.4, 0.68],
];

function colorDistance(a: Rgb, b: Rgb): number {
  return Math.hypot(a.r - b.r, a.g - b.g, a.b - b.b);
}

function saturation(c: Rgb): number {
  const max = Math.max(c.r, c.g, c.b);
  const min = Math.min(c.r, c.g, c.b);
  return max === 0 ? 0 : (max - min) / max;
}

/**
 * Uses local color contrast to refine the landmark prior. It is deliberately
 * bounded so a patterned background cannot pull a candidate away from the fingertip.
 */
function refineNailRegion(data: ImageData, source: NailRegion): NailRegion {
  let best = source;
  let bestScore = -1;
  const shifts = [-0.12, 0, 0.12];
  const scales = [0.88, 1, 1.12];

  for (const across of shifts) {
    for (const along of [-0.08, 0, 0.08]) {
      for (const widthScale of scales) {
        const c = Math.cos(source.angle);
        const s = Math.sin(source.angle);
        const candidate: NailRegion = {
          ...source,
          cx: source.cx + across * source.nw * c - along * source.nl * s,
          cy: source.cy + across * source.nw * s + along * source.nl * c,
          nw: source.nw * widthScale,
        };
        const inner = sampleMean(data, candidate, INNER_SAMPLES);
        const ring = sampleMean(data, candidate, RING_SAMPLES);
        const contrast = colorDistance(inner, ring);
        const score = contrast + saturation(inner) * 22 - Math.abs(widthScale - 1) * 6;
        if (score > bestScore) {
          bestScore = score;
          best = candidate;
        }
      }
    }
  }

  return { ...best, confidence: bestScore >= 18 ? "high" : "low" };
}

// ─── 在静态图片上运行 MediaPipe Hands ─────────────────

async function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.crossOrigin = "anonymous";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("CDN 加载失败"));
    document.head.appendChild(s);
  });
}

/**
 * 在静态图片上运行 MediaPipe Hands 检测
 *
 * 策略：
 *   - 将图片缩放到合理尺寸（max 640px）后绘制到 canvas
 *   - 从 canvas 创建临时 video 流（captureStream），因为
 *     MediaPipe hands.send() 原生只接受 HTMLVideoElement
 *   - 降低置信度阈值（静态图 vs 视频）
 *   - 发送预热帧后再发送正式帧
 *   - 重试机制
 */
async function detectHandsOnImage(
  img: HTMLImageElement
): Promise<LmPt[][] | null> {
  // 1. 确保 CDN 已加载
  const HW = window.Hands as unknown as HandsCtor | undefined;
  if (!HW) {
    await loadScript(CDN_HANDS_URL);
  }
  const HF = window.Hands as unknown as HandsCtor;
  if (!HF) throw new Error("MediaPipe Hands 加载失败");
  const hands = new HF({ locateFile: (f) => CDN_BASE + f });
  hands.setOptions({
    maxNumHands: 1,
    modelComplexity: 1,
    minDetectionConfidence: 0.3,  // 静态图降低阈值
    minTrackingConfidence: 0.3,
  });

  // 3. 将图片缩放到合理尺寸
  const maxDim = 640;
  const scale = Math.min(1, maxDim / Math.max(img.naturalWidth, img.naturalHeight));
  const canvasW = Math.round(img.naturalWidth * scale);
  const canvasH = Math.round(img.naturalHeight * scale);

  const canvas = document.createElement("canvas");
  canvas.width = canvasW;
  canvas.height = canvasH;
  const ctx = canvas.getContext("2d")!;
  // 白背景（部分照片有透明区域会干扰）
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvasW, canvasH);
  ctx.drawImage(img, 0, 0, canvasW, canvasH);

  // 4. canvas → 临时 video（captureStream 兼容 Chrome/Firefox/Safari 15+）
  // 这是最可靠的 MediaPipe 静态图处理方式
  let stream: MediaStream | null = null;
  try {
    stream = (canvas as HTMLCanvasElement).captureStream(10); // 10fps
  } catch {
    // 降级：直接用 canvas（部分浏览器不支持 captureStream）
  }

  // 5. Promise 化检测，带预热 + 重试
  async function detectOnce(src: HTMLCanvasElement): Promise<HandsResults> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("检测超时")), DETECT_TIMEOUT);
      hands.onResults((r) => { clearTimeout(timer); resolve(r); });
      hands.send({ image: src }).catch((e) => { clearTimeout(timer); reject(e); });
    });
  }

  let lastError: string | null = null;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      if (stream) {
        // 用 video 包装（最兼容）
        const video = document.createElement("video");
        video.srcObject = stream;
        video.width = canvasW;
        video.height = canvasH;

        // 等待 video 可播放
        await new Promise<void>((resolve) => {
          video.onloadedmetadata = () => {
            video.play().then(resolve).catch(resolve);
          };
          setTimeout(resolve, 2000); // fallback
        });

        // 预热帧（MediaPipe 视频管线需要第一帧初始化）
        try { await detectOnce(canvas); } catch { /* 预热帧失败忽略 */ }
        // 正式帧
        const results = await detectOnce(canvas);
        if (results.multiHandLandmarks?.length) {
          stream.getTracks().forEach((t) => t.stop());
          hands.close();
          return results.multiHandLandmarks;
        }
      } else {
        // 直接 canvas 发送
        if (attempt === 0) {
          try { await detectOnce(canvas); } catch { /* 预热 */ }
        }
        const results = await detectOnce(canvas);
        if (results.multiHandLandmarks?.length) {
          hands.close();
          return results.multiHandLandmarks;
        }
      }
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      console.warn(`[NailArtPicker] Attempt ${attempt + 1} failed:`, lastError);
      // 等待一秒后重试
      if (attempt < 2) await new Promise((r) => setTimeout(r, 1000));
    }
  }

  if (stream) stream.getTracks().forEach((t) => t.stop());
  hands.close();
  console.warn("[NailArtPicker] All attempts failed, last error:", lastError);
  return null;
}

// ─── 从选区提取纹理 ────────────────────────────────────

async function extractNailFromRegion(
  img: HTMLImageElement,
  region: NailRegion,
  displayScale: number
): Promise<ImageBitmap> {
  if (displayScale <= 0) throw new Error("无效的图片缩放比例");
  const original = mapGeometryScale(
    {
      cx: region.cx,
      cy: region.cy,
      length: region.nl,
      width: region.nw,
      angle: region.angle,
    },
    1 / displayScale
  );
  const outputWidth = Math.max(4, Math.ceil(original.width));
  const outputHeight = Math.max(4, Math.ceil(original.length));
  const canvas = new OffscreenCanvas(outputWidth, outputHeight);
  const ctx = canvas.getContext("2d")!;
  ctx.translate(outputWidth / 2, outputHeight / 2);
  drawNailPath(ctx, original.length, original.width);
  ctx.clip();
  ctx.rotate(-original.angle);
  ctx.drawImage(img, -original.cx, -original.cy);
  return createImageBitmap(canvas);
}

// ─── 工具函数 ───────────────────────────────────────────

function clientToCanvas(cx: number, cy: number, cvs: HTMLCanvasElement) {
  const r = cvs.getBoundingClientRect();
  return { x: (cx - r.left) * (cvs.width / r.width), y: (cy - r.top) * (cvs.height / r.height) };
}

/* _isInNail 预留未使用
function _isInNail(px: number, py: number, r: NailRegion): boolean {
  const dx = px - r.cx, dy = py - r.cy;
  const c = Math.cos(-r.angle), s = Math.sin(-r.angle);
  const lx = dx * c - dy * s, ly = dx * s + dy * c;
  const hw = r.nw * 0.5, hl = r.nl * 0.5;
  return (lx * lx) / (hw * hw) + (ly * ly) / (hl * hl) <= 1.0;
}
*/

function fitScale(iw: number, ih: number) {
  const s = Math.min(1, MAX_CANVAS_DIM / Math.max(iw, ih));
  return { canvasW: Math.round(iw * s), canvasH: Math.round(ih * s), scale: s };
}

// ═══════════════════════════════════════════════════════════
//  COMPONENT
// ═══════════════════════════════════════════════════════════

export default function NailArtPicker({ imageUrl, onConfirm, onCancel }: NailArtPickerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detecting, setDetecting] = useState(true); // 自动检测中
  const [scale, setScale] = useState(1);
  const [detectionSummary, setDetectionSummary] = useState<DetectionSummary | null>(null);
  const [originalRegions, setOriginalRegions] = useState<NailRegion[]>([]);

  // 选区
  const [regions, setRegions] = useState<NailRegion[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  // cursorStyle 未使用（预留）
  // const [cursorStyle, setCursorStyle] = useState("default");

  // 拖拽状态
  type Handle =
    | "body"
    | "edge-l" | "edge-r" | "edge-t" | "edge-b"
    | "corner-tl" | "corner-tr" | "corner-bl" | "corner-br"
    | "rotator";
  const dragRef = useRef<{
    handle: Handle;
    startX: number; startY: number;
    orig: NailRegion;
  } | null>(null);

  const [extracting, setExtracting] = useState(false);

  const sel = selectedIdx !== null ? regions[selectedIdx] : null;
  const selectedQualitySummary = sel ? summarizeRegionQuality(sel) : null;
  const selectedExtractionSummary = summarizeExtractionDiagnostics(sel?.extractionDiagnostics);
  const selectedReviewMessages = selectedQualitySummary?.messages ?? [];
  const detectionWarningMessages = detectionSummary?.warnings.map(presentRecognitionWarning) ?? [];
  const hasRegionsNeedingReview = regions.some((region) => regionNeedsReview(region));

  // ── 1. 加载图片 ──────────────────────────────────────

  useEffect(() => {
    let dead = false;
    const img = new Image();
    img.crossOrigin = "anonymous";

    img.onload = () => {
      if (dead) return;
      imgRef.current = img;
      const cvs = canvasRef.current;
      if (!cvs) return;

      const { canvasW, canvasH, scale: s } = fitScale(img.naturalWidth, img.naturalHeight);
      cvs.width = canvasW;
      cvs.height = canvasH;
      setScale(s);

      const ctx = cvs.getContext("2d")!;
      ctx.drawImage(img, 0, 0, canvasW, canvasH);
      setImgLoaded(true);
    };

    img.onerror = () => { if (!dead) setError("图片加载失败"); };
    img.src = imageUrl;
    return () => { dead = true; };
  }, [imageUrl]);

  // ── 2. 自动检测指甲区域（图片加载后触发）──────────────

  useEffect(() => {
    if (!imgLoaded || !imgRef.current) return;
    let dead = false;

    (async () => {
      const img = imgRef.current!;
      const cvs = canvasRef.current;
      if (!cvs) return;

      try {
        setDetecting(true);
        setError(null);
        setDetectionSummary(null);
        const landmarks = await detectHandsOnImage(img);
        if (dead) return;

        if (landmarks && landmarks.length > 0) {
          const cw = cvs.width;
          const ch = cvs.height;
          const ctx = cvs.getContext("2d");
          const priors = computeNailRegions(landmarks[0], cw, ch);
          const imageData = ctx?.getImageData(0, 0, cw, ch);
          const detected = imageData
            ? priors.map((region) => refineNailRegion(imageData, region))
            : priors.map((region) => ({ ...region, confidence: "low" as const }));
          if (detected.length > 0) {
            setRegions(detected);
            setOriginalRegions(detected.map((region) => ({ ...region })));
            setDetectionSummary({
              backend: "fallback",
              warnings: ["mediapipe_geometry_detection"],
            });
            setSelectedIdx(0);
            setError(null);
          } else {
            const fallback = imageData ? await computeImageDetectedNailRegions(imageData) : null;
            if (fallback && fallback.regions.length > 0) {
              setRegions(fallback.regions);
              setOriginalRegions(fallback.regions.map((region) => ({ ...region })));
              setDetectionSummary(fallback.summary);
              setSelectedIdx(0);
              setError(null);
              return;
            }
            setError("检测到手指但未识别出指甲区域，请手动添加");
          }
        } else {
          const ctx = cvs.getContext("2d");
          const imageData = ctx?.getImageData(0, 0, cvs.width, cvs.height);
          const fallback = imageData ? await computeImageDetectedNailRegions(imageData) : null;
          if (fallback && fallback.regions.length > 0) {
            setRegions(fallback.regions);
            setOriginalRegions(fallback.regions.map((region) => ({ ...region })));
            setDetectionSummary(fallback.summary);
            setSelectedIdx(0);
            setError(null);
            return;
          }
          setError("未在图片中检测到手指或指甲，请手动添加选区");
        }
      } catch (err) {
        if (!dead) {
          console.warn("[NailArtPicker] Auto-detect failed:", err);
          const cvs = canvasRef.current;
          const ctx = cvs?.getContext("2d");
          const imageData = cvs && ctx ? ctx.getImageData(0, 0, cvs.width, cvs.height) : null;
          const fallback = imageData ? await computeImageDetectedNailRegions(imageData) : null;
          if (fallback && fallback.regions.length > 0) {
            setRegions(fallback.regions);
            setOriginalRegions(fallback.regions.map((region) => ({ ...region })));
            setDetectionSummary(fallback.summary);
            setSelectedIdx(0);
            setError(null);
          } else {
            setError("自动检测失败，请手动添加选区");
          }
        }
      } finally {
        if (!dead) setDetecting(false);
      }
    })();

    return () => { dead = true; };
  }, [imgLoaded]);

  // ── 3. 重绘（含交互手柄） ──────────────────────────

  // HANDLE_R / getHandles 预留（未使用）
  // const HANDLE_R = 6;
  /*
  function getHandles(nl: number, nw: number) {
    const hl = nl * 0.5, hw = nw * 0.5;
    return {
      tip:     { x: 0,    y: -hl },
      left:    { x: -hw,  y: 0 },
      right:   { x: hw,   y: 0 },
      rotator: { x: 0,    y: -hl - 22 },
    };
  }
  */

  /** 世界坐标 → 指甲局部坐标 */
  function toLocal(wx: number, wy: number, r: NailRegion) {
    const dx = wx - r.cx, dy = wy - r.cy;
    const c = Math.cos(-r.angle), s = Math.sin(-r.angle);
    return { x: dx * c - dy * s, y: dx * s + dy * c };
  }

  /** 检测点击命中了哪个手柄（local 坐标） */
  function hitHandle(lx: number, ly: number, r: NailRegion): Handle | null {
    const hs = getHandles2(r.nl, r.nw);
    let best: Handle | null = null;
    let bestDist = 20;
    for (const [name, p] of Object.entries(hs)) {
      const d = Math.hypot(lx - p.x, ly - p.y);
      if (d < bestDist) { bestDist = d; best = name as Handle; }
    }
    if (best) return best;
    const hw = r.nw * 0.5 + 8, hl = r.nl * 0.5 + 8;
    if (Math.abs(lx) < hw && Math.abs(ly) < hl) return "body";
    return null;
  }

  /** 9 个手柄位置（四角+四边+旋转） */
  function getHandles2(nl: number, nw: number) {
    const hw = nw * 0.5, hl = nl * 0.5;
    return {
      "corner-tl": { x: -hw, y: -hl }, "corner-tr": { x: hw, y: -hl },
      "corner-bl": { x: -hw, y:  hl }, "corner-br": { x: hw, y:  hl },
      "edge-l":    { x: -hw, y: 0 },   "edge-r":    { x: hw, y: 0 },
      "edge-t":    { x: 0,   y: -hl }, "edge-b":    { x: 0,  y: hl },
      rotator:     { x: 0,   y: -hl - 26 },
    } as const;
  }

  const redraw = useCallback(() => {
    const cvs = canvasRef.current;
    const img = imgRef.current;
    if (!cvs || !img) return;

    const ctx = cvs.getContext("2d")!;
    ctx.clearRect(0, 0, cvs.width, cvs.height);
    ctx.drawImage(img, 0, 0, cvs.width, cvs.height);

    for (let i = 0; i < regions.length; i++) {
      const r = regions[i];
      const isSel = i === selectedIdx;

      ctx.save();
      ctx.translate(r.cx, r.cy);
      ctx.rotate(r.angle);

      // 半透明底色
      ctx.fillStyle = isSel ? "rgba(232,160,191,0.28)" : "rgba(232,160,191,0.10)";
      drawNailPath(ctx, r.nl, r.nw);
      ctx.fill();

      // 边框
      ctx.strokeStyle = isSel ? BORDER_COLOR : "rgba(232,160,191,0.45)";
      ctx.lineWidth = isSel ? 2.5 : 1.5;
      if (!isSel) ctx.setLineDash([4, 3]);
      drawNailPath(ctx, r.nl, r.nw);
      ctx.stroke();
      ctx.setLineDash([]);

      // 手指标签
      const fingerLabel = r.assignedFinger !== null ? FINGER_NAMES[r.assignedFinger] : `${i + 1}`;
      const label = regionNeedsReview(r) ? `${fingerLabel}⚠` : fingerLabel;
      ctx.fillStyle = "rgba(232,160,191,0.9)";
      ctx.font = isSel ? "bold 16px sans-serif" : "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, 0, r.nl * 0.35);

      // ── 选中时绘制交互手柄 ──
      if (isSel) {
        const hs = getHandles2(r.nl, r.nw);
        const hw = r.nw * 0.5, hl = r.nl * 0.5;

        // 辅助虚线框
        ctx.strokeStyle = "rgba(212,116,157,0.15)";
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 4]);
        ctx.strokeRect(-hw, -hl, r.nw, r.nl);
        ctx.setLineDash([]);

        for (const [name, p] of Object.entries(hs)) {
          const isCorner = name.startsWith("corner");
          // isEdge 未使用（预留）
          // const isEdge = name.startsWith("edge");
          const isRot = name === "rotator";

          ctx.beginPath();
          ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);

          if (isRot) {
            ctx.fillStyle = "rgba(255,255,255,0.15)";
            ctx.fill();
            ctx.strokeStyle = HANDLE_COLOR;
            ctx.lineWidth = 2.5;
            ctx.stroke();
            // 三角箭头
            ctx.fillStyle = HANDLE_COLOR;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y - 14);
            ctx.lineTo(p.x - 4, p.y - 9);
            ctx.lineTo(p.x + 4, p.y - 9);
            ctx.closePath();
            ctx.fill();
          } else if (isCorner) {
            ctx.fillStyle = "#fff";
            ctx.fill();
            ctx.strokeStyle = HANDLE_COLOR;
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.fillStyle = HANDLE_COLOR;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
            ctx.fill();
          } else {
            ctx.fillStyle = HANDLE_COLOR;
            ctx.fill();
            ctx.strokeStyle = "#fff";
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }
        }
      }
      ctx.restore();
    }
  }, [regions, selectedIdx]);

  useEffect(() => { redraw(); }, [redraw]);

  // ── 4. 光标 + 拖拽交互 ─────────────────────────────

  function patchRegion(idx: number, p: Partial<NailRegion>) {
    setRegions((prev) => prev.map((r, i) => (i === idx ? { ...r, ...p } : r)));
  }

  const handleDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const cvs = canvasRef.current;
    if (!cvs || regions.length === 0) return;
    const p = clientToCanvas(e.clientX, e.clientY, cvs);
    for (let i = regions.length - 1; i >= 0; i--) {
      const r = regions[i];
      const local = toLocal(p.x, p.y, r);
      const h = hitHandle(local.x, local.y, r);
      if (h) {
        setSelectedIdx(i);
        cvs.setPointerCapture(e.pointerId);
        dragRef.current = { handle: h, startX: p.x, startY: p.y, orig: { ...r } };
        return;
      }
    }
    setSelectedIdx(null);
  };

  const handleMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const p = clientToCanvas(e.clientX, e.clientY, cvs);
    const drag = dragRef.current;

    if (drag && selectedIdx !== null) {
      const dx = p.x - drag.startX, dy = p.y - drag.startY;
      const r = drag.orig;
      switch (drag.handle) {
        case "body":
          patchRegion(selectedIdx, { cx: r.cx + dx, cy: r.cy + dy }); break;
        case "corner-tl": case "corner-tr": case "corner-bl": case "corner-br": {
          const s = Math.max(0.2, Math.hypot(r.nl + dy, r.nw + dx) / Math.hypot(r.nl, r.nw));
          patchRegion(selectedIdx, { nl: Math.max(MIN_NAIL_SIZE, r.nl * s), nw: Math.max(MIN_NAIL_SIZE, r.nw * s) });
          break;
        }
        case "edge-l": case "edge-r":
          patchRegion(selectedIdx, { nw: Math.max(MIN_NAIL_SIZE, r.nw + dx * (drag.handle === "edge-r" ? 1 : -1)) }); break;
        case "edge-t": case "edge-b":
          patchRegion(selectedIdx, { nl: Math.max(MIN_NAIL_SIZE, r.nl + dy * (drag.handle === "edge-b" ? 1 : -1)) }); break;
        case "rotator":
          patchRegion(selectedIdx, { angle: Math.atan2(p.y - r.cy, p.x - r.cx) + Math.PI / 2 }); break;
      }
      return;
    }

    // 光标反馈
    if (selectedIdx === null) { cvs.style.cursor = "default"; return; }
    const l = toLocal(p.x, p.y, regions[selectedIdx]);
    const h = hitHandle(l.x, l.y, regions[selectedIdx]);
    const cs: Record<string, string> = {
      "corner-tl": "nw-resize", "corner-tr": "ne-resize", "corner-bl": "sw-resize", "corner-br": "se-resize",
      "edge-l": "ew-resize", "edge-r": "ew-resize", "edge-t": "ns-resize", "edge-b": "ns-resize", rotator: "grab",
    };
    cvs.style.cursor = h ? (cs[h] ?? "move") : "default";
  };

  const handleUp = () => { dragRef.current = null; };

  // ── 选区操作 ─────────────────────────────────────────

  const addRegion = () => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const r: NailRegion = {
      id: nextId(),
      cx: cvs.width / 2, cy: cvs.height / 2,
      angle: 0, nl: 50, nw: 32,
      assignedFinger: null,
    };
    setRegions((prev) => [...prev, r]);
    setSelectedIdx(regions.length);
  };

  const delRegion = () => {
    if (selectedIdx === null) return;
    setRegions((prev) => prev.filter((_, i) => i !== selectedIdx));
    setSelectedIdx(null);
  };

  // ── 手指分配 ─────────────────────────────────────────

  const exportDebugSample = () => {
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
    const blob = new Blob([JSON.stringify(record, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = createNailDebugSampleFilename(record);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
  };

  const assignFinger = (fi: number) => {
    if (selectedIdx === null) return;
    setRegions((prev) => prev.map((r, i) => i === selectedIdx ? { ...r, assignedFinger: fi } : r));
  };

  // ── 确认提取 ─────────────────────────────────────────

  const handleConfirm = async () => {
    const assigned = regions.filter((r) => r.assignedFinger !== null);
    if (assigned.length === 0) { setError("请先为选区分配手指"); return; }
    const img = imgRef.current;
    if (!img) return;

    setExtracting(true);
    setError(null);
    try {
      const results: NailAssignment[] = [];
      for (const r of assigned) {
        if (results.some((a) => a.finger === r.assignedFinger)) continue;
        if (r.mask) {
          const extracted = await extractTextureFromMaskDetailed(
            img,
            img.naturalWidth,
            img.naturalHeight,
            r.mask
          );
          setRegions((prev) =>
            prev.map((candidate) =>
              candidate.id === r.id
                ? { ...candidate, extractionDiagnostics: extracted.diagnostics }
                : candidate
            )
          );
          results.push({
            texture: extracted.texture,
            finger: r.assignedFinger!,
            diagnostics: extracted.diagnostics,
          });
          continue;
        }

        const texture = await extractNailFromRegion(img, r, scale);
        results.push({ texture, finger: r.assignedFinger! });
      }
      onConfirm(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "纹理提取失败");
    } finally {
      setExtracting(false);
    }
  };

  // ── 渲染 ─────────────────────────────────────────────

  if (error && !imgLoaded) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70 p-4">
        <div className="bg-white rounded-2xl p-6 text-center max-w-sm">
          <p className="text-red-500 mb-4">{error}</p>
          <button onClick={onCancel} className="px-4 py-2 bg-pink-100 text-pink-600 rounded-xl">返回</button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black">
      {/* 顶部栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/90">
        <span className="text-white text-sm">
          {detecting ? "⏳ 正在检测指甲区域..." :
           regions.length > 0
              ? `已定位 ${regions.length} 个候选` +
                (hasRegionsNeedingReview ? " · ⚠ 请检查标记" : "") +
                (detectionSummary ? ` · ${detectionSummary.backend === "model" ? "模型" : "回退"}识别` : "") +
                (detectionSummary?.modelVersion ? ` · ${detectionSummary.modelVersion}` : "") +
                (sel ? ` · 选区 ${selectedIdx! + 1}/${regions.length}` : "")
             : "未检测到指甲，请手动添加"}
        </span>
        <button onClick={onCancel} className="text-gray-400 text-sm px-3 py-1 rounded-lg hover:bg-white/10 transition-colors">
          取消
        </button>
      </div>

      {/* Canvas */}
      <div className="flex-1 flex items-center justify-center overflow-hidden bg-[#222]">
        {!imgLoaded && (
          <div className="absolute z-10 text-white/70"><span>⏳ 加载中...</span></div>
        )}
        {detecting && imgLoaded && (
          <div className="absolute z-10 flex flex-col items-center gap-2 text-white/70 bg-black/50 px-6 py-4 rounded-2xl">
            <span className="text-xl animate-pulse">🔍</span>
            <span className="text-sm">正在识别指甲区域...</span>
            <span className="text-[10px] text-gray-400">使用 MediaPipe 手部检测</span>
          </div>
        )}
        <canvas
          ref={canvasRef}
          onPointerDown={handleDown}
          onPointerMove={handleMove}
          onPointerUp={handleUp}
          onPointerLeave={handleUp}
          className="max-w-full max-h-full object-contain touch-none select-none"
          style={{ cursor: regions.length > 0 && !detecting ? "crosshair" : "default" }}
        />
      </div>

      {/* 底部控制区 */}
      <div className="bg-black/95 px-4 py-3 space-y-2.5">
        {error && <p className="text-red-400 text-xs text-center">{error}</p>}
        {!error && detectionWarningMessages.length ? (
          <p className="text-yellow-300 text-[10px] text-center">
            {detectionWarningMessages.join(" · ")}
          </p>
        ) : null}

        {/* 选区操作 */}
        {!error && selectedQualitySummary ? (
          <div
            className={`rounded-xl px-3 py-2 text-[10px] ${
              selectedQualitySummary.severity === "review"
                ? "border border-amber-500/20 bg-amber-500/10 text-amber-200"
                : "border border-emerald-500/20 bg-emerald-500/10 text-emerald-200"
            }`}
          >
            <p className="text-center font-medium">{selectedQualitySummary.title}</p>
            {selectedReviewMessages.length ? (
              <ul className="mt-1 space-y-1">
                {selectedReviewMessages.map((message) => (
                  <li key={message} className="text-center">
                    {message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        {!error && selectedExtractionSummary ? (
          <div
            className={`rounded-xl px-3 py-2 text-[10px] ${
              selectedExtractionSummary.severity === "review"
                ? "border border-sky-500/20 bg-sky-500/10 text-sky-200"
                : "border border-cyan-500/20 bg-cyan-500/10 text-cyan-200"
            }`}
          >
            <p className="text-center font-medium">{selectedExtractionSummary.title}</p>
            <p className="mt-1 text-center">{selectedExtractionSummary.stats.join(" · ")}</p>
            {selectedExtractionSummary.messages.length ? (
              <ul className="mt-1 space-y-1">
                {selectedExtractionSummary.messages.map((message) => (
                  <li key={message} className="text-center">
                    {message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-center gap-2 justify-center">
          <button onClick={addRegion} className="px-3 py-1.5 text-xs rounded-full bg-pink-500/60 text-white hover:bg-pink-500 transition-colors">
            ＋ 添加选区
          </button>
          {regions.length > 0 && (
            <button
              onClick={exportDebugSample}
              className="px-3 py-1.5 text-xs rounded-full bg-emerald-500/50 text-white hover:bg-emerald-500/70 transition-colors"
            >
              导出修正样本
            </button>
          )}
          {sel && (
            <button onClick={delRegion} className="px-3 py-1.5 text-xs rounded-full bg-red-500/40 text-white hover:bg-red-500/60 transition-colors">
              删除
            </button>
          )}
          {regions.length > 0 && (
            <button
              onClick={() => { setRegions([]); setSelectedIdx(null); setError("已清除所有选区"); }}
              className="px-3 py-1.5 text-xs rounded-full bg-gray-600/40 text-gray-300 hover:bg-gray-600/60 transition-colors"
            >
              全部清除
            </button>
          )}
        </div>

        {/* 操作提示 */}
        {sel && (
          <div className="flex items-center justify-center gap-2 text-[10px] text-gray-400">
            <span>▣ 四角 = 等比缩放</span>
            <span>⎯ 四边 = 单轴缩放</span>
            <span>⭕ 顶部 = 旋转</span>
            <span>✋ 本体 = 移动</span>
          </div>
        )}

        {/* 手指分配 */}
        <div className="flex items-center justify-center gap-1.5">
          <span className="text-xs text-gray-400 mr-1">分配到:</span>
          {FINGER_FULL.map((name, i) => {
            const taken = regions.some((r, ri) => r.assignedFinger === i && ri !== selectedIdx);
            const active = sel?.assignedFinger === i;
            return (
              <button key={i} disabled={!sel}
                onClick={() => assignFinger(i)}
                className={`w-9 h-9 rounded-full text-xs font-bold transition-all ${
                  active ? "bg-pink-500 text-white shadow-sm scale-110" :
                  taken ? "bg-gray-700 text-gray-500 cursor-not-allowed" :
                  sel ? "bg-white/10 text-gray-300 hover:bg-white/20" :
                  "bg-white/5 text-gray-600 cursor-default"
                }`}>{name}</button>
            );
          })}
        </div>

        {/* 确认 */}
        {!detecting && (
          <div className="flex justify-center pt-1">
            <button onClick={handleConfirm}
              disabled={extracting || regions.filter((r) => r.assignedFinger !== null).length === 0}
              className="w-full max-w-xs py-2.5 rounded-xl text-sm font-medium transition-all
                bg-gradient-to-r from-pink-400 to-rose-500 text-white
                disabled:opacity-40 disabled:cursor-not-allowed hover:shadow-lg active:scale-[0.98]"
            >
              {extracting ? "⏳ 提取纹理中..." : "✅ 完成分配"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
