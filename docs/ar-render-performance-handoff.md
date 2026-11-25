# 甲如 AR 实时贴图性能交接

更新于 2026-11-23。工作区位于 `E:\AI Project\Codex\JiaRu`。

## 当前结论

PA2373 上，独立 CPU 材质 Worker 的三组短窗和 10 分钟混合运动回放均达到 **每秒至少 27 次实际贴图、间隔 p95 不高于 50ms**。这一方案将甲根保护、光泽和纹理合成移出跟踪回调，画布继续按最新手部几何绘制，直接消费同版本已就绪的位图。该方案已合入工作区默认关闭候选（白皮书 v1.2.454），并于集成后在同机通过四组生产烟测、10 分钟持续运行与交互复验（v1.2.456，性能状态 §5.27）；桌面 Windows Chrome 第二平台四组烟测亦通过（v1.2.458）。线上默认仍使用 Hands。

## 代码与部署状态

| 路径 | 当前状态 | 接手入口 |
| --- | --- | --- |
| 线上默认 | 同源 MediaPipe Hands，主线程材质合成。早期 PA2373 五指纹理测得 17.9–18.4fps，测试口径和最新混合回放不同。 | `src/components/ArView.tsx`；[白皮书 §4.5](technical-whitepaper.md#45-ar-tryon-ar-试戴) |
| 工作区隔离生产候选 | `NEXT_PUBLIC_AR_WORKER_CANDIDATE=1` 启用 Hand Landmarker 跟踪 Worker 和环境光采样 Worker，材质仍在主线程重建。跟踪故障回落 Hands，环境光故障回落同步采样。 | `src/lib/ar-hand-tracker.ts`、`src/lib/ar-light-sampler.ts`、`public/ar/` |
| CPU 材质 Worker 实测原型 | 三组性能对照、成品像素、故障注入与 10 分钟回放已有报告。通过试验参数选择，保留在本机隔离构建。 | `.tmp/ar-perf/production-material-worker-20261123/` |
| CPU 材质 Worker 接入草案 | 已合入工作区默认关闭候选（白皮书 v1.2.454）：`ArView.tsx`、`ar-material-painter.ts`、`ar-material-jobs.ts`、`ar-material.worker.ts` 随现有生产候选开关启动，工作区较新的侧缘保护提取版保留。定向 ESLint、源码与测试 TypeScript、94 项 AR 回归及隔离生产构建通过。原草案与四组生产烟测报告留存本机。 | 工作区 `src/`；原草案 `.tmp/ar-perf/production-material-release-20261123/`，构建 ID `18hDmLNiepfJYVdseYJKo` |

隔离源码、测试脚本和报告均在本机已忽略的 `.tmp/ar-perf/`。跨机器接手时需要单独传递相关文件。当前工作区有其他未提交改动，接入时应核对差异并保留这些改动。

## PA2373 验收证据

短窗使用 Android Edge、同一 1280×720 混合旋转和平移回放、同一测试纹理和五指应用流程。每次预热后采 30 秒，以主画布实际贴图且对应不同跟踪帧序号计数。

| 30 秒对照 | 主线程材质 | CPU 材质 Worker | 贴图间隔 p95 |
| --- | ---: | ---: | --- |
| 第 1 组 | 26.40 次/秒 | 29.37 次/秒 | 51.2 → 43.7ms |
| 第 2 组，反序 | 26.10 次/秒 | 28.83 次/秒 | 53.5 → 44.1ms |
| 第 3 组，反序 | 25.20 次/秒 | 28.77 次/秒 | 53.6 → 44.2ms |

- **持续运行**。10 分钟共 17,389 次贴图，平均 28.98 次/秒，全窗 p95 44.9ms。逐分钟 28.65–29.18 次/秒，p95 44.2–46.0ms；电池温度 20.9 → 21.2°C，起止热状态均为 0。
- **成品像素**。静止 3 次、混合运动 84 次，共 1,036,944 个 RGBA 字节逐字节一致。对照使用相同输入和颗粒图，读取的是 Worker 转回主线程的完整材质位图。
- **故障与资源**。注入一次材质传输失败后，跟踪 Worker 持续运行，同步材质路径 10 秒绘制 250 个不同帧。另将一张材质位图延迟 300ms，其间注入 13 次丢手结果，迟到位图被丢弃，重入后恢复贴图。关闭时轨道、视频绑定和已启动 Worker 均完成释放。
- **接入草案生产烟测**。ADB 恢复后，在 30 秒内实际绘制 880 个不同帧，29.33 次/秒、间隔 p95 44.1ms，显示 236 张 Worker 生成的材质位图。材质传输故障后 10 秒继续贴图 262 次，迟到位图在丢手时被关闭且未绘制，重入后 10 秒贴图 279 次。跟踪 Worker 故障后 Hands 恢复贴图。四组均停轨、解绑视频并各终止三个 Worker 一次，生产诊断事件为 0。测试结束已重新核对原 AR 标签，随后回收本次临时映射。
- **集成版复验**。合入工作区后同机复跑四组烟测（正常 883 帧、29.43 次/秒、p95 49.0ms）、10 分钟长跑（17,604 帧、29.34 次/秒、逐分钟 p95 ≤45.5ms、电池 22.8–23.3°C、热状态 0）、换纹理/横竖布局/纯色切换与三次相机启停。报告与 SHA-256 见 [性能状态 §5.27](ar-render-performance-status.md)；补核脚本 `.tmp/ar-perf/production-material-integrated-endurance*.mjs`。
- **已排除路径**。直接将 Canvas 甲根保护移到 WebGL2 后，贴图降至 19.50–19.90 次/秒，间隔 p95 增至 84.7–88.0ms。此前窄带读回、保护域合并和重叠采样复用也未稳定过门。详见 [性能状态 §5.21–5.26](ar-render-performance-status.md)。

## 接手后的验证顺序

1. **同步业务源码（已完成）。** 草案四个文件已合入工作区默认关闭候选，工作区其他未提交改动（含侧缘保护提取版 `extract-mask-texture.ts`）保留；定向 ESLint、源码与测试 TypeScript、94 项 AR 回归及隔离生产构建通过，白皮书 §4.5 与当日日志已按 v1.2.454 同步。接手者从第 2 步继续。
2. **复验集成后的运行行为（已完成，2026-11-24）。** 集成版四组生产烟测通过：正常 30 秒 29.43 次/秒、p95 49.0ms；10 分钟连续运行 29.34 次/秒、逐分钟 p95 43.5–45.5ms、热状态 0；换纹理、横竖布局、纯色切换与三次相机启停均通过（初测启停漂移经排查为探针合成视频源未释放所致，修正后三轮 p95 43.3–45.3ms 全过门）。切后台发现 Edge 不派发 visibilitychange，新增活动间隔看门狗（5 秒阈值）并复验复位与重启吞吐通过。证据与 SHA-256 见性能状态 §5.27。
3. **补齐发布证据。** 端到端 p95 配对已完成：候选 63.3ms ≤ Hands 168.2ms，无回退；桌面 Chrome 第二平台四组烟测通过（29.83 次/秒、p95 46.4ms，性能状态 §5.27）。剩余两项：①真人实拍——验收脚本 `.tmp/ar-perf/real-hand-acceptance.mjs` 已就绪（真实前摄、手部稳定 3 秒后自动测 30 秒＋3 张整屏截图，有效窗 ≥300 次贴图），需用户拿起手机、手背朝前摄持续在镜约 60 秒并做横移/快速反向/侧转/翻掌/遮挡重入，随后逐指检查甲根、两侧、甲尖及透明轮廓；五轮自动尝试因手部未持续在镜未取得有效窗（手机平放镜头朝天花板），失败报告保留。②多机型——当前仅一台 PA2373 在线，需补充硬件。真实手部验收此前已由用户安排后续进行。发布口径见 [白皮书 §11](technical-whitepaper.md#11-已知限制与下一阶段) 和 [性能验收 §5.4](ar-render-performance-status.md#54-工程验收草案)。

真人实拍复跑（服务与映射就绪后，一条命令）：

```powershell
$env:AR_SMOKE_CDP = 'http://127.0.0.1:9222'
$env:AR_REAL_REPORT = ".tmp/ar-perf/real-hand-acceptance-$(Get-Date -Format yyyyMMdd-HHmmss).json"
node .tmp/ar-perf/real-hand-acceptance.mjs
```

## 复跑和原始报告

当前工作区的隔离候选在同一 PowerShell 会话中构建和启动。使用独立输出目录 `.next-ar-worker`。离线时可通过 `AR_WORKER_MODEL_FILE` 指向已校验的官方模型文件。草案验证应启动草案自己的生产构建目录。

```powershell
$env:NEXT_PUBLIC_AR_WORKER_CANDIDATE = '1'
$env:CODEBUDDY_SAFE_DELETE_ENABLED = '0'
npm.cmd run build
npm.cmd run start -- --hostname 127.0.0.1 --port 3199
```

真机脚本从工作区根目录运行。设置 `AR_SMOKE_CDP` 为 CDP 地址、`AR_SMOKE_ORIGIN` 为设备侧隔离服务地址、`AR_SMOKE_REPORT` 为新的报告路径。脚本复用 PA2373 已有的 `http://localhost:3000/ar-tryon` 标签，结束时尝试恢复该地址。旧报告按原路径留存。

在已恢复设备和 CDP、已确认端口空闲的情况下，可用以下命令验证已构建的接入草案。先在一个终端启动服务，再在另一个终端建立临时映射并跑烟测。结束后仅移除本次映射并关闭本次启动的服务。

```powershell
# 服务终端
$env:NEXT_PUBLIC_AR_WORKER_CANDIDATE = '1'
node node_modules/next/dist/bin/next start .tmp/ar-perf/production-material-release-20261123 --hostname 127.0.0.1 --port 3199

# 测试终端
adb.exe reverse tcp:3199 tcp:3199
$env:AR_SMOKE_CDP = 'http://127.0.0.1:9222'
$env:AR_SMOKE_ORIGIN = 'http://localhost:3199'
$env:AR_SMOKE_REPORT = ".tmp/ar-perf/production-material-release-replay-$(Get-Date -Format yyyyMMdd-HHmmss).json"
try {
  node .tmp/ar-perf/production-material-release-smoke.mjs
  if ($LASTEXITCODE) { throw '接入草案烟测失败' }
} finally {
  adb.exe reverse --remove tcp:3199
}
```

| 证据 | `.tmp/ar-perf/` 下的脚本 | 原始 JSON |
| --- | --- | --- |
| 同帧像素及两组交叉对照、第三组对照 | `production-material-worker-replay.mjs` | `production-material-worker-parity-20261123.json`、`production-material-worker-abba-20261123.json`、`production-material-worker-third-pair-20261123.json` |
| 传输异常与丢手回包 | `production-material-worker-lifecycle.mjs` | `production-material-worker-lifecycle-20261123.json` |
| 10 分钟回放 | `production-material-worker-soak.mjs` | `production-material-worker-soak-20261123.json` |
| 接入草案的生产烟测 | `production-material-release-smoke.mjs` | `production-material-release-smoke-20261123.json` |

报告 SHA-256 和阶段核验见 [11 月 23 日开发日志](../dev-log/2026-11-23.md) 与 [性能状态 §5.26](ar-render-performance-status.md#526-独立-cpu-材质合成-worker)。
