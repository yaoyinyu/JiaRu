import { labDistance, rgbToLab } from "./nail-personalization/color-science.ts";

/**
 * 编辑器「美甲纹理套装」静态清单。
 *
 * 资产由 `scripts/build-nail-texture-sets.py` 从真实照片经本机 WeVisOne-VL
 * 抠图提取（归一化：甲尖朝上、紧致裁剪、长边 ≤256px，自带 alpha 轮廓），
 * 落盘 `public/nail-textures/<setId>/finger-1..5.png` 后在此登记。
 * 一套 = 同一张真实照片中提取的五根手指各一枚纹理。
 */

export interface NailTextureSetTexture {
  /** 手指索引：0=拇指 … 4=小指 */
  finger: 0 | 1 | 2 | 3 | 4;
  /** 纹理 PNG 的 public 路径（以 / 开头） */
  src: string;
}

export interface NailTextureSet {
  /** 稳定 id（同时是 public/nail-textures/ 下的目录名） */
  id: string;
  /** 中文展示名 */
  name: string;
  /** 来源说明（真实照片与提取方式），用于展示与追溯 */
  source: string;
  /** 套装主色（hex），灵感色 → 套装映射的依据 */
  dominantColor: string;
  textures: readonly NailTextureSetTexture[];
}

export const NAIL_TEXTURE_SETS: readonly NailTextureSet[] = [
  {
    id: "midnight-glitter",
    name: "黑耀碎闪",
    source: "真实照片 真实素材/美甲图片素材/1/301.jpg，WeVisOne-VL 抠图提取",
    dominantColor: "#272b35",
    textures: [
      { finger: 0, src: "/nail-textures/midnight-glitter/finger-1.png" },
      { finger: 1, src: "/nail-textures/midnight-glitter/finger-2.png" },
      { finger: 2, src: "/nail-textures/midnight-glitter/finger-3.png" },
      { finger: 3, src: "/nail-textures/midnight-glitter/finger-4.png" },
      { finger: 4, src: "/nail-textures/midnight-glitter/finger-5.png" },
    ],
  },
  {
    id: "milk-tea-gold-charm",
    name: "奶茶金饰",
    source: "真实照片 真实素材/美甲图片素材/2/563.jpg，WeVisOne-VL 抠图提取",
    dominantColor: "#a67859",
    textures: [
      { finger: 0, src: "/nail-textures/milk-tea-gold-charm/finger-1.png" },
      { finger: 1, src: "/nail-textures/milk-tea-gold-charm/finger-2.png" },
      { finger: 2, src: "/nail-textures/milk-tea-gold-charm/finger-3.png" },
      { finger: 3, src: "/nail-textures/milk-tea-gold-charm/finger-4.png" },
      { finger: 4, src: "/nail-textures/milk-tea-gold-charm/finger-5.png" },
    ],
  },
  {
    id: "rose-glitter-pearl",
    name: "玫红爆闪珍珠",
    source: "真实照片 真实素材/美甲图片素材/3/1161.jpg，WeVisOne-VL 抠图提取",
    dominantColor: "#a76876",
    textures: [
      { finger: 0, src: "/nail-textures/rose-glitter-pearl/finger-1.png" },
      { finger: 1, src: "/nail-textures/rose-glitter-pearl/finger-2.png" },
      { finger: 2, src: "/nail-textures/rose-glitter-pearl/finger-3.png" },
      { finger: 3, src: "/nail-textures/rose-glitter-pearl/finger-4.png" },
      { finger: 4, src: "/nail-textures/rose-glitter-pearl/finger-5.png" },
    ],
  },
  {
    id: "navy-pink-pearl",
    name: "蓝粉珍珠混搭",
    source: "真实照片 真实素材/美甲图片素材/1/437.jpg，WeVisOne-VL 抠图提取",
    dominantColor: "#ba9796",
    textures: [
      { finger: 0, src: "/nail-textures/navy-pink-pearl/finger-1.png" },
      { finger: 1, src: "/nail-textures/navy-pink-pearl/finger-2.png" },
      { finger: 2, src: "/nail-textures/navy-pink-pearl/finger-3.png" },
      { finger: 3, src: "/nail-textures/navy-pink-pearl/finger-4.png" },
      { finger: 4, src: "/nail-textures/navy-pink-pearl/finger-5.png" },
    ],
  },
  {
    id: "nude-pink-french",
    name: "裸粉白星法式",
    source: "真实照片 真实素材/美甲图片素材/1/234.jpg，WeVisOne-VL 抠图提取",
    dominantColor: "#b88c84",
    textures: [
      { finger: 0, src: "/nail-textures/nude-pink-french/finger-1.png" },
      { finger: 1, src: "/nail-textures/nude-pink-french/finger-2.png" },
      { finger: 2, src: "/nail-textures/nude-pink-french/finger-3.png" },
      { finger: 3, src: "/nail-textures/nude-pink-french/finger-4.png" },
      { finger: 4, src: "/nail-textures/nude-pink-french/finger-5.png" },
    ],
  },
];

export function parseHexColor(hex: string): { r: number; g: number; b: number } | null {
  if (typeof hex !== "string") return null;
  const match = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!match) return null;
  const value = parseInt(match[1], 16);
  return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255 };
}

/**
 * 灵感色（图库/分析页推荐色）→ 最接近主色的纹理套装。
 * 无可用套装或 hex 非法时返回 null，调用方按「未预选」处理。
 */
export function closestTextureSet(hex: string): NailTextureSet | null {
  const rgb = parseHexColor(hex);
  if (!rgb || NAIL_TEXTURE_SETS.length === 0) return null;
  const lab = rgbToLab(rgb.r, rgb.g, rgb.b);
  let best: NailTextureSet | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const set of NAIL_TEXTURE_SETS) {
    const setRgb = parseHexColor(set.dominantColor);
    if (!setRgb) continue;
    const distance = labDistance(lab, rgbToLab(setRgb.r, setRgb.g, setRgb.b));
    if (distance < bestDistance) {
      bestDistance = distance;
      best = set;
    }
  }
  return best;
}

/** 套装中指定手指的纹理；缺失返回 null。 */
export function textureSrcFor(set: NailTextureSet, finger: number): NailTextureSetTexture | null {
  return set.textures.find((item) => item.finger === finger) ?? null;
}
