import { randomInt, randomUUID } from "node:crypto";

/**
 * 图形验证码（人机验证）——自研零依赖实现。
 * 在发送短信验证码之前要求用户输入图形验证码，防止机器人批量刷验证码
 * （文档 §5.1：验证码防轰炸 / §9.1：邮箱防垃圾注册频控同思路）。
 *
 * 说明：
 * - 答案只存服务端内存（5 分钟过期、一次性、错 5 次作废），响应只返回图片；
 * - 单实例内存 Map 对 MVP 足够；多实例/生产可替换为共享存储或专业人机验证服务
 *   （如腾讯云验证码、阿里云验证码），接口保持不变。
 */

const CAPTCHA_TTL_MS = 5 * 60 * 1000; // 5 分钟有效
const CAPTCHA_MAX_ATTEMPTS = 5; // 单次最多尝试 5 次
const CAPTCHA_LENGTH = 4;
// 去除易混淆字符（0/O/1/I/L）
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

function escapeXml(input: string): string {
  return input.replace(/[<>&'"]/g, (c) => {
    switch (c) {
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case "&":
        return "&amp;";
      case "'":
        return "&apos;";
      case '"':
        return "&quot;";
      default:
        return c;
    }
  });
}

/** 生成一张干扰线+噪点+旋转字符的 SVG 验证码图片 */
function renderSvg(answer: string): string {
  const width = 140;
  const height = 48;
  const chars = answer.split("");
  const positions = chars.map((_, i) => {
    const x = 18 + i * 28 + randomInt(-4, 5);
    const y = 32 + randomInt(-6, 7);
    const rotate = randomInt(-24, 25);
    const fontSize = randomInt(24, 31);
    return { x, y, rotate, fontSize, fill: `hsl(${randomInt(0, 360)} 55% 40%)` };
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

  const text = chars
    .map(
      (ch, i) =>
        `<text x="${positions[i].x}" y="${positions[i].y}" font-size="${positions[i].fontSize}" font-family="monospace, sans-serif" font-weight="bold" fill="${positions[i].fill}" transform="rotate(${positions[i].rotate} ${positions[i].x} ${positions[i].y})">${escapeXml(ch)}</text>`
    )
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="${width}" height="${height}" rx="8" fill="#fff6f8"/>${lines.join("")}${dots.join("")}${text}</svg>`;
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
