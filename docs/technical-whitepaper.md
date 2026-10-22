# 甲如（JiaRu）技术白皮书

> 文档版本：v1.2.146
>
> 基线日期：2026-07-12
>
> 最近全面审查：2026-10-12（v1.2.0结构重构：实验历史与变更记录拆分归档、§3/§11.1历史快照清理；v1.2.2内容精简：§8.1历史执行叙事与§8.4/§9.7/§9.8/§9.9/§11.2复核原文迁至`docs/archive/whitepaper-dataset-contract-history.md`，过期readiness快照改为当前口径指针。见 dev-log/2026-10-12.md）
>
> 文档状态：持续维护
>
> 适用范围：产品页面、前端组件、浏览器端识别、AR 试戴、服务端 API、数据集、训练、模型发布与验证

## 1. 文档定位与维护规则

本文档是甲如项目各功能模块对接的唯一总入口，用于回答以下问题：

- 当前有哪些能力，分别处于已完成、待验证、未完成还是占位状态；
- 页面、组件、函数、HTTP API、模型文件和训练脚本之间如何对接；
- 开发、测试和使用时需要哪些输入、输出、环境变量与前置条件；
- 后续任务完成后，应修改哪些接口说明、状态和变更记录。

### 1.1 状态定义

| 状态 | 含义 | 对接要求 |
| --- | --- | --- |
| 已完成 | 代码已存在，主流程可运行，已有相应验证 | 可以接入，但仍应遵守接口约束 |
| 待验证 | 代码已实现，但缺少目标设备、真实数据或完整验收 | 只能试用，不应作为正式质量承诺 |
| 进行中 | 已有部分实现，接口可能变化 | 对接前确认版本和缺口 |
| 占位 | 页面、清单、模拟模型或接口骨架存在，但不具备生产能力 | 不得按正式能力上线 |
| 未完成 | 尚无可用实现 | 需要先完成设计和开发 |
| 阻塞 | 已有实现或流程，但存在明确发布阻断项 | 修复阻断项并重新验证后才能发布 |

### 1.2 信息来源与冲突处理

白皮书不是独立于代码的事实来源。审查或对接时按以下优先级确认当前事实：

1. 当前工作区实际源码、`package.json`、manifest 和文件是否存在；
2. 当前生成的机器可读审计报告；
3. 自动化测试和最近一次有记录的真机/浏览器验证；
4. 本白皮书；
5. 其他规划、历史记录和归档文档。

如果白皮书与更高优先级来源冲突，应以可复现的当前事实为准，并在同一任务内修订白皮书和开发日志。历史规划中的“已完成”不能覆盖当前审计中的 `blocked` 或文件缺失事实。

### 1.3 强制任务生命周期

每个任务都必须执行以下门禁；“任务”包括代码修改、文档修改、诊断、测试、配置、模型、数据和脚本工作。

#### 开始任务前

1. 读取 `AGENTS.md`；
2. 读取本文档，至少覆盖“功能状态总表”、任务对应模块、已知限制和最新变更记录；
3. 对照当前源码或机器可读报告确认相关状态没有过期；
4. 在开始实施前确定本次需要修改或新增的白皮书章节；
5. 若白皮书与源码冲突，先把冲突列入本次任务范围，不得继续引用错误信息。

任务第一次进度更新必须明确说明已读取白皮书，并指出本次采用的模块章节和当前状态，作为可观察的开始凭证。

#### 结束任务前（2026-10-12 v1.2.0 起分层执行）

1. 若任务改变了接口、状态、配置、数据或模型契约：更新对应模块的状态、接口、使用方式、配置、限制或验证结论，顺延白皮书头部版本号，并在当天唯一的 `dev-log/YYYY-MM-DD.md` 中以「白皮书 v1.2.x」标记简要记录变更内容与影响范围（当日多次实质变更合并记录）；
2. 纯实验迭代、审核批次、诊断等不改变上述正文内容的工作：只记录到当天唯一的 `dev-log/YYYY-MM-DD.md`（及相关进度文档），并在其中写明已复核的白皮书章节与"无接口/状态变化"结论，不修改白皮书、不顺延版本；
3. 执行文档差异检查和编码审计；行为变更还需执行相应代码测试；
4. 最终答复必须说明白皮书（或明确说明本轮无需白皮书变更及原因）和开发日志已同步；任一项未完成时不得宣称任务完成。

最终答复应点名本次修改的白皮书章节与当日日志中的版本标记（或说明无白皮书变更及原因）和当天日志文件，作为结束凭证。

涉及美甲纹理正式模型Goal的轮次形成可重放阶段结论后，必须在同一轮删除已完成或已证伪的活动目标，并把`docs/nail-texture-current-goal.md`中的“本轮活动目标”切换为下一项唯一可执行里程碑；不得只追加进度后继续沿用旧目标。纯治理说明不构成模型里程碑完成，不能为满足改写形式而伪造状态推进。

### 1.4 内容维护要求（2026-10-12 v1.2.0 起）

本白皮书只登记当前接口、状态与仍在生效的合同，不再收录实验过程叙事与逐任务变更明细：

1. 影响功能、接口、使用方式、配置、数据结构、模型契约或部署方式的任务：更新对应模块说明，必要时更新“已知限制与待办”，顺延版本号并在当日 dev-log 中以「白皮书 v1.2.x」标记简要记录（操作内容＋影响标记；哈希、字节等证据细节引用机器报告或归档，不在正文复述）；
2. 状态表“当前结论”列保持简要；过程证据与逐轮实验叙事一律进当日 dev-log、相关进度文档或归档，不写入正文；
3. 体积回归门槛：正文超过约 300KB 或状态表重新堆积历史行时，应先把历史内容迁入 `docs/archive/` 归档再继续登记；
4. 执行与风险相匹配的验证，并记录验证结论，不得把“代码存在”直接写成“生产可用”；
5. 历史实验叙事（原§12.9—§12.351）与逐条变更记录（v1.0.0—v1.1.995）完整保存在 `docs/archive/whitepaper-experiment-history.md` 与 `docs/archive/whitepaper-changelog-archive.md`，归档内容只增不改写；
6. 检索纪律：全仓 grep/批量扫描默认排除 `docs/archive/`（归档已达数MB，误命中会灌满上下文）；当前事实查本文件、`docs/nail-texture-current-goal.md` 与实施规范文档，历史证据按归档头部声明的编号指向规则查对应归档文件。

### 1.5 内容追溯与署名规则

按2026-10-11用户指示，新增或修改内容禁止添加署名或工具标记。事实追溯使用权威报告路径、SHA-256、数据角色与可重放结果；历史专项脚本的操作锚点保留，不恢复已清理标记。此规则与AGENTS一致，取代旧署名要求。

## 2. 系统概览

甲如是基于 Next.js App Router 的美甲设计与试戴应用。核心处理原则是“图片与摄像头数据默认在浏览器本地处理”；「用户改进计划」开关（默认开启，用户可随时关闭）开启时手部照片等数据可能被上传用于产品改进（当前尚无实际上传通道，见§10）。仅 AI 文生图功能始终向服务端发送文字描述（不发送原图）；v1.1.484 起 AI 页面新增可选手部参考图功能，仅在用户主动上传时该图片才随文字发送给第三方 Agnes，仅用于本次生成。

### 2.1 技术栈

| 层级 | 技术 | 当前版本/方式 |
| --- | --- | --- |
| Web 框架 | Next.js App Router | 16.3.6（源码、锁文件与安装包一致） |
| UI | React | 19.2.4 |
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS + CSS Modules | Tailwind 4 |
| 手部关键点 | MediaPipe Hands | 浏览器端运行；固定0.4.1675469240运行资源由本站`/vendor/mediapipe/hands/`同源提供 |
| 纹理模型推理 | ONNX Runtime Web | 1.27.0，WebGPU/WASM |
| 图形处理 | Canvas、OffscreenCanvas、ImageBitmap | 浏览器端 |
| 3D 依赖 | Three.js | 0.184.0，仅安装依赖，当前 `src` 未使用 |
| AI 生图 | Agnes Images HTTP API | 当前代码使用`agnes-image-2.1-flash`，依赖服务端密钥 |
| AI 生图（新引擎） | 火山方舟 Ark Images HTTP API | Seedream 5 系列：pro=`doubao-seedream-5-0-pro-260628`（已实测）、lite 档=`doubao-seedream-5-0-260128`（**已开通**，脚本端到端与路由层实测均通过），依赖服务端密钥`VOLCENGINE_ARK_API_KEY`；两个 Model ID 由`ARK_SEEDREAM_PRO_MODEL`/`ARK_SEEDREAM_LITE_MODEL`注入，源码不硬编码。 |

### 2.2 逻辑数据流

```text
图片试色：用户照片 -> 浏览器 Canvas 手工涂色 -> 本地 PNG 下载

纹理 AR：参考图 -> 浏览器纹理识别/人工裁剪 -> ImageBitmap
                                      + 摄像头 -> MediaPipe 关键点 -> Canvas AR 合成

AI 生图：文字描述（+ 可选手部参考图 Data URI）-> POST /api/generate-ai -> 外部图像 API
         （文生图：仅文字；图生图：文字 + 参考图，保持原图手部仅改指甲）-> 远程图片 URL/本地下载

AI 生图（Seedream 引擎）：文字描述（+ 可选手部参考图 Data URI）-> POST /api/generate-seedream
         -> 火山方舟 Ark /images/generations（档位×比例映射为显式 WxH）-> 远程图片 URL（24h 有效）
```

图库款式已可带入编辑器灵感色、AI参考图和AR选取器；AI生成结果可收录到浏览器IndexedDB，再由图库带入AI或AR。编辑器笔画/成品尚无共享项目协议，云端保存与跨设备同步未实现；相关链路见§4.3—§4.5。

## 3. 功能状态总表

Stage B真实训练权重的九尺寸合成完整图已通过CPU ORT/WASM/WebGPU各9/9：两头最大差6.10352e-5/6.53267e-5/6.72340e-5，解码零像素差及presence一致；完整300状态/原权重不变，见`model/reviews/cycle016-presence-stable-learned-v1/report.json`。当前仅合成接口资格，下一真实训练154保真合同已冻结要求且预算0，显式排除已消费保留8；未通过来源隔离质量、Stage A+B产品链或正式发布，PRODUCT HOLD。 当前唯一活动见Goal及§8.9/§11.1。


| 模块 | 用户入口/接口 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| 首页与统一导航 | `/` | 已完成 | 提供功能入口与统一视觉框架 |
| 消费者端新版设计提案 | 独立本机预览 `127.0.0.1:4318`，见 §4.7 | 待验证（真机与设计评审） | 最终手机／短横屏、触控模拟和Windows Chrome／Edge检查通过；原生分享与移动真机待验；旧版保留，真实模型、云同步与公开社区未接入 |
| 登录与账号原型 | `/login`、`/account`、`/api/auth/*`、`/api/me` | 进行中（生产闭环未完成） | 已有JWT/SQLite、手机号/微信身份与偏好接口；生图路由身份与配额/预算熔断、SQLite目录预检已由v1.1.649修复（见§5更正段）；剩余缺口为真实短信、refresh入口及身份一致性/验证码治理。详见§5补充及§9.7。 |
| 灵感图库 | `/gallery` | AI 素材 + 编辑器灵感参数消费 + 图库→AR/AI 链路打通 + 本地收录（2026-09-03，v1.1.580/581/583） | 6 张 Seedream pro 文生图素材本地落盘 `public/nail-gallery/ai-look-1..6.jpg` 并逐张通过视觉审核；`/editor?gallery=` 已实现灵感卡 + 灵感色预涂（v1.1.581，见 §4.3）；v1.1.583 起图库卡片新增「AI 相似款」(`/ai-generate?gallery=<id>`) 与「AR 试戴」(`/ar-tryon?gallery=<id>`) 入口，图库款式到 AR 的纹理传递已打通（§4.5）；AI 生成结果可一键收录到浏览器本地 IndexedDB 图库（`/gallery`「我的收录」区块，§4.3），真实内容后端与跨设备同步仍无 |
| 图片试色编辑器 | `/editor` | 已完成 | 本地上传、MIME/大小/分辨率/解码校验、逐指选色、Canvas 涂抹与本地保存链路均已实现并通过浏览器审核 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 已完成（用户验收） | 已接入Agnes Image 2.1 Flash（文生图 + 图生图）；2026-08-29服务端Endpoint已切换为`https://api.agnes-ai.cn/v1/images/generations`并换用新服务端密钥，实测模型列表`GET /v1/models`认证HTTP 200、目标模型`agnes-image-2.1-flash`可见，真实文生图返回图片URL且产物可下载。`.cn`模型列表认证HTTP 200且目标模型可见，协议专项测试、Lint、全量758项测试和生产构建通过。2026-08-10用户确认AI美甲真实生图功能验证通过，并于2026-08-12再次确认；2026-08-19新增可选「参考图」图生图（上传手部照片→浏览器压缩至最长边1024 JPEG→与提示词一起生成，Agnes在参考图手部指甲上绘制美甲并保持原图构图，实测图生图成功且约12s，文生图约157s），并新增生成中 shimmer 加载与页面过渡动画；2026-08-29新增用户可选择**画面比例**（8 种）与**输出尺寸档位**（1K/2K/3K/4K），按 Agnes「输出尺寸参考」表实时显示最终像素尺寸，文生图与图生图共用（默认 1K+1:1 ≈ 1024x1024，行为与历史一致）。参考图仅在用户主动上传时发送第三方、仅用于本次生成；成本、内容安全和生产持续可用性继续作为运营监测项 |
| AI 美甲生图（Seedream 引擎） | `/ai-generate`（引擎切换）、`POST /api/generate-seedream` | 待验证（路由层 lite 实测通过；pro 脚本端到端通过；仅剩浏览器视觉呈现等待用户确认） | v1.1.564 新增火山方舟 Seedream 5 系列作为第二生图引擎，Agnes 保持默认且链路零改动。新增`src/lib/seedream-image-api.ts`（扁平 body、顶层`error{code,message}`解析、429/500/503 指数退避重试、240s 超时、`watermark`默认关）、`seedream-image-size.ts`（pro=1K/1.5K/2K、lite=2K/3K/4K 档位×8 比例→显式 WxH 表）与`seedream-prompt.ts`（Seedream 专用精简系统词约 100 字，独立于 Agnes 长提示词；用户提示词上限 300 字）。前端`/ai-generate`新增「生成引擎」切换（Agnes / Seedream pro / Seedream lite），切引擎联动尺寸档位与提示词上限。真实端到端：pro 引擎经`doubao-seedream-5-0-pro-260628`文生图 19.7s 成功返回 186KB 有效 JPEG；v1.1.577 更换用户临时 Key 后 pro 复测 28.5s 成功、lite 档`doubao-seedream-5-0-260128` 33.1s 成功返回 249KB 有效 JPEG（该账号已开通，此前"has not activated"阻塞解除）。v1.1.578 修复路由层 `env` 缺省导致的 watermark 读取崩溃（`Cannot read properties of undefined (reading 'ARK_IMAGE_WATERMARK')`），`generateSeedreamImage` 入口统一 `env = options.env ?? process.env`，新增"不传 env 的成功路径"回归测试；v1.1.579 通过 curl 实测本机 `POST /api/generate-seedream`（lite 2K 1:1）HTTP 200、27.1s 返回有效 imageUrl，确认修复已被 dev 服务器 hot-reload 加载。模型 ID 经`GET /api/v3/models`实测发现（必须带版本日期后缀）。新增 18 项测试全过（v1.1.578 增 1）、路由校验冒烟 6/6 通过；仅剩浏览器视觉呈现由用户确认。生成 URL 24h 过期，项目不做长期留存 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 单手摄像头、关键点、指甲绘制、手心/手背识别已实现；MediaPipe运行文件使用本站同源静态资源，实时路径启用`modelComplexity: 1`。甲面几何结合TIP/DIP/PIP、深度和手背平面生成长轴、横轴及侧转透视剪切，工程回归通过；真实边界仍需多设备真机验收 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | 上传含完整手背的参考图时优先通过MediaPipe Hands逐指定位；完整手部关键点失败后，局部近景先用甲色连通域定位黑色、彩色、银色和镜面甲；甲面为裸色/半透明且被肤色种子吞掉时，再以闭合甲缘、甲板内部/肤色邻环和4—5枚同手连续链复合定位，仍失败才进入人工补选。两条辅助路径均没有像素级mask，低对比边界候选固定低置信并要求用户检查；实时AR支持拇/食/中/无/小指各自独立的长度75%—140%、宽度70%—145%及甲尖/指根位置±20%校准，摄像头最终贴合仍需多设备真机验收 |
| 独立 AR 演示桥接 | `/ar-demo` | 占位 | 仅将本机 `http://localhost:8080/?embedded=jiaru-main` 临时嵌入 iframe，要求用户另行启动 Python demo；不是生产 AR 服务，部署环境不能依赖该地址 |
| 视频自适应展示 | `calculateCoverVideoLayout()` | 已完成 | 保持比例，采用居中 cover 裁切，不拉伸 |
| 个性化美甲分析推荐 | `/nail-analysis` | 待验证（工程门通过；真实照片与真机验收待补） | 纯规则启发式，不引入新模型训练：浏览器本地完成甲面候选识别、甲床/手型派生比例、甲周肤色采样（Lab/ITA°/底调，含甲面自污染排除与采样质量门）、指甲健康三类启发式，结合场景问卷由确定性规则引擎推荐甲型、长度与色系并附中文解释，可一键跳转 `/editor?preset=` 预涂。全部本地计算，不新增上传通道；即使开启「用户改进计划」分析结果也不外发。正式模型未部署期间识别100%走辅助定位且无像素级mask，指甲健康通道不可用（隐藏而非降级展示），琥珀辅助声明页面级常显，不得表述为自动分析成功，也不计入正式识别成功率或Beta直接可用率；0候选时不产出任何推荐。设计文档：`docs/nail-personalization-design.md`、`docs/nail-personalization-research.md`。 |
| 美甲纹理自动识别 | `/ar-tryon`图片纹理识别 | 研发进行中 / PRODUCT HOLD | Stage B学得图九尺寸CPU/WASM/WebGPU各9/9；下一真实训练154保真，正式来源质量及产品链仍缺，见§8.9/§11.1。 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()`、`NailArtPicker` | 已实现（辅助定位提示；正式模型HOLD） | 所有fallback候选数均显示琥珀色辅助定位/人工确认提示，0候选提示手工添加；未部署标记在window/worker会话创建前返回明确warning。MediaPipe/局部近景无像素级mask，不计模型成功或Beta直接可用率。行为及发布拦截本地独立测试通过，真实浏览器产品路径待验收。 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 阻塞（无批准生产模型） | 生产manifest仍无批准ONNX或新releaseIdentity，正式训练准入v7及新来源val/正负留出、角标捷径消融、生产运行时/产品、真机/Beta与双批准权重回滚均未闭合。当前内部val诊断质量/数值未过且有上游训练历史，禁止据此正式校准、登记或部署。candidate57受保护test100失败保持，历史测试部署例外不构成正式发布；当前证据与下一路线见§11.1、Goal及当日日志。 |
| 数据集治理 | `model/datasets/nail-texture-v1`及候选物化报告 | 进行中（发布角色需重建） | 仓库历史基础数据集仍为409图/2142 mask、split=300/46/63；正式训练输入已演进三代：candidate52/56（328张正图/1981 mask/112来源组加160张train困难负样本，物化train488/val30/test0）→ candidate58b（343张/2071 mask/127来源组，train503）→ 循环011/012开发口径（唯一一次12 epoch训练为循环012，350图训练文件树`34fe0a85…1edf`、124来源组均衡采样）。train内来源组开发折已由循环001—015落地为现行评估主线，clean98开发基线（58图/354-mask v2加40困难负图）与循环015扩容（源图供给55图/55来源组/322甲冻结、开发评估真值43图/265甲、训练禁用）为当前事实；旧val30、旧test100及编号261—360、361—460等已消费holdout现在只作受保护历史回归，禁止训练、配方/阈值选择或再次冒充未见证据；候选锁定后的全新校准集、一次性正样本发布留出与全新困难负样本要求保持不变；当前无批准发布候选。 |
| 验证真值当前快照 | 外部`val-annotation-workspace-v1/validation-truth-index-v1.json` | 已完成 | v1.1.189：30个批准报告归并为30张唯一图片/144个完整mask、0拒绝、0冗余、0冲突，索引SHA-256为`2ccde9420141e5e67a9696959cc18e78aaee808ba29b592670990967bdc4b92d`。批次014—018严格排除裁断、遮挡或甲数错误源图，透明甲尖和全部附着装饰均经整图与逐甲2×复核；所有polygon合法且同图严格零交叠。规范val-only数据集物化为30图/30 annotation/30 label/144 mask、train/test均0、孤儿0，物化报告SHA-256为`200b087b…b1776`。来源隔离审计对当前train 100张和冻结test 67张重新读取、复算身份，文件名、图片SHA-256和来源组均零重叠，报告SHA-256为`7372d14d…f6479e`。最终审计SHA-256为`5152dc52…66a3a`，决定`approved_as_calibration_truth`、`calibrationTruthEligible=true`，同时保持`trainingUse=prohibited` |
| 规范候选训练数据与输入门 | `finalize-reviewed-hard-negative-manifest.py`、`materialize-canonical-candidate-training-dataset.py`、`audit-candidate-training-input.py`、`train-yolo-seg.py --candidate-mode` | 已完成（第二候选输入PASS） | 固定正式下限为train正样本100、正式hard negative 100、val30且CLI不得下调。第二候选包为train258（100张正样本/521 mask + 158张零字节标签困难负样本）、val30/144 mask、test0、孤儿0，物化与输入深审分别为`033b8d02…2ec`和`b9bd6897…94dd`，文件树SHA-256为`8709fa80…1170`。GPU训练前后均重放通过，Ultralytics缓存仅出现在隔离runtime并已清理；输入PASS只授权本次候选训练，不授权模型发布 |
| 候选三路训练发布编排 | `run-training-release-pipeline.ts --candidate-mode`、`verify-training-release.ts --candidate-mode` | 进行中（candidate5发布拒绝） | candidate5已完成隔离训练、规范val30、冻结test100和训练后新100张独立留出全链；独立留出三变体未通过零误检/零delta门，因此终止导出与登记。下一候选必须使用与编号361—460留出隔离且另获商业训练授权的新训练负样本，训练后再建立另一份全新未见独立留出；不得复用或按本次模型输出缩减当前清单 |
| 移动真机基准与证据门 | `/device-benchmark`、`build-nail-texture-mobile-memory-raw.ts`、`build-nail-texture-device-acceptance.ts` | 已完成（工程门） | 真机页固定3次预热+20次正式推理，导出同一session/device/model/backend/input身份；fallback、混合身份和少样本不能晋级。Android Profiler/iOS Instruments内存CSV经会话与源SHA绑定后进入内存验证；设备验收v2和最终完成度审计均深度重算性能样本、原始内存、统计、路径及哈希，拒绝伪造外层PASS、跨session和写后漂移。2026-07-28复核本机ADB可用但未连接任何设备，PnP未发现移动设备，`idevice_id`不可用且四份真机报告均不存在，因此`M3-T3-DEVICE`继续PARTIAL |
| 训练/评估/导出 | `model/training/*` | 进行中（candidate8拒绝，准备下一轮数据） | nano分支早停于epoch23、最佳epoch3；val30阈值0.55通过后一次性冻结test100逐实例门失败。高容量分支早停于epoch51，最佳权重`2be3104e…6081`，仅用val30比较时阈值0.60召回0.76389，低于nano的0.80556，故不运行test。下一步以新来源完整甲面真值提升召回；继续禁止ONNX导出、登记和部署。 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门、逐图失败画像、规范val30阈值深审、三路候选编排、最终完成度审计和外部验收证据构建器。独立留出链固定100张下限、训练用途禁止、权重/阈值绑定、首次推理账本、512输入、确定性三变体和推理重放。首个正式发布采用“双批准版本”启动：先以`--set-current false`登记独立通过全部发布门的fallback，再激活另一个不同版本；仍需两个版本全部manifest/模型字节完整且至少一个非当前候选，禁止synthetic/smoke或已拒绝模型充当回滚。真实candidate4独立留出3/2/3张误检仍按预期HOLD；当前没有合格生产资产 |
| 隐私说明 | `/privacy` | 已完成（产品文案；法律合规审核仍待外部） | 静态说明页覆盖核心原则（本地优先/数据由你掌控/不追踪）、「用户改进计划」开关（客户端组件，默认开启，可随时关闭，状态存 localStorage）、各功能数据流向（试色默认本地、AI生图仅文字并经第三方Agnes、AR默认内存处理不录制、识别与图库本地）、第三方与用户权利；v1.1.470 已将“不上传照片”承诺修订为改进计划模式；当前尚无实际上传通道，开关为偏好记录；法律/产品合规审计不构成 |
| 用户账户（注册/登录） | `/login`、`/account`、`/api/auth/*`、`/api/me` | 进行中（Phase 1 初始注册登录已实现；商户/云同步未开始） | v1.1.475 已落地初始注册登录功能：手机号+验证码「登录即注册」，自研 HS256 JWT（access 2h + refresh 30d）+ SQLite 会话表（可踢下线）；`/api/me` 档案与登录方式管理（查看/解绑，至少保留一种）、账号级「用户改进计划」偏好（§5.6 联动 localStorage）。v1.1.476 起发送短信验证码前必须通过人机验证（自研 SVG 图形验证码 `GET /api/auth/captcha`，5 分钟有效、一次性、错 5 次作废、60 秒节流保持不变）。v1.1.477 起按用户要求仅保留**手机号 + 微信**两种登录：新增微信 OAuth 全流程（`GET /api/auth/oauth/wechat` 授权跳转 + `/callback` 回调登录，state 存 httpOnly Cookie 防 CSRF，code 换 openid，首次登录须在 `/account` 补绑手机号，`/status` 探测配置），**邮箱与 GitHub 登录入口已移除**（email-register 路由删除、bcryptjs 依赖卸载、/login 页邮箱 tab 与 GitHub 占位按钮删除、/account 新增「绑定手机号」卡片含人机验证）。微信登录需 `WECHAT_APP_ID`/`WECHAT_APP_SECRET`（开放平台企业认证，300 元/年），未配置时按钮显示「未配置」、接口返回 503。数据库为本地 SQLite（Node 内置 node:sqlite，路径 `data/jiaru-user.db`），生产换 Postgres 时仅替换 `src/lib/auth/db.ts` 边界。短信验证码在未配置服务商时进入开发模式（接口返回 devCode 仅供本地联调），生产须配置短信服务商。完整设计见 `docs/user-system-plan.md`（v0.2，Phase 1 目标）；商户体系、云端作品/收藏/历史/色板、配额、注销导出、游客数据合并仍为后续 Phase 1 项 |

## 4. 页面与用户使用接口

### 4.1 启动与访问

```powershell
cd "E:\AI Project\Codex\JiaRu"
npm.cmd install
npm.cmd run dev
```

默认访问 `https://localhost:3000`。开发脚本使用 `next dev --experimental-https`；若本机自签名证书生成失败，Next.js 可能回退至 HTTP。摄像头应通过 `localhost` 或正式 HTTPS 域名访问，不应使用普通局域网 HTTP 地址。

生产启动应先执行 `npm.cmd run build`，再执行 `npm.cmd run start`。开发模式的实验性自签名 HTTPS 不等同正式部署证书。

云端生产部署形态（2026-10-04 实测）：腾讯云轻量服务器 `lhins-1oklqsh2`（ap-beijing-7，公网 `49.233.141.42`）上，Next.js 以 `next start -H 127.0.0.1 -p 3000` 只监听本机，由 Nginx（`deploy/nginx/jiaru.conf` + `jiaru-proxy.conf`）终结 80 端口并反向代理，**3000 端口不得直接暴露公网**；应用层设 `JIARU_TRUST_PROXY=1` 后采信 `X-Real-IP`/最右 XFF 用于限流与来源推导，写操作由 `src/middleware.ts` 校验 `Origin`。此前遗留的 iptables 80→3000 REDIRECT 会绕过 Nginx 使反代形同虚设，已移除并停用 `jiaru-port80.service`。该地址为 HTTP，非安全上下文，`getUserMedia` 不可用，AR 摄像头仍需 HTTPS 域名或本机隧道演示。

生产验证命令：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

### 4.2 `/editor` 图片试色

状态：已完成。

2026-09-05复核发现两个待修缺陷：`NailCanvas`直接导出≤400×600的预览画布，4096方图保存为400方图；20份撤销历史淘汰原图后，“重置”回到最旧编辑状态。已有上传/涂抹链路可用不代表原分辨率导出与长历史重置正确，本轮只登记，未改运行代码。

更正（v1.1.658）：上述两项缺陷已于本日修复——①`NailCanvas` 改为笔级笔画记录＋预览/导出分离：预览画布最长边仍受 400×600 约束，保存时按原图尺寸离屏重放原图与全部笔画（点坐标与笔刷半径按预览/原图缩放比等比换算），4096 方图导出 4096 方图；②「重置」改为清空笔画重放＝原图基线（与撤销栈解耦），修复 20 份快照淘汰后重置回最旧编辑状态的问题，撤销同时不再有 20 步上限。共用纯逻辑模块 `src/lib/canvas/strokes.ts`。

使用方式：

1. 上传或拍摄清晰的手部图片；文件选择器与运行时均限制为 JPG/PNG/WebP、最大 10 MB、宽高各 320–4096 像素；
2. 选择拇指至小指之一；
3. 选择颜色，可将当前颜色应用到全部手指；
4. 在 Canvas 上点击或拖动完成局部涂色；
5. 使用组件提供的撤销、重置和保存能力。

数据边界：上传校验在浏览器本地完成；通过后才调用 `URL.createObjectURL()`，页面卸载或更换文件时释放对象 URL。无效 MIME、超限大小、解码失败、过小或过大分辨率会在上传区显示可读错误，不创建编辑会话。

核心组件接口：

```ts
<UploadButton onUpload={(file: File) => void | Promise<void>} />

<NailCanvas
  imageUrl={string}
  selectedColor={string | undefined}
  nailColors={string[] | undefined}
  activeFinger={number | undefined}
  brushSize={number}
/>

<ColorPalette
  selectedColor={string}
  onSelectColor={(color: string) => void}
/>
```

### 4.3 `/gallery` 灵感图库

状态：已完成（2026-09-03，v1.1.580/581/583）。

当前使用 `src/lib/utils.ts` 中的 `GALLERY_IMAGES` 和 `public/nail-gallery/ai-look-1..6.jpg`。这 6 张素材由本项目 Seedream pro 引擎（`doubao-seedream-5-0-pro-260628`，经 `POST /api/generate-seedream`，`ratio:"1:1"`+`size:"1K"`=1024x1024 文生图）于 2026-09-03 生成（v1.1.580），对应款式渐变裸粉/法式白边/亮片闪粉/简约纯色/复古花纹/宝石镶嵌，逐张下载落盘为本地静态资源（165—221KB 有效 JPEG，不依赖 Ark 生成 URL 的 24h 有效期），并逐张通过原分辨率视觉审核（≤2 手、五指无畸形、款式与名称对应）。素材为演示用途的 AI 生成图，不代表真实商品款式，也没有真实素材授权链；旧 `placeholder-*.svg` 仍保留在目录中但不再被引用。卡片三个入口：①点击「试色」跳 `/editor?gallery=<id>`（v1.1.581 起被消费，编辑器以 Suspense 包裹的 `useSearchParams` 解析，空态渲染「灵感款式」参考卡 + 灵感色预涂，逻辑见 `src/lib/gallery-inspiration.ts`，灵感色为整图采样启发式推导不等于真实甲油色）；②「AI 相似款」跳 `/ai-generate?gallery=<id>`；③「AR 试戴」跳 `/ar-tryon?gallery=<id>`（v1.1.583，见 §4.5）。

**v1.1.583 新增：图库→AR/AI 链路打通与本地收录（IndexedDB）。**
- 桥接函数 `src/lib/gallery-bridge.ts`：`findGalleryLook(id)` 校验 id；`loadGalleryReference(id)` / `loadCollectReference(collectId)` / `loadReferenceFromParams({gallery, collect})` 把图库静态图或 IndexedDB 收录图取为 `File`（fetch 失败、非 2xx、非图片类型一律降级返回 null，不抛错）。
- AI 相似款（`/ai-generate?gallery=<id>` 或 `?collect=<id>`，v1.1.583）：`src/app/ai-generate/page.tsx` 以 Suspense 包裹的 `useSearchParams` 消费参数（与 v1.1.581 同一约定），进入后自动 `fetch` 图库图、`createImageBitmap` → 复用 `compressReferenceImage` 同源压缩链路填入参考图（与手动上传代码完全一致），并以款式名预填提示词（如「参考「亮片闪粉」的美甲样式，生成同风格的新设计」）；任何失败静默降级，不阻塞手动上传主流程。
- 图库到 AR 的纹理传递（§11.3 第 7 条已改写）：`/ar-tryon?gallery=<id>` 或 `?collect=<id>` 进入后自动取图、复用编辑器/AR 共用的 `validateImageUpload` + `URL.createObjectURL` 管线，直接打开多指指甲选取器（`setShowNailPicker(true)`）；失败降级不阻塞手动上传。编辑器涂抹纹理链路仍无。
- **AI 生成结果一键收录**：`src/lib/gallery-collection.ts` 为原生 IndexedDB 轻量封装（库名 `jiaru-gallery`、store `collects`、keyPath `id`），`addCollect`/`listCollects`（按 createdAt 降序）/`deleteCollect`/`clearCollects`，所有函数对 `typeof indexedDB === "undefined"` 安全降级为 no-op（SSR 不抛错）；浏览器冒烟验证通过 `fake-indexeddb` 之外的 headless Chrome 实际写入。AI 生图结果区「收录到图库」按钮先 `fetch(imageUrl)` 取 blob（跨域受限时降级提示「先保存到本地再手动上传参考图」）再 `addCollect(blob, {engine, prompt})`。`/gallery` 卡片网格下方「我的收录」区块首屏不渲染、客户端 `useEffect` 读取 IndexedDB 后异步追加，避免 SSR 水合错位；收录卡带「我的收录」徽标、删除单条与「清空全部」入口，且同样具备「AI 相似款」(`/ai-generate?collect=<id>`) 与「AR 试戴」(`/ar-tryon?collect=<id>`) 入口；blob 的 objectURL 在卸载与删除时 `revokeObjectURL`。

当前没有服务端数据库/上传管理/分页/搜索/跨设备同步。后续接入真实图库时应至少补充：资源 ID、来源授权、缩略图、原图、可试戴纹理、标签、创建时间、审核状态和删除策略。

### 4.4 `/ai-generate` AI 生图

状态：已完成（2026-08-10用户真实功能验收通过）。

使用方式：输入 1～520 字符描述，或选择预设风格按钮随机填入该风格的一段提示词，点击生成；成功后前端显示外部服务返回的远程图片 URL，并尝试跨域下载，失败时在新窗口打开图片。**输出尺寸与画面比例（v1.1.542，参考 Agnes Image 2.1 Flash「输出尺寸参考」表）**：用户可选**画面比例**（1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9，默认 1:1）与**输出尺寸档位**（1K/2K/3K/4K，默认 1K），页面实时显示最终像素尺寸（如 2K+16:9 → `2624x1472`）；文生图与图生图共用该选择，定义见 `src/lib/ai-image-size.ts`（`AI_IMAGE_SIZE_TABLE`）。**参考图（可选）**：可上传手部照片（浏览器端校验 MIME/≤10MB，canvas 压缩至最长边 1024 的 JPEG，上传时按原图比例就近选中画面比例，用户随后可在「画面比例」选择器中覆盖），上传后请求携带 `image`（Data URI）、`ratio` 与 `size`，服务端走图生图组装并启用**第二套图生图系统提示词**（`IMAGE_EDIT_SYSTEM_PROMPT`，与文生图系统提示词完全独立）：以参考图为唯一底图做局部编辑，唯一允许修改的区域是指甲，手部数量/姿势/动作、皮肤纹理与肤色、服装配饰、背景场景、光线构图等一切细节原样保留，禁止整体风格重绘，并保留手部解剖负面约束防止重绘缺陷；Agnes 在参考图手部指甲上直接绘制美甲样式（实测图生图约 12—41s，远快于文生图约 157s）；不上传则行为与历史文生图完全一致。参考图仅在用户主动上传时发送给第三方 Agnes，仅用于本次生成、不用于训练或存储。生成期间（loading 状态）右侧图像展示区不新增外框卡片：白色 shimmer 光带直接扫过整个展示区背景（光带限定在展示区内，由展示区 section 自身 `overflow-hidden` 裁剪，不会溢出到左侧提示词输入区；光带 80% 宽、峰值透明度 0.55、3.6s 周期并带 0.9s 淡入出现，适配 `prefers-reduced-motion` 时停用动画），中央沿用空闲态图标卡样式显示微光呼吸的 SVG 火花矢量图标（`src/components/Icon.tsx` 的 `sparkles`，v1.1.488 起全站 emoji 统一替换为内联 SVG 矢量图标）与「正在凝聚你的灵感…」文案；页面进入与空闲/加载/成功/失败四态切换均带柔和淡入上移过渡（`fade-in-up` 0.45s、页面级 0.65s），无接口变化。前端只向本项目 API 发送文字与（可选的）参考图。

**图库灵感自动带入（v1.1.583）**：从灵感图库「AI 相似款」入口进入时带 `?gallery=<id>`（或「我的收录」带 `?collect=<id>`），页面以 Suspense 包裹的 `useSearchParams` 消费参数，自动 `fetch` 图库图/`createImageBitmap` 复用同源压缩链路填入参考图，并以款式名预填提示词；任何失败静默降级，不阻塞手动上传主流程。生成成功后结果区「收录到图库」按钮把图片 `fetch` 为 blob 写入浏览器本地 IndexedDB（库名 `jiaru-gallery`，见 §4.3 与 `src/lib/gallery-collection.ts`），跨域受限导致 fetch 失败时降级提示「先保存到本地再手动上传参考图」；该收录不离开本机、不经任何服务端，可在 `/gallery`「我的收录」区块查看与删除。

**生成引擎（v1.1.564，Seedream 5 半分离接入）**：页面顶部新增「生成引擎」切换（Agnes 默认 / Seedream pro / Seedream lite），Agnes 链路与行为完全不变。选择 Seedream 引擎时：①尺寸档位切换为该模型的合法档位（pro=1K/1.5K/2K，lite=2K/3K/4K，默认 2K），与 8 种画面比例组合实时映射为显式像素尺寸（如 pro 2K+21:9 → `3136x1344`）；②提示词输入上限由 520 收紧为 300 字符（对齐 Ark 文档建议），计数器同步变化；③请求改发 `POST /api/generate-seedream`（契约见 §5.2），服务端组装 Seedream 专用精简系统词（`SEEDREAM_T2I_SYSTEM_PROMPT`/`SEEDREAM_I2I_SYSTEM_PROMPT`，约 100 字，独立于 Agnes 两套长系统提示词，二者互不复用）。参考图上传、压缩与图生图交互与 Agnes 一致。切引擎会重置尺寸档位为该引擎默认值。

风格提示词库：`src/lib/ai-style-prompts.ts` 导出 `AI_STYLE_PROMPTS`，包含 10 个风格（甜美风、欧美风、日系、极简、复古、节日、水墨、几何、花草、金属），每个风格 50 段独立的中文场景提示词。用户每次点击风格按钮时，从该风格的 50 段提示词中随机抽取一段填入输入框（各风格独立随机，并避免连续两次抽到同一段；刷新页面后首次点击同样是随机结果）。提示词描述了底色、装饰、甲型、手持道具、光线、背景和皮肤质感等完整场景。`src/lib/utils.ts` 中原有的 `AI_STYLES` 字符串数组仍保留以维持向后兼容，但 `/ai-generate` 页面已改为从 `AI_STYLE_PROMPTS` 读取。

前置条件：

```env
AGNES_API_KEY=有效的服务端密钥
AGNES_API_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_IMAGE_MODEL=agnes-image-2.1-flash
```

当前服务端按Agnes Image 2.1 Flash协议请求`POST {AGNES_API_BASE_URL}/images/generations`，按用户选择的**尺寸档位**（`size`，1K/2K/3K/4K，默认 1K）与**画面比例**（`ratio`，默认 1:1）组合决定输出尺寸（默认即 `1024x1024`，由`size:"1K"`+`ratio:"1:1"`得到，行为与历史一致），并将`response_format: "url"`置于`extra_body`。总超时为180秒；503最多按1/2/4秒退避后重试，401、429及供应商异常保持结构化错误响应。基础地址与模型ID可由服务端环境变量覆盖；本机用户配置当前使用`https://api.agnes-ai.cn/v1`（2026-08-29由`https://apihub.agnes-ai.cn/v1`切换并换用新服务端密钥），其`GET /models`认证返回HTTP 200并列出目标模型，`/v1/images/generations`真实文生图返回图片URL且产物可下载。2026-08-10用户确认AI美甲真实生图功能已经验证通过，并于2026-08-12再次确认；该验收证明当前交互链路可用，不代表供应商长期可用性、成本或内容安全无需继续监测。AI输出可一键收录到本地图库，再由图库带入AI或AR；编辑器尚无直接消费生成成品的共享项目协议，见§4.3。

### 4.5 `/ar-tryon` AR 试戴

状态：待验证。

使用方式：

1. 选择“纯色”或“纹理”；
2. 纯色模式可逐指选色或应用全部；
3. 纹理模式可上传单个纹理手动裁剪，也可上传参考图提取多个甲面；正式自动模型可用时展示模型候选，模型不可用时先用MediaPipe Hands从完整手背照片自动生成五指甲面区域；若完整手部关键点失败，再对含2—5枚清晰已上色甲面的局部近景执行保守定位；两级辅助定位均无可靠结果时才进入“在图片上添加甲面”模式；
4. 点击画面内唯一的“开启摄像头”按钮；该次点击会直接调用摄像头权限请求，不需要再点第二个启动按钮；
5. 将手放入画面并展示手背，系统根据手部关键点绘制指甲；
6. 手心、手背或不确定状态会显示对应提示，手心状态不绘制指甲纹理。

上传约束：PNG/JPEG/WebP，最大 10 MB，宽高各 320–4096 像素，并要求浏览器可成功解码；编辑器与AR共用同一校验器。摄像头画面默认只在内存中处理，不录制；「用户改进计划」开启时手部数据可能被上传（见§10，当前尚无实际上传通道）。

**图库灵感自动带入纹理（v1.1.583）**：从灵感图库「AR 试戴」入口进入时带 `?gallery=<id>`（或「我的收录」带 `?collect=<id>`），页面以 Suspense 包裹的 `useSearchParams` 消费参数，自动 `fetch` 图库图、复用编辑器/AR 共用的 `validateImageUpload` + `URL.createObjectURL` 管线后直接打开多指指甲选取器（`setShowNailPicker(true)`），用户即可在图中五指上分配甲面纹理；任何失败静默降级，不阻塞手动上传主流程。这是 §11.3 第 7 条原「图库款式到 AR 的纹理传递」的落地。

2026-07-30 安全降级修复：默认正式manifest指向的ONNX仍不存在，且candidate5已被发布质量门拒绝，不能为恢复功能而部署该权重。此前模型初始化失败后，弹窗会把衣袖等saliency候选显示为“高置信度”，造成用户无法可靠提取甲面。本次将所有规则候选统一降为低置信度，并在`NailArtPicker`正式流程中隐藏它们，只保留在诊断JSON；回退后区域数从0开始并自动开启人工添加。人工区域按首个空闲手指顺序分配，支持画布点击新增、拖动定位、方向/角度/长宽微调和删除，提取时以椭圆裁剪并令区域外像素透明。弹窗、统计、告警、区域、质量、调整、手指分配和按钮文案均改为中文；`/ar-tryon`遗留的“Live Try-on”“Style controls”也已中文化。真实浏览器使用用户提供图片完成上传、添加、拖动、提取并回填“拇指纹理”，控制台0错误。该修复恢复的是安全可用的人工提取路径，不代表自动美甲识别已发布或通过质量门。

2026-07-30 自动定位与AR贴合修复：新增`nail-hand-geometry-detection.ts`，在正式模型回退后动态加载项目既有`@mediapipe/hands`，对上传的完整手背照片执行一次本地关键点检测；明确手心图会拒绝，严重弯折手指会过滤，其余候选按拇指至小指生成中/低置信几何区域并自动绑定手指。规则saliency候选仍不会回到正式UI。使用用户本轮截图在真实浏览器中自动得到5/5区域、5/5分配，无手动框选即可一次提取，控制台0错误；首轮模型及WASM资源加载约8.3秒。该路径从jsDelivr下载MediaPipe程序/模型资源，但上传图片像素只在浏览器本地处理。实时AR的TIP→DIP比例由旧的约0.48—0.58长度、0.36—0.52宽度校正为0.64—0.74长度、0.45—0.62宽度，并在控制面板增加大小75%—140%及甲尖/指根位置±20%滑杆和恢复默认按钮。自动化环境无法提供用户真实摄像头，本轮以几何单元测试、控制交互和生产构建作为工程验证，最终视觉贴合仍保留多设备真机门。

2026-07-30 同源资源修复：用户现场截图明确出现“手部关键点自动定位加载失败”，耗时约0.5秒，证明失败发生在检测前的外部资源加载。新增`mediapipe-hands-assets.ts`并把锁定npm依赖中的`hands.js`、TFLite、graph、packed assets及SIMD/普通WASM复制到`public/vendor/mediapipe/hands/`；静态图片定位和实时AR统一用`resolveMediaPipeHandsAsset()`从本站加载，供应商目录排除ESLint但由资源存在性测试守护。真实浏览器主动阻断`cdn.jsdelivr.net`后，本站TFLite、graph、packed data及SIMD WASM均HTTP 200；上传从用户既有AR截图取得的完整手部画面后约1.66秒自动得到5/5区域、5/5分配并完成一次提取，控制台0错误。用户本轮提交的是包含整套界面的截图而非原始上传文件；该截图只用于确认加载故障，不用于宣称其中局部近景满足完整手部检测门。

2026-07-30 局部近景自动定位修复：用户新截图证明同源资源已经加载，但MediaPipe对袖口遮挡、手指弯曲且只露出4枚甲面的近景返回“无完整手部”，原流程因而错误地直接进入人工添加。新增`nail-partial-closeup-detection.ts`，只在正式模型fallback且MediaPipe没有可用区域时分析最长边480像素的本地副本；候选必须同时通过连通面积、长宽比、填充率、甲色亮度/方差和平滑皮肤邻接门，全图不足2个候选时整条路径拒绝展示，最多返回5个`source: "partial-closeup"`低置信椭圆并自动分配。规则saliency候选继续隐藏。真实浏览器上传从本轮截图按原显示区域裁出的参考图后，自动得到4/4个可见甲面、已分配4、袖口0候选，一次点击完成四纹理提取并回填试戴设置，控制台0错误；该证据只覆盖这类清晰已上色局部近景，不覆盖透明、裸色、极小、单甲或高度反光甲面。

2026-07-30 五甲完整性与提示降噪修复：后续用户截图含5枚清晰甲面，但旧局部检测只返回2枚；机器复算确认亮银/复杂装饰甲面被0.40填充率门误删，拇指被0.36平滑皮肤邻接门误删，且全局按分数截取会让远处背景占用最多5个名额。本次将填充率与邻接门调整为0.32/0.30，在截取前按最长边32%距离建立候选空间连通簇，只保留候选数最多、同数时总分最高的一簇，并拒绝接触图像边缘的连通域；同簇4—5枚标为中置信“已定位”，2—3枚仍保持低置信。真实浏览器上传从用户界面截图按原显示区域取得的724×960裁片后，得到区域5、已分配5，五枚实际甲面均被覆盖、远端背景和底部边缘物体未进入候选，控制台0错误。局部路径成功后，模型/Worker/MediaPipe基础设施告警仍保留在诊断JSON，但不再向用户重复展示；界面改为明确的“已自动定位5个甲面”结果提示。裁片含上一轮界面叠加的两个既有椭圆，因此该证据用于验证漏检回归与候选排斥，不冒充用户原始文件的无叠加终审。

2026-07-30 银色/镜面甲面稳定性修复：用户在v1.1.268后重新上传同一类五甲照片，实际页面仍只有3/5，证明上一轮截图裁片5/5没有覆盖原始文件的色彩差异。对本轮截图显示区域做受控变体复现后，饱和度降低会从5枚降为3枚，亮度提高12%会降为0—4枚；根因是固定“灰度低于172且足够暗或饱和”的前景门会把低饱和银色和镜面高光切成多个碎片。局部路径改为先保留“非皮肤且灰度低于225”的连续区域，让银色高光参与完整甲面连通，再继续使用面积、形状、填充率、纹理方差、平滑皮肤邻接、贴边拒绝和同手空间簇排除背景；平滑皮肤邻接下限由0.30调整为0.24，以兼容高亮造成的局部皮肤边缘增强。当前截图裁片的原色、低饱和、提亮、变暗、模糊及JPEG压缩8种机器变体均为5个实际甲面；真实浏览器对原先3/5的低饱和变体和提亮变体均得到区域5/已分配5，五个框落在拇、食、中、无名、小指甲面，随后一次提取确认五指均写入纹理，控制台0错误。用户本轮仍只提供带3个界面椭圆的截图而非原始上传文件，因此变体验证用于覆盖已复现的色彩/高光失效模式，不把截图叠加区域冒充原始像素真值。

2026-07-31 干燥甲缘复合证据修复：本轮先形成并两轮审查`docs/nail-texture-recognition-recovery-plan-2026-07-31.md`，运行代码在方案v1.0批准前保持不变。逐组件复算证明现场五枚甲面均已形成独立连通域，漏掉的食指和无名指面积、形状、填充率、方差及触边门全部通过，仅因干燥皮肤、甲缘和镜面高光使`directSmoothSkinRatio < 0.24`而被误杀；同图大背景组件已被面积/长边/触边门拒绝。局部分析提高到最长边640，新增最大肤色手部支持域、原始肤色环、候选—肤色环RGB距离、小核开/闭运算和逐原因诊断，平滑肤色改为评分项而非单点硬门；五候选按手部支持域中心的极角弧排序并从端点尺度/间距判断拇指方向。真实浏览器重新上传现场临时裁片得到5/5区域、5/5唯一分配，五框均落在真实甲面；一次提取后逐指确认五份纹理均存在，控制台0错误。诊断JSON记录484×640、33组件、5个合格/5个选中及其余组件拒绝计数。该裁片来自用户截图且顶部含既有界面条，只用于当前功能回归，不进入训练或正式模型证据；正式ONNX阻塞、candidate5拒绝和产品HOLD不变。

2026-07-31 低对比裸色甲面补充修复：用户更换为裸色/半透明五甲图后再次得到0区域。真实页面与640像素逐阶段复算确认MediaPipe没有完整手部候选，四枚无遮挡可见甲面有96.5%—100%像素被当前肤色分类器判为皮肤，蝴蝶结甲与小指甲的甲色候选种子为0；原颜色路径只留下1个指缝暗阴影组件，证明后置放宽色差或面积门无效。恢复方案v1.2在任何运行代码修改前完成证据复审，拒绝把肤色像素直接并入甲色掩码或取消MediaPipe安全门；仅在甲色路径不足2枚时启用本地低对比边界路径，以固定5×5平滑、Sobel、两档闭合边缘补集、甲板内部/肤色邻环、非暗平滑内部、边界梯度、跨阈值去重和最长边21%连续链共同筛选，只有单一4—5枚链才展示，候选固定低置信。第二现场截图临时裁片在真实浏览器由0/5恢复到5/5区域和唯一分配，五框分别覆盖顶部横向甲、上方裸色甲、蝴蝶结甲、圆点甲和小指甲，背景/掌纹0候选；一次提取后逐指确认五份纹理均存在，控制台0 error。诊断为640×637、甲色44组件/1合格、低对比140组件/6合格/同手链5选中，`strategy=low-contrast-boundary`；旧深色/银色现场裁片仍走`painted-color`并保持5/5。截图裁片仅用于功能回归，不入Git、训练或发布质量证据；正式ONNX、candidate5拒绝和产品HOLD不变。

2026-07-31 生产模型路径与复杂拼图现场核验：用户继续上传含中文标题、说明文字、主手照片和右下重复缩略图的社交媒体拼图后，正式UI仍返回0区域并明确显示模型会话初始化失败。磁盘复核确认默认生产manifest存在但其声明的`nail-texture-seg-v1.onnx`缺失，因此本次页面没有运行此前训练权重，实际仍是MediaPipe/局部规则辅助路径。为区分产品装载故障和模型能力，仅以用户界面截图裁出的725×897临时图做本地诊断：SHA-256为`58b0fc25…2ea2`，不入Git、训练或发布证据。交接指定candidate5权重`26daf742…a56`在部署512、阈值0.50下离线得到6个mask，其中五枚主图甲面置信度约0.84—0.90且视觉覆盖完整，另把标题文字误检为甲面（0.68）；这同时证明“页面0枚”不是candidate5输出，也证明candidate5仍不满足零误检发布门。不得根据本图把阈值临时提高到0.68以上、把candidate5复制到生产目录或继续扩张规则分支；正确修复必须是获得新训练授权和来源隔离数据后训练下一候选，冻结完整模型与后处理方案，再用另一份全新未见独立留出、真机和Beta门验证。

2026-07-30 实时AR三维透视贴合改进：实时手部关键点模型由lite几何档切换为`modelComplexity: 1`；`computeNailGeometry()`不再仅把二维TIP→DIP长度乘固定宽度，而是用TIP/DIP/PIP三点和缩放后源视频的z像素尺度估计远端真实尺度，用中段指骨的逐指解剖比例抑制深度抖动，并由手背平面法向与远端指骨轴构造甲面横轴。侧转甲面会按横轴投影自动变窄，长轴与横轴不垂直时通过Canvas仿射矩阵产生透视剪切；移除旧的额外深度缩小项，避免指尖朝镜头时长度与宽度同时二次收缩。关键点EMA响应系数由0.45提高到0.66，几何平滑按移动幅度采用0.55/0.82，降低移动拖尾；手离开画面后清空关键点与几何历史，避免下一只手继承旧位置。控制面板从全手统一大小/位置升级为五指独立长度、宽度与位置校准，可重置当前手指或全部。合成正面、指向镜头、侧转及仿射方向专项与AR周边共29/29通过；真实浏览器验证逐指状态独立保存，食指120%不会污染拇指100%。自动化点击摄像头后停在宿主权限请求，未取得真实视频帧，因此这些证据是工程几何与UI通过，不是实机甲面边界PASS。

运行约束：当前 `maxNumHands: 1`、`modelComplexity: 1`，检测和跟踪阈值均为 `0.5`。`hands.js`、WASM 和相关 MediaPipe 文件从固定本站路径`/vendor/mediapipe/hands/`加载，脚本等待超时为15秒；部署时必须完整保留该目录，缺失或内容发布不完整会导致AR无法启动。高精度关键点会增加端侧推理开销，仍须在四类移动真机上验证帧率、温升和内存。

摄像头启动故障排查顺序：

1. 确认项目服务正在运行，并通过 `http://localhost:3000/ar-tryon` 或有效 HTTPS 地址访问；
2. 页面初始状态只能出现一个“开启摄像头”按钮；点击一次后应立即显示“请求摄像头权限...”及诊断步骤 `1/7`；
3. 浏览器弹出权限请求时选择允许；若曾拒绝，在地址栏网站权限中重新允许并刷新；
4. 若显示设备占用，关闭系统相机、视频会议及其他占用摄像头的应用；
5. 摄像头画面启动后若停在“加载手部识别”，检查`/vendor/mediapipe/hands/hands.js`和对应WASM/模型请求是否为HTTP 200，并确认部署没有遗漏`public/vendor`；此时摄像头权限本身已经成功。

2026-07-14 修复：`/ar-tryon` 页面原先先显示外层启动按钮，第一次点击只挂载 `ArView`，随后 `ArView` 又显示第二个同名按钮，必须点击两次才会调用 `getUserMedia()`。现已移除页面外层 `isStarted` 门控，始终挂载 `ArView`，由组件内部唯一按钮直接处理用户手势和权限请求。浏览器 DOM 验证确认初始按钮数量为 1，一次点击后进入 `1/7 请求摄像头权限...`。自动化应用内浏览器无法提供真实摄像头设备，本轮不把该状态转换验证当作真机画面验收，模块继续保持“待验证”。

主要组件：

```ts
<ArView
  nailColors={string[]}
  nailTextures={(ImageBitmap | null)[] | undefined}
  mode={"color" | "texture" | undefined}
  nailAdjustments={NailFitAdjustment[] | undefined}
/>

interface NailFitAdjustment {
  lengthScale: number; // 0.75..1.40
  widthScale: number;  // 0.70..1.45
  rootOffset: number;  // -0.20..0.20，正值向指根
}

<TextureCropper
  imageUrl={string}
  onConfirm={(bitmap: ImageBitmap) => void}
  onCancel={() => void}
/>

<NailArtPicker
  imageUrl={string}
  onConfirm={(assignments: NailAssignment[]) => void}
  onCancel={() => void}
/>

interface NailAssignment {
  texture: ImageBitmap;
  diagnostics?: TextureExtractionDiagnostics;
  finger: number;
}
```

约定上页面始终传入 5 个颜色/纹理槽位并使用手指索引 `0..4`，但组件公开的 TypeScript Props 当前只是普通数组和 `number`，没有在类型层强制长度或索引范围；外部调用方必须自行校验。

AR 内部关键契约：

```ts
type HandOrientation = "dorsum" | "palm" | "ambiguous" | "none";

interface NailGeometry {
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  transverseAngle?: number;
}
```

朝向语义：`palm` 明确禁止绘制；`dorsum` 允许绘制；`ambiguous` 在 UI 中显示“侧手”，当前采用 fail-open 策略仍允许绘制。状态切换需要连续稳定帧以减少抖动，因此提示不会在单帧内立即变化。这个策略有误贴风险，仍属于真机待验证项。

视频布局使用 `calculateCoverVideoLayout(videoWidth, videoHeight, viewportWidth, viewportHeight)`，输出缩放后的显示尺寸和居中偏移。宽屏转竖屏时从左右两侧对称裁切，竖屏转宽屏时从上下两侧对称裁切，不做非等比拉伸。

### 4.6 `/nail-analysis` 个性化分析推荐

状态：待验证（工程门通过；真实照片与真机验收待补）。纯规则启发式，不引入新模型训练。

使用方式：
1. 上传或拍摄一张五指清晰的手背照片（复用同一上传校验：JPG/PNG/WebP、≤10MB、320–4096px）；
2. 系统本地完成甲面候选识别（降采样至最长边 ≤800，识别结果回原图坐标；正式模型不可用时走 MediaPipe/局部近景辅助定位并页面级常显琥珀声明）；
3. 填写场景问卷（场合必填；风格/劳作强度/长度偏好/甲面状况可选，未填按 unknown 处理；可自评底调覆盖测量值）；
4. 查看分析：手型与甲床比例（含手轴旋转归一化与掌心跨度近似）、肤色 ITA°与底调（附采样点数量与质量）、指甲健康三类启发式（附非医疗声明）；
5. 查看推荐卡片（甲型+长度+色系+「为什么适合」+置信度+命中规则）；
6. 点击推荐色跳转 `/editor?preset=<色名>` 预涂试色（与 `?gallery=` 同时传入时 gallery 优先）。

数据边界：照片、候选与采样全部浏览器本地处理；不新增上传通道；即使开启「用户改进计划」，本功能分析结果也不进入上传通道；ImageBitmap/canvas/objectURL 在取消与卸载时释放。

核心组件接口：

```ts
function analyzeNailPersonalization(input: PersonalizationInput): PersonalizationResult
```

模块位于 `src/lib/nail-personalization/`：`types.ts`、`color-science.ts`（sRGB→Lab/ITA°分档/Monk ITA°近似/底调判定/ΔE76）、`skin-sampling.ts`（甲周椭圆环采样、甲面自污染排除、双条件质量门）、`hand-profile.ts`（手轴旋转归一化、重复甲面判据、四类手型）、`nail-health.ts`（均匀度/高光/条纹，复用 `isSpecularHighlightPixel`）、`rules.ts`（11 条甲型 + 15 条颜色规则、安全硬过滤、同组合取最高权重、组合分归一化）、`present.ts`（中文文案与提示去重）、`bridge.ts`（`?preset=` 出站）、`index.ts`（纯编排）。全部为无 DOM 依赖纯函数，Node 测试环境可直接运行。

前置条件：无新增环境变量；识别库直连方式同 `/device-benchmark`（本页自持一份精简编排，琥珀提示由 `present.ts` 统一提供，同步责任人=本功能维护者）。琥珀辅助定位边界同纹理识别：fallback 候选未经人工确认，不得表述为自动分析成功。

已知限制：手型为甲面派生近似比例（候选不含掌部 landmarks，未做掌宽/掌长口径）；肤色 ITA° 为非受控拍摄估计值，仅供色号筛选参考，**同一双手在不同光照下色系建议可能不同**（已实证：同色温照度每降约 10% 移一档、仅更换光源色温即可跨档），且深肤色在阴影下会被系统性压低、浅中性皮肤在 `|b*|` 接近 0 时分档会退化为由 b\* 符号决定；缓解为**弃权而非猜测**——`classifyItaBandStable()` 在低彩度（`|b*|<4`）或距分档边界不足 3° 时判 `itaReliable=false`，7 条肤色类颜色规则整体弃权、颜色回落场合/风格规则并在 UI 明示，`color-ita-deep-jewel` 另设采样质量门；项目**不做**亮度/曝光归一化（会摧毁 ITA° 测量的深浅信号）与整图白平衡（皮肤主导画面无可靠参考白）；Monk 仅按 ITA° 近似映射，项目不输出 Fitzpatrick；指甲健康为启发式观察，不构成医疗诊断，且当前无像素级 mask 通道恒不可用；`season` 仅为展示标签（四季色彩无同行评审效度验证）；规则表为 TS 常量，调整须同步黄金测试与规则覆盖 meta-test。

关联文档：`docs/nail-personalization-research.md`（资料汇编，含 §2.5 争议/失效证据与 §9 检索维护说明）、`docs/nail-personalization-design.md`（设计）。

### 4.7 消费者端独立设计预览

- **入口与范围**：`node scripts/serve-consumer-design.mjs`，浏览器访问 `http://127.0.0.1:4318`。消费者设计提案位于 `design/consumer-v1/`，不注册 Next.js 正式路由，不导入旧版样式。米白／深墨／珊瑚与五种甲型、工艺的手背贴图方向已获用户认可；继续遵循“设计不一定是加法”，未切换或部署。
- **页面与流程**：为你／试戴／创作／我的，另含可跳过的轻问答、可编辑偏好模板、款式详情、收藏、发布与个人主页布局、美甲方案卡。说明收进可展开区域，保留必要标签与模拟状态；摄像头、语言模型总结、真正生成、个性化推荐、账号认证、跨设备同步和公开社区均未接入。
- **终端与动效**：按可用宽度和输入能力适配手机、平板、横屏与桌面，包含安全区、动态视口、触控目标、键盘焦点和输入时底部导航避让；保留浏览器缩放。短横屏压缩页头与重复引导，两张试戴卡以紧凑横向图形排列。标题使用 OFL 许可的本地 Noto Serif SC 衍生子集，正文用系统字体。路由、收藏、卡片和弹层使用短过渡，遵从 `prefers-reduced-motion`；缺少动画、观察器或 VisualViewport 时保留基本操作。中文合成输入不重建输入节点，返回恢复页面位置；原生 dialog 支持 Esc、焦点回返与背景滚动锁定。关闭只向原页面恢复焦点，跨页返回聚焦主体；已重新打开的弹层不被旧 close 事件解锁。
- **数据与草稿隔离**：仅使用 `jiaru-consumer-design-v1` 保存文字偏好和互动选项；图片为本次会话内存对象 URL，刷新需重选。本人／他人照片分离且沿用账号审美；照片试戴／创作分别持有草稿、模拟生成状态与结果，方案返回对应编辑页。未保存的偏好改动与已保存档案分开；发布图、来源及授权选项在模拟登录后保留。未读写旧版账号、数据库或既有存储键。
- **方案导出与分享**：预先生成本地 PNG，用户点击后在支持文件分享的浏览器调用 `navigator.share`；不支持或分享失败时下载，用户取消不显示成功。仅声明已交给系统面板，不宣称送达；不分享本机预览地址。旧方案异步完成不能提前启用当前方案分享。原生分享尚待真机验证。
- **预览服务**：只绑定 `127.0.0.1`，默认4318，可用 `--port` 指定；仅白名单 GET／HEAD 提供原型、必要图片与本地 WOFF2，禁止写请求与任意工作区文件访问。CSP 禁止页面网络连接，摄像头等权限关闭；无需密钥或环境配置。
- **备份与恢复边界**：实施前当前磁盘版本（包括未提交修改）已保存至本地 `.backup-consumer-20261020-v1/`，含源码、必要运行时资产、锁文件和配置模板；不含真实密钥／用户库／训练产物。逐文件恢复验真与四页开发服务访问已验证；恢复副本的生产构建尚未通过，不宣称完成生产恢复验收。机器记录见本地 `output/frontend-redesign/backup-verification.json`。
- **验收边界**：最终 Chrome 核心75项与补充12项、独立Pixel 7触控模拟55项、Windows Edge补充24项检查通过；紧凑竖屏及短横屏入口完成完整截图复查。覆盖中文输入、异步状态、粗指针 tap、返回与弹层、减少动态效果、分享／编码／剪贴板失败恢复，绑定最终源码的记录见本地 `output/frontend-redesign-final-20261021/`。Android／iOS真机、iOS Safari／WebKit、真实系统键盘／安全区与原生分享仍未验收；模拟不代替真实服务或生产质量。旧审批服务额度故障已解除，历史失败保持。服务选型与正式切换仍待确认。完整设计、检查范围与恢复说明见 `docs/consumer-redesign-design-brief.md`。

## 5. HTTP API 契约

账号接口补充（2026-09-05源码复核）：当前已存在`/login`、`/account`及`/api/auth/*`、`/api/me`、`/api/me/improvement`、身份绑定/解绑接口；底层为JWT与Node内置SQLite的账户原型。真实短信发送尚未接入，refresh轮换没有实际请求入口，默认数据库父目录缺少初始化；验证码发送历史、手机号换绑一致性和生产部署仍有缺口。因此账户不是“完全未实现”，也不能按生产可用登记。两条付费生图路由尚未使用现有账户鉴权与额度保护。源码证据与复现见`docs/project-review-2026-09-05.md`第5—7项。

更正（v1.1.649）：上段两项缺口已在同日修复——①两条付费生图路由已接入`requireUser`身份识别与配额/预算熔断（见§5.1配额规则）；②`createUserDb`已对数据库父目录做`mkdirSync`初始化预检，干净克隆首次匿名请求不再抛`ERR_SQLITE_ERROR`。短信适配、refresh续期入口、验证码发送历史与手机号换绑一致性仍未修复。

更正（v1.1.657）：上段三项缺口已修复——①新增`POST /api/auth/refresh`静默续期入口与`requireUserWithRenewal`（access失效自动以refresh续期，不轮换会话、并发安全；refresh剩余寿命不足15天时滑动重签），`/api/me`（GET/PATCH）、身份列表/解绑、改进计划偏好、绑手机共6处调用点接入；②验证码消费改为`consumed_at`标记、发送台账与验证码生命周期分离，60秒节流与单日10条上限依据完整台账，成功登录不再抹掉发送历史；③手机号换绑在同一事务内一致更新`users.phone`与phone identity，解绑phone同步清空资料手机号（解绑后同号可再绑）。图形验证码已重写为5×7点阵笔画路径渲染（SVG无`<text>`节点、源码不含明文答案）。短信服务商适配仍未接入（生产需配置）。

### 5.1 `POST /api/generate-ai`

状态：功能链路已有既有用户验收；服务端身份与配额/预算熔断已接入（v1.1.649，见下方配额规则），内容审核记录、请求幂等、结果持久化和计费统计仍未完成，不能把功能验收等同生产开放资格。

请求：

```http
POST /api/generate-ai
Content-Type: application/json

{"prompt":"银色亮片渐变，月光质感","ratio":"1:1","size":"1K"}
```

请求字段：

- `prompt`：必填，1～520 字符描述。
- `image`：可选，Data URI 参考图（PNG/JPEG/WebP，≤9,000,000 字符 ≈6.7MB）；提供后走图生图。
- `ratio`：可选，画面比例，取值 `1:1`/`3:4`/`4:3`/`16:9`/`9:16`/`2:3`/`3:2`/`21:9`，默认 `1:1`。
- `size`：可选，输出尺寸档位，取值 `1K`/`2K`/`3K`/`4K`，默认 `1K`；与 `ratio` 组合决定最终像素尺寸（参考 §4.4「输出尺寸参考」）。

成功响应：

```json
{"imageUrl":"https://..."}
```

错误响应统一格式：

```json
{"error":"错误说明"}
```

| HTTP 状态 | 含义 |
| --- | --- |
| 400 | 非法 JSON、空描述或超过 520 字符、画面比例无效、尺寸档位无效 |
| 401 | 外部 API 密钥无效 |
| 429 | 本地配额拒绝（身份日额度/全局预算熔断/并发上限，响应带 `Retry-After`）或外部 API 限流 |
| 500 | 未分类服务端异常 |
| 502 | 外部 API 错误或响应缺少图片 URL |
| 503 | 未配置`AGNES_API_KEY` |
| 504 | 180秒总超时 |

**配额规则（v1.1.649，与 §5.2 共用 `src/lib/ai-quota.ts`）**：请求在参数校验后、外部调用前经 `requireUser` 识别身份并同步预留额度——登录用户每日 20 次、游客（`x-forwarded-for` 首段 SHA-256 前 16 位为键）每日 5 次、全局每日 200 次预算熔断、全局并发 3 且同一身份同时仅 1 个任务；外部调用成功后 `commit` 确认消耗，失败时 `release` 返还该身份当日次数但全局日计数保留（防刻意失败刷预算）。超限返回 429、中文错误与 `Retry-After`。限额由 `AI_QUOTA_GUEST_DAILY`/`AI_QUOTA_USER_DAILY`/`AI_QUOTA_GLOBAL_DAILY`/`AI_QUOTA_GLOBAL_CONCURRENCY` 调整（非法值回退默认）。配额为进程内存态，适配当前 Windows 单实例 `next start` 部署，重启清零；多实例共享与持久化消费台账未实现。

当前未实现内容审核记录、请求幂等、结果持久化和计费统计；正式开放前必须补齐相应治理能力。

### 5.2 `POST /api/generate-seedream`

状态：待验证（服务端已实现；pro 与 lite 引擎均经脚本端到端实测通过（v1.1.565）；浏览器全链路验收待做）。

请求：

```http
POST /api/generate-seedream
Content-Type: application/json

{"prompt":"银色亮片渐变，月光质感","model":"pro","ratio":"21:9","size":"2K"}
```

请求字段：

- `prompt`：必填，1～300 字符描述（Seedream 文档建议中文 ≤300 字，短于 Agnes 的 520）。
- `model`：可选，`pro`（默认，`doubao-seedream-5-0-pro-260628`）或 `lite`（`doubao-seedream-5-0-260128`）；非法值回退 `pro`。
- `image`：可选，Data URI 参考图（PNG/JPEG/WebP，≤9,000,000 字符 ≈6.7MB）；提供后走图生图，作为 Ark 顶层 `image` 字段发送。
- `ratio`：可选，画面比例，取值与 §5.1 相同的 8 值白名单，默认 `1:1`。
- `size`：可选，输出尺寸档位；pro 合法值 `1K`/`1.5K`/`2K`，lite 合法值 `2K`/`3K`/`4K`，默认 `2K`；与 `ratio` 组合经 `resolveSeedreamDimension` 映射为 Ark 显式 `size`（WxH 像素字符串，如 `3136x1344`），非法组合在调用外部 API 前返回 400。

成功响应：`{"imageUrl":"https://..."}`（Ark 返回的 URL 24 小时后过期，项目不做长期留存）。

错误响应统一格式同 §5.1（`{"error":"..."}`）。主要状态码：

| HTTP 状态 | 含义 |
| --- | --- |
| 400 | 非法 JSON、空描述或超过 300 字符、比例无效、档位与模型组合非法、参考图格式非法 |
| 401 | `VOLCENGINE_ARK_API_KEY` 无效 |
| 429 | 本地配额拒绝（同 §5.1 配额规则，响应带 `Retry-After`）或外部 API 限流（客户端已按 1/2/4s 退避重试，重试耗尽后透传） |
| 500/503 | 外部 API 异常或未配置密钥 |
| 502 | Ark 顶层 `error{code,message}`、`data[0].error` 或响应缺少图片 URL |
| 503 | 未配置`VOLCENGINE_ARK_API_KEY`或 Model ID |

服务端环境变量：`VOLCENGINE_ARK_API_KEY`（必填）、`ARK_SEEDREAM_PRO_MODEL`/`ARK_SEEDREAM_LITE_MODEL`（Model ID，必须带版本日期后缀）、可选 `ARK_BASE_URL`（默认 `https://ark.cn-beijing.volces.com/api/v3`）、可选 `ARK_IMAGE_WATERMARK`（默认 `false`）。`sequential_image_generation` 等组图参数禁止用于 pro；本路由为扁平 body，无 Agnes 的 `extra_body` 包装，也无 `ratio` 参数。身份与配额/预算熔断已随 v1.1.649 与 §5.1 同步接入（同一 `src/lib/ai-quota.ts` 守卫，`engine:"seedream"`）；内容审核记录、请求幂等、结果持久化和计费仍未实现。

## 6. 浏览器端美甲纹理识别接口

### 6.1 对外入口

公共 barrel 位于 `src/lib/nail-texture-recognition/index.ts`。业务主入口是 `recognizeNailTexturesInWorker()`；底层同步流程入口是 `recognizeNailTextures()`：

```ts
async function recognizeNailTexturesInWorker(
  source: ImagePixels,
  options?: RecognizeNailTexturesOptions
): Promise<NailTextureRecognitionResult>

async function recognizeNailTextures(
  source: ImagePixels,
  options?: RecognizeNailTexturesOptions
): Promise<NailTextureRecognitionResult>
```

`ImagePixels` 的实际结构为 `{ width: number; height: number; data: ArrayLike<number> }`，浏览器 `ImageData.data` 的 `Uint8ClampedArray` 是兼容输入之一。

同一 barrel 还导出 manifest/runtime、预处理、后处理、质量排序、mask 提取、反光修复、debug 对比、首跑记录验证和 Worker 生命周期接口。这些属于内部研发接口，除上述识别入口和稳定类型外暂不承诺跨版本兼容；新增外部调用方前必须在本节登记具体函数、输入输出和兼容策略。

主要选项：

```ts
interface RecognizeNailTexturesOptions {
  preferModel?: boolean;
  manifestUrl?: string;
  maxCandidates?: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  debugOutputs?: boolean;
  debugRawModelOutputs?: boolean;
  signal?: AbortSignal;
}
```

主要返回：

```ts
interface NailTextureRecognitionResult {
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  workerElapsedMs?: number;
  modelVersion?: string;
  warnings: string[];
}

interface NailTextureCandidate {
  id: string;
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  score: number;
  confidence: "high" | "medium" | "low";
  source: "model" | "mediapipe" | "partial-closeup" | "saliency" | "manual";
  mask?: NailMask;
  warnings?: string[];
  suggestedFinger: number | null;
}
```

### 6.2 运行策略

1. 直接调用 `recognizeNailTextures()` 时只有显式传入 `preferModel: true` 才加载模型，否则直接使用 fallback；`recognizeNailTexturesInWorker()` 默认将 `preferModel` 设为 `true`；
2. 优先尝试 WebGPU，不支持时回退 WASM；
3. 模型加载、推理、Worker 或后处理失败时底层返回 fallback 结果和 warning；规则候选只供诊断，必须标为低置信度；
4. 正式UI检测到`backend: "fallback"`时隐藏规则候选、保留原候选到debug导出，再调用`detectNailsFromHandImage()`尝试完整手部几何定位；
5. 手部几何定位成功时生成`source: "mediapipe"`候选并按五指索引自动分配；无完整手部或无可靠几何时，再调用`detectPartialCloseupNails()`尝试局部近景定位；兼容入口`detectPartialCloseupNailCandidates()`仍只返回候选数组；
6. 局部近景先运行甲色路径：以小核开/闭运算处理非皮肤且未过曝连通域，并通过面积、形状、方差、触边、手部支持域、原始肤色环和局部RGB距离复合门；同手空间簇有2—5枚时直接返回。甲色路径不足2枚时才运行低对比边界路径：固定5×5平滑与Sobel梯度，两档边缘阈值经5×5闭运算后提取不接触图像边界的内部区域；候选必须同时通过面积/长短轴/长宽比/填充率、内部及邻环肤色、手部支持、内部非暗且平滑、边界梯度，并跨阈值去重。只有单一4—5枚候选以最长边21%相邻距离形成连续链时才返回，否则整条边界路径为空。两路五候选均按手部支持域中心极角弧排序；甲色路径4—5个为`medium`、2—3个为`low`，低对比路径固定为`low`并带`partial_closeup_low_contrast_boundary`复核warning；全部为`source: "partial-closeup"`；
7. 模型候选经过置信度评估、角度稳定、手指建议和mask纹理提取；MediaPipe、局部近景与人工候选使用透明椭圆裁剪；
8. UI必须展示真正影响当前候选的低置信度与提取质量告警，并允许用户点击新增、拖动/按钮调整、重新分配、删除或取消。所有`backend: "fallback"`均持续显示辅助定位及逐个人工确认边界提示，不因局部近景或候选数≥4显示“可直接提取”；零候选提示手工添加。技术warning可保留诊断摘要和导出，但不得隐藏明确降级状态；`model_not_deployed`显示生产模型尚未部署。

当前 `NailArtPicker` 将正式模型检测输入最长边限制在 800 像素，最多请求 10 个候选，Worker 超时为 15 秒。fallback原候选不会进入可确认区域；MediaPipe静态图检测超时为20秒，使用`modelComplexity: 1`、最多1只手、检测/跟踪阈值0.5。局部近景分析会再次把最长边限制为640像素。甲色路径初始前景要求像素不属于皮肤且灰度低于225，连通域填充率下限0.32、原始肤色环下限0.52、最大手部支持环下限0.38、局部RGB均值距离下限18；平滑肤色只参与评分，同一空间簇至少2枚、最多5枚。低对比路径只在甲色候选不足2枚时运行：Sobel阈值22/24，边缘闭运算半径2；内部区域面积占比0.0014—0.015、短轴至少最长边3.4%、长轴不超过18%、长宽比不超过2.7、填充率至少0.34；内部肤色至少0.88、邻环肤色至少0.82、手部支持至少0.72、内部平均灰度至少90且标准差不超过15、邻环平均梯度至少36；跨阈值中心距离在最长边5.5%内去重，最终只接受以21%相邻距离形成的单一4—5枚链。`detectPartialCloseupNails()`诊断新增`strategy`及低对比组件、合格、选中和拒绝计数；UI只把数值写入本地诊断JSON，不上传原图像素。两条路径都是本地几何候选生成器，不提供像素mask或正式模型质量承诺。人工新增区域默认按源图短边约8%宽、短边约16%长建立，并限制在原图边界内。候选确认后以 `NailAssignment[]` 返回，每个 `ImageBitmap` 的所有权转移给 `/ar-tryon` 页面，页面在替换或卸载时负责释放。

模型候选在现有box抑制前新增像素mask同甲抑制。`rankNailTextureCandidates()`的内部质量选项现包括`duplicateMaskIouThreshold`、`duplicateMaskContainmentThreshold`和`duplicateMaskScoreTolerance`，默认分别为0.60、0.85、0.12；当两个等网格mask高度重叠或较小mask被较大mask包含时，优先保留完整大mask，只在分数差不超过容差时允许其替换高分局部mask，空间分离的相邻甲继续保留。该算法已通过18/18后处理专项测试，但参数尚未在来源隔离val30锁定，也未对candidate9冻结test100重放，当前不得写成正式识别质量提升或解除HOLD。

MediaPipe静态图与实时AR共享`MEDIAPIPE_HANDS_ASSET_BASE_PATH=/vendor/mediapipe/hands`。所需浏览器运行文件由锁定的`@mediapipe/hands@0.4.1675469240`复制到`public/vendor/mediapipe/hands/`，不得重新改回运行时CDN；`tests/mediapipe-hands-assets.test.ts`检查关键文件非空及两条调用路径不含MediaPipe CDN地址。

环境变量：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg/manifest.json
```

开发烟雾验证可临时指向：

```env
NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL=/models/nail-texture-seg-smoke/manifest.json
```

`.env.local.example` 默认不再启用 manifest 覆盖；直接复制时由代码使用 `/models/nail-texture-seg/manifest.json`。只有受控 smoke 验证才应临时取消示例注释并指向 smoke manifest。回归测试会拒绝示例文件中任何启用状态的 `NEXT_PUBLIC_NAIL_TEXTURE_MODEL_MANIFEST_URL`，避免测试模型成为共享默认值。在正式 ONNX 缺失期间，默认正式路径仍会进入 fallback，不代表正式模型已经可用。

默认生产manifest明确登记`deploymentStatus: "not-deployed"`，计划文件名仍保留但ONNX尚未部署；运行时会在创建会话前返回`model_not_deployed`及fallback。历史候选及训练域精修权重均未获生产发布资格，禁止用其补齐默认目录或共享环境变量以消除该提示。当前正式模型状态以§3/§11.1与Goal为准。

烟雾/合成模型只验证工程链路，不得用于宣称真实美甲识别质量。结果顶层 `backend: "model"` 只表示走了模型路径；实际执行提供程序 `webgpu`/`wasm` 位于 `modelInfo.backend`。

### 6.3 Worker 消息契约

```ts
interface RecognizeNailTextureRequest {
  id: string;
  imageBitmap: ImageBitmap;
  maxCandidates: number;
  workerTimeoutMs?: number;
  includeLowConfidenceCandidates?: boolean;
  preferModel: boolean;
  manifestUrl?: string;
}

interface RecognizeNailTextureResponse {
  id: string;
  candidates: NailTextureCandidate[];
  backend: "model" | "fallback";
  elapsedMs: number;
  warnings: string[];
  modelVersion?: string;
  modelInfo?: NailTextureModelInfo;
}
```

调用方应在超时、取消、页面卸载或更换图片时释放 `ImageBitmap` 和 Worker 资源。当前 Worker 超时后会重置 Worker，并通过主线程 fallback 尝试返回降级结果；用户取消会重置 Worker 并以 `AbortError` 拒绝当前请求，不执行 fallback。调用方必须分别处理异常和 `warnings`，不能只检查是否返回候选。

### 6.4 纹理提取接口

```ts
extractTexture(imageUrl, { x, y, w, h }): Promise<ImageBitmap>
clampTextureSize(bitmap, maxSize?): Promise<ImageBitmap>
disposeTexture(bitmap): void
disposeAllTextures(bitmaps): void
```

普通裁剪输出最大边默认不超过 256 像素。自动识别路径支持带 mask 的透明纹理提取、羽化边缘、反光检查/修复和诊断信息。

## 7. 模型产物契约

正式 manifest 路径：`public/models/nail-texture-seg/manifest.json`。

`deploymentStatus`为可选枚举`deployed | not-deployed`，缺省兼容旧候选，显式非法值（含null）拒绝。当前默认为`not-deployed`：window/worker共用加载器及Stage B入口均在ORT会话前返回fallback和`model_not_deployed`；`resolveModelUrl`拒绝解析。资产审核、发布登记及切换拒绝未部署/非法状态，且不创建登记或覆盖活动manifest。`deployed`仅表示声明可加载，仍须资产完整性、同一发布身份及全部质量门，不自动授予发布资格。

```json
{
  "version": "nail-texture-seg-v1",
  "deploymentStatus": "not-deployed",
  "inputSize": 640,
  "inputLayout": "NCHW",
  "colorOrder": "RGB",
  "normalization": "zero_to_one",
  "resizeMode": "letterbox",
  "task": "segment",
  "backendPreferences": ["webgpu", "wasm"],
  "modelFile": "nail-texture-seg-v1.onnx",
  "outputContract": "ultralytics-seg-raw-v1",
  "scoreThreshold": 0.35,
  "labels": ["nail_texture"]
}
```

`scoreThreshold`是模型版本级候选阈值：运行时、原始输出过滤和质量排序使用同一有效值；字段缺省时保持`0.35`兼容，显式值必须为0和1之间的有限数。`export-onnx.py`可通过`--score-threshold`写入校准值，浏览器manifest校验和`verify-model-artifact.ts`执行相同约束。该字段只是保存已完成验证的模型校准结果，不能用单次阈值扫描绕过误检、候选数量、直接可用率或Beta发布门。

正式阈值必须由`calibrate-model-score-threshold.py`使用来源隔离的`val`预测生成。校准器绑定数据集、来源报告、模型权重、评估指标和预测制品SHA-256，拒绝`test`/冻结发布测试、val来源跨split和未知预测文件；`--truth-audit`还必须提供`approved_as_calibration_truth`报告，且dataset路径/哈希、逐标签SHA-256、预期/已审/通过数量全部一致、返修和排除均为0。未提供审核或审核明确拒绝时分别输出未审核/已拒绝诊断，永远不生成manifest阈值。至少30张验证图、真值polygon零修复、所有验证图通过原分辨率完整甲面审核，同时满足召回、每图误检和单图候选数门，才输出非空`manifestScoreThreshold`。任何返修/排除项、未声明交叠、漏甲、重复、误标、污染或边缘裁断都会使整套split失去校准资格。

规范校准不能直接让Ultralytics读取受审核数据根目录：标签扫描会自动创建`labels/*.cache`并污染不可变物化清单。`evaluate.py`现在先把所选split的图片与标签逐文件复制到输出侧`evaluation-runtime-dataset`，运行YAML只指向该副本，并在物化后和推理结束后重算源数据整树相对路径及逐文件SHA-256；源树任一新增、删除或字节变化都会拒绝证据。评估制品按POSIX相对路径字符串稳定排序，绑定逐文件SHA-256及覆盖每张验证图的`prediction_records`，无预测图必须显式记录为零而不是从清单消失。v6在规范val30部署512上的box/mask mAP50为0.6241/0.5630；confidence=0.05时召回0.7569但每图误检9.8333、单图最多28候选，其余扫描点召回均低于0.75，因此没有合格manifest阈值。

正式发布要求：

- manifest 通过结构校验；
- ONNX 文件存在，文件名与 manifest 一致；
- 输入/输出名称和张量形状与后处理契约一致；
- 通过 fixture、真实图片、浏览器集成和性能门；
- 具备版本、SHA-256、体积、指标、发布和回滚记录。

当前生产ONNX与releaseIdentity均未批准；默认manifest为显式未部署占位，正式资产审核仍必须拒绝。历史v6及synthetic/smoke只承担原绑定诊断/工程用途，不能充当正式模型或回滚批准版本；当前训练候选状态见§8.9/§11.1。

## 8. 数据集与训练接口

### 8.1 数据集契约

数据集根目录：`model/datasets/nail-texture-v1`。

核心版本：`nail-texture-dataset/v1`。标注以多边形 mask 为主，可转换为 YOLO segmentation 格式。必须维护素材来源、授权、哈希、审核状态、数据切分和负样本信息。

候选训练困难负样本必须先经`record-training-hard-negative-authorization.py`建立精确授权与机器审计：只接受显式相对路径白名单，授权用途必须同时包含商业模型训练和长期回归并排除独立发布测试；图片最短边固定不少于768像素，序号连续且新批文件名前缀必须为training。`--protected-hard-negative-registry`为唯一受保护集合入口，registry固定schema v1、decision、每份manifest的path/SHA-256/role、entriesSha256及training/holdout计数，创建和授权重放都不再接受调用方自由漏传manifest。当前权威registry为Git外`审核工作区/protected-hard-negative-registry-v4.json`，SHA-256为`dd7648c3…951d`；其7份manifest（training 4、holdout 3）当前哈希全部匹配，共728条唯一保护记录。v4在v3基础上单调追加candidate5编号361—460独立留出，因此candidate4编号261—360、candidate5训练160张、candidate5编号361—460及其他历史training/holdout均被技术性禁止改换角色或复用。历史清单中的`hard_negative_ai_*`、training清单旧`hard_negative_independent_*`和`nail_*`仅在受保护侧按manifest decision解释，sourceGroup会移除角色片段并统一日期；新候选自身不获得旧命名兼容。记录器逐图重算SHA-256、规范sourceIdentity和dHash256，距离不大于12的感知重复拒绝，授权与机器清单始终保持`trainingUse=prohibited`。`build-independent-hard-negative-review-workspace.py`在training角色下调用记录器只读深度重放，在independent角色下继续重放冻结记录器；两种角色均核对所选授权/机器清单路径、SHA-256和图片数，强制授权用途与新批文件前缀一致，并采用staging与原子替换生成工作区，覆盖失败时恢复旧目录，禁止半成品或旧审核页混入。

独立AI困难负样本在冻结前先由`build-independent-hard-negative-user-authorization.py`建立schema v2逐文件授权源。该工具只消费已固定的候选清单和预授权机器审计，不按目录扫描自行扩权；要求用户原文与按绝对路径、图片数和连续序号生成的确认文本完全一致，并绑定每张图片的相对路径、SHA-256、尺寸、格式、字节数、dHash、来源组以及候选权重、规范阈值报告和受保护registry。输出明确排除`commercial-model-training`、保持`trainingUse=prohibited`且不可覆盖。`record-independent-hard-negative-authorization.py`兼容历史schema v1冻结只读重放；新schema v2会在首次枚举和原子提交前两次要求当前100项与用户授权清单完全相同，任何换图、增删、改名或上游证据漂移都不得借用旧授权。正式候选冻结还应传入`--expected-candidate-weights-sha256`与`--expected-score-threshold`；它们是阶段计划对本次候选身份的外层断言，必须与权重字节和规范阈值报告的深验结果精确一致。candidate5固定使用权重`26daf742…a56`与阈值`0.50`，因此不能误传candidate4的`2bde9702…2b09`/`0.35`组合。

独立困难负样本只回答“纯非美甲物体是否被误检为甲面”，不能证明“真实甲面承载相同强混淆图案时是否仍被召回”。模型应主要依赖手指上的完整甲面几何和上下文，而非图案类别，但candidate5尚无覆盖肉质叶、花瓣、种荚、软胶囊、牙冠等强混淆纹理的真实甲面正样本挑战集，因此稳定召回不得表述为已验证。后续如验证该能力，应另建来源隔离的真实甲面正样本挑战集并单独审核，不得混入或替代本纯负独立留出，也不得在本批精确授权与freeze前提前消费candidate5输出。

独立AI困难负样本取得上述授权并原子冻结后，使用`build-independent-hard-negative-review-workspace.py`构建原分辨率审核契约：输入必须同时包含A授权、机器审计、当前train/val真值索引和冻结test清单；脚本逐文件复验路径、SHA-256、尺寸、完整解码和三角色身份隔离，并生成不缩放的1:1像素审核页与空白决定CSV。审核人员必须另存完成版CSV，禁止覆盖空白模板。`finalize-independent-hard-negative-review.py`随后重放授权、机器审计、受保护角色、审核页和原图当前字节；通过项必须有审核说明且不得带缺陷码，排除项必须填写受控缺陷码。该终审只生成candidate-only清单，仍由`finalize-reviewed-hard-negative-manifest.py`深验并达到100张后才可形成schema v2留出批准清单。若该批已被当前模型用于错误筛选且结果会影响训练，它不得再承担下一候选的未见独立发布留出角色。

旧的`audit-dataset-source-isolation.py`与`audit-candidate-training-validation.py`保留为历史实验数据诊断工具，但其外层PASS不再能够单独授权正式候选训练。正式链路先运行`materialize-canonical-candidate-training-dataset.py`：必须绑定当前训练真值唯一索引、`approved_hard_negative_manifest`、规范val-only `dataset.yaml`及`approved_as_calibration_truth`终审、冻结发布测试清单；在写目录前固定核验train正样本不少于100张、正式hard negative不少于100张、val不少于30张，并重算四角色文件名、图片SHA-256和来源组零重叠。输出采用事务式目录替换，固定`images/labels train|val|test`，其中hard negative标签必须为零字节、test必须为空，`records`、`datasetFiles`、角色身份和全部聚合哈希写入物化报告。

`approved_hard_negative_manifest`只能由`finalize-reviewed-hard-negative-manifest.py`生成。schema v2终结器重放每批候选清单、原分辨率审核决定、A授权、当前图片哈希和既有来源隔离证据，并固定不少于100张；数量不足时只输出`HOLD`、`trainingUse=prohibited`及不可消费的`candidateItems`。图片在批准前必须由Pillow完成结构验证和完整像素解码，最短边不少于320像素，当前宽高必须与审核记录一致；损坏文件、文本伪装图片或审核/授权漂移均拒绝。若内容是受支持的真实图片格式但扩展名错误，源文件和审核身份不改，正式物化文件名按解码格式规范化。角色隔离器、候选物化器和GPU前输入审计都会调用该终结器的`verify_approved_report()`重放当前证据；输入审计还会再次解码物化后的负样本。

物化成功后必须运行`audit-candidate-training-input.py`，它不信任物化报告外层PASS，而是独立重算上游allow-list、训练annotation到YOLO label转换、val终审逐项等价、polygon合法性与任意非零交叠、负样本空标签、孤儿文件和四角色隔离；正式100/100/30下限不能由CLI调低。`train-yolo-seg.py --candidate-mode --candidate-input-report <report>`在创建训练输出、加载Ultralytics和占用GPU前调用`verify_approved_report()`深度重放当前字节；训练结束后再重放一次，数据中途漂移时不生成合格候选摘要。普通运行仍记录`training_intent=experiment`，旧`--candidate-validation-report`明确拒绝作为候选授权。

候选模型的部署口径val评估必须使用上述只读runtime副本和不可复用的新输出目录；`val-metrics`同时绑定原dataset YAML、权重、源树前后inventory、runtime物化记录和评估制品索引。`calibrate-model-score-threshold.py`对规范模式再次调用validation终审器，重放truth index、物化报告、角色隔离、图片、annotation、label、polygon合法性和零交叠；旧`experiment_only_source_isolated_real_dataset`只允许输出诊断，不能产生manifest阈值。

训练发布编排器使用三路权威证据：`run-training-release-pipeline.ts --candidate-mode`除训练dataset和`candidate-input-report`外，还必须提供规范val的dataset、物化报告、校准真值终审和校准输出，以及冻结release-test的dataset与物化报告；三套dataset路径必须不同，候选模式禁止通用`--split`、`--skip-evaluate`和`--skip-export`。`candidate-input-preflight`与冻结test的`--verify-report`在环境检查/GPU前执行，随后顺序固定为训练、val评估、阈值校准、冻结test评估和证据化导出。恢复训练仍须绑定同一dataset路径/SHA-256、输入报告路径/SHA-256及权重SHA-256；任何不一致都在评估、导出和治理之前停止。dry-run只展示全部命令且不启动Python/GPU，不能生成授权证据。

冻结release-test物化报告为schema v2，绑定冻结manifest路径/SHA/`itemsSha256`、训练身份、三份dataset YAML、评估manifest、core/stress记录及整棵输出树逐文件与聚合SHA；固定test非空、train/val为空、`trainingUse=prohibited`。`materialize-frozen-release-test-evaluation.py --verify-report`会重新读取源manifest、训练sources、图片、annotation、YOLO label、polygon拓扑、来源隔离和当前文件清单，拒绝伪造PASS、写后漂移或dataset错配。`calibrate-model-score-threshold.py --verify-report --expected-weights`同样重放规范val全链路；`export-onnx.py --candidate-mode --calibration-report`禁止手工`--score-threshold`，manifest的`scoreThresholdEvidence`必须记录报告、dataset、metrics、制品索引和权重SHA。最终`verify-training-release.ts --candidate-mode`再次要求release metrics为`split=test`，重算test全树、预测制品和阈值证据，防止把val结果误当发布质量。

当前数据集口径以 §3 状态表「数据集治理」行为准：clean98 开发基线（58 图/354 mask v2 加 40 困难负图）与循环015 扩容（源图供给 55 图/55 来源组/322 甲冻结、开发评估真值 43 图/265 甲、训练禁用）为当前事实。仓库内历史基础数据集仍为 409 图/2142 mask、split=300/46/63，属历史快照，不作为当前训练、评估或发布口径。

> **历史执行叙事已归档（2026-10-12 v1.2.2）**：§8.1 早期版本另含 candidate3/5、261—360 困难负样本批次
> 执行记录，以及 2026-07-13 起逐轮标注返修、质量审核分片与真值批次的执行流水；这些内容属已完成
> 的历史执行记录，不影响当前契约，已整体迁至 `docs/archive/whitepaper-dataset-contract-history.md`。
> 现行契约见本节上文，当前数据集口径见 §3 状态表「数据集治理」行。

### 8.2 训练主流程

```text
素材入库与授权审计
  -> 标注/人工复核
  -> 标签审计与数据切分
  -> materialize 训练数据
  -> train-yolo-seg.py
  -> evaluate.py / assess-model-metrics.py
  -> export-onnx.py
  -> quantize-onnx-int8.py（可选）
  -> 浏览器 fixture 与性能验证
  -> 发布注册、切换与回滚验证
```

关键脚本分类：

| 类别 | 主要入口 |
| --- | --- |
| 环境检查 | `check-training-environment.py` |
| 数据盘点 | `audit-image-corpus.py`、`audit-labels.ts`、`audit-phase1-readiness.ts`；平铺语料统一归入`.`根桶，避免把文件名误计为一级目录 |
| 实拍候选intake、授权、审核工作区与分配 | `build-real-material-candidate-intake.py`、`authorize-real-material-candidate-intake.py`、`build-real-material-review-workspace.py`、`audit-real-material-exclusive-assignment.py`；逐图复核哈希/尺寸、稳定分组并按来源组原子分片，A/B/C授权绑定原证据；未审核条目禁止训练，最终审核必须全覆盖且训练、val、独立发布测试按来源组互斥 |
| 数据准备 | `convert-annotations.ts`、`split-dataset.ts`、`materialize-training-dataset.ts` |
| 辅助标注 | `generate-yolo-prelabels.py`、`sam-assisted-nail-annotation.py`；正样本补强另使用`record-positive-reinforcement-authorization.py`、`build-positive-reinforcement-annotation-workspace.py`、`build-first-annotation-mask-review-decisions.py`与首轮/返修终结器。辅助模型和SAM输出始终是候选，逐甲原分辨率审核及最终真值审计前禁止训练 |
| 审核区域提取 | `extract-reviewed-image-regions.py` |
| 审核区域替换合并 | `merge-reviewed-region-reports.py`；按父图替换错误派生区域，强制父哈希和稳定来源组一致，并物化无重复父项的新版聚合区域包 |
| 发布测试派生区域intake | `build-release-test-region-intake.py`；继承发布测试/长期回归授权，禁止训练，校验stress父项、父子哈希、派生文件和一父一主区域 |
| 发布测试提示修复 | `build-reviewed-sam-repair-prompts.py`；按人工keep/drop/add决定重建提示，支持逐新增框选择SAM提示模式，记录源提示/修复清单哈希并保持候选隔离 |
| SAM提示几何审计 | `audit-sam-prompt-geometry.py`；按提示与多边形输出面积比、包含率、中心关系和同图边界框IoU的JSON/CSV，仅作为提示一致性证据，不能替代原分辨率视觉审核 |
| 发布测试审核聚合 | `build-release-test-annotation-review.py`、`build-release-test-review-summary.py`；叠加修复报告、核对polygon数/来源组并将派生决定映射回父图 |
| 发布测试拓扑返修 | `repair-reviewed-annotation-topology.py`；仅处理清单声明的无效polygon/遮挡交叠，限制丢弃面积与甲面损失，并输出整图和逐甲2×审核证据 |
| 发布测试候选冻结 | `freeze-reviewed-release-test-candidates.py`；要求全部polygon合法、同图零交叠、训练禁用，并固定图片/标注/联合/聚合SHA-256与100张代表性规模门 |
| 冻结测试评估物化 | `materialize-frozen-release-test-evaluation.py`；独立复算冻结快照、验证与正式训练集来源组及图片哈希零重叠，只物化test并禁止训练；schema v2绑定源manifest、三份YAML、评估manifest和递归文件清单，`--verify-report`只读重放全部当前字节 |
| 冻结测试质量报告 | `build-frozen-release-test-quality-report.py`；schema v2动态绑定旧67或新100快照，深验评估物化、assessment标签、部署512全量/核心/压力指标、预测覆盖及同一候选权重SHA-256；三组512必须同时通过，640仅诊断。`--verify-report`重读全部传递输入、临时重建并逐字段比较，完成度审计据此拒绝伪造、漂移、换绑及历史小测试回退 |
| 冻结测试失败画像 | `profile-frozen-release-test-failures.py`；按部署置信度逐实例匹配真值/预测，聚合lane与父来源组并生成最高风险原分辨率叠加图；正式制品必须以逐图预测记录、路径、SHA-256和预测数与快照一一覆盖，严格禁止测试数据回流训练 |
| 验证集阈值校准 | `calibrate-model-score-threshold.py`；只接受来源隔离val证据，绑定数据/权重/预测哈希，少于30图、真值polygon需修复或质量约束不满足时禁止生成manifest阈值；`--verify-report --expected-weights`用于导出前只读深验 |
| 派生区域标注审计 | `verify-reviewed-region-annotations.ts` |
| 派生区域入库构建 | `build-reviewed-region-intake-batch.ts` |
| 训练 | `train-yolo-seg.py` |
| 评估 | `evaluate.py`、`assess-model-metrics.py` |
| 来源隔离实验集增量构建 | `extend-source-isolated-dataset.py`；从已审计快照加入授权样本，禁止新增项进入 test，并对冻结 test 图片与标签做逐文件联合 SHA-256 校验 |
| 导出/量化 | `export-onnx.py`、`quantize-onnx-int8.py`；候选导出必须使用`--candidate-mode --calibration-report`派生阈值并写入`scoreThresholdEvidence`，禁止手工阈值绕过 |
| 浏览器烟雾模型 | `build-browser-smoke-model.py` |
| 发布门 | `scripts/verify-*.ts`、`scripts/run-*-pipeline.ts` |
| 发布治理 | `register-model-release.ts`、`switch-model-release.ts`、`promote-approved-release.ts` |
| 最终完成度审计 | `audit-nail-texture-local-inference-completion.ts`；核对实施规范清单、全部关键证据和生产资产，缺证据时输出HOLD及责任方；用户/工程清单必须非空、候选checkbox格式合法且文本唯一，所有候选进度行必须可解析且标记ID唯一。`--evidence-profile`与四个受保护证据CLI覆盖互斥，profile精确绑定绝对路径、SHA-256、候选权重和部署阈值，加载及写报告前双重验哈希，并校验冻结质量`full_512`、指标权重和困难负样本审计使用同一候选。困难负样本独立强门继续固定要求`independent-holdout`、不少于100张、三变体零误检/零delta，profile或手写外层PASS不得改变审计结论 |
| 外部验收证据 | `build-nail-texture-device-acceptance.ts`、`build-nail-texture-beta-review.ts`、`build-nail-texture-user-failure-cases.ts`；由已验证原始报告或CSV生成总门稳定JSON |

真实训练在本地 Python/Ultralytics/PyTorch 环境执行，不需要在训练循环中调用 GPT。GPT 或其他视觉模型只能作为素材生成、辅助标注或审核工具，生成结果必须经过授权与人工质量控制。

`sam-assisted-nail-annotation.py` 的失败报告会包含具体提示序号和提示模式；mask轮廓转换失败也会记录对应序号。报告中的推理成功只代表候选已生成，仍必须查看原分辨率overlay，整图所有应标甲面完整且无皮肤/背景污染后才能复制到正式审核目录。

### 8.3 real-prelabel-v3 隔离工程验证

`nail-texture-seg-real-prelabel-v3` 仅用于提高人工审核候选召回率，不是正式发布候选。其 512 FP32 ONNX 已完成以下轻量工程检查：

- 文件大小 11,566,101 字节（11.03MB），低于 15MB MVP 上限、高于 8MB 理想值；
- manifest SHA-256 `280a2ff809231ee07130ea350469b26ccd34ab086904c5434c7fa095e1dbb4b8` 与实际文件一致；
- ONNX Runtime 实际输出为 `[1,37,5376]` 和 `[1,32,128,128]`；
- TypeScript 后处理 fixture 解码得到 5 个带 mask 候选；
- 该批次现已获得正式授权，但此历史产物训练时使用的是未完成人工闭环的候选标注，且没有通过正式独立质量门；因此仍只允许辅助标注，不得覆盖生产 manifest、注册或 promotion。

仅使用当前授权正式集训练的 `nail-texture-seg-real-seed-v1` 已在 46 张独立 test 上复评：box mAP50 为 0.380，mask mAP50 为 0.367；相对 512 合成基线分别下降 0.143 和 0.101，均超过 0.02 退化上限。质量门按预期拒绝该候选，因此不继续导出、注册或发布。

### 8.4 真实候选 v4–v9 结论

v4—v9 均为历史候选，逐候选明细与耗时证据已迁至 `docs/archive/whitepaper-dataset-contract-history.md`（C 节）。其中 v6 曾是通过历史 13 张独立真实精度、模型资产、输出协议和桌面 WebGPU 热性能门的候选，但冻结 67 张扩展发布测试在部署 512 下全量 box/mask mAP50=0.8370/0.8313、压力组退化超过 0.02，正式拒绝发布；v7/v8/v9 以 v6 权重续训后 box 均未达 0.85 且两项较 v6 退化，质量门拒绝，未导出 ONNX、未注册、未发布。

仍然生效的契约：

- 冻结 67 张阈值画像暴露共享固定阈值不利于模型版本独立校准：浏览器现已支持由 manifest 携带模型级 `scoreThreshold`，在原始候选和质量排序两道过滤中统一生效；旧 manifest 仍用 0.35。诊断点 0.25 未写入生产 manifest，v6 拒绝与 HOLD 结论不变。
- v6 原始来源隔离实验集的 13 张 val（来源组 `more`）mAP 0.9376/0.9420 与阈值 0.20 **降级为基于不合格真值的历史诊断**：终审确认存在无效 polygon、未声明交叠、漏甲、背景/雕塑误标、重复 mask、皮肤污染、边缘裁断与域外空标签，最终整套 split 输出 `rejected_as_calibration_truth`。这些数值不得用于模型选择、候选比较或 manifest；`manifestScoreThreshold` 继续为空，下一轮必须另建不少于 30 张且全部视觉通过的来源隔离 val。
- 将该拒绝审核报告显式传入新版校准器会输出 `diagnostic_only_validation_truth_rejected`、`calibrationEligible=false` 与 `manifestScoreThreshold=null`；视觉门是校准代码的实际阻断条件，而非文档约定。
- 正式 409 图集的来源审计输出 `rejected_dataset_source_isolation`，候选验证审计输出 `rejected_candidate_training_validation`（AI 来源组跨 split、缺少 46/46 视觉审核、5 处 polygon 交叠）。该拒绝报告传给候选模式时，即使 `--dry-run` 也会在模型加载前报 `candidate validation report is not approved`；普通实验路径仍兼容但摘要标记为 experiment。
- 当前无批准发布候选，生产 promotion 保持 HOLD。

### 8.5 来源审核整图页接口（schema3，2026-10-10）

`build-native-source-pair-review-v3.py`使用既有`--queue/--plan/--output/--target-sha/--native-registry`参数，输出不可覆盖schema3包：新图优先完整PNG页，继承图保持原实看页绑定；图片身份、RGB SHA-256、角色与全部图对观察不改。`--tile-sha`仅允许指定本包新图，在新输出版本选用原像素分块；整图缩放失败不可转成通过或覆盖原包。备用页只作回退候选，不记实际查看。

`images[].nativeLayout`为`whole`或`tiles`。完整页仅一张，尺寸等于原图，唯一`sourceBox=[0,0,w,h]`、`pageOrigin=[0,0]`、`resampling=false`；分块保持660x800来源网格与40px页眉。`record-native-source-image-review.py`绑定实际查看的当前页与`toolScalingNotice=false`，不自动批准视觉、mask、来源独立或训练。

`audit-native-source-review-pages-v3.py --report <report.json>`逐图核验字节身份、原RGB、布局全覆盖、每块像素和实际查看/继承绑定；拒绝重绑定像素漂移、缩放、缺页/错序、未知布局与继承模式漂移。`native-source-page-layout.py`在解码前安装等价只读图片守卫并finally清labels cache。旧schema1/2构建器/审计器不修改，旧证据可完整继承；全部结果只表示来源审核保真，发布门不变。

发送量记录要求：发送前按页SHA与实际文件字节列本批新页/继承/必要重看，完整实看已绑定页复用不重发；文件字节或base64估算不能替代网络计量，缺请求级日志不能宣称无重传。原像素质量门及持续上传授权保持，具体本地统计见实验历史归档§12.297。

请求体积与网络计量须分开：本机请求日志可能含百MB级压缩准备字节，不能以本批唯一图片体积推断总请求；发现大请求先停止增图并保存线程/压缩字段。推送重连不证明推理重传，TUN进程总量不自动归属Codex，完整诊断及未闭合项见实验历史归档§12.298。

### 8.6 已知图对原RGB数值诊断接口

`native-source-grid-diagnostic.py`提供固定网格全覆盖、RGB uint8域/float64误差、五核诊断缩放和正控门；`diagnose()`正控失败时不计算候选，所有结果nativeVisualApproved/sourceParentIndependenceQualified/trainingAllowed恒false。`guarded_rgb_sources()`在只读守卫成功后解码/复核完整RGB，callback内完成像素评分后finally清缓存；源质量、mask及角色资格另审。该模块不扫描语料、不生成图片或执行模型，当前真实方法失败见实验历史归档§12.300；固定fixture无需私有报告/一次性脚本。

### 8.7 已知正控局部配准诊断接口

`native-source-registration-diagnostic.py`提供仅内存SIFT双向匹配、明确镜像/像素中心变换、全幅几何/光度与错误位置控制；不解码路径、不调用神经模型。调用者须先经原RGB只读守卫并绑定方法合同，返回估计对应不等于目视格位或来源资格；candidateSourceCount=0且nativeVisualApproved/sourceParentIndependenceQualified/trainingAllowed均false。当前方法真实失败见实验历史归档§12.301。算法API参照[OpenCV官方教程](https://docs.opencv.org/4.13.0/d1/de0/tutorial_py_feature_homography.html)，本机OpenCV5.0.0运行时及fixture另绑定，不以文档版本代替实测。

### 8.8 来源关系分型与必要重看合同

现行分型合同1区分同摄影帧变换、拍摄系列视觉关联、仅风格相似、可见不同及不确定；拍摄系列关联不作像素复制正控，数值候选继续禁止，完整源/角色父血缘/实际查看及无缩放分别绑定。完整图片输入遵循用户整图政策v5（`model/reviews/cycle016-user-whole-image-batch-review-policy-v5.json`）：单批及单张作为批的一部分≤50000000字节、每响应≤6独立整图、不另设整轮上限；已看完整事实按精确SHA继承，不重发旧分块。发送前冻结实际文件/页面SHA及字节，尝试采集当前线程近时请求；遥测缺失如实记未知并允许有界发送，不记为测量门通过，已观测准备请求≥100000000字节时停止增图。文件、base64估算及实际网络流量分别记录，实际缩放拒绝原像素结论。旧I016等4MiB页/8MiB请求及未知拒发限制只作历史保留，不能覆盖后来用户明确的50MB单批政策。该更正不放宽原像素质量、来源/完整mask、数据角色或发布门；具体历史编号见实验归档§12.302，最新整组实例见当日日志。

既有18源11组106甲/118输入的供给链见`model/reviews/cycle016-6cba-group-review-v1/`和`cycle016-6cba-supply-closeout-v1/`，原角色、真值和历史失败不改写。最新最大组开发扩量的已知来源召回关系与35甲原尺寸输入分别见`cycle016-expansion-family-pairs-v1/`和`cycle016-expansion35-baseline-v1/materialization.json`；只授予本开发合同范围，不构成正式来源独立、全split资格或发布通过。当前研发训练见§11.1。

内部开发诊断的角色/真值读取以`cycle016-internal23-development-diagnostic-v3/report.json`为当前范围：29条内部val真值中27条曾入候选、4条后来源质量排除、23条保留，另2条在候选范围外，禁止把后者改记质量排除。逐甲旧证据须按实际sourceIndex或targetIndex及对应实看字段继承，不能以空train真值槽判val缺标。当前来源裁决补充见`cycle016-internal23-family-ef82-v1/`与`cycle016-internal23-family-e93-v1/`；同既有相册不同手姿照片保留拍摄关联和历史val角色，不成为独立来源。余192对关系与实际候选域未闭合，整23源132甲诊断仍禁止，不能按已闭合子组缩分母启动。

原153开发训练真值资格仍撤回，原追加裁决`model/reviews/cycle016-reference-shadow-review-v1/current-qualification.json`及历史失败不改。完整22源处置现见`cycle016-train153-truth-reaudit-v1/report.json`：五枚污染甲返修通过；源5另露截断甲面整源排除，源8/9/10历史派生图缺父SHA/来源组、三整组保持未决。误发6裁片页不追认整图通过，原角色与全部分母保持；其余18完整源123甲/11候选拒识以`cycle016-requalified134-native-v1/report.json`及`replay.json`建立独立版本的134开发域，原坐标完整、RGB/粗mask不改、原153指标同构。新域只授予开发训练，不授予正式来源独立或发布许可；旧distance-readiness仍失效。

公开六原图、紫色五甲仅诊断及2张GET429未取得继续保留。原26源136甲18组差集内3源18甲已StageA开发训练、dced1源8甲保留已消费对照且不回训；591f/f4f两源8甲整组12图对及完整原像素真值资格见`model/reviews/cycle016-591f-family-admission-v1/report.json`和`model/reviews/cycle016-f4f-family-admission-v1/report.json`及各replay/precision实审。全局v61为2315=822新裁决+17继承+1476未决、7不确定，余20源102甲13组关联832未决仍训练禁止。两源全11候选归属已完整实审，3额外项为同甲局部重复/文字皮肤/手套褶皱；保留原train角色/8甲/标注不变，现已加入StageB开发训练，不充正式未见留出。现行23源149完整训练甲/5同候选拒识、154身份及462固定视图合同见`model/reviews/cycle016-two-source154-v1/materialization.json`及`materialization-replay.json`；全部162原始输入含原保留8，其训练视图始终0，内部val不回流。旧物化/角色/失败保留原报告，可见不同仍不等于正式来源独立。 当前149训练真值的完整原图距离目标、154身份/462视图与全162最终输入完整继承，保留8目标/训练均0；现行绑定见`model/reviews/cycle016-pretrained-context-v2/materialization.json`/`materialization-replay.json`，上游完整距离派生重放仍保留`cycle016-distance154-v1/`，不新增图片/角色或正式资格。

### 8.9 学得原尺寸候选的精度复验接口

`refine-mask-with-grabcut.py::refine(rgb, mask, presence_accepted, radius=8, iterations=3)`与`refine-mask-with-edgecut.py::refine(rgb, logits, presence_accepted, radius=8, weight=1)`仍为隔离开发接口，两分支关闭。旧StageA完整新3源18甲基线联合门0/18，同种子一一ROI上限13/18，固定该候选和ROI仅改StageB不可达85%完整mask要求；旧统一presence无解/固定presence仅改mask头2/5上限、紫色五甲及原8甲边界失败保持。

新StageA固定30轮的覆盖提升及整体开发门false仍见`model/reviews/cycle016-stage-a21-v1/`，149/149几何容纳不是边界通过。全22源149甲151候选原生StageB基线见`cycle016-full149-stage-b-v1/quality-report.json`/`quality-replay.json`，旧123严格联合9、新18和保留8均0，两额外候选未拒识。

新候选143输入（141完整甲面、同候选局部重复/皮肤拒识各1）另立开发训练，固定60轮/8580增强输入/2160优化步/151最终两头RAW，整数旋转翻转及光度增强逐次重放。固定最终旧123联合8（9基线中4退化、3新恢复）、新18和保留开发8均0，141正presence全部接受、两拒识零输出；开发门false、分支关闭。见`model/reviews/cycle016-newcandidate143-v2/run/report.json`、`replay.json`及完整`preview/index.html`。不更改生产权重/阈值或转授旧数值通过。

粗候选自动提示SAM2.1-L有限基线现见`model/reviews/cycle016-seeded-semantic8-v2/quality-report.json`/`quality-replay.json`及完整`preview/index.html`：先新增过滤前全量观察控制，续接原未消费单次完整8甲真图，权重/提示/公开conf不改。原控制4/8失败保留，现行全8项真实输出严格联合0/8、IoU0.58981且皮肤/缎面污染，固定分支关闭，不扩提示。峰值CUDA allocated1498892288字节、单真图主机墙钟2.805秒含RAW保存，不代表浏览器性能或完整峰值成本。

当前开发结构`model/training/native-pretrained-context-refiner.py`继承原生四通道RGB+粗mask、mask/presence两头及固定先验/阈值，在原上下文精修上复用现有StageA已训练骨干4/6/10层的stride8/16/32特征；骨干冻结、始终eval，三个零初始化1×1投影仅向mask路径添加语义残差。输入RGB从现行float32 ImageNet归一化反变换、舍入回原整数格点后/255，仅右下pad32（114/255），不缩放RGB；骨干原点0、原生quarter中心4*i+1.5显式双线性采样，禁止将pad范围压缩映射回ROI。presence仍读取原e3；60张量414802可训练参数及1365472冻结骨干参数（240状态含BN）。原完整损失和0.25距离辅助项保持，原像素真值/角色不变。8项针对性测试、独立1536非零控制/全162热启动两头精确/462梯度预检重放通过；学得图当前合成接口资格见下方；真实图片、完整产品及正式部署资格未授予，不继承旧数值通过。

上一上下文结构分支见`model/reviews/cycle016-context143-v1/run/report.json`及`training-replay.json`；原开发门false、固定分支关闭，作为本次新监督配方的显式初始化和基线，不追认旧失败或转授部署资格。

存档损失分析`model/reviews/cycle016-native-loss-alignment-v1/analysis/report.json`及`replay.json`已闭合：全151前后质量同构、2损失控制、143训练身份前后286次损失及完整输出梯度数组重算。旧/新最终错误32445/17224像素，完整梯度方向正确32385/17187、零梯度均0；不支持单以损失无约束解释失败，也不证明网络参数优化或泛化。保留8仅重建旧质量，无新损失。两组精细真值及12对关系已闭合，新开发全链路基线见下段；开发资格/诊断不自动改变现训练集或正式保护角色/质量门。旧粗mask数学诊断及全部历史失败保持原报告。

上一闭合训练见`model/reviews/cycle016-paired154-v1/plan.json`、`run/report.json`、`training-replay.json`与`quality-migration-replay.json`，原147/149、压力45/298和完整开发门false保持。147已通过mask的原图保持、全部154 presence及完整真值监督仍是当前配对基线；失败教师mask不蒸馏。

最新闭合训练见`model/reviews/cycle016-normalized154-v1/plan.json`、`training-replay.json`、`quality-migration-replay.json`和`failure-attribution-v2/report.json`。通道均值/方差规范化配方已完成固定60轮、18480训练前向、2340更新和462最终RAW的完整重放。原图146/149，旧147中147/150两项退化、151恢复，压力220/298（暗暖146/149、亮冷74/149）；正presence149+298及拒识5+10均过，但完整开发门false，分支关闭、保留原147/149模型，不追加轮数或换阈值。仅训练域，无新来源泛化结论；调整8/10（微调6次），产品HOLD。 `native-photometric-normalization.py`及对应mjs仅属关闭实验：原尺寸RGB通道均值/标准差下限1、映射0.5/0.2、clamp及偶数舍入uint8；1386实际输入Python/JS完整缓冲一致不证明mask质量。现保留模型不加入该预处理，源图/纹理/坐标/真值/角色和全部原参考不改写；固定20/50分位零推理替代未过稳定门，未训练。

离线Qwen仅定位试验见`cycle016-qwen3-v1/localization-closure-v2.json`：冻结3整图22甲，原裸StageA资格门仍可达且未执行；重建实际接受集合22/22、0额外后，当前端到端仅定位严格增益余量0，基于目标相关收益关闭分支。Qwen图像输入0、无蒸馏/效果结论，部分官方权重下载已停止，不能据此否定像素教师或SAM能力。

当前技术实施总合同见`docs/nail-texture-local-inference-implementation-spec.md`v1.11 §6.1/§6.3：Stage A 512候选、Stage B原尺寸四通道及mask/presence双头、完整原图坐标逆映射。当前修复仅Stage B合成接口通过；真实输入、Stage A+B完整Worker/Canvas及发布身份仍须验收，旧单阶段manifest例子不构成双阶段生产合同。

上一冻结RGB基线完整执行见`model/reviews/cycle016-pretrained-context-v2/plan.json`、`preflight-replay.json`、`run/report.json`及`training-replay.json`：23源149正/5同候选拒识154训练身份、462视图，独立固定60轮/9240训练输入/2340更新，全部162最终RAW/157真值及143训练基线保留、6取证checkpoint和全部事件重放。训练域旧123/123、新17/18及新两源7/8，143基线零退化、149正presence全接受、5拒识零像素，开发门true；147/149属于训练域，不是正式准确率。原保留开发8训练0、最终诊断0/8，不用于选择。全部60训练张量改变、240骨干状态完全不变；预检与训练CUDA allocated1273385984/559591424字节不代表浏览器/完整流程成本。此前距离分支开发门false仍保持`cycle016-distance154-v1/`原报告；距离目标/损失合同见`normal-stage-b-distance-loss.py`和其`loss-value-replay.json`，不将本轮增量全归因新结构。已完成的新图独立导出/控制见下段；该阶段展示账为3次微调，当前调整计数见本轮训练段；无新成果视觉通过或生产切换。

当前完整图导出接口`export-native-trained-fullchain.py`提供真实300状态严格加载、原尺寸双头导出、严格FP32 CUDA/CPU ORT及完整RAW/事件重放。`onnx-native-fullchain-repairs.py`组合16处同epsilon的float32分块归一化、4处3×3空间分段和最终1×1分段；其后`onnx-blocked-presence-reductions.py`仅改三处Sum/Mean为同float32三级128分块累加。各变换逆序恢复原完整ONNX字节，全部原权重、偏置、阈值不变。生产接入仍须真实输入与整条链验收。

当前完整部署控制见`cycle016-presence-stable-independent-v1/report.json`和`cycle016-presence-stable-learned-v1/report.json`：独立非零及真实训练权重分别全27输入54RAW，各三后端九尺寸达到两头绝对1e-4、解码零像素差和presence一致门，包含1536方形与极端长宽比。真实模型未改300状态；同一实际图修复不因独立/学得验证重复计数。旧`cycle016-fullresolution-partition-v1/report.json`、首次学得WASM7/9及全部历史失败保持；合成通过不授正式质量、性能或发布资格。

当前边界观测接口`audit-pretrained-native-boundary.py`提供实际图只增enc1.0输出、原图字节回剥、严格CUDA捕获及`verify-cuda`/`verify-all`零推理重放；`serve-pretrained-boundary-capture.py`提供绑定完整9输入的WASM/WebGPU捕获。最终头保真按全部输入逐后端原始字节校验，全部27输入/81张量完整有限及54最终头通过后才允许层统计，否则`reconstruction_mismatch`且拒绝归因；同请求SHA/长度/身份一致的有界传输重试不重跑模型。当前完整门通过见`model/reviews/cycle016-pretrained-first-boundary-v1/report.json`：WASM首卷积全9最大差1.90735e-6，WebGPU前8为2.38419e-6，1536为8.602846。首卷积同输入隔离已完成，当前结论见下段；较小8例最终失败仍需后续定位，学得模型与正式发布资格不变。浏览器完整进程峰值与端到端成本未验收，文件/HTTP载荷字节不能冒充实际网络流量。

当前单卷积隔离接口`audit-onnx-conv-isolation.py`保留原节点/初始权重、同9输入及严格CUDA边界，提供CPU执行与完整RAW/事件重放；旧28控制及原WebGPU1536失败保持`cycle016-firstconv-isolation-v1/report.json`。现行分段转换`onnx-spatial-partition-convolution.py`对原3×3/stride1/pad1无bias卷积采用显式零padding、4个动态高度段/完整halo及Concat，全部原权重不变，原图可逐字节回剥，16..1536整数高度覆盖无丢失/重复。`audit-partitioned-conv-controls.py`及`serve-single-output-controls-v2.py`提供同9三后端单输出捕获、实际ORT设备limits及零推理重放；实际申请描述符未拦截，不把源码策略当申请实测。当前`model/reviews/cycle016-partitioned-firstconv-v1/report.json`全27数值通过，WebGPU最大3.33786e-6；实测/实际ORT设备上限65535、分段最大18432。完整图已实际验收但WebGPU未过，现行失败见上段；单算子通过不得转授完整图或学得部署。

只读诊断接口`onnx-observe-normalization-moments.py`与`onnx-observe-presence-reductions.py`仅增加既有输出，配套服务独占保存RAW；原图字节回剥、CPU/WASM全九尺寸36原最终头全字节保真后才允许层统计。当前分别18输入612RAW及18输入126RAW通过保真，首次学得WASM两项失败仅presence标量；同输入float64归约反事实不是实际模型输出。新float32归约修复实际全27通过见上段。提交原因跟踪已分开7948计算、144观察读回、2179独立上传及9空flush；原7948=8065错误合同失败不追认，原未加观察的117读回与本观察新增27读回分开，见`cycle016-submit-boundary-v1/report.json`。最新完整真实训练域合同见Goal，所有旧跟踪/缓存/准备失败及已消费预算保持。

`export-trained-native-candidate.py --scope <冻结范围> --output <新目录>`仅导出开发候选并核验全68存档Torch/CPU ORT；输出隔离ONNX、float32缓冲及`report.json`，CPU门失败时禁止浏览器准入，不修改生产manifest。

`audit-trained-native-precision-v2.py --plan <冻结计划> --output <新目录>`在同权重、全68候选上显式关闭CUDA两类TF32，持久化CPU Torch及严格CUDA两头RAW，分别复算旧部署数值失败与严格FP32独立容量；`--verify-report <报告>`只读重建全部比较、逐甲质量、角色和绑定，无新增模型调用。严格参考不得替换旧TF32存档追认旧部署通过。

`audit-native-ort-optimization.py --plan <冻结计划> --output <新目录>`固定ONNX字节、CPU线程4/1及全68输入，只把图优化设为`ORT_DISABLE_ALL`；`--verify-report <报告>`从实际缓冲重放两头有限、数值≤1e-4、存在性与解码0像素差。报告`ok=true`只证明重建正确，实际CPU门须读取`strictFp32CpuGatePassed`；当前为false。所有路径优化0、val/保护输入0，保留旧失败、预算和正式HOLD。

`audit-native-layerwise-parity.py --plan <冻结范围> --output <新目录>`只增加ONNX中间输出，持久化全68候选的CPU Torch/严格CUDA/CPU ORT两头与逐层float32张量；只有最终两头逐字节保持未插桩输出后才重建层级误差。`--verify-report <报告>`只读重放完整分母、图结构、形状、有限值及字节绑定；失败须拒绝层结论。

`audit-native-saved-operators.py --plan <冻结范围> --output <新目录>`用已捕获的同一输入隔离两处双线性插值和末级GroupNorm，全68分母、原尺寸、epsilon与学习仿射固定；不新增完整模型前向或训练。`--verify-report <报告>`重建全部算子误差并验证严格CUDA归一化输出与原层存档逐字节一致。两类诊断的`ok=true`只证明重建正确，不能代表部署/模型质量通过；旧失败和正式HOLD保留。

`onnx-native-bilinear-resize.py`只展开目标Resize的原尺寸half-pixel坐标与邻点加权，未选节点、学习参数、归一化及其epsilon字节保持。`audit-native-resize-repair.py --plan <冻结执行> --output <新目录>`按全68同输入算子、确定性非零未训练控制、同权重全68 CPU三门串行执行；`--verify-report <报告>`从RAW、图结构与权重绑定重放，实际门读取`operatorStagePassed`/`nonzeroControlGatePassed`/`learnedCpuGatePassed`，重建ok不覆盖失败。

`serve-trained-native-browser.py --plan <冻结范围> --output <新目录>`准备完整68输入及CPU批准ONNX的浏览器页，`--serve --output <目录> --port <回环端口>`仅提供哈希绑定资产与一次性事件/RAW捕获；全部136个双后端非零控制通过后才执行136个学得输入。`audit-trained-native-browser.py --root <捕获目录> --output <新报告>`及`--verify-report <报告>`核验实际事件、形状、两头有限、1e-4/完整解码0像素差/存在性门，`learnedBrowserGatePassed`才表示浏览器通过。当前false；内部val及正式发布仍禁止。

`audit-repaired-native-browser-layerwise.py --execution <冻结执行> --output <新目录>`仅在已修复图增加31个输出，CPU68保真后准备回环WASM/WebGPU；`--serve`提供精确字节捕获，`--audit`/`--verify-report`只读核验三后端全68两头字节一致后解释层误差。当前执行中断，完整门为reconstruction_mismatch，不得据部分RAW给出全量层结论。

`serve-native-capture-transport-probe-v2.py --output <新目录>`仅准备合成字节正控，`--serve`提供回环页，`--audit`/`--verify-report`核验应答丢失与保存前明确HTTP错误的恢复；模型输入0，响应体须消费，ACK/状态须同时绑定SHA和字节数，重试只补传文件。当前正控通过，不证明原Failed to fetch根因；首版断连未触发预期JavaScript错误的失败保留。

`continue-native-browser-layerwise.py --execution <冻结续接执行> --output <新目录>`仅准备尚未执行的浏览器输入，不新增CPU/Torch前向；`--serve`以唯一页面/输入UUID认领、SHA/字节ACK及已保存状态查询捕获，补传不重复模型。`--audit`/`--verify-report`合并已绑定旧RAW并先核验三后端全68最终两头逐字节一致，再按明确缺层分母解释。当前续接114输入通过，28层全68、末3层CPU68/WASM67/WebGPU68；原中断失败及WASM22缺层不填充、不改写。该诊断通过不代表学得浏览器数值门通过。

`audit-native-browser-tail-operators.py --execution <冻结执行> --output <新目录>`以全68相同严格CUDA存档输入和原输出参考执行三算子CPU隔离并准备浏览器页，`--serve`提供一次性事件与SHA/字节捕获；`--audit`/`--verify-report`重放CPU/WASM/WebGPU各204输入的形状、有限值、身份与数值误差。`ok=true`只证明重建，`allOperatorNumericGatesPassed`为实际隔离门；当前false（WebGPU末级插值4项超2e-5）。完整模型/Torch/优化/val/保护输入0；隔离通过不能晋升完整模型或内部val。

`audit-native-browser-precision-trace.py --execution <冻结执行> --output <新目录>`只新增算子图输出，准备CPU追踪与FP64诊断统计，`--serve`执行固定浏览器范围；`--audit`/`--verify-report`须先逐字节核验全范围原算子结果再返回坐标/统计结论。当前WebGPU插值保真失败，审计返回 `reconstruction_mismatch`，不产生通过报告。`audit-native-trace-fidelity.py --input <失败追踪目录> --output <新报告> [--verify-report]`仅重建全分母开始事件、所有张量、传输和原结果变化；其 `ok=true`是失败盘点可重放，`allFinalOperatorOutputsBitwiseIdenticalAllBackends=false`、`intermediateTraceConclusionsAllowed=false`，不得追认追踪或模型质量通过。完整模型/Torch/优化/val/保护输入0，合成控制须独立绑定且不构成学得质量证据。

`audit-native-trace-observability-control.py`及`audit-native-trace-observability-copy-control.py`以 `--execution <冻结控制> --output <新目录>`执行CPU合成控制并准备浏览器页，`--serve`仅回环捕获，`--audit`/`--verify-report`重放每变体对同后端原单输出的字节保真。合成控制中直接公开向量失败，副本观测通过；不证明学得模型质量。`audit-native-trace-observability-combined-control.py`提供组合观测执行；其旧审核44/68计数缺陷保留，组合结果必须经 `audit-native-trace-observability-combined-replay.py --capture-root <目录> --output <报告> --contract <新只读合同> [--verify-report]` 按完整模型/输入清单派生张量分母。只读修复不重跑控制或追认原工具通过。全68副本追踪须另立范围，仅允许4个不馈入原节点的Identity副本，原节点/学习参数及最终输出不变；先过各后端原算子结果字节保真门才解释中间值。

`onnx-native-joint-fullmodel-v2.py`按每图冻结的四个比例Div输出及末级GN语义节点新增resizeRatios float32[4]，仅替换四Div为Gather，并在末级GN原128分块后追加128级求和；回剥须恢复原图字节，权重、epsilon及其余9个GN不变。`audit-native-joint-fullmodel.py --execution <冻结执行> --stage control|learned --output <新目录>`执行CPU全68并准备捕获页；`--serve`仅监听回环、按一次性认领捕获WASM/WebGPU，逐输入核验四比例字节；`--audit`/`--verify-report`重建全204两头、开始事件、源与运行时绑定。任一学得输入前须重放全204非零控制通过；ok=true仅表示重建通过，allThreeBackendStageGatesPassed与fullModelLearnedGatePassed单列。旧父图控制通过、学得WASM40失败保留；现行首GN修补完整图接口见下文。既有hostRatios float32[2]隔离工具及全612结果保持；新完整候选接口仅用于本地开发证据，生产接口与manifest不变。正式1e-4/0像素门不变。

`audit-native-joint-fulltrace.py --execution <冻结执行> --stage control|learned --output <新目录>`只执行新增31输出图的CPU全68并准备回环页；`--serve`按独占事件捕获WASM/WebGPU实际33输出，`--audit`/`--verify-report`按真实输出名、原尺寸、float32有限值、完整候选与存储字节重建。先重放控制204对各自未插桩双头的字节保真，才允许学得输入；学得204全保真后才返回31层误差。ok=true是重建通过，allOwnHeadsBitwiseIdenticalAllBackends与layerConclusionsAllowed单列，首次跨门不证明根因。当前双阶段保真通过、WASM40首跨门在dec1.4；原完整候选1e-4数值失败不变。GN64解析已闭合，当前接口见下文；原float32 CUDA参考、epsilon与参数存储域不变，生产接口与manifest保持。

`analyze-native-groupnorm-decomposition.py --execution <冻结执行> --output <新目录>`以完整同候选CUDA/WASM原float32输入、原仿射及epsilon计算136次GN64数学结果，保存float64 RAW、统计和逐坐标输入传播/两端舍入分解；`--verify-report`按全68身份、原模型初始化器字节、原存储域、开始事件和GN64闭式结果重放，分解残差门1e-12。数学参考不替换CUDA或生产输出，ok=true只表示完整解析重建，fullModelLearnedGatePassed保持false。当前WASM40理想GN仍在该层超1e-4，末级Conv64已闭合，现行接口见下文；生产接口与manifest不变。

`analyze-native-convolution-decomposition.py --execution <冻结执行> --output <新目录>`以完整同候选CUDA/WASM原float32输入和原无bias核计算136次Conv64数学结果。单线程BLAS及动态库字节固定，4096输出像素分块覆盖完整原尺寸与零填充邻域；原卷积节点/核初始化器字节不变，持久化float64 RAW、全68有符号分解和开始事件。`--verify-report`逐字节重放数学输出、统计、身份与原追踪层差异，残差门1e-12。当前WASM40同最大差坐标主要为输入传播；ok=true只表示完整解析重建。四分支尾链反事实已闭合，原最终mask的seed+delta字节保真；当前接口见下文。反事实不批准实际FP32修补、不证明全模型不可达，正式接口和manifest保持。

`analyze-native-tail-counterfactual.py --execution <冻结执行> --output <新目录>`以全68四分支解析GN64/GELU64/delta64及最终mask相加，136份GN64继承、952数学阶段另记；原参数、float32常量位值及CUDA参考保持，最终mask只舍入一次float32、presence继承原分支。单线程BLAS与SciPy Erf二进制固定，持久化952开始事件、1224原尺寸RAW和68记录。`--verify-report`逐阶段/逐字节重放结果、原seed+delta保真与原双头比较；ok=true仅表示完整重建，actualFp32RepairOrWholeModelUnreachableProven和fullModelLearnedGatePassed始终false。当前两个WASM分支仍仅40数值失败，两个CUDA分支通过数学诊断门；不支持只修末级Conv/GN，以dec1.0实际输出为起点的双分支已闭合，当前接口见下文。正式接口和manifest保持。

`analyze-native-decoder-counterfactual.py --execution <冻结执行> --output <新目录>`以全68原dec1.0输出双分支计算两组GN/GELU、中间无bias卷积、真实bias的delta及原seed相加；首输入float32提升一次，保持float64传播至最终mask舍入一次float32，presence继承。单线程BLAS/SciPy运行时固定，952阶段事件、1088原尺寸RAW与68记录持久化；`--verify-report`逐阶段逐字节重建原参数/常量、原输出头保真及双头比较。当前两分支通过数学诊断门、WASM余量约4.51e-6；actualFp32RepairOrWholeModelUnreachableProven/fullModelLearnedGatePassed仍false。首GN实际隔离已闭合，接口见下文；数学结果仍不证明完整模型通过。正式接口和manifest保持。

`audit-native-first-decoder-gn.py --execution <冻结执行> --stage original|patched --output <新目录>`固定原始/候选图与全68双来源136上下文，各阶段CPU/WASM/WebGPU共408，原始全408同输入float64参考及原尺寸float32有限门通过前禁止候选。`--serve`通过独占页面/输入UUID、开始事件、精确RAW及ACK捕获真实浏览器；`--audit`/`--verify-report`重建全分母、原始准入、来源/环境/字节及数值门。当前816全部闭合，ok=true只证明重建，allOperatorNumericGatesPassed另列；完整模型/Torch/优化/val/保护输入0。

`analyze-native-operator-stage-comparison.py --execution <冻结执行> --output <新目录>`只读重建原始/候选全部408配对上下文，同FP64参考不舍入；逐项保留改善、退化与同值，核验68项原始WASM同来源输出与完整图首GN字节一致。`--verify-report <报告>`逐缓冲重放；当前WASM最大误差改善约8.14倍仍仅是算子诊断。后续完整图已闭合，当前接口见下文；正式manifest/身份及质量门保持。

`audit-native-first-gn-fullmodel.py --execution <冻结执行> --stage control|learned --output <新目录>`按两图实际首GN语义目标205/191，仅追加mean/variance的128级求和并精确逆变换恢复父图；全68原输入、四主机比例、非零控制与严格CUDA原双头参考固定。先控制204全门通过才允许学得204；`--serve`独占页面/输入事件并捕获真实两头RAW，`--audit`/`--verify-report`重建全分母、原尺寸float32有限、数值1e-4、解码0像素与presence门。当前控制/学得全部通过，ok=true仅为重建，fullModelLearnedGatePassed另列且仅覆盖开发输入；生产接口/manifest不变。后续完整内部val已执行，数值/质量未过，现行接口见下文；原train通过及val失败分别保留，禁止推定正式来源独立或发布通过。

`verify-reviewed-internal-val-inputs.py --scope <冻结范围> --output <新报告>`安装只读图片守卫后，独立重建内部val全部56原像素RGB/粗mask归一化输入及主机比例的112个float32文件，逐项核验角色、候选/目标/裁框与原像素SHA。完整10源50甲、49正候选/7拒识与1无候选甲不缩减；缺候选真值禁止伪造模型输入。`--verify-report <报告>`只读重建相同结果，结束清理cache；ok=true只证明输入及分母保真，新模型调用0，禁止回训、正式阈值校准或来源独立晋升。

`audit-reviewed-internal-val-native.py --execution <冻结执行> --stage control|learned --output <新目录>`对完整内部val56候选先严格CUDA56再CPU56，并由`--serve`独占回环页捕获WASM/WebGPU各56；控制224全部数值/解码/presence门通过前禁止学得224。原norm、权重、候选与原尺寸float32两头固定，CUDA/cuDNN TF32及autocast关闭；`--audit`/`--verify-report`只读重建开始事件、RAW、实际环境/源及全预算，不重跑模型。严格CUDA的自比较不冒充独立后端证据。学得质量按uint8 L/128真值、原float32 logits/0及presence/0解码，全10源50甲含1无候选甲，49正候选/7拒识分别报告原图2像素边界、逐甲/源汇总与Wilson95；拒识空目标只约束同候选，不宣称RGB无甲或自动标背景误检。ok=true只证明重建，internalValNumericGatePassed及qualityDiagnostics分列；当前WASM4项数值失败、边界联合0/50，内部val有上游训练历史且禁训/禁止正式校准或模型选择，正式接口/manifest及HOLD不变。

`analyze-reviewed-internal-val-outcomes.py --scope <冻结范围> --output <新报告>`只读重建完整val阶段及四端解码，固定原候选/真值一一分配、uint8 L/128粗mask/真值与float32 logits/0、presence/0；按原像素2像素边界比较粗mask、实际输出与取消presence拒绝的反事实，全10源50甲含1无候选甲，7拒识保持同候选语义。`analyze-reviewed-internal-val-outcomes-v2.py --scope <范围> --prior-report <v1> --output <新报告>`完整重建v1后，只将超出0..N的不可达统计差值改为null，保留原浮点端点、旧报告及失败；`--verify-report <报告>`只读重建，不执行模型。相对诊断包含Wilson95、同分母最小可判别差和二项规划样本量，未设相对分支验收门且同源相关/上游训练历史不被当作独立泛化。当前三视图边界0/50，正常StageB路线仅冻结train-only供给及待审缺口，未授予新训练预算、角色晋升或正式发布资格。

`audit-reviewed-stage-b-supply.py`保留首版绝对路径读取失败；`audit-reviewed-stage-b-supply-v2.py --execution <冻结执行> --output <新报告>`按同一冻结scope重建全角色、质量97源投影、train/独立val真值槽、父保护角色、71库存、38未决train源与全组采集资产。v2仅兼容固定项目根下历史相对审核页，保持原路径字符串/SHA并拒绝越界、重复身份、文件漂移或分母不一致；`--verify-report <报告>`完整只读重建同报告。ok=true仅证明供给盘点保真，当前原v2盘点没有新增训练资格或预算；后续v3单图对关系投影只保留新增候选，不授权训练。整图审核依用户政策v5记录请求遥测未知并核验有界发送、真实载荷/原RGB；旧实审只继承图片事实，不继承旧图对结论或批准来源独立。扩充供给闭环另绑定实际StageA权重、单源新预算、整图误检裁决与71甲一一ROI证据；`cycle016-stage-b-expanded-native-input-plan-v1.json`约束全74个train候选原尺寸物化；当前222个原尺寸文件已完整重放，不分配训练预算，不引入内部val或新推理/优化/图片输入。空目标只否定同粗mask候选，不标整块RGB为无甲面；原124输入/745文件、正式manifest/HOLD保持。

`materialize-reviewed-stage-b-train-inputs.py --execution <冻结执行> --output <新目录>`独立物化全train候选；保留旧124个train/val物化器及产物，拒绝内部val回流。执行前逐项重建当前完整角色/父血缘、源质真值、已保存预测、一一分配、整图拒识及分母，验证新候选与全部继承train身份/目标/粗mask。每候选只写原尺寸RGB、粗mask和目标三份无损PNG，不生成384参考资产；正例须完整真值/整数逆映射零像素差，拒识只否定同候选且不回退粗mask。只读图片守卫先于像素读取，finally清cache；`--verify-report <报告>`重建全部像素、源绑定、报告完整JSON字节及目录精确清单，缺文件、篡改、角色/分母漂移或不完整真值均失败。当前13源84输入/252文件及完整81甲通过，全部旧74输入像素一致。扩充合同由`model/training/oneoff/materialize-cycle016-b225-native-v1.py freeze|run|verify`适配现行角色/诊断/完整整图裁决；只替换资源校验入口，冻结像素引擎与零丢失门不变，原11源物化及失败保留。84输入无冲突仅证明表示可达；后续全84独立正常训练及拒识拟合已闭合训练容量，现行合同见下文与Goal，不批准正式来源独立或发布。

`train-reviewed-stage-b-normal-development.py --plan <冻结合同> --preflight-output <新目录>`从头初始化原尺寸条件U-Net，全74原图RGB/同候选粗mask前向反向但优化0，逐项核验有限双头/损失/所需梯度和初始化不变；拒识只训练presence，不对含邻甲RGB施加空mask像素损失。`--plan <合同> --preflight <报告> --output <新目录>`在完整预检后一次100轮/1900步训练，整数D4与有限光度增强不插值真值，固定原像素边界损失/类别平衡presence和最终轮验收，无旧权重/优化器或val选型。严格FP32/TF32关闭，唯一事件逐步fsync、10轮取证checkpoint和独占终态/异常报告绑定；取证不授予恢复权限。当前预算已消费，训练质量未过，不得追加或恢复。

`verify-reviewed-stage-b-normal-training.py --report <训练报告> --output <新审核>`只读重建全74预检、11376事件、100轮1900成功步/7400增强输入/74最终输入、10取证checkpoint及原尺寸float32 RAW。全71甲按整数ROI放回完整原图，2原像素Boundary IoU/F1、IoU、全positive presence及3拒识零输出门不变；`--verify-report <审核>`重建完整JSON字节。ok=true只表示执行/审核可重放，trainQualityGatePassed必须单列，当前false。存档RAW的粗mask/实际/取消presence反事实为全71边界0/5/5，固定mask的presence修复上限5低于57；后续独立分支VJP测量与唯一去增强对照设计见下文；原质量失败和全部预算保持，不批准新权重/正式发布。

`audit-reviewed-stage-b-shared-gradients.py --execution <合同> --output <新目录>`为原双头RAW/共享梯度重建诊断，原分量和门失败，禁止据该报告归因或恢复预算。`inspect-reviewed-stage-b-gradient-reconstruction.py --execution <单候选合同> --output <新目录>`独立取证保存原FP32分支/整项梯度及误差，`--verify-report <报告>`只读复算，ok=true仅表示取证可重放，原门仍false。

`measure-reviewed-stage-b-branch-vjps.py --execution <独立分支测量合同> --output <新目录>`逐候选保存原mask损失及类别平衡presence损失的独立FP32 VJP、实际双头RAW和稳定身份；同候选拒识mask梯度为精确0，不把RGB中的邻甲标空。全74/71正例/3拒识/11源9组两头与训练存档逐字节相同后，才按存档向量作FP64统计；不把两次反传代数和冒充整项FP32反传，原重建门失败不改写。`--verify-report <报告>`无模型调用，完整重建逐向量/双头字节、参数身份、事件/预算及统计；固定权重瞬时方向不证明训练冲突根因、AdamW更新或质量改善。后续去增强单变量对照已完整执行但presence门失败并关闭；现行接口与下一固定特征判决见下文及Goal。

`train-reviewed-stage-b-augmentation-control.py --plan <新合同> --preflight-output <新目录>`复用冻结正常训练循环及目标，从头初始化，完整全74原尺寸零优化预检；`--plan <合同> --preflight <报告> --output <新目录>`执行独立一次100轮/1900步。适配点仅把实际输入增强应用改为identity，原增强参数仍完整抽样，逐训练事件同时保存抽样参数、实际identity及RGB/粗mask/目标原像素哈希；不改冻结基线源文件、不读旧权重/优化器，不通过内部val选型。底层兼容字段augmentedTrainingInputs保留为训练输入计数，当前7400实际为未增强输入；固定质量门/只读守卫/不可覆盖事件与异常取证保持，当前预算已消费且整体质量失败，不可恢复。

`verify-reviewed-stage-b-augmentation-control.py --preflight <预检> --output <新审核>`只读核验完整预检及相对基线的初始张量一致；`--report <训练> --output <新审核>`独立复用原质量/事件审核，再按冻结seed重建全部epoch排列和7400抽样参数，逐项等于基线并验证实际输入哈希等于原尺寸物化记录。`--verify-report <审核>`重建完整审核字节；ok=true表示执行和单变量合同可重放，trainQualityGatePassed另列，当前false。

`compare-reviewed-stage-b-development-runs.py --baseline-audit <审核> --control-audit <审核> --output <新报告>`不调用模型，完整重建同71真值/3拒识的粗mask、基线、对照及取消presence反事实，全图2原像素边界与逐实例迁移必须等于权威审核后才给出诊断。相对差附Wilson95/同分母最小可判别差/最小规划样本量，不能替代绝对质量门；反事实拒识输出与上限不代表可部署。`--verify-report <报告>`只读重建完整字节；后续全74固定特征保真与精确可分性已闭合，现行接口和下一独立凸头拟合见下文；阈值及旧失败保持。

`capture-reviewed-presence-features.py --execution <新捕获合同> --output <新目录>`固定失败控制权重和严格FP32，对完整74原尺寸train输入仅安装presence线性层输入的非干预观测hook，逐候选保存1×128 float32特征/实际双头RAW/稳定身份。两头必须相对该权重存档逐字节一致，全部权重不变，失败拒绝特征归因；完整非零合成控制先验验证hook返回None、不改两头。`--verify-report <报告>`无模型调用，重建全部特征/头字节、角色、150事件及预算，不授予头部训练或权重物化。

`certify-reviewed-presence-separability.py --execution <数学合同> --capture <完整捕获> --output <新目录/report.json>`先只读复验全74捕获保真，再一次HiGHS求解全71正例/3同候选拒识的带偏置线性间隔可行性；FP32特征和binary64数学见证按精确有理数逐行验证全部有符号间隔≥1。求解器不可行但缺精确证书时仅inconclusive；对立标签完全重复特征可给精确不可行证书。`--verify-report <报告>`只验原精确证书与完整JSON字节，不重新求解LP/调用模型。证书见证永不加载为模型，不证明FP32 CUDA或浏览器质量；后续独立拟合及开发候选验收已闭合，现行接口见下文，原证书与控制模型失败保留。

`fit-reviewed-convex-presence-head.py --execution <新冻结执行合同> --output <新目录>`只用完整74×128已存FP32 train特征，新一次HiGHS带偏置L1最小化求解有符号间隔≥2；执行前登记固定倍数2，scaled binary64头须逐行精确有理数间隔≥2，再一次完整float32舍入。缩放头不声称精确L1最优，原诊断见证不加载为模型。只改presence.weight/presence.bias，74缓存CUDA头与74完整原尺寸模型逐项事件/RAW持久化；全部非presence权重及74 RAW mask字节须与失败控制保持，零logit/完整原图绝对质量门不变。不恢复旧优化器、自动重试或使用内部val/保护数据。

`verify-reviewed-convex-presence-head.py --training <完整报告> --output <新审核报告>`及`--verify-report <审核报告>`不调用模型或重解LP；复算原捕获与精确资格、全74拟合间隔/单次舍入、候选权重、300不可覆盖事件、全部mask字节、71正例/3拒识与完整原图质量。ok仅表示重建正确，trainQualityGatePassed独立判读；当前二者均true，仅批准保留本地开发候选。本候选隔离部署验收已执行，现行完整数值失败及下一保真诊断见本节下文与§11.1；生产接口/manifest与正式HOLD保持。

`materialize-reviewed-native-deployment.py`仅物化绑定完整train清单的原尺寸F32输入/主机比例及新参数图；参数逐字节对应、回剥须恢复模板完整字节，不执行导出追踪前向。`capture-reviewed-native-control.py`在独立冻结预算内一次捕获确定性非零未训练完整模型的严格CUDA双头参考，实际TF32/autocast关闭；其只读重放不调用模型。

`audit-reviewed-native-deployment-v2.py --execution <冻结合同> --stage learned --output <唯一目录>`须先继承全清单CPU/WASM/WebGPU控制实际通过，再执行学得CPU；CPU通过才可用`--serve --port <本机端口>`启动仅127.0.0.1隔离验收页。页面按完整清单串行执行WASM/WebGPU，开始事件与双头RAW不可覆盖持久化；仅允许相同上传字节的ACK恢复，禁止重启模型输入。`--audit`及`--verify-report`按完整清单重建report-v2.json，不调用模型；原v1范围重建失败与原捕获保留，v2只修三处旧范围上界，承接剩余预算。ok表示重建正确，allThreeBackendStageGatesPassed/fullModelLearnedGatePassed须独立判读；当前控制true、学得false。任一新图仍须重新完整控制/学得验收，门为双头最大误差1e-4、presence一致及解码零像素差。

`analyze-reviewed-native-head-errors.py --report <完整审核报告> --output <新报告>`及`--verify-report <分头报告>`从全后端/全候选F32 RAW逐项重建原判定后分别统计mask/presence误差；身份、分母或原判定不一致即reconstruction_mismatch并拒绝归因。当前WASM仅mask第40/41/74项超差，所有presence均通过；分头定位不证明算子根因。现行全74观测保真及末级GN64层内分解见下文与§11.1；原完整模型数值失败不变。

`prepare-reviewed-native-observation.py`按每份实际图语义解析31个Conv/GroupNorm/GELU端点，追加float32输出后须回剥恢复完整原图字节；静态同构不证明运行保真。`audit-reviewed-native-observation.py --execution <新冻结合同> --output <唯一阶段目录>`复用既有不可覆盖捕获传输，按当前输出清单独立派生形状、张量数与字节分母。先独立非零合成基线/观测三后端，再全74项目非零控制保真，全部通过才开放学得观测；`--serve`仅监听127.0.0.1，`--audit`/`--verify-report`只从原RAW重建。独立基线不是保真通过证据，任何完整范围保真失败均禁止逐层解释。

`capture-reviewed-native-observation-cuda.py --execution <冻结合同> --output <唯一目录>`仅在新全74项目控制通过后捕获严格CUDA的完整模块输出，钩子不得反馈计算，全部原双头须逐字节保持；开始/确认事件与终态独占持久化。`--verify-report <报告>`不调用模型，复算权重、精度政策、原双头、全部31层形状/存储域/有限值及完整事件。当前全74×3学得后端及严格CUDA原双头均保真，layerConclusionsAllowed=true；原完整模型WASM1e-4失败仍为false，观测通过不批准模型。

`analyze-reviewed-decoder-counterfactual.py --execution <冻结数学合同> --output <唯一目录>`先核验原coarse+delta完整F32字节保真，从各自实际dec1.0沿原两级GN/GELU/Conv及最终头传播FP64并仅最终转F32；`--verify-report`独立逐字节重算完整清单、事件、原最终头门和同坐标有符号分解。原F32参数、epsilon及GELU常量位值保留，分解残差门1e-12，链内残差是累计误差。该尾链数学失败与原CUDA参考保留，当前扩展范围见下文。

`analyze-reviewed-upstream-counterfactual.py --execution <冻结数学合同> --output <唯一目录>`从完整同候选CUDA/WASM的enc1.5、dec2.5和主机比例出发，仅用NumPy解释实际图的形状/坐标子图，保持F32坐标及权重位值，再以FP64进行原顺序的可分离插值、跳连拼接、无bias首卷积及末级尾链。`--verify-report`重算全部阶段、坐标绑定、RAW字节与最终头门。未捕获Resize/Concat不能冒充实际观测，数学结果不能替换原冻结参考。

`analyze-reviewed-feature-cross-counterfactual.py --execution <新冻结合同> --output <唯一目录>`继承完整两域和148份上采样结果，只新计算全74两条深层/跳连交叉路径；按原失败坐标分解深层、跳连与非线性交互，presence固定同候选原WASM头。`--verify-report`独立重算交叉路径及四格恒等式；CUDA存档深层替换仅为诊断oracle，不批准实际修复。现行更上游数学范围与下一计划见下文及§11.1。

`analyze-reviewed-deep-decoder-counterfactual.py --execution <冻结合同> --output <唯一目录>`从完整两域enc2.5/enc3.5计算首上采样及完整dec2，再衔接末级链，两个分支固定原WASM enc1.5/presence。实际图语义解析、原F32坐标/常量/参数保持，特征F64传播且仅最终转F32；阶段开始/完成事件及完整数组形状、域、字节数和SHA不可覆盖，只保存深层边界及最终RAW。`--verify-report`重新计算全部阶段并逐哈希、统计、保存RAW及原双头门重放；摘要或哈希本身不替代重算。完整两域及后续enc2/enc3四格定位均闭合，当前结论与下一范围见下文和§11.1；历史失败保持，数学输出不证明实际修复或整体不可达。旧产物、原1e-4/解码零差及全部正式门保持。

`analyze-reviewed-encoder-cross-counterfactual.py --execution <冻结合同> --output <唯一目录>`继承完整两域enc2/enc3纯域证据及独立重算绑定，只新增两条交叉路径；每个候选明确两路原特征来源，固定原WASM enc1.5/presence。按原实际WASM最终最大误差坐标分解enc2、enc3和交互项，完整四格与原分母保持。全部阶段持久化完整数组哈希及开始/完成事件，仅存必要边界/最终RAW；`--verify-report`独立重算新交叉全部阶段、字节/统计/输入链、保存RAW、原双头门和四格恒等式。编码四格条件oracle及全部旧失败保留，现行扩大范围与下一计划见下文和§11.1；不证明单算子根因或批准实际部署。全部旧证据与发布门不变。

`analyze-reviewed-enc3-chain-counterfactual.py --execution <冻结合同> --output <唯一目录>`从各自已存CUDA/WASM enc3.0卷积输出起算原两级GN4/GELU及第二卷积，再接完整dec2/末级链，固定原WASM enc2.5/enc1.5跳连及presence。按实际图解析64通道无bias卷积、GN仿射/epsilon及GELU原F32常量位值，特征F64跨全部阶段传播，仅最终转F32；全部阶段独占持久化开始/完成事件及完整数组哈希/统计，只存enc3边界与最终RAW。`--verify-report`独立重算全部阶段、输入链、完整字节、统计、保存RAW及原双头门。该首GN范围及后续完整enc3范围均不足，当前结论和下一计划见下文与§11.1。数学诊断不批准实际FP32图或正式发布，全部旧失败和预算保留。

`analyze-reviewed-full-enc3-counterfactual.py --execution <冻结合同> --output <唯一目录>`从各自已存CUDA/WASM enc2.5特征，经实际2×2/stride2无补边池化、32→64无bias首卷积和原enc3首GN至完整输出链，固定原WASM enc2/enc1跳连及presence。按实际语义节点冻结池化及首卷积参数位值；池化数学值不冒充实际F32捕获，特征F64连续传播、原坐标/常量和参考保持、仅最终转F32。所有26阶段完整数组哈希与开始/完成事件不可覆盖，只存enc3边界及最终RAW；`--verify-report`独立重算全数组、全部输入/字节/统计/保存RAW和原双头门。该条件enc3范围不足，原失败保持；后续原输入完整mask链已闭合，当前结论与下一实际运行时控制见下文及§11.1。数学结果不批准实际部署或整体不可达，旧失败与全部正式门保持。

`analyze-reviewed-full-mask-counterfactual.py --execution <冻结合同> --output <唯一目录>`从原4通道F32候选及主机比例计算完整mask支路；参数/常量按原F32位值提升，编码、池化、两处计算跳连及全部解码连续F64传播，坐标和coarse seed保持原F32顺序，仅最终mask转F32，presence固定原WASM。按原图解析前端参数/池化并保留旧完整分支、参考与输入角色；39阶段均绑定全数组形状/域/长度/SHA、输入链及独占开始/完成事件，仅存最终mask。`--verify-report`独立重算全数组、全部字节/统计/保存RAW及原双头对照门；数学通过与实际部署修复严格分列。当前结果及下一控制见§11.1和Goal；实际CPU/WASM/WebGPU新运行时仍须完整非零控制、真实两头捕获及学得验收，不批准正式发布。

`model/runtime/nail-mask-f64.c`与`nail-mask-f64-v2.mjs`是隔离验收的真实SIMD WASM mask路径：F32参数按位提升、F64 Conv/GN/GELU/池化/resize及残差，仅最终mask转F32；坐标与coarse seed保留F32顺序，exp显式调用主机Math.exp。两段输入卷积避免Concat物化，尾部空闲回收及全74实测工作地址均在固定256 MiB线性内存内；该界不等于浏览器总峰值。`nail-two-head-route.mjs`的WASM路由从同次原F32 ONNX实际读取presence，mask采用同输入F64模块，原ONNX mask另存诊断；WebGPU保留原双头图。`nail-mask-f64-coordinate-observer.c`只扩展原核的坐标观测出口。`build-reviewed-mask-wasm.py --compiler <clang> --output <新目录>`冻结编译器/链接器/头文件/源码及模块；Windows须把TEMP/TMP置于工作区隔离目录。当前全74新控制、学得原生双头数值及保存输出的原图Canvas往返均通过，尚无正式泛化验收或生产manifest接入。

`prepare-reviewed-mask-wasm-control.py --output <新目录>`仅从确定性未训练控制图提取原参数并生成独立合成输入及F64参考，不读取项目图片作模型输入。`audit-reviewed-mask-wasm-node.mjs <参考报告> <新目录>`与`serve-reviewed-mask-wasm-control.py --reference <报告> --output <新目录> --port <回环端口>`分别执行Node/浏览器完整mask控制；页面独占认领、输入开始事件和输出不可覆盖持久化，HTTP ACK只允许原路径同字节恢复。`verify-reviewed-mask-wasm-control.py --reference <报告> --node <目录> --browser <目录> --output <新报告>`不调用WASM/神经模型，重新计算全部144参考数组，并重建已保存原生数组比较、预算及事件。合成门与后续新双头控制分列，当前全74三后端控制及下一学得验收见下文；控制原生像素差不冒充原图逆映射或正式质量。

`prepare-two-head-route-control.py`在零神经输入下绑定完整74候选、严格CUDA控制参考、实际图坐标和F32参数；Node及浏览器分别重放1184份实际坐标字节。`audit-two-head-route-control-v2.py cpu|serve|audit|verify --root <冻结目录>`保留原控制执行器，仅修正Windows来源键读取；CPU全74先过门才允许浏览器唯一页面消费WASM/WebGPU各74项。每次ONNX及额外mask执行前独占持久化开始事件，保存实际两头及未使用原WASM mask，原请求同字节可继承ACK但不得重跑；verify只从原RAW、事件和资产独立重建。完整新控制已闭合，见`model/reviews/cycle016-two-head-route-closeout-v1/report.json`。后续学得验收及下一原图回放见下文、Goal及当日日志。

`prepare-two-head-route-learned.py --design <设计> --output <新目录>`在零推理下重放严格CUDA学得参考、实际图参数/坐标及权重保真，绑定相同已验运行时。`audit-two-head-route-learned.py freeze|cpu|serve|audit|verify --root <冻结目录>`复用原捕获/数值协议，仅另立learned参考、预算/显示和报告记账；CPU全74先过门才允许浏览器WASM/WebGPU执行，完整两头RAW、未用原WASM mask和唯一开始/确认事件保持不可覆盖。当前222项ONNX学得输入及额外74次F64 mask全部原生门通过，保存输出的原图整数往返与逐甲质量已另行零模型回放通过；见`model/reviews/cycle016-two-head-route-learned-closeout-v1/report.json`。

`audit-native-canvas-roundtrip.py prepare|serve|audit|verify --root <新目录>`只读取已保存严格CUDA/三后端双头，先重放权威原尺寸物化、完整来源真值、角色及父保护，再按presence与F32 logits零阈值解码、原cropBox整数平移；不新增推理、缩放或概率插值。真实浏览器先通过非零边缘/非方形和拒识控制，逐项独占持久化开始/确认事件，实际写入/读回OffscreenCanvas。完整原图二值画布以little-bitorder bitpack保存，明确长度与零尾部位；verify从全部字节、身份和事件独立重建。`verify-native-canvas-quality.py --root <目录> --output <新报告>`及`--verify-report`直接从浏览器实际画布对原图真值重算逐甲质量；候选拒识不代表RGB ROI没有邻甲。当前完整证据见`model/reviews/cycle016-original-canvas-closeout-v1/report.json`，仅为train-only工程/质量回放，不批准正式发布。

`model/training/oneoff/train-cycle016-full84-pixels-v1.py`另立全84正常微调合同：仅从既有开发权重初始化，不恢复优化器；原尺寸/原角标、恒等增强，正例BCE+Dice+0.2 soft Boundary IoU+2倍4原像素边界带，拒识像素损失0、presence参数冻结。完整零步预检后固定100轮/2100成功步及最终轮验收；取证checkpoint不授予重启。`verify-cycle016-full84-pixels-v1.py`按全部21270事件、100轮顺序、10 checkpoint、84原尺寸输出/特征与完整原图分母重建；像素强制接受诊断与实际双头门分列。开发全train原联合率≥0.8保持，新增10甲另须≥0.8；正式质量阈值不变。

`model/training/oneoff/fit-cycle016-full84-presence-v1.py prepare|run|verify`先对新像素权重的完整84×128特征建立精确线性可分证据，再独立一次L1求解、固定倍数和一次F32舍入；数学见证不得初始化头。实际缓存CUDA Linear及完整模型各84输入须全部presence符号正确、mask原始字节/非presence参数不变，按同81真值与3拒识验收；当前81/81联合、新10/10、3拒识零输出，仍仅train-only容量。`materialize-cycle016-full84-deployment-v1.py freeze|build|verify`只适配权威资源入口，复用通用图参数双射/精确逆变换及原像素引擎，零前向物化隔离新图和全84输入/学得参考。`capture-cycle016-full84-control-v1.py freeze|run|verify`复用控制捕获引擎，另立84个确定性非零未训练严格CUDA参考和168事件，独立验真完整新分母。完整三后端新控制已过门，学得数值失败和当前下一范围见下文；旧74控制/数值/Canvas不得转授新权重。

`model/training/oneoff/prepare-cycle016-full84-route-v1.py control|learned`零推理解析完整84图参数与1344坐标；`audit-cycle016-full84-route-v1.py freeze|cpu|serve|audit|verify --kind control|learned`只适配冻结计数/资源/参考槽，每阶段252项ONNX及额外84次F64 mask预算分别冻结，非零控制全部通过后才准学得。`browser-two-head-control-v2.mjs`仅将显示分母改为实际清单，捕获协议不变。实际控制3端通过；学得CPU84/84、WASM/WebGPU83/84，第41mask超1e-4，presence及解码零差仍不晋升。`close-cycle016-full84-route-v1.py write|verify`从全252实际记录逐头重建504张量误差，原WASM回退7项失败另列。Canvas适配入口已按数值前置拒绝，无浏览器Canvas或新增神经输入；根因未证，不把F64数学更高精度直接等同修复。原数值失败证据`model/reviews/cycle016-full84-route-closeout-v1/report.json`保持，现行观测与下一范围见下文。

`model/training/oneoff/observe-cycle016-full84-mask-v1.py`与同名`.mjs`另立非零观测控制及全84只读捕获合同；先验证4个独立非零输入观测前后CUDA两头/WASM mask字节保真，再捕获新预算的完整84原头，仅第41项保存完整模块层级RAW。全168个CUDA头与84个WASM mask均须等于原冻结输出，否则拒绝层归因。`analyze-cycle016-mask41-local-arithmetic-v1.py`对20个同原输入GN/GELU数学数组及两份完整头数组保存独占事件/全数组SHA并独立重算，同坐标拆分传播与本层算术；不把独立最大值相加或把WASM结果归因WebGPU。原观测证据`model/reviews/cycle016-full84-mask-observation-v1/closeout.json`，未修改运行时/权重、未通过数值修复或正式质量门。

`prepare-native-coordinate-graph-v3.py`的`transform/verify`保留18输入合同：candidate、resizeRatios和`nativeCoord_{dec2|dec1}_{y|x}_{lower|upper|weight0|weight1}`；lower/upper为int64，weight0/weight1为F32广播轴。16个端点改为主机输入并直接连接全部32处消费者，移除Identity中转；按原节点位置和消费者映射逆变换须恢复原图所有字节，新增输入完整类型/动态形状、权重和两头均不得漂移。原v1/v2构建器及Identity版失败保持。`nail-native-coordinates.mjs`、`nail-two-head-native-coordinates.mjs`及原生坐标C内核继续用于隔离路由；CPU/WebGPU实际执行18输入ONNX双头，WASM执行实际ONNX presence及同输入F64 mask，未采用输出伪造或修改严格CUDA参考。新直连图完整84非零控制和学得三端、两阶段Chrome1344坐标及原图Canvas均已通过，接口与捕获重放见`model/training/oneoff/audit-cycle016-native-coordinate-route-v2.py`、`audit-cycle016-native-coordinate-canvas-v2.py`及`model/reviews/cycle016-native-coordinate-actual-closeout-v1/`。仅训练域开发证据；生产manifest/ar-tryon尚未接入新路由，真机性能和独立质量未批准。

原18源学得权重在隔离`model/runtime/native-conditional-worker-service.mjs`/`native-conditional-worker.mjs`真实Chrome118/118通过原两头1e-4、解码零差和presence门，输入及原Chrome两头字节一致，原Canvas继承后仍训练105/106、第110失败、12拒识零输出；证据`model/reviews/cycle016-native4-worker-learned-v1/report.json`及replay。局部模型P95约2351.64ms，不含Stage A/完整产品或进程峰值。新隔离`model/runtime/stage-a-linear-input.mjs`的`packStageALinearInput(rgb,width,height)`接收精确解码RGB Uint8Array及1..8192整数边长，拒绝长度不符或缩放为空；返回512×512×3 HWC uint8 letterbox、3×512×512 CHW Float32 tensor和resizedWidth/resizedHeight/padLeft/padTop，按冻结OpenCV5.0.0线性缩放/中心填114/CPU除255语义，合成8项及Node/Chrome各18源字节同构。只覆盖固定RGB到CPU输入，不证明JPEG浏览器解码或历史CUDA身份。当前Stage A原完整控制仍为检测头0.0008087158203125/402框坐标超1e-4、原型头4.00543212890625e-5，见`model/reviews/cycle016-stage-a-export-control-v1/report.json`。Node/Chrome首两Conv4完整数组/12,582,912字节与原CPU精确保持，Chrome两核单次约281.3/770.8ms只属局部成本。原CPU精确post1单次介入未改字节的385节点剩余图后，检测头仍315框坐标超1e-4、max0.000732421875；原型头3.921985626220703e-5通过，完整RAW/报告重放通过。按合同关闭只修首两块/耦合浏览器前缀分支，不拟合补偿或消费后续预算；此结果不证明任意前缀或全模型修复不可达。证据`model/reviews/cycle016-stage-a-exact-prefix-tail-v1/`。最新153研发权重的训练域结果见§11.1；旧118的Worker/Canvas和局部P95不转授新权重。当前优先完整开发验证准入与独立来源质量证据；全部旧失败、预算与原产品入口保持。

`model/runtime/stage-a-blocked-conv.mjs`提供隔离纯JS算术接口：`fmaFloat32(a,b,c,statistics?)`仅接受有限且精确为binary32的数，返回单舍入binary32结果；通过binary64精确乘积与TwoSum中点残差处理二次舍入，溢出拒绝。`convolveStageABlocked({input,inputShape,weights,weightShape,bias,strides,pads})`接收NCHW/普通权重域Float32Array、batch1/groups1，输入通道3或8的整数倍；首层块3、其余块8，块→kh→kw→块内通道顺序、偏置首加及越界跳过。尺寸/长度/有限性不符、空输出或输出超过16,777,216元素时拒绝；返回`{data:Float32Array,shape:[1,oc,oh,ow],statistics:{midpointHits,correctedMidpoints}}`。该接口用于独立算子验证，尚无生产图/Worker全链接入或设备成本批准。

## 9. 验证与质量门

基础工程门：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

纹理识别与模型发布还应根据改动范围执行：

- `scripts/verify-model-artifact.ts`
- `scripts/verify-model-output-fixture.ts`
- `scripts/verify-browser-integration.ts`
- `scripts/verify-recognition-performance.ts`
- `scripts/verify-texture-quality-gate.ts`
- `scripts/verify-real-model-readiness.ts`
- `scripts/run-real-model-final-audit.ts`
- `scripts/audit-nail-texture-local-inference-completion.ts`
- `scripts/build-nail-texture-device-acceptance.ts`
- `scripts/build-nail-texture-mobile-memory-raw.ts`
- `scripts/build-nail-texture-beta-review.ts`
- `scripts/build-nail-texture-user-failure-cases.ts`

验收原则：

- 单元测试通过不等于真实设备通过；
- synthetic/smoke 模型通过不等于真实模型质量通过；
- 数据 readiness 通过不等于训练指标或用户体验通过；
- 摄像头、WebGPU、移动端裁切和手心/手背识别必须进行目标浏览器真机测试。

`npm.cmd run audit:mvp-readiness:deferred`只用于明确排除真实数据与真实模型资产的工程脚手架阶段；它会把数据集、训练授权和浏览器模型资产三项标为`deferred`，不能替代严格`audit:mvp-readiness`，也不能作为实施规范最终完成、生产 promotion 或发布解锁证据。

移动真机验收必须从`/device-benchmark`导出的20次同会话性能样本开始；浏览器JS堆只作诊断，Android整体进程内存必须来自Profiler或系统采样，iPhone/iPad必须来自Instruments。`build-nail-texture-device-acceptance.ts`当前输出`nail-texture-device-acceptance/v2`，并绑定性能验证、内存验证及原始内存文件路径和SHA-256；最终完成度审计会重新打开这些文件并重算统计与身份，不能只信任设备报告外层`ok=true`。具体执行步骤见`docs/mobile-device-acceptance-runbook.md`。

Git 推送若出现`Failed to connect to github.com port 443`，应先用只读的DNS、HTTPS和`git ls-remote`复核链路，再比较`origin/master...master`，避免在提交其实已经到达远端时重复推送。2026-07-20复核时Git智能HTTPS端点已恢复，`git ls-remote`约1.18秒返回，本地`master`与`origin/master`均为`dfbf4e8`且ahead/behind为0/0；该现象属于传输层瞬时超时，不改变模型、数据或发布状态。2026-07-21再次收到同类21.595秒连接超时后，只读复核确认DNS解析、GitHub首页HTTPS 200和`git ls-remote origin HEAD`均已恢复，Git握手约1秒返回；环境变量与WinHTTP均无代理，GitHub状态页的Git Operations为正常。因此仍按瞬时链路故障处理，不通过改分支、重写提交、关闭TLS校验或重复推送规避。

### 9.1 最近一次白皮书一致性审查

2026-10-12 v1.2.0 结构重构审查结果：

- 白皮书拆分为「状态与接口正文」（本文件）与两个历史归档（docs/archive/whitepaper-experiment-history.md、whitepaper-changelog-archive.md）；变更记录并入按天开发日志 dev-log/（以「白皮书 v1.2.x」标记记录），不再设独立变更文档；
- §3 功能状态总表与 §11.1 已清除历史快照块、历史候选行与历史版本快照段（原文迁入实验历史归档附录），保留当前有效状态行；
- 模型开发当前口径以 §3「美甲纹理自动识别」「正式纹理模型」行与 docs/nail-texture-current-goal.md 为准，与归档前 v1.1.995 口径逐段核对一致；
- 2026-07-12 v1.1.0 审查的历史结论（页面/API 登记完整性、版本一致性等）原文保留在实验历史归档附录。


### 9.2 端侧实施技术规范复核

2026-07-12 对 `docs/nail-texture-local-inference-implementation-spec.md` v1.0 进行现状复核：

- 文档的产品边界、浏览器端侧架构、模型/数据/性能分阶段门禁、隐私和回滚原则仍可作为目标实施规范；
- 第 3.2 节及第 16–17 节部分“当前缺口/待办”已过期：源码现已具备 Worker 环境识别、可静态分析的 ONNX Runtime WebGPU/WASM 导入和 letterbox 预处理，对应进度文档的 `M1-T1-RUNTIME` 已通过；
- 正式 `nail-texture-seg-v1.onnx` 仍缺失，生产 manifest 的最终状态继续为 blocked；真实数据已开始导入和视觉审核，但尚未形成独立真实测试集与正式发布证据；
- 因此该文档当前应定位为“目标规范 + 历史实施基线”，不能单独作为当前完成度来源；实时状态应以本白皮书和 `docs/nail-texture-current-goal.md` 为准。

**2026-10-12 分层更新**：该规范文档头部版本为 v1.7；§23 及以后小节（2026-08-25 起的逐候选/逐轮实验合同，约376KB）已整体迁至 `docs/archive/nail-texture-implementation-spec-history.md`，规范文档现只保留 §1—§22 当前生效的架构、协议、口径与执行清单（含脚本依赖的 §16.1/§16.2 清单锚点，编号与行偏移未变）。上条“目标规范 + 历史实施基线”的定位中，历史基线部分已随之归档；当前完成度来源仍以本白皮书 §3/§11.1 与 Goal 文档为准。ail-texture-local-inference-implementation-progress.md` 为准。

本次为只读评审，没有修改运行时接口、模块状态或被评审规范原文。

### 9.3 模型落地Goal文档谱系

2026-07-31按用户要求回查此前以技术文档持续推进的模型落地Goal。当前Goal接口没有活动目标，项目内存索引也没有保存历史Goal正文；仓库文档与开发日志可以还原其文档谱系：

- `docs/nail-texture-recognition-model-plan.md`是2026-06-30建立的原始模型落地路线图，定义Phase 0—5、MVP目标和验收清单。`dev-log/2026-07-04.md`两次明确记录“真实授权数据和真实ONNX仍是goal完成前的阻塞”，因此它是与早期Goal最直接对应的规划文档；
- `docs/nail-texture-progress-audit-2026-07-01.md`是上述路线图的早期逐阶段事实审计；
- `docs/nail-texture-local-inference-implementation-spec.md`随后把路线图升级为可实施、可测试、可验收、可回滚的目标技术规范，并通过第16节用户/工程清单、第17节推荐顺序和第19节Go/Hold/回滚标准持续驱动落地；
- `docs/nail-texture-local-inference-implementation-progress.md`明确以实施规范为依据，是后续逐标记推进的实时进度账本；
- `docs/nail-texture-completion-audit.md`及`model/reports/nail-texture-local-inference-completion-audit.json`是Goal能否完成的最终机器门。

因此，查找“之前设置为Goal的技术文档”时，应把原始Goal入口定位为`nail-texture-recognition-model-plan.md`，把后来实际持续推进模型落地的权威主文档定位为`nail-texture-local-inference-implementation-spec.md`；当前状态不得只读早期路线图，应联合实施进度、完成度审计和本白皮书判断。本次只建立文档索引关系，不改变模型、接口、manifest、阈值或产品HOLD状态。

### 9.4 推荐的正式模型落地Goal

唯一可持续目标文件为`docs/nail-texture-current-goal.md`，只维护目标、核心要求、当前状态和下一步计划；本节不再复制启动指令、当前里程碑或旧技术配方。旧推荐文本已原样追加到`docs/archive/whitepaper-changelog-archive.md`的“2026-10-16 v1.2.67：§9.4旧Goal推荐文本”条目，不构成当前单阶段512合同。

当前唯一活动以Goal为准：按cycle016-learned-train154-deployment-v1/next-execution-requirements.json冻结并执行真实训练域Stage B部署保真：154训练身份（149正/5同候选拒识）与保留8显式分开，先复验300状态、原输入pack/坐标和资源门，再执行新严格CUDA/CPU ORT各154；CPU完整通过后才执行WASM/WebGPU各154。保留616输入/1232RAW完整分母及异常终态；原1e-4、解码零像素和presence门不变，不作为未见质量或整条链性能证据。

最终范围与门限沿用§9.5、`docs/nail-texture-completion-audit.md`及现行audit v3：同一releaseIdentity全部当前门`ok=true、decision=complete`之前保持PRODUCT HOLD。既有训练合同、数据角色、原数值参考与全部历史失败不因本次执行编排重整而失效； standing商业开发授权与真实设备/人工证据边界继续按AGENTS执行。

### 9.5 正样本识别质量门（schema v2 加权模式）

2026-08-28起，`model/training/build-positive-recognition-quality-report.py`支持两种门模式：

- **`--gate-mode weighted`（默认，schema v2）**：保留全部结构门（最少图片数、实例召回≥0.90、完整mask比例≥0.85、缺甲图片率≤0.10、每图有模型输出），并把旧版与漏检容忍明显不对称、在有限样本上统计上脆弱的三个零缺陷门（重复=0、额外候选=0、无效mask=0）替换为单一严重度加权伪实例率门：`(1.0×重复 + 1.5×无效mask + 2.0×额外候选) / 真值实例数 ≤ --max-weighted-spurious-rate`（默认0.02）。三项零缺陷状态降级为`zeroDefectDiagnostics`诊断字段，不再参与决策。contract新增`maximumWeightedSpuriousRate`与`spuriousWeights`，summary新增`weightedSpuriousInstances`与`weightedSpuriousRate`。
- **`--gate-mode zero-defect`（schema v1）**：完整复刻历史八门语义与输出结构，仅用于通过`--verify-report`重放历史v1报告；`--verify-report`按报告自身的`schemaVersion`自动选择模式，v1证据链不受本次修改影响。

v1.1.591起，复合运行时的正样本质量报告可额外传入`--runtime-selection-lock`。启用后，预测制品索引必须绑定同一锁文件的绝对路径与SHA-256；报告的`candidate`会记录锁路径/哈希，`deploymentContract.selectionMode`固定为`locked-composite-runtime`，`--verify-report`会重新校验锁字节并按报告合同重建。该参数用于candidate57这类“两个权重+固定组合规则”的候选，防止只绑定其中一个权重而丢失阈值、晋级规则、polygon选择或去重契约。

修改动机：v1门在容忍召回≥0.90（即容忍一定漏检）的同时要求重复/额外/无效严格为零，质量风险预算明显不对称，单个伪实例也会让有限样本整门失败，难以表达候选的渐进改善；这两组约束数学上仍可同时满足，旧文档把它写成“不可同时满足”并不准确。v2按业务严重度定价缺陷（额外候选最严重、无效mask次之、重复最轻），给出明确预算。该修改不放宽任何结构门阈值：candidate21的13重复/18额外/17无效在v2口径下加权率为0.1345，仍远超0.02预算，其冻结test100 HOLD结论不变。训练后独立困难负样本三变体零误检门（负样本侧）与所有发布门不受影响。

### 9.6 质量门一致性复核（2026-08-29）

本轮对§3状态、§9.5门定义、§11.1限制、当前构建器及测试进行了只读行为核对，结论分为三类：

1. **已确认的表述问题**：schema v1的“召回≥0.90”和“重复/额外/无效均为零”并非逻辑矛盾；前者允许假阴性，后者约束假阳性或不可用输出，两者可以同时成立。准确问题是风险预算不对称且零容忍对有限样本过于敏感。§9.5及本节已纠正表述，不改变schema v2实现、历史v1重放或candidate21的HOLD结论。
2. **可执行门槛漏洞已封闭**：`build-positive-recognition-quality-report.py`现把100图、召回0.90、完整mask 0.85、缺甲图率0.10和加权伪实例率0.02固化为不可放宽的正式边界；CLI只允许更严格值，弱化任一门的构建与schema v2重放均拒绝。普通构建不再接受`zero-defect`，历史schema v1只在`--verify-report`内部重建。专项覆盖5类弱门、弱contract重放和历史v1兼容，6/6通过。尚余编排项是把该逐实例报告作为独立正式gate接入最终完成度审计；在完成前不据此增加发布门通过数。
3. **仍存在的方法学张力**：冻结test100虽然没有回流图片、标签或参与阈值选择，但已经被多个候选反复评估，且逐实例失败画像被允许指导“从新来源采集类似失效模式”的训练数据方向。因此它仍具备来源隔离，却不再是严格意义上的未见最终正样本测试；继续把它同时称为“冻结最终test”和“候选迭代诊断集”会高估发布证据独立性。后续应把现有test100明确降格为受保护回归/开发基准，并在模型结构、训练数据方案、阈值和后处理全部锁定后，再冻结一份全新来源的正样本发布留出用于一次性最终判断。

以下两项只是分阶段口径不同，不构成矛盾：正样本test使用加权伪实例预算，而全负样本独立留出要求三变体零误检/零delta，是因为两者条件分布和失败含义不同；新160张训练困难负样本在70/160暂停也不破坏最低100张训练负样本门，因为下一训练计划复用的是既有已批准集合，暂停批次仍不得计入。

### 9.7 项目全面复核（2026-09-05）

本轮结合当前源码、候选决策、三方向独立审查与局部行为复现，形成 `docs/project-review-2026-09-05.md` 的 12 组问题及推进顺序；属代码/证据评审，不构成模型、真机或法律验收。当时结论为 candidate57 TEST HOLD、产品 HOLD。逐组明细已迁至 `docs/archive/whitepaper-dataset-contract-history.md`（C 节）。

已闭合、不再作为当前缺陷的更正：

- v1.1.658：原「编辑器/AI/AR」行四项缺陷已全部修复——编辑器原尺寸导出与重置回原图基线（见 §4.2 更正段）、AI 参考图比例改 log 空间就近映射（`pickReferenceRatio` 抽取至 `src/lib/ai-image-size.ts`，3:4/2:3 不再错判为 2:3/9:16）、AR「应用全部」位图释放改集合 diff。
- v1.1.659：原「工程与维护」行「缺默认浏览器交互回归」缺口已闭合——引入 `@playwright/test`（Chromium）与 `playwright.config.ts`（独立 3399 端口 dev 实例，`JIARU_DB_PATH` 指向 `.playwright-tmp` 隔离 SQLite、显式 `JWT_SECRET`，不触碰真实 `data/`）。

账号/API 行的剩余缺口（真实短信、refresh 请求入口、身份一致性与验证码发送限额治理）仍为当前未完成项，见 §5 补充与 §11.3。

### 9.8 模型技术路线与训练速度复核（2026-09-05）

结论：浏览器端单类 YOLO 实例分割与 512 方形部署输入**没有根本路线错误**，训练速度也不是瓶颈——candidate56 单阶段主模型在 RTX 4060 Laptop 8GB 上用 488 张全图训练 17 轮仅需 785.02 秒。当时主要问题是实验收敛方式与 candidate53—57 两阶段实现：ROI stage2 把同一批 328 张正图/1981 个 mask/112 个来源组展开为 1.38 万—1.55 万张近重复裁片，使每轮训练与候选验证成本放大。逐候选耗时表已迁至 `docs/archive/whitepaper-dataset-contract-history.md`（C 节）。

决定性证据：candidate57 在 test100 中**没有任何 stage2 晋级**，最终 polygon 始终来自 stage1；其实例召回为 95.85%，但 23 个漏甲集中在 13 张图，531 个匹配中只有 479 个完整 mask，最终只有 59/100 图可直接提取。

仍然生效的路线决定：

- P0：candidate57 保持终止；保留单阶段 YOLO 基线与部署一致的方形 letterbox/产品去重，暂停继续训练「只打分、不替换 mask」的 ROI stage2。
- P0：把缺甲图片率、完整 mask 比例、加权杂散率、直接可提取率及来源组最差值前移到开发选择；旧 val30 降为历史回归证据，从 train 内按 `sourceGroup` 建立互斥开发折，配方锁定后再建立全新来源校准集和一次性正样本发布留出。
- P1：优先增加透明/裸色、相邻长甲、侧视、多手和复杂背景的独立父图与来源组；停止用更多近重复 ROI 数量代替来源多样性。普通配方实验使用 experiment ID，只有准备晋升的方案占用 candidate 编号和正式审计链。
- P1：在不改变质量参数的短基准上比较 `workers=0/2/4`、`cache=false/ram` 和固定实际 batch；Windows 错误 1455 说明不能直接恢复 `workers=8`。
- P2：只有新数据循环后仍由边界主导失败，才重建两阶段；stage2 必须实际输出替换 mask，并使用充足的真实 proposal 负样本或独立校准质量头，同时先扩展浏览器多模型 manifest、Worker、体积、延迟和真机合同。

严格真值审核、来源隔离、候选锁和失败保持 HOLD 均应保留；应拆分轻量研发实验轨与正式晋升轨，避免每个小阈值、插值或微调都支付接近发布候选的完整治理成本。

### 9.9 Goal与三份引用文档一致性审计（2026-09-05）

对 Goal、实施规范、实施进度、完成度说明、实际审计脚本和当前机器报告交叉核对后确认旧 Goal 不能原样继续：最高优先级问题不是质量门太严，而是完成语义不可达与证据身份不一致。完整审计与替换文本见 `docs/nail-texture-goal-and-reference-docs-review-2026-09-05.md`；逐项 P0/P1 明细已迁至 `docs/archive/whitepaper-dataset-contract-history.md`（C 节）。

已落地、不再作为当前缺口的整改：

- Goal 授权语义重构为「精简 Goal 启动器 + 可更新权威文件」：Codex Goal 只引用 `docs/nail-texture-current-goal.md`（见 §9.10）；精确清单、来源、许可、用途角色与 SHA-256 继续机器追溯，逐批授权、训练启动和证据门后的原子 freeze 直接推进。
- 旧 val30/test100 降为只读历史回归；train 内按 `sourceGroup` 建立互斥开发折选配方，另建全新来源校准集，运行时锁定后再原子冻结全新一次性正样本发布留出。
- audit v3 已完成活动标记、统一 `releaseIdentity`、固定逐实例 schema v3 深度重放和一次性消费台账接线；三份引用文档的活动状态、角色和质量合同已于 2026-09-06 同步，完成度说明升级 v1.4。
- 正式完成审计必须调用正样本报告 `--verify-report`，固定核验召回≥0.90、完整 mask≥0.85、漏甲图片率≤0.10、加权杂散率≤0.02 和每图输出；mAP 只作辅助回归。
- 只有 `backend=model`、发布身份一致且每个候选有有效 mask 时才计正式识别；fallback 持续显示辅助定位/人工确认并从 Beta 成功率排除。

剩余顺序固定为：train 内 `sourceGroup` 开发折与下一单阶段候选 → 全新校准/正样本发布留出 → 困难负样本 → 生产运行时与产品门。当前没有批准 release identity，审计继续 HOLD。

### 9.10 可持续Goal指针合同（2026-09-07）

当前会话Goal为`active`，以`docs/nail-texture-current-goal.md`为唯一目标文件；完成状态仅在同一releaseIdentity的completion audit v3对全部当前发布门返回`ok=true`、`decision=complete`时允许写入。Goal状态接口不用于改写未完成目标或追认历史失败。

项目采用“精简Goal启动器 + 可更新权威文件”：目标文件仅保留目标、核心要求、当前状态和下一步计划；读取、回写、字段保护和文档同步规则放在`AGENTS.md`。执行Agent可依据可重放证据主动调整当前路线与下一步，不得降低正式阈值、改变数据角色、拼接发布身份或移动最终完成语义。通用模板见`docs/continuous-goal-template.md`；早期静态Goal重构与旧轮次口径见历史归档，当前规模和里程碑以Goal为准。

## 10. 隐私、安全与资源管理

- `/editor` 上传照片默认在浏览器本地处理；「用户改进计划」开关默认开启时，手部照片等数据可能被上传用于产品改进（当前代码尚无实际上传通道，开关为偏好记录，未来数据收集上线后生效）；
- `/ar-tryon` 摄像头帧默认在浏览器内存中处理，不录制；MediaPipe程序和模型由本站同源静态目录提供；
- 自动纹理识别默认在浏览器 Worker/主线程中运行；
- `/api/generate-ai`与`/api/generate-seedream`接收文字及可选参考图，并分别转发给Agnes与火山方舟；返回图片由浏览器访问外部URL，主动生图不由“用户改进计划”开关禁用。
- `AGNES_API_KEY`只能存在于服务端环境变量；本机`.env.local`受`.gitignore`保护，文档、日志和源码不得记录真实密钥；
- `ImageBitmap`、对象 URL、MediaStream track、Worker 和动画帧循环必须在取消或卸载时释放；
- 用户素材、训练图片、大模型权重和生成数据默认不应加入 Git；应通过 `.gitignore`、对象存储或独立数据盘管理；
- `model/reviews/`的已冻结二进制采用原路径、原字节不变的NTFS透明无损压缩；完全相同内容可共享只读硬链接。维护须冻结终态清单及完整SHA、拒绝链接越界和并发写、独占持久化操作事件，并在原子替换失败时恢复原文件；结束后按全部原路径重验SHA与终态报告。禁止单独解除共享别名只读后改写内容；新产物须另建版本。终态目录的稳定大文本报告使用同一透明压缩原语并逐文件完整SHA验真；增量维护先压缩未共享的可写文件，再精确去重，已有压缩/共享文件跳过重复操作。当前91019份二进制/大文本原路径全量核验及前轮记录见`model/training/oneoff/reviews-storage-maintenance-20261015-v7/combined-report.json`和`model/training/oneoff/reviews-storage-maintenance-20261014-v2/verification-report.json`；未决/近期写入目录保持跳过，旧质量失败与模型发布HOLD不变。
- Git与远端的跟踪边界固定为完整可运行的业务、训练和审计代码，测试、配置模板、浏览器运行时必需资产与必要说明。模型权重、数据集、逐文件开发清单、训练计划/判定JSON、训练输出、评估明细、机器报告与review、审核截图、浏览器调试快照及其他可重建证据仅保留本地并由`.gitignore`隔离；小型稳定测试fixture可保留。历史`辅助材料`只跟踪必要Markdown说明，图片、标注、CSV/JSON/YAML和审核产物不再进入当前Git树。
- 正式 API 上线前需增加鉴权、限流、内容安全、审计、费用保护和错误信息脱敏。
- `/privacy`是待纠正的产品文案，不构成法律合规验收：仍称无账户体系、只列Agnes、关闭改进计划后不再上传任何数据，与已有账户、Seedream和主动生图数据流不符。账户数据库可保存手机号、身份、会话IP和审计记录；个人收录保存在本地IndexedDB。第三方“不用于训练或存储”不能仅凭本项目代码保证，需要实际服务条款/协议依据。
- 改进计划目前尚无实际素材上传通道；隐私页开关仅写localStorage，账户页开关同时写`/api/me/improvement`与localStorage，反向同步未实现，可能出现账号与设备偏好不一致。后续接入上传前必须统一权威偏好与作用范围，不能把关闭可选改进计划描述为关闭用户主动请求的全部网络服务。

## 11. 已知限制与下一阶段

### 11.1 阻塞项

旧微拟合学得权重与全部68候选的严格FP32复验独立通过train-only容量门：66正例全部保留、严格联合54/66（要求53）、拒识2/2且输出0像素，mean IoU/Boundary IoU/F1=0.972076/0.794394/0.978412。旧TF32容量、4096新头更新、11968分割步和全部历史失败保留。

完整内部val全50甲零推理归因已闭合：粗mask/实际精修/取消presence拒绝的反事实IoU≥0.75为47/43/47，三者原像素边界联合均0/50；4新增IoU失败来自presence拒绝，实际精修的边界IoU及F1单门各0/50，6/7拒识仍输出。四端解码完全相同，固定CUDA参考的数值修补不能恢复边界或拒识质量，该历史权重不晋升；WASM4项和全部旧失败保持，正式HOLD。

当前质量状态：原147/149仅训练域，光度规范化开发门false及旧失败保持。Stage B真实训练权重的九尺寸合成完整图已通过CPU ORT/WASM/WebGPU各9/9：两头最大差6.10352e-5/6.53267e-5/6.72340e-5，解码零像素差及presence一致；完整300状态/原权重不变，见`model/reviews/cycle016-presence-stable-learned-v1/report.json`。当前仅合成接口资格，下一真实训练154保真合同已冻结要求且预算0，显式排除已消费保留8；未通过来源隔离质量、Stage A+B产品链或正式发布，PRODUCT HOLD。 新来源val/留出、角标消融、整条链成本、真机/Beta/回滚仍缺，无批准生产身份。

两种原像素修边分支仍关闭、没有接入产品；旧GrabCut总2/141及置信度图割131/141、139候选3429像素变化保持原报告，不能因当前真值错误而改写成通过，也不能据其证明真实甲缘能力。最新完整18源训练前/最终预测/新真值对照为`model/reviews/cycle016-requalified134-training-v1/preview/index.html`。旧未终审参考预览及其错误提示原样保留作历史证据，现行训练资格只读§8.8新域报告。

正式来源独立评估尚未准入。原26差集中3源18甲开发StageA训练、1源8甲保留对照不回训、新2源8甲已消费开发诊断并加入StageB训练，余20源102甲仍禁止；原角色与全部历史失败保持，内部val不得回训。独立val≥30、新正负留出各≥100、角标消融、同身份完整数值/生产/ar-tryon、真机/Beta及双批准回滚仍缺。

### 11.2 暂停交接与恢复进展快照（2026-07-30）

本节为 2026-07-30 旧会话停止时的权威恢复点与恢复后进展快照（candidate5 独立留出补齐、100 张拟选与精确授权、原子 freeze、100/100 原分辨率终审、部署 512 三变体审计与发布拒绝）。快照中的拟选与待授权状态已由精确授权、冻结和正式批准清单替代，当前口径见 §11.1 与 §3 状态表。快照原文（仓库/源码状态、120 张补齐、拟选 100 张、授权冻结终审、能力边界与恢复约束七项）已迁至 `docs/archive/whitepaper-dataset-contract-history.md`（D 节）。

保留的当前约束：

- 该纯负留出只回答「纯非美甲物体是否被误检为甲面」，不能证明真实甲面承载相同强混淆图案时仍被召回；稳定召回不得表述为已验证，须另建来源隔离的真实甲面正样本挑战集并单独审核，不得混入或替代本纯负独立留出。
- 用户对 `.codex` 异常磁盘 I/O 的观察继续只作为 operator report，不升级为未经验证的根因结论。
- 不得根据已经产生的模型输出替换或缩减已冻结批准清单，也不得将本批转为商业训练。
- 完整发布另缺后续合格候选、用户真实失败案例、四类移动真机、至少 100 张 Beta 人工质量、生产 ONNX/浏览器协议、正式注册及双批准版本回滚证据。

### 11.3 未完成或占位能力

1. 真实灵感图库与内容后台；
2. 用户账户原型已存在，真实短信、会话续期、数据库初始化与生产治理仍待补齐；云端项目保存、跨设备同步未实现，详见§5补充及§9.7。
3. 订单、门店、商品、预约、支付等业务后端；
4. 正式 3D 指甲网格、遮挡、光照和物理材质试戴；
5. AI 生图的供应商抽象、任务队列、结果持久化和配额系统；
6. 正式模型监控、线上质量回流和自动回滚闭环。
7. 图库/本地收录→AI/AR及AI→本地图库已实现，不再列为待实现链路；剩余缺口是编辑器笔画/成品共享与服务端持久项目协议，见§4.3—§4.5。

### 11.4 外网演示与内网穿透已知限制

- `/ar-demo` 页面通过 iframe 加载 `http://localhost:8080/?embedded=jiaru-main`（访问者本机的 Python demo 服务）。在经由 Cloudflare / cpolar 等隧道暴露的 HTTPS 公网地址下，该 iframe 因「HTTPS 页面加载 HTTP 子资源」被浏览器混合内容策略拦截，且访问者电脑通常并未运行该 Python demo，故 `/ar-demo` 外网演示必然不可用；此为页面设计对本地环境的依赖，与穿透工具或 `allowedDevOrigins` / `Permissions-Policy` 配置无关。
- AR 摄像头（`/ar-tryon`、`/ar-demo` 的 `camera=(self)`）在隧道 HTTPS 域名下已实测可正常调用 `getUserMedia`（GRANTED、视频轨 live），前提为隧道提供有效 TLS 且未改动 `next.config.ts` 的 Permissions-Policy。
- 纹理识别与 AR 合成依赖 onnxruntime-web（WebGPU 优先、WASM 回退）在浏览器端推理；远程演示所用的手机或老旧浏览器若不支持 WebGPU 且未回退 WASM，识别会失败，属设备能力问题。
- AI 生图（`/ai-generate`）密钥 `AGNES_API_KEY` 已在 `.env.local` 配置，由服务端 `/api/generate-ai` 调用 `api.agnes-ai.cn`；外网可用，前提是运行服务的本机可访问该外部 API。
- 临时演示默认使用 Cloudflare quick tunnel，域名每次启动变化、节点可能位于境外（实测 kix04 / sjc10 / sjc11），国内访问延迟高；如需稳定国内节点应使用 cpolar / 花生壳等（需注册账号获取 authtoken），且仍需解决 `/ar-demo` 的本地 8080 依赖。
- 隧道进程失效是外网演示「部分功能突然不可用」的首要根因（进程存活但边缘连接断开时外网返回 530，或进程被回收后返回 000）。为防复发，v1.1.582 新增守护脚本 `C:\Users\YaoYinyu\.workbuddy\binaries\jiaru-tunnel\jiaru-tunnel-supervisor.mjs`（配套 `start-jiaru-tunnel.cmd` 双击启动）：它 spawn cloudflared、从输出中按「3 个及以上连字符词」的快隧道域名正则抓取候选（**排除 cloudflared 日志中的内部地址 `api.trycloudflare.com`**）、对候选做最多 6 次×间隔 5s 的 HTTP 校验后才写入 `jiaru-tunnel-url.txt`（quick tunnel 域名刚生成时 DNS 尚未生效，一次性校验会永久丢弃好地址，实测第 6 次≈32s 才通）、每 30 秒做一次健康检查（15 秒超时）、连续 2 次健康检查失败则 kill 重建、重连间隔按 5s 起指数退避至上限 60s；日志落在同目录 `jiaru-tunnel.log`。实测 `taskkill /F /IM cloudflared.exe` 后的「退出→重建→域名可用」全闭环耗时：QUIC 下约 36 秒（偶发最快 8 秒，演示规划按 30—60s 计），强制 HTTP/2 后缩短为 **15 秒**。稳定性实测：强制 HTTP/2 后连续 19 次健康检查（约 9.5 分钟）全部 200，期间 0 次进程退出、0 条 `ERR Serve tunnel` / `Retrying connection`（QUIC 下该类错误反复出现）。v1.1.586 追加两项修正：① 守护启动 cloudflared 时固定追加 `--protocol http2`——本机到 Cloudflare 边缘的 QUIC/UDP 不稳定，cloudflared 预检即给出 `suggested_protocol=http2`，QUIC 下会以 `timeout: no recent network activity` 触发 datagram manager 失败并反复重连，导致隧道慢启动最长约 5 分钟；改用 HTTP/2 后候选地址校验从「最多 6 次全失败」变为**第 2 次（约 7 秒）即通过**。② 候选校验失败不再「判定无效并放弃」，改为保留待定候选、由后续每个健康检查周期续试，否则守护会进入「cloudflared 存活却永不发布地址」的惰性状态。注意：重连会产生**新随机域名**，因此演示期间应以 `jiaru-tunnel-url.txt` 的当前内容为准，不要分发旧链接；守护脚本本身随启动它的终端/会话存在，需要长期驻留时应在独立窗口双击 `.cmd` 运行。
- 外网演示时的静态资源一致性已复验：MediaPipe 手部模型 `hand_landmark_full.tflite` 经隧道下载 5,478,688 字节、SHA-256 前 32 位 `8c026882c9ec059ce0f8e75266bee5a9`，与 `public/vendor/mediapipe/hands/` 本地文件逐位一致，隧道不改写或截断静态资源。

## 12. 新模块对接登记模板

后续新增模块时，在对应章节至少记录以下内容：

```md
### 模块名称

- 状态：已完成 / 待验证 / 进行中 / 占位 / 未完成 / 阻塞
- 负责人或来源：
- 用户入口：
- 代码入口：
- 输入：
- 输出：
- 错误与降级：
- 环境变量/配置：
- 隐私与资源释放：
- 使用步骤：
- 验证命令与结果：
- 已知限制：
- 关联文档：
```

### 历史内容归档索引（2026-10-12 v1.2.0 起）

- 原§12.9—§12.351实验叙事（2026-09-03至2026-10-12，343个小节）及原§3/§11.1中的历史快照内容，整体迁至 `docs/archive/whitepaper-experiment-history.md`；
- 原§13完整变更表（v1.0.0—v1.1.995）整体迁至 `docs/archive/whitepaper-changelog-archive.md`；
- 原§8.1中的历史执行叙事（2026-07-13起的标注返修/审核批次流水，以及candidate3/5与261—360困难负样本批次执行记录）和原§8.4/§9.7/§9.8/§9.9/§11.2复核原文，整体迁至 `docs/archive/whitepaper-dataset-contract-history.md`；正文相应小节只保留仍生效的契约、路线决定与当前口径指针；
- 其他历史文档中形如「白皮书§12.3xx」「§13 v1.1.xxx」的引用均指上述归档文件，正文不再维护这些编号；证据细节以归档与机器可读报告为准；
- 本白皮书只登记当前接口、状态与仍在生效的合同；后续新增模块按上述模板登记，实验迭代过程记录进当日 dev-log 与相关进度文档，不写入本节。

## 13. 版本与变更记录

变更记录自 v1.2.0 起并入按天开发日志 `dev-log/YYYY-MM-DD.md`：白皮书发生实质变更（接口、状态、配置、数据或模型契约）的当天，在当日日志中以「白皮书 v1.2.x」标记简要记录变更内容与影响范围，不再逐任务登记、不设独立变更文档；无实质变更的任务不产生版本标记。v1.0.0—v1.1.995 的逐条历史记录完整保存在 `docs/archive/whitepaper-changelog-archive.md`。

- 白皮书顶部「文档版本」在每次实质变更时顺延，并与当日 dev-log 中的版本标记一致；
- 纯实验迭代、审核批次、流程性提交推送等记录到当日 dev-log 与相关进度文档，不进入白皮书、不顺延版本。
