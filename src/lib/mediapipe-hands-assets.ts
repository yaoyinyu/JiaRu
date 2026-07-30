export const MEDIAPIPE_HANDS_ASSET_BASE_PATH = "/vendor/mediapipe/hands";

export function resolveMediaPipeHandsAsset(fileName: string): string {
  return `${MEDIAPIPE_HANDS_ASSET_BASE_PATH}/${fileName}`;
}
