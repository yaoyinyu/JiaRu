import assert from "node:assert/strict";
import test from "node:test";

import {
  describeFocusCandidate,
  isFocusableCandidate,
  nextCyclicIndex,
  selectInitialFocusIndex,
} from "../src/components/ui/dialog-focus.ts";

/**
 * AppDialog 焦点管理纯逻辑行为测试（无 DOM，普通对象构造最小结构）：
 *  - nextCyclicIndex：Tab/Shift+Tab 循环、空列表、单元素、越界索引；
 *  - selectInitialFocusIndex：按 initialFocus 选择目标、标记缺失回退、空候选；
 *  - isFocusableCandidate / describeFocusCandidate：可聚焦判定与最小结构提取。
 */

/** 构造满足 describeFocusCandidate 最小结构的假元素 */
function fakeElement(overrides: {
  tagName: string;
  disabled?: boolean;
  tabIndex?: number;
  attributes?: Record<string, string>;
}) {
  return {
    tagName: overrides.tagName,
    disabled: overrides.disabled,
    tabIndex: overrides.tabIndex,
    getAttribute: (name: string): string | null => overrides.attributes?.[name] ?? null,
  };
}

test("nextCyclicIndex 在焦点圈内循环步进（Tab 与 Shift+Tab）", () => {
  // Tab 向后：中段 +1，末尾回卷到 0
  assert.equal(nextCyclicIndex(5, 2, 1), 3);
  assert.equal(nextCyclicIndex(5, 4, 1), 0);
  // Shift+Tab 向前：开头回卷到末尾
  assert.equal(nextCyclicIndex(5, 0, -1), 4);
  assert.equal(nextCyclicIndex(5, 2, -1), 1);
});

test("nextCyclicIndex 边界：空列表返回 -1，单元素恒为 0", () => {
  assert.equal(nextCyclicIndex(0, 0, 1), -1);
  assert.equal(nextCyclicIndex(0, 0, -1), -1);
  assert.equal(nextCyclicIndex(0, 7, 1), -1);
  assert.equal(nextCyclicIndex(1, 0, 1), 0);
  assert.equal(nextCyclicIndex(1, 0, -1), 0);
});

test("nextCyclicIndex 边界：越界与负数索引按模回卷后步进", () => {
  // 正向越界：7 % 3 = 1 → 2
  assert.equal(nextCyclicIndex(3, 7, 1), 2);
  // 恰好等于 count：回卷到 0 → 1
  assert.equal(nextCyclicIndex(3, 3, 1), 1);
  // 负数索引：-1 回卷到末位 2 → Tab 回到 0
  assert.equal(nextCyclicIndex(3, -1, 1), 0);
  // 负数索引越界：-5 % 3 = -2 → 回卷到 1 → Shift+Tab 到 0
  assert.equal(nextCyclicIndex(3, -5, -1), 0);
  // 非整数索引（如 NaN）无意义，返回 -1
  assert.equal(nextCyclicIndex(3, Number.NaN, 1), -1);
});

test("selectInitialFocusIndex：first 恒取第一个，confirm/cancel 按标记命中", () => {
  const candidates = [
    { tagName: "button", autoFocusMark: "cancel" },
    { tagName: "button", autoFocusMark: "confirm" },
    { tagName: "input" },
  ];
  assert.equal(selectInitialFocusIndex(candidates, "first"), 0);
  assert.equal(selectInitialFocusIndex(candidates, "cancel"), 0);
  assert.equal(selectInitialFocusIndex(candidates, "confirm"), 1);
});

test("selectInitialFocusIndex：同名标记取第一个命中", () => {
  const candidates = [
    { tagName: "button" },
    { tagName: "button", autoFocusMark: "confirm" },
    { tagName: "button" },
    { tagName: "button", autoFocusMark: "confirm" },
  ];
  assert.equal(selectInitialFocusIndex(candidates, "confirm"), 1);
});

test("selectInitialFocusIndex：标记缺失时回退到第一个候选", () => {
  const candidates = [{ tagName: "button", autoFocusMark: "confirm" }, { tagName: "button" }];
  // 请求 cancel 但无 cancel 标记：回退第一个
  assert.equal(selectInitialFocusIndex(candidates, "cancel"), 0);
  // 无任何标记：confirm/cancel/first 都回退第一个
  const unmarked = [{ tagName: "button" }, { tagName: "input" }];
  assert.equal(selectInitialFocusIndex(unmarked, "confirm"), 0);
  assert.equal(selectInitialFocusIndex(unmarked, "cancel"), 0);
  assert.equal(selectInitialFocusIndex(unmarked, "first"), 0);
});

test("selectInitialFocusIndex：空候选列表返回 -1", () => {
  assert.equal(selectInitialFocusIndex([], "first"), -1);
  assert.equal(selectInitialFocusIndex([], "confirm"), -1);
  assert.equal(selectInitialFocusIndex([], "cancel"), -1);
});

test("isFocusableCandidate：禁用、负 tabindex、无 href 链接被排除", () => {
  assert.equal(isFocusableCandidate({ tagName: "button" }), true);
  assert.equal(isFocusableCandidate({ tagName: "button", disabled: true }), false);
  assert.equal(isFocusableCandidate({ tagName: "button", tabIndex: -1 }), false);
  assert.equal(isFocusableCandidate({ tagName: "input", disabled: true }), false);
  assert.equal(isFocusableCandidate({ tagName: "a" }), false);
  assert.equal(isFocusableCandidate({ tagName: "a", hasHref: true }), true);
  assert.equal(isFocusableCandidate({ tagName: "div" }), false);
  assert.equal(isFocusableCandidate({ tagName: "div", tabIndex: 0 }), true);
  assert.equal(isFocusableCandidate({ tagName: "span", tabIndex: 2 }), true);
});

test("describeFocusCandidate：从最小结构提取小写标签、href、data-autofocus 与 tabindex", () => {
  const described = describeFocusCandidate(
    fakeElement({
      tagName: "BUTTON",
      attributes: { "data-autofocus": "confirm" },
    })
  );
  assert.deepEqual(
    { ...described, tabIndex: described.tabIndex },
    {
      tagName: "button",
      disabled: false,
      hasHref: false,
      tabIndex: undefined,
      autoFocusMark: "confirm",
    }
  );
  assert.equal(isFocusableCandidate(described), true);
});

test("describeFocusCandidate：disabled 提取与 tabindex 属性解析", () => {
  const disabledButton = describeFocusCandidate(
    fakeElement({ tagName: "BUTTON", disabled: true })
  );
  assert.equal(disabledButton.disabled, true);
  assert.equal(isFocusableCandidate(disabledButton), false);

  const negativeTabindex = describeFocusCandidate(
    fakeElement({ tagName: "DIV", tabIndex: -1, attributes: { tabindex: "-1" } })
  );
  assert.equal(negativeTabindex.tabIndex, -1);
  assert.equal(isFocusableCandidate(negativeTabindex), false);

  // 非法 tabindex 属性值：回退到元素自带的 tabIndex
  const garbageTabindex = describeFocusCandidate(
    fakeElement({ tagName: "DIV", tabIndex: 0, attributes: { tabindex: "abc" } })
  );
  assert.equal(garbageTabindex.tabIndex, 0);
  assert.equal(isFocusableCandidate(garbageTabindex), true);
});

test("describeFocusCandidate：链接元素按 href 判定", () => {
  const linkWithoutHref = describeFocusCandidate(fakeElement({ tagName: "A" }));
  assert.equal(linkWithoutHref.hasHref, false);
  assert.equal(isFocusableCandidate(linkWithoutHref), false);

  const linkWithHref = describeFocusCandidate(
    fakeElement({ tagName: "A", attributes: { href: "#settings" } })
  );
  assert.equal(linkWithHref.hasHref, true);
  assert.equal(isFocusableCandidate(linkWithHref), true);
});

test("组合链路：模拟 ConfirmDialog 按钮排的初始焦点选择", () => {
  // DOM 顺序：取消钮在前、确认钮在后（与 ConfirmDialog footer 一致）
  const candidates = [
    describeFocusCandidate(
      fakeElement({ tagName: "BUTTON", attributes: { "data-autofocus": "cancel" } })
    ),
    describeFocusCandidate(
      fakeElement({ tagName: "BUTTON", attributes: { "data-autofocus": "confirm" } })
    ),
  ];
  assert.equal(isFocusableCandidate(candidates[0]), true);
  assert.equal(isFocusableCandidate(candidates[1]), true);
  // ConfirmDialog 的安全默认：初始焦点落在取消钮
  assert.equal(selectInitialFocusIndex(candidates, "cancel"), 0);
  assert.equal(selectInitialFocusIndex(candidates, "confirm"), 1);
  // 焦点圈：在两个按钮间循环
  assert.equal(nextCyclicIndex(candidates.length, 0, 1), 1);
  assert.equal(nextCyclicIndex(candidates.length, 1, 1), 0);
});
