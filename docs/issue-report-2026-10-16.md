# 甲如项目问题报告（复核修订与实施状态）

更新日期：2026-10-16

本稿已按实际源码、测试和全118项观测证据修订。原工单字节保存在`model/reviews/cycle016-product-presence-20261016-v1/baseline/3.bin`，路径/SHA见同目录`baseline.json`；此前独立复核见`docs/issue-report-2026-10-16-review.md`。历史失败不因本稿修订变为通过。唯一模型目标仍为`docs/nail-texture-current-goal.md`。

## 1. 已采纳并实现的产品修复

### 1.1 辅助定位提示

原绿框仅在模型fallback、局部近景接管且当前区域≥4时触发，不能称所有图片100%触发。现由`auxiliaryDetectionNotice()`统一处理全部fallback区域数：持续显示琥珀色“模型不可用/生产模型尚未部署、辅助定位、人工确认”；零区域提示手工添加。不再显示“可直接提取”，原候选与fallback判定不变。底层技术warning可保留诊断明细，明确降级状态始终可见。

本地行为测试覆盖0/1/3/4/5/10区域及不同降级warning；尚未取得本次真实浏览器产品交互验收，不把单元测试作为Beta直接可用率。

### 1.2 显式未部署模型合同

保留默认manifest，增加`deploymentStatus: "not-deployed"`；计划中的ONNX文件名可以保留，不能声称该资产已存在。类型与校验允许`deployed | not-deployed`，字段缺省兼容旧候选，显式非法值（含null）拒绝。window/worker及Stage B在创建会话前返回`model_not_deployed`与fallback；未部署资产不能通过资产审核、登记或切换，失败不得改活动manifest或登记表。

新测试同时验证没有ORT会话/模型请求，以及即使目录内放置模型fixture也不能绕过状态门。`deployed`声明不取代同一releaseIdentity及全部正式发布门。

### 1.3 CI与构建

新增`npm.cmd run test:ci`，13份可用稳定夹具/临时目录独立执行的产品、几何、运行时及发布契约套件，本地83/83通过，0跳过，已接入Windows CI工作流。没有把spawn或model路径字符串当作必须迁出CI的依据，也没有整体否定合规串行全量结果；GitHub远端实跑尚未取得。

首次沙箱测试82通过/1失败来自临时硬链接EPERM；在允许该能力的环境中保持断言串行复验通过，原失败保留。Lint排除本地冻结reviews/oneoff产物，未改其原源码；最终0错误/1条既有登录页警告。构建生成类型发现微信路由额外导出共享cookie常量，已移至现有auth库并保持cookie值/鉴权行为不变，双类型检查通过。

生产构建尚未通过：默认Turbopack的PostCSS子进程连接失败，提权及路由导出修复后仍失败；官方Webpack诊断构建编译后因Node内存分配失败退出。两类失败分别保留，不改变默认构建器或跳过检查。

### 1.4 CSP注释

已将`next.config.ts`注释改为仓库模板实际情况：Nginx模板未启用CSP、HSTS仅在HTTPS示例列出。未更改响应头策略；仓库模板不能证明所有线上环境的实际响应头。严格CSP仍须验证WASM、worker、blob及摄像头兼容性后另行实施。

## 2. 模型主线：采纳完整presence链，拒绝放宽门

### 2.1 当前阻断与本轮实际进展

当前权重CPU/WebGPU各118/118数值通过，WASM112/118；第40/42/85/87/90/92项presence绝对误差超过1e-4，最大0.0002772808075。mask数值、解码零像素差及presence决策一致不能覆盖这些失败。这是当前运行时直接阻断，并非全部正式发布条件中唯一缺口。

独立非零观测控制累计CUDA/CPU/WASM各4次通过；全118 CUDA及118 WASM实际128维特征捕获完成，原两个输出头均与各自原参考逐字节一致，权重不变。实际WASM原ONNX mask与该路径原始输出比较，不与独立F64 mask混用。报告：`model/reviews/cycle016-full118-presence-observation-v1/project/report.json`，精确分解：同目录`decomposition.json`，只读重放通过。

六项失败中，上游特征差异对presence的贡献绝对值均大于1e-4；保留同一实际WASM特征、以精确线性头计算并按F32落盘，仍0/6修复，可达比0。因此停止“只延伸末端F64线性头”的方案。现有证据尚未拆开编码器与池化各自误差，不提前归因具体算子。

下一实现复用现行F64编码器的完整presence链，包括原二值种子池化、local64/global64顺序与固定线性头；先冻结结构/内存和独立非零控制，全部通过才另立全118学得验收预算，仍以绝对1e-4、零像素差及决策一致验收。新运行时尚未实现或证明通过。合同见`model/reviews/cycle016-product-presence-20261016-v1/next-scope.json`。

### 2.2 不采纳的建议

- 不把绝对1e-4替换为相对1e-4。本批相对误差虽小于1e-4，但允许绝对误差将放宽约4至44倍，不能称严格度不变；仅保留诊断，不改原六失败。
- 不停用已通过的F64 mask与坐标路径，不改权重、mask、原严格CUDA参考或已消费预算。
- 不因presence符号一致、未接生产或sigmoid饱和而删除数值门。
- 不把独立控制、训练域105/106或本次观测通过写成正式来源泛化、生产批准或Goal完成。

原“控制参考/基线与运行时索引不同”判断修正为：118项候选稳定身份及ordinal一致，三套权重不同；比较必须同时绑定候选身份、权重及输出路径，不混用权重参考。

## 3. 延后项与正式发布缺口

- 根目录约498MB权重“零引用”仅由原有限范围检索得出，未覆盖ignored oneoff、冻结JSON血缘、动态参数或外部脚本，不足以授权删除。本轮未删除权重或清理reviews，优先推进模型正式发布。
- e2e覆盖薄仍是待补项；本轮未新增真实产品浏览器验收，不冒充四类真机或Beta。
- 正式发布仍缺第110边界失败处理、训练扩量及未见来源泛化、新来源隔离val≥30、全新正负留出各≥100、角标变体消融、生产ONNX与同一releaseIdentity、浏览器/四类真机各≥20次、Beta≥100及两个不同批准权重回滚。只有全部当前门`ok=true、decision=complete`才能解除PRODUCT HOLD。

## 4. 验证及证据入口

在Python3.13 PATH与工作区TEMP/TMP环境下串行执行；完整日志及结论位于`model/reviews/cycle016-product-presence-20261016-v1/validation.json`及`report.json`。

| 项目 | 本轮结论 |
| --- | --- |
| `npm.cmd run test:ci` | 83/83通过，0跳过；不是全量测试或远端CI实跑 |
| 双类型检查 | 路由导出修复后通过；原生成类型失败保留 |
| `npm.cmd run lint` | 0错误、1条既有警告 |
| `npm.cmd run build` | 未通过，Turbopack子进程连接失败 |
| `npm.cmd run build -- --webpack` | 诊断未通过，Node内存分配失败 |
| 全118观测/精确分解只读重放 | 通过；证明保真与head-only不可达，不证明修复或发布 |
| 原绝对门、数据角色、历史失败 | 保持；PRODUCT HOLD |

白皮书v1.2.66的§3/§6.2/§7/§8.9/§11.1及`dev-log/2026-10-16.md`同步本轮合同与当前结论。
