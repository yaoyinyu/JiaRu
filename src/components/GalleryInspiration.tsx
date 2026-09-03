"use client";

/**
 * 灵感参考卡：展示 /gallery 选中的灵感款式缩略图，并在浏览器端从素材图
 * 采样推导「灵感色」（推导逻辑见 src/lib/gallery-inspiration.ts）。
 *
 * - `variant="banner"`：空态时在上传区上方展示的横向大卡。
 * - `variant="mini"`：照片载入后侧栏里的紧凑行，点击色块可把灵感预设色
 *   涂到当前选中手指。
 *
 * 采样失败（图片加载失败等）时只降级为不显示推荐色，卡片本身仍可用，
 * 不阻塞试色主流程。
 */

import { useEffect, useState } from "react";
import Image from "next/image";
import {
  closestPresetColor,
  pickInspiredSwatch,
  pixelsFromRgbaBuffer,
} from "@/lib/gallery-inspiration";
import { Icon } from "@/components/Icon";

/** 采样画布边长：48x48 ≈ 2304 像素，足以稳定聚类且开销可忽略。 */
const SAMPLE_CANVAS_SIZE = 48;

type Props = {
  src: string;
  name: string;
  variant?: "banner" | "mini";
  /** 灵感预设色推导完成时回调（参数为 PRESET_COLORS 中的色值；失败为 null）。 */
  onPresetColor?: (preset: { name: string; color: string } | null) => void;
  /** 仅 mini 形态：用户点击卡片时把推荐色应用到当前手指。 */
  onApplyPreset?: (preset: { name: string; color: string }) => void;
};

async function derivePresetColorFromImage(
  src: string
): Promise<{ name: string; color: string } | null> {
  if (typeof document === "undefined") return null;
  const image = document.createElement("img");
  image.src = src;
  image.decoding = "async";
  try {
    await image.decode();
  } catch {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = SAMPLE_CANVAS_SIZE;
  canvas.height = SAMPLE_CANVAS_SIZE;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return null;
  context.drawImage(image, 0, 0, SAMPLE_CANVAS_SIZE, SAMPLE_CANVAS_SIZE);
  const { data } = context.getImageData(
    0,
    0,
    SAMPLE_CANVAS_SIZE,
    SAMPLE_CANVAS_SIZE
  );
  const swatch = pickInspiredSwatch(pixelsFromRgbaBuffer(data));
  if (!swatch) return null;
  return closestPresetColor(swatch.hex);
}

export function GalleryInspirationCard({
  src,
  name,
  variant = "banner",
  onPresetColor,
  onApplyPreset,
}: Props) {
  const [preset, setPreset] = useState<{ name: string; color: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    derivePresetColorFromImage(src).then((result) => {
      if (cancelled) return;
      setPreset(result);
      onPresetColor?.(result);
    });
    return () => {
      cancelled = true;
    };
    // onPresetColor 由父组件以稳定引用传入，采样只依赖 src。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  const swatch = (
    <span
      className="h-9 w-9 shrink-0 rounded-full border-2 border-white shadow-[0_3px_12px_rgba(0,0,0,.12)]"
      style={{ backgroundColor: preset ? preset.color : "#EEE4E9" }}
      title={preset ? `灵感色：${preset.name}` : "正在提取灵感色"}
    />
  );

  if (variant === "mini") {
    return (
      <button
        type="button"
        onClick={() => preset && onApplyPreset?.(preset)}
        className="flex w-full items-center gap-3 rounded-2xl border border-pink-100/70 bg-white/70 p-3 text-left transition hover:border-pink-200"
        title={preset ? `点击把「${preset.name}」涂到当前手指` : undefined}
      >
        <span className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl border border-white/80">
          <Image src={src} alt={name} width={44} height={44} className="h-full w-full object-cover" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[10px] uppercase tracking-[.14em] text-[#CF6F99]">灵感参考</span>
          <span className="block truncate text-sm font-medium text-[#554D51]">{name}</span>
          <span className="mt-0.5 block text-[10px] text-[#A49A9F]">
            {preset ? `推荐色：${preset.name}` : "正在提取灵感色…"}
          </span>
        </span>
        {swatch}
        <Icon name="arrow-up-right" className="h-4 w-4 shrink-0 text-[#C96690]" />
      </button>
    );
  }

  return (
    <div className="flex items-center gap-4 rounded-[24px] border border-white/80 bg-white/62 p-4 shadow-[0_18px_48px_rgba(116,73,92,.08)] backdrop-blur-2xl sm:p-5">
      <span className="relative h-20 w-20 shrink-0 overflow-hidden rounded-2xl border border-white/80 sm:h-24 sm:w-24">
        <Image src={src} alt={name} width={96} height={96} className="h-full w-full object-cover" priority />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-[#CF6F99]">灵感款式</p>
        <h2 className="mt-1 text-lg font-semibold text-[#4A4447]">{name}</h2>
        <p className="mt-1.5 text-xs leading-5 text-[#90878C]">
          {preset
            ? <>已为你预选相近的预设色「{preset.name}」，上传手部照片后自动作为初始甲色。</>
            : "上传一张手部照片，以此为灵感开始试色。"}
        </p>
      </div>
      <div className="hidden shrink-0 flex-col items-center gap-1.5 sm:flex">
        {swatch}
        <span className="text-[10px] text-[#A49A9F]">{preset ? preset.name : "提取中"}</span>
      </div>
    </div>
  );
}
