"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { extractTexture } from "@/lib/texture";
import { AppDialog } from "@/components/ui/AppDialog";
import { applyCropperKeyboardInput } from "@/lib/ar-cropper-keys";
import styles from "./TextureCropper.module.css";

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
const BORDER_COLOR = "#ac5145";
const BORDER_WIDTH = 2;
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
  const [imgLoaded, setImgLoaded] = useState(false);

  const startRef = useRef<{ x: number; y: number } | null>(null);
  // §7.5：提取中关闭视为取消——关闭后被提取的位图一律不再应用。
  const closeCancelledRef = useRef(false);

  // AppDialog 面板宽度放宽标记（见 TextureCropper.module.css 头注）。
  useEffect(() => {
    document.body.dataset.arCropperOpen = "true";
    return () => {
      delete document.body.dataset.arCropperOpen;
    };
  }, []);

  // ── 加载图片 ──────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    const img = new Image();

    img.onload = () => {
      if (cancelled) {
        // 不在这里 revoke：blob URL 由页面 prepareUploadUrl 统一管理，
        // StrictMode 双挂载时两次 effect 共用同一 URL，此处吊销会让
        // 第二次挂载的图片与确认时的 extractTexture 重新加载失败（#11 回归发现）。
        return;
      }
      imgRef.current = img;
      setImgLoaded(true);

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
        // 同上：不吊销共享 blob URL（页面生命周期统一管理）
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

    // 珊瑚虚线边框
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

  // ── 取消（Escape / 取消按钮统一入口；AppDialog onClose 也汇到这里）──

  const handleCancel = useCallback(() => {
    // §7.5：取消（含提取中关闭）之后结果一律不再应用；
    // 提取完成后发现已取消时，直接释放位图并跳过 onConfirm。
    closeCancelledRef.current = true;
    onCancel();
  }, [onCancel]);

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

  // ── 键盘选区（§7.5）：方向键移动、Shift+方向键调整大小 ──

  const handleCanvasKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLCanvasElement>) => {
      if (loading || loadingTexture || (error && !imgLoaded)) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const next = applyCropperKeyboardInput(
        selection,
        { key: e.key, shiftKey: e.shiftKey },
        canvas.width,
        canvas.height
      );
      if (!next) return;
      e.preventDefault();
      setSelection(next);
      setError(null);
    },
    [selection, loading, loadingTexture, error, imgLoaded]
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
      // 提取期间弹层被关闭：视为取消，释放位图且不应用结果（§7.5）。
      if (closeCancelledRef.current) {
        bitmap.close();
        return;
      }
      onConfirm(bitmap);
    } catch (err) {
      if (closeCancelledRef.current) return;
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
  const loadFailed = error != null && !imgLoaded;

  // ── 渲染 ──────────────────────────────────────────────

  return (
    <AppDialog
      open
      onClose={handleCancel}
      title="裁剪单条纹理"
      description="在图片上框出一块完整甲面纹理，确认后应用到当前手指。"
      // 误触背景遮罩会丢掉已画的选区：只保留 Escape 与「取消」按钮关闭。
      closeOnOutside={false}
      initialFocus="confirm"
      footer={
        <>
          <button
            type="button"
            onClick={handleReset}
            disabled={!selection || loadingTexture}
            className={styles.secondaryButton}
          >
            重选
          </button>
          <button
            type="button"
            data-autofocus="cancel"
            onClick={handleCancel}
            className={styles.cancelButton}
          >
            取消
          </button>
          <button
            type="button"
            data-autofocus="confirm"
            onClick={() => void handleConfirm()}
            disabled={!canConfirm}
            className={styles.confirmButton}
          >
            {loadingTexture ? (
              <span className="flex items-center gap-1">
                <span
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                  aria-hidden="true"
                />{" "}
                提取中…
              </span>
            ) : (
              "确认使用"
            )}
          </button>
        </>
      }
    >
      {loadFailed ? (
        <div className="py-6 text-center">
          <p className={styles.errorMessage}>{error}</p>
          <button
            type="button"
            onClick={handleCancel}
            className={`${styles.cancelButton} mt-4`}
          >
            返回
          </button>
        </div>
      ) : (
        <>
          <div className={styles.canvasArea}>
            {loading && (
              <div className="absolute z-10 flex items-center gap-2 text-white/85">
                <span
                  className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white"
                  aria-hidden="true"
                />
                <span>加载中…</span>
              </div>
            )}
            <canvas
              ref={canvasRef}
              tabIndex={0}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onKeyDown={handleCanvasKeyDown}
              aria-label="纹理裁剪画布：拖拽画选区；也可用方向键移动选区，Shift 加方向键调整大小"
              className={styles.canvas}
              style={{ cursor: "crosshair" }}
            />
          </div>
          <p className={styles.hint}>
            {isDragging
              ? "松开完成选区"
              : selection
                ? "可拖拽重新选取；方向键移动选区，Shift + 方向键调整大小。"
                : "拖拽选取指甲区域，或用方向键生成默认选区后微调。"}
          </p>
          {error && (
            <p role="alert" className={`${styles.errorMessage} mt-2`}>
              {error}
            </p>
          )}
        </>
      )}
    </AppDialog>
  );
}
