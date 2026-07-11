import type { ImagePixels } from "../nail-image-detection.ts";

export interface NailTexturePreprocessResult {
  inputSize: number;
  originalWidth: number;
  originalHeight: number;
  scaleX: number;
  scaleY: number;
  resizeScale?: number;
  resizedWidth?: number;
  resizedHeight?: number;
  padLeft?: number;
  padTop?: number;
  tensorData: Float32Array;
  tensorShape: [1, 3, number, number];
}

function pixelOffset(width: number, x: number, y: number): number {
  return (y * width + x) * 4;
}

export function preprocessNailTextureImage(
  source: ImagePixels,
  inputSize: number
): NailTexturePreprocessResult {
  if (source.width < 1 || source.height < 1) {
    throw new Error("invalid_nail_texture_source_dimensions");
  }
  if (!Number.isInteger(inputSize) || inputSize < 1) {
    throw new Error("invalid_nail_texture_input_size");
  }

  const tensorData = new Float32Array(3 * inputSize * inputSize);
  const resizeScale = Math.min(inputSize / source.width, inputSize / source.height);
  const resizedWidth = Math.max(1, Math.min(inputSize, Math.round(source.width * resizeScale)));
  const resizedHeight = Math.max(1, Math.min(inputSize, Math.round(source.height * resizeScale)));
  const padLeft = Math.floor((inputSize - resizedWidth) / 2);
  const padTop = Math.floor((inputSize - resizedHeight) / 2);
  const scaleX = 1 / resizeScale;
  const scaleY = 1 / resizeScale;
  const channelArea = inputSize * inputSize;
  const paddingValue = 114 / 255;
  tensorData.fill(paddingValue);

  for (let resizedY = 0; resizedY < resizedHeight; resizedY++) {
    const y = padTop + resizedY;
    const sourceY = Math.min(
      source.height - 1,
      Math.floor((resizedY + 0.5) / resizeScale)
    );
    for (let resizedX = 0; resizedX < resizedWidth; resizedX++) {
      const x = padLeft + resizedX;
      const sourceX = Math.min(
        source.width - 1,
        Math.floor((resizedX + 0.5) / resizeScale)
      );
      const sourceIndex = pixelOffset(source.width, sourceX, sourceY);
      const targetIndex = y * inputSize + x;
      tensorData[targetIndex] = (Number(source.data[sourceIndex]) || 0) / 255;
      tensorData[channelArea + targetIndex] = (Number(source.data[sourceIndex + 1]) || 0) / 255;
      tensorData[channelArea * 2 + targetIndex] = (Number(source.data[sourceIndex + 2]) || 0) / 255;
    }
  }

  return {
    inputSize,
    originalWidth: source.width,
    originalHeight: source.height,
    scaleX,
    scaleY,
    resizeScale,
    resizedWidth,
    resizedHeight,
    padLeft,
    padTop,
    tensorData,
    tensorShape: [1, 3, inputSize, inputSize],
  };
}
