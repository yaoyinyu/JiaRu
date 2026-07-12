# 纹理识别内存与连续运行门禁

本门禁验证浏览器连续识别时是否出现持续内存增长。它与推理耗时门分开，不使用单次 tensor 理论尺寸代替真实浏览器采样。

## 采样

Windows 桌面基准使用真实 `/ar-tryon` 页面、候选模型 manifest、真实图片和 Chromium WebGPU。采样脚本连续执行上传、Worker 推理、候选返回、关闭弹窗，并同时记录：

- `performance.memory` 的 JS heap；
- Playwright Chromium 全部进程的 working set 和 private bytes；
- 模型版本、后端、端到端时间和 Worker 时间。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/benchmark-recognition-memory.ps1 `
  -ImagePath "<real-image>" `
  -OutputPath "<raw-report.json>" `
  -Samples 20

node --no-warnings --experimental-strip-types scripts/verify-recognition-memory.ts `
  --input "<raw-report.json>" `
  --output "<verification.json>"
```

桌面暂定门槛为至少 20 次、JS 首末五次均值增长不超过 32MiB、Chromium 私有内存首末五次均值增长不超过 128MiB，且 20 次内不得几乎全程单调增长。该阈值用于发现明显泄漏，不是移动端正式内存承诺。

## v6 桌面结果

`nail-texture-seg-real-candidate-v6` 在 Windows / Playwright Chromium / WebGPU 下通过：

- 20 次真实识别；
- JS heap 峰值 19.86MiB，首末窗口增长 1.69MiB；
- Chromium 全进程 private memory 峰值 929.50MiB，首末窗口增长 121.81MiB；
- Chromium working set 峰值 840.63MiB；
- JS 与私有内存最长连续增长分别为 14 和 7 次，序列均在第 20 次前出现回落；
- 原始采样保留在 Git 忽略的本地模型导出目录，摘要证据为 `model/reports/nail-texture-seg-real-candidate-v6-desktop-memory.json`。

全浏览器内存包含 renderer、GPU、utility、缓存和自动化进程，不能解释为模型独占内存。Android、iPhone 和 iPad 的增量峰值 128–150MiB 建议仍必须在对应真机测量。
