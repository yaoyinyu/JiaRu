# 甲如（JiaRu）技术白皮书

> 文档版本：v1.2.447
>
> 基线日期：2026-07-12
>
> 最近全面审查：2026-11-08（v1.2.280 内容合规性修复：§8.9/§3/§11.1/§4.5 的逐版本实验叙事归档至 `docs/archive/whitepaper-native-precision-history.md`，§9.2 生产 manifest 过期口径更正为 deployed；正文 316,247→224,418 字节。历史审查见 dev-log/2026-10-12.md 的 v1.2.0 结构重构与 v1.2.2 内容精简记录）
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
3. **逐版本叙事禁入正文（2026-11-08 v1.2.280 强化）**：正文的任何章节（含 §3 表格前后、§4 各页面小节、§8 各接口小节、§11.1 阻塞项）都不得逐段追加「v1.2.xxx 做了什么/得到什么指标」式的版本流水。每个模块只保留**一段当前口径**；新版本取代旧版本时**改写该段**，而非在其上方追加新段。接口/工具登记只保留当前活跃入口，历史分支、已结项实验与 `model/training/oneoff/` 一次性脚本一律进归档或 dev-log。同一结论只允许出现在一个章节，其他章节用指针引用；
4. 体积回归门槛：正文超过约 300KB 或状态表重新堆积历史行时，应先把历史内容迁入 `docs/archive/` 归档再继续登记；
5. 执行与风险相匹配的验证，并记录验证结论，不得把“代码存在”直接写成“生产可用”；
6. 历史实验叙事（原§12.9—§12.351）与逐条变更记录（v1.0.0—v1.1.995）完整保存在 `docs/archive/whitepaper-experiment-history.md` 与 `docs/archive/whitepaper-changelog-archive.md`，归档内容只增不改写；
7. 检索纪律：全仓 grep/批量扫描默认排除 `docs/archive/`（归档已达数MB，误命中会灌满上下文）；当前事实查本文件、`docs/nail-texture-current-goal.md` 与实施规范文档，历史证据按归档头部声明的编号指向规则查对应归档文件。

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
| AI 生图 | Agnes Images HTTP API | 当前代码使用`agnes-image-2.5-flash`（2026-10-22 由 `agnes-image-2.1-flash` 切换，请求参数、尺寸参考表与计费口径不变），依赖服务端密钥 |
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

图库款式已可带入编辑器灵感色、AI参考图和AR选取器；AI生成结果可收录到浏览器IndexedDB，再由图库带入AI或AR。编辑器成品（纹理贴合结果）尚无共享项目协议，云端保存与跨设备同步未实现；相关链路见§4.3—§4.5。

## 3. 功能状态总表


当前全量开发基线为等权局部几何侧缘头，见§8.9。冻结侧缘轮廓的开发域纹理收益已复验至摆正和贴合几何，已核验关键点覆盖子集的全部甲尖方向并否决无条件绕开掌面拒绝，已用真值对照验证双向修边可同时改善浏览器纹理漏抠及甲外残留（§6.4），已结项冻结端头候选重排，已结项新增素材可直接核验的来源图对，现有来源凭证核对已结项，待上游凭证与完整父图（§8.8）。共用摆正框与生产覆盖率原图直采均已结项（§6.4），冻结完整轮廓的分歧像素纠错已结项，8px全边带联合监督首折已结项，冻结连续片段与组外选择均已结项（§8.9），固定轮廓的软边借色路线已结项（§6.4），现行浏览器实图偏差已定位至低分辨率精修链，双分辨率局部精修的浏览器冻结轮廓已完成634甲实测及迁移对照，固定整轮廓替换和局部搬运均未过几何门，16px局部保拓扑的真值控制通过继续门，线性原图信号和独立连通域清理未通过，实测Stage B原始半径归因已完成634甲，原输出上的区间残差首折已结项，首折JPEG浏览器本地解码已通过字节对拍，同输入Stage A粗遮罩偏差可从原型入口传入，三尺度及DFL交叉将单图剩余超门误差定位至P5框回归分支，整体扩大P5卷积累加精度未通过，逐层交叉把窗口收窄到P5前两个卷积块，两种显式BN表达未通过，Chrome WebGPU已证实设备落点、独立非零对照仍超门，浏览器同输入真实首折的候选身份和顺序已稳定，框误差遍及三尺度，原型单像素差影响严格贴合。主机宽精度DFL单独修复已结项，冻结交叉显示框回归需至少恢复P5第二卷积块的输出，Stage A整段分类交叉保留CPU控制，三种浏览器卷积原型已结项（§6.2）；Stage B角度微移、强精修头空间采样及冻结编码特征排序均已结项，已结项相邻截面补边及只优化内收，已结项整甲坐标纠偏，原图颜色混合及纯几何排序已结项，连续甲缘整段自动评分与修边变淡信号已结项，甲根颜色优先收敛画质，按画面倍率平滑调整的1–2px不透明保护通过标准及压力画质门，并已接入试戴生产渲染默认路径（§6.4），进入隔离相机画质复验，原图局部跨甲缘锚点的对照结项，人工修边盲测见§8.9，活动计划见 `docs/nail-texture-current-goal.md`。纹理提取和相机贴合的现行契约分别见§6.4、§4.5。逐版本实验叙事见 `docs/archive/whitepaper-native-precision-history.md`（B 节）。


| 模块 | 用户入口/接口 | 状态 | 当前结论 |
| --- | --- | --- | --- |
| 首页与统一导航 | `/` | 已完成（v1.2.158 新拟态设计；v1.2.213 导航换位与移动缩放恢复） | 提供功能入口与统一视觉框架；桌面 5 项顶部导航（首页／灵感／试戴／创作／我的）+ 2 个圆形图标入口（上传试色 `/editor`、灵感图库 `/gallery`），移动 5 项底部导航同构；个性化分析由首页风格卡直达；首页不再重复功能入口网格，旧玫瑰粉视觉已废弃；`viewport` 已恢复用户缩放（删除 `maximumScale=1`/`userScalable=false`） |
| 消费者端新版设计提案 | 独立本机预览 `127.0.0.1:4318`，见 §4.7 | 待验证（真机与设计评审） | 最终手机／短横屏、触控模拟和Windows Chrome／Edge检查通过；原生分享与移动真机待验；旧版保留，真实模型、云同步与公开社区未接入 |
| 登录与账号原型 | `/login`、`/account`、`/api/auth/*`、`/api/me` | 进行中（生产闭环未完成） | 已有JWT/SQLite、手机号/微信身份与偏好接口；生图路由身份与配额/预算熔断、SQLite目录预检已由v1.1.649修复（见§5更正段）；剩余缺口为真实短信、refresh入口及身份一致性/验证码治理。详见§5补充及§9.7。 |
| 灵感图库 | `/gallery` | AI 素材 + 编辑器灵感参数消费 + 图库→AR/AI 链路打通 + 本地收录（2026-09-03，v1.1.580/581/583；v1.2.213 收录区状态模型与删除撤销；v1.2.215 卡片试戴方式选择弹层） | 6 张 Seedream pro 文生图素材本地落盘 `public/nail-gallery/ai-look-1..6.jpg` 并逐张通过视觉审核；`/editor?gallery=` 已实现灵感卡（灵感色自 v1.2.174 起映射为最接近主色的纹理套装，v1.2.215 起识别后自动贴合，见 §4.2）；v1.2.215 起点击卡片图或标题先弹「试戴方式」选择弹层（静态试色/AR 实时预览，见 §4.3）；v1.1.583 起图库卡片新增「AI 相似款」(`/ai-generate?gallery=<id>`) 与「AR 试戴」(`/ar-tryon?gallery=<id>`) 入口，图库款式到 AR 的纹理传递已打通（§4.5）；AI 生成结果可一键收录到浏览器本地 IndexedDB 图库（`/gallery`「我的收录」区块，§4.3），v1.2.213 起收录区具备 checking/empty/load_error/unavailable 可区分状态、单条删除 5 秒撤销与「清空全部」确认弹层，旧收录按 id 幂等迁移为 WorkItem（`jiaru-works`，§4.4），真实内容后端与跨设备同步仍无 |
| 图片试色编辑器 | `/editor` | 进行中（2026-10-31 v1.2.173 画布重写为「甲面框 + 纹理贴合实例」；v1.2.174 页面接线落地：纯色试色删除、纹理套装点选贴合上线；v1.2.179 登记 5 套真实照片纹理资产（5 套×5 指）并完成浏览器端到端功能验收；v1.2.213 对象面板/键盘/会话草稿/导出治理，hover 视觉细节待用户实机复核；v1.2.215 灵感款识别后自动贴合；v1.2.217 本地/云端识别模式切换） | 本地上传、MIME/大小/分辨率/解码校验、识别级联辅助定位、纹理套装点选贴合与原尺寸本地保存链路已实现；v1.2.215 起灵感款（`?gallery=`/作品卡/灵感卡回调）在识别出甲面框后自动贴合一次（可撤销/逐指调整，见 §4.2）；v1.2.217 起识别提供「本地 | 云端」两种模式（云端为用户显式选择的辅助定位通道，见 §5.5）；纹理资产来源与提取管线见 §4.2，画布组件接口与页面合同见 §4.2 |
| AI 美甲生图 | `/ai-generate`、`POST /api/generate-ai` | 已完成（用户验收；v1.2.213 交互重构见 §4.4） | 已接入Agnes Image 2.5 Flash（文生图 + 图生图；2026-10-22 由 Agnes Image 2.1 Flash 切换，请求参数、尺寸参考表与计费口径不变）；2026-08-29服务端Endpoint已切换为`https://api.agnes-ai.cn/v1/images/generations`并换用新服务端密钥，实测模型列表`GET /v1/models`认证HTTP 200、当时目标模型`agnes-image-2.1-flash`可见，真实文生图返回图片URL且产物可下载。`.cn`模型列表认证HTTP 200且目标模型可见，协议专项测试、Lint、全量758项测试和生产构建通过。2026-08-10用户确认AI美甲真实生图功能验证通过，并于2026-08-12再次确认；2026-08-19新增可选「参考图」图生图（上传手部照片→浏览器压缩至最长边1024 JPEG→与提示词一起生成，Agnes在参考图手部指甲上绘制美甲并保持原图构图，实测图生图成功且约12s，文生图约157s），并新增生成中 shimmer 加载与页面过渡动画；2026-08-29新增用户可选择**画面比例**（8 种）与**输出尺寸档位**（1K/2K/3K/4K），按 Agnes「输出尺寸参考」表实时显示最终像素尺寸，文生图与图生图共用（默认 1K+1:1 ≈ 1024x1024，行为与历史一致）。参考图仅在用户主动上传时发送第三方、仅用于本次生成；成本、内容安全和生产持续可用性继续作为运营监测项。2026-10-22 默认模型切换为`agnes-image-2.5-flash`（白皮书 v1.2.147）：实测`GET /v1/models`新模型可见，真实文生图（1K+1:1）约9.1s、真实图生图（`extra_body.image`）约102.3s均HTTP 200返回可用URL；受影响测试4文件20/20、全量1189/1189、typecheck与生产构建通过；历史验收记录中的2.1 Flash为当时模型口径；图生图参考图编辑的提示词约束（弃用文生图场景后缀、按句提取设计描述、环境元素锁定）见 §4.3（v1.2.161）。|
| AI 美甲生图（Seedream 引擎） | `/ai-generate`（引擎切换）、`POST /api/generate-seedream` | 待验证（路由层 lite 实测通过；pro 脚本端到端通过；仅剩浏览器视觉呈现等待用户确认；v1.2.213 交互重构见 §4.4） | v1.1.564 新增火山方舟 Seedream 5 系列作为第二生图引擎，Agnes 保持默认且链路零改动。新增`src/lib/seedream-image-api.ts`（扁平 body、顶层`error{code,message}`解析、429/500/503 指数退避重试、240s 超时、`watermark`默认关）、`seedream-image-size.ts`（pro=1K/1.5K/2K、lite=2K/3K/4K 档位×8 比例→显式 WxH 表）与`seedream-prompt.ts`（Seedream 专用精简系统词约 100 字，独立于 Agnes 长提示词；用户提示词上限 300 字）。前端`/ai-generate`新增「生成引擎」切换（Agnes / Seedream pro / Seedream lite），切引擎联动尺寸档位与提示词上限。真实端到端：pro 引擎经`doubao-seedream-5-0-pro-260628`文生图 19.7s 成功返回 186KB 有效 JPEG；v1.1.577 更换用户临时 Key 后 pro 复测 28.5s 成功、lite 档`doubao-seedream-5-0-260128` 33.1s 成功返回 249KB 有效 JPEG（该账号已开通，此前"has not activated"阻塞解除）。v1.1.578 修复路由层 `env` 缺省导致的 watermark 读取崩溃（`Cannot read properties of undefined (reading 'ARK_IMAGE_WATERMARK')`），`generateSeedreamImage` 入口统一 `env = options.env ?? process.env`，新增"不传 env 的成功路径"回归测试；v1.1.579 通过 curl 实测本机 `POST /api/generate-seedream`（lite 2K 1:1）HTTP 200、27.1s 返回有效 imageUrl，确认修复已被 dev 服务器 hot-reload 加载。模型 ID 经`GET /api/v3/models`实测发现（必须带版本日期后缀）。新增 18 项测试全过（v1.1.578 增 1）、路由校验冒烟 6/6 通过；仅剩浏览器视觉呈现由用户确认。生成 URL 24h 过期，项目不做长期留存 |
| AR 纯色试戴 | `/ar-tryon` | 待验证 | 单手摄像头、关键点、指甲绘制、手心/手背识别已实现；MediaPipe运行文件使用本站同源静态资源，实时路径启用`modelComplexity: 1`。甲面几何结合TIP/DIP/PIP、深度和手背平面生成长轴、横轴及侧转透视剪切，工程回归通过；v1.2.213 起页面为三步流程（选择来源→提取与复核→试戴与校准，顶部步骤状态）、摄像头新增主动关闭按钮（停轨/关 Hands/解绑/复位/焦点返回）与连续失败覆盖层、校准面板当前指珊瑚高亮并显示已调整数量；真实边界仍需多设备真机验收 |
| AR 纹理试戴 | `/ar-tryon` | 待验证 | v1.2.259已接入甲根固定校准、可见alpha内容尺寸、连续采样、完整透明轮廓及逐指180°翻转/撤销；真实相机贴合待复核（当前契约见§4.5/§6.4）。上传含完整手背的参考图时优先通过MediaPipe Hands逐指定位；完整手部关键点失败后，局部近景先用甲色连通域定位黑色、彩色、银色和镜面甲；甲面为裸色/半透明且被肤色种子吞掉时，再以闭合甲缘、甲板内部/肤色邻环和4—5枚同手连续链复合定位，仍失败才进入人工补选。v1.2.217 起选择器识别提供「本地 | 云端」模式切换（云端候选固定低置信、按既有复核门分流，云端路由见 §5.5）；两条本地辅助路径均没有像素级mask，低对比边界候选固定低置信并要求用户检查；实时AR支持拇/食/中/无/小指各自独立的长度75%—140%、宽度70%—145%及甲尖/指根位置±20%校准，摄像头最终贴合仍需多设备真机验收。2026-10-29（v1.2.165）起带mask候选提取纹理时按掩膜主轴自动摆正并紧致裁剪（甲尖方向由候选区域角消歧、主轴与区域角分歧>25°告警），输出满足实时渲染「正立、甲尖朝上、甲面充满位图」约定，识别侧栏提供「旋转180°」人工兜底。2026-10-29（v1.2.167）起识别完成后自动执行「精细抠图（已记住隐私确认且服务就绪时）→指位推断（识别未给指位时按画面x序补全并告警，可在选择器修正）→纹理提取→参数分析→自动上屏」一条龙，无需手动点击；参数分析（浏览器端启发式，`texture-analysis.ts`）从提取纹理得出甲型（圆/方/杏仁/尖，行宽剖面阈值分类）、主色（4096桶量化聚类）、图案（纯色/渐变/法式/亮片/花纹参考标签）与光泽度（高光比代理），渲染端按甲型套用轮廓模板（`ar-nail-shape.ts`，round档与历史常量逐字段一致、未传样式时渲染不变）并按光泽系数缩放高光/菲涅尔；2026-10-30（v1.2.170）起纹理模式渲染改为长宽比保真（原封不动）：宽度对齐真实甲面（含宽度滑杆），渲染长度=宽度×提取纹理自身长宽比（`computeTextureRenderPlan`），甲根边缘锚定估算甲面的甲根边缘、延长部分向甲尖自然伸出（不短于估算长度、上限3×估算长度），自带alpha轮廓的提取产物直接以纹理alpha成形（跳过贝塞尔裁剪），菲涅尔/颗粒/暗角/高光材质层经离屏source-atop合成限制在纹理alpha内，quality-first-v7甲根颜色保护为纹理层默认路径（精确面积采样+1–2px内缩，`NEXT_PUBLIC_AR_ROOT_COLOR_PROTECTION=off`可构建回退，异常自动保留现行摄影层）；不透明位图（手动裁剪路径）回退贝塞尔形状裁剪（历史行为）；同时取消v1.2.167的按甲型自动加长系数（1.2×/1.35×），长度由纹理比例自然决定、滑杆仍可整段微调；本地识别0候选（局部特写/多手图片）时自动流程在已记住隐私确认且服务就绪前提下自动执行一次兜底识别并继续上屏（2026-10-29 v1.2.168；该自动兜底仅本地模式执行，云端模式 0 候选提示切换本地或手动处理）；低对比/兜底低置信候选自 v1.2.213 起按覆盖前复核门分流（`src/lib/ar-review-flow.ts`，§4.5）：无旧纹理时中置信自动应用+可复核提示、低置信进入复核态（[应用到试戴][继续调整][取消]，应用后可单级撤销），有旧纹理时高置信显示替换预览、中低置信必须确认（修订 2026-10-29 的「一律自动应用+提示」口径）；分析标签为启发式参考，真实端到端复测见§5.4 |
| 独立 AR 演示桥接 | `/ar-demo` | 占位 | 仅将本机 `http://localhost:8080/?embedded=jiaru-main` 临时嵌入 iframe，要求用户另行启动 Python demo；不是生产 AR 服务，部署环境不能依赖该地址 |
| 视频自适应展示 | `calculateCoverVideoLayout()` | 已完成 | 保持比例，采用居中 cover 裁切，不拉伸 |
| 个性化美甲分析推荐 | `/nail-analysis` | 待验证（工程门通过；真实照片与真机验收待补） | 纯规则启发式，不引入新模型训练：浏览器本地完成甲面候选识别、甲床/手型派生比例、甲周肤色采样（Lab/ITA°/底调，含甲面自污染排除与采样质量门）、指甲健康三类启发式，结合场景问卷由确定性规则引擎推荐甲型、长度与色系并附中文解释，可一键跳转 `/editor?preset=` 预选最接近主色的纹理套装（不自动贴合）。默认全部本地计算；v1.2.217 起甲面候选识别另提供用户显式选择的云端辅助通道（一次性隐私确认后图片才上传，仅用于本次定位，见 §5.5），甲面定位之外的分析计算（比例派生/肤色采样/规则推荐）仍在浏览器本地完成，不新增其他上传通道；即使开启「用户改进计划」分析结果也不外发。正式模型未部署期间识别100%走辅助定位且无像素级mask（云端候选同为低置信辅助），指甲健康通道不可用（隐藏而非降级展示），琥珀辅助声明页面级常显，不得表述为自动分析成功，也不计入正式识别成功率或Beta直接可用率；0候选时不产出任何推荐。设计文档：`docs/nail-personalization-design.md`、`docs/nail-personalization-research.md`。 |
| 美甲纹理自动识别 | `/ar-tryon`图片纹理识别 | 已发布（浏览器业务，v1.2.256；商用完成门 HOLD） | 生产manifest `nail-texture-seg-geometry64-browser-aa4-v2`：几何64轮 Stage A（512 letterbox）+ Stage B 径向精修（2048角×129径向，presence拒识）双 ONNX，WASM 单后端（发布对拍绑定）；mask 替换型 stage2 组合（§6.2/§7）。业务发布门全部通过：ONNX↔PyTorch数值保真（det相对7e-7、presence相对3e-6、确定性非零控制）、Python↔浏览器逐实例mask对拍三方（PyTorch CPU/serve GPU/浏览器WASM）IoU全=1.0、letterbox字节级diffBytes=0、生产服务器 `/ar-tryon` 真图端到端自动提取4指纹理无降级提示、全量1530测试。已知限制：商用完成门（严格联合≥539/634、独立val/留出、四类真机、Beta≥100、双批准回滚）保持HOLD；训练分布外甲面（超长淡色梯形甲等）召回弱（2026-11-05探针实证），按用户反馈迭代512轮版或后续权重 |
| 传统算法降级 | `recognizeNailTexturesWithFallback()`、`NailArtPicker` | 已实现（故障兜底；正式模型已发布） | 正式模型部署后自动流程默认走模型路径；仅模型加载/推理失败或manifest回滚为`not-deployed`时进入fallback并显示琥珀色辅助定位/人工确认提示，0候选提示手工添加。MediaPipe/局部近景无像素级mask，不计模型成功或Beta直接可用率。行为及发布拦截本地独立测试通过，真实浏览器产品路径待验收。 |
| 本机自研业务候选 | `/ar-tryon`参考图→精细抠图、`/api/nail-matte` | 本机接入已验证（v1.2.255）；浏览器版已发布（v1.2.256） | `jiaru-real100-geometry64-trial-v1`：真实100源Stage A+几何64轮精修，按已完整终评分支的平均Boundary IoU选择。API4枚原尺寸mask与既存终评逐像素一致；浏览器自动/手动各一次均200、4实例，手动匹配4/5并应用纹理。Python/GPU回环服务，前端沿用1600 JPEG编码/候选匹配/复核；同权重的浏览器版已作为正式业务发布（`nail-texture-seg-geometry64-browser-v1`，§6.2/§7），本机通道保持可用作对照与回退。启动、回退和证据见[业务候选说明](nail-texture-business-candidate.md)。 |
| 本机精细抠图（WeVisOne-VL） | `NailArtPicker` 侧栏「精细抠图（本机）」、`POST /api/nail-matte` | 已实现（辅助能力，默认关闭；路由级 5/5，UI 端到端 2026-10-28 为 3/5、2026-10-29 同图复测 5/5） | 仅在服务端配置`VLM_MATTE_URL`时出现入口：浏览器把原图压到长边≤1600 JPEG后提交，由同机`127.0.0.1:8008`的WeVisOne-VL-4B int4生成整图软 alpha（服务默认`--max-pixels 262144`），按「实例中心落入候选框优先、外接框IoU≥0.15兜底」与现有候选一一匹配并**只替换mask**（不增删候选、不改指位与置信度）。2026-10-28 实测：业务路由整图请求 5 实例/16.6s/5 候选全匹配（`output/nail-matte-p3/20261028-210056/`），nvidia-smi 设备峰值 7817 MiB（8 GiB 卡余量约 370 MiB）；1048576 档在同一原图只解出 1 个`<OBJ>`（响应文本含 5 个框），故不作为默认。UI 端到端（`/ar-tryon` 多纹理上传）2026-10-28 同图返回 5 实例、14.3s，但只替换 3/5：两个未匹配候选与服务实例框仅部分重叠（IoU 0.075/0.049），本地 MediaPipe 候选几何偏移且偏小，按保守规则保留原 mask，未发生错误替换；2026-10-29 同图复测 5/5 全匹配并完成归一化提取（`output/nail-matte-ui-v165/`，当轮本地候选几何更准，匹配规则未变）。2026-10-29（v1.2.165）修复：客户端匹配前把候选框换算到编码空间，原图长边 >1600 时候选框（原图坐标）与实例框（编码坐标）此前不同域会导致匹配恒不命中。2026-10-29（v1.2.166）默认档换档：36 张真实照片、203 枚完整甲人工真值评估显示 589824 档实例级召回仅 0.8325（Wilson95% [0.7751,0.8776]，低对比裸色/果冻甲漏检集中，skin_low_contrast 桶 0.6364），262144 档召回 0.9803、单图均时 16.2s→9.0s，1310720 档反而劣化（探针 20/42），故 `DEFAULT_MAX_PIXELS` 改为 262144（真值与逐图数据在 `output/matte-edge-lab/real-eval/`，不入库）；代价是 192 个配对实例中位二值 alpha IoU 0.957、约 1–2% 实例形状漂移（含个别向皮肤溢出，2/601 实测 2.55× 面积），由前端 ≥128 二值化与「需复核」流程消化；「指甲（共N枚）」query 计数提示（589824 档召回 0.9951、欠数提示会截断召回）与 LLM int4+视觉塔 bf16 混合量化实测均无附加收益，不采纳。未配置/忙/超时/鉴权失败一律降级并保留本地结果，不自动重试；本地0候选时可发起一次兜底识别，结果固定`confidence:"low"`且需逐指核对。2026-10-29（v1.2.167）起该能力并入自动流程：选择器识别完成时，若用户已记住隐私确认（`jiaru.nail-matte.notice.v1`）且服务就绪则自动执行一次精细处理；本地识别0候选时改为自动执行一次兜底识别（2026-10-29 v1.2.168；每次选择器打开至多一次，不自动重试口径不变；未确认则跳过、直接使用本地结果，不发送任何图片）；2026-10-30（v1.2.169）修复：兜底 detect 候选的 cx/cy/length/width 改由 alpha 栅格实心边界按原图坐标域逐轴推导（与提取端 `imageWidth/mask.width` 映射同口径），空栅格才回退编码空间实例框——此前直接采用上游编码图（长边 ≤1600）坐标域的实例框，长边 >1600 原图的选择器叠加层会整体缩聚到左上角（提取不受影响，因其只消费 mask 栅格）；自动流程对兜底低置信候选改为自动提取并上屏、界面保留「需复核」提示（原「需逐指核对」条款按2026-10-29用户决策修订为「自动应用+提示核对」，旧值保留于当日开发日志），手动路径仍保留逐指核对文案。2026-10-31（v1.2.177）matting query 定版为英文单词 `nails`：262144 档下同一 36 图/203 完整甲真值实测截断召回 1.0000（203/203 零漏检，此前「指甲」0.9803 的最后两处漏检——2/451 奶油甲与 3/973 全部 4 枚银色甲——均找回）、单图均时 9.0s→8.0s（每实例 `<ref>` 更短）、欠检图 0；对基线的实例增量为 +4 召回、−3 冗余碎片（1/234 −1、3/1134 两片合一片）、+2 皮肤假阳性（3/1026、3/1080，均不落入候选框、按规则保留本地 mask，无功能影响）；225 个配对实例中位二值 alpha IoU 0.9949（几何无回退）；预热后跨重启复现同一探针结果，裸甲/果冻甲对照（1/238、1/4、2/792）无系统性抑制。「manicured fingernails」召回 0.9951 但单图 12.9s（+43%，`<ref>` 每实例重复长词），单词「manicured」不稳定（个别图塌缩为 1 实例），均不采纳；`vlm-refinement.ts` 两处请求与 `server.py`/`matting.py` 默认 query 同步改为 `nails`。不计正式识别成功率、Beta直接可用率、阈值校准或训练真值，不写生产manifest、不产生releaseIdentity，PRODUCT HOLD不变。 |
| 合成/烟雾模型 | `/models/nail-texture-seg-synthetic-v1/` 等 | 占位 | 仅用于接口、后处理、浏览器集成和性能验证，不代表真实识别质量 |
| 正式纹理模型 | `/models/nail-texture-seg/manifest.json` | 浏览器业务已发布（v1.2.258）；商用完成门 HOLD | 当前发布身份 `nail-texture-seg-geometry64-browser-aa4-v2`（`deploymentStatus: "deployed"`，Stage A SHA `0a6b842e…b4e78`、Stage B SHA `e63d50f0…97ef`，源权重 SHA 见§7）：业务发布门（导出数值保真、Python↔浏览器mask对拍、浏览器端到端、测试链）已全部通过并经 register/switch 登记。商用完成门（正式训练准入v7及新来源val/正负留出、角标捷径消融、真机/Beta与双批准权重回滚）未闭合，completion audit `decision=complete` 前保持 HOLD；candidate57受保护test100失败保持，历史测试部署例外不构成正式发布。当前证据与下一路线见§11.1、Goal及当日日志。 |
| 纹理边缘覆盖率抗锯齿 | `edge-refine.ts`、`extract-mask-texture.ts` | 已接入（产品层） | 原始半径/二值mask独立保留，边界带4×4覆盖率经Worker传递，纹理alpha连续缩放、RGB直接原图采样。100图634甲/636候选离线重放通过；两种受限平滑均退步并关闭。部署尺寸4实例原mask零差及覆盖率Python↔TS零字节差。原严格联合0/634保持，真机与未见边界质量待验；详见§6.4/§7及边缘评审文档。 |
| 数据集治理 | `model/datasets/nail-texture-v1`及候选物化报告 | 进行中（发布角色需重建） | 仓库历史基础数据集仍为409图/2142 mask、split=300/46/63；正式训练输入已演进三代：candidate52/56（328张正图/1981 mask/112来源组加160张train困难负样本，物化train488/val30/test0）→ candidate58b（343张/2071 mask/127来源组，train503）→ 循环011/012开发口径（唯一一次12 epoch训练为循环012，350图训练文件树`34fe0a85…1edf`、124来源组均衡采样）。train内来源组开发折已由循环001—015落地为现行评估主线，clean98开发基线（58图/354-mask v2加40困难负图）与循环015扩容（源图供给55图/55来源组/322甲冻结、开发评估真值43图/265甲、训练禁用）为当前事实；旧val30、旧test100及编号261—360、361—460等已消费holdout现在只作受保护历史回归，禁止训练、配方/阈值选择或再次冒充未见证据；候选锁定后的全新校准集、一次性正样本发布留出与全新困难负样本要求保持不变；当前无批准发布候选。 |
| 验证真值当前快照 | 外部`val-annotation-workspace-v1/validation-truth-index-v1.json` | 已完成 | v1.1.189：30个批准报告归并为30张唯一图片/144个完整mask、0拒绝、0冗余、0冲突，索引SHA-256为`2ccde9420141e5e67a9696959cc18e78aaee808ba29b592670990967bdc4b92d`。批次014—018严格排除裁断、遮挡或甲数错误源图，透明甲尖和全部附着装饰均经整图与逐甲2×复核；所有polygon合法且同图严格零交叠。规范val-only数据集物化为30图/30 annotation/30 label/144 mask、train/test均0、孤儿0，物化报告SHA-256为`200b087b…b1776`。来源隔离审计对当前train 100张和冻结test 67张重新读取、复算身份，文件名、图片SHA-256和来源组均零重叠，报告SHA-256为`7372d14d…f6479e`。最终审计SHA-256为`5152dc52…66a3a`，决定`approved_as_calibration_truth`、`calibrationTruthEligible=true`，同时保持`trainingUse=prohibited` |
| 规范候选训练数据与输入门 | `finalize-reviewed-hard-negative-manifest.py`、`materialize-canonical-candidate-training-dataset.py`、`audit-candidate-training-input.py`、`train-yolo-seg.py --candidate-mode` | 已完成（第二候选输入PASS） | 固定正式下限为train正样本100、正式hard negative 100、val30且CLI不得下调。第二候选包为train258（100张正样本/521 mask + 158张零字节标签困难负样本）、val30/144 mask、test0、孤儿0，物化与输入深审分别为`033b8d02…2ec`和`b9bd6897…94dd`，文件树SHA-256为`8709fa80…1170`。GPU训练前后均重放通过，Ultralytics缓存仅出现在隔离runtime并已清理；输入PASS只授权本次候选训练，不授权模型发布 |
| 候选三路训练发布编排 | `run-training-release-pipeline.ts --candidate-mode`、`verify-training-release.ts --candidate-mode` | 进行中（candidate5发布拒绝） | candidate5已完成隔离训练、规范val30、冻结test100和训练后新100张独立留出全链；独立留出三变体未通过零误检/零delta门，因此终止导出与登记。下一候选必须使用与编号361—460留出隔离且另获商业训练授权的新训练负样本，训练后再建立另一份全新未见独立留出；不得复用或按本次模型输出缩减当前清单 |
| 移动真机基准与证据门 | `/device-benchmark`、`build-nail-texture-mobile-memory-raw.ts`、`build-nail-texture-device-acceptance.ts` | 已完成（工程门） | 真机页固定3次预热+20次正式推理，导出同一session/device/model/backend/input身份；fallback、混合身份和少样本不能晋级。Android Profiler/iOS Instruments内存CSV经会话与源SHA绑定后进入内存验证；设备验收v2和最终完成度审计均深度重算性能样本、原始内存、统计、路径及哈希，拒绝伪造外层PASS、跨session和写后漂移。2026-07-28复核本机ADB可用但未连接任何设备，PnP未发现移动设备，`idevice_id`不可用且四份真机报告均不存在，因此`M3-T3-DEVICE`继续PARTIAL |
| 训练/评估/导出 | `model/training/*` | 进行中（candidate8拒绝，准备下一轮数据） | nano分支早停于epoch23、最佳epoch3；val30阈值0.55通过后一次性冻结test100逐实例门失败。高容量分支早停于epoch51，最佳权重`2be3104e…6081`，仅用val30比较时阈值0.60召回0.76389，低于nano的0.80556，故不运行test。下一步以新来源完整甲面真值提升召回；继续禁止ONNX导出、登记和部署。 |
| 模型发布治理 | `scripts/*release*` | 进行中 | 已有注册、切换、回滚、质量门、逐图失败画像、规范val30阈值深审、三路候选编排、最终完成度审计和外部验收证据构建器。独立留出链固定100张下限、训练用途禁止、权重/阈值绑定、首次推理账本、512输入、确定性三变体和推理重放。首个正式发布采用“双批准版本”启动：先以`--set-current false`登记独立通过全部发布门的fallback，再激活另一个不同版本；仍需两个版本全部manifest/模型字节完整且至少一个非当前候选，禁止synthetic/smoke或已拒绝模型充当回滚。真实candidate4独立留出3/2/3张误检仍按预期HOLD；当前没有合格生产资产 |
| 隐私说明 | `/privacy` | 已完成（产品文案；法律合规审核仍待外部） | 静态说明页覆盖核心原则（本地优先/数据由你掌控/不追踪）、「用户改进计划」开关（客户端组件，默认开启，可随时关闭，状态存 localStorage）、各功能数据流向（试色默认本地、AI生图仅文字并经第三方Agnes、AR默认内存处理不录制、识别与图库本地）、第三方与用户权利；v1.1.470 已将“不上传照片”承诺修订为改进计划模式；当前尚无实际上传通道，开关为偏好记录；法律/产品合规审计不构成 |
| 用户账户（注册/登录） | `/login`、`/account`、`/api/auth/*`、`/api/me` | 进行中（Phase 1 初始注册登录已实现；商户/云同步未开始） | v1.1.475 已落地初始注册登录功能：手机号+验证码「登录即注册」，自研 HS256 JWT（access 2h + refresh 30d）+ SQLite 会话表（可踢下线）；`/api/me` 档案与登录方式管理（查看/解绑，至少保留一种）、账号级「用户改进计划」偏好（§5.6 联动 localStorage）。v1.1.476 起发送短信验证码前必须通过人机验证（自研 SVG 图形验证码 `GET /api/auth/captcha`，5 分钟有效、一次性、错 5 次作废、60 秒节流保持不变）。v1.1.477 起按用户要求仅保留**手机号 + 微信**两种登录：新增微信 OAuth 全流程（`GET /api/auth/oauth/wechat` 授权跳转 + `/callback` 回调登录，state 存 httpOnly Cookie 防 CSRF，code 换 openid，首次登录须在 `/account` 补绑手机号，`/status` 探测配置），**邮箱与 GitHub 登录入口已移除**（email-register 路由删除、bcryptjs 依赖卸载、/login 页邮箱 tab 与 GitHub 占位按钮删除、/account 新增「绑定手机号」卡片含人机验证）。微信登录需 `WECHAT_APP_ID`/`WECHAT_APP_SECRET`（开放平台企业认证，300 元/年），未配置时按钮显示「未配置」、接口返回 503。数据库为本地 SQLite（Node 内置 node:sqlite，路径 `data/jiaru-user.db`），生产换 Postgres 时仅替换 `src/lib/auth/db.ts` 边界。短信验证码在未配置服务商时进入开发模式（接口返回 devCode 仅供本地联调），生产须配置短信服务商。v1.2.153 起 `/account` 个人资料可编辑头像/昵称/简介/公开联系方式（契约见 §5.3），页面含查看/编辑双态、字段校验、保存取消、成功失败反馈与加载骨架/失败重试；头像为 256×256 压缩 data URL，旧库由 `createUserDb` 自动补 `bio`/`contact`/`contact_type` 列。完整设计见 `docs/user-system-plan.md`（v0.2，Phase 1 目标）；商户体系、云端作品/收藏/历史/色板、配额、注销导出、游客数据合并仍为后续 Phase 1 项 |

## 4. 页面与用户使用接口

### 4.1 启动与访问

```powershell
cd "E:\AI Project\Codex\JiaRu"
npm.cmd install
npm.cmd run dev
```

默认访问 `https://localhost:3000`。开发脚本使用 `next dev --experimental-https`；若本机自签名证书生成失败，Next.js 可能回退至 HTTP。摄像头应通过 `localhost` 或正式 HTTPS 域名访问，不应使用普通局域网 HTTP 地址。

生产启动应先执行 `npm.cmd run build`，再执行 `npm.cmd run start`。开发模式的实验性自签名 HTTPS 不等同正式部署证书。

Sites 公网静态演示已部署：`https://jiaru-private-trial.rare-wren-2089.chatgpt.site`，构建生成13个页面；账户、AI生图、云端识别等服务端接口尚未接入，公网 IPv4 请求首页 HTTP 200；当前本机浏览器此前遇连接关闭，交互待验。正式纹理模型继续 PRODUCT HOLD。源码副本与构建位于 `output/sites-jiaru-trial/`。

云端生产部署形态（2026-10-04 实测）：腾讯云轻量服务器 `lhins-1oklqsh2`（ap-beijing-7，公网 `49.233.141.42`）上，Next.js 以 `next start -H 127.0.0.1 -p 3000` 只监听本机，由 Nginx（`deploy/nginx/jiaru.conf` + `jiaru-proxy.conf`）终结 80 端口并反向代理，**3000 端口不得直接暴露公网**；应用层设 `JIARU_TRUST_PROXY=1` 后采信 `X-Real-IP`/最右 XFF 用于限流与来源推导，写操作由 `src/middleware.ts` 校验 `Origin`。此前遗留的 iptables 80→3000 REDIRECT 会绕过 Nginx 使反代形同虚设，已移除并停用 `jiaru-port80.service`。该地址为 HTTP，非安全上下文，`getUserMedia` 不可用，AR 摄像头仍需 HTTPS 域名或本机隧道演示。

生产验证命令：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

### 4.2 `/editor` 图片试色

状态：进行中（2026-10-31 v1.2.173 画布模型重写为「甲面框 + 纹理贴合实例」；v1.2.174 页面接线落地，纯色试色删除；v1.2.179 真实照片纹理资产登记与浏览器端到端功能验收通过，hover 视觉细节待用户实机复核）。

画布模型（v1.2.173 起，取代旧「纯色笔刷笔画」模型）：

- 识别级联（`src/lib/nail-detection-cascade.ts`，§6 同源识别）产出的甲面框（原图像素域）以绿色虚线椭圆＋指名（拇/食/中/无/小）或序号标签叠加在底图上，`showFrames` 控制；点击空框把当前纹理（`src/lib/nail-texture-sets.ts` 纹理套装，甲尖朝上、紧致裁剪、自带 alpha 轮廓的 ≤256px RGBA PNG）贴合为 placement 实例，`activeTexture` 为 null 时仍回调由页面提示；同一框重贴时旧贴合按 `frameId` 替换。
- 贴合渲染长宽比保真：渲染长 = 框宽×纹理长宽比（`computeTextureRenderPlan`：甲根边缘锚定、不短于框长、上限 3×框长，延长沿甲尖方向伸出）；用户微调长度/宽度/甲根位置经 `adjustNailGeometry` 钳制（0.75–1.4 / 0.7–1.45 / ±0.2，rootOffset 正值向指根方向 (−sin(angle), cos(angle))）。
- 指针交互优先级：贴合命中（选中＋拖动；拖动中组件本地预览、松手提交，位置钳制画布范围内）→ 甲面框命中（`onFrameClick`）→ 加框模式空白点击（`onEmptyClick`，原图坐标手动加框）→ 取消选中；命中域为旋转椭圆（逆旋转到局部坐标，数组末尾顶层优先）。
- 显示与输出分离：预览画布最长边 400/600（`previewScale`，沿用旧口径），贴合几何以原图像素域存储；保存时按原图尺寸离屏重放全部贴合（贴合存储域即原图像素，重放因子恒为 1），4096 方图导出仍为原尺寸，输出 `jiaru-<时间戳>.png` 下载；纹理经模块级缓存预加载，未就绪时加载完成后重绘。
- 纯逻辑模块 `src/lib/canvas/placements.ts`（node 可测）：`buildPlacementFromFrame`（框+纹理→贴合，确定性 id `placement-<frameId>`）、`applyPlacementAdjust`（从 base 几何重算渲染几何）、`placementHitTest`/`frameHitTest`、`placementDrawList`（按因子缩放的导出重放清单）、`previewScale`、`loadTextureImage`/`loadTextureAspect`（aspect=naturalHeight/naturalWidth，非法回退 1）。旧笔刷模块 `src/lib/canvas/strokes.ts` 已删除。
- `src/components/NailCanvas.tsx` 为无状态画布组件（placements 全部由 props 传入、事件上报；选中贴合画珊瑚色椭圆高亮）：

```ts
<NailCanvas
  imageUrl={string}
  frames={readonly PlacementFrameInput[]}        // 识别甲面框（原图像素域）
  placements={readonly NailPlacement[]}          // 贴合实例（原图像素域）
  activeTexture={{ key, src, aspect } | null}    // 点击空框时贴合的纹理
  selectedId={string | null}
  showFrames={boolean}
  addingFrame={boolean}
  canUndo={boolean}
  onFrameClick={(frame) => void}
  onPlacementSelect={(id | null) => void}
  onPlacementMove={(id, cx, cy) => void}         // 拖动结束提交
  onEmptyClick={(x, y) => void}                  // addingFrame 时手动加框（原图坐标）
  onUndo={() => void}
  onReset={() => void}
/>
```

使用方式：上传或拍摄清晰的手部图片（文件选择器与运行时均限制为 JPG/PNG/WebP、最大 10 MB、宽高各 320–4096 像素）→ 识别甲面框 → 选择纹理套装（可展开钉选单指纹理）→ 点击甲面框贴合 → 拖动/微调 → 撤销、重置和保存。

页面接线（v1.2.174 起，`src/app/editor/page.tsx`）：

- 识别与兜底：上传成功后自动执行一次识别级联（画布取 imageData 最长边 ≤800 → `computeImageDetectedNailRegions` → `autoAssignNailRegionFingers` 补缺失指位），过程浮层提供「跳过」转手动加框；0 区域且用户已记住本机抠图隐私确认（`jiaru.nail-matte.notice.v1`）且服务就绪时自动执行一次 `detectNailsWithMatte` 兜底（候选固定低置信、warnings 保留），否则提示手动添加。识别失败/降级一律保留已有甲面框并显示辅助定位声明（`auxiliaryDetectionNotice`），界面不出现「自动识别成功」类表述。v1.2.217 起识别提供「本地 | 云端」模式切换（`NailDetectModeSwitch`，识别模式为会话级、默认本地）：云端模式跳过浏览器级联，按所选云端后端调用 `/api/nail-detect-ark`（方舟视觉，框→轴对齐低置信候选）或 `/api/nail-matte-cloud`（云端自托管 matte 契约），结果经 `nailCandidatesToDetectionRegions` + `autoAssignNailRegionFingers` 进既有甲面框链路（撤销栈操作键 `cloud-detect`）；云端 0 候选提示手动处理、不做静默二次兜底，降级/错误保留本地结果并显示分类文案（`cloudDetectMessageFromReason`）。
- 纹理选择：侧栏 `TextureSetPicker` 卡片堆叠——静止态前 3 张可见（第 1 张为该套拇指纹理封面＋套装名），桌面 hover / 移动端点按容器展开为 5 张单指卡扇形（FAN=56px，360px 面板内不溢出），点堆叠＝应用整套、点单卡＝钉选单指纹理，展开时页面渲染全页模糊遮罩（z-30，堆叠 z-40 置顶）；解析顺序为 `pinnedTextureKey`（"<setId>/<finger>"）优先，其次激活套装按甲面框指位取纹理，指位缺失或该指无纹理时提示「请先在套装中确认指位或钉选单张纹理」并不贴合。`?gallery=`/`?preset=`/灵感卡回调经 `closestTextureSet` 映射最接近主色的套装；v1.2.215 起灵感款（`?gallery=` 灵感卡、本地作品卡、侧栏灵感卡点击确立）在识别出甲面框后自动贴合一次（见下），`?preset=`（个性化分析推荐）仍仅预选不参与自动贴合，无匹配套装时忽略并提示。

灵感款自动贴合（v1.2.215，2026-11-03 用户指示）：

- 编辑器 `applyInspirationSet`（`src/app/editor/page.tsx`）：灵感款来源（名称＋套装 id）确立后登记待贴合；识别级联产出甲面框时若当前无贴合实例且本次上传未恢复会话草稿，自动 `applySetToFrames` 贴合并压撤销栈（操作键 `inspiration-apply`，可单次撤销回「已识别未贴合」），提示贴合数量与「可逐指调整或撤销」；每次上传至多自动一次，更换照片（`resetEditState`）重新武装。灵感色先于识别完成时由识别完成路径触发，识别先完成时由灵感卡确立路径即时触发；无可匹配指位或套装缺失时提示手动贴合，不静默失败。
- 图库侧（§4.3）：点击灵感卡图或标题先弹「试戴方式」选择弹层（AppDialog）——「上传手部照片 · 静态试色」→`/editor?gallery=<id>`（走上述自动贴合）、「开启摄像头 · AR 实时预览」→`/ar-tryon?gallery=<id>`（走 §4.5）；卡片底部「试色/AI 相似款/AR 试戴」三出口保持直达。
- 纯逻辑模块 `src/lib/editor-texture-state.ts`（node 可测）：`resolveActiveTexture`（钉选/套装指位/缺失三分支）、`replacePlacementForFrame`（同框重贴先移除旧贴合）、`pushPlacementHistory`/`undoPlacementHistory`（撤销栈快照与弹栈）、`buildManualFrame`（nl/nw 按原图最长边 10%/58% 推导并钳制 42–120/28–72、指位取首个空闲）、`frameToMatteCandidate`、`applyRefinedFrameMasks`（按 candidateId 回填 mask 并以 `frameGeometryFromMask` 重算帧几何，几何为 null 时保留原几何）。
- 本机精细抠图（辅助路径）：NailMattePanel 的精细处理只替换 mask 并重算帧几何（不增删候选、不改指位与置信度），结束后提示「已精细处理 N/M 个甲面」；兜底识别与自动兜底同口径。降级/错误一律保留本地结果。
- 贴合撤销栈只记 placement 变更（点框贴合、拖动结束提交、滑杆经 `applyPlacementAdjust` 75–140%/70–145%/±20%、删除贴合、重置），同一操作键 800ms 内合并入栈；旧纯色逻辑（`ColorPalette` 组件、nailColors、applyToAll）已整体删除。

纹理资产（v1.2.179 起）：`src/lib/nail-texture-sets.ts` 的 `NAIL_TEXTURE_SETS` 登记 5 套真实照片纹理套装（黑耀碎闪、奶茶金饰、玫红爆闪珍珠、蓝粉珍珠混搭、裸粉白星法式），每套 5 指纹理落盘 `public/nail-textures/<setId>/finger-1..5.png`，由可复用脚本 `scripts/build-nail-texture-sets.py` 从 `E:\AI Project\Codex\JiaRu_image\真实素材\美甲图片素材` 的 5 张真实照片（1/301、2/563、3/1161、1/437、1/234）经本机 WeVisOne-VL 抠图服务（§5.4 同服务）提取：exif_transpose → 长边 ≤1600 JPEG q0.85 → `/matte` 实例 alphaPng → 栅格 ≤1024 → 主轴角摆正、alpha 羽化、紧致裁剪、≤256px RGBA（与 §4.5 纹理提取同一数学约定）；每源 instance_count 必须 =5，确定性贴边细条过滤剔除误检，拇指→小指映射与朝向经 plan.json 逐张人工复核修正。`dominantColor` 取提取纹理主色统计，供 `closestTextureSet` 灵感色映射（§4.3/§4.6 出站链路）。资产仅供编辑器点选贴合消费；纹理提取与识别级联辅助定位均不计入正式识别质量结果。

数据边界：上传校验在浏览器本地完成；通过后才调用 `URL.createObjectURL()`，页面卸载或更换文件时释放对象 URL。无效 MIME、超限大小、解码失败、过小或过大分辨率会在上传区显示可读错误，不创建编辑会话。

编辑器交互重构（v1.2.213，frontend-interaction-redesign-plan Batch 4）：

- 对象面板 `src/components/EditorObjectPanel.tsx`：按甲面框枚举编辑对象（`items[]` 含名称、是否已贴合、贴合影名、手动框标记），列表行点击选中（`aria-current` 高亮），面板提供贴合替换（当前纹理）、微调聚焦、贴合删除、空框贴合（`onApplyToFrame`）、指位修改（`onAssignFinger`）与甲面框删除入口；空态提示上传识别或手动添加。
- 撤销栈扩展：覆盖甲面框与贴合的增删改（画布全局 keydown 支持选中对象的键盘操作），撤销/重做后同步清理失效选中；同操作键合并口径不变（800ms）。
- 会话草稿 `src/lib/editor-draft.ts`（node 可测）：编辑态变更防抖写入 `sessionStorage`（键 `jiaru-editor-draft-v1`，mask 字段剥离后序列化，存储异常静默返回 false）；恢复时校验原图尺寸一致才应用（`draftMatchesImageSize`），换图与导出成功时清除。
- 导出治理：存在未保存编辑时 `beforeunload` 提示（导出成功复位豁免，继续编辑重新生效）；导出跳过无法加载的贴合时仍完成并明示跳过数量。
- `?work=<id>`（WorkItem，§4.4）：读取本地作品预览展示为灵感卡，优先于 `?gallery=`/`?preset=`；不自动装载照片；v1.2.215 起作品灵感卡确立后与 `?gallery=` 同口径（识别出甲面框后自动贴合一次），产品其余能力边界不变。

历史口径：2026-09-05 评审缺陷登记与 v1.1.658 笔画模型修复记录见 `docs/archive/whitepaper-changelog-archive.md`；本节自 v1.2.173 起仅保留当前模型合同。

### 4.3 `/gallery` 灵感图库

状态：已完成（2026-09-03，v1.1.580/581/583）。

当前使用 `src/lib/utils.ts` 中的 `GALLERY_IMAGES` 和 `public/nail-gallery/ai-look-1..6.jpg`。这 6 张素材由本项目 Seedream pro 引擎（`doubao-seedream-5-0-pro-260628`，经 `POST /api/generate-seedream`，`ratio:"1:1"`+`size:"1K"`=1024x1024 文生图）于 2026-09-03 生成（v1.1.580），对应款式渐变裸粉/法式白边/亮片闪粉/简约纯色/复古花纹/宝石镶嵌，逐张下载落盘为本地静态资源（165—221KB 有效 JPEG，不依赖 Ark 生成 URL 的 24h 有效期），并逐张通过原分辨率视觉审核（≤2 手、五指无畸形、款式与名称对应）。素材为演示用途的 AI 生成图，不代表真实商品款式，也没有真实素材授权链；旧 `placeholder-*.svg` 已随 2026-11-03 仓库清理一并删除，目录中不再保留。卡片交互（v1.2.215 起）：点击卡片图或标题先弹「试戴方式」选择弹层（AppDialog 基元）——「上传手部照片 · 静态试色」跳 `/editor?gallery=<id>`（编辑器识别出甲面框后自动贴合，见 §4.2）、「开启摄像头 · AR 实时预览」跳 `/ar-tryon?gallery=<id>`；另保留三个直达出口：①「试色」跳 `/editor?gallery=<id>`（v1.1.581 起被消费，编辑器以 Suspense 包裹的 `useSearchParams` 解析，空态渲染「灵感款式」参考卡，并将采样灵感色映射为最接近主色的纹理套装，v1.2.215 起识别后自动贴合，逻辑见 `src/lib/gallery-inspiration.ts`，灵感色为整图采样启发式推导不等于真实甲油色）；②「AI 相似款」跳 `/ai-generate?gallery=<id>`；③「AR 试戴」跳 `/ar-tryon?gallery=<id>`（v1.1.583，见 §4.5）。

**v1.1.583 新增：图库→AR/AI 链路打通与本地收录（IndexedDB）。**
- 桥接函数 `src/lib/gallery-bridge.ts`：`findGalleryLook(id)` 校验 id；`loadGalleryReference(id)` / `loadCollectReference(collectId)` / `loadReferenceFromParams({gallery, collect})` 把图库静态图或 IndexedDB 收录图取为 `File`（fetch 失败、非 2xx、非图片类型一律降级返回 null，不抛错）。
- AI 相似款（`/ai-generate?gallery=<id>` 或 `?collect=<id>`，v1.1.583）：`src/app/ai-generate/page.tsx` 以 Suspense 包裹的 `useSearchParams` 消费参数（与 v1.1.581 同一约定），进入后自动 `fetch` 图库图、`createImageBitmap` → 复用 `compressReferenceImage` 同源压缩链路填入参考图（与手动上传代码完全一致），并以款式名预填提示词（如「参考「亮片闪粉」的美甲样式，生成同风格的新设计」）；任何失败静默降级，不阻塞手动上传主流程。
- 图库到 AR 的纹理传递（§11.3 第 7 条已改写）：`/ar-tryon?gallery=<id>` 或 `?collect=<id>` 进入后自动取图、复用编辑器/AR 共用的 `validateImageUpload` + `URL.createObjectURL` 管线，直接打开多指指甲选取器（`setShowNailPicker(true)`）；失败降级不阻塞手动上传。编辑器纹理贴合自 v1.2.173 起仅限纹理套装（§4.2），图库→编辑器纹理传递仍无。
- **AI 生成结果一键收录**：`src/lib/gallery-collection.ts` 为原生 IndexedDB 轻量封装（库名 `jiaru-gallery`、store `collects`、keyPath `id`），`addCollect`/`listCollects`（按 createdAt 降序）/`deleteCollect`/`clearCollects`，所有函数对 `typeof indexedDB === "undefined"` 安全降级为 no-op（SSR 不抛错）；浏览器冒烟验证通过 `fake-indexeddb` 之外的 headless Chrome 实际写入。AI 生图结果区「收录到图库」按钮先 `fetch(imageUrl)` 取 blob（跨域受限时降级提示「先保存到本地再手动上传参考图」）再 `addCollect(blob, {engine, prompt})`。`/gallery` 卡片网格下方「我的收录」区块首屏不渲染、客户端 `useEffect` 读取 IndexedDB 后异步追加，避免 SSR 水合错位；收录卡带「我的收录」徽标、删除单条与「清空全部」入口，且同样具备「AI 相似款」(`/ai-generate?collect=<id>`) 与「AR 试戴」(`/ar-tryon?collect=<id>`) 入口；blob 的 objectURL 在卸载与删除时 `revokeObjectURL`。
- **收录区状态模型与删除治理（v1.2.213，frontend-interaction-redesign-plan §3/§4.3）**：`src/lib/gallery-collection.ts` 写路径不再静默假成功——IndexedDB 缺失/打开失败时 `addCollect`/`deleteCollect`/`clearCollects` 抛 `CollectUnavailableError`（`collectUnavailableMessage()` 提供分类文案），仅读取 `listCollects` 保持 no-op 降级；`probeCollectStorage()` 供页面挂载探测。「我的收录」区块状态为 checking/empty/load_error/unavailable 五态可区分文案（`StatusRegion`/行内反馈承载），单条删除采用 5 秒撤销窗口（新删除终结上一撤销点，卸载时提交真实删除，失败恢复卡片并提示），「清空全部」经 `ConfirmDialog` 确认（默认焦点 cancel）后才执行；删除/清空成功与失败均有可读屏反馈。图库挂载时把旧收录按 id 幂等迁移为 WorkItem（`migrateCollectsToWorkItems`，失败静默不阻塞展示，详见 §4.4）。

当前没有服务端数据库/上传管理/分页/搜索/跨设备同步。后续接入真实图库时应至少补充：资源 ID、来源授权、缩略图、原图、可试戴纹理、标签、创建时间、审核状态和删除策略。

### 4.4 `/ai-generate` AI 生图

状态：已完成（2026-08-10用户真实功能验收通过）。

使用方式：输入 1～520 字符描述，或选择预设风格按钮随机填入该风格的一段提示词，点击生成；成功后前端显示外部服务返回的远程图片 URL，并尝试跨域下载，失败时在新窗口打开图片。**输出尺寸与画面比例（v1.1.542，参考 Agnes Image 2.5 Flash「输出尺寸参考」表）**：用户可选**画面比例**（1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9，默认 1:1）与**输出尺寸档位**（1K/2K/3K/4K，默认 1K），页面实时显示最终像素尺寸（如 2K+16:9 → `2624x1472`）；文生图与图生图共用该选择，定义见 `src/lib/ai-image-size.ts`（`AI_IMAGE_SIZE_TABLE`）。**参考图（可选）**：可上传手部照片（浏览器端校验 MIME/≤10MB，canvas 压缩至最长边 1024 的 JPEG，上传时按原图比例就近选中画面比例，用户随后可在「画面比例」选择器中覆盖），上传后请求携带 `image`（Data URI）、`ratio` 与 `size`，服务端走图生图组装并启用**第二套图生图系统提示词**（`IMAGE_EDIT_SYSTEM_PROMPT`，与文生图系统提示词完全独立）：以参考图为唯一底图做局部编辑，唯一允许修改的区域是指甲，手部数量/姿势/动作、皮肤纹理与肤色、服装配饰、背景场景、光线构图等一切细节原样保留，禁止整体风格重绘，并保留手部解剖负面约束防止重绘缺陷；Agnes 在参考图手部指甲上直接绘制美甲样式（实测图生图约 12—41s，远快于文生图约 157s）；不上传则行为与历史文生图完全一致。参考图仅在用户主动上传时发送给第三方 Agnes，仅用于本次生成、不用于训练或存储。生成期间（loading 状态）右侧图像展示区不新增外框卡片：白色 shimmer 光带直接扫过整个展示区背景（光带限定在展示区内，由展示区 section 自身 `overflow-hidden` 裁剪，不会溢出到左侧提示词输入区；光带 80% 宽、峰值透明度 0.55、3.6s 周期并带 0.9s 淡入出现，适配 `prefers-reduced-motion` 时停用动画），中央沿用空闲态图标卡样式显示微光呼吸的 SVG 火花矢量图标（`src/components/Icon.tsx` 的 `sparkles`，v1.1.488 起全站 emoji 统一替换为内联 SVG 矢量图标）与「正在凝聚你的灵感…」文案；页面进入与空闲/加载/成功/失败四态切换均带柔和淡入上移过渡（`fade-in-up` 0.45s、页面级 0.65s），无接口变化。前端只向本项目 API 发送文字与（可选的）参考图。

**图库灵感自动带入（v1.1.583）**：从灵感图库「AI 相似款」入口进入时带 `?gallery=<id>`（或「我的收录」带 `?collect=<id>`），页面以 Suspense 包裹的 `useSearchParams` 消费参数，自动 `fetch` 图库图/`createImageBitmap` 复用同源压缩链路填入参考图，并以款式名预填提示词；任何失败静默降级，不阻塞手动上传主流程。生成成功后结果区「收录到图库」按钮把图片 `fetch` 为 blob 写入浏览器本地 IndexedDB（库名 `jiaru-gallery`，见 §4.3 与 `src/lib/gallery-collection.ts`），跨域受限导致 fetch 失败时降级提示「先保存到本地再手动上传参考图」；该收录不离开本机、不经任何服务端，可在 `/gallery`「我的收录」区块查看与删除。

**生成引擎（v1.1.564，Seedream 5 半分离接入）**：页面顶部新增「生成引擎」切换（Agnes 默认 / Seedream pro / Seedream lite），Agnes 链路与行为完全不变。选择 Seedream 引擎时：①尺寸档位切换为该模型的合法档位（pro=1K/1.5K/2K，lite=2K/3K/4K，默认 2K），与 8 种画面比例组合实时映射为显式像素尺寸（如 pro 2K+21:9 → `3136x1344`）；②提示词输入上限由 520 收紧为 300 字符（对齐 Ark 文档建议），计数器同步变化；③请求改发 `POST /api/generate-seedream`（契约见 §5.2），服务端组装 Seedream 专用精简系统词（`SEEDREAM_T2I_SYSTEM_PROMPT`/`SEEDREAM_I2I_SYSTEM_PROMPT`，约 100 字，独立于 Agnes 两套长系统提示词，二者互不复用）。参考图上传、压缩与图生图交互与 Agnes 一致。切引擎会重置尺寸档位为该引擎默认值。

**生图交互重构（v1.2.213，frontend-interaction-redesign-plan §6）**：`src/lib/ai-generate-flow.ts`（node 可测纯逻辑）提供请求快照 `createRequestSnapshot`（requestId/engine/prompt/ratio/size/referenceImage 不可变快照，请求只用快照）、端点解析 `resolveGenerateEndpoint`（契约不变）、请求体组装 `buildAiRequestBody`（model 字段仅 Seedream 需要）与错误分类 `classifyAiGenerationError`+`AI_ERROR_MESSAGES`（429→配额、401/403/503→服务未配置、504→上游超时、网络失败/超时/无效结果等八类文案）。页面行为：①生成期间不清空旧结果，新图成功后旧图折叠为「上一版」（可展开查看/一键设为主结果，互换时快照随之切换）；②生成中提供「取消生成」（AbortController 中断前端请求，取消是独立终态不算失败，不宣称服务端任务终止），失败时若已有结果则保留旧图并以反馈区呈现错误；③每引擎独立设置 `AiEngineSettingsMap`（尺寸档位与提示词草稿互不串扰，切换引擎恢复各自上次状态，不再强制重置）；④等待秒数计时在 live region 之外展示（读屏不反复播报）；⑤表单可访问性——textarea 可见 label「设计描述」、引擎/比例/尺寸 chips `aria-pressed`、提示词超限行内错误并禁用生成；⑥收录失败分类提示（存储不可用/读取失败等，见 §4.3），收录成功后同步登记 WorkItem（`src/lib/work-items.ts`：`jiaru-works` 库 `works` store，type `ai-result`，source 绑定请求快照的 engine/prompt；写失败不回滚旧收录、不打断成功反馈）。跨页参数新增 `?work=<id>`（优先于 `?gallery=`/`?collect=`，经 `src/lib/work-bridge.ts` `loadWorkItemReference` 读取本地作品为 File），仍走同源压缩链路，失败静默降级。

风格提示词库：`src/lib/ai-style-prompts.ts` 导出 `AI_STYLE_PROMPTS`，包含 10 个风格（甜美风、欧美风、日系、极简、复古、节日、水墨、几何、花草、金属），每个风格 50 段独立的中文场景提示词。用户每次点击风格按钮时，从该风格的 50 段提示词中随机抽取一段填入输入框（各风格独立随机，并避免连续两次抽到同一段；刷新页面后首次点击同样是随机结果）。提示词描述了底色、装饰、甲型、手持道具、光线、背景和皮肤质感等完整场景。`src/lib/utils.ts` 中原有的 `AI_STYLES` 字符串数组仍保留以维持向后兼容，但 `/ai-generate` 页面已改为从 `AI_STYLE_PROMPTS` 读取。

**图生图提示词约束（v1.2.161）**：内置风格提示词是完整文生图场景描述（含「女性手部近景生活照」「双手自然地捧着一个复古瓷茶杯」「温暖、柔焦的美学光线，温馨的背景」「精致美颜风格」），原样用于图生图会直接命令模型重绘背景、道具、光线与皮肤——修复前实测（`output/edit-preserve-test.png`）参考图被整幅换成「捧茶杯的温馨客厅」，与「保持原图」目标相反。现为三层约束：①`assembleAiImageEditPrompt` 不再拼接文生图场景后缀 `AI_IMAGE_SCENE_SUFFIX`（其 `close-up hand photo, beautiful, high detail` 本身就是重新构图指令），改用图生图专用后缀 `AI_IMAGE_EDIT_SUFFIX`，逐项锁定构图、取景、画幅与裁剪、机位与透视、背景物件与道具、光线与阴影（方向、强度）、色温与白平衡、景深与虚化、皮肤质感；②新增 `extractNailDesign(userPrompt)`，在服务端发送前按句剥离场景、人物、道具、光线、肤质与美颜类语句，只保留底色／图案／装饰／甲型描述（全部句被判为场景时退回原文，避免误删简短设计词），Seedream 图生图 `assembleSeedreamEditPrompt` 同样接入并使用精简后缀 `SEEDREAM_EDIT_SUFFIX`；③`IMAGE_EDIT_PREFIX` 与 `IMAGE_EDIT_SYSTEM_PROMPT` 增加「用户描述中涉及场景、道具、姿势、背景、光线与美肤的语句一律忽略，不是本图的修改依据」，系统提示词新增「禁止美化与重绘」（磨皮、美颜、锐化、HDR、滤镜、色彩分级、风格迁移、背景虚化或替换、重新打光、重新构图、改画幅）。修复后同一提示词与参考图实测（`output/edit-preserve-test2.png`）保留米白织物背景与柔和自然光、皮肤保留真实纹理，仅指甲按描述改为浅粉法式＋3D 蝴蝶结＋微珍珠。残余偏差（背景材质细节、新增袖口）来自 Agnes 图生图仅接受 `extra_body.image` 参考图、**无 mask 局部重绘能力**，且参考图 1200×1499(0.8006) 只能就近映射到 3:4，属模型与接口边界；若需像素级保留须改接支持 inpaint 的模型。测试：`tests/ai-hand-anatomy-prompt.test.ts`、`tests/seedream-prompt.test.ts`（16/16 通过）。

前置条件：

```env
AGNES_API_KEY=有效的服务端密钥
AGNES_API_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_IMAGE_MODEL=agnes-image-2.5-flash
```

当前服务端按Agnes Image 2.5 Flash协议请求`POST {AGNES_API_BASE_URL}/images/generations`，按用户选择的**尺寸档位**（`size`，1K/2K/3K/4K，默认 1K）与**画面比例**（`ratio`，默认 1:1）组合决定输出尺寸（默认即 `1024x1024`，由`size:"1K"`+`ratio:"1:1"`得到，行为与历史一致），并将`response_format: "url"`置于`extra_body`。总超时为180秒；503最多按1/2/4秒退避后重试，401、429及供应商异常保持结构化错误响应。基础地址与模型ID可由服务端环境变量覆盖；本机用户配置当前使用`https://api.agnes-ai.cn/v1`（2026-08-29由`https://apihub.agnes-ai.cn/v1`切换并换用新服务端密钥），其`GET /models`认证返回HTTP 200并列出目标模型，`/v1/images/generations`真实文生图返回图片URL且产物可下载。2026-08-10用户确认AI美甲真实生图功能已经验证通过，并于2026-08-12再次确认；该验收证明当前交互链路可用，不代表供应商长期可用性、成本或内容安全无需继续监测。AI输出可一键收录到本地图库，再由图库带入AI或AR；编辑器尚无直接消费生成成品的共享项目协议，见§4.3。

### 4.5 `/ar-tryon` AR 试戴


**当前贴合契约**：以 v1.2.259 `cuticle-fit-v1` 的甲根固定长度校准为基线；v1.2.261 增加独立长横轴投影、宽度校准与长度解耦、甲根锚定横移 ±40% 与旋转 ±30°、甲床行宽排除甲尖装饰影响；v1.2.265（`cuticle-fit-v4`）将甲根对齐改为 alpha 轮廓下部中心，摄影甲床宽度与完整纹理长度分别映射，根部短 alpha 过渡在离屏合成层完成；v1.2.267（`cuticle-fit-v5`）开启「甲根辅助线」后可在相机画面拖动根部圆点平移、甲尖圆点调长、侧边圆点调宽。v1.2.268 修复开发预览卡顿：PostCSS 按 `postcss.config.mjs` 中的绝对 src 路径扫描正式站样式。逐版本细节见 `docs/archive/whitepaper-native-precision-history.md`（D 节）。

浏览器模型纹理自v1.2.258使用4×4亚像素覆盖率抗锯齿：Worker保留原mask及独立覆盖率，原图纹理与连续alpha经提取、摆正后应用到逐指试戴。该处理针对栅格台阶；低对比甲缘偏移仍需模型/人工复核。真实开发图的归一化对照已闭合。同一来源100张完整参考图的手部几何在两组轮廓中均覆盖59/634甲，其余继续按轮廓和方向复核流程处理。对16张完整原图的59枚已配对甲，两组轮廓的轴端正确数均由39/59增至59/59，20枚纠正且39枚保持正确。该同来源子集的结果适用于已经建立几何配对的甲。七张掌面拒绝图中有一张手背斜侧照片；离线绕开拒绝可为该图恢复4枚正确方向，但也会为另外六张的21枚甲自动定向，生产继续保留掌面拒绝。逐甲与旁路证据分别见 `model/reports/hand-direction-remaining-v1/comparison.json`（SHA-256 `5ca6391ae8641b24d7a9ae0d3db17dace55a4315f91dc0eab6801901c434399c`）和 `model/reports/hand-direction-original-review-v2/palm-rescue-probe.json`（SHA-256 `0666714cb1c73a1471fdc6e8fafa2bb7cdd57deb4f7b7b9932dc89ba71e7b535`）。归一化证据见§6.4。

状态：待验证。

使用方式：

1. 选择“纯色”或“纹理”；
2. 纯色模式可逐指选色或应用全部；
3. 纹理模式可上传单个纹理手动裁剪，也可上传参考图提取多个甲面；正式自动模型可用时展示模型候选，模型不可用时先用MediaPipe Hands从完整手背照片自动生成五指甲面区域；若完整手部关键点失败，再对含2—5枚清晰已上色甲面的局部近景执行保守定位；两级辅助定位均无可靠结果时才进入“在图片上添加甲面”模式；v1.2.217 起选择器识别侧栏提供「本地 | 云端」模式切换（云端模式上传后直接走云端识别，云端 0 候选不做本机自动兜底；云端候选固定低置信、经既有复核门应用）；
4. 点击画面内唯一的“开启摄像头”按钮；该次点击会直接调用摄像头权限请求，不需要再点第二个启动按钮；
5. 将手放入画面并展示手背，系统根据手部关键点绘制指甲；
6. 手心、手背或不确定状态会显示对应提示，手心状态不绘制指甲纹理。

上传约束：PNG/JPEG/WebP，最大 10 MB，宽高各 320–4096 像素，并要求浏览器可成功解码；编辑器与AR共用同一校验器。摄像头画面默认只在内存中处理，不录制；「用户改进计划」开启时手部数据可能被上传（见§10，当前尚无实际上传通道）。

**图库灵感自动带入纹理（v1.1.583）**：从灵感图库「AR 试戴」入口进入时带 `?gallery=<id>`（或「我的收录」带 `?collect=<id>`），页面以 Suspense 包裹的 `useSearchParams` 消费参数，自动 `fetch` 图库图、复用编辑器/AR 共用的 `validateImageUpload` + `URL.createObjectURL` 管线后直接打开多指指甲选取器（`setShowNailPicker(true)`），用户即可在图中五指上分配甲面纹理；任何失败静默降级，不阻塞手动上传主流程。这是 §11.3 第 7 条原「图库款式到 AR 的纹理传递」的落地。v1.2.213 起该链路新增 `?work=<id>` 优先级最高（本地 WorkItem 作品，`src/lib/work-bridge.ts`），`?gallery=`/`?collect=` 保持兼容。

**AR 三步流程与覆盖前复核（v1.2.213，frontend-interaction-redesign-plan §7）**：

- 三步流程：页面顶部步骤状态条（选择来源 → 提取与复核 → 试戴与校准，`aria-current="step"`；顺序数据来自 `src/lib/ar-review-flow.ts` 的 `AR_STEPS`）。侧栏「第一步 · 选择来源」卡提供上传参考图 / 上传单纹理（`UploadTrigger`）/ 开启实时摄像头（递增 `startSignal` 由 ArView 消费一次启动）三个入口。
- 低置信覆盖前复核：`decideArReview({hasExistingTexture, lowestConfidence})` 按规则表分流——无旧纹理：高置信自动应用、中置信自动应用+可复核提示、低置信进入复核态；有旧纹理：高置信显示替换预览、中低置信必须确认。复核界面显示「已识别 N 个甲面，其中 M 个建议复核」（`formatArReviewSummary`）与逐指甲位标记，[应用到试戴]（应用后提示，可单级撤销恢复旧配置）/ [继续调整]（丢弃待应用集合重开选择器，不改配置）/ [取消]（不改配置）。自动路径文案由 `formatArApplyNotice` 提供。置信三档沿用 `NailTextureCandidateConfidence`（high/medium/low），整批按最低档决策。
- 弹层统一：`NailArtPicker` 与 `TextureCropper` 迁入共享 `AppDialog`（§4.8）——Escape 可关闭、提取中关闭视为取消（取消后不应用任何结果、临时位图统一释放）、关闭后焦点恢复打开按钮；`TextureCropper` 画布支持键盘选区（方向键移动、Shift+方向键调尺寸、无选区时 Enter 生成居中默认选区；几何纯逻辑在 `src/lib/ar-cropper-keys.ts`）。
- 摄像头会话补充（在 v1.2.171 释放契约之上）：就绪后新增主动「关闭摄像头」按钮（与翻转按钮同列），点击即执行同一停轨/关 Hands/解绑/复位并使焦点返回「开启摄像头」；连续 30 帧推理失败时显示「手部识别暂时失败」覆盖层，提供 [重试] 与 [改用上传照片试色]。
- 校准辅助线：`ArView` 的 `activeFinger` 指定当前手指，`showFitGuides` 默认关闭；开启后仅以珊瑚横线标记甲根。校准面板显示当前手指与已调整数量，长度、宽度及位置独立调节。
- 诊断信息降级：逐步摄像头日志（初始化与加载中面板）与 `NailArtPicker` 的总耗时/后台线程/模型版本统计、逐区「最近一次提取诊断」收进「技术详情」折叠区（`details/summary`，默认收起）；「导出诊断 JSON」入口一并折叠。

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

实时渲染性能契约（v1.2.447）：实时贴合帧率由 MediaPipe Hands 单帧推理主导——测试机 OPPO PA2373（Android 15、Edge 155、WebGL2）实测 `hands.send()` 单帧 47—50ms，与送帧分辨率（480×270—1280×720）和 `modelComplexity` 0/1 基本无关，主线程推理上限约 18.5fps；绘制侧曾在此基础上再扣约 20ms/帧。现行实现有五条约束：①环境光采样为整帧缩略一次读取（96×54 CPU 画布、320ms 时间窗），五指共享同一份像素后各自取邻域均值，避免逐指 `getImageData` 触发的 GL 同步回读；②带 alpha 轮廓的纹理走逐指合成层缓存，层内容只依赖纹理、甲面尺寸、光照与光泽，位移与旋转由画布变换承担，上屏按当前几何等比缩放以保证甲面大小始终跟随几何，相对尺寸变化 <15% 不重建；③层重建按单帧预算限量（最多 1 指/帧）并限最小间隔 100ms，把五指同帧重建的像素回读尖峰摊到后续帧，未重建的指继续用旧层缩放上屏；④层内亮度是烘焙结果，只在环境光亮度差 ≥0.12 时重建，静止画面不产生重建；⑤`handCnt`、`handLabel`、逐指可见性等 UI 状态仅在发生变化时写入 React 状态。复测方法为用整手照片合成 `MediaStream` 作为摄像头输入、按生产路径上传带 alpha 纹理并「应用到全部」，同一构图下纯色 18.3fps、五指纹理 17.9—18.4fps，绘制耗时均值 2—3ms、p90 9—11ms，两条路径都已贴住推理上限。突破该上限需把 Hands 移出主线程（Worker + OffscreenCanvas），当前未实施。

摄像头释放契约（2026-10-30，v1.2.171）：`ArView` 摄像头会话在以下三种情形一律停止全部 `MediaStream` 轨道、关闭 Hands 实例并解绑 `video.srcObject`——①组件卸载（应用内切换页面，`Link` 客户端导航即触发）；②启动失败（视频就绪超时/加载失败、hands.js 加载失败、`window.Hands` 缺失等，此前版本只切换错误界面不停流，已修复）；③页面进入隐藏态（切换标签页/应用、最小化窗口、`pagehide`）：自动复位到「开启摄像头」初始态并释放摄像头，返回页面后需重新点击开启。该契约与「摄像头画面仅在内存中处理」的隐私声明一致。

摄像头启动故障排查顺序：

1. 确认项目服务正在运行，并通过 `http://localhost:3000/ar-tryon` 或有效 HTTPS 地址访问；
2. 页面初始状态只能出现一个“开启摄像头”按钮；点击一次后应立即显示“请求摄像头权限…”及诊断步骤 `1/7`；
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
6. 点击推荐色跳转 `/editor?preset=<色名>`，预选最接近主色的纹理套装但不自动贴合（与 `?gallery=` 同时传入时 gallery 优先）。

数据边界：照片、候选与采样默认全部浏览器本地处理；v1.2.217 起甲面候选识别可由用户显式切换为云端辅助通道（一次性隐私确认后当前照片经 `/api/nail-detect-ark` 或 `/api/nail-matte-cloud` 上传、仅用于本次定位，见 §5.5），甲面定位之外的分析计算（比例派生/肤色采样/规则推荐）与结果渲染仍在浏览器本地完成；除该显式云端识别外不新增上传通道；即使开启「用户改进计划」，本功能分析结果也不进入上传通道；ImageBitmap/canvas/objectURL 在取消与卸载时释放。

核心组件接口：

```ts
function analyzeNailPersonalization(input: PersonalizationInput): PersonalizationResult
```

模块位于 `src/lib/nail-personalization/`：`types.ts`、`color-science.ts`（sRGB→Lab/ITA°分档/Monk ITA°近似/底调判定/ΔE76）、`skin-sampling.ts`（甲周椭圆环采样、甲面自污染排除、双条件质量门）、`hand-profile.ts`（手轴旋转归一化、重复甲面判据、四类手型）、`nail-health.ts`（均匀度/高光/条纹，复用 `isSpecularHighlightPixel`）、`rules.ts`（11 条甲型 + 15 条颜色规则、安全硬过滤、同组合取最高权重、组合分归一化）、`present.ts`（中文文案与提示去重）、`bridge.ts`（`?preset=` 出站）、`index.ts`（纯编排）。全部为无 DOM 依赖纯函数，Node 测试环境可直接运行。

前置条件：无新增环境变量；识别库直连方式同 `/device-benchmark`（本页自持一份精简编排，琥珀提示由 `present.ts` 统一提供，同步责任人=本功能维护者）。琥珀辅助定位边界同纹理识别：fallback 候选未经人工确认，不得表述为自动分析成功。

已知限制：手型为甲面派生近似比例（候选不含掌部 landmarks，未做掌宽/掌长口径）；肤色 ITA° 为非受控拍摄估计值，仅供色号筛选参考，**同一双手在不同光照下色系建议可能不同**（已实证：同色温照度每降约 10% 移一档、仅更换光源色温即可跨档），且深肤色在阴影下会被系统性压低、浅中性皮肤在 `|b*|` 接近 0 时分档会退化为由 b\* 符号决定；缓解为**弃权而非猜测**——`classifyItaBandStable()` 在低彩度（`|b*|<4`）或距分档边界不足 3° 时判 `itaReliable=false`，7 条肤色类颜色规则整体弃权、颜色回落场合/风格规则并在 UI 明示，`color-ita-deep-jewel` 另设采样质量门；项目**不做**亮度/曝光归一化（会摧毁 ITA° 测量的深浅信号）与整图白平衡（皮肤主导画面无可靠参考白）；Monk 仅按 ITA° 近似映射，项目不输出 Fitzpatrick；指甲健康为启发式观察，不构成医疗诊断，且当前无像素级 mask 通道恒不可用；`season` 仅为展示标签（四季色彩无同行评审效度验证）；规则表为 TS 常量，调整须同步黄金测试与规则覆盖 meta-test。

关联文档：`docs/nail-personalization-research.md`（资料汇编，含 §2.5 争议/失效证据与 §9 检索维护说明）、`docs/nail-personalization-design.md`（设计）。

### 4.7 消费者端独立设计预览

- **入口与范围**：`node scripts/serve-consumer-design.mjs`，浏览器访问 `http://127.0.0.1:4318`。消费者设计提案位于 `design/consumer-v1/`，不注册 Next.js 正式路由，不导入旧版样式。米白／深墨／珊瑚与五种甲型、工艺的手背贴图方向已获用户认可；继续遵循“设计不一定是加法”，未切换或部署。2026-10-22 起按新拟态（Neumorphism / Soft UI）规范完成品牌适配迭代：基底仍为品牌米白、强调色仍为珊瑚，交互面统一为双光源阴影语言；渐变背景、描边按钮与位移悬停已从原型移除（线框诊断态除外），适配范围与偏差登记见 `docs/consumer-redesign-design-brief.md` §8。
- **页面与流程**：为你／试戴／创作／我的，另含可跳过的轻问答、可编辑偏好模板、款式详情、收藏、发布与个人主页布局、美甲方案卡。说明收进可展开区域，保留必要标签与模拟状态；摄像头、语言模型总结、真正生成、个性化推荐、账号认证、跨设备同步和公开社区均未接入。
- **终端与动效**：按可用宽度和输入能力适配手机、平板、横屏与桌面，包含安全区、动态视口、触控目标、键盘焦点和输入时底部导航避让；保留浏览器缩放。短横屏压缩页头与重复引导，两张试戴卡以紧凑横向图形排列。标题使用 OFL 许可的本地 Noto Serif SC 衍生子集，正文用系统字体。路由、收藏、卡片和弹层使用短过渡，遵从 `prefers-reduced-motion`；缺少动画、观察器或 VisualViewport 时保留基本操作。中文合成输入不重建输入节点，返回恢复页面位置；原生 dialog 支持 Esc、焦点回返与背景滚动锁定。关闭只向原页面恢复焦点，跨页返回聚焦主体；已重新打开的弹层不被旧 close 事件解锁。新拟态适配后（2026-10-22）：可交互面以凸起／凹陷（inset）区分可点与已选／输入态；悬停为阴影缩小（遮光）、按压为凸起转凹陷且无位移，输入聚焦时内阴影深度减小（通道开放）；双光源方向全局锁定为左上亮／右下暗，阴影尺寸随断点缩放（移动端小、桌面端大）；墨底引用卡与 toast 保留柔和环境投影。2026-10-23 起按压反馈为 `.is-pressed` 140ms 下沉 `scale(.96)`＋释放 340ms 弹簧（`cubic-bezier(.34,1.56,.64,1)`）过冲后落位：缩放只做原地反馈，不产生平移、布局位移，阴影不参与形变。同日按 `docs/consumer-redesign-motion-plan.md` 落地 11 项交互动效——指针落点为原点的水波、成功档粒子爆散（轻档 9 粒／中档 13 粒，失败不爆散）、勾选逐笔绘制、开关滑块起步挤压＋磁吸回弹、液态滑杆 `--v` 单时间轴 400ms 同频、统计与滑杆数字 320ms 起强减速滚动、骨架与真实内容同格等量替换（高度差 ≤1px）、卡片 3D 翻面双面隐藏背面、汉堡单组线条形变、堆叠卡抽走与放回；`prefers-reduced-motion` 下关闭脚本水波／爆散／回弹，勾选完成与弹层显隐瞬时到位。本地浏览器验证见 `output/design-motion-verify.mjs`（93 项：11 项规格＋16 路由回归＋reduced-motion），截图 `output/design-review-shots/v11-motion-*.png`；真机验收边界不变。喜欢/收藏自 2026-10-23 起改为就地更新：点击只改被点控件（及同页可见计数），不重建页面或区块、不重设滚动、不发起任何数据请求；卡片图标钮与详情文字钮共用 `is-saved`/`is-liked`＋`aria-pressed` 选中态（珊瑚底/珊瑚字＋实心图标）、340ms 回弹脉冲与轻档爆散，成功与失败（本地存储不可用时回滚）各有明确文案；收藏页取消收藏只收起该卡并在清空后换空态。验证见 `output/design-reaction-verify.mjs`（49 项，含快速连点、取消再点、移动端与 reduced-motion），截图 `output/design-review-shots/v12-reaction-*.png`。同日完成同类交互的整页重渲染清理：关注只改关注按钮（`is-following`＋`aria-pressed`，与收藏共用选中态与 340ms 脉冲）与可见计数，标签切换只重排结果网格并同步选中态，灵感词只补写描述框文本（保留焦点与光标），换款只复位结果面板，上传只替换上传位与生成按钮文案，生成开始只把结果面板切到骨架；上述交互均不重建页面、不重设滚动、不发起请求。仅登录态切换、路由切换、诊断场景（错误/空态/重置）与骨架缺失兜底保留整页渲染。验证见 `output/design-local-update-verify.mjs`（37 项），截图 `output/design-review-shots/v13-*.png`。
- **数据与草稿隔离**：仅使用 `jiaru-consumer-design-v1` 保存文字偏好和互动选项；图片为本次会话内存对象 URL，刷新需重选。本人／他人照片分离且沿用账号审美；照片试戴／创作分别持有草稿、模拟生成状态与结果，方案返回对应编辑页。未保存的偏好改动与已保存档案分开；发布图、来源及授权选项在模拟登录后保留。未读写旧版账号、数据库或既有存储键。
- **方案导出与分享**：预先生成本地 PNG，用户点击后在支持文件分享的浏览器调用 `navigator.share`；不支持或分享失败时下载，用户取消不显示成功。仅声明已交给系统面板，不宣称送达；不分享本机预览地址。旧方案异步完成不能提前启用当前方案分享。原生分享尚待真机验证。
- **预览服务**：只绑定 `127.0.0.1`，默认4318，可用 `--port` 指定；仅白名单 GET／HEAD 提供原型、必要图片与本地 WOFF2，禁止写请求与任意工作区文件访问。CSP 禁止页面网络连接，摄像头等权限关闭；无需密钥或环境配置。
- **备份与恢复边界**：2026-10-20 实施前当前磁盘版本（包括未提交修改）已保存至本地 `.backup-consumer-20261020-v1/`，含源码、必要运行时资产、锁文件和配置模板；不含真实密钥／用户库／训练产物。逐文件恢复验真与四页开发服务访问已验证；恢复副本的生产构建尚未通过，不宣称完成生产恢复验收。机器记录见本地 `output/frontend-redesign/backup-verification.json`。2026-10-22 追加设计提案快照：当前磁盘版本（含 `design/consumer-v1/` 未提交改动与 `assets/` 下本地位图素材、字体，及 `scripts/serve-consumer-design.mjs`）保存至本地 `.backup-consumer-20261022-v1/design-snapshot/`，12 个文件、7,482,955 字节，逐文件 SHA-256 与字节同源一致（`manifest.json`、`verification.json` 随备份落盘；脚本见本地 `output/backup-consumer-design-2026-10-22.mjs`）；该快照只覆盖设计提案与预览入口，不含真实密钥、用户库与训练产物，恢复范围不含 Next.js 生产构建，亦不构成生产恢复验收。
- **验收边界**：最终 Chrome 核心75项与补充12项、独立Pixel 7触控模拟55项、Windows Edge补充24项检查通过；紧凑竖屏及短横屏入口完成完整截图复查。覆盖中文输入、异步状态、粗指针 tap、返回与弹层、减少动态效果、分享／编码／剪贴板失败恢复，绑定最终源码的记录见本地 `output/frontend-redesign-final-20261021/`。Android／iOS真机、iOS Safari／WebKit、真实系统键盘／安全区与原生分享仍未验收；模拟不代替真实服务或生产质量。旧审批服务额度故障已解除，历史失败保持。服务选型与正式切换仍待确认。完整设计、检查范围与恢复说明见 `docs/consumer-redesign-design-brief.md`。

### 4.8 正式站新设计系统（v1.2.158）

- **切换结论**：2026-10-27 起正式站启用 `design/consumer-v1/` 同一套新拟态（Neumorphism / Soft UI）品牌语言，**旧「玫瑰粉渐变 + 流动色块 + 毛玻璃」视觉废弃并从代码移除**——`AmbientMotion` 组件已删除，全部 `backdrop-blur` 与高不透明半透明白面板改为实心新拟态表面（仅摄像头深色叠加控件保留 `bg-white/5—/30`）。路由、HTTP 契约与组件业务 Props 均未变更。
- **品牌令牌**：`src/app/globals.css` 定义 `--paper #f7f4ee`、`--ink #292a27`、`--coral #ac5145`、`--coral-text #a34b3f`、`--coral-deep #884338`、`--coral-soft #f0e2db`、`--sage #e3e7dd`、`--line #deddd4` 与双光源 `--shadow-light #fffdf8` / `--shadow-dark #d3ccbd`；凸起 `--neu-out-*`、凹陷 `--neu-in-*` 随断点缩放。Tailwind `pink-*`／`rose-*`／`purple-*` 刻度经 `@theme` 重映射到品牌色，页面既有 class 无需改写即完成换肤；历史硬编码色值已批量映射到新令牌（旧玫瑰粉 → 珊瑚、旧灰紫文字 → 墨／中性灰），`rgba()` 粉色阴影改为墨／珊瑚阴影。
- **导航结构（v1.2.213 更新）**：`Header` 桌面为「JiaRu／nail atelier／甲如」锁定组合 + 中央 5 项胶囊导航「首页（`/`）／灵感（`/gallery`）／试戴（`/ar-tryon`、`/editor`）／创作（`/ai-generate`）／我的（`/account`、`/login`）」+ 右侧 2 个圆形图标按钮「上传试色（→`/editor`）」「灵感图库（→`/gallery`，命中时输出 `aria-current="page"` 并呈凹陷态）」。个性化分析不再占据导航位：`/nail-analysis` 由首页风格卡直达（§4.6）。`src/components/BottomNav.tsx` 移动端固定底栏同步为同构 5 项（首页 lightbulb／灵感 bookmark／试戴 hand／创作 sparkles／我的 user），按 `usePathname` 高亮并输出 `aria-current="page"`，输入法唤起时（`VisualViewport` 高度收缩 >140px）隐藏避让。`FlowingShell` 保留，但移除流动色块与毛玻璃，与 `AppShell` 共用品牌基底。
- **设计基元（新增接口）**：`src/components/ui/primitives.tsx` + `primitives.module.css` 提供 `Eyebrow`（珊瑚短线＋大写字距）、`PageHeading`（衬线标题＋可选珊瑚强调行＋描述＋右侧插槽）、`NeuCard`（`inset` 切换凸起/凹陷）、`SectionHead`（大写小标＋衬线标题＋右侧动作）、`Chip`。页面统一通过基元组装，不再各自堆叠圆角与阴影类。
- **产品内容色不受换肤影响**：默认甲油色 `#E8A0BF`（`src/app/editor/page.tsx` 的 `DEFAULT_NAIL_COLOR` 与其五指甲默认数组、`ArView` 的无选中色回退；`NailCanvas` 自 v1.2.173 起不含颜色逻辑）**保持原值不变**，`ColorPalette` 的色板数据未改动。换肤只替换 UI 强调色与表面色，不得改变用户实际看到的甲油颜色；`layout.tsx` 的 `body` 底色改为 `var(--paper)`／文字 `var(--ink)`。
- **字体资产**：`public/fonts/jiaru-editorial-serif.woff2` 为 OFL 许可（`public/fonts/OFL.txt`）的思源宋体（Noto Serif SC）可变字体改名子集「JiaRu Editorial」，wght 400–600，`@font-face` 用于标题与 eyebrow，`font-display: swap`。2026-10-31（v1.2.198）子集由 723 字符扩至 1,827 字符（旧子集 ∪ `src/**/*.{ts,tsx,css}` 全文 ∪ ASCII/常用标点，602,668 字节），修复 17 处标题含子集外汉字（如「肤/员/句/套/册/掌/基/优/追/踪/三/政/策/临/跑」与「—」）时逐字回退 SimSun 造成的字重不一致；2026-11-04（v1.2.253）随全站文案升级重建（写出 1,852 字符、610,584 字节），2026-11-05（v1.2.254）AR 标题微调后重建为现值 1,852 字符（610,472 字节）；重建工具 `scripts/build-editorial-font-subset.py`，文案新增字符后可重跑（日志「目标字符数」含无字形或未实例化的目标，现值以写出文件 cmap 计数为准）。
- **首页（v1.2.160 精简）**：5 个功能入口改由顶部导航与圆形图标承担，首页**移除 `START HERE` 入口网格**（原 5 张卡片及其 `EntryIcon`、`entries` 数据与 `.card*`/`.bentoGrid` 样式一并删除），保留编辑部式 Hero（eyebrow + 衬线大标题 + 双 CTA，其中「上传照片试色」直达 `/editor`）、风格卡（`/nail-analysis`）、`CURATED FOR YOU / 此刻心动` 与款式网格（`/gallery`、`/editor?gallery=`）及页脚全部链接（`/editor`、`/gallery`、`/ai-generate`、`/ar-tryon`、`/privacy`、`mailto:`）；能力边界说明保留为 Hero 下四项注释行（`AR 需摄像头与 HTTPS／AI 生成需联网／识别仅作辅助定位／照片默认留在本机`，Level 1 细分隔线、不浮起），不作为正式纹理识别能力承诺。
- **完整应用（v1.2.159）**：本轮不再只做配色替换，按 `design/consumer-v1` 的布局与组件结构重做正式站界面——首页改为「编辑部式 Hero（左文案＋右侧手部拼贴，含和纸胶带、竖排小字、图注）＋风格卡＋`CURATED FOR YOU / 此刻心动`＋搜索胶囊＋款式网格＋`START HERE` 入口网格」；图库改为无外框的款式网格（`LOOK 01` 标签、三枚操作胶囊；v1.2.162 起改为图标按钮，见下条）；全站卡片阴影统一为 `--neu-out-*`/`--neu-in-*` 双光源、移除卡片描边；旧渐变按钮、渐变图标底、径向渐变预览区与装饰渐变全部改为纯色面（仅保留语义色：成功绿、微信绿、默认甲油色 `#E8A0BF`）；清理换肤过程中产生的无效孤儿类名（`-2xl` 等 12 处）；其中 `START HERE` 入口网格已于 v1.2.160 移除（当前口径见上条）。
- **图库图形优先收口（v1.2.162）**：`/gallery` 页头移除描述段落与「共 N 款精选」说明胶囊（`AppShell` 的 `description` Prop 转为可选，其余页面不受影响）；主款式卡与收录卡操作改为 44px 图标按钮（试色＝调色板/珊瑚软底、AI 相似款＝星芒/鼠尾草底、AR 试戴＝相机/白底凸起），每钮携带含款式名的 `aria-label`；灵感网格密度 2/3/4 列，≥1100px 档经 `@theme` 命名令牌 `--breakpoint-wl: 68.75rem` 实现（Tailwind 4 任意变体 `min-[1100px]:` 层叠于命名断点之前导致失效，禁止使用，规则已登记 AGENTS.md）；首页图库入口胶囊改为图片图标＋「共 N 款精选」（现值：已改为「查看全部灵感款式」明链）。路由、HTTP API 与数据契约无变化。
- **资产**：新增 `public/nail-gallery/hero-hand.jpg`（1200×1499，JPEG q84，约 220KB），由 `design/consumer-v1/assets/hero-hand-collage-v2.png` 压缩导出。
- **共享交互基元（v1.2.213，frontend-interaction-redesign-plan §2.2）**：`src/components/ui/` 新增——`AppDialog`（portal 弹层：焦点陷阱走 `src/components/ui/dialog-focus.ts` 纯函数、滚动锁计数、`data-autofocus`、`initialFocus` "first"/"confirm"/"cancel"、Escape 关闭且关闭后焦点恢复触发元素）、`ConfirmDialog`（确认弹层，默认焦点 cancel，destructive 珊瑚样式）、`StatusRegion`（反馈区：loading/success→`role=status`+polite，error→`role=alert`，idle 不渲染；severity 仅影响配色；计时器类持续变化数值禁止放入该区域）、`UploadTrigger`（真实 `<button type="button">` + sr-only `<input type=file>` 兄弟结构：原生键盘/读屏语义、选择后重置 value 支持重复选同一文件、focus-within 珊瑚焦点环、凸起→按压凹陷、reduced-motion 降级）。配套纯逻辑 `src/lib/async-task.ts`（node 可测：单飞、取消不算失败、取消双条件判定 `signal.aborted`∧名 `AbortError` 防任务内部 AbortError 冒充、dispose 后 settle 冻结且迟到结果不外露、结算永不 reject）+ `src/lib/use-async-task.ts`（薄封装：runner 以 `useState` 惰性工厂创建、每实例独享，卸载 `dispose()`，StrictMode 重挂天然新实例）。
- **视觉系统收敛（v1.2.213，frontend-interaction-redesign-plan §8）**：①字号——主流程最小 12px，全站 `text-[9px]/[9.5px]/[10px]` 清零（ArView「技术详情」折叠区诊断日志等宽 11px 为唯一例外，非主流程非触控），触控按钮文字 ≥11px；②对比度——辅助文字灰 `#8a8b81/#75766c/#8b8c81/#b9bab1` 统一提升为 `#6f7066`/`#67685f`（对 `--paper` ≥4.5:1），摄像头深色覆盖层文字 `white/60`、`white/70` → `white/85`；③动效——全站 `transition-all` 类清零，替换为显式 `transition-[transform,background-color,border-color,box-shadow,color]`（只动画非布局属性），`globals.css` 追加全局 `prefers-reduced-motion` 兜底（冻结全部 transition/animation 时长、只保留终态），GalleryGrid 图片 hover 缩放降级为 opacity；④三级层级——隐私说明卡由「外凸大阴影 + hover 位移」降级为 Level 1「细边框、无阴影、不浮起」，可交互（Level 2 外凸）与输入/选中（Level 3 内凹+珊瑚描边）维持新拟态三级合同；⑤移动端缩放恢复——`layout.tsx` viewport 删除 `maximumScale=1` 与 `userScalable=false`，恢复 200% 缩放与系统字体放大（对应方案 §3 P0）。
- **验收**（v1.2.159 复跑，串行）：`lint` 0 problems、`typecheck` 0、`npm.cmd test` **1205/1205 pass、0 fail、0 skip**、`npm.cmd run build` **exit 0** 且路由清单完整（12 页面 + 15 API）；生产服务 `next start` 启动后 `/`、`/gallery`、`/editor`、`/ai-generate`、`/ar-tryon`、`/account`、`/nail-analysis`、`/privacy`、`/login` 全部 **200**；桌面 1280×900 与移动 390×844 截图核对（`output/shots/`）。视觉评审与真机验收仍未执行，不宣称已上线或已在真机通过。

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

**配额规则（v1.1.649，与 §5.2 共用 `src/lib/ai-quota.ts`）**：请求在参数校验后、外部调用前经 `requireUser` 识别身份并同步预留额度——登录用户每日 20 次、游客每日 5 次、全局每日 200 次预算熔断、全局并发 3 且同一身份同时仅 1 个任务；外部调用成功后 `commit` 确认消耗，失败时 `release` 返还该身份当日次数但全局日计数保留（防刻意失败刷预算）。超限返回 429、中文错误与 `Retry-After`。配额为进程内存态，适配当前 Windows 单实例 `next start` 部署，重启清零；多实例共享与持久化消费台账未实现。

**配额环境变量（v1.2.157 修订）**：限额由 `AI_QUOTA_GUEST_DAILY`/`AI_QUOTA_USER_DAILY`/`AI_QUOTA_GLOBAL_DAILY`/`AI_QUOTA_GLOBAL_CONCURRENCY` 调整，非法值与负数回退默认；三条"次数上限"自 v1.2.157 起接受 **0＝关闭该通道**（游客／登录用户／全局各自独立，关闭游客不影响已登录用户），`AI_QUOTA_GLOBAL_CONCURRENCY` 仍要求 ≥1、0 视为非法（0 并发无恢复路径）。此项为 2026-09-23 安全审计 M5 的遗留项：旧实现把 `parsed < 1` 一律回退，导致 `AI_QUOTA_GUEST_DAILY=0` 无法生效、运营不能按审计建议关停匿名付费接口。旧值＝`0` 回退为默认 5；新值＝`0` 关闭。

**游客身份键（安全审计 M5 修复口径）**：不再无条件采信 `x-forwarded-for` 首段——仅当显式设置 `JIARU_TRUST_PROXY=1`（由 Nginx 覆盖 XFF 并注入 `X-Real-IP: $remote_addr`）时才采信代理头，否则一律归为 `guest:<hash("unknown")>` 共享额度（宁紧勿松）。与 `src/lib/rate-limit.ts`、`src/lib/auth/cookies.ts` 共用同一 `resolveClientIp` 判定。

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

### 5.3 `GET/PATCH /api/me`（个人档案）

状态：已实现（本地 SQLite 账户原型口径，见 §3「用户账户」行）。`/account` 个人资料卡片使用本接口；服务端校验与前端实时校验共用 `src/lib/profile/profile.ts`。

GET 响应：`{"user":{user,identities,consent}}`，`user` 字段为 `id/phone/email/nickname/avatar/bio/contact/contactType/ageGroup/status/createdAt`；旧库迁移后 `bio`/`contact`/`contactType` 为 `null`。

PATCH 请求体（字段均可选，只写本次提交的字段；未提交字段保持原值）：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `nickname` | string | 去首尾空格后 1–30 字符（按码点计），禁止换行/控制字符 |
| `bio` | string | 去首尾空格后 ≤120 字符；空串清空（存 `null`） |
| `contact` | string | ≤40 字符；非空时必须符合所选类型；空串清空 |
| `contactType` | `wechat`\|`email`\|`phone`\|`other`\|`null` | 未知值返回 400；与 `contact` 成对写入，无联系方式时两者同存 `null` |
| `avatar` | string\|null | PNG/JPEG/WebP data URL（`/account` 端压缩为 256×256 JPEG），解码后 ≤300KB 且文件签名须与 MIME 一致；`null` 移除头像；`https://…` 等非 data URL 返回 400 |
| `ageGroup` | string\|null | 既有字段，未新增约束 |

联系方式校验：`wechat` 为 `wxid_…` 或以字母开头的 6–20 位字母/数字/下划线/减号；`email` 为常规邮箱格式；`phone` 归一去掉空格、连字符与 `+86` 前缀后须为 11 位大陆手机号；`other` 至少 2 字符且无控制字符。任一字段校验失败返回 400 `{"error":"<字段级中文原因>"}` 且不写库；成功返回更新后的 `{"user":{user,identities,consent}}`，并以 `audit_logs` 记录 `update_profile` 的变更字段名（不含字段值）。

`/account` 交互口径：查看态展示头像/昵称/简介/联系方式，空字段给出补充入口；编辑态支持头像上传与移除、字段实时校验、保存与取消（存在未保存修改时需确认），保存成功/失败在卡片内分别以 `role=status`/`role=alert` 反馈；读取中显示骨架卡片，读取失败与未登录分开呈现且失败可原地重试。头像以 data URL 存入 `users.avatar`；`bio`/`contact`/`contact_type` 由 `createUserDb` 对旧库自动补列。仍为账户原型：未接入对象存储、头像内容审核与跨设备同步。

### 5.4 `GET/POST /api/nail-matte`（本机精细抠图）

v1.2.257新增服务端选择的`backend`字段供前端区分整图候选识别与原WeVis精修；无令牌或权重路径回传。共享面板支持原地重新探测（GET，无图片），确认本机处理后直接执行本次识别。

状态：已实现（v1.2.165）；路由级端到端 5/5、UI 端到端 2026-10-28 为 3/5、2026-10-29 同图复测 5/5（UI 已验证联通）；2026-10-29（v1.2.167）起 UI 自动流程在已记住隐私确认时自动调用本路由（每次选择器打开至多一次，`output/nail-auto-profile-v167/` 实测上传→上屏 15.1s、零页面错误），路由行为与限流不变；不改变正式识别 PRODUCT HOLD。

v1.2.255新增本机自研候选配置：服务端`NAIL_CANDIDATE_URL`+`NAIL_CANDIDATE_TOKEN`优先于原WeVis配置，URL仅允许HTTP/127.0.0.1且无路径、查询和用户凭据，独立令牌至少32字符；未配置候选URL时沿用原配置。通用入口`model/training/serve-nail-candidate.py`提供鉴权`/health`和`/matte`，加载SHA核验的Stage A与原尺寸几何精修权重，单请求串行、最多900万像素、图片仅内存处理，返回二值PNG mask。当前模型整图识别，文字和提示框不参与推理；前端候选匹配和复核保持。移除两项配置并重启业务服务可回退。当前本机实例已启用，见[业务候选说明](nail-texture-business-candidate.md)。

配置：`VLM_MATTE_URL`（如 `http://127.0.0.1:8008`）+ `VLM_MATTE_TOKEN`，仅服务端读取。未配置 URL 时 `GET` 返回 `{"enabled":false}` 且前端整块不渲染；已配置但上游不可达返回 `enabled:true, ready:false`。

`GET` 响应：`{"enabled":boolean,"ready":boolean,"busy":boolean,"backend"?:"candidate"|"wevis"}`，只读上游 `/health`，不触发推理。

`POST` 请求（**仅这四个字段**，其余忽略）：

```http
POST /api/nail-matte
Content-Type: application/json

{"image":"data:image/jpeg;base64,...","task":"matting","query":"nails"}
```

| 字段 | 约束 |
| --- | --- |
| `image` | 必填，`data:image/(png\|jpeg\|jpg\|webp);base64,` 前缀；请求体 ≤8MB，`content-length` 超限在解析前返回 413 |
| `task` | 可选，`matting`/`segmentation`/`visual_prompt`，默认 `matting` |
| `query` | 可选，≤32 字符，默认「nails」（2026-10-31 v1.2.177 起定版，实测召回/耗时最优；此前「指甲」） |
| `boxes` | 可选，≤10 组 `[x1,y1,x2,y2]` 且 `x1<x2`、`y1<y2`；仅 `visual_prompt` 允许（refine 路径已不使用） |

上游输入预算默认 262144 像素（`matting.py` 的 `DEFAULT_MAX_PIXELS`，`server.py --max-pixels` 同源；2026-10-29（v1.2.166）起，此前为 589824）。2026-10-28 参数实测：589824 在 7 张高对比业务图（含双手 9 甲）按 `<OBJ>` 逐甲返回、单图 11.8–18.7s；1048576 档对 `hero-hand.jpg` 只解出 1 个 `<OBJ>`（响应文本含 5 个框），故不得作为默认；`visual_prompt` 在本权重下对同一原图恒定返回 0 实例，refine 统一使用 `matting`。2026-10-29 真实照片评估（36 图、203 枚完整甲人工真值）证伪了「分辨率影响有限」在真实照片上的外推：档位显著改变实例召回——589824 档 0.8325、262144 档 0.9803（单图 16.2s→9.0s）、1310720 档劣化，故默认改为 262144；mask 几何代价与 query/量化实验结论见 §3 本机精细抠图行。UI 端到端（`/ar-tryon` 多纹理上传，2026-10-28）实测服务返回 5 实例/14.3s，面板替换 3/5；未匹配两例的服务实例框与本地候选框仅部分重叠（IoU 0.075/0.049），属本地候选几何偏移，不是实例召回不足，按规则保留本地 mask。2026-10-29（v1.2.165）修复：客户端匹配前把候选外接框按编码几何（`computeMatteEncodeGeometry`）换算到编码空间再比对——此前原图长边 >1600 时候选框（原图坐标）与实例框（编码坐标）不同域，IoU 与中心归属恒不成立，精细替换会静默不生效；掩膜回映射原图口径不变。

成功响应：`{width, height, instances[], omittedInstances, model, quant, elapsedMs}`；`instances[]` 只保留 `index/box/bbox/area/alphaPng/width/height`，`alphaPng` 必须是 `data:image/png;base64,`（其他形式丢弃），超过 10 个实例截断并在 `omittedInstances` 显式计数。上游的 VLM 文本 `response` 与 `metrics` **不回传**。

错误映射：未配置→503 `disabled`；上游忙→503 `busy`（带 `retryAfterSeconds` 与 `Retry-After`）；超时→504 `timeout`；上游鉴权失败→503 `auth_misconfigured`；上游 5xx/不可达→502 `upstream_error`；图片不合法→400；超过 8MB→413；超过每身份额度（默认 3 次/10 分钟，`JIARU_RL_NAIL_MATTE` 可覆盖）→429 `rate_limited`。降级响应统一形如 `{"degraded":true,"reason":"...","error":"..."}`，正文不含 token 与上游堆栈。

安全约束：转发层按白名单重建请求体，**不读取也不透传 `imagePath`**（上游该分支可直接打开本机文件）；上游 token 只在服务端环境变量；服务只应绑定回环地址；本路由不得进入实时 AR 帧链路。

### 5.5 `GET/POST /api/nail-detect-ark` 与 `GET/POST /api/nail-matte-cloud`（云端识别，v1.2.217）

云端识别模式（v1.2.217，2026-11-03 用户指示）为三个识别站点（编辑器/AR 选择器/个性化分析）提供「本地 | 云端」切换的云端侧：**用户显式选择 + 一次性隐私确认**（`jiaru.nail-detect-cloud-consent.v1`，`NailDetectModeSwitch` 内置 AppDialog 说明）后图片才离开本机；候选一律固定 `confidence:"low"` + `warnings:["needs_review"]`（source `"cloud-ark"`/`"cloud-matte"`，§6.1），仅作辅助定位，不计入正式识别成功率，PRODUCT HOLD 不变。模式为会话级（不持久化，默认本地）；本地路径行为不变。

- **方舟视觉后端 `src/lib/nail-detect-ark-api.ts` + `/api/nail-detect-ark`**：配置 `ARK_VISION_MODEL`（必填，含版本后缀）+ 复用 `VOLCENGINE_ARK_API_KEY`/`ARK_BASE_URL`（HTTPS 强制，校验同 Seedream 客户端）；未配置时 GET `{enabled:false}` 且前端云端选项禁用。POST 请求体白名单 `{image: DataURI(PNG/JPEG/WebP), width, height}`（浏览器经 `encodeImageForMatte` 同源链路编码至长边 ≤1600，width/height 为编码图坐标域）、8MB 上限、身份+限流（桶 `nailDetectArk`，`JIARU_RL_NAIL_DETECT_ARK`，默认 3 次/10 分钟）；服务端以 chat/completions 调视觉模型（temperature 0、max_tokens 1000、超时 120s、429/500/503 指数退避），解析 `{"nails":[{"box":[x1,y1,x2,y2]}]}` 像素框（剥围栏、逐框形状校验、上限 10），响应 `{ok:true, boxes, model, elapsedMs}`；坐标→原图映射在浏览器 `src/lib/nail-cloud-detect.ts`（与 matte 同一编码几何换算、钳制、<8px 剔噪、IoU>0.9 去重、矩形 mask 兜底）。401/403→503 `auth_misconfigured`、429→`rate_limited`（Retry-After）、超时→504 `timeout`、上游 5xx→502 `upstream`；错误正文脱敏（不含密钥/堆栈）。真实端到端需方舟账号实际开通所选视觉模型（路由层逻辑由 mock 测试覆盖，真实调用待用户配置 `ARK_VISION_MODEL` 后实测，同 Seedream 接入先例）。
- **云端自托管 matte 后端 `/api/nail-matte-cloud`**：与 `/api/nail-matte` 契约完全同构（白名单四字段、8MB、实例上限 10、降级响应格式、`imagePath` 不可达），仅转发目标与限流桶不同——转发 `NAIL_CLOUD_MATTE_URL`（须自行部署与运维、与本地 WeVisOne-VL 同 `/matte` 契约）+ `NAIL_CLOUD_MATTE_TOKEN`，限流桶 `nailMatteCloud`（`JIARU_RL_NAIL_MATTE_CLOUD`，默认 3 次/10 分钟）。GET 探测 `{enabled, ready, busy}`（上游 /health，不触发推理）。转发封装在 `src/lib/nail-matte-api.ts` 参数化（`resolveNailMatteConfig(target)`，本地默认行为逐字节不变，既有路由测试回归保护）。
- **共享判决与文案**：`src/lib/nail-detect-mode.ts`（node 可测）提供模式/后端类型、`decideNailDetectRun`（local 恒可运行；cloud 需后端可用+已确认，未确认→弹确认，不可用→分类提示）、`classifyNailDetectError`+`NAIL_DETECT_ERROR_MESSAGES`（八类脱敏文案）；`src/lib/nail-cloud-detect.ts` 提供两条云端识别的浏览器封装（`detectNailsWithArk`/`detectNailsWithCloudMatte`，后者完整复用 `detectNailsWithMatte` 换算、仅替换端点与来源标注）与候选映射；三站接线为 `NailDetectModeSwitch`（共享切换组件）+ `useNailDetectMode`（hook）。

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
  source: "model" | "mediapipe" | "partial-closeup" | "saliency" | "manual" | "vlm-matte" | "cloud-ark" | "cloud-matte";
  mask?: NailMask;
  warnings?: string[];
  suggestedFinger: number | null;
}

interface NailMask {
  width: number;
  height: number;
  data: Uint8Array;          // 二值几何，非零即前景
  originX: number;           // 恒 0（整图栅格）
  originY: number;
  scale: number;             // max(原图宽/mask 宽, 原图高/mask 高)
  alpha?: Uint8ClampedArray; // 可选软边 0..255，仅 vlm-matte 来源提供
  coverageAlpha?: Uint8ClampedArray; // 独立产品覆盖率，原始data保持
}
```

`mask.alpha` 为 v1.2.163 新增的可选字段：`buildFeatheredAlphaMask()` 在存在且长度等于 `width*height` 时取 `min(软边, 羽化斜坡)`，即软边只能收紧边缘、不能扩张二值几何；未提供或长度不符时完全沿用原逻辑，既有调用方零改动。`source: "vlm-matte"` 由本机精细抠图（§5.4）产生，固定 `confidence: "low"`，界面显示「本机精细抠图」并要求人工复核。v1.2.217 起新增 `source: "cloud-ark"`（方舟视觉识别，轴对齐框 + 矩形 mask）与 `source: "cloud-matte"`（云端自托管 matte），同属云端识别模式（§5.5）：固定 `confidence: "low"` + `warnings:["needs_review"]`，仅作辅助定位，须经人工复核，不计入正式识别成功率。

### 6.2 运行策略

1. 直接调用 `recognizeNailTextures()` 时只有显式传入 `preferModel: true` 才加载模型，否则直接使用 fallback；`recognizeNailTexturesInWorker()` 默认将 `preferModel` 设为 `true`；
2. 后端按 manifest `backendPreferences` 选择；当前生产发布声明仅 `wasm`（发布对拍在 WASM EP 完成，WebGPU EP 数值未经验证不启用），WebGPU 硬件加速待另次数值验证后再评估；
3. 模型加载、推理、Worker 或后处理失败时底层返回 fallback 结果和 warning；规则候选只供诊断，必须标为低置信度；
4. 正式UI检测到`backend: "fallback"`时隐藏规则候选、保留原候选到debug导出，再调用`detectNailsFromHandImage()`尝试完整手部几何定位；
5. 手部几何定位成功时生成`source: "mediapipe"`候选并按五指索引自动分配；无完整手部或无可靠几何时，再调用`detectPartialCloseupNails()`尝试局部近景定位；兼容入口`detectPartialCloseupNailCandidates()`仍只返回候选数组；
6. 局部近景先运行甲色路径：以小核开/闭运算处理非皮肤且未过曝连通域，并通过面积、形状、方差、触边、手部支持域、原始肤色环和局部RGB距离复合门；同手空间簇有2—5枚时直接返回。甲色路径不足2枚时才运行低对比边界路径：固定5×5平滑与Sobel梯度，两档边缘阈值经5×5闭运算后提取不接触图像边界的内部区域；候选必须同时通过面积/长短轴/长宽比/填充率、内部及邻环肤色、手部支持、内部非暗且平滑、边界梯度，并跨阈值去重。只有单一4—5枚候选以最长边21%相邻距离形成连续链时才返回，否则整条边界路径为空。两路五候选均按手部支持域中心极角弧排序；甲色路径4—5个为`medium`、2—3个为`low`，低对比路径固定为`low`并带`partial_closeup_low_contrast_boundary`复核warning；全部为`source: "partial-closeup"`；
7. 模型候选经过置信度评估、角度稳定、手指建议和mask纹理提取；MediaPipe、局部近景与人工候选使用透明椭圆裁剪；
8. UI必须展示真正影响当前候选的低置信度与提取质量告警，并允许用户点击新增、拖动/按钮调整、重新分配、删除或取消。所有`backend: "fallback"`均持续显示辅助定位及逐个人工确认边界提示，不因局部近景或候选数≥4显示“可直接提取”；零候选提示手工添加。技术warning可保留诊断摘要和导出，但不得隐藏明确降级状态；`model_not_deployed`显示生产模型尚未部署。

当前独立非零控制中，三尺度Chrome WASM共享特征与冻结WebGPU框、原型配合CPU ORT完整分类支路，可恢复原候选顺序及粗遮罩，并满足两头1e-4。已接回全部原WASM激活，三种浏览器卷积原型仍未通过原候选顺序门，结项。实际图像与完整设备链维持现行验收。见[完整分类参考](../model/reports/ar-stage-a-class-complete-v1/replay.json)和[原激活交叉](../model/reports/ar-stage-a-browser-class-original-activations-v1/replay.json)。

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

默认生产manifest自v1.2.258起为已发布的浏览器业务模型`nail-texture-seg-geometry64-browser-aa4-v2`（`deploymentStatus: "deployed"`，Stage A 512输入+Stage B radial-refine双ONNX，契约见§7）；运行时正常加载时自动流程走模型路径，`model_not_deployed`等降级提示仅在manifest回滚为`not-deployed`或模型故障时出现（提示映射保留为防御口径）。发布登记与切换经`scripts/register-model-release.ts`/`switch-model-release.ts`写入`public/models/nail-texture-seg/release-registry.json`；ONNX文件由`.gitignore`保持本地，manifest与registry快照入库。历史候选及未获发布资格的权重禁止用其补齐默认目录或共享环境变量。当前正式模型状态以§3/§11.1与Goal为准。

双分辨率隔离构建使用800像素图运行Stage A，页面逐ROI读取原图像素供Worker的Stage B，返回带原图坐标的局部mask及4×4覆盖率。100张开发图实测均走WASM，634甲一一匹配，原图2px严格0/634，平均Boundary IoU 0.316。定义不同的冻结原图纹理链与正式几何参考的均值分别为0.338和0.725；正式参考原已过门248枚全部丢失。实测ROI完整容纳634甲真值，在距实测轮廓4/8/16px内替换为真值的诊断可达564/624/632。同ROI搬运完整五折侧缘轮廓严格397/634，保留正式原通过248甲，最大回退0.02845；限制在实测轮廓8px带内则为377/634，丢4枚原通过甲。正式和侧缘轮廓分歧像素按真值选择可达612/634；以新增连通域或孔洞触发整甲回退并用真值逐甲择优，仅达500/634。固定搬运开发路线结项。原图16px边带的局部补去真值控制逐甲保留前景连通域和孔洞数量，严格629/634，保住原通过248甲，所有几何及同配方alpha继续门通过。实测630甲有孔洞，单次径向交叉与严格等拓扑约束组合仅通过4甲并结项。仅形状与加原图Lab/梯度的五折离线对照均严格0/634，独立连通域清理也未提高严格通过数。全100图634甲的Stage B原始半径已绑定现行中心、角桶和presence。其中631甲与历史上传栅格逐字节一致，另3甲由原上传构建Worker复采重现并保留对历史栅格的差异。仅换真值辅助半径的原图2px严格为634/634，平均Boundary IoU 0.99977，保留原正式参考248甲，最小单甲增益0.11130。只计631甲的同范围敏感性结论一致。固定实测半径的连续角度解码已在六图结项。首折直接续训预检出现CUDA与浏览器半径数值及硬遮罩差异。以冻结浏览器半径和presence为共同输入的两臂残差训练仍为0/115，区间损失较同配方单值对照的平均Boundary IoU变化为−0.00065，且纹理覆盖率联合门失败，该配方结项。首折115甲配对的粗遮罩平均IoU为0.98017，只有8甲ROI四元组一致。现行浏览器输入上使用冻结第90次Stage B权重做CUDA诊断，平均Boundary IoU从0.33033升至0.51467，113甲改善，presence零新增拒绝，严格仍为0/115，直接替换路线结项。相同权重的冻结本机严格参考为57/115，组合侧缘及两端头为98/115（§8.9）。首折同权重交叉对照中，完整本机粗轮廓与径向几何投影至浏览器ROI后恢复原57/115，均值0.73773。只换RGB或中心仍为0/115。相同Stage A浏览器原始头使用两种解码器的粗遮罩平均IoU为0.99845，两条运行链的原始头改用同一原图解码器后为0.98221。首折20张JPEG原图直达512使115甲粗遮罩与本机参考的平均IoU从0.98224升至0.99901，冻结第90次Stage B的CUDA对照严格9/115。同一OpenCV张量运行Chrome WASM时粗遮罩114/115逐像素一致，Stage B严格56/115。余下1甲的原始遮罩logit变号与过门丢失由同ROI单像素交叉复现。现行 TypeScript 缩放在同 OpenCV RGB 上20/20张量逐字节一致，Chrome隔离页用固定MozJPEG解码路径的整图RGBA及512张量对20张JPEG均与OpenCV逐字节一致。Stage A同输入的单像素翻转仍出现在四档WASM图优化；冻结头交叉仅用本机原型可重现115甲粗遮罩全等。保真插桩支持最后原型卷积最大误差主要由其输入传播，同后端后段正控覆盖六个切点，换入原型分支前的本机共享特征可恢复157.jpg目标像素及该图候选粗遮罩。显式BatchNorm导出仍漏同一像素，且检测头超过1e-4。157.jpg三尺度原头后段在同后端逐字节重放。换本机P3即可恢复该图4枚候选的全部粗遮罩，并消除P3框坐标越界。换入全部三尺度后，检测头892项越界降至21项，剩余全为P5框坐标，最大0.00030518，未过原1e-4。同P5输入替换为本机DFL前logits后，21项剩余超差归零，检测框最大差9.15527e−5，保留4个候选身份及零遮罩差。同输入替换DFL距离后框坐标逐值一致。P5框回归三种float64卷积累加数学对照接真实Chrome DFL，剩余14/12/12项越界，仍保留候选与零遮罩差，均已结项。在同CUDA三尺度输入上，P5两个卷积与两次SiLU的四接缝同后端均逐字节重放。第一个卷积/SiLU换入本机值后分别余2/4项超差，第二个卷积或SiLU换入后均归零，保留4候选及零遮罩差。相同第一块SiLU输入仍产生第二块卷积/BN差异，两块同时改为显式BN或单次舍入仿射的Chrome WASM对照分别余17/14项，固定同SiLU1只改第二块余1/2项；换入相同CUDA BN前输出仍余2/1项，候选数与粗遮罩均保持。两种表达结项。Chrome WebGPU以原拓扑的独立非零对照验证103/103关键算子实际GPU执行；原型头通过，检测头3个P5框高度的最大绝对差为1.22070e−4，浏览器JS DFL使用原图GPU前缀，以64位归约后继续原32位坐标顺序，消除3项超差。候选身份的差异可由原分类分数交叉独立复现，在同一非零对照上联合门仍未过。原CPU Sigmoid处理同GPU logits仅余26项分数差，Chrome WASM独立分类仍余23项，均改变候选；固定Sigmoid替代及WASM分类路线已结项。真实首折20图115甲使用同一OpenCV输入时，Chrome WASM候选身份和顺序与CUDA一致，换分数或框均保留原型单像素差和Stage B严格56/115；换入CUDA原型使115甲粗遮罩全等。Chrome原图直达512组换分数恢复4张图的候选顺序，严格仍为9/115；换框使遮罩差异像素4,482降至3,396，26甲后段输入改变待判。同输入框的原两头数值检测在20张图均超1e-4，覆盖P3/P4/P5，最大0.00149536。整折存档仅保留双头，157.jpg的三尺度冻结轨迹显示，在本机特征交叉后，主机宽精度DFL仍有19至22项框超1e-4，换入本机DFL前logits则全过，并保留原候选及遮罩。同输入四处接缝继承完整两头和原坐标舍入时，结合宽精度DFL，第一块卷积或SiLU交叉仍余2项超限；第二块卷积和SiLU交叉均归零，保留四候选及零遮罩差。加宽坐标使第二块卷积交叉重新超限1项。独立非零样本上，固定相同第二块输入时，WebGPU卷积和P5 logits最大差5.96e−8及2.98e−8。完整WebGPU图的观测插桩改动检测头55项，其中1项超1e-4，原型逐字节一致。分块重放 `model/reports/ar-stage-a-p5-webgpu-block-isolated-v1/replay.json`（SHA-256 `0d34d84220a876728bf07d93a2cfb96652cb671ecc5e0ed9074e1f3f7d96de79`）。完整两头重建后，固定CPU上下文交叉WebGPU/WASM分块，两个臂均保住10个候选的原身份、顺序和全部粗遮罩。保留真实WebGPU上下文时，任一分块的最大检测差为9.15527e−5，仍有8/10候选身份不一致。结束只替换P5框回归的路线。固定相同WASM分类logits时，CPU和Chrome WASM的原Sigmoid逐字节一致，并复现原WASM分支结果。将CPU分类logits交给同一Chrome WASM算子后，5376个分数全部恢复，固定WebGPU其余头时10候选原身份和全部粗遮罩也恢复。WASM上游的残差覆盖P3/P4/P5，23个最终分数差分别为12/3/8，转查分类卷积及共享输入。重放 `model/reports/ar-stage-a-wasm-sigmoid-crossover-v1/replay.json`（SHA-256 `d148fac7cbee3dd76b625580c904fe95064ddd2be7050603f01f64cf28899186`）。重放 `model/reports/ar-stage-a-p5-isolated-head-transfer-v1/replay.json`（SHA-256 `d3f63b81de20704e270dfcfd1249269e4e30a85fe3ea2e19bc7a8e8f14fa57ed`）。见 `model/reports/ar-stage-a-p5-seams-wide-dfl-v1/replay.json`（SHA-256 `889844b88854c26d3c27f4236ea43cf1deb2f6d6a5809df9d06bf88bbac42692`）。见 `model/reports/ar-stage-a-real-wide-dfl-v2/replay.json`（SHA-256 `945747e5110035cf3865708f678f0d950a936280312965d70d0efc8170f813f8`）。见 `model/reports/ar-stage-a-real-score-box-cross-v1/replay.json`（SHA-256 `cfd793ea1030601dcf15afb5b2a8ba1c9fcca7370a41d87dafb379c3b595ae16`）与 `model/reports/ar-stage-a-real-score-box-cross-v1/raw-axes-replay-v1.json`（SHA-256 `cedaa52c6649140c4d398ca617dc04ebf20607125a1d694cc3ae5466a7c25e49`）。分类交叉 `model/reports/ar-stage-a-webgpu-sigmoid-v1/report.json`（SHA-256 `dcbfe214f0ae528c8d6dc9a5e4d08bb7267975609324c1524c18c8ab99c30e56`）。候选归因 `model/reports/ar-stage-a-webgpu-host-dfl-v2/identity-attribution-v1.json`（SHA-256 `8b0ee715626e40c2a951d1949585809bcc4329d180c4383c30e340e94c6359e8`）。设备落点 `model/reports/ar-stage-a-webgpu-control-v3/placement-audit-v1.json`（SHA-256 `92f762574bd833590f54c2c318f47237e97626eec0db92f6532252cff39455d1`）。BN后段交叉 `model/reports/ar-stage-a-p5-prebn-cross-v1/report.json`（SHA-256 `e071e8dcc2c8bed710c14d7041a088e2de12f9d6f54abb1087bc7ebcc06ab4f1`）。接缝交叉 `model/reports/ar-stage-a-p5-seams-v2/report.json`（SHA-256 `fb0166d34e270641d7e395e212cc1637fddb785332aca8aef3bd4c0dd4ac5ce2`）。累加对照 `model/reports/ar-stage-a-p5-wide-accumulate-v1/report.json`（SHA-256 `905534299350b8548351464e257f8ff756a99eb47448cf53c7d8a64fa47d962c`）。归因 `model/reports/ar-stage-a-p5-dfl-v2/report.json`（SHA-256 `c49edd7d86f94479247c9089b3cd98a5570ff880123d6fa4958fc79f5b06c4cc`）。三尺度交叉 `model/reports/ar-stage-a-shared-scales-tail-v1/report.json`（SHA-256 `d82ef5c72b5d1e3846a77c055b73bec30f3b5bb373b2a7191cdb4eb93aca3256`）。入口交叉 `model/reports/ar-stage-a-prototype-entry-tail-v1/report.json`（SHA-256 `19b3297be7721c74b0839ae9681ce7853aa3778a404a74ab354bc34bf4ad8850`）。解码报告 `model/reports/ar-stage-a-mozjpeg-local-v2/report.json`（SHA-256 `75702d9ada5dd4b0327e9c27be9c2d729dba19b430affa48eaff1b20eda438e2`）。原型追踪 `model/reports/ar-stage-a-prototype-trace-v1/report.json`（SHA-256 `74a8e056d592d1dd1d49f64f373fcf55167b24e45288891b5a490494f9337b20`）。评分 `model/reports/ar-stage-b-from-direct-stage-a-v1/report.json`（SHA-256 `a14eda11741e0fc8caf5b8c15361edc813546ebf4a04b116fae2e8007e5bb65d`）。交叉报告 `model/reports/ar-browser-stage-b-spatial-crossover-v1/report.json`（SHA-256 `2f22121ef7a4967275dd01b51038ec78266844eeed21fe96b5813ce0d0ce2adb`）。逐甲换权重报告 `model/reports/ar-browser-neighborhood-stage-b-v3/report.json`（SHA-256 `f97d505136d84611df17538fa9f6421a405f2d7060de20ee1fda6dc82386b237`）。归因报告 `model/reports/ar-browser-radius-cohort-score-v1/report.json`（SHA-256 `7caf7a57dd646d55c50c2eb117ddd2374b3b6816929d982303bc43fdc0e338f9`）。原图信号报告 `model/reports/ar-browser-rgb-signal-v1/report.json`（SHA-256 `ac95d8202847894ae157463300eb0369e05a694ec1dbf8e259ce6696d9e5d800`）。可达性报告 `model/reports/ar-browser-topology-reach-v1/report.json`（SHA-256 `0fc39baec84cd476bc939d8536e005b4317cdb604ee91a3cd8738c1dbfcc577f`）。迁移报告 `model/reports/ar-browser-contour-transfer-v3/report.json`（SHA-256 `504d318139d043a784ca6dd1e665f358f2d9ffe41675fff8ff86b9f30f51087f`）。94张可计时样本上传至复核或自动应用P95为4.87秒，Chrome相关进程采样工作集之和最大1.31 GB。评分 `model/reports/ar-dual-resolution-development-v2/quality.json`（SHA-256 `ccb22a5188cf23a7f89eef7b251e18666c0895dc52fe195fb8a3077e4006a977`）。

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

v1.2.259归一化新增`referenceIsDirected`（缺省true，兼容已有调用）：选择器对模型轮廓轴向传false；明显收尖的长甲可通过两端宽度剖面补全甲尖方向（`mask+taper`），对称/方向证据弱时提示复核并降低自动应用置信度。手部关键点及人工明确方向继续传true；人工180°翻转从当前有效方向计算，应用页也支持直接翻转和撤销。`ar-texture-fit.ts`提供完整alpha内容框/甲床宽度测量、连续绘制矩形与半周旋转；按ImageBitmap缓存测量结果，渲染帧内复用。证据见`model/reviews/ar-fit-cuticle-v1/`与当日日志。

```ts
extractTexture(imageUrl, { x, y, w, h }): Promise<ImageBitmap>
clampTextureSize(bitmap, maxSize?): Promise<ImageBitmap>
disposeTexture(bitmap): void
disposeAllTextures(bitmaps): void
```

普通裁剪输出最大边默认不超过 256 像素。自动识别路径支持带 mask 的透明纹理提取、羽化边缘、反光检查/修复和诊断信息。

**试戴甲根纹理开发对照**：固定alpha、试戴仿射与渐隐，按原图精确面积重建甲根内区RGB并维持接缝约束。按画面倍率平滑调整的1–2px不透明保护使两组共5,184对渲染帧相对原2px基线总颜色误差下降2.05%，48/48甲改善，12个轨迹尺寸分层的相邻色差误差改善幅度为0.00%–6.09%，144个分组无回退，透明度、完全甲外、混合边缘和接缝零新增。该方案当前为纹理试戴生产渲染默认路径：`src/lib/ar-root-color-protection.ts`提供行积分精确采样、2px/1px保护域、根带邻域限幅替换与物理覆盖权重，`ArView.tsx`在离屏层按当前绘制矩形映射原图坐标；`NEXT_PUBLIC_AR_ROOT_COLOR_PROTECTION=off`可构建回退现行采样，任一步失败自动保留基线。隔离Chromium最重双保护路径100帧P50/P95为5.30/7.70ms，最终alpha与基线逐字节一致。真实相机画质、长会话与真机成本仍按§4.5和Goal验收。见[标准与压力重放](../model/reports/ar-root-quality-first-v7/replay.json)（SHA-256 6f3249c34524d5fef0c1d49fccf7c05e4c045d5a5585ff19a592d29da256e95f）及[生产实现测速](../model/reports/ar-root-quality-first-v7/production-performance-20261122.json)（SHA-256 fbe5dbbd751241e9814bf8e5a5e675a0040282b32552aa2e66eb07be81c26f55）。

v1.2.258的径向模型提供`coverageAlpha`（长度严格等于`width*height`）：它记录原始轮廓的4×4亚像素覆盖率，允许保留二值边缘外的部分覆盖像素；原始`data`继续用于几何评分与方向估计。提取范围含有效覆盖率支持域，覆盖率经Canvas连续缩放，RGB直接从原图采样到目标纹理后乘alpha，并保留原图透明度；原`alpha`来源继续沿用向内羽化契约。主轴摆正、alpha加权旋转与256封顶继续执行。生产权重原图开发域634甲的同提取器对照中，4×4及其轮廓内裁限均比2px向内羽化减少加权漏抠并增加甲面外残留。裁限的最大alpha跳变明显增多，该方案已结项，生产继续使用完整4×4覆盖率。固定2px羽化和现行v5真值时，同来源五折侧缘轮廓同时降低加权漏抠与甲外残留，结果绑定 `model/reports/production-side-texture-v3/decision.json`（SHA-256 `8d5a5edfee95688b9b8ba2dbc1f008b3bc847260d8466c02f84a2ea11acc78c3`）。冻结634甲的同提取器对照中，仅补前景因甲外alpha增加结项。两侧和两端8px带内双向真值编辑均达616/634并同时降低加权漏抠与甲外alpha，两端的逐甲漏抠回退较少。该结论为真值辅助可达性，报告 `model/reports/side-replace-browser-texture-v1/report.json`（SHA-256 `1d03bfe935ee7397981f179de3198cb826742e1865e509f474445db1fd1c62af`）。生产至五折轮廓的原配对经过选择器归一化后保留纹理联合改善，并减少相对v5参考的贴合几何偏差。共用两次裁剪、角度和终态尺寸的634甲对照仍保留侧缘轮廓的整体纹理收益，恢复2/10枚仅摆正后加权漏抠回退及3/13枚仅摆正后甲外alpha回退。49枚贯穿摆正前后的漏抠回退仍有48枚回退，共用框路线结项，证据 `model/reports/texture-shared-normalization-v1/decision.json`（SHA-256 `31a5a217bab43e4b64309f61908eca3ff3d37a61261f7e8f97fc5aa29fe04c89`）。生产4×4覆盖率在相同终态坐标下的原图直采减少甲外alpha，加权漏抠配对区间跨零且触发边缘跳变和贴合几何回退门，归一化沿用现行路径。见 `model/reports/aa4-direct-normalization-score-v2/decision.json`（SHA-256 `821ff21c25eb91138000885c428288b6be90532be9511b698b7719cea7d10b61`）。固定生产覆盖率和几何的634甲颜色对照中，只在真值外侧借色可降低色晕代理13.7%并保留甲内细节；低alpha与预测轮廓外侧选点的甲内高对比误差分别增加4.2%和6.7%，均未过花纹保护门。现行提取沿用直接采色。报告 `model/reports/aa4-edge-color-gating-v1/report.json`（SHA-256 `b9296b159a04ba871a1ce454bb2e048dfedc37df1ce2e4c3e80f000a2317fa31`）。无手部方向时维持甲尖复核，证据见 `model/reports/production-side-normalized-v4/decision.json`（SHA-256 `32dd443755aca8b8e3c58114078e9f6280ad747c6d5dd0f6abb986a8efab8a7e`）。双分辨率隔离上传链按局部mask坐标从原图直接采色。冻结全量输入的逐指绘制纹理中，412份由新上传直接采集，53份经冻结Worker结果重放核实；其中17份可见alpha触及位图边缘，未测得0↔255邻接跳变。原图源覆盖率的加权漏抠为3.017%，冻结原图纹理链为2.647%。同ROI硬轮廓的独立2px羽化对照中，完整侧缘轮廓使加权漏抠从3.923%降至1.805%，甲外alpha从1.805%降至0.416%。同口径的16px局部保拓扑真值对照分别为1.479%和0.032%，两项对照均未出现0↔255邻接跳变。全634甲的真值半径对照在硬mask逐字节相同时，取接近首个排除像素的半径使原图4×4覆盖率加权漏抠3.017%→0.034%，甲外alpha 2.268%→1.605%，原图0↔255邻接跳变3707→1538处。区间中点的漏抠0.827%、甲外alpha 0.533%，跳变增至15081，停止优先考虑中点。原像素方向已独立复核的20甲在近上界对照中，甲根和甲尖加权漏抠分别从7.216%与8.085%降至0.044%与0.052%，两侧也下降。这是原图覆盖率的真值对照，摆正纹理及真机指标仍用现行独立验收。硬mask与透明边缘继续分别验收。原图网格几何判决见§6.2。双手图仍保留未分配候选，试戴应用按单手5指处理。全图手部方向覆盖与现场试戴见§4.5和Goal。

## 7. 模型产物契约

正式 manifest 路径：`public/models/nail-texture-seg/manifest.json`。

静态目录准入（v1.2.163）：`public/models/` 只保留生产 manifest 与批准/合成占位权重；仅测试用导出（如 candidate57 的 `testOnly: true` 双阶段权重）一律存放于 `model/test-assets/<候选名>/`，元数据 JSON 入库、`*.onnx` 由 `.gitignore` 排除，避免任何构建把 `deploymentAuthorized: false` 的权重作为静态资源公开。该搬迁只改变资产位置，不改变 candidate57 的 TEST HOLD、不恢复其部署资格，也不改变正式 manifest 的 `not-deployed` 状态。

`deploymentStatus`为可选枚举`deployed | not-deployed`，缺省兼容旧候选，显式非法值（含null）拒绝。当前默认manifest为`deployed`（`nail-texture-seg-geometry64-browser-aa4-v2`）；`not-deployed`时window/worker共用加载器及Stage B入口均在ORT会话前返回fallback和`model_not_deployed`，`resolveModelUrl`拒绝解析。资产审核、发布登记及切换拒绝未部署/非法状态，且不创建登记或覆盖活动manifest。`deployed`仅表示声明可加载，仍须资产完整性、同一发布身份及全部质量门，不自动授予发布资格。

```json
{
  "version": "nail-texture-seg-geometry64-browser-aa4-v2",
  "deploymentStatus": "deployed",
  "inputSize": 512,
  "inputLayout": "NCHW",
  "colorOrder": "RGB",
  "normalization": "zero_to_one",
  "resizeMode": "letterbox",
  "task": "segment",
  "backendPreferences": ["wasm"],
  "modelFile": "geometry64-browser-v1-stage-a-512-fp32.onnx",
  "modelSizeBytes": 11538755,
  "sha256": "0a6b842e1ae61011320881e2a4161a86a485841d27797ef88d3efdc5554b4e78",
  "outputContract": "ultralytics-seg-raw-v1",
  "scoreThreshold": 0.35,
  "labels": ["nail_texture"],
  "stage2": {
    "mode": "radial-refine",
    "modelFile": "geometry64-browser-v1-stage-b-radius-presence-fp32.onnx",
    "angularSamples": 2048,
    "presenceThreshold": 0,
    "nmsIoUThreshold": 0.7,
    "edgeRefinement": { "mode": "radial-coverage-v1", "samples": 4 }
  }
}
```

`stage2.mode: "radial-refine"`（v1.2.256）为mask替换型两阶段组合：Stage A 按ultralytics-seg-raw-v1输出det/proto，宿主逐候选裁剪1.7×方形上下文（round-half-even）、计算径向格（2048角×129径向偏移）并构建strip输入[1,5,2048,129]+coarse_radii[1,2048]，Stage B输出radius[1,2048]+presence[1,1]；宿主按`radius[bins]−distance ≥ 0`解码原图域mask替换粗mask。`presenceThreshold: 0`表示presence<0拒识（拒识候选按既有低置信复核流处理），`nmsIoUThreshold: 0.7`与Stage A服务端NMS一致；径向偏移数129与上下文比例0.35为宿主实现常量。manifest校验（`validateNailTextureModelManifest`）对radial-refine要求modelFile、可选angularSamples（≥16整数）、presenceThreshold（有限数）与nmsIoUThreshold（0—1开区间）；旧`rescore`模式字段组（inputSize/cropContextRatio/promotionMarginThreshold）仅适用于rescore语义，两模式互斥校验。该组合与本机serve-nail-candidate.py同构，逐实例mask对拍三方（PyTorch CPU/serve CUDA/浏览器WASM）IoU全=1.0（证据`model/reviews/geometry64-browser-parity-v1/`，含letterbox字节级检查diffBytes=0）。

`stage2.edgeRefinement`（v1.2.258）为可选产品处理字段，只接受`radial-refine`下的`{mode:"radial-coverage-v1",samples:2|4}`；缺省关闭。当前4×4配方保留原角桶半径与原解码，另算边界带覆盖率；关闭本轮退步的均值平滑。组合发布身份为`nail-texture-seg-geometry64-browser-aa4-v2`，两个ONNX字节及原始数值血缘沿用v1。全100源634甲/636候选逐像素重建与独立重放、600×800部署4实例原mask零差及覆盖率Python↔TS零差见`model/reviews/edge-refine-geometry64-v1/`（report SHA-256 `354543987da8a55ef632e77c71f24df40d4ea0a626458070e53b96e9c1524fdf`）。8×8数值参考下4×4平均覆盖率误差0.02099，硬二值0.15779；真实几何平均Boundary IoU/F1仍0.338758/0.764382，严格联合0/634。该train开发对照与桌面Canvas成本验证保留各自范围，来源组仅1个，来源簇置信区间不可估；真机、未见质量及商用完成门保持。

`stage2.radiusSmoothing`（v1.2.323）为可选产品处理字段，只接受`radial-refine`下的`{mode:"rms-bounded-gaussian",deviationRmsArcPixels,gridArcPixels,areaCompensation?}`；缺省关闭，关闭时解码与覆盖率输出与 v1.2.322 逐位一致。语义：对 Stage B 输出的 2048 角半径向量做角度域循环高斯低通，核宽在`gridArcPixels`（弧长像素，升序）中取满足 RMS 径向偏移 ≤ `deviationRmsArcPixels` 的最大者，弧长换算`arcPerBin = 2π·max(1,median(radius))/bins`；`areaCompensation`（缺省 true）按`δ=(A_目标−A_当前)/周长`整体平移半径并重解一次，使平滑不改变 mask 面积（`|δ|>2px` 视为不可信并放弃补偿）。平滑后向量同时供`radialMaskLogits`与`radialCoverageAlpha`，两者必须同源否则 mask 与覆盖率不一致。证据为三轮零推理判决：全局/每甲腐蚀膨胀与1px平移均不足以过门（`radial_family_insufficient`，`model/reports/cycle091-contour-calibration-ceiling-v1/`）；循环低通使训练域严格联合248→422/634、meanMaskIoU 0.9877（`cycle092-contour-smoothing-prior-v2/`）；去面积混淆后`adaptive0.7+ac`仍420/634、meanMaskIoU 0.98804、meanF1 0.99004、面积偏置相对对照+0.034、eligible上限436（`cycle093-bias-neutral-smoothing-v1/`，report SHA-256 `710201aa…`）。运行时与证据侧逐位对拍：16枚冻结预测半径向量（按运行时bin原点`floor(wrapped·N/2π)`重拟合，`tests/fixtures/radius-smoothing-parity-v1.json`）的解码指纹、核宽与面积全零差，且与093模块自带实现16/16选出同一核宽。**原生半径复测（v1.2.323 追加，重要口径更正）**：上述420/634是在「从预测mask重新拟合的轮廓半径」上的代理指标（重拟合有约0.5px外扩，重建IoU仅0.998），而运行时平滑的是Stage B**原生radius输出**，两者不是同一向量。直接在原生半径上复算（`model/reports/cycle094-native-radius-smoothing-v1/`，保真门：原生解码与评估存下的mask逐像素零差、基线严格联合精确复现248）得：τ=0.7时仅**3/634**触发平滑、严格联合**248→248（增益0）**——因为原生半径的相邻bin抖动实测约3.47px，连σ=0.5px核都会产生2.17px的RMS位移，超出0.7的界。τ扫描（`cycle095-native-radius-tau-sweep-v1/`）：τ=1.0→251、1.5→261（+14/−1，p=9.8e-4）、**2.0→281（+47/−14，净+33，配对双侧p=2.7e-5，meanBoundaryIoU 0.7247→0.7308、meanMaskIoU 0.98467→0.98553，但meanBoundaryF1 0.98880→0.98505）**、2.5→273、3.0→278（后两者不一致对增多且不显著）、4.0以上→241（过平滑）。结论：该算子**在当前默认τ下对真实输出不生效**，按τ=2.0重标定才有约+33甲的净增益，仍远低于539门。**未启用**：生产manifest未声明该字段，不改发布身份；`deviationRmsArcPixels`与核宽网格为in-sample选定，独立来源未标定，真机与商用完成门不受此字段影响。

**训练侧半径平滑正则**：该开发路线已关闭，原生半径终评见§8.9，三组实验及配对统计见2026-11-17开发日志。

`scoreThreshold`是模型版本级候选阈值：运行时、原始输出过滤和质量排序使用同一有效值；字段缺省时保持`0.35`兼容，显式值必须为0和1之间的有限数。`export-onnx.py`可通过`--score-threshold`写入校准值，浏览器manifest校验和`verify-model-artifact.ts`执行相同约束。该字段只是保存已完成验证的模型校准结果，不能用单次阈值扫描绕过误检、候选数量、直接可用率或Beta发布门。

当前组合版本生产构建与真实浏览器端到端通过：`/ar-tryon`实际Worker返回4枚600×800原mask和覆盖率，自动提取并应用4指纹理（单次约1.68秒），无识别warning、页面脚本或资源错误。相关44项测试通过；全量首轮1532项中的26项环境失败，在10个原失败文件的原生串行117项复验中全部解决，原日志与复核保留。完整证据及开发A/B页见上述目录，移动端实际性能及真实低对比边缘视觉验收继续单列。

正式阈值必须由`calibrate-model-score-threshold.py`使用来源隔离的`val`预测生成。校准器绑定数据集、来源报告、模型权重、评估指标和预测制品SHA-256，拒绝`test`/冻结发布测试、val来源跨split和未知预测文件；`--truth-audit`还必须提供`approved_as_calibration_truth`报告，且dataset路径/哈希、逐标签SHA-256、预期/已审/通过数量全部一致、返修和排除均为0。未提供审核或审核明确拒绝时分别输出未审核/已拒绝诊断，永远不生成manifest阈值。至少30张验证图、真值polygon零修复、所有验证图通过原分辨率完整甲面审核，同时满足召回、每图误检和单图候选数门，才输出非空`manifestScoreThreshold`。任何返修/排除项、未声明交叠、漏甲、重复、误标、污染或边缘裁断都会使整套split失去校准资格。

规范校准不能直接让Ultralytics读取受审核数据根目录：标签扫描会自动创建`labels/*.cache`并污染不可变物化清单。`evaluate.py`现在先把所选split的图片与标签逐文件复制到输出侧`evaluation-runtime-dataset`，运行YAML只指向该副本，并在物化后和推理结束后重算源数据整树相对路径及逐文件SHA-256；源树任一新增、删除或字节变化都会拒绝证据。评估制品按POSIX相对路径字符串稳定排序，绑定逐文件SHA-256及覆盖每张验证图的`prediction_records`，无预测图必须显式记录为零而不是从清单消失。v6在规范val30部署512上的box/mask mAP50为0.6241/0.5630；confidence=0.05时召回0.7569但每图误检9.8333、单图最多28候选，其余扫描点召回均低于0.75，因此没有合格manifest阈值。

正式发布要求：

- manifest 通过结构校验；
- ONNX 文件存在，文件名与 manifest 一致；
- 输入/输出名称和张量形状与后处理契约一致；
- 通过 fixture、真实图片、浏览器集成和性能门；
- 具备版本、SHA-256、体积、指标、发布和回滚记录。

当前生产manifest为业务发布`nail-texture-seg-geometry64-browser-aa4-v2`（v1.2.258；双ONNX字节及源权重沿用v1.2.256的`nail-texture-seg-geometry64-browser-v1`）：几何64轮Stage A源权重SHA `5ef154704e36691871a50e162b8e446a12dc3211404ad014f8aceeb9d8b52b4e`、Stage B源权重SHA `161e10be562fa4becd00cbde2c7bb4fcf80611308c681afc9dfd4e6d71fbf9ea`，ONNX导出数值验证与发布对拍证据在`model/exports/geometry64-browser-v1/onnx-verification.json`及`model/reviews/geometry64-browser-parity-v1/`。该发布只声明业务发布门（§3），商用完成门保持HOLD；历史v6及synthetic/smoke只承担原绑定诊断/工程用途，不充当正式模型或回滚批准版本；当前训练候选状态见§8.9/§11.1。

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

当前指定素材精标链为`model/reviews/cycle016-wevis-real-material-v1/batch037/annotation-closeout-v1.json`及`annotation-final-verification-v1.json`，现行100图634甲规范索引`batch037/cumulative-training-truth-index-v5.json`绑定已闭合的同RGB修复及原角色。原图均来自`E:\AI Project\Codex\JiaRu_image\真实素材\美甲图片素材`，哈希核验通过。444已审及779未审、124/384/175未决保持。历史旧23中1张AI生成正例10甲已实际进入混合Stage A/B，相关权重撤回后续使用；旧角色和失败不改写。当前专用重建只含100指定源，范围`batch037/real-only-training-scope-v3.json`，初始化官方来源及全部曝光闭环见`real-only100-closeout-v1.json`。17张卖家包待核验图在开发范围内召回33对局部特征线索。可直接核验队列已结项。其中12对裁为可见不同，8份当前文件因甲面不完整或失焦被排除，关联21对待完整父图。其余9张候选中6张命中历史冻结清单及预标注记录，均待可核验的上游拍摄与父组凭证及完整mask准入。凭证核对账 `model/reports/seller-lead-parent-recall-v2/nine-candidate-provenance-v1.json`（SHA-256 `f48c0b7a3c60c922616bf813a3ce63d309937bdad4f7d28a4fea722028064f4e`）。候选结项账见 `model/reports/seller-lead-parent-recall-v2/whole-original-source-closeout-v1.json`（SHA-256 `bc0a8de72abb0548e4c77b6b526dd020fd1bbf88f06410980823a21a080583cb`）。

现行分型合同1区分同摄影帧变换、拍摄系列视觉关联、仅风格相似、可见不同及不确定；拍摄系列关联不作像素复制正控，数值候选继续禁止，完整源/角色父血缘/实际查看及无缩放分别绑定。完整图片输入遵循用户整图政策v5（`model/reviews/cycle016-user-whole-image-batch-review-policy-v5.json`）：单批及单张作为批的一部分≤50000000字节、每响应≤6独立整图、不另设整轮上限；已看完整事实按精确SHA继承，不重发旧分块。发送前冻结实际文件/页面SHA及字节，尝试采集当前线程近时请求；遥测缺失如实记未知并允许有界发送，不记为测量门通过，已观测准备请求≥100000000字节时停止增图。文件、base64估算及实际网络流量分别记录，实际缩放拒绝原像素结论。旧I016等4MiB页/8MiB请求及未知拒发限制只作历史保留，不能覆盖后来用户明确的50MB单批政策。该更正不放宽原像素质量、来源/完整mask、数据角色或发布门；具体历史编号见实验归档§12.302，最新整组实例见当日日志。

既有18源11组106甲/118输入的供给链见`model/reviews/cycle016-6cba-group-review-v1/`和`cycle016-6cba-supply-closeout-v1/`，原角色、真值和历史失败不改写。最新最大组开发扩量的已知来源召回关系与35甲原尺寸输入分别见`cycle016-expansion-family-pairs-v1/`和`cycle016-expansion35-baseline-v1/materialization.json`；只授予本开发合同范围，不构成正式来源独立、全split资格或发布通过。当前研发训练见§11.1。

内部开发诊断的角色/真值读取以`cycle016-internal23-development-diagnostic-v3/report.json`为当前范围：29条内部val真值中27条曾入候选、4条后来源质量排除、23条保留，另2条在候选范围外，禁止把后者改记质量排除。逐甲旧证据须按实际sourceIndex或targetIndex及对应实看字段继承，不能以空train真值槽判val缺标。当前来源裁决补充见`cycle016-internal23-family-ef82-v1/`与`cycle016-internal23-family-e93-v1/`；同既有相册不同手姿照片保留拍摄关联和历史val角色，不成为独立来源。余192对关系与实际候选域未闭合，整23源132甲诊断仍禁止，不能按已闭合子组缩分母启动。

原153开发训练真值资格仍撤回，原追加裁决`model/reviews/cycle016-reference-shadow-review-v1/current-qualification.json`及历史失败不改。完整22源处置现见`cycle016-train153-truth-reaudit-v1/report.json`：五枚污染甲返修通过；源5另露截断甲面整源排除，源8/9/10历史派生图缺父SHA/来源组、三整组保持未决。误发6裁片页不追认整图通过，原角色与全部分母保持；其余18完整源123甲/11候选拒识以`cycle016-requalified134-native-v1/report.json`及`replay.json`建立独立版本的134开发域，原坐标完整、RGB/粗mask不改、原153指标同构。新域只授予开发训练，不授予正式来源独立或发布许可；旧distance-readiness仍失效。

公开六原图、紫色五甲仅诊断及2张GET429未取得继续保留。原26源136甲18组差集内3源18甲已StageA开发训练、dced1源8甲保留已消费对照且不回训；591f/f4f两源8甲整组12图对及完整原像素真值资格见`model/reviews/cycle016-591f-family-admission-v1/report.json`和`model/reviews/cycle016-f4f-family-admission-v1/report.json`及各replay/precision实审。全局v61为2315=822新裁决+17继承+1476未决、7不确定，余20源102甲13组关联832未决仍训练禁止。两源全11候选归属已完整实审，3额外项为同甲局部重复/文字皮肤/手套褶皱；保留原train角色/8甲/标注不变，现已加入StageB开发训练，不充正式未见留出。现行23源149完整训练甲/5同候选拒识、154身份及462固定视图合同见`model/reviews/cycle016-two-source154-v1/materialization.json`及`materialization-replay.json`；全部162原始输入含原保留8，其训练视图始终0，内部val不回流。旧物化/角色/失败保留原报告，可见不同仍不等于正式来源独立。 当前149训练真值的完整原图距离目标、154身份/462视图与全162最终输入完整继承，保留8目标/训练均0；现行绑定见`model/reviews/cycle016-pretrained-context-v2/materialization.json`/`materialization-replay.json`，上游完整距离派生重放仍保留`cycle016-distance154-v1/`，不新增图片/角色或正式资格。

既有Stage B已批准训练素材队列终止条件为`eligibleUnconsumedIdentityCount == 0`，现已满足：`model/reports/nail-texture-training-material-consumption-closeout-v2.json`逐事件验证154/154身份、462/462固定视图已消费，42,625个事件SHA及18,480个开始/确认输入完整，每视图20次；该消费审计新增训练0；当前新素材Stage A训练另见下节。数据消费终态不等于最新训练开发门通过、Goal完成或发布通过，保留8及未审/未决素材不转入eligible集合。

后续批次衔接固定为“批准角色账与未消费身份→冻结完整分母/SHA/假设/可达性/预算→单次训练与原子事件→独立重放→登记消费和保留候选→仅在仍有合法新批次时另冻下一轮”。失败预算不回滚，失败权重不自动续训；素材耗尽后报告`dataConsumption=complete`，同时保持`modelGoal=ACTIVE / PRODUCT HOLD`及全部质量/发布缺口。新素材须重新完成审核、准入、物化和新合同，不改写本终态。

### 8.9 学得原尺寸候选的精度复验接口

**当前训练与评估口径**：真值v5/范围v3为100名义图634甲。等权局部几何侧缘头同来源五折397/634，严格通过与最差单甲回退两项尚未达门。两端逐像素头首折98/115；前景加权及同图颜色统计均未过继续门，当前开发候选止步首折。同图冻结判决见 `model/reports/end-sibling-context-v2/report.json`，SHA-256 `c72d5b26dc68849235385d248c57cb3fa773f515aeb8b435747bdafa05c77c17`。冻结634甲原像素诊断中，只修53枚纹理漏抠回退甲最多到420/634；扩大至全组，在8px边带仅补两侧真前景可达542/634，保留原严格通过248甲。结论属于同来源真值辅助可达性，见 `model/reports/side-alpha-edge-reach-v2/report.json`（SHA-256 `d03b8189d44325d0e0fd6d27296b59c609667c686cd57d88ce79b4f223a54008`）。冻结首折115甲上，预测端带与真值端区各有114/115的真值辅助可达性。端头的现有提议覆盖39.5%的应补像素和62.1%的应去像素，邻域符号重排在同修改量下未改善精确率，几何继续门失败。见 `model/reports/end-signed-support-v2/report.json`（SHA-256 `78aa64d8e1b0e70046489b7726335a3d5707df4605935a6b4bba511179b9f17a`）。第90/92次四份完整轮廓经逐甲原像素评分重建。侧缘头8px带内只纠正模型分歧覆盖的错误时，带拓扑保护达471/634，移除拓扑保护并保留原通过的对照为510/634。完整8px带的真值对照为629/634。联合监督实训首折97/115，较两端头98/115无新增、丢1，最差Boundary IoU下降0.02140，关闭本配方。实训重放 `model/reports/contour-full-band-v1/replay.json`（SHA-256 `2f6a604ee388442c8df3cf14d0a03e0468ebd54d564dc143397ccb7d4d89af4e`）。分歧像素证据 `model/reports/full-contour-disagreement-v1/report.json`（SHA-256 `ffea2708848b516e24a9594832b9dace3f6e37c215b5f4cb946da9c03b98daa1`）。首折同来源115甲的连续片段对照在既有8px带内用真值选择净纠错片段，原图2px严格105/115，保留两端头原通过98甲，平均Boundary IoU增加0.03303。仅在分歧内逐像素纠正可达107/115。两项均为真值辅助可达性。使用冻结几何、分数及来源做同像素单元组外预测，严格97/115，较端头无新增、丢1，低于分区先验98/115，片段路线结项。逐甲报告 `model/reports/contiguous-fragment-selector-v1/report.json`（SHA-256 `71c8af9525773d723654bc8a8e7e4a1db5b51de4684e770759c8ec42a0d0e4d1`）。同首折换权重的浏览器输入对照见§6.2。当前浏览器8px侧缘及两端支持域用真值直接替换时达113/115并保留本机组合98甲，沿用分阶段拓扑回退后为107/115并失去其中6甲。冻结五折轮廓的纹理评估见§6.4。当前修边候选使用甲缘弧长上的闭合位移优化。同首折115甲在8px边带内以真值引导位置选择，严格98→115、原通过零丢失、平均Boundary IoU增加0.05255、拓扑回退0。拟合和首折评估均使用侧缘加两端轮廓，拟合端按嵌套组外生成并排除首折及输出折。匹配的原图及纯几何成本回归在首折均严格98/115，全部遮罩保持原端头，训练配方结项。拟合组约32.3%的弧段有净纠错位移，全组的0/+1档像素等价。合并等价档后的平衡有符号收益拟合，两臂在519甲拟合子折预检均0/519（参照353/519），内收、外扩均净增错分，关闭配方，首折保持未调用。在相同519拟合甲与候选位移上，有序原像素窄带的内收和外扩AUROC为0.5813/0.6018，较最强对照高0.0162/0.0009，两个方向在最高1%至全量各档均净增错分。结束该局部打分配方。4/8个均匀控制点的真值辅助轮廓严格88/92甲，丢失10/6枚端头已通过甲。改为最多1/2次局部位移、未选区域保持原样，严格100/107甲，较基线净纠正3,251/4,892像素，端头原通过丢失0/0甲。最多两次局部修边通过真值辅助继续门。开发拟合组519甲的同像素分组组外对照，基线353甲。真值辅助的最多两次局部修正达430甲，纯几何和加原图颜色的自动提议分别352/350甲，新过2/1甲，基线丢失3/4甲。两臂均未过门，结束本次修边打分配方。此自动配方未调用首折115甲。人工盲测载体已冻结，20张完整原图逐字节一致，Chrome已载入115个候选，合成点击和原像素坐标、拓扑回退、跳过、续作及导出过工程检查，真实操作者记录等待回收。当前1px外侧补回基于冻结几何修边，在519甲上使用真值且保拓扑、周长不增时357→462。配对训练加入冻结Stage B和侧缘轮廓后达到366甲，保住原通过且减轻漏抠和甲外残留，Boundary IoU平均增量未过门。冻结连续分数在等候选量下未提高真前景覆盖。每甲允许现有硬轮廓模型提供四分之一外侧候选时，真值筛选满足内部继续门，直接补回因错补回退。对现有自动输出逐甲真值择优的平均Boundary IoU松弛上限仍低于继续门；停止重排和整甲切换。固定外侧候选后的单笔正负锚点和局部真值过滤均未过内部继续门，停止该局部手势配方。模型工作继续验证实际部署路径分类保真（§6.2），局部修边盲测仍按冻结合同独立回收。局部手势报告 `model/reports/contour-crossing-anchors-v1/report.json`（SHA-256 `614975cf7f65284bf329963f7372c775ca4712b0215f8d9ba805de588a200a82`）。组外实训重放 `model/reports/contour-outer-foreground-v1/replay.json`（SHA-256 `18fb2b1ba0294b7848e7019adbcdf630fbabb7bfef9238fef5659d39b4f05d29`），其他对照见Goal。实训报告 `model/reports/contour-arc-cost-paired-v2/report.json`（SHA-256 `1151085e2bb85fbfeed9ea2acad44b7a55f078fabd03b030eca43110f9ad812e`）。该结果为单来源真值辅助对照，报告 `model/reports/contour-arc-displacement-reach-v1/report.json`（SHA-256 `d73f3226663a0aba2cd139fe0f8326da68037c99438e255cea994369daef1de9`）。跨来源模型复验仍需独立准入，活动计划及正式质量门见Goal。冻结编码特征的局部排序未增加严格通过数，已结项。现行方案把原图3px边带分成互斥局部截面，各自保留一个内移、不动或外移的切点。519甲按79同像素开发组完成自动定位的四折配对。两臂增加严格通过甲数，同时增加加权漏抠，几何增量未过继续门，配方结项。冻结几何内收时，按实际2px羽化损益的真值辅助外扩可同时改善两项纹理指标。按硬像素或羽化损益的自动外扩均未过漏抠及几何门，羽化目标的等量排序也弱于原几何，单截面监督配方结项。等实际补边预算下，相邻原图联合打分的净纠错组间区间跨零、整体漏抠增加。固定自动外扩时，内收真值保护仍未过Boundary IoU继续门。内外两向均用真值时过内部整体继续门，甲根漏抠仍增加。单向编辑和整甲配准均已结项。局部颜色混合弱于纯几何排序。按自身拓扑守卫复算的纯几何也未达到几何与纹理联合继续门。现行矢量覆盖率在1px带偏向去除，作为统一监督筛法已结项。只补回的固定像素与整段评分均已结项。现有2px连续候选用真值辅助可同时通过几何和纹理继续门，同量逐点保留更多甲根纹理。冻结预测一致性、低分位置信及原图Lab对比六臂同量复核均增加甲外残留。最强固定序列即使用真值逐甲选择安全停点也仅补回635像素，低于已核验的14,482像素可行配置。4px仅补回在原始2px羽化下使定向甲根漏抠最多降低24.66%，甲外残留和最大相邻alpha落差逐甲未增加。固定双向真值纠错几何和最外羽化圈后，在确认方向的真甲根第二圈以逐处梯度约束提高alpha，保留501甲几何通过，与同几何默认羽化相比甲根漏抠降低6.30%，甲外残留逐甲持平，所有原分区继续门通过。自动修边前后同坐标的羽化变淡及冻结邻接几何筛选均增加甲外残留，已结项。试戴纹理的传递证据见§6.4，暂缓训练。见[自动转变重放](../model/reports/contour-root-alpha-transition-signal-v1/replay.json)（SHA-256 3b4bc654e31aaab8ac10f1ad9d73faa8036fdf55c4891701a20e4ff485d82d78）。见[整甲配准重放](../model/reports/contour-whole-registration-v1/replay.json)（SHA-256 136b41f8a06d67309f8e1c49481b5c6c3d132c52ac0def1ddaee69fd1357b3d1）及Goal。

**当前技术实施总合同**：见 `docs/nail-texture-local-inference-implementation-spec.md` v1.13 §6.1/§6.3——Stage A 512 候选、Stage B 原尺寸四通道及 mask/presence 双头、完整原图坐标逆映射。当前修复仅 Stage B 合成接口通过；真实输入、Stage A+B 完整 Worker/Canvas 及发布身份仍须验收。

**当前导出与修复接口**：`export-native-trained-fullchain.py` 提供真实 300 状态严格加载、原尺寸双头导出、严格 FP32 CUDA/CPU ORT 及完整 RAW/事件重放；`onnx-native-fullchain-repairs.py` 组合 16 处同 epsilon 的 float32 分块归一化、4 处 3×3 空间分段和最终 1×1 分段，其后 `onnx-blocked-presence-reductions.py` 仅改三处 Sum/Mean 为同 float32 三级 128 分块累加。各变换逆序恢复原完整 ONNX 字节，全部原权重、偏置、阈值不变。生产接入仍须真实输入与整条链验收。

**当前部署控制**：见 `cycle016-presence-stable-independent-v1/report.json` 与 `cycle016-presence-stable-learned-v1/report.json`——独立非零及真实训练权重分别全 27 输入 54 RAW，各三后端九尺寸达到两头绝对 1e-4、解码零像素差和 presence 一致门，含 1536 方形与极端长宽比。合成通过不授正式质量、性能或发布资格。

**本机业务候选（2026-11-05）**：几何 64 轮权重 SHA `161e10be…f9ea` 经 Python/GPU 接入 §5.4，仅选择已完整终评真实 100 源分支中平均边界 IoU 最高版；证据见 `model/reviews/business-candidate-20261105-v1/` 与 `docs/nail-texture-business-candidate.md`。

**历史叙事与脚本登记已归档（2026-11-08 v1.2.280）**：本节此前的逐版本实验叙事（v1.2.274—279 各轮配对/容量结论）、已结项实验（全634边缘监督64轮、几何残差64轮、像素径向24轮）、历史分支报告索引与 60 余条诊断/一次性脚本登记，整体迁至 `docs/archive/whitepaper-native-precision-history.md`（A 节）。当前接口以本节上文与实施规范为准。

## 9. 验证与质量门

基础工程门：

```powershell
npm.cmd run lint
npm.cmd run test
npm.cmd run audit:encoding
npm.cmd run build
```

通过标准与已知环境陷阱：

- `lint`：必须 **0 problems（0 error / 0 warning）**，退出码 0。`eslint.config.mjs` 的 `globalIgnores` 已与 `.gitignore` 对齐，排除 `output/**` 与 `.backup-consumer-*/**`（二者为本地非入库产物，此前贡献 2654 条噪音，使 lint 长期退出码 1 且无法作为 CI 门禁）。新增本地产物目录必须同步进 `globalIgnores`，不得靠"基线有噪音"放行。
- `test` 与 `build`：**必须串行执行**，并行高负载会产生临时目录或进程竞争型假失败；并行失败时先逐文件串行复验，只有串行结果可作为阶段验收结论。
- `build`：在带批量删除守卫的沙箱中执行时，Next.js 清理 `.next/turbopack` 可能触发 `[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED]`（一次性删除超过 500 个文件）。这属于**宿主环境限制而非项目缺陷**：先用 PowerShell `Remove-Item -Recurse -Force .next` 清理构建输出后串行重跑，不得据此放宽断言或跳过构建检查。
- 用「把 `.next` 移走」代替删除来重建时，目标位置必须落在 TypeScript `include` 之外（工作区外最稳）。移入 `output/` 会让残留的 `.next/types/validator.ts` 以相对路径引用 `src/app/**`，构建在 `Running TypeScript` 阶段报 `TS2307: Cannot find module '../../src/app/...'`，属于自造的构建失败，不能记为项目缺陷。
- `build` 的替代路径 `next build --webpack` **不能充当构建门**：默认堆下在静态生成阶段 OOM（与 2026-10-16 记录一致），提高 `--max-old-space-size` 后会出现编译完成却不进入静态生成、无路由清单的早退（退出码 0 具有误导性），继续加大会触发栈溢出（`0xC00000FD`）。只有默认 Turbopack 构建输出完整路由清单且退出码 0 才算构建门通过。
- 含裸 `python` 子进程的命令（含 `npm.cmd test` 与 `audit:nail-texture-completion`）必须把 `C:\Users\YaoYinyu\AppData\Local\Programs\Python\Python313` 显式置于当前进程 `PATH` 首位。

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

Git 推送若出现`Failed to connect to github.com port 443`，应先用只读的DNS、HTTPS和`git ls-remote`复核链路，再比较`origin/master...master`，避免在提交其实已经到达远端时重复推送；按瞬时链路故障处理，不通过改分支、重写提交、关闭TLS校验或重复推送规避。历史发生与只读复核记录见dev-log/2026-07-20.md与dev-log/2026-07-21.md。

### 9.1 最近一次白皮书一致性审查

2026-11-08 v1.2.280 内容合规性审查与修复结果：

- 检查范围：§1、§3、§4.5、§8.1、§8.9、§9.1、§9.2、§11.1，并以当前源码与机器可读文件核验。
- 发现 §3 状态表前堆积 10 段逐版本叙事、§11.1 堆积 16 段且其中 4 段（v1.2.274—277）与 §3 逐字重复、§8.9 达 42,125 字符（占全文 25.6%）、§4.5 含 5 段版本叙事，均不符合「仅保留最新口径与必要技术文档引用」标准。
- 上述叙事原文已整体迁至 `docs/archive/whitepaper-native-precision-history.md`（A/B/C/D 节），正文保留当前口径与现行接口；全部章节标题保留，外部章节级引用不受影响。
- §9.2 生产 manifest 口径现为 deployed（见该节现行口径段）。
- 正文由 316,247 字节 / 1506 行降至约 225KB / 1257 行，回到约 300KB 体积门槛以内。

历史审查：2026-10-12 v1.2.0 结构重构（实验历史与变更记录拆分归档）与 v1.2.2 内容精简记录见 dev-log/2026-10-12.md；2026-07-12 v1.1.0 审查的历史结论原文保留在实验历史归档附录。

### 9.2 端侧实施技术规范复核

2026-07-12 对 `docs/nail-texture-local-inference-implementation-spec.md` v1.0 进行现状复核：文档的产品边界、浏览器端侧架构、模型/数据/性能分阶段门禁、隐私和回滚原则仍可作为目标实施规范；第 3.2 节及第 16–17 节部分「当前缺口/待办」已过期（源码现已具备 Worker 环境识别、ONNX Runtime WebGPU/WASM 导入和 letterbox 预处理）。该文档定位为「目标规范 + 历史实施基线」，实时状态以本白皮书和 `docs/nail-texture-current-goal.md` 为准。

**2026-10-12 分层更新**：规范文档头部版本为 v1.7；§23 及以后小节（2026-08-25 起的逐候选/逐轮实验合同，约376KB）已整体迁至 `docs/archive/nail-texture-implementation-spec-history.md`。

**生产 manifest 现行口径**：`public/models/nail-texture-seg/manifest.json` 为 `deploymentStatus=deployed`、`version=nail-texture-seg-geometry64-browser-aa4-v2`，模型文件 `geometry64-browser-v1-stage-a-512-fp32.onnx`（11,538,755 字节）与 `geometry64-browser-v1-stage-b-radius-presence-fp32.onnx`（1,495,223 字节）均实际存在。浏览器业务已发布，商用完成门仍 HOLD，见 §3「正式纹理模型」行。

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

当前唯一活动与阶段结论以Goal及§8.9/§11.1为准；本节不复制执行指令或旧里程碑。

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

当前研发采用Stage A候选与原尺寸Stage B精修，活动及优先级只读Goal和§8.8—§8.9；既有单阶段顺序不再作为当前指令。正式全新校准/正负留出、生产运行时/产品与真实外部验收门不变，当前没有批准releaseIdentity，审计继续HOLD。

### 9.10 可持续Goal指针合同（2026-09-07）

持续Goal以`docs/nail-texture-current-goal.md`为唯一目标文件；本轮依据用户最新“开始”指示推进，运行时Goal接口仍保留先前`paused`标记，未宣称工具已恢复`active`。完成状态仅在同一releaseIdentity的completion audit v3对全部当前发布门返回`ok=true`、`decision=complete`时允许写入；工具状态不用于改写未完成目标或追认历史失败。

项目采用“精简Goal启动器 + 可更新权威文件”：目标文件仅保留目标、核心要求、当前状态和下一步计划；读取、回写、字段保护和文档同步规则放在`AGENTS.md`。执行Agent可依据可重放证据主动调整当前路线与下一步，不得降低正式阈值、改变数据角色、拼接发布身份或移动最终完成语义。通用模板见`docs/continuous-goal-template.md`；早期静态Goal重构与旧轮次口径见历史归档，当前规模和里程碑以Goal为准。

## 10. 隐私、安全与资源管理

- `/editor` 上传照片默认在浏览器本地处理；「用户改进计划」开关默认开启时，手部照片等数据可能被上传用于产品改进（改进计划本身当前代码尚无实际上传通道，开关为偏好记录，未来数据收集上线后生效）；
- `/ar-tryon` 摄像头帧默认在浏览器内存中处理，不录制；MediaPipe程序和模型由本站同源静态目录提供；
- 自动纹理识别默认在浏览器 Worker/主线程中运行；
- `/api/generate-ai`与`/api/generate-seedream`接收文字及可选参考图，并分别转发给Agnes与火山方舟；返回图片由浏览器访问外部URL，主动生图不由“用户改进计划”开关禁用。
- v1.2.163 起新增一条**用户主动触发**的上传通道：`/api/nail-matte` 把浏览器压缩后的图片（长边≤1600 JPEG）发送到自托管（默认同机 `127.0.0.1:8008`）的 WeVisOne-VL 服务，仅用于本次轮廓提取，服务按内存处理、不转发第三方、不写入训练数据；未配置任何本机服务URL时通道与入口都不存在；v1.2.255起可优先转发本机自研候选（§5.4），保持同一隐私确认和内存处理流程。该请求不受「用户改进计划」开关约束（用户点击即授权本次处理），也不属于改进计划的数据收集。
- v1.2.217 起新增云端识别通道（§5.5）：`/api/nail-detect-ark`（方舟视觉理解模型）与 `/api/nail-matte-cloud`（云端自托管 /matte 契约服务）。与 nail-matte 同为用户主动请求通道——须用户在三个识别站点显式切换到云端模式，且首次使用前经一次性隐私确认（`jiaru.nail-detect-cloud-consent.v1`，说明图片仅用于本次甲面定位、不用于训练存储），确认后本会话内切换不再重复询问；识别模式为会话级不持久化，每次进入页面默认本地。结果固定低置信候选、须人工复核，不入训练数据、不写生产 manifest；方舟密钥复用服务端 `VOLCENGINE_ARK_API_KEY`，云端自托管 token 只存服务端环境变量；错误响应脱敏（不含密钥与上游堆栈）。真实第三方数据边界须以实际服务条款为准（同 §4.4 生图口径）。
- `AGNES_API_KEY`只能存在于服务端环境变量；本机`.env.local`受`.gitignore`保护，文档、日志和源码不得记录真实密钥；
- `ImageBitmap`、对象 URL、MediaStream track、Worker 和动画帧循环必须在取消或卸载时释放；
- 用户素材、训练图片、大模型权重和生成数据默认不应加入 Git；应通过 `.gitignore`、对象存储或独立数据盘管理；
- `model/reviews/`的已冻结二进制采用原路径、原字节不变的NTFS透明无损压缩；完全相同内容可共享只读硬链接。维护须冻结终态清单及完整SHA、拒绝链接越界和并发写、独占持久化操作事件，并在原子替换失败时恢复原文件；结束后按全部原路径重验SHA与终态报告。禁止单独解除共享别名只读后改写内容；新产物须另建版本。终态目录的稳定大文本报告使用同一透明压缩原语并逐文件完整SHA验真；增量维护先压缩未共享的可写文件，再精确去重，已有压缩/共享文件跳过重复操作。历史维护（2026-10-14/15）的原路径核验记录见`model/training/oneoff/reviews-storage-maintenance-20261015-v7/combined-report.json`和`model/training/oneoff/reviews-storage-maintenance-20261014-v2/verification-report.json`；当前捕获可用性另按下条退役登记查询。未决/近期写入目录保持跳过，旧质量失败与模型发布HOLD不变。
- 历史捕获退役（2026-11-03）：四组旧观察/全链路诊断目录的原始`.bin`已经用户授权永久移除，各目录有`CAPTURES-RETIRED-20261103.json`登记；原报告、失败分母与历史判决保留，被移除捕获的精确重放已退役（当前可用性见§11.3第8项）。执行证据、逐文件删除前哈希与操作事件见`output/reviews-history-cleanup-execution-20261103-v1/report.json`，过程记录见dev-log/2026-11-03.md。
- Git与远端的跟踪边界固定为完整可运行的业务、训练和审计代码，测试、配置模板、浏览器运行时必需资产与必要说明。模型权重、数据集、逐文件开发清单、训练计划/判定JSON、训练输出、评估明细、机器报告与review、审核截图、浏览器调试快照及其他可重建证据仅保留本地并由`.gitignore`隔离；小型稳定测试fixture可保留。历史`辅助材料`只跟踪必要Markdown说明，图片、标注、CSV/JSON/YAML和审核产物不再进入当前Git树。
- 正式 API 上线前需增加鉴权、限流、内容安全、审计、费用保护和错误信息脱敏。
- `/privacy`是待纠正的产品文案，不构成法律合规验收：仍称无账户体系、只列Agnes、关闭改进计划后不再上传任何数据，与已有账户、Seedream和主动生图数据流不符。账户数据库可保存手机号、身份、会话IP和审计记录；个人收录保存在本地IndexedDB。第三方“不用于训练或存储”不能仅凭本项目代码保证，需要实际服务条款/协议依据。
- 改进计划目前尚无实际素材上传通道（指改进计划的数据收集，与本机精细抠图这类用户主动请求无关）；隐私页开关仅写localStorage，账户页开关同时写`/api/me/improvement`与localStorage，反向同步未实现，可能出现账号与设备偏好不一致。后续接入上传前必须统一权威偏好与作用范围，不能把关闭可选改进计划描述为关闭用户主动请求的全部网络服务。

## 11. 已知限制与下一阶段

### 11.1 阻塞项

**模型质量**：当前训练及真值验收见§8.9；实际浏览器轮廓及其冻结迁移对照仍低于完整开发质量门（§6.2），独立来源与产品发布验收按各自现行合同推进。

**AR 试戴**：工程修复已接入（甲根锚定、可见尺寸、完整透明轮廓、连续采样、方向复核/翻转，见 §4.5）；实际摄像头根部定位、尺寸与侧转自然度、完整生产构建终态仍待真机与实机验证。

**生产与发布**：浏览器业务发布及覆盖率抗锯齿已接入（§3/§6.2/§7），当前组合身份 `nail-texture-seg-geometry64-browser-aa4-v2`；商用完成门仍 HOLD。

**来源与留出**：正式来源独立评估尚未准入；独立 val≥30、全新正负发布留出、四类真机与 Beta 验收仍待建立。已消费留出与内部 val 不得回训。

**历史资产**：按分层保留口径（2026-11-18 用户批准，执行细则见[冻结证据与重放](agent-rules/evidence-replay.md)「捕获保留与存储维护」）：发布绑定证据（源权重、导出验证、对拍捕获）、在途与当前阶段链（81—92）轮次完整证据、各轮评估级预测/报告/判决、最终权重及首末与计划引用接缝永久保留；被取代轮次的训练过程 RAW/逐步事件/中间 checkpoint 经逐目录清单批准与退役登记后停止保留。首批已于 2026-11-18 执行：16 个被取代目录（含 5 个嵌套 recovery/resume 训练目录）退役训练过程文件 5,039,555 个、逻辑 47.60GB，7,503 个保留文件（3.63GB）全量重验字节一致，发布源权重绑定复核通过；登记与逐目录退役标记在 `model/reviews/training-raw-retirement-20261118-v1/`，清单见 `docs/training-raw-retirement-plan-2026-11-18.md`。退役轮次的完整重放输入缺失须如实登记，历史判决、旧失败与原分母原样保留。2026-11-04 已退役四族逐步 checkpoint；逐轮叙事与证据索引见 `docs/archive/whitepaper-native-precision-history.md`（C 节）。

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
7. 图库/本地收录→AI/AR及AI→本地图库已实现，不再列为待实现链路；剩余缺口是编辑器成品（纹理贴合结果）共享与服务端持久项目协议，见§4.3—§4.5。

8. 历史诊断原始捕获可用性：§10所列四组已退役捕获的原始`.bin`已按授权移除，原报告继续保留历史结果，依赖这些文件的完整重放及诊断页原始张量读取已失去对应输入。后续读取先检查目录内退役登记；当前模型质量结论、发布状态和暂停恢复资料保持。

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
- 原§8.9逐版本实验叙事与脚本登记、§3状态表前的逐版本叙事、§11.1阻塞项叙事、§4.5的AR版本叙事，整体迁至 `docs/archive/whitepaper-native-precision-history.md`（2026-11-08 v1.2.280）；§3每个模块只登记一行当前状态，逐版本叙事一律写入当日 dev-log；
- 其他历史文档中形如「白皮书§12.3xx」「§13 v1.1.xxx」的引用均指上述归档文件，正文不再维护这些编号；证据细节以归档与机器可读报告为准；
- 本白皮书只登记当前接口、状态与仍在生效的合同；后续新增模块按上述模板登记，实验迭代过程记录进当日 dev-log 与相关进度文档，不写入本节。

## 13. 版本与变更记录

变更记录自 v1.2.0 起并入按天开发日志 `dev-log/YYYY-MM-DD.md`：白皮书发生实质变更（接口、状态、配置、数据或模型契约）的当天，在当日日志中以「白皮书 v1.2.x」标记简要记录变更内容与影响范围，不再逐任务登记、不设独立变更文档；无实质变更的任务不产生版本标记。v1.0.0—v1.1.995 的逐条历史记录完整保存在 `docs/archive/whitepaper-changelog-archive.md`。

- 白皮书顶部「文档版本」在每次实质变更时顺延，并与当日 dev-log 中的版本标记一致；
- 纯实验迭代、审核批次、流程性提交推送等记录到当日 dev-log 与相关进度文档，不进入白皮书、不顺延版本。
