import assert from "node:assert/strict";
import test from "node:test";

import {
  extractNormalizedNailTexture,
  resolveMaskTextureRotation,
  WARNING_ORIENTATION_DISAGREEMENT,
  WARNING_TIP_DIRECTION_UNKNOWN,
} from "../src/lib/nail-texture-recognition/index.ts";
import type { NailMask } from "../src/lib/nail-texture-recognition/types.ts";

function normalizeAngleDelta(delta: number): number {
  let result = delta;
  while (result > Math.PI) result -= Math.PI * 2;
  while (result <= -Math.PI) result += Math.PI * 2;
  return result;
}

/** 构造倾斜椭圆甲面掩膜：tipAngle 为长轴指向甲尖的方向。 */
function buildTiltedNailMask(options: {
  width: number;
  height: number;
  center: { x: number; y: number };
  longRadius: number;
  shortRadius: number;
  tipAngle: number;
}): NailMask {
  const { width, height, center, longRadius, shortRadius, tipAngle } = options;
  const data = new Uint8Array(width * height);
  const tipX = Math.cos(tipAngle);
  const tipY = Math.sin(tipAngle);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const dx = x - center.x;
      const dy = y - center.y;
      const along = dx * tipX + dy * tipY;
      const across = -dx * tipY + dy * tipX;
      const ratio =
        (along / longRadius) * (along / longRadius) + (across / shortRadius) * (across / shortRadius);
      if (ratio <= 1) data[y * width + x] = 1;
    }
  }
  return { width, height, data, originX: 0, originY: 0, scale: 1 };
}

test("resolveMaskTextureRotation：斜甲面主轴解析为横轴半转角", () => {
  // 长轴指向 π/2+0.4（甲尖朝下偏右），横轴半转角应为 0.4
  const mask = buildTiltedNailMask({
    width: 80,
    height: 80,
    center: { x: 40, y: 40 },
    longRadius: 30,
    shortRadius: 12,
    tipAngle: Math.PI / 2 + 0.4,
  });
  const resolved = resolveMaskTextureRotation(mask, null);
  assert.equal(resolved.source, "mask");
  assert.ok(
    Math.abs(normalizeAngleDelta(resolved.rotation - 0.4)) < 0.06,
    `主轴角应为 0.4，实际 ${resolved.rotation}`
  );
  assert.ok(resolved.warnings.includes(WARNING_TIP_DIRECTION_UNKNOWN));
});

test("resolveMaskTextureRotation：referenceAngle 消歧甲尖 180° 方向", () => {
  const mask = buildTiltedNailMask({
    width: 80,
    height: 80,
    center: { x: 40, y: 40 },
    longRadius: 30,
    shortRadius: 12,
    tipAngle: Math.PI / 2 + 0.4,
  });

  // 参考横轴 = 甲尖方向 + π/2 = π + 0.4，蕴含的指尖方向与掩膜长轴一致 → 不翻转
  const aligned = resolveMaskTextureRotation(mask, Math.PI + 0.4);
  assert.equal(aligned.source, "mask+reference");
  assert.deepEqual(aligned.warnings, []);
  assert.ok(
    Math.abs(normalizeAngleDelta(aligned.rotation - (0.4 + Math.PI))) < 0.06,
    `全角应为 0.4+π，实际 ${aligned.rotation}`
  );

  // 参考横轴 = 0.4，蕴含的指尖方向与掩膜长轴相反 → 不补 π（全角保持 0.4）
  const flipped = resolveMaskTextureRotation(mask, 0.4);
  assert.ok(
    Math.abs(normalizeAngleDelta(flipped.rotation - 0.4)) < 0.06,
    `反向参考应保持 0.4，实际 ${flipped.rotation}`
  );
  assert.notEqual(
    Math.abs(normalizeAngleDelta(aligned.rotation - flipped.rotation)),
    0,
    "两种参考应给出相差 π 的全角"
  );
});

test("resolveMaskTextureRotation：近圆掩膜回退参考角，缺参考时告警", () => {
  const round: NailMask = {
    width: 12,
    height: 12,
    data: new Uint8Array(144).fill(1),
    originX: 0,
    originY: 0,
    scale: 1,
  };
  const fallback = resolveMaskTextureRotation(round, 0.7);
  assert.equal(fallback.source, "reference");
  assert.equal(fallback.rotation, 0.7);
  assert.deepEqual(fallback.warnings, []);

  const none = resolveMaskTextureRotation(round, null);
  assert.equal(none.source, "none");
  assert.equal(none.rotation, 0);
  assert.ok(none.warnings.includes(WARNING_TIP_DIRECTION_UNKNOWN));
});

test("resolveMaskTextureRotation：主轴与参考角分歧超 25° 时交叉检查告警", () => {
  const mask = buildTiltedNailMask({
    width: 80,
    height: 80,
    center: { x: 40, y: 40 },
    longRadius: 30,
    shortRadius: 12,
    tipAngle: Math.PI / 2 + 0.4,
  });
  const limit = (25 * Math.PI) / 180;

  const agree = resolveMaskTextureRotation(mask, 0.4 + limit - 0.05);
  assert.deepEqual(agree.warnings, []);

  const disagree = resolveMaskTextureRotation(mask, 0.4 + limit + 0.05);
  assert.ok(disagree.warnings.includes(WARNING_ORIENTATION_DISAGREEMENT));
});

class FakeImageData implements ImageData {
  readonly colorSpace = "srgb";
  data: Uint8ClampedArray<ArrayBuffer>;
  width: number;
  height: number;

  constructor(data: Uint8ClampedArray<ArrayBuffer>, width: number, height: number) {
    this.data = data;
    this.width = width;
    this.height = height;
  }
}

class FakeCanvasRenderingContext2D {
  imageData: FakeImageData;
  private readonly canvasWidth: number;
  private readonly canvasHeight: number;

  constructor(canvasWidth: number, canvasHeight: number) {
    this.canvasWidth = canvasWidth;
    this.canvasHeight = canvasHeight;
    this.imageData = new FakeImageData(
      new Uint8ClampedArray(canvasWidth * canvasHeight * 4),
      canvasWidth,
      canvasHeight
    );
  }

  drawImage(
    source: { width: number; height: number; data: Uint8ClampedArray },
    sx: number,
    sy: number,
    sw: number,
    sh: number,
    dx: number,
    dy: number,
    dw: number,
    dh: number
  ) {
    for (let y = 0; y < dh; y++) {
      const srcY = Math.min(source.height - 1, sy + Math.floor((y / dh) * sh));
      for (let x = 0; x < dw; x++) {
        const srcX = Math.min(source.width - 1, sx + Math.floor((x / dw) * sw));
        const sourceOffset = (srcY * source.width + srcX) * 4;
        const targetOffset = ((dy + y) * this.canvasWidth + (dx + x)) * 4;
        for (let channel = 0; channel < 4; channel++) {
          this.imageData.data[targetOffset + channel] = source.data[sourceOffset + channel] ?? 0;
        }
      }
    }
  }

  getImageData(x: number, y: number, w: number, h: number) {
    void x;
    void y;
    void w;
    void h;
    return new FakeImageData(
      new Uint8ClampedArray(this.imageData.data),
      this.imageData.width,
      this.imageData.height
    );
  }

  putImageData(imageData: FakeImageData, x: number, y: number) {
    void x;
    void y;
    this.imageData = new FakeImageData(
      new Uint8ClampedArray(imageData.data),
      imageData.width,
      imageData.height
    );
  }
}

class FakeOffscreenCanvas {
  readonly context: FakeCanvasRenderingContext2D;
  width: number;
  height: number;

  constructor(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.context = new FakeCanvasRenderingContext2D(width, height);
  }

  getContext(kind: string) {
    return kind === "2d" ? this.context : null;
  }
}

interface FakeBitmap {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

test("extractNormalizedNailTexture：斜甲面摆正为甲尖朝上并紧致裁剪", async () => {
  const previousOffscreenCanvas = globalThis.OffscreenCanvas;
  const previousCreateImageBitmap = globalThis.createImageBitmap;
  const previousImageData = globalThis.ImageData;

  Object.assign(globalThis, {
    OffscreenCanvas: FakeOffscreenCanvas,
    ImageData: FakeImageData,
    createImageBitmap: async (canvas: FakeOffscreenCanvas): Promise<FakeBitmap> => ({
      width: canvas.width,
      height: canvas.height,
      data: new Uint8ClampedArray(canvas.context.imageData.data),
    }),
  });

  try {
    const imageWidth = 80;
    const imageHeight = 80;
    const center = { x: 40, y: 40 };
    const longRadius = 30;
    const shortRadius = 12;
    const tipAngle = Math.PI / 2 + 0.4;

    const mask = buildTiltedNailMask({
      width: imageWidth,
      height: imageHeight,
      center,
      longRadius,
      shortRadius,
      tipAngle,
    });

    // 合成源图：甲面底色 (200,100,50)，甲尖 40% 区域标记色 (240,200,180)，其余背景 (30,30,30)
    const source = {
      width: imageWidth,
      height: imageHeight,
      data: new Uint8ClampedArray(imageWidth * imageHeight * 4),
    };
    const tipX = Math.cos(tipAngle);
    const tipY = Math.sin(tipAngle);
    for (let y = 0; y < imageHeight; y++) {
      for (let x = 0; x < imageWidth; x++) {
        const offset = (y * imageWidth + x) * 4;
        if (!mask.data[y * imageWidth + x]) {
          source.data[offset] = 30;
          source.data[offset + 1] = 30;
          source.data[offset + 2] = 30;
          source.data[offset + 3] = 255;
          continue;
        }
        const dx = x - center.x;
        const dy = y - center.y;
        const along = dx * tipX + dy * tipY;
        const isTip = along > longRadius * 0.55;
        source.data[offset] = isTip ? 240 : 200;
        source.data[offset + 1] = isTip ? 200 : 100;
        source.data[offset + 2] = isTip ? 180 : 50;
        source.data[offset + 3] = 255;
      }
    }

    // 参考横轴 = 甲尖方向 + π/2 = π + 0.4
    const result = await extractNormalizedNailTexture(
      source as unknown as CanvasImageSource,
      imageWidth,
      imageHeight,
      mask,
      { referenceAngle: Math.PI + 0.4, featherRadius: 2 }
    );

    const normalization = result.diagnostics.normalization;
    assert.ok(normalization, "归一化诊断应存在");
    assert.equal(normalization.source, "mask+reference");
    assert.deepEqual(normalization.warnings, []);
    assert.ok(
      Math.abs(normalizeAngleDelta(normalization.rotationRadians - (0.4 + Math.PI))) < 0.06,
      `旋转全角应为 0.4+π，实际 ${normalization.rotationRadians}`
    );

    const texture = result.texture as unknown as FakeBitmap;
    assert.ok(texture.height > texture.width, "摆正后长轴应竖直");

    // 紧致裁剪：尺寸接近 2×短轴/2×长轴 + 边距（羽化 2px + 裁剪 pad 2px + 双线性边缘）
    assert.ok(texture.width < shortRadius * 2 + 14, `宽 ${texture.width} 应接近 ${shortRadius * 2}`);
    assert.ok(texture.height > longRadius * 2 - 6, `高 ${texture.height} 应接近 ${longRadius * 2}`);

    // 甲尖方向：标记色像素应集中在输出上半部
    let markerPixels = 0;
    let markerCentroidY = 0;
    for (let y = 0; y < texture.height; y++) {
      for (let x = 0; x < texture.width; x++) {
        const offset = (y * texture.width + x) * 4;
        if ((texture.data[offset + 3] ?? 0) < 200) continue;
        const r = texture.data[offset] ?? 0;
        const g = texture.data[offset + 1] ?? 0;
        const b = texture.data[offset + 2] ?? 0;
        if (r > 220 && g > 180 && b > 150) {
          markerPixels += 1;
          markerCentroidY += y;
        }
      }
    }
    assert.ok(markerPixels >= 20, `甲尖标记像素应可见，实际 ${markerPixels}`);
    const centroid = markerCentroidY / markerPixels;
    assert.ok(
      centroid < texture.height * 0.55,
      `甲尖标记应位于上半部，质心 y=${centroid} / 高 ${texture.height}`
    );

    // 无旋转场景：竖直甲面 + 一致参考，输出保持竖直且诊断为 0 旋转
    const verticalMask = buildTiltedNailMask({
      width: imageWidth,
      height: imageHeight,
      center,
      longRadius,
      shortRadius,
      tipAngle: Math.PI / 2,
    });
    for (let y = 0; y < imageHeight; y++) {
      for (let x = 0; x < imageWidth; x++) {
        const offset = (y * imageWidth + x) * 4;
        source.data[offset] = verticalMask.data[y * imageWidth + x] ? 200 : 30;
        source.data[offset + 1] = verticalMask.data[y * imageWidth + x] ? 100 : 30;
        source.data[offset + 2] = verticalMask.data[y * imageWidth + x] ? 50 : 30;
        source.data[offset + 3] = 255;
      }
    }
    const upright = await extractNormalizedNailTexture(
      source as unknown as CanvasImageSource,
      imageWidth,
      imageHeight,
      verticalMask,
      { referenceAngle: Math.PI / 2 + Math.PI / 2, featherRadius: 2 }
    );
    assert.ok(upright.diagnostics.normalization);
    // 竖直甲面横轴为 0（半转角），reference 补全甲尖方向后全角可能为 0 或 π（均为横向摆正）
    const uprightRotation = upright.diagnostics.normalization.rotationRadians;
    const uprightDelta = normalizeAngleDelta(uprightRotation);
    assert.ok(
      Math.abs(uprightDelta) < 0.06 || Math.abs(Math.abs(uprightDelta) - Math.PI) < 0.06,
      `竖直甲面旋转应等价横向摆正（0 或 π），实际 ${uprightRotation}`
    );
    const uprightTexture = upright.texture as unknown as FakeBitmap;
    assert.ok(uprightTexture.height > uprightTexture.width);
  } finally {
    Object.assign(globalThis, {
      OffscreenCanvas: previousOffscreenCanvas,
      createImageBitmap: previousCreateImageBitmap,
      ImageData: previousImageData,
    });
  }
});
