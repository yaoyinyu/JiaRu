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
- `build-reviewed-sam-repair-prompts.py` 的 `keepPromptIndices` 使用从 1 开始的提示序号；编写返修清单时不得按数组的 0 起始索引填写。
- Windows 下运行项目 npm 脚本必须显式使用 `npm.cmd`，禁止调用无扩展名的裸 `npm`；本机 `C:\Windows\System32\npm` 可能优先于 Node.js 安装目录并触发“选择应用打开”弹窗。
- 未经用户在当前任务中明确要求，不执行 `git commit` 或 `git push`；完成修改与验证后仅保留本地工作区差异。
- 父截图可用但派生区域选错时，应按父文件 SHA-256 和稳定 `sourceGroup` 替换旧区域，并保持一父图一派生区域；禁止把新旧区域重复计数，也不得因此误排除父图。
