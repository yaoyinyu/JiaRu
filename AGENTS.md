# 本文档应使用中文编辑
<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Project documentation rules

- `docs/technical-whitepaper.md` is the canonical integration and interface document.
- **Mandatory before every task:** read `docs/technical-whitepaper.md` before planning, diagnosing, editing, or running task-specific operations. At minimum inspect the status table, relevant module sections, known limitations, and latest change-log entry; verify relevant claims against current source or machine-readable reports.
- In the first progress update for a task, explicitly state that the whitepaper was read and name the relevant section/status used. This is the observable task-start acknowledgment.
- **Mandatory after every task:** update the relevant whitepaper content and append its change log before declaring completion. This applies even when no interface changes: record that the whitepaper was reviewed and why no interface/status change was required.
- If source/configuration/audit results conflict with the whitepaper, current reproducible evidence wins and the whitepaper must be corrected in the same task.
- Keep one development log file per day under `dev-log/YYYY-MM-DD.md`; append all work from the same day to that file instead of creating multiple daily files.
- Mirror the task summary, whitepaper changes, and verification result into the daily development log before finishing.
- In the final response, explicitly name the whitepaper section/change-log entry and daily log that were synchronized.
- Do not report a task as complete until the whitepaper and daily log are synchronized and appropriate checks have passed.

## Behavior rules and key points

- Use this file for durable behavior rules and key project constraints. Do not copy stage summaries, changing sample counts, temporary paths, commit records, or one-off results here.
- When a development-log entry reveals a reusable workflow constraint, review rule, or troubleshooting technique, extract only the durable rule and add it here; keep the underlying event and evidence in the whitepaper and daily log.
- For nail annotation, a passing prompt-geometry audit proves only that the mask is geometrically consistent with its prompt. It never replaces original-resolution visual review for missing nails, incomplete nail surfaces, duplicates, skin, clothing, or background contamination.
- Prioritize fully visible nails during annotation review. Every fully exposed nail must have exactly one complete mask covering the whole visible nail surface; a mask that captures only the color, decoration, tip, or another partial region is a rework failure even when its geometry audit passes.
- 返修透明、低对比或延长甲时，优先用多个正点分别覆盖有色甲面与透明甲尖，并把定向负点放在邻近皮肤、衣物或背景污染区；禁止把正点放入污染区。多点提示仍只是候选生成手段，必须通过原分辨率视觉审核。
- Exclude a source image instead of repeatedly repairing it when any required nail is cropped by an image edge or is not fully visible. Prompt modes such as `box-center` and `center-negative-corners` remain candidate-generation aids; accept their output only after the same original-resolution review gate.
- 模糊、失焦、低清到无法确认完整甲面轮廓，或存在应标甲面裁断、残缺、仅局部露出的源图，必须在源图筛选阶段排除；此类图片及其派生物不得进入模型训练。源图筛选通过也只代表待标注候选，完整mask逐甲原分辨率审核通过前`trainingUse`必须保持`prohibited`。
- 质量分片审核必须以审核页报告中绑定的输入分片路径和SHA-256为唯一清单来源；工作区内即使存在同编号的`review-*.csv`或其他旧分片，也不得按文件名猜测或混用，写决策前必须复验报告绑定路径、哈希和条目数。
- `build-reviewed-sam-repair-prompts.py` 的 `keepPromptIndices` 使用从 1 开始的提示序号；编写返修清单时不得按数组的 0 起始索引填写。
- Windows 下运行项目 npm 脚本必须显式使用 `npm.cmd`，禁止调用无扩展名的裸 `npm`；本机 `C:\Windows\System32\npm` 可能优先于 Node.js 安装目录并触发“选择应用打开”弹窗。
- Windows 下执行项目 PowerShell 命令时优先显式使用 `C:\Program Files\PowerShell\7\pwsh.exe`；不要因宿主默认仍指向旧版 Windows PowerShell 而误判 PowerShell 7 未安装。
- 未经用户在当前任务中明确要求，不执行 `git commit` 或 `git push`；完成修改与验证后仅保留本地工作区差异。
- 父截图可用但派生区域选错时，应按父文件 SHA-256 和稳定 `sourceGroup` 替换旧区域，并保持一父图一派生区域；禁止把新旧区域重复计数，也不得因此误排除父图。
- 验证集真值必须逐图通过原分辨率完整甲面审核；任一图片仍为返修或排除、存在未声明交叠、漏甲、重复、误标或污染时，整套 split 不得用于模型选择或阈值校准，基于该真值产生的高指标只能保留为历史诊断。
- 模型`scoreThreshold`只能使用来源隔离且未进入train/test的`val`证据校准；冻结test、发布测试及其派生物禁止参与阈值选择。验证集少于30张、存在需修复真值polygon或未通过召回/误检/候选数门时，只能输出诊断阈值，禁止写入候选或生产manifest。
- 冻结发布测试候选前必须逐文件验证多边形合法性与同图零交叠，并复算图片、标注、图片/标注联合及聚合清单哈希；冻结门发现假阳性或拓扑错误时必须回到原图修正并重建上游审核统计，禁止用容差或忽略错误绕过。
- 当透明、低对比或相邻长甲在多轮 SAM 紧框/多点提示后仍持续合并皮肤或邻指时，可以切换为原分辨率人工多边形；人工多边形必须逐甲覆盖完整可见甲面，并继续通过多边形合法性、两两零交叠、提示/外接框几何审计和原图局部放大视觉复核，禁止把“人工绘制”本身视为通过依据。
- `build-reviewed-manual-polygon-repair.py` 清单中的 `nails[].sourceIndex` 使用从 1 开始的原标注序号；混合返修只允许保留已完成原分辨率视觉审核的polygon，脚本产物始终是候选，不能因合法性、零交叠或几何通过而自动晋升训练或test真值。
- 训练真值规模必须按稳定图片身份去重，禁止按`training-truth-*.json`报告文件数直接累计；同一`item.fileName`存在多个批准报告时，只有图片身份、annotation SHA-256、来源组和mask数完全一致才可选最高序号报告作为规范记录并计数一次，任一字段冲突必须拒绝训练物化。
- 模型发布质量必须以实际部署输入尺寸和来源隔离的冻结测试快照判定；更高输入尺寸的诊断结果或历史小测试集不得覆盖扩展快照在部署口径上的失败。失败快照必须继续禁止训练，改进候选只能使用获得训练授权且与冻结测试来源隔离的新样本。
- 冻结测试集上的置信度扫描只能用于候选诊断；降低阈值提高召回时，必须同时审核误检、浏览器候选数量上限和Beta直接可用率，禁止仅凭离线召回提升修改共享默认阈值。
- 全量`npm.cmd test`与`npm.cmd run build`必须串行执行；当前测试套件包含文件系统与子进程敏感用例，并行高负载可能产生临时目录或进程竞争型假失败。若并行运行出现失败，先逐文件串行复验，再执行一次全量串行回归，只有串行结果可以作为阶段验收结论。
- AI生成困难负样本不得因来源为AI而放宽清晰度、完整性、真人甲面排除或原分辨率审核门；若负样本存在系统性水印、模糊角标或生成器特征，正式晋升前必须完成原图与去水印/遮挡变体的误检消融，禁止让模型以来源标记代替真实视觉语义。
