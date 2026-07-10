export interface CoverVideoLayout {
  scale: number;
  scaledWidth: number;
  scaledHeight: number;
  offsetX: number;
  offsetY: number;
  cropX: number;
  cropY: number;
  cropLeft: number;
  cropRight: number;
  cropTop: number;
  cropBottom: number;
}

function requirePositiveDimension(value: number, name: string): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new RangeError(`${name} must be a positive finite number`);
  }
}

/** Uniformly scales and center-crops video like CSS `object-fit: cover`. */
export function calculateCoverVideoLayout(
  sourceWidth: number,
  sourceHeight: number,
  frameWidth: number,
  frameHeight: number,
): CoverVideoLayout {
  requirePositiveDimension(sourceWidth, "sourceWidth");
  requirePositiveDimension(sourceHeight, "sourceHeight");
  requirePositiveDimension(frameWidth, "frameWidth");
  requirePositiveDimension(frameHeight, "frameHeight");

  const scale = Math.max(frameWidth / sourceWidth, frameHeight / sourceHeight);
  const scaledWidth = sourceWidth * scale;
  const scaledHeight = sourceHeight * scale;
  const horizontalOverflow = Math.max(0, scaledWidth - frameWidth);
  const verticalOverflow = Math.max(0, scaledHeight - frameHeight);
  const cropLeft = horizontalOverflow / 2;
  const cropRight = horizontalOverflow - cropLeft;
  const cropTop = verticalOverflow / 2;
  const cropBottom = verticalOverflow - cropTop;

  return {
    scale,
    scaledWidth,
    scaledHeight,
    offsetX: -cropLeft,
    offsetY: -cropTop,
    cropX: cropLeft,
    cropY: cropTop,
    cropLeft,
    cropRight,
    cropTop,
    cropBottom,
  };
}

export function calculateViewportAspectRatio(width: number, height: number): number {
  requirePositiveDimension(width, "width");
  requirePositiveDimension(height, "height");
  return width / height;
}
