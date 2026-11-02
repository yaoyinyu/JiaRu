"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import {
  describeFocusCandidate,
  isFocusableCandidate,
  nextCyclicIndex,
  selectInitialFocusIndex,
  type DialogInitialFocus,
} from "./dialog-focus";
import styles from "./AppDialog.module.css";

interface AppDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  /** 初始焦点落点：默认 "first"（第一个可聚焦元素） */
  initialFocus?: DialogInitialFocus;
  /** Escape 关闭，默认开启 */
  closeOnEsc?: boolean;
  /** 点击背景遮罩关闭，默认开启 */
  closeOnOutside?: boolean;
  children?: ReactNode;
  /** 底部动作排（如 ConfirmDialog 的按钮组） */
  footer?: ReactNode;
}

/** 可聚焦元素查询选择器：链接需带 href；tabindex="-1" 由 isFocusableCandidate 过滤 */
const FOCUSABLE_SELECTOR = "a[href], button, input, select, textarea, summary, [tabindex]";

/* 背景滚动锁定：模块级计数，多实例叠加时只在第一个实例加锁、最后一个实例解锁 */
let scrollLockCount = 0;

function lockBodyScroll(): void {
  scrollLockCount += 1;
  if (scrollLockCount === 1 && typeof document !== "undefined") {
    document.body.style.overflow = "hidden";
  }
}

function unlockBodyScroll(): void {
  if (scrollLockCount > 0) scrollLockCount -= 1;
  if (scrollLockCount === 0 && typeof document !== "undefined") {
    document.body.style.overflow = "";
  }
}

/** 收集弹层内可聚焦元素（保持 DOM 顺序，禁用/负 tabindex 已过滤） */
function collectFocusTargets(panel: HTMLElement): HTMLElement[] {
  return Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) =>
    isFocusableCandidate(describeFocusCandidate(element))
  );
}

/**
 * 全站统一弹层基座（新拟态）。
 * 语义：role="dialog" + aria-modal + 标题/描述编程关联；
 * 交互：初始焦点、Tab 焦点圈定、Escape/遮罩关闭、关闭后焦点恢复、背景滚动锁定；
 * 渲染：createPortal 到 document.body，仅在 open 且客户端环境挂载（SSR 安全）。
 */
export function AppDialog({
  open,
  onClose,
  title,
  description,
  initialFocus = "first",
  closeOnEsc = true,
  closeOnOutside = true,
  children,
  footer,
}: AppDialogProps) {
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const descriptionId = `${baseId}-description`;
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  /* 打开：记录此前焦点、锁定背景滚动、按 initialFocus 落初始焦点；
     关闭：解锁滚动并把焦点恢复到打开前的元素 */
  useEffect(() => {
    if (!open || typeof document === "undefined") return;
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    restoreFocusRef.current = previouslyFocused;
    lockBodyScroll();

    const panel = panelRef.current;
    if (panel) {
      const targets = collectFocusTargets(panel);
      const targetIndex = selectInitialFocusIndex(
        targets.map(describeFocusCandidate),
        initialFocus
      );
      if (targetIndex >= 0) {
        targets[targetIndex].focus();
      } else {
        panel.focus();
      }
    }

    return () => {
      unlockBodyScroll();
      const restoreTarget = restoreFocusRef.current;
      restoreFocusRef.current = null;
      if (restoreTarget && restoreTarget.isConnected) restoreTarget.focus();
    };
  }, [open, initialFocus]);

  /* Escape 关闭 + Tab/Shift+Tab 焦点圈定（在弹层内循环，不漏到背景） */
  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape" && closeOnEsc) {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;
      const targets = collectFocusTargets(panel);
      if (targets.length === 0) {
        // 弹层内没有可聚焦元素：拦下 Tab，把焦点按在面板容器上
        event.preventDefault();
        panel.focus();
        return;
      }
      const activeIndex = targets.findIndex((element) => element === document.activeElement);
      const nextIndex =
        activeIndex === -1
          ? event.shiftKey
            ? targets.length - 1
            : 0
          : nextCyclicIndex(targets.length, activeIndex, event.shiftKey ? -1 : 1);
      event.preventDefault();
      targets[nextIndex].focus();
    },
    [closeOnEsc, onClose]
  );

  /* 点击背景遮罩关闭；命中判断保证弹层内容上的点击不关闭 */
  const handleOverlayClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      if (!closeOnOutside) return;
      if (event.target === event.currentTarget) onClose();
    },
    [closeOnOutside, onClose]
  );

  /* 弹层内容点击不冒泡到遮罩（双保险：配合 handleOverlayClick 的命中判断） */
  const handlePanelClick = useCallback((event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
  }, []);

  if (!open) return null;
  // SSR 安全：仅在客户端环境挂载 Portal
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className={styles.overlay}
      role="presentation"
      onClick={handleOverlayClick}
      onKeyDown={handleKeyDown}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={styles.panel}
        onClick={handlePanelClick}
      >
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        {description ? (
          <p id={descriptionId} className={styles.description}>
            {description}
          </p>
        ) : null}
        {children ? <div className={styles.body}>{children}</div> : null}
        {footer ? <div className={styles.footer}>{footer}</div> : null}
      </div>
    </div>,
    document.body
  );
}
