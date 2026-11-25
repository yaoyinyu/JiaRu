import { measureTextureAlphaFrame, textureDrawRect, cuticleBlendDistance, photographicLightGain, type TextureAlphaFrame } from "@/lib/ar-texture-fit";
import {
  AR_ROOT_COLOR_PROTECTION_ENABLED,
  adaptiveRootProtectionWeight,
  blendProtectedRootOutputs,
  buildSquareOpacityMask,
  buildTextureAreaIntegral,
  createExactAreaSampler,
  minimumPixelFootprint,
  renderProtectedRootColors,
  textureLayerToPhysicalMatrix,
  textureLayerToSourceMatrix,
  type TextureAreaIntegral,
} from "@/lib/ar-root-color-protection";
import { getNailShapeProfile, type NailShapeProfile } from "@/lib/ar-nail-shape";
import { createNailAffineTransform, type NailGeometry } from "@/lib/nail-geometry";
/** 甲面绘制共用 2D 上下文类型（主画布与离屏合成层） */
export type Nail2DContext = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

// 纹理 alpha 轮廓检测缓存（按位图实例缓存，检测结果与位图内容一一对应）
const textureFrameCache = new WeakMap<ImageBitmap, TextureAlphaFrame>();

export function getTextureFrame(tex: ImageBitmap): TextureAlphaFrame {
  const existing = textureFrameCache.get(tex);
  if (existing) return existing;
  const canvas = new OffscreenCanvas(tex.width, tex.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("texture_frame_canvas_unavailable");
  ctx.drawImage(tex, 0, 0);
  const frame = measureTextureAlphaFrame(ctx.getImageData(0, 0, tex.width, tex.height).data, tex.width, tex.height);
  textureFrameCache.set(tex, frame);
  canvas.width = canvas.height = 1;
  return frame;
}



interface RootColorTextureResources {
  integral: TextureAreaIntegral;
  guardTwo: OffscreenCanvas;
  guardOne: OffscreenCanvas;
}

/** 每张纹理只构建一次 V7 资源：RGB 行积分与 2px/1px 不透明保护层。 */
const rootColorTextureResourceCache = new WeakMap<ImageBitmap, RootColorTextureResources>();
const rootColorReadbackResourceCache = new WeakMap<ImageBitmap, RootColorTextureResources>();

function getRootColorTextureResources(tex: ImageBitmap, preferReadback: boolean): RootColorTextureResources | null {
  const cache = preferReadback ? rootColorReadbackResourceCache : rootColorTextureResourceCache;
  const cached = cache.get(tex);
  if (cached) return cached;
  if (tex.width <= 0 || tex.height <= 0) return null;
  const source = new OffscreenCanvas(tex.width, tex.height);
  const sourceCtx = source.getContext("2d", { willReadFrequently: true });
  if (!sourceCtx) return null;
  sourceCtx.drawImage(tex, 0, 0);
  const rgba = sourceCtx.getImageData(0, 0, tex.width, tex.height).data;
  const rgb = new Uint8Array(tex.width * tex.height * 3);
  for (let i = 0, j = 0; i < rgba.length; i += 4) {
    rgb[j++] = rgba[i];
    rgb[j++] = rgba[i + 1];
    rgb[j++] = rgba[i + 2];
  }
  const frame = getTextureFrame(tex);
  let integral: TextureAreaIntegral;
  try {
    integral = buildTextureAreaIntegral(rgb, tex.width, tex.height, {
      minX: frame.left,
      minY: frame.top,
      maxX: frame.left + frame.width - 1,
      maxY: frame.top + frame.height - 1,
    });
  } catch {
    return null;
  }
  const guardTwoData = buildSquareOpacityMask(rgba, tex.width, tex.height, 2);
  const guardOneData = buildSquareOpacityMask(rgba, tex.width, tex.height, 1);
  const options = preferReadback ? { willReadFrequently: true } : undefined;
  const guardTwo = new OffscreenCanvas(tex.width, tex.height);
  const guardTwoCtx = guardTwo.getContext("2d", options);
  const guardOne = new OffscreenCanvas(tex.width, tex.height);
  const guardOneCtx = guardOne.getContext("2d", options);
  if (!guardTwoCtx || !guardOneCtx) return null;
  const guardTwoImage = guardTwoCtx.createImageData(tex.width, tex.height);
  guardTwoImage.data.set(guardTwoData);
  guardTwoCtx.putImageData(guardTwoImage, 0, 0);
  const guardOneImage = guardOneCtx.createImageData(tex.width, tex.height);
  guardOneImage.data.set(guardOneData);
  guardOneCtx.putImageData(guardOneImage, 0, 0);
  const resources: RootColorTextureResources = { integral, guardTwo, guardOne };
  cache.set(tex, resources);
  return resources;
}


export interface ArMaterialParams {
  width: number;
  length: number;
  brightness: number;
  finger: number;
  gloss: number;
  shape: NailShapeProfile;
  geometry: NailGeometry;
  pixelRatio: number;
  preferReadback: boolean;
}

export function createArMaterialPainter(sharedGrain?: ImageData) {
  let workCanvas: OffscreenCanvas | null = null;
  let grain: OffscreenCanvas | null = null;
  let fallbackWarned = false;
  let grainData = sharedGrain;

  function getGrainData() {
    if (grainData) return grainData;
    const data = new ImageData(64, 128);
    for (let i = 0; i < data.data.length; i += 4) {
      const noise = 128 + (Math.random() - 0.5) * 30;
      data.data[i] = noise;
      data.data[i + 1] = noise;
      data.data[i + 2] = noise;
      data.data[i + 3] = 18;
    }
    grainData = data;
    return grainData;
  }
  /** 在离屏层 alpha 上融合甲根交界；调用方负责纹理已先绘制。 */
  function applyRootColorFade(
    ctx: OffscreenCanvasRenderingContext2D,
    canvas: OffscreenCanvas,
    renderLength: number,
  ) {
    ctx.globalCompositeOperation = "destination-in";
    const rootY = renderLength / 2;
    const rootBlend = ctx.createLinearGradient(0, rootY - cuticleBlendDistance(renderLength), 0, rootY);
    rootBlend.addColorStop(0, "rgba(0,0,0,1)");
    rootBlend.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = rootBlend;
    ctx.fillRect(-canvas.width / 2, -canvas.height / 2, canvas.width, canvas.height);
    ctx.globalCompositeOperation = "source-over";
  }

  function readRootColorGuardData(
    guard: OffscreenCanvas,
    width: number,
    height: number,
    rect: { x: number; y: number; width: number; height: number },
    renderLength: number,
  ): ImageData | null {
    let canvas = workCanvas;
    if (!canvas || canvas.width !== width || canvas.height !== height) {
      canvas = new OffscreenCanvas(width, height);
      workCanvas = canvas;
    }
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.drawImage(guard, rect.x, rect.y, rect.width, rect.height);
    applyRootColorFade(ctx, canvas, renderLength);
    return ctx.getImageData(0, 0, canvas.width, canvas.height);
  }

  /**
   * V7 resampleTwo 生产路径：先保留现行摄影层作为基线，
   * 再在根带内按精确面积采样替换 2px/1px 保护域 RGB，物理覆盖不足时偏向 2px。
   */
  function applyQualityFirstRootProtection(
    lctx: OffscreenCanvasRenderingContext2D,
    layerCanvas: OffscreenCanvas,
    tex: ImageBitmap,
    rect: { x: number; y: number; width: number; height: number },
    renderGeometry: NailGeometry,
    renderLength: number,
    preferReadback: boolean,
    pixelRatio: number,
  ): boolean {
    if (!AR_ROOT_COLOR_PROTECTION_ENABLED) return false;
    const resources = getRootColorTextureResources(tex, preferReadback);
    const sourceMatrix = textureLayerToSourceMatrix(
      rect, tex.width, tex.height, layerCanvas.width, layerCanvas.height,
    );
    if (!resources || !sourceMatrix) return false;
    const physicalMatrix = textureLayerToPhysicalMatrix(
      createNailAffineTransform(renderGeometry),
      layerCanvas.width,
      layerCanvas.height,
      pixelRatio,
    );
    if (!physicalMatrix) return false;
    const footprint = minimumPixelFootprint(physicalMatrix);
    if (!footprint) return false;
    const weight = adaptiveRootProtectionWeight(footprint);

    const baseData = lctx.getImageData(0, 0, layerCanvas.width, layerCanvas.height);
    const directTwo = readRootColorGuardData(
      resources.guardTwo, layerCanvas.width, layerCanvas.height, rect, renderLength,
    );
    if (!directTwo) return false;
    const sampler = createExactAreaSampler(resources.integral, sourceMatrix);
    const twoData = renderProtectedRootColors(baseData, directTwo, renderLength, sampler);

    let finalData: Uint8ClampedArray;
    if (weight <= 0) {
      finalData = twoData;
    } else {
      const directOne = readRootColorGuardData(
        resources.guardOne, layerCanvas.width, layerCanvas.height, rect, renderLength,
      );
      if (!directOne) return false;
      const oneData = renderProtectedRootColors(baseData, directOne, renderLength, sampler);
      finalData = weight >= 1
        ? oneData
        : blendProtectedRootOutputs(
          { width: layerCanvas.width, height: layerCanvas.height, data: twoData },
          { width: layerCanvas.width, height: layerCanvas.height, data: oneData },
          weight,
        );
    }
    const finalImage = lctx.createImageData(layerCanvas.width, layerCanvas.height);
    finalImage.data.set(finalData);
    lctx.putImageData(finalImage, 0, 0);
    return true;
  }

  /**
   * 绘制指甲形状（贝塞尔路径 —— 比椭圆更贴近真实指甲轮廓）
   * 每根手指使用不同的形状参数：
   *   拇指 — 宽短平尖 / 食指中指 — 标准椭圆 / 无名指 — 圆润 / 小指 — 尖窄
   */
  function drawNailShape(
    ctx: Nail2DContext,
    nl: number,
    nw: number,
    fingerIdx: number = 2,  // 默认中指
    profile: NailShapeProfile = getNailShapeProfile(undefined, fingerIdx)
  ) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;
    const tipNarrow = profile.tipNarrow * nw;
    const cpLen = hl * profile.sideCurve;
    const rootBulge = hl * profile.rootBulge;

    ctx.beginPath();
    ctx.moveTo(hw - tipNarrow, -hl);
    ctx.quadraticCurveTo(0, -hl - hl * profile.tipArch, -(hw - tipNarrow), -hl);
    ctx.bezierCurveTo(
      -(hw + cpLen * profile.sideFlare), -hl * 0.6,
      -(hw + cpLen * profile.sideFlare), hl * 0.3,
      -hw, hl + rootBulge
    );
    ctx.quadraticCurveTo(0, hl + rootBulge + hl * 0.06, hw, hl + rootBulge);
    ctx.bezierCurveTo(
      hw + cpLen * profile.sideFlare, hl * 0.3,
      hw + cpLen * profile.sideFlare, -hl * 0.6,
      hw - tipNarrow, -hl
    );
    ctx.closePath();
  }

  /** 摄影纹理单次采样：内容甲根与甲床宽度对齐，保留来源图已有的曲面光影。 */
  function drawPhotoTexture(ctx: Nail2DContext, tex: ImageBitmap, nl: number, nw: number) {
    const rect = textureDrawRect(getTextureFrame(tex), tex.width, tex.height, nw, nl);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(tex, rect.x, rect.y, rect.width, rect.height);
  }

  /**
   * 绘制材质细节层（在纹理之上叠加）
   *
   * 包含：
   *   1. 菲涅尔反射 — 边缘更亮（模拟指甲曲面边缘的高反射）
   *   2. 颗粒纹理 — 微小噪点模拟指甲表面微观纹理
   *   3. 边缘暗角 — 指甲根部稍暗
   */
  function drawMaterialDetails(
    ctx: Nail2DContext,
    nl: number,
    nw: number,
    envBrightness: number,
    fingerIdx: number = 2,
    glossFactor: number = 1,
    profile: NailShapeProfile = getNailShapeProfile(undefined, fingerIdx)
  ) {
    const hw = nw * 0.5;
    const hl = nl * 0.5;

    // ── 1. 菲涅尔反射（边缘高亮）──
    // 沿宽度方向的渐变：中心暗，边缘亮
    const fresnelGrad = ctx.createLinearGradient(-hw, 0, hw, 0);
    fresnelGrad.addColorStop(0, "rgba(255,255,255,0.28)");
    fresnelGrad.addColorStop(0.25, "rgba(255,255,255,0.05)");
    fresnelGrad.addColorStop(0.5, "rgba(255,255,255,0.0)");
    fresnelGrad.addColorStop(0.75, "rgba(255,255,255,0.05)");
    fresnelGrad.addColorStop(1, "rgba(255,255,255,0.28)");

    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx, profile);
    ctx.clip();
    ctx.fillStyle = fresnelGrad;
    ctx.globalAlpha = 0.6 * envBrightness * glossFactor;
    ctx.fillRect(-hw, -hl, nw, nl);
    ctx.restore();

    // ── 2. 颗粒纹理（微观表面）──
    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx, profile);
    ctx.clip();

    let grainCanvas = grain;
    if (!grainCanvas) {
      grainCanvas = new OffscreenCanvas(64, 128);
      grainCanvas.getContext("2d")?.putImageData(getGrainData(), 0, 0);
      grain = grainCanvas;
    }
    if (grainCanvas) {
      ctx.globalAlpha = 0.35 * Math.min(1, glossFactor);
      ctx.drawImage(grainCanvas, -hw, -hl, nw, nl);
    }
    ctx.restore();

    // ── 3. 根部暗角 ──
    const vignetteGrad = ctx.createLinearGradient(0, -hl, 0, hl);
    vignetteGrad.addColorStop(0, "rgba(0,0,0,0)");
    vignetteGrad.addColorStop(0.6, "rgba(0,0,0,0)");
    vignetteGrad.addColorStop(1, "rgba(0,0,0,0.25)");

    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx, profile);
    ctx.clip();
    ctx.fillStyle = vignetteGrad;
    ctx.globalAlpha = Math.min(1, glossFactor);
    ctx.fillRect(-hw, -hl, nw, nl);
    ctx.restore();
  }

  /**
   * 绘制高光（镜面反射）
   *
   * 三层高光系统：
   *   1. 主高光 — 纵向椭圆，模拟光源在指甲中央的镜面反射
   *   2. 指尖高光 — 指尖边缘的细亮线（自由缘反光）
   *   3. 根部微光 — 甲上皮附近的柔和散射
   */
  function drawSpecularHighlight(
    ctx: Nail2DContext,
    nl: number,
    nw: number,
    envBrightness: number,
    fingerIdx: number = 2,
    glossFactor: number = 1,
    profile: NailShapeProfile = getNailShapeProfile(undefined, fingerIdx)
  ) {
    const hl = nl * 0.5;
    const hw = nw * 0.5;

    ctx.save();
    drawNailShape(ctx, nl, nw, fingerIdx, profile);
    ctx.clip();

    // ── 主高光（镜面反射条）──
    const specAlpha = (0.18 + envBrightness * 0.22) * glossFactor;
    ctx.globalAlpha = specAlpha;

    // 纵向渐变高光（上亮下暗）
    const specGrad = ctx.createLinearGradient(0, -hl, 0, hl);
    specGrad.addColorStop(0, "rgba(255,255,255,0.9)");
    specGrad.addColorStop(0.3, "rgba(255,255,255,0.6)");
    specGrad.addColorStop(0.7, "rgba(255,255,255,0.15)");
    specGrad.addColorStop(1, "rgba(255,255,255,0.0)");

    ctx.fillStyle = specGrad;
    ctx.beginPath();
    ctx.ellipse(-hw * 0.25, -hl * 0.05, hl * 0.38, hw * 0.12, 0, 0, Math.PI * 2);
    ctx.fill();

    // ── 指尖高光（自由缘细亮线）──
    ctx.globalAlpha = (0.12 + envBrightness * 0.1) * glossFactor;
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.ellipse(0, -hl + hl * 0.06, hl * 0.15, hw * 0.55, 0, 0, Math.PI * 2);
    ctx.fill();

    // ── 根部微光 ──
    ctx.globalAlpha = (0.06 + envBrightness * 0.04) * glossFactor;
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.ellipse(0, hl * 0.6, hl * 0.12, hw * 0.4, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }


  function buildLayer(lctx: OffscreenCanvasRenderingContext2D, layerCanvas: OffscreenCanvas,
    tex: ImageBitmap, params: ArMaterialParams) {
    const { width: nw, length: renderLength, brightness, finger: f, gloss: glossFactor,
      shape: shapeProfile, geometry: renderGeometry, pixelRatio, preferReadback } = params;
    const frame = getTextureFrame(tex);
    lctx.setTransform(1, 0, 0, 1, 0, 0);
    lctx.globalAlpha = 1;
    lctx.globalCompositeOperation = "source-over";
    lctx.clearRect(0, 0, layerCanvas.width, layerCanvas.height);
    lctx.save();
    lctx.translate(layerCanvas.width * 0.5, layerCanvas.height * 0.5);
    drawPhotoTexture(lctx, tex, renderLength, nw);
    // 在离屏纹理自身 alpha 上融合甲根交界，避免整枚纹理降低透明度。
    applyRootColorFade(lctx, layerCanvas, renderLength);
    // V7 甲根颜色保护：精确面积采样 + 1–2px 内缩域平滑替换；
    // 任一步失败保持上方现行摄影层，仅记录一次回退提示。
    try {
      applyQualityFirstRootProtection(
        lctx,
        layerCanvas,
        tex,
        textureDrawRect(frame, tex.width, tex.height, nw, renderLength),
        renderGeometry,
        renderLength,
        preferReadback,
        pixelRatio,
      );
    } catch (error) {
      if (!fallbackWarned) {
        fallbackWarned = true;
        console.warn("[AR] 甲根颜色保护回退到现行采样", error);
      }
    }
    lctx.globalCompositeOperation = "source-atop";
    lctx.fillStyle = `rgba(0,0,0,${1 - photographicLightGain(brightness)})`;
    lctx.fillRect(-layerCanvas.width / 2, -layerCanvas.height / 2, layerCanvas.width, layerCanvas.height);
    drawMaterialDetails(lctx, renderLength, nw, brightness, f, glossFactor * .12, shapeProfile);
    drawSpecularHighlight(lctx, renderLength, nw, brightness, f, glossFactor * .12, shapeProfile);
    lctx.restore();
  }

  return { buildLayer, drawNailShape, drawPhotoTexture, drawMaterialDetails, drawSpecularHighlight, getGrainData };
}
