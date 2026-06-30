import type { ImagePixels } from "../nail-image-detection.ts";

export interface NailTexturePreprocessResult {
  inputSize: number;
  originalWidth: number;
  originalHeight: number;
  scaleX: number;
  scaleY: number;
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
  const tensorData = new Float32Array(3 * inputSize * inputSize);
  const scaleX = source.width / inputSize;
  const scaleY = source.height / inputSize;
  const channelArea = inputSize * inputSize;

  for (let y = 0; y < inputSize; y++) {
    const sourceY = Math.min(source.height - 1, Math.floor((y + 0.5) * scaleY));
    for (let x = 0; x < inputSize; x++) {
      const sourceX = Math.min(source.width - 1, Math.floor((x + 0.5) * scaleX));
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
    tensorData,
    tensorShape: [1, 3, inputSize, inputSize],
  };
}
