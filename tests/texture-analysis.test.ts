import assert from "node:assert/strict";
import test from "node:test";

import {
  ANALYSIS_WARNING_LOW_OPACITY,
  analyzeNailTextureProfile,
  classifyNailShapeFromWidthProfile,
} from "../src/lib/nail-texture-recognition/index.ts";

// ── 纯函数：行宽剖面甲型分类 ──

function linearWidths(rows: number, baseWidth: number, tipWidth: number): number[] {
  const widths: number[] = [];
  for (let y = 0; y < rows; y += 1) {
    const t = rows === 1 ? 0 : y / (rows - 1);
    widths.push(Math.max(1, Math.round(tipWidth + (baseWidth - tipWidth) * t)));
  }
  return widths;
}

test("classifyNailShapeFromWidthProfile：四类甲型与失效兜底", () => {
  const round = classifyNailShapeFromWidthProfile(linearWidths(52, 40, 28));
  assert.equal(round.shape, "round");
  assert.ok(round.confidence > 0.5);

  const square = classifyNailShapeFromWidthProfile(linearWidths(60, 40, 38));
  assert.equal(square.shape, "square");
  assert.ok(square.tipRatio >= 0.9);

  const almond = classifyNailShapeFromWidthProfile(linearWidths(64, 40, 16));
  assert.equal(almond.shape, "almond");

  const stiletto = classifyNailShapeFromWidthProfile(linearWidths(80, 36, 4));
  assert.equal(stiletto.shape, "stiletto");
  assert.ok(stiletto.tipRatio < 0.25, `尖甲 tipRatio 应低于尖型阈值，实际 ${stiletto.tipRatio}`);

  const invalid = classifyNailShapeFromWidthProfile([10, 10, 10]);
  assert.equal(invalid.shape, "round");
  assert.equal(invalid.confidence, 0);
});

// ── 位图分析（FakeCanvas 基建，与 nail-texture-mask-orientation.test.ts 同模式）──

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

  constructor(canvasWidth: number, canvasHeight: number) {
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
        const targetOffset = ((dy + y) * this.imageData.width + (dx + x)) * 4;
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

function buildSolidTexture(options: {
  width: number;
  height: number;
  alphaAt: (x: number, y: number) => boolean;
  colorAt: (x: number, y: number) => [number, number, number];
}): FakeBitmap {
  const { width, height, alphaAt, colorAt } = options;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      if (!alphaAt(x, y)) {
        data[offset + 3] = 0;
        continue;
      }
      const [r, g, b] = colorAt(x, y);
      data[offset] = r;
      data[offset + 1] = g;
      data[offset + 2] = b;
      data[offset + 3] = 255;
    }
  }
  return { width, height, data };
}

/** 线性锥形甲面：尖部行半宽 tipHalf，根部行半宽 baseHalf */
function taperedAlpha(x: number, y: number, width: number, height: number, tipHalf: number, baseHalf: number) {
  const t = y / Math.max(1, height - 1);
  const halfWidth = tipHalf + (baseHalf - tipHalf) * t;
  return Math.abs(x - width / 2) <= halfWidth;
}

function centeredBandAlpha(halfWidth: number) {
  return (x: number, y: number, width: number, height: number) => {
    void y;
    void height;
    return Math.abs(x - width / 2) <= halfWidth;
  };
}

async function analyzeWithFakes(texture: FakeBitmap, options?: Parameters<typeof analyzeNailTextureProfile>[1]) {
  const previousOffscreenCanvas = globalThis.OffscreenCanvas;
  Object.assign(globalThis, { OffscreenCanvas: FakeOffscreenCanvas });
  try {
    return await analyzeNailTextureProfile(texture as unknown as ImageBitmap, options);
  } finally {
    Object.assign(globalThis, { OffscreenCanvas: previousOffscreenCanvas });
  }
}

test("analyzeNailTextureProfile：尖甲纯色纹理识别甲型/主色/低光泽", async () => {
  const texture = buildSolidTexture({
    width: 64,
    height: 96,
    alphaAt: (x, y) => taperedAlpha(x, y, 64, 96, 2, 20),
    colorAt: () => [180, 60, 90],
  });
  const profile = await analyzeWithFakes(texture);
  assert.equal(profile.shape, "stiletto");
  assert.equal(profile.pattern, "solid");
  assert.equal(profile.dominantColors[0]?.hex, "#b43c5a");
  assert.ok((profile.dominantColors[0]?.ratio ?? 0) > 0.95);
  assert.ok(profile.gloss < 0.05, `无高光像素时 gloss 应接近 0，实际 ${profile.gloss}`);
  assert.deepEqual(profile.warnings, []);
});

test("analyzeNailTextureProfile：法式（尖部独立色带）与渐变", async () => {
  const french = buildSolidTexture({
    width: 64,
    height: 64,
    alphaAt: (x, y) => centeredBandAlpha(20)(x, y, 64, 64),
    colorAt: (x, y) => (y < 16 ? [240, 240, 255] : [200, 100, 120]),
  });
  const frenchProfile = await analyzeWithFakes(french);
  assert.equal(frenchProfile.pattern, "french");

  const gradient = buildSolidTexture({
    width: 64,
    height: 64,
    alphaAt: (x, y) => centeredBandAlpha(20)(x, y, 64, 64),
    colorAt: (x, y) => {
      if (y < 16) return [220, 120, 150];
      if (y < 32) return [190, 100, 130];
      if (y < 48) return [160, 80, 110];
      return [130, 60, 90];
    },
  });
  const gradientProfile = await analyzeWithFakes(gradient);
  assert.equal(gradientProfile.pattern, "gradient");
});

test("analyzeNailTextureProfile：亮片纹理的高频亮斑判定", async () => {
  const width = 64;
  const height = 64;
  // 确定性 LCG 撒亮斑：约 3% 像素，单像素散点（连段长度 ≈1）
  let seed = 42;
  const nextRandom = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  const specks = new Set<string>();
  while (specks.size < 80) {
    const x = 12 + Math.floor(nextRandom() * 41);
    const y = Math.floor(nextRandom() * height);
    if (Math.abs(x - width / 2) <= 20) specks.add(`${x},${y}`);
  }

  const texture = buildSolidTexture({
    width,
    height,
    alphaAt: (x, y) => centeredBandAlpha(20)(x, y, width, height),
    colorAt: (x, y) => (specks.has(`${x},${y}`) ? [255, 230, 120] : [120, 80, 140]),
  });
  const profile = await analyzeWithFakes(texture);
  assert.equal(profile.pattern, "glitter", `期望 glitter，实际 ${profile.pattern}`);
});

test("analyzeNailTextureProfile：光泽度走高光比（提示优先、白色高自算）", async () => {
  const base = buildSolidTexture({
    width: 64,
    height: 64,
    alphaAt: (x, y) => centeredBandAlpha(20)(x, y, 64, 64),
    colorAt: () => [180, 60, 90],
  });

  const hinted = await analyzeWithFakes(base, { highlightRatioHint: 0.5 });
  assert.ok(Math.abs(hinted.gloss - 0.5) < 1e-9);

  const white = buildSolidTexture({
    width: 64,
    height: 64,
    alphaAt: () => true,
    colorAt: () => [255, 255, 255],
  });
  const glossy = await analyzeWithFakes(white);
  assert.ok(glossy.gloss > 0.9, `全白纹理 gloss 应接近 1，实际 ${glossy.gloss}`);
});

test("analyzeNailTextureProfile：低不透明度兜底并告警", async () => {
  const texture = buildSolidTexture({
    width: 32,
    height: 32,
    alphaAt: () => false,
    colorAt: () => [0, 0, 0],
  });
  const profile = await analyzeWithFakes(texture);
  assert.equal(profile.shape, "round");
  assert.equal(profile.shapeConfidence, 0);
  assert.equal(profile.pattern, "solid");
  assert.ok(profile.warnings.includes(ANALYSIS_WARNING_LOW_OPACITY));
});
