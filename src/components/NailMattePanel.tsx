"use client";

import { useCallback, useState } from "react";

/**
 * 本机精细抠图入口（展示组件，不发请求）。
 *
 * 该能力属于辅助路径：文案不得出现「自动识别成功」；
 * 成功只报告「已精细处理 N/M 个甲面」，降级明确说明已保留本地结果。
 * 入口可见性由父组件通过 `/api/nail-matte` 的 `enabled` 决定。
 */

export type NailMattePanelStatus = "idle" | "running" | "done" | "degraded" | "error";

export interface NailMatteAvailability {
  enabled: boolean;
  ready: boolean;
  busy: boolean;
}

export interface NailMattePanelProps {
  availability: NailMatteAvailability | null;
  candidateCount: number;
  status: NailMattePanelStatus;
  message?: string | null;
  matchedCount?: number | null;
  /** 已用毫秒数，由父组件按秒推进（本组件不持有时钟） */
  elapsedMs?: number | null;
  disabled?: boolean;
  onRefine: () => void;
  onDetect: () => void;
  onCancel: () => void;
}

const NOTICE_STORAGE_KEY = "jiaru.nail-matte.notice.v1";

export default function NailMattePanel({
  availability,
  candidateCount,
  status,
  message,
  matchedCount,
  elapsedMs,
  disabled = false,
  onRefine,
  onDetect,
  onCancel,
}: NailMattePanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [noticeAccepted, setNoticeAccepted] = useState<boolean | null>(null);

  // 首次展开时才读取本地偏好：避免在 effect 中同步 setState 造成级联渲染。
  const toggleExpanded = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next && noticeAccepted === null) {
      try {
        setNoticeAccepted(window.localStorage.getItem(NOTICE_STORAGE_KEY) === "1");
      } catch {
        setNoticeAccepted(false);
      }
    }
  }, [expanded, noticeAccepted]);

  const acceptNotice = useCallback(() => {
    try {
      window.localStorage.setItem(NOTICE_STORAGE_KEY, "1");
    } catch {
      // 隐私模式下写入失败不阻塞使用，只是每次都要确认
    }
    setNoticeAccepted(true);
  }, []);

  if (!availability || !availability.enabled) return null;

  const running = status === "running";
  const needsNotice = noticeAccepted === false;
  const unavailable = !availability.ready || availability.busy;
  const actionDisabled = disabled || running || unavailable || needsNotice;

  return (
    <div className="rounded-2xl border border-slate-200 bg-[var(--surface)] px-3 py-3">
      <button
        type="button"
        onClick={toggleExpanded}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-sm font-medium text-slate-900">精细抠图（本机）</span>
        <span className="text-xs text-slate-500">
          {running ? "处理中" : expanded ? "收起" : "展开"}
        </span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-5 text-slate-600">
            在本机 GPU 上生成更精细的软边蒙版，只替换当前甲面轮廓，不改变候选数量与手指分配。
            结果仍需人工复核，不计入自动识别成功率。
          </p>

          {needsNotice && (
            <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
              图片会发送到自托管的本地抠图服务处理，仅用于本次轮廓提取，不转发第三方、不写入训练数据。
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={acceptNotice}
                  className="rounded-full bg-emerald-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600"
                >
                  继续
                </button>
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  取消
                </button>
              </div>
            </div>
          )}

          {!availability.ready && !running && (
            <div className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-600">
              本机抠图服务未就绪（未启动或加载中），已保留本地结果。
            </div>
          )}

          {availability.ready && availability.busy && !running && (
            <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
              服务正在处理其他图片，请稍后再试。
            </div>
          )}

          {running ? (
            <div className="flex items-center justify-between gap-2">
              <span role="status" className="text-xs text-slate-600">
                已用 {Math.max(0, Math.round((elapsedMs ?? 0) / 1000))} 秒
                ，取消不会中断服务端已开始的推理。
              </span>
              <button
                type="button"
                onClick={onCancel}
                className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
              >
                取消
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={candidateCount > 0 ? onRefine : onDetect}
              disabled={actionDisabled}
              className="w-full rounded-full bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {candidateCount > 0
                ? `精细处理 ${candidateCount} 个甲面`
                : "兜底识别甲面（需逐指确认）"}
            </button>
          )}

          {status === "done" && message && (
            <div role="status" className="rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-700">
              {message}
              {matchedCount != null && candidateCount > 0
                ? `（已精细处理 ${matchedCount}/${candidateCount} 个甲面）`
                : ""}
            </div>
          )}

          {status === "degraded" && message && (
            <div role="status" className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
              {message} 已保留本地结果。
            </div>
          )}

          {status === "error" && message && (
            <div role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
