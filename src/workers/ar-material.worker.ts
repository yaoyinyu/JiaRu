import type { MaterialRequest, MaterialResult } from "@/lib/ar-material-jobs";
import { createArMaterialPainter } from "@/lib/ar-material-painter";

let painter: ReturnType<typeof createArMaterialPainter> | undefined;
const textures = new Map<number, ImageBitmap>();
const canvas = new OffscreenCanvas(1, 1);

self.onmessage = ({ data }: MessageEvent<MaterialRequest>) => {
  const { textureId, canvasWidth, canvasHeight, material, copy, grain, retire } = data;
  let bitmap: ImageBitmap | undefined;
  try {
    if (!painter) {
      if (!grain) throw new Error("missing material grain");
      painter = createArMaterialPainter(grain);
    }
    for (const id of retire) {
      textures.get(id)?.close();
      textures.delete(id);
    }
    if (copy) {
      textures.get(textureId)?.close();
      textures.set(textureId, copy);
    }
    const texture = textures.get(textureId);
    if (!texture) throw new Error("unregistered material texture");
    if (canvas.width !== canvasWidth) canvas.width = canvasWidth;
    if (canvas.height !== canvasHeight) canvas.height = canvasHeight;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("material canvas unavailable");
    painter.buildLayer(context, canvas, texture, material);
    bitmap = canvas.transferToImageBitmap();
    const response: MaterialResult = { bitmap };
    self.postMessage(response, { transfer: [bitmap] });
  } catch (error) {
    bitmap?.close();
    self.postMessage({ error: String(error) });
  }
};
