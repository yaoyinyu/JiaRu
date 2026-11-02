# 本机开发与前端排障

本文件是根目录 [AGENTS.md](../../AGENTS.md) 的专项规则，命中其读取条件时必须在执行前完整读取；多主题任务须同时遵守所有相关文件。当前状态、样本数、预算与路径绑定以权威文档及可重放报告为准。

## 命令环境与验证范围

- Windows 项目脚本使用 `npm.cmd`，避免裸 `npm` 命中系统目录同名文件并触发应用选择弹窗。PowerShell 优先显式使用 `C:\Program Files\PowerShell\7\pwsh.exe`；先核对实际解释器与工具版本。
- 运行含裸 `python` 子进程的验收命令（含 `npm.cmd test`、`npm.cmd run audit:nail-texture-completion`）前，将 `C:\Users\YaoYinyu\AppData\Local\Programs\Python\Python313` 置于当前进程 PATH 首位，并核验实际解析路径。依赖缺失按环境失败保留，修复后串行重跑。
- 使用 `tempfile` 或系统临时目录的测试，先创建并验证当前权限允许写入的独立目录，再设置当前进程的 `TEMP`/`TMP`。普通测试优先使用工作区内已忽略目录；要求输出位于 Git 工作区外的测试（如 `build-release-test-annotation-workspace.py`）使用已获写权限的仓库外隔离目录。全量测试须选择满足全部测试守卫的目录；若环境尚无合适路径，先解决目录权限。保留原权限或路径失败，保持测试断言与输出守卫原样。
- 全量 `npm.cmd test` 与 `npm.cmd run build` 串行执行，避免文件系统与子进程竞争。若并行高负载下失败，先逐文件串行复验，再执行一次全量串行回归；阶段验收使用串行结果。
- 验证范围按变更风险选择：纯文档执行差异、引用与编码检查；行为修改执行相关测试及适用的 lint/typecheck；阶段验收按任务合同执行全量测试和构建。测试数、退出码、环境失败与重跑结果须如实记录。
- 文本及文件检索优先使用 `rg` / `rg --files`，默认排除 `docs/archive/**`；文件名筛选使用 `--glob` 或先枚举路径，避免依赖 Windows shell 展开通配路径。
- PowerShell 批量 JSON 检查先设置 `$ErrorActionPreference='Stop'`，逐文件执行 `Test-Path -LiteralPath <path> -PathType Leaf`，确认存在后读取并解析；任一步失败即记录失败，禁止继续累加通过数。

## 进程、内存与构建服务

- 服务意外退出时保存 stdout、stderr、退出码和时间，核对并行构建/测试的停服记录、进程归属与内存压力，再判断原因。历史 exit 1、worker 数和内存观察值仅作线索。出现堆内存错误时核验当前可用内存、并发进程及实际 worker 配置；调整配置前查本机对应版本文档，保留失败及重跑结果。

- 查进程命令行、端口归属使用 `Get-CimInstance Win32_Process`／`Get-NetTCPConnection`，避免依赖 `wmic` 的安装状态；在 Git Bash 中内嵌 PowerShell 查询时，整体用单引号包裹、内部条件用双引号，避免 `$` 变量与引号被 bash 展开或转义损坏。

- 操作服务前核验 PID、命令行、工作目录、监听端口和所用构建目录；只停止本次已确认归属的进程，避免按进程名批量结束其他会话或用户服务。
- 端口上已有 `next start`/`next dev` 提供预览时，先停止使用同一 `.next` 的对应服务再执行 `npm.cmd run build`，构建完成后重启并刷新页面。核验 CSS/JS/图片资源请求无 ≥400、无未约束图标或图片异常撑大、无坏图及横向溢出；超过 200px 的 SVG/图片按设计用途检查尺寸约束，主图和画布保留预期尺寸。业务 API 的预期状态码单独核对与登记。构建失败时保留日志，并明确预览的恢复状态。

## 脚本与测试陷阱

- PowerShell对`[ordered]`哈希表使用`Select-Object`/`Measure-Object`前，须先转为`PSCustomObject`或直接按键累加；字节与分母聚合必须和逐记录重算一致，`null`不得解释为0或通过。冻结报告发现空聚合须保留旧版并另版修正。

- 在Node测试内部通过子进程启动独立`node --test`套件时，须从子进程环境移除继承的`NODE_TEST_CONTEXT`，并核验实际测试数与通过数；父测试上下文下的子进程退出0或空输出不能证明子套件执行。

## Tailwind断点

- Tailwind 4 中按像素自定义断点必须通过 `@theme` 增加 `--breakpoint-*` 命名令牌（如 `--breakpoint-wl: 68.75rem` 对应 1100px）后使用命名前缀（如 `wl:`）；任意变体写法 `min-[1100px]:` 虽会生成对应规则，但层叠排序位于 `md:`/`lg:` 等命名断点之前，同优先级下无法覆盖命名断点的工具类（2026-10-28 图库密度优化实测）。
