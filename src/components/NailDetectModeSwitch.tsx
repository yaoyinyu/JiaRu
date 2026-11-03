"use client";

/**
 * 识别模式切换（v1.2.217）：三个识别站点共用的「本地 | 云端」分段控件。
 *
 * - 新拟态凹陷轨道承载两枚 chip：选中态凸起＋珊瑚底，按压/悬停有位移与
 *   阴影反馈，focus-visible 落珊瑚描边环；
 * - 云端 chip 在确认两个后端都未配置时禁用（锁形图标 + title 说明原因）；
 * - 切到云端且尚无一次性隐私确认时先弹 AppDialog 说明（图片将上传至所选
 *   云端视觉服务、仅用于本次定位、不用于训练；本地模式不受影响），同意后
 *   才真正切换；同意回调 onConsentGranted 内由页面自行同步 ref 并触发识别
 *   （组件不再提供同步 onCloudReady——同意点击时刻页面状态尚未重渲染，
 *   同步回调必然读到旧 mode/consent）；
 * - 两个云端后端都可用时显示子选项（方舟视觉默认 / 云端自托管抠图）。
 */
import { useState } from "react";

import { AppDialog } from "@/components/ui/AppDialog";
import {
  hasAnyCloudBackend,
  NAIL_CLOUD_BACKEND_LABELS,
  type NailCloudAvailability,
  type NailCloudBackend,
  type NailDetectMode,
} from "@/lib/nail-detect-mode";

interface NailDetectModeSwitchProps {
  mode: NailDetectMode;
  onModeChange: (mode: NailDetectMode) => void;
  backend: NailCloudBackend;
  onBackendChange: (backend: NailCloudBackend) => void;
  availability: NailCloudAvailability;
  availabilityLoaded: boolean;
  consentGiven: boolean;
  /** 用户在弹层中同意云端识别（hook 落库并刷新状态；页面可在此同步 ref 后立即识别）。 */
  onConsentGranted: () => void;
  /** 云端 chip 禁用时的占位说明由组件内置；页面可追加下划线说明。 */
  disabled?: boolean;
}

const SEGMENT_CLASS = (active: boolean, disabledChip = false) =>
  [
    "inline-flex min-h-9 items-center gap-1.5 rounded-full px-4 py-1.5 text-xs font-medium",
    "transition-all duration-200 ease-out active:scale-[.96]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--coral)]",
    active
      ? "bg-[var(--coral-soft)] text-[var(--coral-deep)] shadow-[var(--neu-out-sm)]"
      : disabledChip
        ? "cursor-not-allowed text-[#b9b3a8]"
        : "text-[#67685f] hover:text-[var(--coral-text)] hover:bg-[#e7e1d8]/80",
  ]
    .filter(Boolean)
    .join(" ");

const BACKEND_CLASS = (active: boolean) =>
  [
    "inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium",
    "transition-all duration-200 ease-out active:scale-[.96]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--coral)]",
    active
      ? "bg-[var(--coral-soft)] text-[var(--coral-deep)] shadow-[var(--neu-out-sm)]"
      : "text-[#67685f] hover:bg-[#e7e1d8]/80 hover:text-[var(--coral-text)]",
  ].join(" ");

function LockGlyph() {
  return (
    <svg aria-hidden="true" viewBox="0 0 12 12" className="h-3 w-3" fill="none">
      <rect x="2.2" y="5.2" width="7.6" height="5.2" rx="1.4" stroke="currentColor" strokeWidth="1.3" />
      <path d="M4 5V3.6a2 2 0 0 1 4 0V5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

export function NailDetectModeSwitch({
  mode,
  onModeChange,
  backend,
  onBackendChange,
  availability,
  availabilityLoaded,
  consentGiven,
  onConsentGranted,
  disabled = false,
}: NailDetectModeSwitchProps) {
  const [consentOpen, setConsentOpen] = useState(false);
  const cloudConfigured = hasAnyCloudBackend(availability);
  const cloudDisabled = disabled || (availabilityLoaded && !cloudConfigured);
  const cloudTitle = availabilityLoaded && !cloudConfigured
    ? "云端识别未配置（需在服务端设置 ARK_VISION_MODEL 或 NAIL_CLOUD_MATTE_URL）"
    : disabled
      ? "当前状态暂不能切换识别模式"
      : undefined;

  const handleModeClick = (next: NailDetectMode) => {
    if (disabled) return;
    if (next === mode) return;
    if (next === "cloud") {
      if (cloudDisabled) return;
      if (!consentGiven) {
        setConsentOpen(true);
        return;
      }
      onModeChange("cloud");
      return;
    }
    onModeChange("local");
  };

  const handleConsentConfirm = () => {
    setConsentOpen(false);
    onConsentGranted();
    onModeChange("cloud");
  };

  return (
    <div className="flex flex-wrap items-center gap-2.5">
      <p className="text-xs font-medium text-[#67685f]">识别模式</p>
      <div
        role="group"
        aria-label="识别模式"
        className="inline-flex items-center gap-1 rounded-full border border-pink-100/80 bg-[#efece6]/70 p-1 shadow-[var(--neu-in-sm)]"
      >
        <button
          type="button"
          aria-pressed={mode === "local"}
          onClick={() => handleModeClick("local")}
          className={SEGMENT_CLASS(mode === "local", disabled && mode !== "local")}
        >
          本地
        </button>
        <button
          type="button"
          aria-pressed={mode === "cloud"}
          onClick={() => handleModeClick("cloud")}
          disabled={cloudDisabled}
          title={cloudTitle}
          className={SEGMENT_CLASS(mode === "cloud", cloudDisabled)}
        >
          {availabilityLoaded && !cloudConfigured ? <LockGlyph /> : null}
          云端
        </button>
      </div>
      {mode === "cloud" && availability.ark && availability.cloudMatte ? (
        <div
          role="group"
          aria-label="云端识别后端"
          className="inline-flex items-center gap-1 rounded-full bg-[#efece6]/50 px-1 py-0.5"
        >
          <button
            type="button"
            aria-pressed={backend === "ark"}
            onClick={() => onBackendChange("ark")}
            className={BACKEND_CLASS(backend === "ark")}
          >
            {NAIL_CLOUD_BACKEND_LABELS.ark}
          </button>
          <button
            type="button"
            aria-pressed={backend === "cloud-matte"}
            onClick={() => onBackendChange("cloud-matte")}
            className={BACKEND_CLASS(backend === "cloud-matte")}
          >
            {NAIL_CLOUD_BACKEND_LABELS["cloud-matte"]}
          </button>
        </div>
      ) : null}
      <AppDialog
        open={consentOpen}
        onClose={() => setConsentOpen(false)}
        title="云端识别隐私说明"
        description="请确认后再使用云端识别。"
        initialFocus="cancel"
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConsentOpen(false)}
              className="inline-flex min-h-11 items-center rounded-full border border-pink-100 bg-pink-50/65 px-4 text-xs font-medium text-[#a34b3f] transition hover:bg-[var(--surface)]"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConsentConfirm}
              className="inline-flex min-h-11 items-center rounded-full bg-[var(--coral-soft)] px-4 text-xs font-medium text-[var(--coral-deep)] transition hover:shadow-[var(--neu-out-sm)] active:scale-[.97]"
            >
              同意并使用云端识别
            </button>
          </div>
        }
      >
        <ul className="grid gap-2 text-sm leading-6 text-[#67685f]">
          <li>· 选择云端后，当前照片将上传至所选云端服务，仅用于本次甲面定位。</li>
          <li>· 照片不用于训练、不长期留存；结果为低置信候选，须逐指确认。</li>
          <li>· 本地模式始终在本机完成；本说明只需确认一次。</li>
        </ul>
      </AppDialog>
    </div>
  );
}
