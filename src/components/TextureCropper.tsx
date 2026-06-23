"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { extractTexture } from "@/lib/texture";

interface TextureCropperProps {
  imageUrl: string;
  onConfirm: (bitmap: ImageBitmap) => void;
  onCancel: () => void;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const OVERLAY_ALPHA = 0.55;
const BORDER_COLOR = "#E8A0BF";
const BORDER_WIDTH = 2;
const MIN_SELECTION_PX = 30;
const MAX_CANVAS_DIM = 1024;

function fitScale(
  imgW: number,
  imgH: number
): { canvasW: number; canvasH: number; scale: number } {
  const scale = Math.min(1, MAX_CANVAS_DIM / Math.max(imgW, imgH));
  return {
    canvasW: Math.round(imgW * scale),
    canvasH: Math.round(imgH * scale),
    scale,
  };
}

function clientToCanvas(
  clientX: number,
  clientY: number,
  canvas: HTMLCanvasElement
): { x: number; y: number } {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left) * (canvas.width / rect.width),
    y: (clientY - rect.top) * (canvas.height / rect.height),
  };
}

function clampRect(r: Rect, maxW: number, maxH: number): Rect {
  const x = Math.max(0, Math.min(r.x, maxW - 1));
  const y = Math.max(0, Math.min(r.y, maxH - 1));
  const w = Math.max(1, Math.min(r.w, maxW - x));
  const h = Math.max(1, Math.min(r.h, maxH - y));
  return { x, y, w, h };
}

function normalizeRect(
  startX: number,
  startY: number,
  endX: number,
  endY: number
): Rect {
  const x = Math.min(startX, endX);
  const y = Math.min(startY, endY);
  const w = Math.abs(endX - startX);
  const h = Math.abs(endY - startY);
  return { x, y, w, h };
}

export default function TextureCropper({
  imageUrl,
  onConfirm,
  onCancel,
}: TextureCropperProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const scaleRef = useRef(1);

  const [selection, setSelection] = useState<Rect | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingTexture, setLoadingTexture] = useState(false);

  const startRef = useRef<{ x: number; y: number } | null>(null);

  // ── 加载图片 ──────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    const img = new Image();

    img.onload = () => {
      if (cancelled) {
        URL.revokeObjectURL(img.src);
        return;
      }
      imgRef.current = img;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const { canvasW, canvasH, scale } = fitScale(
        img.naturalWidth,
        img.naturalHeight
      );
      scaleRef.current = scale;
      canvas.width = canvasW;
      canvas.height = canvasH;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.clearRect(0, 0, canvasW, canvasH);
      ctx.drawImage(img, 0, 0, canvasW, canvasH);
      setLoading(false);
    };

    img.onerror = () => {
      if (!cancelled) {
        URL.revokeObjectURL(img.src);
        setError("图片加载失败，请重试");
        setLoading(false);
      }
    };

    img.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  // ── 重绘：底图 + 遮罩 + 选区 ──────────────────────────

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const cw = canvas.width;
    const ch = canvas.height;

    // 底图
    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(img, 0, 0, cw, ch);

    if (!selection) return;

    const s = clampRect(selection, cw, ch);

    // 半透明遮罩（选区外部四个区域）
    ctx.fillStyle = `rgba(0, 0, 0, ${OVERLAY_ALPHA})`;
    ctx.fillRect(0, 0, cw, s.y);
    ctx.fillRect(0, s.y + s.h, cw, ch - (s.y + s.h));
    ctx.fillRect(0, s.y, s.x, s.h);
    ctx.fillRect(s.x + s.w, s.y, cw - (s.x + s.w), s.h);

    // 粉色虚线边框
    ctx.save();
    ctx.strokeStyle = BORDER_COLOR;
    ctx.lineWidth = BORDER_WIDTH;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(s.x, s.y, s.w, s.h);
    ctx.restore();

    // 四角手柄
    const handleSize = 8;
    ctx.fillStyle = BORDER_COLOR;
    [
      [s.x, s.y],
      [s.x + s.w, s.y],
      [s.x, s.y + s.h],
      [s.x + s.w, s.y + s.h],
    ].forEach(([hx, hy]) => {
      ctx.fillRect(
        hx - handleSize / 2,
        hy - handleSize / 2,
        handleSize,
        handleSize
      );
    });
  }, [selection]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  // ── Pointer 事件 ──────────────────────────────────────

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      canvas.setPointerCapture(e.pointerId);

      const pos = clientToCanvas(e.clientX, e.clientY, canvas);
      startRef.current = pos;
      setSelection(null);
      setIsDragging(true);
    },
    []
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      if (!isDragging || !startRef.current) return;

      const canvas = canvasRef.current;
      if (!canvas) return;

      const pos = clientToCanvas(e.clientX, e.clientY, canvas);
      const rect = normalizeRect(
        startRef.current.x,
        startRef.current.y,
        pos.x,
        pos.y
      );
      setSelection(clampRect(rect, canvas.width, canvas.height));
    },
    [isDragging]
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent<HTMLCanvasElement>) => {
      setIsDragging(false);

      const canvas = canvasRef.current;
      if (!canvas) return;

      canvas.releasePointerCapture(e.pointerId);
      startRef.current = null;
    },
    []
  );

  // ── 确认 / 重选 ──────────────────────────────────────

  const handleConfirm = useCallback(async () => {
    if (!selection || !imgRef.current) return;

    const s = clampRect(
      selection,
      canvasRef.current!.width,
      canvasRef.current!.height
    );
    const scale = scaleRef.current;

    const crop = {
      x: Math.round(s.x / scale),
      y: Math.round(s.y / scale),
      w: Math.round(s.w / scale),
      h: Math.round(s.h / scale),
    };

    if (crop.w < 10 || crop.h < 10) {
      setError("选区太小，请重新选择");
      return;
    }

    try {
      setLoadingTexture(true);
      setError(null);
      const bitmap = await extractTexture(imageUrl, crop);
      onConfirm(bitmap);
    } catch (err) {
      setError(err instanceof Error ? err.message : "纹理提取失败");
      setLoadingTexture(false);
    }
  }, [selection, imageUrl, onConfirm]);

  const handleReset = useCallback(() => {
    setSelection(null);
    setError(null);
    startRef.current = null;
    redraw();
  }, [redraw]);

  const canConfirm = selection != null && !loadingTexture;

  // ── 键盘快捷键 ────────────────────────────────────────

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter" && canConfirm) handleConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, canConfirm, handleConfirm]);

  // ── 渲染 ──────────────────────────────────────────────

  if (error && !imgRef.current) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70 p-4">
        <div className="bg-white rounded-2xl p-6 text-center max-w-sm">
          <p className="text-red-500 mb-4">{error}</p>
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-pink-100 text-pink-600 rounded-xl"
          >
            返回
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black">
      {/* 顶部提示栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/90">
        <span className="text-white text-sm">
          {isDragging
            ? "松开完成选区"
            : selection
              ? "可拖拽调整选区"
              : "拖拽选取指甲区域"}
        </span>
        <button
          onClick={onCancel}
          className="text-gray-400 text-sm px-3 py-1 rounded-lg hover:bg-white/10 transition-colors"
        >
          取消
        </button>
      </div>

      {/* Canvas 裁剪区 */}
      <div className="flex-1 flex items-center justify-center overflow-hidden bg-[#222]">
        {loading && (
          <div className="absolute z-10 flex items-center gap-2 text-white/70">
            <span className="animate-spin text-lg">⏳</span>
            <span>加载中...</span>
          </div>
        )}
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          className="max-w-full max-h-full object-contain touch-none select-none"
          style={{ cursor: "crosshair" }}
        />
      </div>

      {/* 底部操作栏 */}
      <div className="flex items-center gap-3 px-4 py-3 bg-black/90">
        <button
          onClick={handleReset}
          disabled={!selection}
          className={`px-4 py-2 text-sm rounded-xl transition-colors ${
            selection
              ? "bg-white/10 text-white hover:bg-white/20"
              : "bg-white/5 text-gray-500"
          }`}
        >
          重选
        </button>

        <div className="flex-1" />

        {error && (
          <span className="text-red-400 text-xs mr-2">{error}</span>
        )}

        <button
          onClick={handleConfirm}
          disabled={!canConfirm}
          className={`px-6 py-2 text-sm font-medium rounded-xl transition-colors ${
            canConfirm
              ? "bg-pink-400 text-white hover:bg-pink-500 active:scale-95"
              : "bg-pink-400/40 text-white/50 cursor-not-allowed"
          }`}
        >
          {loadingTexture ? (
            <span className="flex items-center gap-1">
              <span className="animate-spin">⏳</span> 提取中
            </span>
          ) : (
            "确认使用"
          )}
        </button>
      </div>
    </div>
  );
}
