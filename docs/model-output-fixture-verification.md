# 模型输出 Fixture 离线验证

这份文档用于在真实 ONNX 文件尚未正式接入浏览器前，先验证当前后处理逻辑能不能正确消费“录制出来的模型输出张量”。

它解决的问题是：

- 当前 detection tensor 的行布局假设是否成立
- prototype tensor 是否能被识别并解码成 mask
- `postprocessNailTextureDetections()` 的输出候选数量、分数、mask、手指建议是否基本合理

它不解决的问题是：

- 浏览器是否成功加载 ONNX 文件
- onnxruntime-web 是否初始化成功
- Worker / session / execution provider 是否正常

## 1. 运行脚本

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-output-fixture.ts
```

默认会读取：

```text
model/fixtures/nail-texture-model-output-sample.json
```

也可以传入你自己的 fixture：

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-output-fixture.ts C:/path/to/your-output-fixture.json
```

## 1.5 如果你拿到的是原始输出 dump

如果你手里不是 fixture，而是一份更接近真实调试结果的输出 dump，可以先转换：

```bash
node --no-warnings --experimental-strip-types scripts/build-model-output-fixture.ts C:/path/to/model-output-dump.json C:/path/to/model-output-fixture.json
```

然后再验证：

```bash
node --no-warnings --experimental-strip-types scripts/verify-model-output-fixture.ts C:/path/to/model-output-fixture.json
```

仓库里也带了一份示例 dump：

```text
model/fixtures/nail-texture-model-output-dump-sample.json
```

## 2. 输出里重点看什么

重点字段：

- `ok`
- `failures`
- `candidateCount`
- `candidates[*].score`
- `candidates[*].suggestedFinger`
- `candidates[*].hasMask`
- `debugOutputs[*].name`
- `debugOutputs[*].dims`

理想状态：

- `ok === true`
- `failures` 为空
- `candidateCount` 和预期一致
- detection / proto 张量名称和维度能看懂
- 需要 mask 的候选都带有 `hasMask: true`

## 3. 什么时候用

建议在这些场景先跑一遍：

- 真实模型刚导出，但还没正式拷进 `public/models/`
- 你已经拿到了某次推理的输出张量，想先验证后处理是否兼容
- 你准备修改 `postprocess.ts`，但不想等浏览器联调后才知道有没有改坏

## 4. 和真实模型接入的关系

推荐顺序：

1. 先跑 `verify-model-output-fixture.ts`
2. 如果拿到的是原始输出 dump，先跑 `build-model-output-fixture.ts`
3. 再跑 `verify-model-artifact.ts`
4. 再跑 `verify-nail-detection.ts`
5. 最后在 `/ar-tryon` 页面里做 UI 验收

如果你想把 “artifact 检查 + dump 转 fixture + fixture 验证” 串成一次执行，也可以直接跑：

```bash
node --no-warnings --experimental-strip-types scripts/verify-real-model-readiness.ts --manifest public/models/nail-texture-seg/manifest.json --dump C:/path/to/nail-model-output-dump.json --fixture-out C:/path/to/nail-model-output-fixture.json
```

如果真实模型文件已经放好，还可以继续把单图识别验证也串进去：

```bash
node --no-warnings --experimental-strip-types scripts/verify-real-model-readiness.ts --manifest public/models/nail-texture-seg/manifest.json --image model/5188.jpg_wh860.jpg --debug-output-dir model/debug/run-001 --debug-prefix model-v1
```

补充：

- `scripts/verify-nail-detection.ts` 在模型路径可用且启用了调试原始输出时，会额外落盘 `nail-model-output-dump.json`
- 这份 dump 可以直接送进 `build-model-output-fixture.ts`
- `scripts/verify-nail-detection.ts` 现在也支持 `--output-dir` 和 `--prefix`，方便把多次联调产物归档到不同目录并区分命名

这样可以把问题拆成两类：

- 如果 fixture 验证都过不了，说明是后处理假设有问题
- 如果 fixture 能过，但浏览器还是走 fallback，说明更可能是模型加载/runtime/worker 问题
