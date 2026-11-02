/**
 * AppDialog 焦点管理的可测纯逻辑（node 可测，不依赖真实 DOM）。
 *
 * 职责边界：
 * - isFocusableCandidate：判定候选元素能否进入 Tab 焦点圈；
 * - nextCyclicIndex：Tab / Shift+Tab 的焦点圈循环（含空列表、单元素、越界索引）；
 * - selectInitialFocusIndex：按 initialFocus 语义从候选中选初始焦点目标；
 * - describeFocusCandidate：从真实元素的最小结构提取候选描述（供上面三者消费）。
 *
 * 依赖真实 DOM API 的元素查询本身留在 AppDialog 组件内。
 */

export type DialogInitialFocus = "first" | "confirm" | "cancel";

/** 可聚焦候选的最小描述：字段全部可在 node 测试里手工构造 */
export interface FocusCandidateInfo {
  /** 小写标签名（如 "button"、"a"） */
  tagName: string;
  /** 表单控件禁用态；非控件元素省略 */
  disabled?: boolean;
  /** tabindex；undefined 表示元素未提供（按标签默认值处理） */
  tabIndex?: number;
  /** 是否携带 href（仅链接参与判定） */
  hasHref?: boolean;
  /** data-autofocus 标记值（"confirm" / "cancel" / 自定义） */
  autoFocusMark?: string | null;
}

/** 原生可聚焦标签（a 需另带 href，见 isFocusableCandidate） */
const FOCUSABLE_TAG_NAMES: ReadonlySet<string> = new Set([
  "a",
  "button",
  "input",
  "select",
  "textarea",
  "summary",
]);

/** 判定候选是否可进入 Tab 焦点圈：禁用、tabindex="-1"、无 href 的链接一律排除 */
export function isFocusableCandidate(info: FocusCandidateInfo): boolean {
  if (info.disabled === true) return false;
  if (info.tabIndex !== undefined && info.tabIndex < 0) return false;
  if (info.tagName === "a" && info.hasHref !== true) return false;
  if (FOCUSABLE_TAG_NAMES.has(info.tagName)) return true;
  return info.tabIndex !== undefined && info.tabIndex >= 0;
}

/** 从真实元素的最小结构提取候选描述（真实 Element 均满足该结构，node 测试可用普通对象） */
export function describeFocusCandidate(element: {
  tagName: string;
  disabled?: boolean;
  tabIndex?: number;
  getAttribute(name: string): string | null;
}): FocusCandidateInfo {
  const tabindexAttribute = element.getAttribute("tabindex");
  const explicit =
    tabindexAttribute === null ? undefined : Number.parseInt(tabindexAttribute, 10);
  return {
    tagName: element.tagName.toLowerCase(),
    disabled: element.disabled === true,
    hasHref: element.getAttribute("href") !== null,
    tabIndex: explicit !== undefined && !Number.isNaN(explicit) ? explicit : element.tabIndex,
    autoFocusMark: element.getAttribute("data-autofocus"),
  };
}

/**
 * 焦点圈循环：count 为圈内候选数，activeIndex 为当前焦点索引，
 * direction 取 1（Tab）或 -1（Shift+Tab），返回下一索引。
 * 空列表返回 -1；单元素恒为 0；越界/负数索引先按模回卷再步进；非整数索引返回 -1。
 */
export function nextCyclicIndex(count: number, activeIndex: number, direction: 1 | -1): number {
  if (!Number.isInteger(count) || count <= 0) return -1;
  if (count === 1) return 0;
  if (!Number.isInteger(activeIndex)) return -1;
  const base = ((activeIndex % count) + count) % count;
  return (base + direction + count) % count;
}

/**
 * 初始焦点目标选择：candidates 须为已经 isFocusableCandidate 过滤的可聚焦候选（保持 DOM 顺序）。
 * "confirm" / "cancel" 优先取 data-autofocus 标记命中的第一个候选，标记缺失时回退到第一个候选；
 * "first" 恒取第一个候选；无候选返回 -1。
 */
export function selectInitialFocusIndex(
  candidates: readonly FocusCandidateInfo[],
  initialFocus: DialogInitialFocus
): number {
  if (candidates.length === 0) return -1;
  if (initialFocus === "confirm" || initialFocus === "cancel") {
    const marked = candidates.findIndex((candidate) => candidate.autoFocusMark === initialFocus);
    if (marked !== -1) return marked;
  }
  return 0;
}
