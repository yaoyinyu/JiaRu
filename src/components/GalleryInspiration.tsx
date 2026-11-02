"use client";

/**
 * 灵感参考卡：展示 /gallery 选中的灵感款式缩略图，并在浏览器端从素材图
 * 采样推导「灵感色」（推导逻辑见 src/lib/gallery-inspiration.ts）。
 *
 * - `variant="banner"`：空态时在上传区上方展示的横向大卡。
 * - `variant="mini"`：照片载入后侧栏里的紧凑行，点击应用最接近主色的
 *   纹理套装（映射逻辑见 src/lib/nail-texture-sets.ts 的 closestTextureSet；
 *   应用后由页面在识别出甲面框时自动贴合一次，见编辑器 applyInspirationSet）。
 *
 * 灵感色提取区分「提取中 / 已完成 / 未能提取」三态：提取失败或无相近
 * 预设色时明确提示手动选择纹理套装，不会永久停留在「正在提取」。
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
  /** 仅 mini 形态：用户点击卡片时预选推荐色对应的纹理套装。 */
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
  // 提取结果带 src 身份：src 变化后旧结果作废，渲染期派生回 loading，
  // 避免 effect 内同步 setState（react-hooks/set-state-in-effect）。
  const [extractionState, setExtractionState] = useState<{
    src: string;
    preset: { name: string; color: string } | null;
    state: "done" | "failed";
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    derivePresetColorFromImage(src).then((result) => {
      if (cancelled) return;
      setExtractionState({ src, preset: result, state: result ? "done" : "failed" });
      onPresetColor?.(result);
    });
    return () => {
      cancelled = true;
    };
    // onPresetColor 由父组件以稳定引用传入，采样只依赖 src。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  const extractionActive = extractionState !== null && extractionState.src === src;
  const preset = extractionActive ? extractionState.preset : null;
  const extraction: "loading" | "done" | "failed" = extractionActive
    ? extractionState.state
    : "loading";

  const swatch = (
    <span
      className="h-9 w-9 shrink-0 rounded-full border-2 border-white shadow-[var(--neu-out-sm)]"
      style={{ backgroundColor: preset ? preset.color : "#f0e2db" }}
      title={preset ? `灵感色：${preset.name}` : extraction === "failed" ? "未能提取灵感色" : "正在提取灵感色"}
    />
  );

  if (variant === "mini") {
    return (
      <button
        type="button"
        onClick={() => preset && onApplyPreset?.(preset)}
        className="flex w-full items-center gap-3 rounded-2xl border border-pink-100/70 bg-[var(--surface)] p-3 text-left transition hover:border-pink-200"
        title={preset ? `点击应用「${preset.name}」相近的纹理套装（识别出甲面后自动贴合）` : undefined}
      >
        <span className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl border border-[var(--line)]">
          <Image src={src} alt={name} width={44} height={44} className="h-full w-full object-cover" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[12px] uppercase tracking-[.14em] text-[#ac5145]">灵感参考</span>
          <span className="block truncate text-sm font-medium text-[#292a27]">{name}</span>
          <span className="mt-0.5 block text-[12px] text-[#67685f]">
            {preset
              ? `推荐色：${preset.name}`
              : extraction === "failed"
                ? "未能提取灵感色，可手动选择纹理套装。"
                : "正在提取灵感色…"}
          </span>
        </span>
        {swatch}
        <Icon name="arrow-up-right" className="h-4 w-4 shrink-0 text-[#ac5145]" />
      </button>
    );
  }

  return (
    <div className="flex items-center gap-4 rounded-[24px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-md)]  sm:p-5">
      <span className="relative h-20 w-20 shrink-0 overflow-hidden rounded-2xl border border-[var(--line)] sm:h-24 sm:w-24">
        <Image src={src} alt={name} width={96} height={96} className="h-full w-full object-cover" priority />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[.16em] text-[#ac5145]">灵感款式</p>
        <h2 className="mt-1 text-lg font-semibold text-[#292a27]">{name}</h2>
        <p className="mt-1.5 text-xs leading-5 text-[#6f7066]">
          {preset
            ? <>已为你预选相近纹理套装，上传照片识别出甲面后将自动贴合，可逐指调整或撤销。</>
            : extraction === "failed"
              ? "未能提取灵感色，可手动选择纹理套装。"
              : "正在提取灵感色…"}
        </p>
      </div>
      <div className="hidden shrink-0 flex-col items-center gap-1.5 sm:flex">
        {swatch}
        <span className="text-[12px] text-[#67685f]">
          {preset ? preset.name : extraction === "failed" ? "未提取" : "提取中"}
        </span>
      </div>
    </div>
  );
}
