"use client";

import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { NEU_TOGGLE_TRAVEL, resolveDragFrame } from "@/lib/ui/toggle-drag";
import styles from "./NeuToggle.module.css";

interface NeuToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
}

/**
 * 新拟态拨动开关：凹陷轨道＋凸起滑块，选中态珊瑚轨道。
 * 支持指针拖拽——越过中点时滑块向吸引极倾斜（磁吸），松手由
 * `--ease-spring` 过冲弹簧完成吸附或回弹；点击/键盘切换走同一弹簧。
 * 语义为真实 checkbox（sr-only），键盘空格可切换、focus 环落在轨道上。
 */
export function NeuToggle({ checked, onChange, disabled = false, children }: NeuToggleProps) {
  const rowRef = useRef<HTMLLabelElement>(null);
  const trackRef = useRef<HTMLSpanElement>(null);
  const dragState = useRef<{ pointerId: number; startX: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const timers = useRef<number[]>([]);

  const clearTimers = useCallback(() => {
    for (const id of timers.current) window.clearTimeout(id);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  /* 起步横拉挤压 120ms → 落位微压 80ms（design/consumer-v1 §2.2 同编排） */
  const playElastic = useCallback(() => {
    const row = rowRef.current;
    if (!row || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    clearTimers();
    row.classList.remove(styles.rowSettling);
    row.classList.add(styles.rowStretching);
    timers.current.push(
      window.setTimeout(() => {
        row.classList.remove(styles.rowStretching);
        row.classList.add(styles.rowSettling);
        timers.current.push(window.setTimeout(() => row.classList.remove(styles.rowSettling), 80));
      }, 120)
    );
  }, [clearTimers]);

  const handleCheckedChange = useCallback(
    (next: boolean) => {
      playElastic();
      onChange(next);
    },
    [onChange, playElastic]
  );

  const applyDragFrame = useCallback((startX: number, pointerX: number) => {
    const row = rowRef.current;
    const track = trackRef.current;
    if (!row || !track) return null;
    const frame = resolveDragFrame({ baseX: checked ? NEU_TOGGLE_TRAVEL : 0, startX, x: pointerX });
    track.style.setProperty("--knob-x", `${frame.x}px`);
    track.style.setProperty("--knob-pull", `${frame.pull}px`);
    row.classList.toggle(styles.rowStretching, frame.moved);
    return frame;
  }, [checked]);

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      if (disabled) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      dragState.current = { pointerId: event.pointerId, startX: event.clientX, moved: false };
      event.currentTarget.setPointerCapture(event.pointerId);
      rowRef.current?.classList.add(styles.rowPressing, styles.rowDragging);
    },
    [disabled]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      const state = dragState.current;
      if (!state || event.pointerId !== state.pointerId) return;
      const frame = applyDragFrame(state.startX, event.clientX);
      if (frame?.moved) state.moved = true;
    },
    [applyDragFrame]
  );

  const endDrag = useCallback(
    (event: React.PointerEvent<HTMLSpanElement>) => {
      const state = dragState.current;
      if (!state || event.pointerId !== state.pointerId) return;
      dragState.current = null;
      const row = rowRef.current;
      row?.classList.remove(styles.rowPressing, styles.rowDragging, styles.rowStretching);
      trackRef.current?.style.setProperty("--knob-pull", "0px");
      trackRef.current?.style.removeProperty("--knob-x");
      if (!state.moved) return; // 视为点击：label 原生切换触发 input onChange
      const frame = resolveDragFrame({ baseX: checked ? NEU_TOGGLE_TRAVEL : 0, startX: state.startX, x: event.clientX });
      suppressClick.current = true; // 拖拽已自行决定状态，拦截 label 的 click 二次翻转
      if (frame.shouldCheck !== checked) handleCheckedChange(frame.shouldCheck);
    },
    [checked, handleCheckedChange]
  );

  /* 拖拽松手后拦截 label 对隐藏 input 的 click 转发，避免状态被二次翻转 */
  const handleClickCapture = useCallback((event: React.MouseEvent<HTMLLabelElement>) => {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const rowClasses = [
    styles.row,
    checked ? styles.rowOn : "",
    disabled ? styles.rowDisabled : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <label className={rowClasses} onClickCapture={handleClickCapture}>
      <input
        type="checkbox"
        className={styles.input}
        checked={checked}
        disabled={disabled}
        onChange={(event) => handleCheckedChange(event.target.checked)}
      />
      <span
        ref={trackRef}
        className={styles.track}
        aria-hidden="true"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <span className={styles.knob} />
      </span>
      <span className={styles.labelText}>{children}</span>
    </label>
  );
}
