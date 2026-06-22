"use client";

import { useRef, useState, useEffect } from "react";

interface Point {
  x: number;
  y: number;
  color: string;
  size: number;
}

interface NailCanvasProps {
  imageUrl: string;
  selectedColor?: string;
  nailColors?: string[];
  activeFinger?: number;
  brushSize: number;
}

export function NailCanvas({
  imageUrl,
  selectedColor,
  nailColors,
  activeFinger = 0,
  brushSize,
}: NailCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [history, setHistory] = useState<ImageData[]>([]);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const lastPosRef = useRef<Point | null>(null);

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

  // 保存历史（撤销用）— 用 ref 存储函数，避免 React Compiler 问题
  const saveHistoryRef = useRef<() => void>(() => {});

  // 加载图片到 Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      imageRef.current = img;
      const maxW = 400;
      const scale = Math.min(maxW / img.width, 600 / img.height, 1);
      canvas.width = img.width * scale;
      canvas.height = img.height * scale;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      // 保存初始状态
      saveHistoryRef.current();
    };
    img.src = imageUrl;
  }, [imageUrl]);

  // 定义 saveHistory 并存入 ref
  useEffect(() => {
    saveHistoryRef.current = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
      setHistory((prev) => [...prev.slice(-19), data]);
    };
  }, []);

  // 获取鼠标/触摸在 Canvas 上的坐标
  const getPos = (e: React.MouseEvent | React.TouchEvent): Point | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
    const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
    return {
      x: (clientX - rect.left) * (canvas.width / rect.width),
      y: (clientY - rect.top) * (canvas.height / rect.height),
      color: selectedColorRef.current,
      size: brushSizeRef.current,
    };
  };

  // 在指定位置画点
  const drawDot = (pos: Point) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.beginPath();
    ctx.arc(pos.x, pos.y, pos.size, 0, Math.PI * 2);
    ctx.fillStyle = pos.color;
    ctx.globalAlpha = 0.7;
    ctx.fill();
    ctx.globalAlpha = 1.0;
  };

  // 画线
  const drawLine = (from: Point, to: Point) => {
    const dist = Math.sqrt((to.x - from.x) ** 2 + (to.y - from.y) ** 2);
    const steps = Math.max(Math.floor(dist / 5), 1);
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      drawDot({
        x: from.x + (to.x - from.x) * t,
        y: from.y + (to.y - from.y) * t,
        color: from.color,
        size: from.size,
      });
    }
  };

  const handleStart = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    setIsDrawing(true);
    const pos = getPos(e);
    if (pos) {
      lastPosRef.current = pos;
      drawDot(pos);
    }
  };

  const handleMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isDrawing) return;
    e.preventDefault();
    const pos = getPos(e);
    if (pos && lastPosRef.current) {
      drawLine(lastPosRef.current, pos);
    }
    lastPosRef.current = pos;
  };

  const handleEnd = () => {
    if (isDrawing) {
      setIsDrawing(false);
      lastPosRef.current = null;
      saveHistoryRef.current();
    }
  };

  // 撤销
  const handleUndo = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx || history.length < 2) return;
    const prev = history[history.length - 2];
    ctx.putImageData(prev, 0, 0);
    setHistory((h) => h.slice(0, -1));
  };

  // 重置
  const handleReset = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx || history.length === 0) return;
    ctx.putImageData(history[0], 0, 0);
    setHistory([history[0]]);
  };

  // 保存到本地
  const handleSave = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `jiaru-${Date.now()}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <canvas
        ref={canvasRef}
        className="w-full max-w-[400px] rounded-2xl shadow-sm bg-white touch-none"
        onMouseDown={handleStart}
        onMouseMove={handleMove}
        onMouseUp={handleEnd}
        onMouseLeave={handleEnd}
        onTouchStart={handleStart}
        onTouchMove={handleMove}
        onTouchEnd={handleEnd}
      />

      <div className="flex gap-4 w-full max-w-[400px]">
        <button
          onClick={handleUndo}
          disabled={history.length < 2}
          className="flex-1 h-12 rounded-2xl bg-white border border-pink-200
                     text-sm text-gray-500 font-medium
                     disabled:opacity-30 disabled:cursor-not-allowed
                     hover:bg-pink-50 active:scale-95 transition-all"
        >
          ↩ 撤销
        </button>
        <button
          onClick={handleReset}
          disabled={history.length < 2}
          className="flex-1 h-12 rounded-2xl bg-white border border-pink-200
                     text-sm text-gray-500 font-medium
                     disabled:opacity-30 disabled:cursor-not-allowed
                     hover:bg-pink-50 active:scale-95 transition-all"
        >
          ↺ 重置
        </button>
        <button
          onClick={handleSave}
          className="flex-1 h-12 rounded-2xl bg-gradient-to-r from-[#E8A0BF] to-[#D4749D]
                     text-sm text-white font-medium shadow-sm
                     hover:shadow-md active:scale-95 transition-all"
        >
          💾 保存
        </button>
      </div>
    </div>
  );
}
