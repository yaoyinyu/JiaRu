// 预设美甲颜色：20 种常用试色
export const PRESET_COLORS = [
  { name: "裸粉色", color: "#F5D5CB" },
  { name: "豆沙红", color: "#C4737D" },
  { name: "酒红色", color: "#722F37" },
  { name: "焦糖色", color: "#AF6E4D" },
  { name: "裸色", color: "#E8C7B7" },
  { name: "纯白色", color: "#FFFFFF" },
  { name: "银色", color: "#C0C0C0" },
  { name: "黑色", color: "#2D2D2D" },
  { name: "雾霾蓝", color: "#7A9EB1" },
  { name: "抹茶绿", color: "#A8B58B" },
  { name: "薰衣草紫", color: "#B39BC8" },
  { name: "橘色", color: "#F4A460" },
  { name: "玫红色", color: "#E2506A" },
  { name: "深蓝色", color: "#2C4A6E" },
  { name: "金色", color: "#CFB53B" },
  { name: "亮片银", color: "#D8D8D8" },
  { name: "透明", color: "rgba(255,255,255,0.3)" },
  { name: "奶茶色", color: "#B89B7B" },
  { name: "樱桃红", color: "#DE3163" },
  { name: "珊瑚粉", color: "#F88379" },
];

// 预设美甲图库
export const GALLERY_IMAGES = [
  { id: 1, src: "/nail-gallery/placeholder-1.svg", name: "渐变裸粉" },
  { id: 2, src: "/nail-gallery/placeholder-2.svg", name: "法式白边" },
  { id: 3, src: "/nail-gallery/placeholder-3.svg", name: "亮片闪粉" },
  { id: 4, src: "/nail-gallery/placeholder-4.svg", name: "简约纯色" },
  { id: 5, src: "/nail-gallery/placeholder-5.svg", name: "复古花纹" },
  { id: 6, src: "/nail-gallery/placeholder-6.svg", name: "宝石镶嵌" },
];

// 手指名称：复用于编辑器和 AR 模块
export const FINGER_NAMES = ["拇指", "食指", "中指", "无名指", "小指"];

// AI 风格关键词
export const AI_STYLES = [
  "甜美风",
  "欧美风",
  "日系",
  "极简",
  "复古",
  "节日",
  "水墨",
  "几何",
  "花草",
  "金属",
];

// 工具函数
export function cn(...classes: (string | boolean | undefined | null)[]) {
  return classes.filter(Boolean).join(" ");
}