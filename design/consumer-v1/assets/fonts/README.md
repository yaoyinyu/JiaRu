# 中文标题字体

`jiaru-editorial-serif.woff2` 是 **Noto Serif SC** 的本地衍生子集，供独立消费者原型标题使用。内部字体家族重命名为 `JiaRu Editorial Serif`，字重轴保留 400–600，默认 400。字体文件 259,272 字节，覆盖 723 个 Unicode 码位，其中汉字 614 个。

## 来源与许可

- [Google Fonts 官方字体源](https://github.com/google/fonts/tree/main/ofl/notoserifsc)；[官方字体元数据](https://github.com/google/fonts/blob/main/ofl/notoserifsc/METADATA.pb)。
- 原字体版权信息保留在字体 name 表中，包含 `(c) 2017-2024 Adobe (http://www.adobe.com/)`。随附的 `OFL.txt` 为官方仓库原件，版权声明及 SIL Open Font License 1.1 全文原样保留。
- 根据 [SIL Open Font License 1.1](./OFL.txt) 分发此字体及其衍生物，允许商业软件内嵌和随软件再分发；字体本身不得单独出售。此衍生字体继续遵守该许可。

## 字符范围与后备

字符集取自 `design/consumer-v1/app.mjs`、`index.html` 的可打印字符，再补入常见界面／设备词及 ASCII。只保留源字体已有字形；emoji、图标与未覆盖文本由系统后备字体处理。标题的 CSS 应继续列出 `Songti SC`、`Noto Serif CJK SC`、`serif` 等后备；用户自由输入与长正文保留系统字体。后续标题文案新增字时应重建子集，不能声称本文件覆盖完整中文。

字体必须从本机原型服务加载，不连接 Google Fonts API 或远程 CDN。`font-display: swap` 可保持初次加载可读；资源请求不应阻塞页面交互。

## 本次验证

- fontTools 4.63.0 重新读取 WOFF2，通过 cmap 全量覆盖与 400–600 字重轴检查。
- 原 TTF SHA-256：`050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9`。
- WOFF2 SHA-256：`225a291eb63cdef7dfa915e127d976d9eda76c7325ac5a1d9844f2d587acc9e1`。
- 许可原件 SHA-256：`5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6`。
- 本地机器记录：`output/frontend-redesign-v2/font-verification.json`。生成脚本：`output/frontend-redesign-v2/build-editorial-font.py`（只在已有本地源字体上执行，不发网络请求）。约 25 MB 的原 TTF 仅置于忽略的处理输出中，不随页面分发。
