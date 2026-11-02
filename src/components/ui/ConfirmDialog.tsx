"use client";

import { AppDialog } from "./AppDialog";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  /** 确认按钮文案，默认「确认」 */
  confirmLabel?: string;
  /** 取消按钮文案，默认「取消」 */
  cancelLabel?: string;
  /** 破坏性确认：确认钮使用珊瑚深色实底 */
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/* 按钮样式与全站一致（ProfileEditor 编辑态的取消/保存按钮同款） */
const cancelButtonClass =
  "min-h-11 rounded-xl border border-[var(--coral-soft)] bg-[var(--surface)] px-5 py-2.5 text-sm font-medium text-[var(--muted)] shadow-[var(--neu-out-sm)] transition hover:opacity-90";

const confirmButtonClass =
  "min-h-11 rounded-xl bg-[var(--coral)] px-6 py-2.5 text-sm font-semibold text-white shadow-[var(--neu-out-sm)] transition hover:opacity-90";

const destructiveConfirmButtonClass =
  "min-h-11 rounded-xl bg-[var(--coral-deep)] px-6 py-2.5 text-sm font-semibold text-white shadow-[var(--neu-out-sm)] transition hover:opacity-90";

/**
 * 破坏性确认弹层（基于 AppDialog）。
 * Escape/背景遮罩/取消钮统一走 onCancel，确认钮走 onConfirm；
 * 初始焦点默认落在取消钮（安全默认），按钮经 data-autofocus 标记交给 AppDialog 定位。
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <AppDialog
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      initialFocus="cancel"
      footer={
        <>
          <button
            type="button"
            data-autofocus="cancel"
            className={cancelButtonClass}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            data-autofocus="confirm"
            className={destructive ? destructiveConfirmButtonClass : confirmButtonClass}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </>
      }
    />
  );
}
