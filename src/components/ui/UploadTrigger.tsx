"use client";

/**
 * 可聚焦上传触区（frontend-interaction-redesign-plan §2.2 `UploadTrigger`）。
 *
 * 替代不可聚焦的 `label + hidden input` 方案：
 * - 交互宿主是真实 `<button type="button">`：原生可聚焦，Enter / Space 激活，
 *   不需要任何自造键盘代码；
 * - `<input type="file">` 以 sr-only 兄弟节点存在（不在 button 内部，避免嵌套交互元素），
 *   button onClick → inputRef.click() 打开文件选择器；
 * - input onChange 无论成功失败都把 value 重置为空，同一文件可重复选择；
 * - disabled / loading 时按钮与文件输入同时不可用；
 * - loading 态的 spinner 旋转动画只在按钮内部（aria-hidden），不在任何 aria-live 区域。
 *
 * 未来接入点：`/ai-generate` 参考图、AR 纹理参考图、编辑器照片、分析页照片。
 */

import { useCallback, useRef, type ChangeEvent, type ReactNode } from "react";
import styles from "./UploadTrigger.module.css";

interface UploadTriggerProps {
  /** 文件选择回调；multiple 时传入全部文件，否则最多一个 */
  onFiles: (files: File[]) => void;
  /** 接受的文件类型，如 "image/jpeg,image/png,image/webp" */
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  /** 上传中：按钮与文件输入同时禁用，展示 spinner 与 loadingLabel */
  loading?: boolean;
  /** loading 态文案，默认「处理中…」 */
  loadingLabel?: string;
  /** 附加到外层容器的类名（布局用，如 w-full） */
  className?: string;
  "aria-label"?: string;
  /** 按钮内容 */
  children: ReactNode;
}

export function UploadTrigger({
  onFiles,
  accept,
  multiple = false,
  disabled = false,
  loading = false,
  loadingLabel = "处理中…",
  className = "",
  "aria-label": ariaLabel,
  children,
}: UploadTriggerProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const inactive = disabled || loading;

  const handleButtonClick = useCallback(() => {
    if (inactive) return;
    inputRef.current?.click();
  }, [inactive]);

  const handleInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const input = event.currentTarget;
      const files = Array.from(input.files ?? []);
      // 无论成功失败都重置 value：同一文件可重复选择
      input.value = "";
      if (inactive || files.length === 0) return;
      onFiles(multiple ? files : files.slice(0, 1));
    },
    [inactive, multiple, onFiles]
  );

  const rootClassName = [styles.root, className].filter(Boolean).join(" ");

  return (
    <span className={rootClassName}>
      <button
        type="button"
        className={styles.button}
        onClick={handleButtonClick}
        disabled={inactive}
        aria-busy={loading || undefined}
        aria-label={ariaLabel}
      >
        {loading ? (
          <>
            <span className={styles.spinner} aria-hidden="true" />
            <span>{loadingLabel}</span>
          </>
        ) : (
          children
        )}
      </button>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept={accept}
        multiple={multiple}
        disabled={inactive}
        tabIndex={-1}
        aria-hidden="true"
        onChange={handleInputChange}
      />
    </span>
  );
}
