# 本机业务候选模型

当前版本：`jiaru-real100-geometry64-trial-v1`。2026-11-05 已启用本机业务体验，入口为 `/ar-tryon` 上传参考图后的「精细抠图（本机）」。服务运行于本机 Python/GPU，返回像素 mask，沿用候选匹配、逐甲复核、纹理提取与应用流程。

## 模型选择

- Stage A：指定真实100源40轮，权重 SHA-256 `5ef154704e36691871a50e162b8e446a12dc3211404ad014f8aceeb9d8b52b4e`。
- 精修：几何残差64轮固定末态，权重 SHA-256 `161e10be562fa4becd00cbde2c7bb4fcf80611308c681afc9dfd4e6d71fbf9ea`。
- 两份权重合计12,898,950字节。在已完成全100图634甲终评的当前真实100源精修分支中，该版平均Boundary IoU最高（0.338758），F1为0.764382；严格联合仍0/634。512轮新版终评尚待完成，再依据完整结果决定替换。

## 使用

1. 打开 `http://localhost:3000/ar-tryon`，上传参考图。当前浏览器ONNX模型优先自动识别。
2. 需要本机服务补充时，在默认展开的「精细抠图（本机）」点击「识别甲面」；首次“同意并识别”直接执行。已有纹理时可在替换确认框选择「继续调整」进入选择器。服务未就绪可原地重新检查，照片和现有结果保留。
3. 核对轮廓、未匹配候选和指位，点击「提取所选纹理」应用。记住本机处理确认后，后续上传在浏览器降级或空结果时自动补充本机识别；有效浏览器模型结果保持。

当前前端沿用长边1600 JPEG编码及实例匹配规则；模型返回整张编码图尺寸的二值PNG mask。存在本地候选时只替换匹配mask，未匹配候选保留原结果；本地0候选时走既有兜底识别。`task/query/boxes`兼容业务请求，模型始终执行整图甲面检测，框与文字不参与模型推理。

## 服务、配置与回退

通用入口：`model/training/serve-nail-candidate.py --config <本地配置JSON> --port 8011`。本次本地配置位于 `model/reviews/business-candidate-20261105-v1/service-config.json`，含独立令牌，应保持本地。启动示例（项目根目录，PowerShell）：

```powershell
& 'C:/Users/YaoYinyu/AppData/Local/Programs/Python/Python313/python.exe' -X utf8 model/training/serve-nail-candidate.py --config model/reviews/business-candidate-20261105-v1/service-config.json --port 8011
```

服务须在独立终端运行；端口已占用时先核验现有服务归属。当前已启动，可直接体验。配置引用的训练源码与权重均校验SHA；保留这些文件供后续启动使用。

`.env.local` 中服务端配置 `NAIL_CANDIDATE_URL=http://127.0.0.1:8011`、`NAIL_CANDIDATE_TOKEN=<独立至少32字符令牌>`，优先于原 `VLM_MATTE_URL/TOKEN`。URL仅允许HTTP、127.0.0.1且无额外路径；令牌仅用于服务端转发。原WeVis配置保留。移除两项候选配置并重启业务服务，即恢复原配置选择；候选服务不可用时沿用现有失败提示和本地结果保留流程。

服务仅监听回环地址，鉴权后单请求串行推理；请求体最多8MiB、解码最多900万像素，图片仅内存处理。生产ONNX/manifest及releaseIdentity保持原状态；PRODUCT HOLD继续生效。当前仅用于参考图纹理提取，摄像头实时帧继续既有链路。

## 已验证证据

本地证据目录 `model/reviews/business-candidate-20261105-v1/`：

- `plan.json`、`plan-v2.json`：固定权重与现有train源图；首请求缺Origin返回403的失败保留，修正请求头后另版执行。
- `smoke-v2-report.json`：真实业务API返回200、4枚2250×2998 mask，端到端1.314秒。
- `native-output-replay.json`：这4枚mask与已保存几何64轮终评预测逐像素一致，差异均0；`preprocessing-replay.json`记录4项预处理数组完全一致。
- `ui-report.json`：浏览器自动、手动各一次真实请求均200、各4实例，编码尺寸1201×1600，服务端转发耗时均367ms；手动4/5候选匹配，纹理已应用，页面脚本错误0、资源HTTP错误0、坏图0、横向溢出0。摄像头未开启，本次未做真机试戴。
- 相关33项测试、typecheck、局部ESLint及生产构建通过。单图接入验收保留其范围，后续边缘质量、未见来源及正式运行时门继续按Goal推进。
