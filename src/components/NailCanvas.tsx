"use client";

import { useRef, useState, useEffect } from "react";
import { Icon } from "@/components/Icon";
import {
  STROKE_STEP,
  interpolateStrokePoints,
  previewScale,
  strokeDots,
  type Stroke,
  type StrokePoint,
} from "@/lib/canvas/strokes";

interface NailCanvasProps {
  imageUrl: string;
  selectedColor?: string;
  nailColors?: string[];
  activeFinger?: number;
  brushSize: number;
}

function getCanvasContext(canvas: HTMLCanvasElement) {
  return canvas.getContext("2d", { willReadFrequently: true });
}

// 在指定位置画点（半径为该坐标系下的笔刷半径）——无组件状态依赖，模块级共享
function paintDot(ctx: CanvasRenderingContext2D, x: number, y: number, radius: number, color: string) {
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.7;
  ctx.fill();
  ctx.globalAlpha = 1.0;
}

// 按 scale 把一条笔画重放到指定 2D 上下文（预览 scale=1，导出 scale=outScale）
function paintStroke(ctx: CanvasRenderingContext2D, stroke: Stroke, scale: number) {
  const dots = strokeDots(stroke, scale, STROKE_STEP * scale);
  for (const dot of dots) {
    paintDot(ctx, dot.x, dot.y, stroke.size * scale, stroke.color);
  }
}

/**
 * 手绘编辑画布（2026-09-05 评审 #8 修复）：
 *  - 显示与输出分离：预览画布最长边 400/600，笔画按预览坐标记录；
 *    保存时用原图尺寸离屏重放全部笔画，4096×4096 上传图导出仍为原尺寸；
 *  - 重置 = 清空笔画重放原图基线，与撤销栈解耦（历史快照淘汰不再污染基线）；
 *  - 撤销 = 去掉最后一条笔画后全量重放，不再有 20 份快照的步数上限。
 */
export function NailCanvas({
  imageUrl,
  selectedColor,
  nailColors,
  activeFinger = 0,
  brushSize,
}: NailCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  // 笔画序列（预览坐标）：state 驱动按钮可用性，ref 供绘制/重放同步读取
  const strokesRef = useRef<Stroke[]>([]);
  const [strokeCount, setStrokeCount] = useState(0);
  // 原图尺寸 / 预览尺寸，导出重放时等比放大坐标与笔刷半径
  const outScaleRef = useRef(1);
  const activeStrokeRef = useRef<Stroke | null>(null);
  const lastPosRef = useRef<StrokePoint | null>(null);
  // 用 ref 存绘制函数，避免 React Compiler 问题（与原实现同思路）
  const redrawRef = useRef<() => void>(() => {});

  // 当前颜色：优先从 nailColors[activeFinger] 取，否则回退到 selectedColor
  const currentColor = nailColors
    ? nailColors[activeFinger] || "#E8A0BF"
    : selectedColor || "#E8A0BF";
  const selectedColorRef = useRef(currentColor);
  const brushSizeRef = useRef(brushSize);

  // 同步 ref（currentColor 和 brushSize 在 props 变化时更新）
  useEffect(() => {
    selectedColorRef.current = currentColor;
  }, [currentColor]);

  useEffect(() => {
    brushSizeRef.current = brushSize;
  }, [brushSize]);

  // 重绘预览：原图基线 + 全部笔画（撤销/重置/新增共用这一条路径）
  useEffect(() => {
    redrawRef.current = () => {
      const canvas = canvasRef.current;
      const img = imageRef.current;
      if (!canvas || !img) return;
      const ctx = getCanvasContext(canvas);
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      for (const stroke of strokesRef.current) {
        paintStroke(ctx, stroke, 1);
      }
    };
  }, []);

  // 加载图片到 Canvas（预览尺寸），换图时清空笔画
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = getCanvasContext(canvas);
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      imageRef.current = img;
      const scale = previewScale(img.width, img.height);
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      outScaleRef.current = img.width / canvas.width;
      strokesRef.current = [];
      setStrokeCount(0);
      redrawRef.current();
    };
    img.src = imageUrl;
  }, [imageUrl]);

  // strokes 数量变化（撤销/重置/新增笔画）→ 全量重放预览
  useEffect(() => {
    redrawRef.current();
  }, [strokeCount]);

  // 获取鼠标/触摸在 Canvas 上的坐标（预览坐标系）
  const getPos = (e: React.MouseEvent | React.TouchEvent): StrokePoint | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
    const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
    return {
      x: (clientX - rect.left) * (canvas.width / rect.width),
      y: (clientY - rect.top) * (canvas.height / rect.height),
    };
  };

  const handleStart = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    const pos = getPos(e);
    if (!pos) return;
    activeStrokeRef.current = {
      color: selectedColorRef.current,
      size: brushSizeRef.current,
      points: [pos],
    };
    lastPosRef.current = pos;
    const canvas = canvasRef.current;
    const ctx = canvas ? getCanvasContext(canvas) : null;
    if (ctx) {
      paintDot(ctx, pos.x, pos.y, brushSizeRef.current, selectedColorRef.current);
    }
  };

  const handleMove = (e: React.MouseEvent | React.TouchEvent) => {
    const active = activeStrokeRef.current;
    if (!active || !lastPosRef.current) return;
    e.preventDefault();
    const pos = getPos(e);
    if (!pos) return;
    const canvas = canvasRef.current;
    const ctx = canvas ? getCanvasContext(canvas) : null;
    if (ctx) {
      // 与重放语义一致：上一位置到当前位置的插值段
      for (const dot of interpolateStrokePoints(lastPosRef.current, pos, STROKE_STEP)) {
        paintDot(ctx, dot.x, dot.y, active.size, active.color);
        active.points.push(dot);
      }
    }
    lastPosRef.current = pos;
  };

  const handleEnd = () => {
    const active = activeStrokeRef.current;
    if (!active) return;
    activeStrokeRef.current = null;
    lastPosRef.current = null;
    strokesRef.current = [...strokesRef.current, active];
    setStrokeCount(strokesRef.current.length);
  };

  // 撤销：去掉最后一条笔画，重放路径自动恢复（不再受历史快照队列限制）
  const handleUndo = () => {
    if (strokesRef.current.length === 0) return;
    strokesRef.current = strokesRef.current.slice(0, -1);
    setStrokeCount(strokesRef.current.length);
  };

  // 重置：清空笔画 → 重放即原图基线（与撤销栈彻底解耦）
  const handleReset = () => {
    if (strokesRef.current.length === 0) return;
    strokesRef.current = [];
    setStrokeCount(0);
  };

  // 保存到本地：原图尺寸离屏重放全部笔画（显示尺寸与输出尺寸分离）
  const handleSave = () => {
    const img = imageRef.current;
    if (!img) return;
    const out = document.createElement("canvas");
    out.width = img.width;
    out.height = img.height;
    const outCtx = out.getContext("2d");
    if (!outCtx) return;
    outCtx.drawImage(img, 0, 0, img.width, img.height);
    const scale = outScaleRef.current;
    for (const stroke of strokesRef.current) {
      paintStroke(outCtx, stroke, scale);
    }
    const link = document.createElement("a");
    link.download = `jiaru-${Date.now()}.png`;
    link.href = out.toDataURL("image/png");
    link.click();
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <canvas
        ref={canvasRef}
        className="w-full max-w-[640px] rounded-[22px] bg-white shadow-[0_18px_55px_rgba(75,52,63,.12)] touch-none"
        onMouseDown={handleStart}
        onMouseMove={handleMove}
        onMouseUp={handleEnd}
        onMouseLeave={handleEnd}
        onTouchStart={handleStart}
        onTouchMove={handleMove}
        onTouchEnd={handleEnd}
      />

      <div className="flex gap-3 w-full max-w-[640px]">
        <button
          onClick={handleUndo}
          disabled={strokeCount < 1}
          className="h-12 flex-1 rounded-2xl border border-pink-100 bg-white/80 text-sm font-medium text-[#71676C] shadow-sm transition-all hover:-translate-y-0.5 hover:bg-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="undo" className="h-4 w-4" />撤销</span>
        </button>
        <button
          onClick={handleReset}
          disabled={strokeCount < 1}
          className="h-12 flex-1 rounded-2xl border border-pink-100 bg-white/80 text-sm font-medium text-[#71676C] shadow-sm transition-all hover:-translate-y-0.5 hover:bg-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="reset" className="h-4 w-4" />重置</span>
        </button>
        <button
          onClick={handleSave}
          className="h-12 flex-1 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#C96591] text-sm font-medium text-white shadow-[0_10px_22px_rgba(207,111,153,.22)] transition-all hover:-translate-y-0.5 hover:shadow-[0_14px_28px_rgba(207,111,153,.3)] active:scale-95"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="save" className="h-4 w-4" />保存</span>
        </button>
      </div>
    </div>
  );
}
