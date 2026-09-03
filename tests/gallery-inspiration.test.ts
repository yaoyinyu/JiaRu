import assert from "node:assert/strict";
import test from "node:test";

import {
  closestPresetColor,
  parseHexColor,
  pickInspiredSwatch,
  pixelsFromRgbaBuffer,
  saturationOf,
  toHexColor,
} from "../src/lib/gallery-inspiration.ts";

function solidPixels(count: number, r: number, g: number, b: number) {
  return Array.from({ length: count }, () => ({ r, g, b }));
}

test("pickInspiredSwatch 对空采样返回 null", () => {
  assert.equal(pickInspiredSwatch([]), null);
});

test("pickInspiredSwatch 对纯色采样返回该色的平均 hex", () => {
  const swatch = pickInspiredSwatch(solidPixels(50, 255, 0, 0));
  assert.ok(swatch);
  assert.equal(swatch.hex, "#ff0000");
  assert.equal(swatch.ratio, 1);
  assert.equal(swatch.saturation, 1);
});

test("pickInspiredSwatch 在数量接近时偏向饱和度更高的簇", () => {
  // 300 个白色 + 200 个正红：白色频次高但饱和度 0，
  // 加权得分 (300×0.25) < (200×1.25)，应选红色。
  const pixels = [...solidPixels(300, 255, 255, 255), ...solidPixels(200, 255, 0, 0)];
  const swatch = pickInspiredSwatch(pixels);
  assert.ok(swatch);
  assert.equal(swatch.hex, "#ff0000");
});

test("pickInspiredSwatch 在大面积低饱和主色面前不被少量鲜艳噪点带偏", () => {
  // 900 个白色 + 100 个正红：白色频次优势足够大（225 > 125），应选白色。
  const pixels = [...solidPixels(900, 255, 255, 255), ...solidPixels(100, 255, 0, 0)];
  const swatch = pickInspiredSwatch(pixels);
  assert.ok(swatch);
  assert.equal(swatch.hex, "#ffffff");
});

test("pixelsFromRgbaBuffer 跳过低于阈值 alpha 的像素", () => {
  const data = new Uint8ClampedArray([
    255, 0, 0, 255, // 保留
    0, 255, 0, 0, // alpha 0，跳过
    0, 0, 255, 127, // alpha 127 < 128，跳过
    10, 20, 30, 128, // alpha 等于阈值，保留
  ]);
  const pixels = pixelsFromRgbaBuffer(data);
  assert.deepEqual(pixels, [
    { r: 255, g: 0, b: 0 },
    { r: 10, g: 20, b: 30 },
  ]);
});

test("toHexColor 截断越界通道并补零", () => {
  assert.equal(toHexColor(0, 15, 255), "#000fff");
  assert.equal(toHexColor(-5, 300, 12.4), "#00ff0c");
});

test("saturationOf 的边界行为", () => {
  assert.equal(saturationOf(0, 0, 0), 0);
  assert.equal(saturationOf(255, 255, 255), 0);
  assert.equal(saturationOf(255, 0, 0), 1);
});

test("parseHexColor 拒绝非法输入", () => {
  assert.equal(parseHexColor("red"), null);
  assert.equal(parseHexColor("#fff"), null);
  assert.equal(parseHexColor("rgba(0,0,0,1)"), null);
  const parsed = parseHexColor("#C4737D");
  assert.deepEqual(parsed, { r: 0xc4, g: 0x73, b: 0x7d });
});

test("closestPresetColor 精确命中同色预设", () => {
  assert.deepEqual(closestPresetColor("#C4737D"), { name: "豆沙红", color: "#C4737D" });
  assert.deepEqual(closestPresetColor("#2D2D2D"), { name: "黑色", color: "#2D2D2D" });
});

test("closestPresetColor 对近似色返回最近预设", () => {
  // 接近纯白 → 纯白
  assert.equal(closestPresetColor("#FDFDFD")?.name, "纯白色");
  // 接近裸粉 → 裸粉色（#F5D5CB 附近）
  assert.equal(closestPresetColor("#F2D2C8")?.name, "裸粉色");
});

test("closestPresetColor 拒绝非法 hex 且跳过无法解析的预设条目", () => {
  assert.equal(closestPresetColor("not-a-color"), null);
  // 白色不应匹配到「透明」的 rgba 条目（该条目会被跳过）
  assert.notEqual(closestPresetColor("#FFFFFF")?.name, "透明");
});
