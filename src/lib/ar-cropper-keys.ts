/**
 * TextureCropper 键盘选区纯逻辑（frontend-interaction-redesign-plan §7.5：
 * 「TextureCropper 提供键盘选区」）。
 *
 * 边界：
 * - 纯几何计算，输入画布尺寸与当前选区，输出新选区；不触碰 DOM / Canvas / 位图；
 * - 方向键移动选区，Shift+方向键从右下角调整大小；无选区时按方向键 / Enter / 空格
 *   先生成一个居中默认选区（竖长甲面比例），再微调；
 * - 所有结果都 clamp 在画布内，最小尺寸 1px。
 */

export interface CropperRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CropperKeyInput {
  key: string;
  shiftKey: boolean;
}

const MOVE_STEP = 1;
const MOVE_STEP_LARGE = 10;
const MIN_SIZE = 1;

const ARROW_KEYS: ReadonlySet<string> = new Set([
  "ArrowLeft",
  "ArrowRight",
  "ArrowUp",
  "ArrowDown",
]);

function clampValue(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clampRect(rect: CropperRect, canvasW: number, canvasH: number): CropperRect {
  const x = clampValue(rect.x, 0, Math.max(0, canvasW - MIN_SIZE));
  const y = clampValue(rect.y, 0, Math.max(0, canvasH - MIN_SIZE));
  const w = clampValue(rect.w, MIN_SIZE, Math.max(MIN_SIZE, canvasW - x));
  const h = clampValue(rect.h, MIN_SIZE, Math.max(MIN_SIZE, canvasH - y));
  return { x, y, w, h };
}

/**
 * 无选区时的键盘默认选区：居中、短边 62% 长的竖长矩形（宽 = 长 × 0.62，
 * 与甲面竖长比例一致），并 clamp 到画布内。
 */
export function createDefaultCropperSelection(
  canvasW: number,
  canvasH: number
): CropperRect {
  if (canvasW <= 0 || canvasH <= 0) {
    return { x: 0, y: 0, w: MIN_SIZE, h: MIN_SIZE };
  }
  const base = Math.min(canvasW, canvasH);
  const h = clampValue(Math.round(base * 0.62), MIN_SIZE, canvasH);
  const w = clampValue(Math.round(h * 0.62), MIN_SIZE, canvasW);
  return clampRect(
    {
      x: Math.round((canvasW - w) / 2),
      y: Math.round((canvasH - h) / 2),
      w,
      h,
    },
    canvasW,
    canvasH
  );
}

/** 移动选区：位置 clamp 到画布内且不改变尺寸（贴边后停止，不缩水）。 */
function moveRect(
  rect: CropperRect,
  dx: number,
  dy: number,
  canvasW: number,
  canvasH: number
): CropperRect {
  const x = clampValue(rect.x + dx, 0, Math.max(0, canvasW - rect.w));
  const y = clampValue(rect.y + dy, 0, Math.max(0, canvasH - rect.h));
  return { ...rect, x, y };
}

/** 从右下角调整大小：只改 w/h，左上角固定，最小 1px 且不越出画布。 */
function resizeRect(
  rect: CropperRect,
  dw: number,
  dh: number,
  canvasW: number,
  canvasH: number
): CropperRect {
  const w = clampValue(rect.w + dw, MIN_SIZE, Math.max(MIN_SIZE, canvasW - rect.x));
  const h = clampValue(rect.h + dh, MIN_SIZE, Math.max(MIN_SIZE, canvasH - rect.y));
  return { ...rect, w, h };
}

/**
 * 键盘输入 → 新选区。
 * 返回 null 表示该输入不改变选区（调用方无需 setState）。
 * 无选区时：方向键 / Enter / 空格生成居中默认选区。
 * 有选区时：方向键移动（Shift 为 10px 步进，否则 1px）；
 *   Shift+左右调宽、Shift+上下调高（从右下角缩放）。
 */
export function applyCropperKeyboardInput(
  selection: CropperRect | null,
  input: CropperKeyInput,
  canvasW: number,
  canvasH: number
): CropperRect | null {
  if (!selection) {
    if (ARROW_KEYS.has(input.key) || input.key === "Enter" || input.key === " ") {
      return createDefaultCropperSelection(canvasW, canvasH);
    }
    return null;
  }

  const step = input.shiftKey ? MOVE_STEP_LARGE : MOVE_STEP;
  switch (input.key) {
    case "ArrowLeft":
      return input.shiftKey
        ? resizeRect(selection, -step, 0, canvasW, canvasH)
        : moveRect(selection, -step, 0, canvasW, canvasH);
    case "ArrowRight":
      return input.shiftKey
        ? resizeRect(selection, step, 0, canvasW, canvasH)
        : moveRect(selection, step, 0, canvasW, canvasH);
    case "ArrowUp":
      return input.shiftKey
        ? resizeRect(selection, 0, -step, canvasW, canvasH)
        : moveRect(selection, 0, -step, canvasW, canvasH);
    case "ArrowDown":
      return input.shiftKey
        ? resizeRect(selection, 0, step, canvasW, canvasH)
        : moveRect(selection, 0, step, canvasW, canvasH);
    default:
      return null;
  }
}
