import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import test from "node:test";
import { recognizeNailTexturesWithFallback } from "../src/lib/nail-texture-recognition/index.ts";

const REFERENCE_IMAGE =
  "C:\\Users\\YaoYinyu\\.codex\\attachments\\e3e3f943-acb1-45f4-899a-a3492814fd2a\\image-1.jpg";
const GREEN_ANNOTATION =
  "C:\\Users\\YaoYinyu\\Desktop\\5188.jpg_wh860.png";

interface GreenComponent {
  cx: number;
  cy: number;
  area: number;
}

function greenComponents(
  pixels: Buffer,
  width: number,
  height: number
): GreenComponent[] {
  const mask = new Uint8Array(width * height);
  for (let i = 0; i < width * height; i++) {
    const r = pixels[i * 4];
    const g = pixels[i * 4 + 1];
    const b = pixels[i * 4 + 2];
    mask[i] = g > 180 && g > r * 1.5 && g > b * 1.5 ? 1 : 0;
  }

  const seen = new Uint8Array(mask.length);
  const queue = new Int32Array(mask.length);
  const components: GreenComponent[] = [];

  for (let start = 0; start < mask.length; start++) {
    if (!mask[start] || seen[start]) continue;
    let head = 0;
    let tail = 0;
    let area = 0;
    let sumX = 0;
    let sumY = 0;
    queue[tail++] = start;
    seen[start] = 1;

    while (head < tail) {
      const current = queue[head++];
      const x = current % width;
      const y = Math.floor(current / width);
      area++;
      sumX += x;
      sumY += y;

      for (let ny = y - 1; ny <= y + 1; ny++) {
        for (let nx = x - 1; nx <= x + 1; nx++) {
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          const next = ny * width + nx;
          if (!mask[next] || seen[next]) continue;
          seen[next] = 1;
          queue[tail++] = next;
        }
      }
    }

    if (area >= 200) {
      components.push({ cx: sumX / area, cy: sumY / area, area });
    }
  }

  return components.sort((a, b) => a.cx - b.cx);
}

test("reference nail-art image detection matches green annotation", async (t) => {
  if (!existsSync(REFERENCE_IMAGE) || !existsSync(GREEN_ANNOTATION)) {
    t.skip("local reference image or green annotation is not available");
    return;
  }

  const { default: sharp } = await import("sharp");
  const reference = await sharp(REFERENCE_IMAGE)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const annotation = await sharp(GREEN_ANNOTATION)
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });

  assert.equal(annotation.info.width, reference.info.width);
  assert.equal(annotation.info.height, reference.info.height);

  const truth = greenComponents(
    annotation.data,
    annotation.info.width,
    annotation.info.height
  );
  const result = recognizeNailTexturesWithFallback({
    width: reference.info.width,
    height: reference.info.height,
    data: reference.data,
  });
  const regions = result.candidates;

  assert.equal(truth.length, 4);
  assert.equal(regions.length, 4);
  assert.equal(result.backend, "fallback");

  const maxAllowedCenterError = 45;
  for (let i = 0; i < truth.length; i++) {
    const distance = Math.hypot(regions[i].cx - truth[i].cx, regions[i].cy - truth[i].cy);
    assert.ok(
      distance <= maxAllowedCenterError,
      `region ${i + 1} center error ${distance.toFixed(2)}px exceeded ${maxAllowedCenterError}px`
    );
  }
});
