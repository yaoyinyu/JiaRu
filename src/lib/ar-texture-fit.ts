/** 摄影纹理按甲床宽度及甲根锚点映射；绘制时保留原有光影与透明轮廓。 */
export const AR_TEXTURE_FIT_VERSION = "cuticle-fit-v5";

/** 参考图保留局部光影，按相机甲面亮度温和调暗，避免暗环境中发白悬浮。 */
export function photographicLightGain(brightness: number): number {
  if (!Number.isFinite(brightness)) return 1;
  return Math.max(.65, Math.min(1, .6 + Math.max(0, brightness) * .65));
}

export interface TextureAlphaFrame {
  left: number;
  top: number;
  width: number;
  height: number;
  rootX: number;
  bodyWidth: number;
  shaped: boolean;
}

export function measureTextureAlphaFrame(
  rgba: Uint8ClampedArray, width: number, height: number,
): TextureAlphaFrame {
  if (width < 1 || height < 1 || rgba.length !== width * height * 4) throw new Error("texture_frame_shape_invalid");
  const rows = Array.from({ length: height }, () => ({ left: width, right: -1 }));
  let left = width, right = -1, top = height, bottom = -1, shaped = false;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (rgba[(y * width + x) * 4 + 3] < 250) shaped = true;
    // 忽略极低覆盖率尾巴，保留它们在后面的原位图绘制中。
    if (rgba[(y * width + x) * 4 + 3] < 32) continue;
    rows[y].left = Math.min(rows[y].left, x); rows[y].right = Math.max(rows[y].right, x);
    left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
  }
  if (right < left) return { left: 0, top: 0, width, height, rootX: width / 2, bodyWidth: width, shaped: false };
  const contentHeight = bottom - top + 1, contentWidth = right - left + 1;
  const bedRows = rows.slice(top + Math.floor(contentHeight * .5), top + Math.max(1, Math.ceil(contentHeight * .82))).filter(r => r.right >= r.left);
  const widths = bedRows.map(r => r.right - r.left + 1).sort((a, b) => a - b);
  const rootRows = rows.slice(top + Math.floor(contentHeight * .82), top + Math.max(1, Math.ceil(contentHeight * .95)))
    .filter(r => r.right >= r.left);
  const rootCenters = (rootRows.length ? rootRows : bedRows)
    .map(r => (r.left + r.right + 1) / 2).sort((a, b) => a - b);
  // 甲尖侧的蝴蝶/钻饰可超出甲床；用甲床行宽匹配，完整装饰仍随位图绘制。
  const bodyWidth = Math.max(1, widths[Math.floor(widths.length * .8)] ?? contentWidth);
  return { left, top, width: contentWidth, height: contentHeight,
    rootX: rootCenters[Math.floor(rootCenters.length / 2)] ?? (left + right + 1) / 2,
    bodyWidth, shaped };
}

/** 只在甲根交界留下短的覆盖率过渡，随显示尺寸钳制，保留甲尖与装饰。 */
export function cuticleBlendDistance(nailLength: number): number {
  return Math.min(2, Math.max(.5, nailLength * .025));
}

/** 单次连续采样，消除分条缩窄后留下的缝；原图边距保持在内容框之外。 */
export function textureDrawRect(frame: TextureAlphaFrame, bitmapWidth: number, bitmapHeight: number, nailWidth: number, nailLength: number) {
  const sx = nailWidth / frame.bodyWidth, sy = nailLength / frame.height;
  return { x: -frame.rootX * sx, y: -nailLength / 2 - frame.top * sy,
    width: bitmapWidth * sx, height: bitmapHeight * sy };
}

/** 纹理和材质共用的对称离屏边界，完整容纳原位图的透明尾边与外伸装饰。 */
export function textureLayerSize(rect: { x: number; y: number; width: number; height: number }, nailWidth: number, nailLength: number) {
  const pad = nailLength * .3 + 4;
  return {
    width: Math.ceil(2 * Math.max(nailWidth / 2 + pad, Math.abs(rect.x) + 2, Math.abs(rect.x + rect.width) + 2)),
    height: Math.ceil(2 * Math.max(nailLength / 2 + pad, Math.abs(rect.y) + 2, Math.abs(rect.y + rect.height) + 2)),
  };
}

export async function rotateNailTextureHalfTurn(texture: ImageBitmap): Promise<ImageBitmap> {
  const canvas = new OffscreenCanvas(texture.width, texture.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("texture_rotation_canvas_unavailable");
  ctx.translate(texture.width, texture.height);
  ctx.rotate(Math.PI);
  ctx.drawImage(texture, 0, 0);
  return createImageBitmap(canvas);
}
