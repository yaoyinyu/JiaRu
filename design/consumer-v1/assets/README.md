# 设计稿位图素材（本地保留，不入库）

`design/consumer-v1/` 下的页面代码、字体与说明文档已进入版本库；本目录中的大尺寸位图素材
（当前为三张 `hero-hand-*.png` 主视觉，单张 2MB 以上）**不随仓库分发**，已在仓库根目录
`.gitignore` 中以 `design/consumer-v1/assets/*.png` 排除。

## 本地预览需要的素材

| 文件名 | 被引用位置 |
| --- | --- |
| `hero-hand-diversity-v3.png` | `app.mjs` 首屏 hero 主视觉（`/assets/hero-hand-diversity-v3.png`） |
| `hero-hand-collage-v2.png` | 拼贴视觉备选稿 |
| `hero-hand-v1.png` | 单手主视觉备选稿 |

缺失时页面结构与交互仍可正常渲染，仅图片位显示为空白。

## 预览方式

```bash
node scripts/serve-consumer-design.mjs
```

说明：本站资源以 `/assets/...` 绝对路径引用，需通过该脚本提供的本地静态服务打开，
直接以文件方式打开 `index.html` 会导致字体与图片加载失败。
