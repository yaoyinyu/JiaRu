"use client";

import { useRef, useEffect, useState } from "react";
import Link from "next/link";

const BTNS = [
  { icon: "📱", label: "AR 实时穿戴", desc: "打开摄像头，实时预览美甲效果", href: "/ar-tryon" },
  { icon: "✨", label: "AI 贴合穿戴", desc: "AI智能生成设计，贴合到手部照片", href: "/ai-generate" },
];

export default function Home() {
  const containerRef = useRef<HTMLDivElement>(null);
  const spotlightRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<(HTMLAnchorElement | null)[]>([]);

  // 物理状态
  const st = useRef({
    cursor: { x: -999, y: -999 },
    light: { x: -999, y: -999 },
    captured: -1,
    captureP: 0,
    captureFrom: { x: -999, y: -999 },
    btnTilt: [{ x: 0, y: 0 }, { x: 0, y: 0 }],
    btnGlow: [0, 0],
    clickLock: -1, // 正在点击动画的按钮索引，-1=无
  });

  // 弹性缓出：产生过冲回弹
  function elasticOut(t: number) {
    if (t <= 0 || t >= 1) return t;
    return Math.pow(2, -9 * t) * Math.sin((t - 0.075) * (2 * Math.PI) / 0.35) + 1;
  }

  const [showHint, setShowHint] = useState(true);

  // ---------- 按需运行的指针动画 ----------
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let rafId = 0;
    let disposed = false;
    let layoutDirty = true;
    let hintDismissed = false;
    let buttonCenters: { x: number; y: number }[] = [];

    function measureButtons() {
      buttonCenters = btnRefs.current.map((el) => {
        if (!el) return { x: -999, y: -999 };
        const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      });
      layoutDirty = false;
    }

    function scheduleTick() {
      if (!disposed && rafId === 0) {
        rafId = requestAnimationFrame(tick);
      }
    }

    function tick() {
      rafId = 0;
      if (disposed) return;

      const s = st.current;
      const sp = spotlightRef.current;
      const gw = glowRef.current;
      if (!sp || !gw) return;
      if (layoutDirty) measureButtons();

      const cx = s.cursor.x;
      const cy = s.cursor.y;
      let needsAnotherFrame = false;
      let captured = -1;
      let minDist = Infinity;

      for (let i = 0; i < BTNS.length; i++) {
        const center = buttonCenters[i];
        if (!center) continue;
        const cdx = cx - center.x;
        const cdy = cy - center.y;
        const cDist = Math.hypot(cdx, cdy);
        if (cDist < minDist) minDist = cDist;
        if (cDist < 100 || (s.captured === i && cDist < 160)) {
          captured = i;
          break;
        }
      }

      if (captured >= 0) {
        if (s.captured < 0) {
          s.captured = captured;
          s.captureP = 0;
          s.captureFrom.x = s.light.x;
          s.captureFrom.y = s.light.y;
        }
      } else if (s.captured >= 0) {
        s.captured = -1;
        s.captureP = 0;
      }

      if (s.captured >= 0) {
        const el = btnRefs.current[s.captured];
        const center = buttonCenters[s.captured];
        if (el && center) {
          s.captureP = Math.min(s.captureP + 0.05, 1);
          needsAnotherFrame ||= s.captureP < 1;
          const k = elasticOut(s.captureP);
          s.light.x = s.captureFrom.x + (center.x - s.captureFrom.x) * k;
          s.light.y = s.captureFrom.y + (center.y - s.captureFrom.y) * k;

          if (s.clickLock !== s.captured) {
            const btnScale = 1 + Math.min(k, 1) * 0.05 + Math.max(0, k - 1) * 0.03;
            el.style.transform = "scale(" + btnScale + ")";
            el.style.boxShadow = "0 0 " + (20 + Math.min(k, 1) * 60) + "px rgba(232,160,191,"
              + (0.3 + Math.min(k, 1) * 0.6) + ")";
            if (s.captured === 0) {
              el.style.boxShadow += ", inset 0 0 30px rgba(255,255,255," + (Math.min(k, 1) * 0.15) + ")";
            }
          }
        }
      } else {
        const deltaX = cx - s.light.x;
        const deltaY = cy - s.light.y;
        s.light.x += deltaX * 0.065;
        s.light.y += deltaY * 0.065;
        needsAnotherFrame ||= Math.abs(deltaX) > 0.25 || Math.abs(deltaY) > 0.25;
      }

      for (let i = 0; i < BTNS.length; i++) {
        if (i === s.captured || i === s.clickLock) continue;
        const el = btnRefs.current[i];
        const center = buttonCenters[i];
        if (!el || !center) continue;
        const dx = s.light.x - center.x;
        const dy = s.light.y - center.y;
        const dist = Math.hypot(dx, dy);
        const field = 200;

        if (dist > 0 && dist < field) {
          const force = 1 - dist / field;
          const ease = force * force * (3 - 2 * force);
          const tiltMag = ease * 10;
          s.btnTilt[i].x += (-dx / dist * tiltMag - s.btnTilt[i].x) * 0.1;
          s.btnTilt[i].y += (-dy / dist * tiltMag - s.btnTilt[i].y) * 0.1;
          s.btnGlow[i] += (ease - s.btnGlow[i]) * 0.12;
        } else {
          s.btnTilt[i].x += (0 - s.btnTilt[i].x) * 0.08;
          s.btnTilt[i].y += (0 - s.btnTilt[i].y) * 0.08;
          s.btnGlow[i] += (0 - s.btnGlow[i]) * 0.08;
        }

        const tiltX = s.btnTilt[i].x;
        const tiltY = s.btnTilt[i].y;
        const gl = s.btnGlow[i];
        needsAnotherFrame ||= Math.abs(tiltX) >= 0.3 || Math.abs(tiltY) >= 0.3 || gl >= 0.01;
        if (Math.abs(tiltX) < 0.3 && Math.abs(tiltY) < 0.3 && gl < 0.01) {
          el.style.transform = "";
          el.style.boxShadow = "";
        } else {
          el.style.transform = "translate(" + tiltX.toFixed(1) + "px, " + tiltY.toFixed(1) + "px)";
          el.style.boxShadow = i === 0
            ? "0 0 " + (20 + gl * 40) + "px rgba(232,160,191," + (0.25 + gl * 0.5) + ")"
            : "0 0 " + (10 + gl * 30) + "px rgba(232,160,191," + (0.1 + gl * 0.35) + ")";
        }
      }

      sp.style.transform = "translate(" + (s.light.x - 200) + "px, " + (s.light.y - 200) + "px)";
      if (s.captured >= 0) {
        const ease = 1 - Math.pow(1 - s.captureP, 3);
        sp.style.opacity = String(0.3 + ease * 0.5);
        sp.style.transform += " scale(" + (1 - ease * 0.35) + ")";
        gw.style.opacity = String(0.4 + ease * 0.4);
      } else {
        sp.style.opacity = String(Math.max(0.2, 0.45 - minDist * 0.001));
        gw.style.opacity = "0.4";
      }

      if (needsAnotherFrame) scheduleTick();
    }

    function move(e: PointerEvent) {
      st.current.cursor = { x: e.clientX, y: e.clientY };
      if (!hintDismissed) {
        hintDismissed = true;
        setShowHint(false);
      }
      scheduleTick();
    }

    function leave() {
      const s = st.current;
      s.cursor = { x: -999, y: -999 };
      s.light = { x: -999, y: -999 };
      s.captured = -1;
      s.captureP = 0;
      scheduleTick();
    }

    function invalidateLayout() {
      layoutDirty = true;
      scheduleTick();
    }

    const resizeObserver = new ResizeObserver(invalidateLayout);
    resizeObserver.observe(container);
    btnRefs.current.forEach((el) => {
      if (el) resizeObserver.observe(el);
    });
    container.addEventListener("pointermove", move, { passive: true });
    container.addEventListener("pointerleave", leave);
    window.addEventListener("resize", invalidateLayout);
    measureButtons();

    return () => {
      disposed = true;
      if (rafId !== 0) cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", move);
      container.removeEventListener("pointerleave", leave);
      window.removeEventListener("resize", invalidateLayout);
    };
  }, []);

  // 点击动画
  function handleClick(i: number) {
    return function(btn: HTMLAnchorElement) {
      st.current.clickLock = i;
      btn.style.transition = "transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s";
      btn.style.transform = "scale(0.94)";
      btn.style.boxShadow = "0 4px 12px rgba(232,160,191,0.3)";
      setTimeout(() => {
        btn.style.transform = "scale(1)";
        setTimeout(() => {
          btn.style.transition = "";
          btn.style.boxShadow = "";
          st.current.clickLock = -1;
        }, 250);
      }, 200);
    };
  }

  return (
    <div
      ref={containerRef}
      className="relative min-h-dvh bg-gradient-to-b from-[#FFF5F7] via-white to-[#FFF0F3] overflow-hidden flex flex-col select-none"
    >
      {/* 环境辉光 */}
      <div className="absolute inset-0 pointer-events-none">
        <div
          ref={glowRef}
          className="absolute inset-0 transition-opacity duration-500"
          style={{
            background: "radial-gradient(ellipse at 50% 40%, rgba(232,160,191,0.12) 0%, transparent 60%)",
            opacity: 0.4,
          }}
        />
        <div className="absolute -top-20 -right-20 w-80 h-80 bg-gradient-to-br from-[#E8A0BF]/15 to-transparent rounded-full blur-3xl" />
      </div>

      {/* 光标聚光灯 */}
      <div
        ref={spotlightRef}
        className="pointer-events-none fixed z-50 w-[400px] h-[400px] rounded-full"
        style={{
          background: "radial-gradient(circle at center, rgba(232,160,191,0.35) 0%, rgba(212,116,157,0.12) 35%, transparent 65%)",
          transform: "translate(-9999px, -9999px)",
          willChange: "transform, opacity",
        }}
      />

      {/* 顶部 */}
      <div className="relative z-10 pt-8 px-6">
        <div className="flex items-center justify-center gap-3">
          <span className="h-px w-12 bg-gradient-to-r from-transparent via-[#E8A0BF]/40 to-transparent" />
          <span className="text-[#E8A0BF]/40 text-xs tracking-[0.3em]">JIA RU</span>
          <span className="h-px w-12 bg-gradient-to-r from-transparent via-[#E8A0BF]/40 to-transparent" />
        </div>
      </div>

      {/* 主视觉 */}
      <div className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 pt-8 pb-6">
        <div className="relative mb-8">
          <div className="absolute inset-0 bg-gradient-to-b from-[#E8A0BF]/10 via-[#D4749D]/5 to-transparent rounded-full blur-2xl scale-150" />
          <div
            className="relative w-32 h-32 rounded-full bg-gradient-to-br from-[#FFF5F7] via-white to-[#FFE4EC] shadow-xl shadow-pink-200/30 flex items-center justify-center border border-white/60"
          >
            <div className="absolute inset-0 rounded-full bg-gradient-to-br from-white/40 to-transparent" />
            <span className="text-5xl relative z-10">💅</span>
          </div>
        </div>

        <h1 className="text-5xl font-bold text-[#4A4A4A] tracking-[0.08em] mb-2">
          甲如
        </h1>
        <p className="text-sm text-gray-400 tracking-[0.15em] mb-8">
          美甲试戴 · 如你所见
        </p>

        {/* 按钮 */}
        <div className="w-full max-w-xs flex flex-col gap-4">
          {BTNS.map((btn, i) => (
            <Link
              key={btn.href}
              ref={(el) => { btnRefs.current[i] = el; }}
              href={btn.href}
              onClick={(e) => handleClick(i)(e.currentTarget as HTMLAnchorElement)}
              className={
                "group relative overflow-hidden rounded-3xl p-5 will-change-transform " +
                (i === 0
                  ? "bg-gradient-to-br from-[#E8A0BF] to-[#D4749D] shadow-lg shadow-pink-200/40"
                  : "bg-white border border-pink-100 shadow-md shadow-pink-50")
              }
            >
              {i === 0 && (
                <>
                  <div className="absolute -top-6 -right-6 w-24 h-24 bg-white/10 rounded-full blur-xl" />
                  <div className="absolute -bottom-4 -left-4 w-16 h-16 bg-white/5 rounded-full blur-lg" />
                </>
              )}
              {i === 1 && (
                <div className="absolute -top-6 -right-6 w-24 h-24 bg-gradient-to-br from-[#E8A0BF]/5 to-transparent rounded-full blur-xl" />
              )}

              <div className="relative z-10 flex items-center gap-4">
                <span className="text-3xl">{btn.icon}</span>
                <div>
                  <h3 className={"font-bold text-lg " + (i === 0 ? "text-white" : "text-[#4A4A4A]")}>
                    {btn.label}
                  </h3>
                  <p className={"text-xs mt-0.5 " + (i === 0 ? "text-white/70" : "text-gray-400")}>
                    {btn.desc}
                  </p>
                </div>
                <span
                  className={
                    "ml-auto text-lg group-hover:translate-x-1 transition-transform duration-200 " +
                    (i === 0 ? "text-white/50" : "text-gray-300")
                  }
                >
                  →
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* 底部 */}
      <div className="relative z-10 pb-6 px-6">
        <div className="text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/60 backdrop-blur-sm border border-white/80 shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span className="text-xs text-gray-400">所有照片本地处理，不上传服务器</span>
          </div>
        </div>
      </div>

      {/* 提示 */}
      {showHint && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 text-xs text-gray-300 animate-bounce pointer-events-none">
          移动鼠标探索 ✨
        </div>
      )}
    </div>
  );
}
