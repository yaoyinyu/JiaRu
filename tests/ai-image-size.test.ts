import assert from "node:assert/strict";
import test from "node:test";

import {
  AI_IMAGE_RATIOS,
  AI_IMAGE_SIZES,
  DEFAULT_AI_IMAGE_RATIO,
  DEFAULT_AI_IMAGE_SIZE,
  isAiImageRatio,
  isAiImageSize,
  pickReferenceRatio,
  resolveAiImageDimension,
} from "../src/lib/ai-image-size.ts";

test("尺寸档位与画面比例白名单符合 Agnes 技术文档", () => {
  assert.deepEqual(AI_IMAGE_SIZES, ["1K", "2K", "3K", "4K"]);
  assert.deepEqual(AI_IMAGE_RATIOS, [
    "1:1",
    "3:4",
    "4:3",
    "16:9",
    "9:16",
    "2:3",
    "3:2",
    "21:9",
  ]);
  assert.equal(DEFAULT_AI_IMAGE_SIZE, "1K");
  assert.equal(DEFAULT_AI_IMAGE_RATIO, "1:1");
});

test("输出尺寸参考表与 Agnes 技术文档逐项一致", () => {
  const expected: Record<string, string> = {
    "1K:1:1": "1024x1024",
    "1K:3:4": "864x1152",
    "1K:4:3": "1152x864",
    "1K:16:9": "1312x736",
    "1K:9:16": "736x1312",
    "1K:2:3": "832x1248",
    "1K:3:2": "1248x832",
    "1K:21:9": "1568x672",
    "2K:1:1": "2048x2048",
    "2K:3:4": "1728x2304",
    "2K:4:3": "2304x1728",
    "2K:16:9": "2624x1472",
    "2K:9:16": "1472x2624",
    "2K:2:3": "1664x2496",
    "2K:3:2": "2496x1664",
    "2K:21:9": "3136x1344",
    "3K:1:1": "3072x3072",
    "3K:3:4": "2592x3456",
    "3K:4:3": "3456x2592",
    "3K:16:9": "3936x2208",
    "3K:9:16": "2208x3936",
    "3K:2:3": "2496x3744",
    "3K:3:2": "3744x2496",
    "3K:21:9": "4704x2016",
    "4K:1:1": "4096x4096",
    "4K:3:4": "3456x4608",
    "4K:4:3": "4608x3456",
    "4K:16:9": "5248x2944",
    "4K:9:16": "2944x5248",
    "4K:2:3": "3328x4992",
    "4K:3:2": "4992x3328",
    "4K:21:9": "6272x2688",
  };

  for (const size of AI_IMAGE_SIZES) {
    for (const ratio of AI_IMAGE_RATIOS) {
      assert.equal(
        resolveAiImageDimension(size, ratio),
        expected[`${size}:${ratio}`],
        `${size} ${ratio}`,
      );
    }
  }
});

test("白名单校验函数", () => {
  assert.equal(isAiImageSize("2K"), true);
  assert.equal(isAiImageSize("5K"), false);
  assert.equal(isAiImageSize(1), false);
  assert.equal(isAiImageRatio("21:9"), true);
  assert.equal(isAiImageRatio("0.5"), false);
  assert.equal(isAiImageRatio(null), false);
});

test("参考图比例就近映射：全部 8 种标准比例自映射（评审 #9 修复）", () => {
  const selfImages: Array<[number, number, string]> = [
    [1024, 1024, "1:1"],
    [900, 1200, "3:4"],
    [1200, 900, "4:3"],
    [1920, 1080, "16:9"],
    [1080, 1920, "9:16"],
    [800, 1200, "2:3"],
    [1200, 800, "3:2"],
    [2100, 900, "21:9"],
  ];
  for (const [width, height, expected] of selfImages) {
    assert.equal(pickReferenceRatio(width, height), expected, `${width}x${height}`);
  }
});

test("参考图比例就近映射：评审复现例不再错判", () => {
  // 旧实现按固定区间切分：标准 3:4 被判为 2:3、标准 2:3 被判为 9:16
  assert.equal(pickReferenceRatio(3, 4), "3:4");
  assert.equal(pickReferenceRatio(2, 3), "2:3");
  assert.equal(pickReferenceRatio(4, 3), "4:3");
});

test("参考图比例就近映射：中间值按对数空间距离就近（横竖对称）", () => {
  // 0.9 在 log 空间离 1:1 更近（旧实现判 3:4）
  assert.equal(pickReferenceRatio(9, 10), "1:1");
  // 互为倒数输入 → 互为倒数候选
  assert.equal(pickReferenceRatio(4, 3), "4:3");
  assert.equal(pickReferenceRatio(3, 4), "3:4");
  assert.equal(pickReferenceRatio(7, 4), "16:9"); // 1.75 → 最近 16:9(1.778)
  assert.equal(pickReferenceRatio(4, 7), "9:16");
});

test("参考图比例就近映射：非法入参回退默认比例", () => {
  assert.equal(pickReferenceRatio(0, 100), DEFAULT_AI_IMAGE_RATIO);
  assert.equal(pickReferenceRatio(100, 0), DEFAULT_AI_IMAGE_RATIO);
  assert.equal(pickReferenceRatio(Number.NaN, 100), DEFAULT_AI_IMAGE_RATIO);
});
