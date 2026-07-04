# 文本编码审计

版本：v1.0
日期：2026-07-04

该门禁用于持续验收模型规划 Phase 0 的“修复文档和源码编码显示问题”。

## 运行

```powershell
npm.cmd run audit:encoding
```

默认扫描：

- `src`
- `scripts`
- `model/training`
- `docs`
- `tests`

支持指定一个或多个目录，并可保存 JSON 报告：

```powershell
node --no-warnings --experimental-strip-types scripts/audit-text-encoding.ts `
  --root src `
  --root docs `
  --output text-encoding-audit.json
```

## 硬失败条件

- 文件无法按严格 UTF-8 解码
- 包含 NUL 字符
- 包含 Unicode replacement character
- 包含 Unicode 私用区字符
- 命中高置信 GBK/UTF-8 mojibake 片段

扫描器只处理已知文本扩展名，并跳过 `.git`、`.next`、`node_modules` 和
`__pycache__`。UTF-8 BOM 会计数但不作为失败，便于后续渐进统一。

## 当前基线

2026-07-04 首次全量扫描结果：

- 文本文件：254
- 编码失败：0
- 带 BOM 文件：18

这证明当前目标目录可以严格按 UTF-8 解码，且未检测到替换字符、私用区字符或已知乱码片段。
