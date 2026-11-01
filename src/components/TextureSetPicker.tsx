"use client";

/**
 * 美甲纹理套装点选器：每套一张「卡片堆叠」。
 *
 * - 静止态：仅前 3 张可见，第 1 张展示该套拇指纹理封面 + 套装名；
 *   点击堆叠 = 应用整套（onApplySet）。
 * - 展开态（桌面 hover / 移动端点按容器触发）：5 张卡横向扇开，
 *   每张为单指纹理缩略图 + 指名；点单卡 = 钉选该纹理（onPinTexture）。
 * - 展开状态通过 onExpandedChange 上报页面渲染全页模糊遮罩；
 *   卸载时确保上报 null。
 * - 静止态第 4、5 张与第 3 张同变换且完全透明，展开时全部就位。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { FINGER_NAMES } from "@/lib/utils";
import type { NailTextureSet } from "@/lib/nail-texture-sets";
import { parsePinnedTextureKey } from "@/lib/editor-texture-state";

export interface TextureSetPickerProps {
  sets: readonly NailTextureSet[];
  activeSetId: string | null;
  /** "<setId>/<finger>" 格式的钉选纹理键 */
  pinnedTextureKey: string | null;
  onApplySet(setId: string): void;
  onPinTexture(setId: string, finger: number): void;
  onExpandedChange(expandedSetId: string | null): void;
}

/** 展开扇形的相邻卡水平间距：2×56 + 96px 卡宽 = 208px，360px 面板（内容约 320px）内不溢出。 */
const FAN_STEP_PX = 56;
/** 静止态可见的堆叠卡数量。 */
const STATIC_VISIBLE_CARDS = 3;

function staticTransform(index: number): string {
  const layer = Math.min(index, STATIC_VISIBLE_CARDS - 1);
  return `translateY(${layer * 8}px) translateX(${layer * 4}px) scale(${(1 - 0.05 * layer).toFixed(2)}) rotate(${(1.5 * layer).toFixed(1)}deg)`;
}

function expandedTransform(index: number): string {
  const offset = index - 2;
  return `translateX(${offset * FAN_STEP_PX}px) translateY(${offset * -6}px) rotate(${offset * 8}deg) scale(0.9)`;
}

interface StackCardProps {
  set: NailTextureSet;
  active: boolean;
  pinnedFinger: number | null;
  onApplySet(setId: string): void;
  onPinTexture(setId: string, finger: number): void;
  onExpandedChange(expandedSetId: string | null): void;
}

function TextureSetStackCard({
  set,
  active,
  pinnedFinger,
  onApplySet,
  onPinTexture,
  onExpandedChange,
}: StackCardProps) {
  const [hovered, setHovered] = useState(false);
  const [tapExpanded, setTapExpanded] = useState(false);
  // hover 能力只在客户端初始化一次；该值不参与渲染，无 SSR 水合差异。
  const [hoverCapable] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(hover: hover) and (pointer: fine)").matches
      : false
  );
  const expanded = hovered || tapExpanded;

  const onExpandedChangeRef = useRef(onExpandedChange);
  const reportedRef = useRef<string | null>(null);

  useEffect(() => {
    onExpandedChangeRef.current = onExpandedChange;
  });

  // 卸载时确保收回展开上报（更换照片 / 离开编辑态）。
  useEffect(
    () => () => {
      if (reportedRef.current) onExpandedChangeRef.current(null);
    },
    []
  );

  const reportExpanded = useCallback((next: boolean) => {
    reportedRef.current = next ? set.id : null;
    onExpandedChangeRef.current(next ? set.id : null);
  }, [set.id]);

  const collapse = useCallback(() => {
    setHovered(false);
    setTapExpanded(false);
    if (reportedRef.current) reportExpanded(false);
  }, [reportExpanded]);

  const handleMouseEnter = useCallback(() => {
    if (!hoverCapable) return;
    setHovered(true);
    reportExpanded(true);
  }, [hoverCapable, reportExpanded]);

  const handleMouseLeave = useCallback(() => {
    if (!hoverCapable && !tapExpanded) return;
    collapse();
  }, [collapse, hoverCapable, tapExpanded]);

  const handleBackgroundClick = useCallback(() => {
    if (!expanded) {
      setTapExpanded(true);
      reportExpanded(true);
      return;
    }
    if (hoverCapable) {
      // 桌面：展开由 hover 维持，点堆叠背景 = 应用整套。
      onApplySet(set.id);
      return;
    }
    // 移动端：点按空白处收起。
    collapse();
  }, [collapse, expanded, hoverCapable, onApplySet, reportExpanded, set.id]);

  const handleCardClick = useCallback(
    (finger: number, hasTexture: boolean) => {
      if (!expanded) {
        // 静止态点堆叠 = 应用整套。
        onApplySet(set.id);
        return;
      }
      if (!hasTexture) return;
      onPinTexture(set.id, finger);
      if (!hoverCapable) collapse();
    },
    [collapse, expanded, hoverCapable, onApplySet, onPinTexture, set.id]
  );

  const handleApplyClick = useCallback(() => {
    onApplySet(set.id);
    if (!hoverCapable) collapse();
  }, [collapse, hoverCapable, onApplySet, set.id]);

  const coverTexture =
    set.textures.find((item) => item.finger === 0) ?? set.textures[0] ?? null;

  return (
    <div
      role="group"
      aria-label={`纹理套装：${set.name}`}
      className={`relative h-28 ${expanded ? "z-40" : ""}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleBackgroundClick}
    >
      {expanded && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            handleApplyClick();
          }}
          className="absolute left-1/2 top-0 z-20 -translate-x-1/2 rounded-full bg-[var(--coral)] px-3 py-1 text-[11px] font-medium text-white shadow-[var(--neu-out-sm)] transition hover:-translate-y-0.5 active:scale-95"
        >
          应用整套
        </button>
      )}
      {Array.from({ length: 5 }, (_, index) => {
        const texture = set.textures.find((item) => item.finger === index) ?? null;
        const isCover = index === 0;
        const showStaticContent = isCover || !expanded;
        const pinned = pinnedFinger === index;
        const hiddenInStatic = !expanded && index >= STATIC_VISIBLE_CARDS;
        const staticOpacity = index < STATIC_VISIBLE_CARDS ? 1 - 0.1 * index : 0;
        return (
          <button
            key={index}
            type="button"
            aria-hidden={hiddenInStatic || undefined}
            tabIndex={hiddenInStatic || (expanded && !texture) ? -1 : undefined}
            aria-pressed={pinned || undefined}
            onClick={(event) => {
              event.stopPropagation();
              handleCardClick(index, Boolean(texture));
            }}
            className={`absolute top-0 h-full w-24 rounded-2xl bg-[var(--surface)] p-1.5 shadow-[var(--neu-out-md)] transition-[transform,opacity] duration-400 ease-[cubic-bezier(.16,1,.3,1)] motion-reduce:transition-none ${
              active && isCover ? "ring-2 ring-[var(--coral)] ring-offset-2 ring-offset-[var(--surface)]" : ""
            } ${pinned ? "ring-2 ring-[var(--coral)] ring-offset-1 ring-offset-[var(--surface)]" : ""} ${
              hiddenInStatic ? "pointer-events-none" : ""
            }`}
            style={{
              left: "calc(50% - 3rem)",
              zIndex: 10 - index,
              opacity: expanded ? 1 : staticOpacity,
              transform: expanded ? expandedTransform(index) : staticTransform(index),
            }}
          >
            <span className="flex h-full w-full flex-col">
              <span className="flex h-16 w-full items-center justify-center overflow-hidden rounded-xl bg-pink-50/70">
                {texture || (showStaticContent && coverTexture) ? (
                  <Image
                    src={(texture ?? coverTexture)!.src}
                    alt={expanded ? FINGER_NAMES[index] : set.name}
                    width={96}
                    height={64}
                    /* object-contain：纹理 PNG 自带透明背景的完整甲形，禁止 cover 裁切成方块 */
                    className="h-16 w-full object-contain drop-shadow-[0_1px_2px_var(--shadow-dark)]"
                  />
                ) : (
                  <span className="text-[10px] text-[#b9bab1]">暂无纹理</span>
                )}
              </span>
              <span className="mt-1 block truncate px-0.5 text-center text-[11px] font-medium text-[#67685f]">
                {expanded ? FINGER_NAMES[index] : isCover ? set.name : ""}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function TextureSetPicker({
  sets,
  activeSetId,
  pinnedTextureKey,
  onApplySet,
  onPinTexture,
  onExpandedChange,
}: TextureSetPickerProps) {
  if (sets.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-pink-100 bg-pink-50/40 px-4 py-6 text-center text-sm text-[#8a8b81]">
        纹理套装准备中
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {sets.map((set) => {
        const pinned = parsePinnedTextureKey(pinnedTextureKey);
        const pinnedFinger = pinned && pinned.setId === set.id ? pinned.finger : null;
        return (
          <TextureSetStackCard
            key={set.id}
            set={set}
            active={activeSetId === set.id}
            pinnedFinger={Number.isInteger(pinnedFinger) ? pinnedFinger : null}
            onApplySet={onApplySet}
            onPinTexture={onPinTexture}
            onExpandedChange={onExpandedChange}
          />
        );
      })}
    </div>
  );
}
