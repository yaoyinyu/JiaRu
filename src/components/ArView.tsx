"use client";
import { useRef, useEffect, useState } from "react";

// MediaPipe 手部关键点索引
const TIPS = [4, 8, 12, 16, 20]; // 指尖
const DIPS = [3, 7, 11, 15, 19]; // DIP 关节（远端指关节）
const PIPS = [2, 6, 10, 14, 18]; // PIP 关节（近端指关节，方向更稳定）

// 指数移动平均平滑因子
const EMA_ALPHA = 0.45;
const EMA_ALPHA_PALM = 0.3; // 朝向深度差平滑（更保守）

// ── 手心/手背朝向检测参数 ──
// 手心判定阈值低（灵敏），手背判定阈值高（严格）
const DEPTH_DIFF_THRESHOLD_DORSUM = 0.005;  // depthDiff 超过此值才判手背（更严格）
const DEPTH_DIFF_THRESHOLD_PALM = 0.001;    // depthDiff 超过此值就判手心（更灵敏）
const FINGER_Z_VOTE_THRESHOLD_DORSUM = 0.003; // 单指投票手背阈值（严格）
const FINGER_Z_VOTE_THRESHOLD_PALM = 0.001;   // 单指投票手心阈值（灵敏）
const OUT_OF_FRAME_THRESHOLD = 0.1;   // x/y 超出 [0.1, 0.9] = 出画面

// 叉积法向量 z 分量阈值
const CROSS_PRODUCT_Z_THRESHOLD_DORSUM = 0.002;  // 手背判定（严格）
const CROSS_PRODUCT_Z_THRESHOLD_PALM = 0.0005;   // 手心判定（灵敏）

// 拇指位置辅助验证：拇指 TIP.x 相对手掌中心 x 的偏移
const THUMB_X_THRESHOLD = 0.02;

// 逐指指甲可见性阈值
// 手心侧：TIP.z - DIP.z > 此值 = 指甲被遮挡 → 不渲染
const NAIL_PALM_Z_THRESHOLD = 0.002;
// 信号 B 阈值：TIP.z - PIP.z > 此值 → 手心侧（更宽松，用于印证）
const NAIL_PALM_Z_THRESHOLD_B = 0.003;
// 透视缩短比阈值：len2D/len3D < 此值 → 手指指向镜头 → 手心侧
const FORESHORTEN_THRESHOLD = 0.65;
// 可见性状态帧间平滑因子
const VISIBILITY_EMA_ALPHA = 0.3;
// 可见性平滑阈值（< 此值视为不可见）
const VISIBILITY_SMOOTH_THRESHOLD = 0.5;

// 4 指投票索引（排除拇指，拇指结构特殊 z 不稳定）
const VOTE_FINGERS = [1, 2, 3, 4];

// 指甲中心从指尖向手根方向的偏移比例
const TIP_OFFSET_RATIO = 0.28;

// 逐指宽长比校准（拇指宽短、小指窄长）
const FINGER_LENGTH_RATIOS = [0.55, 0.58, 0.60, 0.56, 0.52];
const FINGER_WIDTH_RATIOS  = [0.55, 0.50, 0.48, 0.45, 0.40];

// 逐指指甲形状参数 [thumb, index, middle, ring, pinky]
// 指尖收窄系数：拇指最大(平)，小指最小(尖)
const FINGER_TIP_NARROW  = [0.12, 0.08, 0.07, 0.08, 0.06];
// 侧面曲线控制点比率：越小侧线越直
const FINGER_SIDE_CURVE  = [0.50, 0.55, 0.55, 0.52, 0.45];
// 根部凸起系数：控制指甲根部曲线下凸程度
const FINGER_ROOT_BULGE  = [0.06, 0.08, 0.08, 0.07, 0.05];

// 柱面曲率变形参数
const CURVATURE_STRENGTH = 0.22;  // 曲率强度（0=平面，越大越弯）
const CURVATURE_STRIPS = 12;      // 竖条分片数（越多越平滑）

// MediaPipe 全局类型声明（CDN 注入）
interface Landmark {
  x: number;
  y: number;
  z: number;
}

interface Handedness {
  label: "Left" | "Right";
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

interface Props {
  nailColors: string[];
  /** 每指独立纹理（null = 该指使用纯色） */
  nailTextures?: (ImageBitmap | null)[];
  /** 渲染模式：color | texture */
  mode?: "color" | "texture";
}

export function ArView({ nailColors, nailTextures, mode = "color" }: Props) {
  const vref = useRef<HTMLVideoElement>(null);
  const cref = useRef<HTMLCanvasElement>(null);
  const colRef = useRef(nailColors);
  const texRef = useRef(nailTextures);
  const modeRef = useRef(mode);
  const [status, setStatus] = useState("init"); // init|loading|ready|error
  const [statusMsg, setStatusMsg] = useState("初始化...");
  const [handCnt, setHandCnt] = useState(-1); // -1=未检测, 0=无手, N=有手
  const [diag, setDiag] = useState<string[]>([]);

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
  // 朝向状态（用于 UI 显示）
  const [orientation, setOrientation] = useState<"dorsum" | "palm" | "ambiguous" | "none">("none");
  // 左右标识（用于 UI 显示）
  const [handLabel, setHandLabel] = useState<"左手" | "右手" | null>(null);
  // 逐指可见性 UI 状态（true=可见，false=隐藏）
  const [fingerVisible, setFingerVisible] = useState<boolean[]>([true, true, true, true, true]);

  const log = (m: string) => {
    console.log("[AR]", m);
    setDiag((p) => [...p.slice(-8), m]);
  };

  /** 指数移动平均平滑（NaN 安全：首次值直接采用） */
  function ema(prev: number, curr: number, alpha: number = EMA_ALPHA): number {
    if (isNaN(prev)) return curr;
    return prev + alpha * (curr - prev);
  }

  /**
   * 绘制指甲形状（贝塞尔路径 —— 比椭圆更贴近真实指甲轮廓）
   * 每根手指使用不同的形状参数：
   *   拇指 — 宽短平尖 / 食指中指 — 标准椭圆 / 无名指 — 圆润 / 小指 — 尖窄
   */
  function drawNailShape(
    ctx: CanvasRenderingContext2D,
    nl: number,
    nw: number,
    fingerIdx: number = 2  // 默认中指
  ) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;
    const tipNarrow = FINGER_TIP_NARROW[fingerIdx] * nw;
    const cpLen = hl * FINGER_SIDE_CURVE[fingerIdx];
    const rootBulge = hl * FINGER_ROOT_BULGE[fingerIdx];

    ctx.beginPath();
    ctx.moveTo(hw - tipNarrow, -hl);
    ctx.quadraticCurveTo(0, -hl - hl * 0.15, -(hw - tipNarrow), -hl);
    ctx.bezierCurveTo(
      -(hw + cpLen * 0.3), -hl * 0.6,
      -(hw + cpLen * 0.3), hl * 0.3,
      -hw, hl + rootBulge
    );
    ctx.quadraticCurveTo(0, hl + rootBulge + hl * 0.06, hw, hl + rootBulge);
    ctx.bezierCurveTo(
      hw + cpLen * 0.3, hl * 0.3,
      hw + cpLen * 0.3, -hl * 0.6,
      hw - tipNarrow, -hl
    );
    ctx.closePath();
  }

  /**
   * 从视频帧采样环境光照
   * 在指甲中心位置取一小块区域的平均亮度
   */
  function sampleEnvLight(
    video: HTMLVideoElement,
    cx: number,
    cy: number,
    w: number,
    h: number
  ): { brightness: number; r: number; g: number; b: number } {
    // 创建微型离屏 canvas 采样
    const sampleSize = 8;
    const sx = Math.max(0, Math.min(w - sampleSize, cx - sampleSize / 2));
    const sy = Math.max(0, Math.min(h - sampleSize, cy - sampleSize / 2));

    const off = new OffscreenCanvas(sampleSize, sampleSize);
    const octx = off.getContext("2d");
    if (!octx) return { brightness: 1.0, r: 1, g: 1, b: 1 };

    octx.drawImage(video, sx, sy, sampleSize, sampleSize, 0, 0, sampleSize, sampleSize);
    const data = octx.getImageData(0, 0, sampleSize, sampleSize).data;

    let sumR = 0, sumG = 0, sumB = 0;
    const count = sampleSize * sampleSize;
    for (let i = 0; i < data.length; i += 4) {
      sumR += data[i];
      sumG += data[i + 1];
      sumB += data[i + 2];
    }

    const avgR = sumR / count / 255;
    const avgG = sumG / count / 255;
    const avgB = sumB / count / 255;
    // 感知亮度（人眼对绿色最敏感）
    const brightness = avgR * 0.299 + avgG * 0.587 + avgB * 0.114;

    return { brightness, r: avgR, g: avgG, b: avgB };
  }

  /**
   * 柱面曲率变形绘制纹理
   *
   * 将纹理沿宽度方向切分为 N 个竖条，每个竖条按抛物线缩放宽度，
   * 模拟指甲的圆柱形曲面。边缘的竖条更窄（透视压缩），中心更宽。
   */
  function drawCurvedTexture(
    ctx: CanvasRenderingContext2D,
    tex: ImageBitmap,
    nl: number,
    nw: number
  ) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;
    const strips = CURVATURE_STRIPS;
    const stripW = nw / strips;

    for (let i = 0; i < strips; i++) {
      // 归一化 x 坐标（-1 到 1）
      const u = (i + 0.5) / strips; // 0..1
      const nx = u * 2 - 1;          // -1..1

      // 抛物线宽度缩放：中心=1，边缘=cos(arc)
      const cosTheta = Math.cos(nx * CURVATURE_STRENGTH * Math.PI * 0.5);
      const widthScale = Math.max(0.3, cosTheta);

      // 该竖条在屏幕上的位置和宽度
      const sx = -hw + i * stripW;
      const sw = stripW * widthScale;

      // 从纹理中采样对应竖条
      const texSx = (tex.width * i) / strips;
      const texSw = tex.width / strips;

      ctx.drawImage(
        tex,
        texSx, 0, texSw, tex.height,
        sx, -hl, sw, nl
      );
    }
  }

  /**
   * 绘制材质细节层（在纹理之上叠加）
   *
   * 包含：
   *   1. 菲涅尔反射 — 边缘更亮（模拟指甲曲面边缘的高反射）
   *   2. 颗粒纹理 — 微小噪点模拟指甲表面微观纹理
   *   3. 边缘暗角 — 指甲根部稍暗
   */
  function drawMaterialDetails(
    ctx: CanvasRenderingContext2D,
    nl: number,
    nw: number,
    envBrightness: number,
    fingerIdx: number = 2
  ) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;

    // ── 1. 菲涅尔反射（边缘高亮）──
    // 沿宽度方向的渐变：中心暗，边缘亮
    const fresnelGrad = ctx.createLinearGradient(-hw, 0, hw, 0);
    fresnelGrad.addColorStop(0, "rgba(255,255,255,0.28)");
    fresnelGrad.addColorStop(0.25, "rgba(255,255,255,0.05)");
    fresnelGrad.addColorStop(0.5, "rgba(255,255,255,0.0)");
    fresnelGrad.addColorStop(0.75, "rgba(255,255,255,0.05)");
    fresnelGrad.addColorStop(1, "rgba(255,255,255,0.28)");

    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx);
    ctx.clip();
    ctx.fillStyle = fresnelGrad;
    ctx.globalAlpha = 0.6 * envBrightness;
    ctx.fillRect(-hw, -hl, nw, nl);
    ctx.restore();

    // ── 2. 颗粒纹理（微观表面）──
    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx);
    ctx.clip();

    // 用 ImageData 生成随机噪点
    const grainCanvas = new OffscreenCanvas(Math.ceil(nw), Math.ceil(nl));
    const gctx = grainCanvas.getContext("2d");
    if (gctx) {
      const imgData = gctx.createImageData(grainCanvas.width, grainCanvas.height);
      for (let i = 0; i < imgData.data.length; i += 4) {
        const noise = 128 + (Math.random() - 0.5) * 30;
        imgData.data[i] = noise;
        imgData.data[i + 1] = noise;
        imgData.data[i + 2] = noise;
        imgData.data[i + 3] = 18; // 低 alpha
      }
      gctx.putImageData(imgData, 0, 0);
      ctx.globalAlpha = 0.35;
      ctx.drawImage(grainCanvas, -hw, -hl, nw, nl);
    }
    ctx.restore();

    // ── 3. 根部暗角 ──
    const vignetteGrad = ctx.createLinearGradient(0, -hl, 0, hl);
    vignetteGrad.addColorStop(0, "rgba(0,0,0,0)");
    vignetteGrad.addColorStop(0.6, "rgba(0,0,0,0)");
    vignetteGrad.addColorStop(1, "rgba(0,0,0,0.25)");

    ctx.save();
    drawNailShape(ctx, nl, nw);
    ctx.clip();
    ctx.fillStyle = vignetteGrad;
    ctx.globalAlpha = 1;
    ctx.fillRect(-hw, -hl, nw, nl);
    ctx.restore();
  }

  /**
   * 绘制高光（镜面反射）
   *
   * 三层高光系统：
   *   1. 主高光 — 纵向椭圆，模拟光源在指甲中央的镜面反射
   *   2. 指尖高光 — 指尖边缘的细亮线（自由缘反光）
   *   3. 根部微光 — 甲上皮附近的柔和散射
   */
  function drawSpecularHighlight(
    ctx: CanvasRenderingContext2D,
    nl: number,
    nw: number,
    envBrightness: number,
    fingerIdx: number = 2
  ) {
    const hl = nl * 0.5;
    const hw = nw * 0.5;

    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx);
    ctx.clip();

    // ── 主高光（镜面反射条）──
    const specAlpha = 0.18 + envBrightness * 0.22;
    ctx.globalAlpha = specAlpha;

    // 纵向渐变高光（上亮下暗）
    const specGrad = ctx.createLinearGradient(0, -hl, 0, hl);
    specGrad.addColorStop(0, "rgba(255,255,255,0.9)");
    specGrad.addColorStop(0.3, "rgba(255,255,255,0.6)");
    specGrad.addColorStop(0.7, "rgba(255,255,255,0.15)");
    specGrad.addColorStop(1, "rgba(255,255,255,0.0)");

    ctx.fillStyle = specGrad;
    ctx.beginPath();
    ctx.ellipse(-hw * 0.25, -hl * 0.05, hl * 0.38, hw * 0.12, 0, 0, Math.PI * 2);
    ctx.fill();

    // ── 指尖高光（自由缘细亮线）──
    ctx.globalAlpha = 0.12 + envBrightness * 0.1;
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.ellipse(0, -hl + hl * 0.06, hl * 0.15, hw * 0.55, 0, 0, Math.PI * 2);
    ctx.fill();

    // ── 根部微光 ──
    ctx.globalAlpha = 0.06 + envBrightness * 0.04;
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.ellipse(0, hl * 0.6, hl * 0.12, hw * 0.4, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
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
    handedness: "Left" | "Right" | null
  ): { render: boolean; confidence: "high" | "low" | "none"; reason: string } {
    // 边界检查：手部出画面
    const palmPts = [lm[0], lm[5], lm[9], lm[17]];
    const outOfFrame = palmPts.some(
      (p) =>
        p.x < OUT_OF_FRAME_THRESHOLD ||
        p.x > 1 - OUT_OF_FRAME_THRESHOLD ||
        p.y < OUT_OF_FRAME_THRESHOLD ||
        p.y > 1 - OUT_OF_FRAME_THRESHOLD
    );
    if (outOfFrame) {
      return { render: false, confidence: "none", reason: "手部出画面" };
    }

    // ── 方案 A：叉积法向量（基于 x/y，精度最高）──
    const v5x = lm[5].x - lm[0].x;
    const v5y = lm[5].y - lm[0].y;
    const v17x = lm[17].x - lm[0].x;
    const v17y = lm[17].y - lm[0].y;
    const crossZ = v5x * v17y - v5y * v17x;

    let isDorsumByCross = false;
    let isPalmByCross = false;
    if (handedness === "Right") {
      isDorsumByCross = crossZ < -CROSS_PRODUCT_Z_THRESHOLD_DORSUM;
      isPalmByCross = crossZ > CROSS_PRODUCT_Z_THRESHOLD_PALM;
    } else if (handedness === "Left") {
      isDorsumByCross = crossZ > CROSS_PRODUCT_Z_THRESHOLD_DORSUM;
      isPalmByCross = crossZ < -CROSS_PRODUCT_Z_THRESHOLD_PALM;
    }

    // ── 方案 B：深度差判断（z 坐标）──
    // 手心判定灵敏（低阈值），手背判定严格（高阈值）
    const isDorsumByDepth = smoothDepthDiff < -DEPTH_DIFF_THRESHOLD_DORSUM;
    const isPalmByDepth = smoothDepthDiff > DEPTH_DIFF_THRESHOLD_PALM;

    // ── 方案 C：4 指投票（排除拇指，z 坐标）──
    let dorsumVotes = 0;
    let palmVotes = 0;
    for (const f of VOTE_FINGERS) {
      const dz = lm[TIPS[f]].z - lm[PIPS[f]].z;
      if (dz < -FINGER_Z_VOTE_THRESHOLD_DORSUM) dorsumVotes++;
      else if (dz > FINGER_Z_VOTE_THRESHOLD_PALM) palmVotes++;
    }
    const isDorsumByVote = dorsumVotes >= 3;
    const isPalmByVote = palmVotes >= 3;

    // ── 方案 D：拇指位置辅助验证（基于 x 坐标，精度高）──
    const palmCenterX = (lm[0].x + lm[5].x + lm[9].x + lm[17].x) / 4;
    const thumbOffsetX = lm[4].x - palmCenterX;
    let isDorsumByThumb = false;
    let isPalmByThumb = false;
    if (handedness === "Right") {
      isDorsumByThumb = thumbOffsetX > THUMB_X_THRESHOLD;
      isPalmByThumb = thumbOffsetX < -THUMB_X_THRESHOLD;
    } else if (handedness === "Left") {
      isDorsumByThumb = thumbOffsetX < -THUMB_X_THRESHOLD;
      isPalmByThumb = thumbOffsetX > THUMB_X_THRESHOLD;
    }

    // ── 融合决策：手心严格阻止，其他都渲染 ──
    // 手心判定灵敏（低阈值），只要检测到手心就阻止
    // 手背/侧手/过渡态都渲染
    const dorsumScore =
      (isDorsumByCross ? 2 : 0) +
      (isDorsumByThumb ? 1 : 0) +
      (isDorsumByDepth ? 1 : 0) +
      (isDorsumByVote ? 1 : 0);
    const palmScore =
      (isPalmByCross ? 2 : 0) +
      (isPalmByThumb ? 1 : 0) +
      (isPalmByDepth ? 1 : 0) +
      (isPalmByVote ? 1 : 0);

    // 手心判定：只要有明显手心信号就阻止渲染
    if (palmScore >= 2) {
      return { render: false, confidence: "high", reason: "检测到手心" };
    }
    // 叉积单独判定手心（叉积是最可靠的 x/y 平面信号）
    if (isPalmByCross && palmScore >= 1) {
      return { render: false, confidence: "high", reason: "叉积+辅助：手心" };
    }
    // 其他所有情况都渲染
    if (dorsumScore > 0) {
      return { render: true, confidence: "high", reason: "检测到手背特征" };
    }
    return {
      render: true,
      confidence: "low",
      reason: `非手心态 d${dorsumScore}/p${palmScore}`,
    };
  }

  /**
   * 三信号融合逐指指甲可见性判定
   *
   * 使用三个独立信号并投票决定手指指甲是否可见：
   *   信号 A — TIP.z vs DIP.z（z 深度差，传统方法改进）
   *   信号 B — TIP.z vs PIP.z（不同关节参考，印证 A）
   *   信号 C — 透视缩短比 len2D/len3D（基于 x/y 几何，精度最高）
   *
   * 投票策略：强否定优先 + 多数投票
   */
  function computeFingerVisibility(
    lm: Landmark[],
    fingerIdx: number,
    s: {
      tip: { x: number; y: number; z: number };
      dip: { x: number; y: number; z: number };
      pip: { x: number; y: number; z: number };
    }
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

    // ── 强否定：z 差 + 几何同时否定 → 手心侧 → 不可见 ──
    if (!sigA && !sigC) return false;

    // ── 多数投票：≥ 2 信号认可 → 可见 ──
    const votes = [sigA, sigB, sigC].filter(Boolean).length;
    return votes >= 2;
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
    video: HTMLVideoElement
  ) {
    for (let f = 0; f < 5; f++) {
      const rawTip = lm[TIPS[f]];
      const rawDip = lm[DIPS[f]];
      const rawPip = lm[PIPS[f]];
      const color = colors[f] || "#E8A0BF";
      if (!rawTip || !rawDip) continue;

      // ── 时序平滑（先平滑关键点，再用平滑值做可见性判定）──
      const s = smoothRef.current[f];
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

      // ── 三信号融合可见性判定（使用平滑后的值）──
      // 手心侧的手指不贴图；逐指独立判定支持混合态
      const rawVis = computeFingerVisibility(lm, f, s);
      visibleSmoothRef.current[f] = ema(
        visibleSmoothRef.current[f],
        rawVis ? 1 : 0,
        VISIBILITY_EMA_ALPHA
      );
      if (visibleSmoothRef.current[f] < VISIBILITY_SMOOTH_THRESHOLD) continue;

      // ── z 轴深度缩放 ──
      const zScale = Math.max(0.7, Math.min(1.5, 1 - s.tip.z * 0.6));

      // ── 方向向量 ──
      let fx: number, fy: number;
      if (rawPip) {
        const px = s.pip.x * w, py = s.pip.y * h;
        const dx = s.dip.x * w, dy = s.dip.y * h;
        fx = dx - px; fy = dy - py;
      } else {
        const tx = s.tip.x * w, ty = s.tip.y * h;
        const dx = s.dip.x * w, dy = s.dip.y * h;
        fx = tx - dx; fy = ty - dy;
      }

      const rawLen = Math.sqrt(fx * fx + fy * fy);
      if (rawLen < 5) continue;

      const len = rawLen * zScale;
      const a = Math.atan2(fy, fx);
      const nl = len * FINGER_LENGTH_RATIOS[f];
      const nw = len * FINGER_WIDTH_RATIOS[f];

      const tx = s.tip.x * w;
      const ty = s.tip.y * h;
      const cx = tx - (fx / rawLen) * (len * TIP_OFFSET_RATIO);
      const cy = ty - (fy / rawLen) * (len * TIP_OFFSET_RATIO);

      // ── 环境光照采样 ──
      const env = sampleEnvLight(video, cx, cy, w, h);

      // ── 第一层：底色/纹理（带柱面曲率变形）──
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(a);

      const tex = currentMode === "texture" ? textures?.[f] : null;

      if (tex) {
        // 纹理模式：柱面曲率变形
        drawCurvedTexture(ctx, tex, nl, nw);
      } else {
        // 纯色模式：填充指甲形状（使用逐指形状参数）
        drawNailShape(ctx, nl, nw, f);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.85;
        ctx.fill();
      }

      ctx.restore();

      // ── 第二层：材质细节（菲涅尔 + 颗粒 + 暗角）──
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(a);
      drawMaterialDetails(ctx, nl, nw, env.brightness, f);
      ctx.restore();

      // ── 第三层：镜面高光 ──
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(a);
      drawSpecularHighlight(ctx, nl, nw, env.brightness, f);
      ctx.restore();
    }
  }

  useEffect(() => {
    // 同步 nailColors 到 ref（在 effect 内更新 ref 是安全的）
    colRef.current = nailColors;
  }, [nailColors]);

  // 自动启动改为手动启动（移动端需要用户手势触发摄像头权限）
  const [userStarted, setUserStarted] = useState(false);
  const startBtnRef = useRef<HTMLButtonElement>(null);

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
    if (!userStarted) return; // 等待用户点击按钮
    let dead = false;
    let handsInst: HandsInstance | null = null;
    let mediaStream: MediaStream | null = null;
    let rafLoop = 0;

    async function start() {
      try {
        // ── 步骤0: 检查浏览器能力 ──
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          setStatus("error");
          setStatusMsg("浏览器不支持摄像头 API，请使用 Chrome 或 Safari");
          log("❌ navigator.mediaDevices 不可用");
          return;
        }

        // ── 步骤1: 加载 CDN 脚本（带超时）──
        setStatus("loading");
        setStatusMsg("加载 MediaPipe 脚本...");
        log("1/7 加载 hands.js...");

        const scriptTimeout = 15000;
        function loadScript(src: string, name: string): Promise<void> {
          return new Promise((resolve, reject) => {
            const s = document.createElement("script");
            s.src = src;
            s.crossOrigin = "anonymous";
            const timer = setTimeout(() => {
              reject(new Error(name + " 加载超时（15s），请检查网络"));
            }, scriptTimeout);
            s.onload = () => {
              clearTimeout(timer);
              log("  " + name + " 加载完成 ✅");
              resolve();
            };
            s.onerror = () => {
              clearTimeout(timer);
              reject(new Error(name + " 加载失败，可能是网络问题"));
            };
            document.head.appendChild(s);
          });
        }

        await loadScript(
          "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/hands.js",
          "hands.js"
        );
        if (dead) return;

        // camera_utils.js 不再需要（改用原生 getUserMedia + RAF）

        // ── 步骤2: 验证全局对象 ──
        log("2/7 验证全局对象...");
        const H = window.Hands;
        if (!H) {
          setStatus("error");
          setStatusMsg("Hands 模块未加载");
          log("❌ Hands 未注册到 window");
          return;
        }
        log("  Hands ✅");

        // ── 步骤3: 直接用 getUserMedia 获取摄像头（不用 Camera Utils）──
        setStatusMsg("请求摄像头权限...");
        log("3/7 请求摄像头权限...");

        const video = vref.current;
        if (!video) {
          setStatus("error");
          setStatusMsg("视频元素未初始化");
          log("❌ video ref 为空");
          return;
        }

        // 竖屏 480x640（3:4）匹配 CSS aspect-[3/4]，避免 canvas 拉伸导致贴图错位
        let stream: MediaStream;
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user", width: { ideal: 480 }, height: { ideal: 640 } },
            audio: false,
          });
        } catch (camErr) {
          // 降级：不指定 facingMode
          log("  首次尝试失败，降级尝试...");
          try {
            stream = await navigator.mediaDevices.getUserMedia({
              video: { width: { ideal: 480 }, height: { ideal: 640 } },
              audio: false,
            });
          } catch (camErr2) {
            // 再降级：完全无约束
            log("  二次降级尝试...");
            try {
              stream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: false,
              });
            } catch (camErr3) {
              const msg = camErr3 instanceof Error ? camErr3.message : String(camErr3);
              log("❌ 摄像头获取失败: " + msg);
              setStatus("error");
              if (msg.includes("Permission") || msg.includes("permission") || msg.includes("denied") || msg.includes("NotAllowed")) {
                setStatusMsg("摄像头权限被拒绝。请在浏览器设置 → 权限中允许摄像头访问");
              } else if (msg.includes("NotFound") || msg.includes("device")) {
                setStatusMsg("未找到摄像头设备");
              } else if (msg.includes("NotReadable") || msg.includes("busy")) {
                setStatusMsg("摄像头被其他应用占用，请关闭后重试");
              } else {
                setStatusMsg("摄像头不可用: " + msg.slice(0, 50));
              }
              return;
            }
          }
        }
        if (dead) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        mediaStream = stream;
        log("  摄像头获取成功 ✅");

        // 绑定流到 video 元素
        video.srcObject = stream;
        log("  等待视频就绪...");
        await new Promise<void>((resolve, reject) => {
          const timeout = setTimeout(() => {
            reject(new Error("视频加载超时（10s）"));
          }, 10000);
          video.onloadedmetadata = () => {
            clearTimeout(timeout);
            log("  视频就绪 " + video.videoWidth + "x" + video.videoHeight + " ✅");
            resolve();
          };
          video.onerror = () => {
            clearTimeout(timeout);
            reject(new Error("视频加载失败"));
          };
        });
        await video.play().catch((e) => {
          log("  ⚠️ video.play() 警告: " + (e instanceof Error ? e.message : String(e)));
        });
        // 额外等待一帧确保 video 真正开始播放
        await new Promise<void>((resolve) => {
          if (video.readyState >= 3) {
            resolve();
          } else {
            video.oncanplay = () => resolve();
            setTimeout(resolve, 2000); // fallback
          }
        });
        log("  视频播放中 readyState=" + video.readyState + " ✅");
        if (dead) return;

        // ── 步骤4: 创建 Hands 实例 ──
        setStatusMsg("初始化手部识别...");
        log("4/7 创建 Hands 实例...");

        handsInst = new H({
          locateFile: (f: string) =>
            "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/" + f,
        });
        handsInst.setOptions({
          maxNumHands: 1,
          modelComplexity: 0,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });

        // ── 步骤5: 注册 onResults ──
        log("5/7 注册 onResults...");
        handsInst.onResults((res: HandResults) => {
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
          ctx.clearRect(0, 0, cvs.width, cvs.height);

          // ── object-cover 坐标变换 ──
          // video 元素用 object-cover 显示，会裁剪视频以填充容器
          // landmarks 是基于原始视频帧的归一化坐标 [0,1]
          // 需要变换到 canvas 显示坐标
          const vw = video.videoWidth;
          const vh = video.videoHeight;
          const containerRatio = cvs.width / cvs.height;
          const videoRatio = vw / vh;
          let scale = 1, offsetX = 0, offsetY = 0;
          if (videoRatio > containerRatio) {
            // 视频更宽 → 左右裁剪
            scale = cvs.height / vh;
            offsetX = -(vw * scale - cvs.width) / 2;
          } else {
            // 视频更高 → 上下裁剪
            scale = cvs.width / vw;
            offsetY = -(vh * scale - cvs.height) / 2;
          }
          // 变换函数：归一化坐标 → canvas 像素坐标
          const tx2px = (nx: number) => nx * vw * scale + offsetX;
          const ty2py = (ny: number) => ny * vh * scale + offsetY;

          if (res.multiHandLandmarks?.length) {
            setHandCnt(res.multiHandLandmarks.length);
            for (let h = 0; h < res.multiHandLandmarks.length; h++) {
              const lmRaw = res.multiHandLandmarks[h];
              const handedness: "Left" | "Right" | null =
                res.multiHandedness?.[h]?.label ?? null;

              // 同步左右手标识到 UI
              setHandLabel(handedness === "Right" ? "右手" : handedness === "Left" ? "左手" : null);

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

              const decision = shouldRenderNails(lm, smoothDepthDiff, handedness);

              // 更新 UI 朝向指示器
              if (decision.reason.includes("手心")) {
                setOrientation("palm");
              } else if (decision.reason.includes("手背") || decision.reason.includes("非手心")) {
                setOrientation("dorsum");
              } else {
                setOrientation("ambiguous");
              }

              // 全局渲染门控：手心朝镜头时完全跳过贴图
              // 只有手背/侧手/模糊态时才进入 paintNails 做逐指精细可见性判定
              if (decision.render) {
                paintNails(
                  ctx, lm, colRef.current, texRef.current,
                  modeRef.current, cvs.width, cvs.height, video
                );
              }

              // 同步逐指可见性到 UI（从平滑值读取，阈值 0.5 判定显隐）
              if (decision.render) {
                const vis: boolean[] = [];
                for (let fi = 0; fi < 5; fi++) {
                  vis.push(visibleSmoothRef.current[fi] >= VISIBILITY_SMOOTH_THRESHOLD);
                }
                setFingerVisible(vis);
              } else {
                setFingerVisible([false, false, false, false, false]);
              }
            }
          } else {
            setHandCnt(0);
            setOrientation("none");
            setFingerVisible([false, false, false, false, false]);
          }
        });

        // ── 步骤6: 用 requestAnimationFrame 驱动推理（替代 Camera Utils）──
        log("6/7 启动推理循环...");
        let sending = false;
        async function loop() {
          if (dead || !handsInst || !video) return;
          if (!sending && video.readyState >= 2) {
            sending = true;
            try {
              await handsInst.send({ image: video });
            } catch {
              // 忽略单帧错误
            }
            sending = false;
          }
          rafLoop = requestAnimationFrame(loop);
        }
        rafLoop = requestAnimationFrame(loop);

        // ── 步骤7: 就绪 ──
        setStatus("ready");
        setStatusMsg("就绪");
        log("7/7 系统就绪 ✅");
      } catch (err) {
        const m = err instanceof Error ? err.message : String(err);
        log("❌ " + m);
        if (!dead) {
          setStatus("error");
          setStatusMsg(m.includes("permission") || m.includes("权限") ? "摄像头权限被拒绝" : m.slice(0, 60));
        }
      }
    }

    start();
    return () => {
      dead = true;
      cancelAnimationFrame(rafLoop);
      try { handsInst?.close(); } catch {}
      if (mediaStream) {
        mediaStream.getTracks().forEach((t) => t.stop());
      }
    };
  }, [userStarted]);

  return (
    <div className="relative w-full max-w-[480px] mx-auto rounded-2xl overflow-hidden bg-black shadow-lg">
      <video
        ref={vref}
        playsInline
        muted
        className="w-full aspect-[3/4] object-cover"
        style={{ transform: "scaleX(-1)" }}
      />
      <canvas
        ref={cref}
        className="absolute inset-0 w-full h-full pointer-events-none"
        style={{ transform: "scaleX(-1)" }}
      />

      {/* 未启动时显示开始按钮 */}
      {!userStarted && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-black/80 text-white">
          <button
            ref={startBtnRef}
            type="button"
            className="px-8 py-4 bg-gradient-to-r from-pink-400 to-rose-500 rounded-full text-lg font-bold shadow-lg active:scale-95 transition-transform"
            style={{ touchAction: "manipulation", minHeight: "60px" }}
          >
            📷 开启摄像头
          </button>
          <p className="text-xs text-gray-300 mt-4 px-6 text-center max-w-xs">
            点击后浏览器会请求摄像头权限，请允许
          </p>
          {diag.length > 0 && (
            <div className="mt-4 w-full max-w-xs bg-black/60 rounded-lg p-2 max-h-20 overflow-y-auto border border-pink-500/20">
              {diag.map((d, i) => (
                <p key={i} className="text-[9px] font-mono leading-tight mb-0.5 text-gray-300">{d}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 诊断面板 — 始终显示（调试阶段） */}
      {userStarted && status !== "ready" && (
        <div className="absolute top-1 left-1 right-1 z-20 bg-black/80 rounded-lg p-2 max-h-40 overflow-y-auto border border-pink-500/30">
          {diag.map((d, i) => (
            <p
              key={i}
              className={`text-[9px] font-mono leading-tight mb-0.5 ${
                d.includes("❌")
                  ? "text-red-300"
                  : d.includes("✅")
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
      )}

      {/* 非 ready 遮罩 */}
      {userStarted && status !== "ready" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/70 text-white">
          <span className="text-4xl mb-3">&#9203;</span>
          <p className="text-sm px-6 text-center">{statusMsg}</p>
          <div className="mt-4 w-32 h-1 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full w-3/5 bg-[#E8A0BF] rounded-full animate-pulse" />
          </div>
        </div>
      )}

      {/* 手部状态 + 朝向指示 + 逐指可见性 */}
      {status === "ready" && (
        <div className="absolute bottom-0 left-0 right-0 pb-3 text-center pointer-events-none z-10 flex flex-col items-center gap-1">
          {handCnt > 0 && orientation !== "none" && (
            <>
              {/* 朝向 + 左右手 */}
              <span
                className={`inline-block text-xs px-3 py-1 rounded-full backdrop-blur-sm ${
                  orientation === "dorsum"
                    ? "text-green-300 bg-green-900/40"
                    : orientation === "palm"
                      ? "text-orange-300 bg-orange-900/40"
                      : "text-gray-300 bg-gray-800/40"
                }`}
              >
                {orientation === "dorsum"
                  ? "🖐️"
                  : orientation === "palm"
                    ? "✋"
                    : "🤚"}{" "}
                {handLabel ? handLabel + " · " : ""}
                {orientation === "dorsum"
                  ? "手背"
                  : orientation === "palm"
                    ? "手心"
                    : "侧手"}
              </span>

              {/* 逐指可见性指示器 */}
              <div className="flex items-center gap-2 text-xs">
                {["拇","食","中","无","小"].map((name, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full backdrop-blur-sm ${
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
          <span className="inline-block text-xs text-white/70 bg-black/30 px-3 py-1 rounded-full backdrop-blur-sm">
            {handCnt > 0
              ? "检测到 " + handCnt + " 只手"
              : handCnt === 0
                ? "请将手放在摄像头前"
                : "等待检测..."}
          </span>
        </div>
      )}
    </div>
  );
}
