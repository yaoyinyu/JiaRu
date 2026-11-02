import assert from "node:assert/strict";
import test from "node:test";

import {
  applyCropperKeyboardInput,
  createDefaultCropperSelection,
  type CropperRect,
} from "../src/lib/ar-cropper-keys.ts";

const CANVAS_W = 400;
const CANVAS_H = 300;

function rect(x: number, y: number, w: number, h: number): CropperRect {
  return { x, y, w, h };
}

test("createDefaultCropperSelection 生成画布内居中竖长选区", () => {
  const selection = createDefaultCropperSelection(CANVAS_W, CANVAS_H);
  const base = Math.min(CANVAS_W, CANVAS_H); // 300
  assert.equal(selection.h, Math.round(base * 0.62)); // 186
  assert.equal(selection.w, Math.round(Math.round(base * 0.62) * 0.62)); // 115
  // 居中
  assert.equal(selection.x, Math.round((CANVAS_W - selection.w) / 2));
  assert.equal(selection.y, Math.round((CANVAS_H - selection.h) / 2));
  // 界内
  assert.ok(selection.x >= 0 && selection.y >= 0);
  assert.ok(selection.x + selection.w <= CANVAS_W);
  assert.ok(selection.y + selection.h <= CANVAS_H);
});

test("createDefaultCropperSelection 小画布 / 非法尺寸不越界", () => {
  const tiny = createDefaultCropperSelection(3, 2);
  assert.ok(tiny.w >= 1 && tiny.h >= 1);
  assert.ok(tiny.x + tiny.w <= 3 && tiny.y + tiny.h <= 2);

  const degenerate = createDefaultCropperSelection(0, 0);
  assert.equal(degenerate.w, 1);
  assert.equal(degenerate.h, 1);
});

test("无选区时方向键 / Enter / 空格生成默认选区，其他键不动", () => {
  assert.deepEqual(
    applyCropperKeyboardInput(null, { key: "ArrowLeft", shiftKey: false }, CANVAS_W, CANVAS_H),
    createDefaultCropperSelection(CANVAS_W, CANVAS_H)
  );
  assert.deepEqual(
    applyCropperKeyboardInput(null, { key: "Enter", shiftKey: false }, CANVAS_W, CANVAS_H),
    createDefaultCropperSelection(CANVAS_W, CANVAS_H)
  );
  assert.deepEqual(
    applyCropperKeyboardInput(null, { key: " ", shiftKey: false }, CANVAS_W, CANVAS_H),
    createDefaultCropperSelection(CANVAS_W, CANVAS_H)
  );
  assert.equal(
    applyCropperKeyboardInput(null, { key: "a", shiftKey: false }, CANVAS_W, CANVAS_H),
    null
  );
});

test("有选区时方向键按 1px 移动并 clamp 在画布内", () => {
  const selection = rect(10, 20, 50, 60);
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowRight", shiftKey: false }, CANVAS_W, CANVAS_H),
    rect(11, 20, 50, 60)
  );
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowUp", shiftKey: false }, CANVAS_W, CANVAS_H),
    rect(10, 19, 50, 60)
  );
  // 移出边界时被 clamp
  assert.deepEqual(
    applyCropperKeyboardInput(rect(0, 0, 50, 60), { key: "ArrowLeft", shiftKey: false }, CANVAS_W, CANVAS_H),
    rect(0, 0, 50, 60)
  );
  assert.deepEqual(
    applyCropperKeyboardInput(
      rect(CANVAS_W - 50, 0, 50, 60),
      { key: "ArrowRight", shiftKey: false },
      CANVAS_W,
      CANVAS_H
    ),
    rect(CANVAS_W - 50, 0, 50, 60)
  );
});

test("Shift+方向键从右下角调整大小，最小 1px 且不越出画布", () => {
  const selection = rect(10, 20, 50, 60);
  // Shift+Right 加宽 10
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowRight", shiftKey: true }, CANVAS_W, CANVAS_H),
    rect(10, 20, 60, 60)
  );
  // Shift+Up 缩高 10
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowUp", shiftKey: true }, CANVAS_W, CANVAS_H),
    rect(10, 20, 50, 50)
  );
  // 缩到最小 1px
  assert.deepEqual(
    applyCropperKeyboardInput(rect(10, 20, 2, 2), { key: "ArrowLeft", shiftKey: true }, CANVAS_W, CANVAS_H),
    rect(10, 20, 1, 2)
  );
  // 放大到画布右缘为止
  assert.deepEqual(
    applyCropperKeyboardInput(
      rect(390, 20, 10, 60),
      { key: "ArrowRight", shiftKey: true },
      CANVAS_W,
      CANVAS_H
    ),
    rect(390, 20, 10, 60)
  );
});

test("Shift+方向键的尺寸步进为 10px，普通方向键移动步进为 1px", () => {
  const selection = rect(100, 100, 50, 60);
  // Shift+Down 调高 10
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowDown", shiftKey: true }, CANVAS_W, CANVAS_H),
    rect(100, 100, 50, 70)
  );
  // 普通方向键移动 1
  assert.deepEqual(
    applyCropperKeyboardInput(selection, { key: "ArrowDown", shiftKey: false }, CANVAS_W, CANVAS_H),
    rect(100, 101, 50, 60)
  );
});

test("非方向键不改变既有选区", () => {
  const selection = rect(10, 20, 50, 60);
  assert.equal(
    applyCropperKeyboardInput(selection, { key: "Tab", shiftKey: false }, CANVAS_W, CANVAS_H),
    null
  );
  assert.equal(
    applyCropperKeyboardInput(selection, { key: "Escape", shiftKey: false }, CANVAS_W, CANVAS_H),
    null
  );
});
