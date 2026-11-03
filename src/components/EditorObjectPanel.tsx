"use client";

/**
 * 编辑器对象面板（§5.3 / §5.5 对象列表）。
 *
 * - 纯展示 + 回调：选中对象的状态行与动作（替换/微调/删除、贴合）、
 *   甲面框指位修改、按甲面框逐行的对象列表；状态全部由 editor page 持有。
 * - 布局：桌面（lg+）作为画布下方的固定区块；移动端为固定底部抽屉
 *   （CSS 断点实现，同一 DOM 位置切换定位）。
 * - 对象列表键盘替代：每行是 button（Enter 选中/贴合），↑/↓ 在行间移动焦点。
 */

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { FINGER_NAMES } from "@/lib/utils";

/** 当前选中对象（页面侧派生，面板只负责展示）。 */
export interface EditorObjectSelection {
  /** placement = 已贴合实例；frame = 选中但未贴合的甲面框 */
  kind: "placement" | "frame";
  /** 对象标题，如「食指甲面」「甲面框 3」 */
  objectLabel: string;
  /** 状态行，如「已贴合「黑耀碎闪 / 食指」」「未贴合」 */
  statusLine: string;
}

/** 对象列表行：每个甲面框一行。 */
export interface EditorObjectListItem {
  frameId: string;
  /** 行名：指名（拇指…小指）或「甲面框 N」 */
  label: string;
  /** 是否已有贴合 */
  placed: boolean;
  /** 已贴合纹理描述（如「黑耀碎闪 / 食指」）；未贴合为 null */
  placementLabel: string | null;
  /** 手动框标记 */
  manual: boolean;
}

export interface EditorObjectPanelProps {
  selection: EditorObjectSelection | null;
  items: readonly EditorObjectListItem[];
  /** 当前列表中高亮的 frameId（aria-current） */
  selectedFrameId: string | null;
  /** 选中贴合：替换为当前纹理 */
  onReplace(): void;
  /** 选中贴合：滚动/聚焦微调滑杆区 */
  onAdjust(): void;
  /** 选中贴合：删除贴合 */
  onRemove(): void;
  /** 选中甲面框：用当前纹理贴合 */
  onApplyToFrame(): void;
  /** 对象列表行点击（选中贴合或贴合空框） */
  onSelectItem(frameId: string): void;
  /** 选中甲面框：修改指位 */
  onAssignFinger(finger: number): void;
  /** 选中甲面框的当前指位（面板指位选择器高亮） */
  frameFinger: number | null;
  /** 选中甲面框是否为可删除的手动框 */
  frameDeletable: boolean;
  /** 删除选中的手动甲面框 */
  onDeleteFrame(): void;
}

const ACTION_BUTTON_CLASS =
  "rounded-xl border border-pink-100 bg-[var(--surface)] px-3 py-2 text-xs font-medium text-[#67685f] shadow-sm transition hover:-translate-y-0.5 hover:text-[#ac5145] active:scale-95";

/** 对象列表键盘导航：↑/↓ 在行按钮间移动焦点（Enter 由按钮原生激活）。 */
function handleListKeyDown(event: ReactKeyboardEvent<HTMLUListElement>) {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const rows = event.currentTarget.querySelectorAll<HTMLButtonElement>("button");
  if (rows.length === 0) return;
  event.preventDefault();
  const currentIndex = Array.from(rows).findIndex((row) => row === document.activeElement);
  const nextIndex =
    event.key === "ArrowDown"
      ? Math.min(currentIndex + 1, rows.length - 1)
      : Math.max(currentIndex - 1, 0);
  const next = rows[nextIndex === -1 ? 0 : nextIndex];
  next?.focus();
}

export function EditorObjectPanel({
  selection,
  items,
  selectedFrameId,
  onReplace,
  onAdjust,
  onRemove,
  onApplyToFrame,
  onSelectItem,
  onAssignFinger,
  frameFinger,
  frameDeletable,
  onDeleteFrame,
}: EditorObjectPanelProps) {
  return (
    <section
      aria-label="对象面板"
      className="fixed inset-x-0 bottom-0 z-[45] max-h-[50vh] overflow-y-auto rounded-t-[24px] bg-[var(--surface)] p-4 shadow-[var(--neu-out-lg)] lg:static lg:z-auto lg:max-h-none lg:rounded-[24px] lg:p-5 lg:shadow-[var(--neu-out-md)]"
    >
      <p className="text-xs font-semibold uppercase tracking-[.16em] text-[#ac5145]">Objects</p>
      <h2 className="mt-1 text-base font-semibold text-[#292a27]">当前对象</h2>

      {selection === null ? (
        <p className="mt-3 text-sm leading-6 text-[#6f7066]">
          点击甲面框贴合纹理；选中贴合可替换、微调或删除。
        </p>
      ) : selection.kind === "placement" ? (
        <div className="mt-3">
          <p className="text-sm font-medium text-[#292a27]">当前对象：{selection.objectLabel}</p>
          <p className="mt-1 text-sm text-[#6f7066]">{selection.statusLine}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={onReplace} className={ACTION_BUTTON_CLASS}>
              替换为当前纹理
            </button>
            <button type="button" onClick={onAdjust} className={ACTION_BUTTON_CLASS}>
              微调
            </button>
            <button
              type="button"
              onClick={onRemove}
              className="rounded-xl border border-red-100 bg-[var(--surface)] px-3 py-2 text-xs font-medium text-red-600 shadow-sm transition hover:-translate-y-0.5 active:scale-95"
            >
              删除贴合
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3">
          <p className="text-sm font-medium text-[#292a27]">当前对象：{selection.objectLabel}</p>
          <p className="mt-1 text-sm text-[#6f7066]">{selection.statusLine}</p>
          <button type="button" onClick={onApplyToFrame} className={`mt-3 ${ACTION_BUTTON_CLASS}`}>
            用当前纹理贴合
          </button>
          <div className="mt-3">
            <p className="mb-1.5 text-xs text-[#67685f]">甲面框指位</p>
            <div className="grid grid-cols-5 gap-1.5 rounded-2xl bg-pink-50/60 p-1.5">
              {FINGER_NAMES.map((name, finger) => {
                const active = frameFinger === finger;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => onAssignFinger(finger)}
                    aria-pressed={active || undefined}
                    className={`rounded-xl px-1 py-2 text-[11px] transition ${
                      active
                        ? "bg-[var(--surface)] font-medium text-[#ac5145] shadow-sm"
                        : "text-[#6f7066] hover:bg-[var(--surface)]"
                    }`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
            <p className="mt-1.5 text-xs leading-5 text-[#6f7066]">
              指位决定套装贴合所用纹理。
            </p>
          </div>
          {frameDeletable && (
            <button
              type="button"
              onClick={onDeleteFrame}
              className="mt-3 rounded-xl border border-red-100 bg-[var(--surface)] px-3 py-2 text-xs font-medium text-red-600 shadow-sm transition hover:-translate-y-0.5 active:scale-95"
            >
              删除甲面框
            </button>
          )}
        </div>
      )}

      <div className="mt-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[.16em] text-[#ac5145]">
          甲面对象列表
        </p>
        {items.length === 0 ? (
          <p className="text-sm leading-6 text-[#6f7066]">暂无甲面框；上传照片识别或手动添加后可在此逐个选择。</p>
        ) : (
          <ul role="list" aria-label="甲面对象列表" onKeyDown={handleListKeyDown} className="space-y-1.5">
            {items.map((item) => {
              const selected = item.frameId === selectedFrameId;
              return (
                <li key={item.frameId}>
                  <button
                    type="button"
                    onClick={() => onSelectItem(item.frameId)}
                    aria-current={selected ? "true" : undefined}
                    className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                      selected
                        ? "border-pink-200 bg-[var(--coral-soft)] text-[#a34b3f] shadow-sm"
                        : "border-pink-100 bg-[var(--surface)] text-[#67685f] hover:text-[#ac5145]"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium">
                        {item.label}
                        {item.manual ? "（手动框）" : ""}
                      </span>
                      <span className="text-xs text-[#6f7066]">
                        {item.placed ? `已贴合${item.placementLabel ? ` · ${item.placementLabel}` : ""}` : "未贴合"}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-2 text-xs leading-5 text-[#67685f]">
          列表内可用 ↑/↓ 移动、Enter 选中或贴合；画布内 Delete 删除、方向键微调、Ctrl+Z 撤销。
        </p>
      </div>
    </section>
  );
}
