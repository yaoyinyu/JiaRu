# 美甲纹理候选方向稳定化

版本：v1.0  
日期：2026-07-02

这一步对应 `docs/nail-texture-recognition-model-plan.md` 里 Phase 4 的“候选方向稳定化”。

目标不是重新定义候选框，而是在后处理阶段把“角度抖动、近圆候选方向不稳、同组候选朝向不一致”先压下来，让后续：

- `extract-mask-texture`
- `NailArtPicker`
- 最终纹理裁剪

都建立在更稳定的姿态之上。

## 当前实现位置

- `src/lib/nail-texture-recognition/postprocess.ts`

新增能力：

- `stabilizeNailTextureCandidateAngles()`

它现在接在：

1. 模型输出解码
2. 候选质量排序
3. 手指建议分配

之间，属于 postprocess 的一部分。

## 当前稳定化规则

### 1. 先区分“可靠方向候选”和“弱方向候选”

当前把这类候选当作方向可靠：

- 有 mask 主轴角度
- 且长宽比至少达到 `1.2`

这意味着：

- 细长、明显沿某个方向展开的甲面，优先保留自己的 mask 角度
- 近圆、接近方块、或者 mask 主轴本身不稳定的候选，不强行相信它自己的 angle

### 2. 弱方向候选优先借用同组平均方向

如果同一张图里存在可靠方向候选，就对这些可靠角度做 half-turn average（180° 等价平均），得到共享方向。

然后把弱方向候选对齐到这个共享方向，并附加：

- `angle_stabilized_from_group`

这个 warning。

这样做的原因是：同一张参考图里的几枚美甲通常拍摄方向接近，哪怕局部 mask 因为高光、边缘缺失或接近圆形而不稳，也可以从同组姿态恢复出更可信的方向。

### 3. 如果没有可借用的组方向，则回退到竖直默认值

如果整组候选都没有可靠角度来源，就把弱方向候选回退到：

- `angle = 0`

并附加：

- `angle_defaulted_vertical`

这比随机保留噪声角度更稳定，也符合规划文档里“最终至少要有默认竖直方向”的要求。

## 当前没有一起做的部分

这次没有把“邻近皮肤延展方向推断”一起塞进来，原因是那一步会引入新的像素级上下文分析和额外误差源。

本轮先把下面这条链闭起来：

- mask 主轴
- 同组平均方向
- 默认竖直回退

后续如果要继续推进，可以在这个基础上补：

1. skin context 方向推断
2. 更强的异常角度检测
3. UI 层对稳定化 warning 的展示

## 自动化验收

本轮新增和覆盖的重点验收包括：

- `tests/nail-texture-preprocess-postprocess.test.ts`
  - 验证弱方向候选可以借用同组稳定角度
  - 验证无 mask / 无组方向时回退到竖直默认角度
- `tests/verify-model-output-fixture.test.ts`
  - 验证离线 postprocess 验收链未被破坏
- `tests/nail-texture-quality.test.ts`
  - 验证质量排序链仍正常

并额外通过：

- `npm.cmd test`
- `npm.cmd run lint`
- `npm.cmd run build`
