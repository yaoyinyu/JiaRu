import { randomInt, randomUUID } from "node:crypto";

/**
 * 图形验证码（人机验证）——自研零依赖实现。
 * 在发送短信验证码之前要求用户输入图形验证码，防止机器人批量刷验证码
 * （文档 §5.1：验证码防轰炸 / §9.1：邮箱防垃圾注册频控同思路）。
 *
 * 说明：
 * - 答案只存服务端内存（5 分钟过期、一次性、错 5 次作废），响应只返回图片；
 * - 字符以 5×7 点阵笔画渲染为 <polyline> 路径（不再使用 <text> 元素），
 *   SVG 源码中不含明文答案，解析文本无法得到验证码（2026-09-05 评审 #7 修复）；
 * - 单实例内存 Map 对 MVP 足够；多实例/生产可替换为共享存储或专业人机验证服务
 *   （如腾讯云验证码、阿里云验证码），接口保持不变。
 */

const CAPTCHA_TTL_MS = 5 * 60 * 1000; // 5 分钟有效
const CAPTCHA_MAX_ATTEMPTS = 5; // 单次最多尝试 5 次
const CAPTCHA_LENGTH = 4;
// 去除易混淆字符（0/O/1/I/L/S）
const CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";

interface CaptchaRecord {
  answer: string;
  expiresAt: number;
  attempts: number;
}

const store = new Map<string, CaptchaRecord>();

function randomChar(): string {
  return CHARS[randomInt(0, CHARS.length)];
}

/**
 * 5×7 点阵笔画字形表（col: 0-4, row: 0-6）。
 * 每个字符由若干笔画（polyline 坐标序列）组成；渲染时整体缩放、加扰动并旋转。
 * 覆盖 CHARS 全部 30 个字符；SVG 中只有路径坐标，无文本节点。
 */
const GLYPH_STROKES: Record<string, number[][][]> = {
  "2": [[[0, 1], [1, 0], [3, 0], [4, 1], [4, 3], [2, 4], [1, 5], [0, 6], [4, 6]]],
  "3": [[[0, 0], [3, 0], [4, 1], [3, 2], [1, 3], [3, 4], [4, 5], [3, 6], [0, 6]]],
  "4": [[[3, 0], [0, 4], [4, 4]], [[3, 0], [3, 6]]],
  "5": [[[4, 0], [0, 0], [0, 3], [3, 3], [4, 4], [4, 5], [3, 6], [1, 6], [0, 5]]],
  "6": [[[3, 0], [1, 2], [0, 4], [0, 5], [1, 6], [3, 6], [4, 5], [4, 4], [3, 3], [0, 3]]],
  "7": [[[0, 0], [4, 0], [2, 4], [2, 6]]],
  "8": [
    [[1, 0], [3, 0], [4, 1], [4, 2], [3, 3], [1, 3], [0, 2], [0, 1], [1, 0]],
    [[1, 3], [3, 3], [4, 4], [4, 5], [3, 6], [1, 6], [0, 5], [0, 4], [1, 3]],
  ],
  "9": [[[3, 6], [4, 5], [4, 1], [3, 0], [1, 0], [0, 1], [0, 3], [1, 4], [3, 4], [4, 3]]],
  A: [[[0, 6], [0, 2], [2, 0], [4, 2], [4, 6]], [[0, 3], [4, 3]]],
  B: [
    [[0, 0], [0, 6]],
    [[0, 0], [3, 0], [4, 1], [4, 2], [3, 3], [0, 3], [3, 3], [4, 4], [4, 5], [3, 6], [0, 6]],
  ],
  C: [[[4, 1], [3, 0], [1, 0], [0, 1], [0, 5], [1, 6], [3, 6], [4, 5]]],
  D: [[[0, 0], [0, 6]], [[0, 0], [3, 0], [4, 2], [4, 4], [3, 6], [0, 6]]],
  E: [[[4, 0], [0, 0], [0, 6], [4, 6]], [[0, 3], [3, 3]]],
  F: [[[4, 0], [0, 0], [0, 6]], [[0, 3], [3, 3]]],
  G: [[[4, 1], [3, 0], [1, 0], [0, 1], [0, 5], [1, 6], [3, 6], [4, 5], [4, 4], [2, 4]]],
  H: [[[0, 0], [0, 6]], [[4, 0], [4, 6]], [[0, 3], [4, 3]]],
  J: [[[4, 0], [4, 5], [3, 6], [1, 6], [0, 5]]],
  K: [[[0, 0], [0, 6]], [[4, 0], [0, 3], [4, 6]]],
  M: [[[0, 6], [0, 0], [2, 2], [4, 0], [4, 6]]],
  N: [[[0, 6], [0, 0], [4, 6], [4, 0]]],
  P: [[[0, 6], [0, 0], [3, 0], [4, 1], [4, 2], [3, 3], [0, 3]]],
  Q: [[[0, 1], [1, 0], [3, 0], [4, 1], [4, 5], [3, 6], [1, 6], [0, 5], [0, 1]], [[3, 5], [4, 6]]],
  R: [[[0, 6], [0, 0], [3, 0], [4, 1], [4, 2], [3, 3], [0, 3]], [[1, 3], [4, 6]]],
  T: [[[0, 0], [4, 0]], [[2, 0], [2, 6]]],
  U: [[[0, 0], [0, 5], [1, 6], [3, 6], [4, 5], [4, 0]]],
  V: [[[0, 0], [2, 6], [4, 0]]],
  W: [[[0, 0], [1, 6], [2, 3], [3, 6], [4, 0]]],
  X: [[[0, 0], [4, 6]], [[4, 0], [0, 6]]],
  Y: [[[0, 0], [2, 3], [4, 0]], [[2, 3], [2, 6]]],
  Z: [[[0, 0], [4, 0], [0, 6], [4, 6]]],
};

function round1(value: number): string {
  return value.toFixed(1);
}

/** 把一行点阵坐标变换为画布坐标：缩放 + 扰动 + 绕字符中心旋转 */
function strokePoints(
  stroke: number[][],
  originX: number,
  originY: number,
  scaleX: number,
  scaleY: number,
  rotate: number
): string {
  const cx = originX + 2 * scaleX;
  const cy = originY + 3 * scaleY;
  const cos = Math.cos(rotate);
  const sin = Math.sin(rotate);
  return stroke
    .map(([col, row]) => {
      const x = originX + col * scaleX + randomInt(-2, 3);
      const y = originY + row * scaleY + randomInt(-2, 3);
      const dx = x - cx;
      const dy = y - cy;
      return `${round1(cx + dx * cos - dy * sin)},${round1(cy + dx * sin + dy * cos)}`;
    })
    .join(" ");
}

/** 生成一张干扰线+噪点+旋转笔画的 SVG 验证码图片（无 <text> 节点，不含明文答案） */
function renderSvg(answer: string): string {
  const width = 140;
  const height = 48;
  const scaleX = 5.4;
  const scaleY = 5.6;

  const glyphs = answer.split("").map((ch, i) => {
    const originX = 8 + i * 32;
    const originY = 6 + randomInt(-2, 3);
    const rotate = (randomInt(-24, 25) * Math.PI) / 180;
    const color = `hsl(${randomInt(0, 360)} 55% 38%)`;
    const strokeWidth = (randomInt(24, 34) / 10).toFixed(1);
    const strokes = (GLYPH_STROKES[ch] ?? GLYPH_STROKES["2"]).map((stroke) =>
      `<polyline points="${strokePoints(stroke, originX, originY, scaleX, scaleY, rotate)}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"/>`
    );
    return strokes.join("");
  });

  // 干扰线 3 条
  const lines = Array.from({ length: 3 }, () => {
    const x1 = randomInt(0, width);
    const y1 = randomInt(0, height);
    const x2 = randomInt(0, width);
    const y2 = randomInt(0, height);
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="hsl(${randomInt(0, 360)} 50% 60%)" stroke-width="${randomInt(1, 2)}" opacity="0.6"/>`;
  });

  // 噪点 24 个
  const dots = Array.from({ length: 24 }, () => {
    const cx = randomInt(0, width);
    const cy = randomInt(0, height);
    const r = randomInt(1, 2);
    return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="hsl(${randomInt(0, 360)} 50% 55%)" opacity="0.5"/>`;
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="${width}" height="${height}" rx="8" fill="#fff6f8"/>${lines.join("")}${dots.join("")}${glyphs.join("")}</svg>`;
}

/** 惰性清理过期记录，防止 Map 无限增长 */
function sweepExpired(): void {
  const now = Date.now();
  for (const [id, rec] of store) {
    if (now > rec.expiresAt) store.delete(id);
  }
}

/**
 * 创建图形验证码。
 * @returns id 前端回传用；svg 渲染给用户；answer 仅服务端内部使用（调用方不得返回给前端）
 */
export function createCaptcha(): { id: string; svg: string; answer: string } {
  sweepExpired();
  const id = randomUUID();
  const answer = Array.from({ length: CAPTCHA_LENGTH }, randomChar).join("");
  store.set(id, { answer, expiresAt: Date.now() + CAPTCHA_TTL_MS, attempts: 0 });
  return { id, svg: renderSvg(answer), answer };
}

/**
 * 校验图形验证码：正确且未过期 → true 并立即作废（一次性）；
 * 错误/过期/不存在 → false（错误会累计次数，超限作废）。
 */
export function verifyCaptcha(id: string, answer: string): boolean {
  if (!id || !answer) return false;
  const rec = store.get(id);
  if (!rec) return false;
  if (Date.now() > rec.expiresAt) {
    store.delete(id);
    return false;
  }
  if (rec.attempts >= CAPTCHA_MAX_ATTEMPTS) {
    store.delete(id);
    return false;
  }
  const ok = rec.answer.toUpperCase() === answer.trim().toUpperCase();
  if (ok) {
    store.delete(id);
  } else {
    rec.attempts += 1;
    if (rec.attempts >= CAPTCHA_MAX_ATTEMPTS) store.delete(id);
  }
  return ok;
}
