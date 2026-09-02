import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_SEEDREAM_SIZE,
  SEEDREAM_LITE_SIZE_TABLE,
  SEEDREAM_PRO_SIZE_TABLE,
  isSeedreamModel,
  isSeedreamSize,
  resolveSeedreamDimension,
  seedreamSizesFor,
} from "../src/lib/seedream-image-size.ts";

/** 火山方舟文档规定的显式宽高总像素取值范围。 */
const PRO_PIXEL_RANGE: [number, number] = [921_600, 4_624_220];
const LITE_PIXEL_RANGE: [number, number] = [3_686_400, 16_777_216];

function pixelTotal(dimension: string): number {
  const [w, h] = dimension.split("x").map(Number);
  assert.ok(Number.isFinite(w) && Number.isFinite(h), `非法尺寸串: ${dimension}`);
  return w * h;
}

test("pro 档位白名单为 1K/1.5K/2K，lite 为 2K/3K/4K", () => {
  assert.deepEqual(seedreamSizesFor("pro"), ["1K", "1.5K", "2K"]);
  assert.deepEqual(seedreamSizesFor("lite"), ["2K", "3K", "4K"]);
  assert.equal(isSeedreamSize("pro", "3K"), false);
  assert.equal(isSeedreamSize("pro", "4K"), false);
  assert.equal(isSeedreamSize("lite", "1K"), false);
  assert.equal(isSeedreamSize("lite", "1.5K"), false);
  assert.equal(isSeedreamSize("pro", "2K"), true);
  assert.equal(isSeedreamSize("lite", "4K"), true);
  assert.equal(isSeedreamModel("pro"), true);
  assert.equal(isSeedreamModel("lite"), true);
  assert.equal(isSeedreamModel("agnes"), false);
  assert.equal(isSeedreamModel(undefined), false);
});

test("档位×比例换算值与火山方舟文档映射表一致（抽样）", () => {
  assert.equal(resolveSeedreamDimension("pro", "1K", "16:9"), "1424x800");
  assert.equal(resolveSeedreamDimension("pro", "1.5K", "9:16"), "1152x2048");
  assert.equal(resolveSeedreamDimension("pro", "2K", "9:16"), "1584x2816");
  assert.equal(resolveSeedreamDimension("pro", "2K", "21:9"), "3136x1344");
  assert.equal(resolveSeedreamDimension("lite", "2K", "16:9"), "2848x1600");
  assert.equal(resolveSeedreamDimension("lite", "3K", "3:2"), "3744x2496");
  assert.equal(resolveSeedreamDimension("lite", "4K", "21:9"), "6240x2656");
});

test("全部档位×比例组合的总像素落在文档规定区间内", () => {
  const ratios = Object.keys(SEEDREAM_PRO_SIZE_TABLE["1K"]);
  for (const [size, byRatio] of Object.entries(SEEDREAM_PRO_SIZE_TABLE)) {
    assert.equal(Object.keys(byRatio).length, ratios.length, `pro ${size} 比例不全`);
    for (const dimension of Object.values(byRatio)) {
      const total = pixelTotal(dimension);
      assert.ok(
        total >= PRO_PIXEL_RANGE[0] && total <= PRO_PIXEL_RANGE[1],
        `pro ${size} ${dimension} 总像素 ${total} 超出区间`
      );
    }
  }
  for (const [size, byRatio] of Object.entries(SEEDREAM_LITE_SIZE_TABLE)) {
    assert.equal(Object.keys(byRatio).length, ratios.length, `lite ${size} 比例不全`);
    for (const dimension of Object.values(byRatio)) {
      const total = pixelTotal(dimension);
      assert.ok(
        total >= LITE_PIXEL_RANGE[0] && total <= LITE_PIXEL_RANGE[1],
        `lite ${size} ${dimension} 总像素 ${total} 超出区间`
      );
    }
  }
});

test("非法模型/档位/比例组合返回 null 而非抛错", () => {
  assert.equal(resolveSeedreamDimension("pro", "3K", "1:1"), null);
  assert.equal(resolveSeedreamDimension("lite", "1K", "1:1"), null);
  assert.equal(resolveSeedreamDimension("pro", "2K", "5:3"), null);
  assert.equal(resolveSeedreamDimension("pro", "未知", "1:1"), null);
});

test("默认档位合法且可解析", () => {
  assert.equal(DEFAULT_SEEDREAM_SIZE.pro, "2K");
  assert.equal(DEFAULT_SEEDREAM_SIZE.lite, "2K");
  assert.ok(isSeedreamSize("pro", DEFAULT_SEEDREAM_SIZE.pro));
  assert.ok(isSeedreamSize("lite", DEFAULT_SEEDREAM_SIZE.lite));
});
