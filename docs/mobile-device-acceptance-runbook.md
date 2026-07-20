# 移动真机性能与内存验收操作手册

## 1. 适用范围

本手册用于 Android 手机、Android 平板、iPhone 和 iPad 四类真实设备。桌面模拟器、浏览器设备模拟模式和人工填写的假数据不能替代真机证据。

每个设备报告必须绑定同一个：

- `sessionId`；
- `deviceFamily`；
- 模型版本；
- WebGPU 或 WASM 后端；
- 模型输入尺寸；
- 20 次正式推理性能样本；
- 20 次对应的系统级内存样本。

任何 fallback、混合模型、混合后端、跨会话拼接、少于 20 次或源文件漂移都会保持 HOLD。

## 2. 采集浏览器推理会话

1. 在目标真机上访问项目的 `/device-benchmark`。WebGPU 和模型加载需要浏览器认可的安全上下文，优先使用受信任 HTTPS 测试地址。
2. 选择真实设备类别，上传一张清晰、完整露出甲面的实拍图。
3. 点击“开始真机基准”。页面固定执行 3 次预热和 20 次正式采样。
4. 完成后导出 `nail-texture-device-session-<sessionId>.json`。
5. 如果页面显示 fallback、混合后端、模型缺失或样本不足，本轮仅可诊断，不能继续构建 PASS。

将会话转换为正式性能验证报告：

```powershell
node --no-warnings --experimental-strip-types scripts/verify-recognition-performance.ts `
  --profile mobile `
  --min-samples 20 `
  --output E:\evidence\performance.json `
  E:\evidence\nail-texture-device-session-SESSION.json
```

## 3. 采集系统级内存

浏览器 `performance.memory` 只表示部分 JavaScript 堆，不能证明移动端整体峰值内存。必须使用：

- Android：Android Studio Profiler 或等价系统级进程采样；
- iPhone / iPad：Xcode Instruments 的真实 Safari/WebContent 相关进程采样。

复制 [内存采样模板](../model/fixtures/nail-texture-mobile-memory.template.csv)，按性能会话中的 20 次正式推理顺序填写：

```csv
iteration,usedJSHeapMiB,browserPrivateMiB,browserWorkingSetMiB,browserProcessCount
1,0,120.5,105.2,1
```

`usedJSHeapMiB`无法可靠取得时填 `0`；`browserPrivateMiB`和`browserWorkingSetMiB`必须来自系统级工具，禁止用理论估算或浏览器 JS 堆代替。

把 CSV 与同一会话绑定为原始内存报告：

```powershell
npm.cmd run build:nail-texture-mobile-memory -- `
  --session E:\evidence\nail-texture-device-session-SESSION.json `
  --csv E:\evidence\memory.csv `
  --output E:\evidence\memory.raw.json

node --no-warnings --experimental-strip-types scripts/verify-recognition-memory.ts `
  --input E:\evidence\memory.raw.json `
  --output E:\evidence\memory.verified.json
```

## 4. 生成单设备验收报告

```powershell
npm.cmd run build:nail-texture-device-acceptance -- `
  --device-family android `
  --device-name "设备具体型号" `
  --os "Android 版本" `
  --browser "Chrome 版本" `
  --backend webgpu `
  --performance E:\evidence\performance.json `
  --memory E:\evidence\memory.verified.json `
  --output model\reports\nail-texture-device-android.json
```

四个固定输出槽位分别为：

- `model/reports/nail-texture-device-android.json`
- `model/reports/nail-texture-device-android-tablet.json`
- `model/reports/nail-texture-device-iphone.json`
- `model/reports/nail-texture-device-ipad.json`

最终完成度审计不会信任报告外层的 `ok=true`，而会重新读取性能验证、内存验证和原始内存报告，核对路径、SHA-256、20 次样本、统计值及会话身份。源证据发生一字节变化后，既有设备 PASS 自动失效。
