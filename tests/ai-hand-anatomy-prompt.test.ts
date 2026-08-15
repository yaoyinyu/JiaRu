import assert from "node:assert/strict";
import test from "node:test";
import {
  AI_IMAGE_SCENE_SUFFIX,
  HAND_ANATOMY_SYSTEM_PROMPT,
  HAND_COUNT_PREFIX,
  assembleAiImagePrompt,
} from "../src/lib/ai-hand-anatomy-prompt.ts";

test("assembleAiImagePrompt orders prefix, user prompt, suffix, then hidden system prompt", () => {
  const user = "粉色的樱花美甲";
  const assembled = assembleAiImagePrompt(user);
  const prefixIndex = assembled.indexOf(HAND_COUNT_PREFIX);
  const userIndex = assembled.indexOf(user);
  const suffixIndex = assembled.indexOf(AI_IMAGE_SCENE_SUFFIX);
  const systemIndex = assembled.indexOf(HAND_ANATOMY_SYSTEM_PROMPT);
  assert.ok(prefixIndex === 0, "hand-count prefix must come first");
  assert.ok(userIndex > prefixIndex, "user prompt must follow the prefix");
  assert.ok(suffixIndex > userIndex, "scene suffix must follow user prompt");
  assert.ok(systemIndex > suffixIndex, "system prompt must follow suffix");
  assert.ok(assembled.endsWith(HAND_ANATOMY_SYSTEM_PROMPT));
});

test("assembleAiImagePrompt covers all hand defect constraints", () => {
  for (const keyword of [
    "描述中的动作决定手部数量",
    "单手动作",
    "双手动作",
    "手捧、手端、手托",
    "绝对禁止第三只手",
    "必须且只能有五根手指",
    "不多不少",
    "第六根手指",
    "七根手指",
    "手指分叉",
    "六指",
    "七指",
    "NO extra fingers",
    "NO sixth finger",
    "NO missing fingers",
    "NO four fingers",
    "NO fused fingers",
    "NO webbed fingers",
    "严禁从画面外伸出额外的第三只手",
    "再次强调",
    "第三只手",
    "多余的手",
    "多余的手臂",
    "五根完整",
    "手指数量精确为五根",
    "手掌完整无残缺",
    "两只手轮廓清晰",
    "不得交叠、粘连、融合或互相穿插",
    "双手交叠",
    "双手粘连",
    "双手融合",
    "手指交叉缠绕",
    "手指互相穿插",
    "双手边界模糊",
    "NO merged hands",
    "NO overlapping hands",
    "NO tangled fingers",
    "NO interlocked fingers",
    "NO conjoined hands",
    "NO blurred hand boundaries",
    "不得相互穿模",
    "多指",
    "缺指",
    "手指不全",
    "手指粘连",
    "手掌残缺",
    "畸形手",
    "坏解剖",
    "NO extra hands",
    "NO third hand",
    "NO more than two hands",
    "NO multiple hands",
    "NO additional hands",
    "NO duplicate hands",
    "NO extra arms",
    "extra fingers",
    "missing fingers",
    "fused fingers",
    "deformed hand",
    "mutated hand",
    "bad anatomy",
    "clipping artifacts",
  ]) {
    assert.ok(
      HAND_ANATOMY_SYSTEM_PROMPT.includes(keyword),
      `system prompt must contain: ${keyword}`
    );
  }
});

test("assembleAiImagePrompt is deterministic", () => {
  const user = "紫色渐变长甲";
  assert.equal(assembleAiImagePrompt(user), assembleAiImagePrompt(user));
});
