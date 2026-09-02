import assert from "node:assert/strict";
import test from "node:test";

import {
  SEEDREAM_I2I_SYSTEM_PROMPT,
  SEEDREAM_T2I_SYSTEM_PROMPT,
  assembleSeedreamEditPrompt,
  assembleSeedreamPrompt,
} from "../src/lib/seedream-prompt.ts";

test("Seedream 系统提示词保持精简（火山方舟建议中文不超过 300 字）", () => {
  assert.ok(
    SEEDREAM_T2I_SYSTEM_PROMPT.length <= 150,
    `文生图系统词 ${SEEDREAM_T2I_SYSTEM_PROMPT.length} 字超限`
  );
  assert.ok(
    SEEDREAM_I2I_SYSTEM_PROMPT.length <= 150,
    `图生图系统词 ${SEEDREAM_I2I_SYSTEM_PROMPT.length} 字超限`
  );
});

test("组装后总长（含 300 字用户提示词）仍远低于 Agnes 旧链路", () => {
  const userPrompt = "银".repeat(300);
  const t2i = assembleSeedreamPrompt(userPrompt);
  const i2i = assembleSeedreamEditPrompt(userPrompt);
  assert.ok(t2i.length <= 550, `文生图组装后 ${t2i.length} 字超限`);
  assert.ok(i2i.length <= 550, `图生图组装后 ${i2i.length} 字超限`);
  assert.ok(t2i.includes(userPrompt));
  assert.ok(i2i.includes(userPrompt));
});

test("两套提示词核心约束齐全且互相独立", () => {
  // 文生图：手数量 + 五指约束。
  assert.ok(SEEDREAM_T2I_SYSTEM_PROMPT.includes("严禁第三只手"));
  assert.ok(SEEDREAM_T2I_SYSTEM_PROMPT.includes("五根手指"));
  // 图生图：只改指甲、其余保留。
  assert.ok(SEEDREAM_I2I_SYSTEM_PROMPT.includes("唯一基准"));
  assert.ok(SEEDREAM_I2I_SYSTEM_PROMPT.includes("指甲"));
  assert.ok(SEEDREAM_I2I_SYSTEM_PROMPT.includes("完全不变"));
  // 两套提示词不得相同。
  assert.notEqual(SEEDREAM_T2I_SYSTEM_PROMPT, SEEDREAM_I2I_SYSTEM_PROMPT);
});
