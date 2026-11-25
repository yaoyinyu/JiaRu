# AR 手势验收集 v1（角色隔离）

清单与哈希见同目录 `ar-gesture-acceptance-set-v1.json`（schema `ar-gesture-acceptance-set-v1`）。

## 用途与角色隔离

- 仅用于 **AR 渲染门控（逐指可见性 / 朝向 / 几何）校准与产品验收**。
- 禁止回流模型 train/val/test、禁止用于模型 `scoreThreshold` 校准、禁止冒充模型质量或来源独立证据、禁止作为发布证据。
- 模型权重、manifest、发布质量门与 `PRODUCT HOLD` 不受本集影响。

## 手势八类

伸展开掌背 open-dorsum、握拳 fist、比耶 peace、蜷指/钩指 curled-hook、掌面回蜷 palm-curl、捏合特写 pinch-closeup、双手捧物 two-hand-cup、侧转 sideways。

静态示例 6 图（253/255/241/8/1/361.jpg）已按 SHA-256 与字节冻结于 JSON，覆盖 pinch-closeup / curled-hook / palm-curl / fist / two-hand-cup；open-dorsum / peace / sideways 由真机视频与补充真图补齐。

## 真机视频协议（已冻结，待采集）

- 每类 >=10s，含静止 / 缓慢移动 / 快速移动三段；记录设备型号、浏览器、朝向标签、逐指显隐 UI。
- 误贴对照：掌面伸直指三变体（原构图 / 镜像 / 提亮）零渲染；双手 / 侧转记录错配率。
- 设备：四类移动真机 + 桌面第二平台（用户已确认可提供）。

## 基线性能

基线 fps / 贴图间隔 p95 / 内存于 M4 用同一合成 MediaStream harness 实测后回填 JSON `baselinePerformance`，作为回归对照（<=5% fps 回归门）。

## 审核纪律

图像审核只发完整原图（visual-review）；真机视频 / 截图仅作功能回归，不入训练与发布证据。冻结报告哈希绑定、只读重放、失败保留原分母（evidence-replay）。