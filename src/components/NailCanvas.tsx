"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Icon } from "@/components/Icon";
import {
  frameHitTest,
  loadTextureImage,
  placementDrawList,
  placementHitTest,
  previewScale,
  type NailPlacement,
  type PlacementFrameInput,
} from "@/lib/canvas/placements";

/** 点击空框时贴合的纹理 */
export interface ActiveTexture {
  key: string;
  src: string;
  aspect: number;
}

export interface NailCanvasProps {
  imageUrl: string;
  /** 识别甲面框（原图像素域） */
  frames: readonly PlacementFrameInput[];
  /** 纹理贴合实例（原图像素域；数组序即绘制层序，末尾在最上） */
  placements: readonly NailPlacement[];
  /** 点击空框时贴合的纹理；null 时仍回调 onFrameClick，由页面提示 */
  activeTexture: ActiveTexture | null;
  /** 选中的贴合实例 id */
  selectedId: string | null;
  showFrames: boolean;
  addingFrame: boolean;
  canUndo: boolean;
  onFrameClick(frame: PlacementFrameInput): void;
  onPlacementSelect(id: string | null): void;
  /** 拖动结束提交（拖动中组件仅本地预览） */
  onPlacementMove(id: string, cx: number, cy: number): void;
  /** addingFrame 时空白处点击，手动加框（原图坐标） */
  onEmptyClick(x: number, y: number): void;
  onUndo(): void;
  onReset(): void;
}

/** 甲面框标签短名（顺序与 FINGER_NAMES 一致；未分配时显示序号） */
const FRAME_SHORT_NAMES = ["拇", "食", "中", "无", "小"];
const FRAME_STROKE = "rgba(34, 197, 94, 0.9)";
const FRAME_LABEL_BG = "rgba(34, 197, 94, 0.95)";
const SELECTED_STROKE = "#ac5145";

/** 甲面框叠加层：绿色虚线椭圆 + 指名/序号标签（标签不随框旋转） */
function drawFrameOverlay(
  ctx: CanvasRenderingContext2D,
  frames: readonly PlacementFrameInput[],
  scale: number,
) {
  if (frames.length === 0) return;
  ctx.save();
  ctx.font = "11px sans-serif";
  ctx.textBaseline = "top";
  frames.forEach((frame, index) => {
    const label =
      frame.assignedFinger !== null
        ? FRAME_SHORT_NAMES[frame.assignedFinger] ?? `指${frame.assignedFinger + 1}`
        : String(index + 1);
    ctx.save();
    ctx.translate(frame.cx * scale, frame.cy * scale);
    ctx.rotate(frame.angle);
    ctx.beginPath();
    ctx.ellipse(0, 0, (frame.nw * scale) / 2, (frame.nl * scale) / 2, 0, 0, Math.PI * 2);
    ctx.strokeStyle = FRAME_STROKE;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.restore();

    const boxW = ctx.measureText(label).width + 8;
    const boxH = 16;
    const boxX = frame.cx * scale - boxW / 2;
    const boxY = frame.cy * scale - (frame.nl * scale) / 2 - boxH - 6;
    ctx.fillStyle = FRAME_LABEL_BG;
    ctx.fillRect(boxX, boxY, boxW, boxH);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, boxX + 4, boxY + 2);
  });
  ctx.restore();
}

/**
 * 单个贴合：在旋转坐标系内把纹理画到渲染几何矩形上。
 * 渲染几何由 computeTextureRenderPlan 保证长宽比保真（adjust 显式改宽/长除外），
 * 这里不额外拉伸：目标矩形宽高比 = width:length = 贴合几何自身比例。
 */
function drawPlacement(
  ctx: CanvasRenderingContext2D,
  placement: NailPlacement,
  scale: number,
  tex: HTMLImageElement,
) {
  ctx.save();
  ctx.translate(placement.cx * scale, placement.cy * scale);
  ctx.rotate(placement.angle);
  ctx.drawImage(
    tex,
    -(placement.width * scale) / 2,
    -(placement.length * scale) / 2,
    placement.width * scale,
    placement.length * scale,
  );
  ctx.restore();
}

/** 选中高亮：珊瑚色椭圆轮廓（外扩 2px 套在贴合几何之外） */
function drawSelectionHighlight(
  ctx: CanvasRenderingContext2D,
  placement: NailPlacement,
  scale: number,
) {
  ctx.save();
  ctx.translate(placement.cx * scale, placement.cy * scale);
  ctx.rotate(placement.angle);
  ctx.beginPath();
  ctx.ellipse(
    0,
    0,
    (placement.width * scale) / 2 + 2,
    (placement.length * scale) / 2 + 2,
    0,
    0,
    Math.PI * 2,
  );
  ctx.strokeStyle = SELECTED_STROKE;
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.restore();
}

/**
 * 编辑器画布（甲面框 + 纹理贴合实例模型）：
 *  - 显示与输出分离：预览画布最长边 400/600，贴合几何以原图像素域存储；
 *    保存时按原图尺寸离屏重放全部贴合（因子 1），4096 方图导出仍为原尺寸；
 *  - 组件不管理 placements 状态：全部由 props 传入、事件上报；
 *  - 指针交互优先级：贴合命中（选中+拖动）→ 甲面框命中（onFrameClick）→
 *    addingFrame 时空白加框（onEmptyClick）→ 取消选中。
 */
export function NailCanvas({
  imageUrl,
  frames = [],
  placements = [],
  activeTexture,
  selectedId,
  showFrames,
  addingFrame,
  canUndo,
  onFrameClick,
  onPlacementSelect,
  onPlacementMove,
  onEmptyClick,
  onUndo,
  onReset,
}: NailCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [imageReady, setImageReady] = useState(false);
  /** 原图 → 预览画布缩放（绘制用）；坐标反解用其倒数（invScale，精确到画布栅格） */
  const drawScaleRef = useRef(1);
  const invScaleRef = useRef({ x: 1, y: 1 });
  /** 已就绪纹理：textureSrc → HTMLImageElement；版本号驱动加载完成后重绘 */
  const texturesRef = useRef(new Map<string, HTMLImageElement>());
  const [textureVersion, setTextureVersion] = useState(0);
  /** 拖动状态：grab 偏移（原图坐标）与拖动中的本地预览位置 */
  const dragRef = useRef<{ id: string; grabDx: number; grabDy: number } | null>(null);
  const dragPosRef = useRef<{ id: string; cx: number; cy: number } | null>(null);
  // 用 ref 存绘制函数，避免 React Compiler 问题（与旧实现同思路）
  const redrawRef = useRef<() => void>(() => {});

  // 重绘预览：底图 → 甲面框叠加层 → 贴合实例（拖动项用本地预览坐标）→ 选中高亮
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const scale = drawScaleRef.current;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    if (showFrames) {
      drawFrameOverlay(ctx, frames, scale);
    }

    const drag = dragPosRef.current;
    for (const placement of placements) {
      const effective =
        drag && drag.id === placement.id
          ? { ...placement, cx: drag.cx, cy: drag.cy }
          : placement;
      const tex = texturesRef.current.get(placement.textureSrc);
      if (tex) {
        drawPlacement(ctx, effective, scale, tex);
      }
      if (placement.id === selectedId) {
        drawSelectionHighlight(ctx, effective, scale);
      }
    }
  }, [frames, placements, selectedId, showFrames]);

  useEffect(() => {
    redrawRef.current = redraw;
  }, [redraw]);

  useEffect(() => {
    redrawRef.current();
  }, [redraw, imageReady, textureVersion]);

  // 加载图片到 Canvas（预览尺寸），换图时清空拖动状态
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      imageRef.current = img;
      const scale = previewScale(img.width, img.height);
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      drawScaleRef.current = canvas.width / img.width;
      invScaleRef.current = {
        x: img.width / canvas.width,
        y: img.height / canvas.height,
      };
      dragRef.current = null;
      dragPosRef.current = null;
      setImageReady(true);
      redrawRef.current();
    };
    img.src = imageUrl;
    return () => {
      cancelled = true;
    };
  }, [imageUrl]);

  // 纹理预加载：未就绪的纹理异步加载，完成后触发一次重绘
  useEffect(() => {
    let cancelled = false;
    const sources = new Set<string>();
    for (const placement of placements) {
      sources.add(placement.textureSrc);
    }
    if (activeTexture) {
      sources.add(activeTexture.src);
    }
    for (const src of sources) {
      if (texturesRef.current.has(src)) continue;
      loadTextureImage(src)
        .then((img) => {
          if (cancelled) return;
          if (texturesRef.current.get(src) !== img) {
            texturesRef.current.set(src, img);
            setTextureVersion((v) => v + 1);
          }
        })
        .catch(() => {
          // 加载失败：绘制时跳过该纹理，不阻塞其余贴合；缓存未写入可重试
        });
    }
    return () => {
      cancelled = true;
    };
  }, [placements, activeTexture]);

  /** 客户端坐标 → 画布像素 → 原图坐标（除以预览缩放的精确形式） */
  const getOriginalPos = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    const canvasX = (e.clientX - rect.left) * (canvas.width / rect.width);
    const canvasY = (e.clientY - rect.top) * (canvas.height / rect.height);
    const inv = invScaleRef.current;
    return { x: canvasX * inv.x, y: canvasY * inv.y };
  };

  const clampToImage = (x: number, y: number) => {
    const img = imageRef.current;
    if (!img) return { x, y };
    return {
      x: Math.min(Math.max(x, 0), img.width),
      y: Math.min(Math.max(y, 0), img.height),
    };
  };

  const handlePointerDown = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!imageReady) return;
    const pos = getOriginalPos(e);
    if (!pos) return;
    e.preventDefault();

    // 1) 贴合命中：立即选中并开始拖动（顶层优先）
    const hitIndex = placementHitTest(placements, pos.x, pos.y);
    if (hitIndex >= 0) {
      const placement = placements[hitIndex];
      onPlacementSelect(placement.id);
      dragRef.current = {
        id: placement.id,
        grabDx: pos.x - placement.cx,
        grabDy: pos.y - placement.cy,
      };
      dragPosRef.current = null;
      try {
        canvasRef.current?.setPointerCapture(e.pointerId);
      } catch {
        // 捕获失败仅降级为元素内拖动
      }
      return;
    }

    // 2) 甲面框命中：回调由页面处理（activeTexture 为 null 时也回调，由页面提示）
    const frameIndex = frameHitTest(frames, pos.x, pos.y);
    if (frameIndex >= 0) {
      onFrameClick(frames[frameIndex]);
      return;
    }

    // 3) 加框模式空白点击：手动加框；否则取消选中
    if (addingFrame) {
      onEmptyClick(pos.x, pos.y);
      return;
    }
    onPlacementSelect(null);
  };

  const handlePointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const pos = getOriginalPos(e);
    if (!pos) return;
    e.preventDefault();
    const clamped = clampToImage(pos.x - drag.grabDx, pos.y - drag.grabDy);
    dragPosRef.current = { id: drag.id, cx: clamped.x, cy: clamped.y };
    redrawRef.current();
  };

  const endDrag = (commit: boolean) => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    const preview = dragPosRef.current;
    dragPosRef.current = null;
    if (commit && preview) {
      // 位置未变化时不提交，避免纯点击污染页面的撤销历史
      const target = placements.find((p) => p.id === drag.id) ?? null;
      if (!target || target.cx !== preview.cx || target.cy !== preview.cy) {
        onPlacementMove(drag.id, preview.cx, preview.cy);
      }
    }
    redrawRef.current();
  };

  const handlePointerUp = () => {
    endDrag(true);
  };

  const handlePointerCancel = () => {
    endDrag(false);
  };

  // 保存到本地：原图尺寸离屏重放全部贴合。
  // 贴合几何存储域即原图像素，导出画布同为原图尺寸，重放因子恒为 1
  // （旧笔刷模型的 1/previewScale 换算属于预览域存储，已随模型重写废弃）。
  const handleSave = async () => {
    const img = imageRef.current;
    if (!img || placements.length === 0) return;
    const out = document.createElement("canvas");
    out.width = img.width;
    out.height = img.height;
    const outCtx = out.getContext("2d");
    if (!outCtx) return;
    outCtx.drawImage(img, 0, 0, img.width, img.height);
    for (const item of placementDrawList(placements, 1)) {
      let tex = texturesRef.current.get(item.textureSrc) ?? null;
      if (!tex) {
        try {
          tex = await loadTextureImage(item.textureSrc);
          texturesRef.current.set(item.textureSrc, tex);
        } catch {
          continue;
        }
      }
      outCtx.save();
      outCtx.translate(item.cx, item.cy);
      outCtx.rotate(item.angle);
      outCtx.drawImage(tex, -item.width / 2, -item.length / 2, item.width, item.length);
      outCtx.restore();
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
        className={`w-full max-w-[640px] rounded-[22px] bg-[var(--surface)] shadow-[var(--neu-out-md)] touch-none ${addingFrame ? "cursor-crosshair" : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
      />

      <div className="flex gap-3 w-full max-w-[640px]">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className="h-12 flex-1 rounded-2xl border border-pink-100 bg-[var(--surface)] text-sm font-medium text-[#67685f] shadow-sm transition-all hover:-translate-y-0.5 hover:bg-[var(--surface)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="undo" className="h-4 w-4" />撤销</span>
        </button>
        <button
          onClick={onReset}
          className="h-12 flex-1 rounded-2xl border border-pink-100 bg-[var(--surface)] text-sm font-medium text-[#67685f] shadow-sm transition-all hover:-translate-y-0.5 hover:bg-[var(--surface)] active:scale-95"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="reset" className="h-4 w-4" />重置</span>
        </button>
        <button
          onClick={handleSave}
          disabled={placements.length === 0}
          className="h-12 flex-1 rounded-2xl bg-[var(--coral)] text-sm font-medium text-white shadow-[var(--neu-out-sm)] transition-all hover:-translate-y-0.5 hover:shadow-[var(--neu-out-sm)] active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
        >
          <span className="inline-flex items-center justify-center gap-1.5"><Icon name="save" className="h-4 w-4" />保存</span>
        </button>
      </div>
    </div>
  );
}
