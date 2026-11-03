"use client";

/**
 * 美甲纹理套装点选器（§5.4 重构）：每套一张「卡片堆叠」+ 独立「应用全部」。
 *
 * - 静止态：前 3 张可见（第 1 张为该套拇指纹理封面 + 套装名），
 *   堆叠下方给出两个明确动作 [选择这套]（onApplySet）与 [查看单指]（展开扇形）；
 *   点堆叠本体只展开（移动端不再直接应用套装），桌面 hover 展开保留。
 * - 容器可聚焦（tabIndex=0，role=group + aria-expanded）：
 *   Enter 展开/收起，Escape 收起；展开态点单卡 = 钉选该纹理（aria-pressed）。
 * - 「应用全部」独立按钮：为当前激活套装做两步内联确认（armed 态 5 秒内
 *   再次点击执行，超时/失焦/Esc 取消；不使用浏览器原生确认弹窗）。
 * - 展开状态通过 onExpandedChange 上报页面渲染全页模糊遮罩；卸载时确保上报 null。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import Image from "next/image";
import { FINGER_NAMES } from "@/lib/utils";
import type { NailTextureSet } from "@/lib/nail-texture-sets";
import { parsePinnedTextureKey } from "@/lib/editor-texture-state";

export interface TextureSetPickerProps {
  sets: readonly NailTextureSet[];
  activeSetId: string | null;
  /** "<setId>/<finger>" 格式的钉选纹理键 */
  pinnedTextureKey: string | null;
  /** 可贴合的甲面框数量（应用全部按钮的确认计数；0 时按钮禁用） */
  frameCount: number;
  /** 已有贴合数量（armed 说明中提示将被替换） */
  placementCount: number;
  onApplySet(setId: string): void;
  onPinTexture(setId: string, finger: number): void;
  onApplyAll(setId: string): void;
  onExpandedChange(expandedSetId: string | null): void;
}

/** 展开扇形的相邻卡水平间距：2×56 + 96px 卡宽 = 208px，360px 面板（内容约 320px）内不溢出。 */
const FAN_STEP_PX = 56;
/** 静止态可见的堆叠卡数量。 */
const STATIC_VISIBLE_CARDS = 3;
/** 应用全部两步确认的 armed 等待时长。 */
const APPLY_ALL_ARMED_MS = 5000;

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

  const expand = useCallback(() => {
    setTapExpanded(true);
    reportExpanded(true);
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

  // 点堆叠本体：静止态展开、展开态收起（不再由堆叠点击直接应用套装）。
  const handleStackClick = useCallback(() => {
    if (expanded) {
      collapse();
      return;
    }
    expand();
  }, [collapse, expand, expanded]);

  const handleStackKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        if (expanded) {
          collapse();
        } else {
          expand();
        }
        return;
      }
      if (event.key === "Escape" && expanded) {
        event.preventDefault();
        collapse();
      }
    },
    [collapse, expand, expanded]
  );

  const handleCardClick = useCallback(
    (finger: number, hasTexture: boolean) => {
      if (!expanded) {
        // 静止态点堆叠卡 = 展开（不直接应用套装）。
        expand();
        return;
      }
      if (!hasTexture) return;
      onPinTexture(set.id, finger);
      if (!hoverCapable) collapse();
    },
    [collapse, expanded, expand, hoverCapable, onPinTexture, set.id]
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
      aria-label={expanded ? `纹理套装：${set.name}（已展开）` : `纹理套装：${set.name}（已折叠）`}
      tabIndex={0}
      className={`relative rounded-2xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--coral)] ${expanded ? "z-40" : ""}`}
      onKeyDown={handleStackKeyDown}
    >
      <div
        className="relative h-28"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleStackClick}
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
            选择这套
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
                    <span className="text-[12px] text-[#6f7066]">暂无纹理</span>
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
      {!expanded && (
        <div className="mt-1.5 flex gap-1.5">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              handleApplyClick();
            }}
            className={`flex-1 rounded-xl px-2 py-1.5 text-[11px] font-medium transition hover:-translate-y-0.5 active:scale-95 ${
              active
                ? "bg-[var(--coral)] text-white shadow-[var(--neu-out-sm)]"
                : "border border-pink-100 bg-[var(--surface)] text-[#ac5145] shadow-sm"
            }`}
          >
            {active ? "已选择 · 重新选择" : "选择这套"}
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              expand();
            }}
            className="flex-1 rounded-xl border border-pink-100 bg-[var(--surface)] px-2 py-1.5 text-[11px] text-[#6f7066] shadow-sm transition hover:-translate-y-0.5 hover:text-[#ac5145] active:scale-95"
          >
            查看单指
          </button>
        </div>
      )}
    </div>
  );
}

export function TextureSetPicker({
  sets,
  activeSetId,
  pinnedTextureKey,
  frameCount,
  placementCount,
  onApplySet,
  onPinTexture,
  onApplyAll,
  onExpandedChange,
}: TextureSetPickerProps) {
  const [applyAllArmed, setApplyAllArmed] = useState(false);
  const armedTimerRef = useRef<number | null>(null);

  const disarmApplyAll = useCallback(() => {
    setApplyAllArmed(false);
    if (armedTimerRef.current !== null) {
      window.clearTimeout(armedTimerRef.current);
      armedTimerRef.current = null;
    }
  }, []);

  // 套装切换 / 卸载时解除 armed 态并清理计时器。
  // 经微任务触发：effect 同步路径不调用含 setState 的 disarm。
  useEffect(() => {
    queueMicrotask(disarmApplyAll);
  }, [activeSetId, disarmApplyAll]);

  useEffect(
    () => () => {
      if (armedTimerRef.current !== null) {
        window.clearTimeout(armedTimerRef.current);
      }
    },
    []
  );

  const activeSet = sets.find((item) => item.id === activeSetId) ?? null;
  const applyAllDisabled = !activeSet || frameCount === 0;

  const handleApplyAllClick = useCallback(() => {
    if (!activeSetId || frameCount === 0) return;
    if (!applyAllArmed) {
      // 首次点击进入 armed 态：5 秒内再次点击执行，超时/失焦/Esc 取消。
      setApplyAllArmed(true);
      if (armedTimerRef.current !== null) window.clearTimeout(armedTimerRef.current);
      armedTimerRef.current = window.setTimeout(() => {
        armedTimerRef.current = null;
        setApplyAllArmed(false);
      }, APPLY_ALL_ARMED_MS);
      return;
    }
    disarmApplyAll();
    onApplyAll(activeSetId);
  }, [activeSetId, applyAllArmed, disarmApplyAll, frameCount, onApplyAll]);

  if (sets.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-pink-100 bg-pink-50/40 px-4 py-6 text-center text-sm text-[#6f7066]">
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

      <div className="pt-1">
        <button
          type="button"
          disabled={applyAllDisabled}
          onClick={handleApplyAllClick}
          onBlur={applyAllArmed ? disarmApplyAll : undefined}
          onKeyDown={(event) => {
            if (event.key === "Escape" && applyAllArmed) {
              event.preventDefault();
              disarmApplyAll();
            }
          }}
          className={`h-11 w-full rounded-2xl text-sm font-medium transition-[transform,background-color,border-color,box-shadow,color] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 ${
            applyAllArmed
              ? "bg-[#a34b3f] text-white shadow-[var(--neu-out-sm)]"
              : "border border-pink-100 bg-[var(--surface)] text-[#67685f] shadow-sm hover:-translate-y-0.5 hover:text-[#ac5145]"
          }`}
        >
          {applyAllArmed
            ? `确认替换 ${frameCount} 个甲面`
            : "将当前套装应用到全部甲面"}
        </button>
        {applyAllArmed && activeSet ? (
          <p role="status" className="mt-1.5 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
            将为 {frameCount} 个甲面框贴合「{activeSet.name}」纹理
            {placementCount > 0 ? `，其中 ${placementCount} 处已有贴合将被替换` : ""}
            ；5 秒内再次点击确认，Esc、移开焦点或超时取消。
          </p>
        ) : applyAllDisabled ? (
          <p className="mt-1.5 text-xs leading-5 text-[#6f7066]">
            {activeSet ? "暂无甲面框，请先识别或手动添加。" : "先在上方选择一套纹理。"}
          </p>
        ) : null}
      </div>
    </div>
  );
}
