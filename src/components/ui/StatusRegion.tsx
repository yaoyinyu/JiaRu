"use client";

/**
 * 统一异步反馈区域。
 *
 * 语义合同（frontend-interaction-redesign-plan §2.2）：
 * - status = loading / success：role="status" + aria-live="polite"；
 * - status = error：role="alert"；
 * - status = idle：不渲染任何内容。
 *
 * live region 约束：计时器/已等待秒数等持续变化的数值禁止放进本区域，
 * 否则读屏会反复播报；如需展示耗时，由调用方放在本组件之外。
 */

export type StatusRegionStatus = "idle" | "loading" | "success" | "error";
export type StatusRegionSeverity = "info" | "success" | "warning" | "error";

interface StatusRegionProps {
  status: StatusRegionStatus;
  message?: string;
  /** 视觉严重级（仅影响配色，不改变 role 语义），默认 info */
  severity?: StatusRegionSeverity;
  className?: string;
}

/** severity → 全站一致色系（emerald/amber/red 与现有页面同色阶，info 用墨/muted） */
const SEVERITY_CLASSES: Record<StatusRegionSeverity, string> = {
  info: "border-[var(--line)] bg-[var(--surface)] text-[var(--muted)]",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  error: "border-red-100 bg-red-50 text-red-600",
};

/** loading 文案若未自带省略号则以 … 结尾 */
export function withLoadingEllipsis(message?: string): string {
  const base = message ?? "正在处理";
  return base.endsWith("…") ? base : `${base}…`;
}

export function StatusRegion({
  status,
  message,
  severity = "info",
  className = "",
}: StatusRegionProps) {
  if (status === "idle") return null;

  const isError = status === "error";
  const text = status === "loading" ? withLoadingEllipsis(message) : (message ?? "");
  if (!text) return null;

  const classes = [
    "rounded-2xl border px-4 py-3 text-sm leading-5",
    SEVERITY_CLASSES[severity],
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      role={isError ? "alert" : "status"}
      aria-live={isError ? undefined : "polite"}
      className={classes}
    >
      {text}
    </div>
  );
}
