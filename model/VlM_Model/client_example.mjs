/**
 * 从 Node 调用本地抠图服务的参考实现。
 *
 * 用法：
 *   node client_example.mjs <图片路径> [文本提示]
 *
 * 这就是 /api/nail-matte 转发层要写的东西：把浏览器传来的 data URI 与候选框
 * 原样转给 127.0.0.1:8008，再把 alpha 原样转回去。不要在 Node 里解码图片。
 */

import { readFile } from "node:fs/promises";
import { extname } from "node:path";

const BASE = process.env.VLM_MATTE_URL ?? "http://127.0.0.1:8008";
const TOKEN = process.env.VLM_MATTE_TOKEN ?? "";

const MIME = { ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp" };

function headers() {
  const base = { "Content-Type": "application/json" };
  return TOKEN ? { ...base, Authorization: `Bearer ${TOKEN}` } : base;
}

/** 健康检查：进程在、模型已加载、当前是否忙。 */
export async function health() {
  const res = await fetch(`${BASE}/health`);
  return await res.json();
}

/**
 * 请求抠图。
 *
 * @param {object} input
 * @param {string} input.image  data URI（浏览器端 canvas 重编码后的结果）
 * @param {string} [input.query] 文本提示，默认「指甲」
 * @param {number[][]} [input.boxes] 参考框，配合 task="visual_prompt"
 * @param {"matting"|"segmentation"|"visual_prompt"} [input.task]
 * @returns {Promise<{ok:boolean, instances:Array<{index:number, box?:number[], alphaPng:string, area:number, bbox:number[]}>}>}
 */
export async function matte({ image, query = "指甲", boxes, task = "matting" }) {
  const res = await fetch(`${BASE}/matte`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ image, query, boxes, task }),
  });

  // 忙的时候服务端返回 503：调用方应回退到浏览器本地结果，而不是重试排队。
  if (res.status === 503) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, busy: true, error: body.error ?? "服务忙碌" };
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return { ok: false, error: body.error ?? `HTTP ${res.status}` };
  }
  return await res.json();
}

/**
 * 把服务端返回的实例对回浏览器端的候选。
 *
 * 关键约束：服务端可能多返或少返实例，而前端的指位是按「候选数量 + 顺序」推出来的
 * （见 src/lib/nail-texture-recognition/finger-assignment.ts）。因此**不能按 index 直接对齐**，
 * 必须按框的 IoU 匹配；匹配不到就保留本地掩膜，绝不改变候选数量。
 */
export function matchByIou(candidates, instances, minIou = 0.3) {
  const iou = (a, b) => {
    const x1 = Math.max(a[0], b[0]);
    const y1 = Math.max(a[1], b[1]);
    const x2 = Math.min(a[2], b[2]);
    const y2 = Math.min(a[3], b[3]);
    const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1);
    const areaA = Math.max(0, a[2] - a[0]) * Math.max(0, a[3] - a[1]);
    const areaB = Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
    const union = areaA + areaB - inter;
    return union <= 0 ? 0 : inter / union;
  };

  const used = new Set();
  return candidates.map((candidate) => {
    let best = null;
    let bestScore = minIou;
    instances.forEach((item, i) => {
      if (used.has(i) || !item.box) return;
      const score = iou(candidate.box, item.box);
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    });
    if (best === null) return { candidate, refined: null };
    used.add(best);
    return { candidate, refined: { alphaPng: instances[best].alphaPng, iou: bestScore } };
  });
}

// ── 命令行自测 ──
import { pathToFileURL } from "node:url";

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const imagePath = process.argv[2];
  const query = process.argv[3] ?? "指甲";
  if (!imagePath) {
    console.error("用法：node client_example.mjs <图片路径> [提示词]");
    process.exit(2);
  }
  const ext = extname(imagePath).toLowerCase();
  const bytes = await readFile(imagePath);
  const image = `data:${MIME[ext] ?? "image/jpeg"};base64,${bytes.toString("base64")}`;

  console.log("health:", await health());
  const started = Date.now();
  const result = await matte({ image, query });
  console.log(`往返 ${Date.now() - started}ms`);
  if (!result.ok) {
    console.error("失败：", result.error);
    process.exit(1);
  }
  console.log("prompt:", result.prompt);
  console.log("response:", result.response);
  console.log("metrics:", result.metrics);
  for (const item of result.instances) {
    console.log(`  #${item.index} box=${JSON.stringify(item.box)} area=${item.area} bbox=${JSON.stringify(item.bbox)} png=${Math.round(item.alphaPng.length / 1024)}KB`);
  }
}
