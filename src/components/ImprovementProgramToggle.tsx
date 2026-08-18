"use client";

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "jiaru-improvement-program";
const CHANGE_EVENT = "jiaru-improvement-change";

function readStoredValue(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "on";
  } catch {
    // localStorage 不可用时保持默认开启
    return "on";
  }
}

/** 服务器快照：默认开启，与客户端首帧一致，避免 hydration 闪烁。 */
function getServerSnapshot(): string {
  return "on";
}

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

/**
 * 用户改进计划开关（客户端组件）。
 * 默认开启：参与改进计划，允许将手部照片等数据用于产品改进。
 * 用户可随时关闭：关闭后不再上传任何数据。
 * 状态持久化到 localStorage（key: jiaru-improvement-program，值 on/off）。
 */
export function ImprovementProgramToggle() {
  const stored = useSyncExternalStore(subscribe, readStoredValue, getServerSnapshot);
  const enabled = stored !== "off";

  const handleToggle = () => {
    const next = !enabled;
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "on" : "off");
    } catch {
      // 忽略存储失败
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  };

  return (
    <div className="rounded-[26px] border border-pink-100/70 bg-white/60 p-6 shadow-[0_18px_50px_rgba(116,73,92,.07)] backdrop-blur-xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-pink-100/90 to-purple-100/90 text-[#B95F87] shadow-[inset_0_1px_0_rgba(255,255,255,.8)]">
            <svg viewBox="0 0 24 24" width={20} height={20} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </span>
          <div>
            <h2 className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-lg font-semibold text-[#4D464A]">
              用户改进计划
              <span className="rounded-full border border-pink-200/60 bg-pink-50/80 px-2.5 py-0.5 text-[10px] font-semibold tracking-wide text-[#B95F87]">
                {enabled ? "已开启（默认）" : "已关闭"}
              </span>
            </h2>
            <p className="mt-1 text-xs leading-5 text-[#9E9499]">
              {enabled
                ? "开启时，手部照片等数据可能被上传，用于改进识别与生成效果。你随时可以关闭。"
                : "已关闭：所有处理均在浏览器本地完成，不会上传任何数据。可随时重新开启。"}
            </p>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={handleToggle}
          className={`relative inline-flex h-8 w-14 shrink-0 cursor-pointer items-center rounded-full border transition-colors duration-200 ${
            enabled ? "border-pink-200 bg-gradient-to-r from-[#D4749D] to-[#B95F87]" : "border-[#E3D9DD] bg-[#EFE7EA]"
          }`}
        >
          <span
            className={`inline-block h-6 w-6 transform rounded-full bg-white shadow transition-transform duration-200 ${
              enabled ? "translate-x-7" : "translate-x-1"
            }`}
          />
        </button>
      </div>
    </div>
  );
}
