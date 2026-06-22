"use client";
import { useRef, useEffect, useState } from "react";

const TIPS = [4, 8, 12, 16, 20];
const DIPS = [3, 7, 11, 15, 19];

// MediaPipe 全局类型声明（CDN 注入）
interface Landmark {
  x: number;
  y: number;
  z: number;
}

interface HandResults {
  multiHandLandmarks?: Landmark[][];
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

interface CameraInstance {
  start: () => void;
}

interface CameraConstructor {
  new (
    video: HTMLVideoElement,
    opts: {
      onFrame: () => Promise<void>;
      width: number;
      height: number;
      facingMode: string;
    }
  ): CameraInstance;
}

declare global {
  interface Window {
    Hands?: HandsConstructor;
    Camera?: CameraConstructor;
  }
}

interface Props {
  nailColors: string[];
}

export function ArView({ nailColors }: Props) {
  const vref = useRef<HTMLVideoElement>(null);
  const cref = useRef<HTMLCanvasElement>(null);
  const colRef = useRef(nailColors);
  const [status, setStatus] = useState("init"); // init|loading|ready|error
  const [statusMsg, setStatusMsg] = useState("初始化...");
  const [handCnt, setHandCnt] = useState(-1); // -1=未检测, 0=无手, N=有手
  const [diag, setDiag] = useState<string[]>([]);

  const log = (m: string) => {
    console.log("[AR]", m);
    setDiag((p) => [...p.slice(-8), m]);
  };

  // 指甲绘制函数（纯函数，无副作用依赖）
  function paintNails(
    ctx: CanvasRenderingContext2D,
    lm: Landmark[],
    colors: string[],
    w: number,
    h: number
  ) {
    for (let f = 0; f < 5; f++) {
      const tip = lm[TIPS[f]],
        dip = lm[DIPS[f]],
        color = colors[f] || "#E8A0BF";
      if (!tip || !dip) continue;
      const tx = tip.x * w,
        ty = tip.y * h,
        dx = dip.x * w,
        dy = dip.y * h;
      const fx = tx - dx,
        fy = ty - dy,
        len = Math.sqrt(fx * fx + fy * fy);
      if (len < 5) continue;
      const a = Math.atan2(fy, fx),
        nl = len * 0.52,
        nw = len * 0.42;
      const cx = tx - (fx / len) * (len * 0.18),
        cy = ty - (fy / len) * (len * 0.18);
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(a);
      ctx.beginPath();
      ctx.ellipse(0, 0, nl * 0.5, nw * 0.5, 0, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.8;
      ctx.fill();
      ctx.globalAlpha = 0.4;
      ctx.fillStyle = "white";
      ctx.beginPath();
      ctx.ellipse(-nl * 0.05, -nw * 0.18, nl * 0.3, nw * 0.12, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  useEffect(() => {
    // 同步 nailColors 到 ref（在 effect 内更新 ref 是安全的）
    colRef.current = nailColors;
  }, [nailColors]);

  useEffect(() => {
    let dead = false;
    const rafId = 0;
    let handsInst: HandsInstance | null = null;

    async function start() {
      try {
        // ── 步骤1: 加载 CDN 脚本 ──
        setStatus("loading");
        setStatusMsg("加载 MediaPipe 脚本...");
        log("1/6 加载 hands.js...");

        await new Promise<void>((resolve, reject) => {
          const s = document.createElement("script");
          s.src =
            "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/hands.js";
          s.crossOrigin = "anonymous";
          s.onload = () => {
            log("  hands.js 加载完成 ✅");
            resolve();
          };
          s.onerror = () => reject(new Error("hands.js 加载失败"));
          document.head.appendChild(s);
        });
        if (dead) return;

        await new Promise<void>((resolve, reject) => {
          const s = document.createElement("script");
          s.src =
            "https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils@0.3.1675466862/camera_utils.js";
          s.crossOrigin = "anonymous";
          s.onload = () => {
            log("  camera_utils.js 加载完成 ✅");
            resolve();
          };
          s.onerror = () => reject(new Error("camera_utils.js 加载失败"));
          document.head.appendChild(s);
        });
        if (dead) return;

        // ── 步骤2: 验证全局对象 ──
        log("2/6 验证全局对象...");
        const H = window.Hands;
        const C = window.Camera;
        if (!H) {
          log("  ❌ Hands 未注册到 window");
          return;
        }
        if (!C) {
          log("  ❌ Camera 未注册到 window");
          return;
        }
        log("  Hands ✅ Camera ✅");

        // ── 步骤3: 创建 Hands 实例 + 摄像头 ──
        setStatusMsg("启动摄像头...");
        log("3/6 创建实例 + 获取摄像头...");

        handsInst = new H({
          locateFile: (f: string) =>
            "https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469240/" +
            f,
        });
        handsInst.setOptions({
          maxNumHands: 1,
          modelComplexity: 0,
          minDetectionConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });

        const video = vref.current;
        if (!video) {
          log("  ❌ video ref 为空");
          return;
        }

        // Camera 工具类会自动处理 getUserMedia
        log("  创建 Camera 实例...");
        const camera = new C(video, {
          onFrame: async () => {
            if (!handsInst) return;
            try {
              await handsInst.send({ image: video });
            } catch (e) {
              const msg = e instanceof Error ? e.message : String(e);
              log("send: " + msg.slice(0, 60));
            }
          },
          width: 480,
          height: 640,
          facingMode: "user",
        });
        log("  启动 Camera...");
        camera.start();

        // ── 步骤4: 注册结果回调 ──
        log("4/6 注册 onResults...");
        handsInst.onResults((res: HandResults) => {
          const cvs = cref.current;
          if (!cvs) return;
          const ctx = cvs.getContext("2d") as CanvasRenderingContext2D;
          if (!ctx) return;
          if (
            cvs.width !== video.videoWidth ||
            cvs.height !== video.videoHeight
          ) {
            cvs.width = video.videoWidth;
            cvs.height = video.videoHeight;
          }
          ctx.clearRect(0, 0, cvs.width, cvs.height);
          if (res.multiHandLandmarks?.length) {
            setHandCnt(res.multiHandLandmarks.length);
            for (
              let h = 0;
              h < res.multiHandLandmarks.length;
              h++
            ) {
              paintNails(
                ctx,
                res.multiHandLandmarks[h],
                colRef.current,
                cvs.width,
                cvs.height
              );
            }
          } else {
            setHandCnt(0);
          }
        });

        setStatus("ready");
        setStatusMsg("就绪");
        log("6/6 系统就绪 ✅");
      } catch (err) {
        const m = err instanceof Error ? err.message : String(err);
        log("❌ " + m);
        if (!dead) {
          setStatus("error");
          setStatusMsg(
            m.includes("permission") ? "权限被拒绝" : "启动失败"
          );
        }
      }
    }

    start();
    return () => {
      dead = true;
      cancelAnimationFrame(rafId);
      try {
        handsInst?.close();
      } catch {
        // ignore
      }
    };
  }, []);

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

      {/* 诊断面板 — 仅非 ready 状态显示 */}
      {status !== "ready" && (
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
      {status !== "ready" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/70 text-white">
          <span className="text-4xl mb-3">&#9203;</span>
          <p className="text-sm px-6 text-center">{statusMsg}</p>
          <div className="mt-4 w-32 h-1 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full w-3/5 bg-[#E8A0BF] rounded-full animate-pulse" />
          </div>
        </div>
      )}

      {/* 手部状态 */}
      {status === "ready" && (
        <div className="absolute bottom-0 left-0 right-0 pb-3 text-center pointer-events-none z-10">
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
