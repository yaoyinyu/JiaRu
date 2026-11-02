# 清理任务卡

## 任务 1：清理未使用依赖

### 验收标准
- [ ] `npm uninstall @mediapipe/camera_utils @mediapipe/drawing_utils ngrok`
- [ ] `npm run build` 通过
- [ ] `npm run lint` 0 errors

## 任务 2：清理根目录残留文件

### 验收标准
- [ ] `backup_ar_working/` 移到 `.archive/` 或删除
- [ ] `certificates/` 移到 `.archive/`
- [ ] `https-dev.mjs` 移到 `.archive/`
- [ ] `1f65f04cdd5df509463a03fb17d8ea03.jpg` 移到 `.archive/`
- [ ] `deep-analysis-2026-06-24.md` 移到 `docs/archive/`
- [ ] `scan-report-2026-06-24.md` 移到 `docs/archive/`
- [ ] `_lint*.ps1` / `_build*.ps1` 临时脚本删除
- [ ] `package.json` 不含未使用依赖

## 任务 3：修复 12 个 ESLint warnings

### 验收标准
- [ ] `npm run lint` 输出 `0 problems`
- [ ] `npm run build` 通过
