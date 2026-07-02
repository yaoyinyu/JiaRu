import assert from "node:assert/strict";
import test from "node:test";

import { extractTextureFromMaskDetailed } from "../src/lib/nail-texture-recognition/index.ts";

class FakeImageData implements ImageData {
  readonly colorSpace = "srgb";
  data: Uint8ClampedArray;
  width: number;
  height: number;

  constructor(data: Uint8ClampedArray, width: number, height: number) {
    this.data = data;
    this.width = width;
    this.height = height;
  }
}

function cloneImageData(imageData: FakeImageData): FakeImageData {
  return new FakeImageData(new Uint8ClampedArray(imageData.data), imageData.width, imageData.height);
}

class FakeCanvasRenderingContext2D {
  imageData: FakeImageData;
  private readonly canvasWidth: number;
  private readonly canvasHeight: number;

  constructor(canvasWidth: number, canvasHeight: number) {
    this.canvasWidth = canvasWidth;
    this.canvasHeight = canvasHeight;
    this.imageData = new FakeImageData(new Uint8ClampedArray(canvasWidth * canvasHeight * 4), canvasWidth, canvasHeight);
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
    return cloneImageData(this.imageData);
  }

  putImageData(imageData: FakeImageData, x: number, y: number) {
    void x;
    void y;
    this.imageData = cloneImageData(imageData);
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

test("extractTextureFromMaskDetailed returns transparent crop with feathered alpha and repaired highlight diagnostics", async () => {
  const previousOffscreenCanvas = globalThis.OffscreenCanvas;
  const previousCreateImageBitmap = globalThis.createImageBitmap;
  const previousImageData = globalThis.ImageData;

  Object.assign(globalThis, {
    OffscreenCanvas: FakeOffscreenCanvas,
    ImageData: FakeImageData,
    createImageBitmap: async (canvas: FakeOffscreenCanvas) => ({
      width: canvas.width,
      height: canvas.height,
      data: new Uint8ClampedArray(canvas.context.imageData.data),
    }),
  });

  try {
    const source = {
      width: 4,
      height: 4,
      data: new Uint8ClampedArray([
        20, 30, 40, 255,   30, 40, 50, 255,   40, 50, 60, 255,   50, 60, 70, 255,
        60, 20, 30, 255,  180, 40, 60, 255,  255, 255, 252, 255, 80, 40, 50, 255,
        70, 30, 40, 255,  180, 40, 60, 255,  180, 40, 60, 255,   90, 50, 60, 255,
        30, 20, 20, 255,   40, 30, 30, 255,   50, 40, 40, 255,   60, 50, 50, 255,
      ]),
    };

    const extracted = await extractTextureFromMaskDetailed(
      source as unknown as CanvasImageSource,
      source.width,
      source.height,
      {
        width: 4,
        height: 4,
        data: new Uint8Array([
          0, 0, 0, 0,
          0, 1, 1, 0,
          0, 1, 1, 0,
          0, 0, 0, 0,
        ]),
        originX: 0,
        originY: 0,
        scale: 1,
      },
      256,
      2
    );

    const texture = extracted.texture as unknown as {
      width: number;
      height: number;
      data: Uint8ClampedArray;
    };

    assert.equal(texture.width, 2);
    assert.equal(texture.height, 2);
    assert.equal(extracted.diagnostics.quality.ok, false);
    assert.ok(extracted.diagnostics.quality.warnings.includes("mask_foreground_too_small"));
    assert.equal(extracted.diagnostics.highlightRepair.highlightPixels, 1);
    assert.equal(extracted.diagnostics.highlightRepair.repairedPixels, 1);

    const alphaTopLeft = texture.data[3];
    const alphaBottomRight = texture.data[(texture.width * texture.height - 1) * 4 + 3];
    assert.ok(alphaTopLeft > 0 && alphaTopLeft < 255);
    assert.ok(alphaBottomRight > 0 && alphaBottomRight < 255);

    const repairedHighlightOffset = 1 * 4;
    assert.ok(texture.data[repairedHighlightOffset] < 255);
    assert.ok(texture.data[repairedHighlightOffset + 1] < 255);
    assert.ok(texture.data[repairedHighlightOffset + 2] < 255);
  } finally {
    Object.assign(globalThis, {
      OffscreenCanvas: previousOffscreenCanvas,
      createImageBitmap: previousCreateImageBitmap,
      ImageData: previousImageData,
    });
  }
});
