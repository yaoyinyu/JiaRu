# 个性化美甲分析推荐 · 公开资料汇编

> 收集日期：2026-10-19。用途：为 JiaRu「根据甲型、手型、皮肤质量、应用场景/个人身份进行个性化美甲分析推荐」功能提供竞品、学术、领域知识、技术方法与市场依据。
> 整理纪律：只增不改写；同事实多来源保留最高可信度一条、其余在来源清单标「佐证」；可信度标注 `[同行评审]`/`[数据集官方]`/`[厂商]`/`[行业媒体]`/`[通用媒体]`/`[低可信·SEO/营销向]`；每条附「对本功能可用性」判断（**可用** / 需训练不可用 / 仅背景）。
> 本文档不进入技术白皮书正文、不顺延白皮书版本号（AGENTS.md 外部调研收录边界）；功能落地轮在白皮书 §4.x「关联文档」以一行指向本文档。

---

## 1. 竞品矩阵

### 1.1 B2B 平台级玩家

#### Perfect Corp 玩美移动（YouCam Nails / 玩美彩妆「AI 精灵」/ 穿戴甲试戴 SDK）[厂商]

行业事实标准，四条产品线覆盖本功能全部四个输入维度 [S1][S2][S3][S4][S5][S6]：

- **YouCam Nails**（C 端 App）：AgileHand® 技术 = 手部检测 + 指尖/甲面分割 + 实时渲染；jitter 控制保证手部移动时甲面贴合不漂移；数千色号 × 4 种 finish（cream/matte/jelly/sheer）+ 图案/模板/贴纸/珠宝；**可调整甲型**；设计可保存分享给美甲师；官方称全肤色平滑体验。
- **玩美彩妆「AI 精灵」**（C 端）：上传手部照片 + 文字指令 → 合成美甲效果；官方博客明确列举能力：**分析甲型、判断适合风格、分析手部肤色后推荐「显白」款式**；同一账号还有个人色彩分析（找最显白色系）、肤质诊断、脸型分析；可同时侦测多人手指；生成约 10 秒。
- **穿戴甲试戴技术**（B2B SDK/API）：手部检测（轮廓+指关节）→ 指尖分割（支持不同长度、弧度、款式在各手型上保持自然比例）→ 实时渲染（镜面/珠光/哑光质感）；**肤色适配与色彩校正算法**按肤色色温自动优化对比；可嵌入品牌官网/App/淘宝天猫京东/微信小程序，也可部署线下门店屏；官方明确建议**试戴行为数据回流 CRM 与商品分析，形成用户画像与款式偏好库，实现「试戴—推荐—下单」闭环**。
- 市场佐证：Perfect Corp 全球洞察报告称使用 AR 试戴工具的美妆消费者购买/预约信心为普通用户 **2.5 倍** [S7]。

对本功能：**可用**。证明「分割→肤色/甲型分析→场合推荐→试戴→数据闭环」的完整商业路径已被验证；JiaRu 差异化空间在其本地处理与原分辨率甲面审核纪律。

#### ModiFace（L'Oréal 2018 年收购）[厂商]

- **Nail Virtual Try-On**：指甲颜色、finish、 nail art 的 AR 试戴，SDK 或可嵌入 miniprogram [S8]。
- **Skin Analysis**：基于 10,000+ 专家标注图像训练，识别 **20+ 临床皮肤体征、15 种皮肤问题**，官方称准确率接近皮肤科医生 [S8][S9]。
- **Face Analysis / Foundation Finder / Color Match / Live Scan**：脸型识别、粉底色号匹配 [S8]。
- 规模：1B+ 试戴会话、50+ 注册专利、300+ 科学论文；官方宣布 2026 年夏将在 ChatGPT 内提供 Virtual Try-On [S8][S9][S10]。

对本功能：**可用**（作为「多因子分析→产品推荐」在美妆领域成立的最强证据：Face Analysis + Skin Analysis + Foundation Finder 的组合即本功能的脸部版先例）；指甲维度 ModiFace 只有试戴不做推荐，恰是 JiaRu 可做深的缝隙。

#### 美图 MeituGenius（美图公司）[厂商]

- AR 试妆/试戴 SDK：2.7ms 完成人脸检测、118 关键点；MT 分割支撑实时试妆与饰品试戴；支持口红/粉底/腮红/眉/眼影/眼线/睫毛 + 墨镜/耳环/隐形眼镜 [S11]。
- 覆盖小程序/PC/H5/App 四端；合作品牌含 MAKE UP FOR EVER、Sephora、Givenchy、TOM FORD、Lancôme、L'Oréal、Estee Lauder、Clarins、Shiseido、Watsons、DFS、MyGlamm [S11]。
- 美图 AI 开放平台另有图像分割/增强/生成能力与皮肤病变分析竞赛成绩（MICCAI-ISIC 2018 冠军）[S12]。

对本功能：**仅背景**（指甲非其产品重点；证明国内 B2B 试戴 SDK 生态存在，可作潜在合作/竞合对象）。

### 1.2 C 端 App 矩阵

| 产品 | 甲型分析 | 手型分析 | 肤色/底调 | 指甲健康 | 场合/身份 | 可解释性 | 技术路线 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **CutieCure** [厂商][S13][S14] | ✅ 甲床形状 | ✅ 手部风格识别 | ✅ 肤色深浅 + 暖/冷/中底色 | ✅ 0-100 健康评分（干燥/脆弱/变色/条纹/剥落，分严重级+护理计划+进度跟踪） | ✅ 风格偏好（简约/奢华/可爱）+ 场合（办公/派对/婚礼/约会/度假） | ✅ 每条推荐附「为什么适合」+ 色系/甲型/设计描述 | AI 分析 + 虚拟试戴 |
| **Cutie Nails** (iOS) [厂商][S15] | ✅ 方/圆/杏仁/保持原样 | —（按手在照片中的实际形态贴合） | ✅ 读照片底色，从 **408 个真实在售色号**（20 品牌 36 产品）推荐并文字解释（暖度、长度、光线） | — | ✅ 场合隐含于风格选择 | ✅ 解释为什么这个色适合 | 照片分析 + 试戴；照片仅本地存储 |
| **Glazii**（原 Nails AI）[厂商][S16] | ✅ 21 种甲型试戴 | ✅ Hand Analysis | ✅ 肤色匹配 | ✅ 健康评分 + 甲上皮状态 | ✅ Match My Outfit（穿搭照→3 个 Look）/ Match My Mood（自拍→按情绪） | ✅ 建议+技巧 | AI 生成 + 试戴 + 产品扫描（成分/安全性） |
| **Nailtist**（中国·长沙蜜獾，2025 智汇潇湘 AI 大赛）[行业媒体][S17][S18] | —（上传甲片图试戴） | ✅ LLM 美学顾问依据手型、肤色个性化推荐 | ✅ 肤色 | — | ✅ 风格 |  Hybrid-AI 混合渲染（特征提取+自适应曲面映射+神经光影重绘）；**沉淀「手型-甲型」匹配数据与审美画像作为核心数据资产**；CPS+API 商业模式 | 生成式 AI + LLM |
| **NailDesignsLab / nail-designs.ai** [厂商][S19][S20][S21] | ✅ Shape Finder（按生活方式与手指类型） | ✅ 手指长度 | ✅ Skin Tone Detector（传照测肤色→推荐） | — | ✅ 场合/季节/心情/Outfit Match | 部分 | AI 工具站；声称 14 项解剖因素（甲床形状/指长/肤色底调） |
| **Nailstry**（美国，2018 创立）[行业媒体][S22][S23][S24][S25] | ✅ 按 shape/length/finish 定制 | ✅ **CV 测每指甲宽与曲率**定做穿戴甲尺码（专利在申） | — | — | — | — | CV 测量 + 300+ 设计师 marketplace；B2B 可授权 |
| **NailedBy** [行业媒体][S26] | — | — | ✅ 肤色+整体 look 分析→推荐色 | — | — | ✅ 色彩理论助手定位 | $9.99/月订阅 |
| **Facetune** [厂商][S27] | ✅ 全甲型（椭圆/方/杏仁/尖头/coffin） | ✅ 宣称考虑手型 | ✅ 肤色+光线感知 | ✅ 修图级（修补磕损/甲上皮） | ✅ 特殊场合（婚礼/活动/社媒） | — | AI 检测 + 生成 |
| **美甲帮**（中国·杭州摩友）[厂商][S28] | — | — | — | — | ✅ 首页按浏览习惯智能推荐当季趋势 | — | 内容社区+门店预约+AI 试甲（自己的照片预览灵感款式）+CPMA 认证体系 | 内容推荐为主，非身体特征个性化 |
| **BeautyPlus / 美图秀秀** [行业媒体][S26][S29] | ✅ 自动手部检测套用图案 | — | — | — | ✅ 心情/场合模板库 | — | 约 300 款模板，3-5s/张 |
| **Wanna Nails / OPI Virtual Studio / Sally Hansen（AgileHand web AR）** [行业媒体][S7] | ✅ | — | ✅ 不同光线条件下呈现 | — | — | — | 实时 AR；OPI 强在色号与门店库存精确对应；Sally Hansen 免下载 |

**矩阵结论**：
1. 「甲型+手型+肤色+场合」四维分析推荐在 C 端已有多个产品落地（CutieCure 最完整），但**几乎全部把分析放在云端**，本地处理是明显空位（Cutie Nails 是少数强调照片仅存本地的）。
2. 可解释性（「为什么适合」）已成为头部产品标配而非差异点——JiaRu 必须做到，且要更实（基于测得数据而非固定文案）。
3. 「手型-甲型」匹配数据被 Nailtist 明确定义为行业数据资产——JiaRu 若走规则路线，规则表+黄金样例即是同类资产的可测试雏形。
4. Nailstry 证明「纯 CV 测量（甲宽/曲率）」即可支撑定制商业，不需生成式 AI。

---

## 2. 学术论文注释清单

### 2.1 直接相关（手型/甲型/肤色 → 美甲推荐）

1. **Gunasekera, H. (2025). Nail Shape and Color Recommendations Through Hand Shape Detection and Skin Color Extraction with Machine Learning. BEng Dissertation, Informatics Institute of Technology (斯里兰卡).** [同行评审·学位论文][S30]
   - 方法：手部关键点检测（15 点）→ 掌宽/掌高/指长测量 → 手型分类；按关键点划定区域提取肤色；结合**用户偏好与特殊场合输入**生成甲型+颜色推荐。
   - 指标：手型识别 90%、肤色识别 95%、手指关键点 94%、右手掌 83%、左手掌 4%（明显短板）、手部验证 86%。
   - 对本功能：**方法学模板**（v1 手型四分类的规则来源之一）；注意其掌宽/掌长口径依赖关键点，JiaRu 候选不含掌部 landmarks，v1 只能用甲面派生近似比例。

2. **Nail Type Recommendation using Deep Learning Models. IEEE, 2024.** [同行评审][S31]
   - 方法：2050 张标注图；按**掌长、掌宽、中指长**分手型；每种手型推荐 7 种甲型中的 2 种；比较 VGG16/LeNet-5/AlexNet/GoogLeNet/ResNet/DenseNet/MobileNet，VGG16 最佳。
   - 对本功能：**需训练不可用**（v1 不训练），但其「三维测量→手型→甲型推荐」的映射结构与 v1 规则引擎同构，可作为规则表交叉验证来源。

3. **Nerida, P. J. M. 等 (2024). AI Nail Art Customization: Enhancing User Experience Through Skin Tone and Nail Disease Detection Using Self-Supervised Learning. IEEE ICICyTA 2024 (巴厘岛). DOI 10.1109/ICICYTA64807.2024.10913297.** [同行评审][S32]
   - 方法：移动 App；肤色检测 + 自监督学习（SSL）指甲健康分析（内置指甲疾病检测+医疗建议）→ 个性化美甲推荐。
   - 指标：ISO 25010 评估（功能 3.34/性能 3.38/兼容 3.63/可靠 3.29/易用 3.47）；SSL 整体准确率 86.5%。
   - 对本功能：**需训练不可用**（SSL 疾病检测明确排除）；「肤色→推荐」主链路与 ISO 25010 评估框架可参考。

4. **Khidirbekova, M. (2025). AI as a Nail Technician's Assistant: Personalized Design and Color Selection based on the Client's Skin Tone and Style. Universal Library of Innovative Research and Studies, 02(03).** [同行评审·开放获取][S33]
   - 方法：多因子 AI 助手 = 视觉分析 + NLP + 预测分析 + 安全材料数据库；输入含**肤色与底调色板、风格偏好、过敏史、甲板状况**；输出设计与配色建议。
   - 关键论断（对 v1 有直接指导）：①多数 AI 研究只做视觉个性化，很少整合材料化学兼容性与安全性（HEMA 接触性皮炎文献）；②文化差异对色彩感知的影响、自动化肤色分析的伦理风险均未被充分研究；③CV 系统可能复刻或放大皮肤图像评估中的社会偏见（引 Hanley 等），需多样化数据集验证+偏见缓解。
   - 对本功能：**可用**（过敏史/甲板状况进入问卷设计的依据；非医疗声明与偏见注意事项的依据）。

### 2.2 肤色测量与公平性（ITA° 主线）

5. **Chardon, A. 等 (1991). Skin color and erythema（ITA° 原始文献，经 [S38][S39] 转引）。** [同行评审·转引] ITA° = arctan((L*−50)/b*) × 180/π，由 CIELAB 均值计算，是客观肤色测量的 pivotal 指标。
6. **Ulrich, P., Zink, A., Biedermann, T., Sitaru, C. (2025). Beyond Fitzpatrick: automated AI-based skin tone analysis in dermatological patients. npj Digital Medicine, 8:378.** [同行评审][S38]
   - 用 DensePose/OpenFace 定位皮肤区域 → CIELAB → ITA° → 映射 Fitzpatrick 与 **Monk 十级肤色**；与 Monk 分类高度一致、与 Fitzpatrick 一致性较低。
   - 对本功能：**可用**（v1 色彩科学模块 ITA°/Monk 近似的直接方法来源；注意 Monk 映射在其受控条件下成立）。
7. **Addressing Bias and Data Scarcity in AI-Based Skin Disease Diagnosis with Non-Dermoscopic Images. Aequitas Project, 2025.** [同行评审·项目论文][S39]
   - 改进 ITA°：先用分割 mask 排除病变区域再计算（病变皮肤更暗更红会污染基线）；用 GMM 六分量把 ITA° 分布分入六档而非套用皮肤镜数据集固定阈值；指出阴影与差光照会系统性压低 ITA°（深色图像无论真实肤色都被分到低 ITA°）。
   - 对本功能：**可用**（非受控手机拍照下 ITA° 偏差的警示与质量门设计依据；v1 不做 GMM，但「中位数聚合+质量门+用户自评覆盖」即其思想的规则化简化）。
8. **Monk Skin Tone Scale（skintone.google，十级开源肤色标度）。** [数据集官方][S40，经 S38 转引] 为克服 Fitzpatrick 偏向浅肤色的系统偏见而建；Google 开源。
9. **Hanley, M. 等（经 [S33] 转引）**：自动化 CV 在皮肤图像描述与评估中会复刻/放大社会偏见，需严格多样化验证与偏见缓解机制。

### 2.3 指甲健康/疾病检测（v1 明确不做疾病分类，仅登记边界）

10. **Han, S. S. 等 (2018). Deep neural networks show an equivalent and often superior performance to dermatologists in onychomycosis diagnosis. PLOS ONE, 13(1): e0191493.** [同行评审][S34]
    - R-CNN 先从图像分割指甲（构建 49,567 张训练图）→ ResNet-152 + VGG-19 集成分类甲癣；多中心验证 sensitivity/specificity/AUC 最高 96.0/94.7/0.98；Youden 指数显著高于 42 位皮肤科医生（p=0.01）。
    - 对本功能：**需训练不可用**（医疗分类器明确排除）；价值在于证明「指甲区域分割」是可规模化的独立任务，且公开了 figshare A–E 数据集 [S35]。
11. **Deep Convolutional Neural Networks for Onychomycosis Detection. arXiv:2106.16139.** [同行评审·预印本][S36] OnI/NnI 数据集：160 真菌显微图 + 297 角质显微图 → 9,215 个 500×500 patch；InceptionV3/VGG16。
12. **Low resource federated learning for classification of nail disease. Scientific Reports, 2026.** [同行评审][S37] Kaggle Nail Disease Classification（~3,500 图、5 类：甲癣/甲沟炎/指甲银屑病/甲营养不良/健康）+ ResNet152V2/DenseNet201/MobileNetV2/InceptionResNetV2 联邦学习。

### 2.4 手部分割/测量与推荐系统方法

13. **A review on deep learning for vision-based hand detection, hand segmentation and hand gesture recognition in human–robot interaction. 2025.** [同行评审][S41] 手部分割数据集系统综述：EgoHands（4,800 像素级帧、15,000+ 手）、Ego2Hands（2,000 帧，手间遮挡）、Obman（147,000 合成图带 mask+关键点）、HandSeg（150,000 RGB-D）、COCO-Hands（26,499 图中 45,671 手框）、COCO-WholeBody/Halpe-FullBody（42 手部关键点）、H2O（571,645 RGB-D）。
14. **AI-Powered Ring Size Estimation for a Realistic Virtual Try On. Zenodo, 2025. DOI 10.5281/zenodo.15479899.** [同行评审·会议/预印本][S42] CNN + MediaPipe 21 点手部 landmark 实时跟踪；关键点欧氏距离 → 戒指尺码校准；OpenCV Haar 检测 + alpha 合成 AR。对本功能：**可用**（「21 点测尺寸」方法先例；与 JiaRu 已有 MediaPipe 管线同源）。
15. **Wulandari, E. & Baizal, Z. K. A. (2025). Belle: LLM-Based Conversational Recommender Systems for Beauty Products. ICADEIS 2025.** [同行评审][S43] 微调 GPT-4o（53,511 tokens/3 epochs）做美妆对话推荐；BERTScore F1 0.8921、cosine 0.7227、Distinct@1 0.7089→0.9081。对本功能：**仅背景**（v1 不引入 LLM；证明对话式推荐学术可行）。
16. **Sistem Rekomendasi Layanan Nails dan Lashes Menggunakan Item-Based Collaborative Filtering. JESA（印尼）.** [同行评审][S44] 基于项目协同过滤+余弦相似度的美甲/美睫服务推荐；功能测试 95% 成功、SUS 81.54。对本功能：**仅背景**（v1 无用户行为数据，CF 路线不可用；登记为后续数据积累后的可选路线）。

---

## 3. 领域知识库（v1 规则引擎的规则来源）

### 3.1 甲型 × 手型匹配表 [通用媒体·多源一致][S47][S48][S49][S50][S51][S52]

七个经典甲型：round（圆）、squoval（方圆）、square（方）、oval（椭圆）、almond（杏仁）、coffin（棺形/芭蕾形）、stiletto（尖头）。

| 手/甲床类型 | 推荐甲型 | 避免 | 依据 |
| --- | --- | --- | --- |
| 短手指 | oval、almond、coffin（带长度） | square、短长度 round | 锥形收窄拉长视觉 |
| 长手指 | square、coffin、squoval、stiletto | round（显短） | 直边加宽平衡纤细比例 |
| 宽甲床 | oval、almond、round | square、flare | 锥形收窄显瘦 |
| 窄甲床 | squoval、round、coffin | 过尖（显薄脆） | 方中带圆加宽 |
| 小手 | round、oval、almond | 过大甲型 | 保持比例 |
| 大手 | coffin、stiletto、squoval | 短圆（显更大） | 可承托夸张形 |
| 啃咬/极短甲 | round、squoval | almond/stiletto/coffin | 无需长度的基底 |
| 骨节明显手 | 方圆/方（避免过于圆润放大骨节）[S62] | oval | 线条修饰 |

强度与最短长度（耐久度排序，越靠后越需延长）[S51]：round（极强，指尖长度）> squoval（很强，短）> square（强，短）> oval（强，短）> almond（易裂，中）> coffin（易裂，长）> stiletto（最弱，长）。长度口径：游离缘测量——贴指尖 0–1mm / 短 2–4mm / 中 5–8mm / 长 8–15mm / 特长 13–15mm+（各源略有差异，取保守区间）。

**甲床-甲型镜映法则**：圆形甲上皮 → oval/almond 最自然；直形甲上皮 → square/squoval [S51]。

**生活方式覆盖规则** [S47][S51][S52]：体力劳动/手工作业 → round/squoval/oval 中长；办公键盘族 → almond/oval/coffin 中等（避免过长与尖角）；特殊场合 → stiletto/coffin/arrowhead 可夸张（临时性）；低维护 → round/squoval（长出最自然）。

### 3.2 底调（undertone）理论 [通用媒体·多源一致][S53][S54][S55][S56][S57][S58][S59][S60]

- 分类：**暖**（金/蜜桃/杏光泽，易晒黑）、**冷**（粉/蓝/灰光泽，易晒红）、**中性**（平衡）、**橄榄**（金调灰绿，多见于小麦色皮肤）[S54]。
- 自判方法：静脉测试（蓝紫=冷/绿橄榄=暖/混合=中）、首饰测试（银=冷/金=暖/均可=中）、日照反应（易红=冷/易黑=暖）、白/奶油布对比 [S54][S59][S60]。
- 配色方向：
  - 暖调 → 珊瑚、砖红、橘调红、蜜桃、陶土、芥末、金、橄榄、暖棕、奶油/沙色裸、铜/玫瑰金金属 [S59][S60][S53]；
  - 冷调 → 蓝调红、樱桃、蔓越莓、莓果、 Fuchsia、薰衣草、梅、长春花蓝、海军蓝、祖母绿、青绿、冷灰/米灰、银金属 [S59][S60][S53]；
  - 中性 → 正红、平衡粉米裸、莓/梅、雾蓝、鼠尾草绿 [S60]；
  - 橄榄 → 大地色、番茄红、浓郁宝石色（惨白 pastel 易显平）[S57]。
- 肤色深浅分层（与底调正交）[S57][S58][S60]：白皙 → 柔粉、蓝调红、丁香、淡紫、蜜桃裸、透明奶白；中度/橄榄 → 珊瑚、 mauve、勃艮第、大地色、灰蓝/雾霾蓝/薰衣草（ trends 亦可）；深肤 → Fuchsia、祖母绿、金属金、钴蓝、霓虹亮色、纯白、pastel、巧克力裸。**裸色甲油定律：比肤色略深或略亮，避免与肤色同明度显脏** [S57]。

### 3.3 四季个人色彩 → 甲色推荐 [通用媒体·理论体系][S53][S55][S56]

Caygill 1942 创立的四季色彩分析，按**冷暖 × 明度/对比度**分型 [S53]：

| 季型 | 特征 | 甲色推荐 | 整体规避 |
| --- | --- | --- | --- |
| 春（暖+明亮） | 金黄/蜜桃底调、浅金/红棕发、亮浅瞳 | 奶白、蜜桃粉、珊瑚、明黄、薄荷、透明果冻色 | 暗沉灰调 |
| 夏（冷+柔和） | 粉/蓝底调、灰棕发、浅灰/蓝绿瞳 | 裸粉、冰透、灰粉、雾霾蓝、豆沙紫、薄荷 | 荧光、土黄 |
| 秋（暖+浓郁） | 金/桃/橄榄底调、红/暖棕发、深绿/榛瞳 | 陶土、砖红、焦糖、芥末、墨绿、深咖 | 荧光、冷粉 |
| 冬（冷+高对比） | 瓷白或深肤冷调、黑/深棕发、强对比瞳色 | 正红、宝蓝、墨绿、纯白、酒红、黑 | 发灰的粉、浑浊橙 |

中文源同构表述（黄皮显白：正红/酒红/焦糖裸/奶白；冷白皮大部分可驾驭）[S62][S63]。

### 3.4 场合/身份规则表 [行业媒体·中文源][S61][S62][S63][S64][S65][S66]

| 场景 | 甲型/长度 | 色系 | 备注 |
| --- | --- | --- | --- |
| 职场/通勤 | 短方圆、短至中等 | 裸色、淡粉、微妙金属、磨砂纯色、简约线条 | 通勤风订单占比约 42% [S75]；不耽误键盘/快递 |
| 派对 | 可夸张（stiletto/coffin） | 大胆色、闪粉、醒目艺术 | 临时性场景可突破日常规则 |
| 婚礼（当天） | 中长椭圆/杏仁 | 优雅裸粉、法式白边、低饱和细闪 | 不抢婚纱与婚戒；抹胸婚纱→裸色焦点在锁骨 |
| 婚礼（pre-wedding/拍婚纱照） | 中长 | 奶白、裸粉、奶茶、微法式+珍珠 chrome | 白纱百搭 |
| 日常（婚后通勤） | 短方圆 | 纯色磨砂、简约线条、小面积亮片 | 「婚礼上镜+日常实用+不伤指甲」三原则 [S63] |
| 约会 | 中长 | 浪漫红、深浆果、纯欲水红 | Y2K/蝴蝶结=闺蜜聚会减龄 |
| 度假 | 中长 | 明亮珊瑚、热带色调、有趣图案 | — |
| 短甲/甲床短 | 圆形、方圆形 | 微法式、奶白果冻、裸粉渐变、淡猫眼、小珍珠 | 不必为场合勉强驳长 [S65] |
| 指甲薄软 | 先加固（建构胶/水晶甲）再谈款式 | — | 甲面状况影响做工 [S63] |
| 新娘时间线 | 婚礼前 2–3 天做甲（或提前 1 周试款） | — | 留适应时间 [S62][S63] |

长度光学规则：**深色显短、浅裸色拉长**；较短指甲选浅裸色，拍照显手长 [S14][S47]。

拍照分享动机：约 60% 消费者为拍照分享而做美甲 [S75]——「上镜/显白」是强场景标签，建议问卷单列。

---

## 4. 技术方法参考

| 方法 | 内容 | v1 是否采用 |
| --- | --- | --- |
| **MediaPipe Hands 21 点测尺寸** [同行评审][S42][S67][S68] | HandLandmarker（2 手、GPU delegate、VIDEO 模式）；landmark 0=腕、5/17=掌指关节（手镯尺寸动态计算）、16=环指指尖（戒指）；归一化坐标→canvas 像素+镜像；关键点欧氏距离→尺码校准 | **采用**（JiaRu 已有同款管线，nail-geometry.ts 已算甲面几何；新功能只读消费） |
| **AR 指甲试戴技术栈** [通用媒体·技术向][S69] | ARKit/ARCore 环境跟踪 + MediaPipe/ManoMotion 指尖检测；指尖 landmark + ML 边缘检测勾甲面轮廓；反抖动；gloss shader；环境光自适应 | **部分采用**（分析链路用；渲染仍归 ar-tryon，本功能只出站桥接） |
| **ITA° 肤色测量** [同行评审][S38][S39] | CIELAB→ITA°→Fitzpatrick/Monk 映射；病变区遮罩后计算；GMM 自适应分档；阴影光照偏差警示 | **采用**（color-science.ts；质量门+自评覆盖替代 GMM） |
| **LLM 对话式推荐** [同行评审][S43]；美妆 AI Agent 格局 [行业媒体][S71][S72] | Belle：微调 GPT-4o 做美妆对话推荐；2025-2026 欧莱雅 Beauty Genius（110 万+ 次对话）/Noli（100 万+ 面部扫描→Beauty Profile 匹配配方）、资生堂 ELIXIR（AI 测肤+LLM 咨询约 56 万人次）、爱茉莉 AMORE CHAT/Beauty Concierge（整合皮肤、肤色、头皮与**个人色彩诊断**的 AI Agent）、Sephora/Ulta 接入 ChatGPT；对话式商务：AI 记忆用户档案（肤质/肤色/敏感/偏好 finish），对话数据回流 CRM [S70] | **不采用**（v1 无 LLM；登记为后续可选：Nailtist 已用 LLM 做美学顾问 [S17]） |
| **CV 测量定制** [行业媒体][S22][S24] | Nailstry：摄像头测每指甲宽与曲率→press-on 尺码；专利在申；B2B 可授权 | **不采用**（v1 不做电商尺码；其「纯测量即可商用」结论支持 v1 规则路线可行性） |
| **GAN/U-Net 款式迁移** [同行评审·转引][S33] | Miah 等：把艺术图案应用到指甲图像并保留明暗纹理 | 不采用（生成方向与 v1 无关） |
| **虚拟试戴 inverse-graphics** [同行评审·转引][S33] | Kips 等：深逆图形+可微渲染，单例生成逼真预览 | 不采用 |
| **Item-based CF 服务推荐** [同行评审][S44] | 美甲店服务协同过滤 | 不采用（无行为数据；后续可选） |

---

## 5. 市场数据（均为第三方口径，注明来源与年份；冲突处并列）

| 指标 | 数值 | 口径/来源 |
| --- | --- | --- |
| 中国美甲行业市场规模 | 2020 年 867 亿元 → 2024 年 2,058 亿元 → 2025 年 2,371.9–2,500 亿元 → 2030 年破 3,000–5,000 亿元（CAGR 约 15%） | 中国报告大厅/艾媒咨询/中研普华 [S75][S76][S77]（机构口径有差异） |
| 穿戴甲（press-on） | 2019 年 4 亿元 → 2024 年近 100 亿元 → 2026 年预计约 230 亿元 → 2030 年破 400–641 亿元（十年约 160 倍） | 义乌指数/中国报告大厅 [S76][S77] |
| 穿戴甲产业带 | 东海县占全国产量 70%+，2025 年销售额 150 亿元 | 江苏省政府公开数据/义乌指数 [S77] |
| 人群结构 | Z 世代消费占比 >70%（2030 预计 80%）；人均年消费 2,200 元、年 4–6 次、客单价 300–500 元、复购率 >70%；女性占 95%；男性市场增速 30%（2025 约 160 亿元） | 艾媒咨询/中国报告大厅 [S75][S76] |
| 动机结构 | 60% 消费者为拍照分享选择美甲；68% 认为 IP 联名是「文化认同」；IP 联名订单 2023 +120%；国潮元素 2025 预计 +85% | 中国报告大厅 [S75] |
| 数字化渗透 | AR 试甲数字化工具渗透率约 50%（2025）；智能美甲设备渗透率 25%（单店效率 +30%）；线上订单占比 47% | 三个皮匠报告汇总 [S76][S77] |
| 线下 AR 转化 | 线下体验店通过 AR 试戴+即时打印将转化率提升至 34% | ZVZO 消费观察 [S78]（厂商报告，谨慎引用） |
| 全球指甲护理产品 | 2025 年 251 亿美元 → 2032 年 372 亿美元（CAGR 5.8%）；指甲油占 55.3%；延长甲为最快细分（CAGR 7.2% → 42 亿美元）；北美占 27.5%，亚太最快 | Persistence Market Research [S79] |
| 全球智能美甲 | 2025 年 47.2 亿美元（+38.6%）→ 2030 年 182.7 亿美元；62.4% 消费者以「个性化图案快速生成」为首要动机 | ZVZO [S78]（厂商报告，谨慎引用） |
| AR 试戴效能 | 使用 AR 试戴的消费者购买/预约信心 2.5 倍 | Perfect Corp 全球洞察 [S7]（厂商报告） |

**对功能定位的含义**：个性化推荐的需求侧证据充分（Z 世代主导、拍照分享动机 60%、穿戴甲高增长降低试错成本诉求强）；供给侧（C 端 App）已有多家，但「基于真实甲面测量的本地分析」仍空位。

---

## 6. 公开数据集清单（登记备查；v1 不训练、不使用）

| 数据集 | 规模 | 标注 | 用途判断 |
| --- | --- | --- | --- |
| **11k Hands**（Afifi）[S46] | 11,076 张手部图（1600×1200），190 名 18–75 岁受试者 | 元数据含身份/性别/年龄/**肤色**/利手/配件 | 肤色多样性参考；如需手型/肤色模型可作预训练来源 |
| **EgoHands** [同行评审·数据集官方][S45] | 4,800 像素级分割帧（48 段第一视角视频） | 左右手/两人四方类；CC BY 4.0 | 手部分割参考（第一视角，与甲拍场景不完全一致） |
| Ego2Hands [S41] | 2,000 帧 | 手间遮挡分割 | 同上 |
| Obman [S41] | 147,000 合成图 | mask+关键点 | 合成数据路线参考 |
| HandSeg [S41] | 150,000 RGB-D 帧 | 彩手套半自动标注 | 光照/遮挡多样性有限 |
| COCO-Hands / COCO-WholeBody / Halpe-FullBody [S41] | 45,671 手框 / 每图 42 手部关键点 | 框/关键点 | 手部关键点预训练来源 |
| H2O [S41] | 571,645 RGB-D 帧 | 3D 双手+物体 | 3D 路线参考 |
| Han et al. 甲癣 figshare A–E（含 Virtual E 3,317 图 6 类）[S35] | 49,567 训练图 | 指甲分类 | 医疗方向，v1 明确不用 |
| Kaggle Nail Disease Classification [S37] | ~3,500 图 5 类 | 指甲疾病 | 同上 |
| OnI/NnI 甲癣显微 patch [S36] | 9,215 patch（500×500） | 显微真菌 | 同上 |
| Monk Skin Tone Scale [S40] | 十级色板 | 肤色标度 | 色号筛选沟通用途（非测量标准） |

---

## 7. 来源 URL 全清单

**竞品与厂商**
- [S1] Perfect Corp 玩美移动《AI 穿戴甲试戴技术》https://cn.perfectcorp.com/zh-cn/business/blog/general/Enhancing-Wearable-Armor-Experience
- [S2] Perfect Corp《2025 法式美甲 33 款+试戴 App（玩美彩妆 AI 精灵）》https://www.perfectcorp.com/zh-tw/consumer/blog/nail/20-nails-design
- [S3] Perfect Corp《2025 圣诞美甲（AI 精灵分析甲型/肤色）》https://cn.perfectcorp.com/zh-tw/consumer/blog/nail/christmas-nail-design
- [S4] AiThority《Latest AI Developments Bring Glamour to the YouCam Nails App》https://aithority.com/machine-learning/latest-ai-developments-bring-glamour-to-the-youcam-nails-app-powering-the-market-leading-live-virtual-try-on-manicure-experience/
- [S5] Happi《Perfect Corp. Sees Success with Revamped Nail Art App》https://www.happi.com/contents/view_breaking-news/2022-09-29/perfect-corp-sees-success-with-revamped-nail-art-app/
- [S6] Professional Beauty AU《Digital Innovations Tapping Into the Nail Space》https://www.professionalbeauty.com.au/?p=93786
- [S7] QuarkBooker《The Best Digital Nail Polish Apps》https://www.quarkbooker.com/blog/digital-nail-polish-apps
- [S8] ModiFace 官网 https://modiface.com/
- [S9] INVIAI《AI in the Beauty Industry》https://inviai.com/en/ai-in-the-beauty-industry
- [S10] L'Oréal《Discovering ModiFace》https://www.loreal.com/en/italy/pages/group/our-purpose-it/discovering-modiface-it/
- [S11] 美图《Meitu launches MeituGenius Online》https://www.meitu.com/hk/media/287
- [S12] 美图 AI 开放平台 https://ai.meitu.com/
- [S13] CutieCure 中文官网 https://www.cutiecure.app/zh/
- [S14] CutieCure《适合你肤色的美甲颜色》https://www.cutiecure.app/zh/blog/personalized-nail-art-skin-tone
- [S15] Cutie Nails https://cutienails.app/
- [S16] Glazii（App Store）https://apps.apple.com/bj/app/nails-ai-design-scan-try-on/id6745216296
- [S17] 智汇潇湘 2025「人工智能」创新大赛作品展示：Nailtist http://mp.weixin.qq.com/s?__biz=MzI2MzMzNzgxMQ==&mid=2247499076&idx=2&sn=c9a597cea2f3267ad81355ed2e46b4a1
- [S18] Nailtist 产品页 https://chuchuang.work/product/nailtist
- [S19] nail-designs.ai Tools http://www.nail-designs.ai/tools
- [S20] Dang.ai《AI Nail Designs - NailDesignsLab》https://dang.ai/tool/ai-nail-designs-naildesignslab-com
- [S21] NailDesignsLab《Nail Shapes Analysis》https://naildesignslab.com/nail-shapes-analysis
- [S22] Woman & Home《This new app will help you achieve the perfect press-on nails》https://www.womanandhome.com/us/life/news-entertainment/this-new-app-will-help-you-achieve-the-perfect-press-on-nails/
- [S23] Refresh Miami《Ditch the salon… Nailstry》https://refreshmiami.com/ditch-the-salon-this-holiday-season-instead-try-virtual-nails-with-nailstry/
- [S24] Dealroom《Nailstry》https://app.dealroom.co/companies/nailstry
- [S25] Canvas Rebel《Meet Aurelia Edwards》https://canvasrebel.com/meet-aurelia-edwards/
- [S26] BeautyPlus Academy《Top 8 Nail Design Apps for Virtual Try-On 2026》http://www.beautyplus.com/academy/nail-design-app
- [S27] Facetune《Best Virtual Nail Try-On & Nail Simulator Apps (2025)》https://www.facetuneapp.com/blog/best-virtual-nail-simulator-app
- [S28] 美甲帮官网 http://www.meijiabang.cn/ ；佐证：Mergeek https://mergeek.com/latest/eyVzpWBYg1lAvME7 ；PP3 https://m.pp3.cn/app/42163.html ；灵狐数据 https://foxdata.cn/app-marketing-analytics/683740908/as/CN/
- [S29] BeautyPlus《Virtual Nail Try On: How to Try 100+ AI Nails for Free?》http://www.beautyplus.com/academy/virtual-nail-try-on

**学术**
- [S30] Gunasekera (2025) IIT 学位论文库 http://dlib.iit.ac.lk/xmlui/handle/123456789/3261
- [S31] IEEE《Nail Type Recommendation using Deep Learning Models》https://ieeexplore.ieee.org/document/10710729
- [S32] Nerida et al. (2024) IEEE ICICyTA https://ieeexplore.ieee.org/document/10913297/similar
- [S33] Khidirbekova (2025) ULIRS https://www.ulopenaccess.com/ulpages/fulltextULIRS?PublishID=ULIRS20250203_006 （PDF：https://ulopenaccess.com/papers/ULIRS_V02I03/ULIRS20250203_006.pdf）
- [S34] Han et al. (2018) PLOS ONE https://dx.plos.org/10.1371/journal.pone.0191493
- [S35] Han Virtual E Dataset（figshare）https://figshare.com/articles/dataset/Virtual_E_Dataset/5513407
- [S36] arXiv:2106.16139《Deep Convolutional Neural Networks for Onychomycosis Detection》https://arxiv.org/html/2106.16139v3
- [S37] Scientific Reports (2026)《Low resource federated learning for classification of nail disease》https://www.nature.com/articles/s41598-026-36848-w
- [S38] Ulrich et al. (2025) npj Digital Medicine https://www.nature.com/articles/s41746-025-01770-4
- [S39] Aequitas Project (2025)《Addressing Bias and Data Scarcity…》https://www.aequitas-project.eu/wp-content/uploads/2025/12/paper8.pdf
- [S40] Monk Skin Tone Scale https://skintone.google （经 [S38] 转引核实）
- [S41] 《A review on deep learning for vision-based hand detection, hand segmentation and hand gesture recognition in HRI》https://www.sciencedirect.com/science/article/pii/S0736584525001644
- [S42] 《AI-Powered Ring Size Estimation for a Realistic Virtual Try On》https://dx.doi.org/10.5281/zenodo.15479899
- [S43] Belle: LLM-Based CRS for Beauty Products（ICADEIS 2025）https://plu.mx/plum/a/?doi=10.1109/icadeis65852.2025.10933248 ；佐证：https://openlibrary.telkomuniversity.ac.id/home/catalog/id/231553/
- [S44] JESA《Sistem Rekomendasi Layanan Nails dan Lashes…Item-Based CF》https://jesa.aks.or.id/jesa/article/view/95
- [S45] EgoHands（Roboflow Universe）https://universe.roboflow.com/holeno/hands-osrr0
- [S46] 常用公共数据集汇总（11k Hands 等）https://2048ai.net/68254168a5baf817cf4bff0f.html ；佐证：https://leezhao415.github.io/2021/12/12/

**领域知识（中英文）**
- [S47] NailBold《Nail Shapes Chart 2026》https://www.nailbold.com/nail-shapes-chart-the-complete-guide-for-2026/
- [S48] RatnaStyle《The Best Nail Shapes for Your Hand Type》https://www.ratnastyle.com/2025/06/the-best-nail-shapes-for-your-hand-type.html
- [S49] NabaStyle《Finding Your Perfect Nail Shape》https://www.nabastylenails.com/post/nail-shapes-gel-manicure
- [S50] GlowMag《How to Choose the Perfect Nail Shape for Your Hands》https://glowmag.co.za/?p=6948
- [S51] NeedleStyle《Nail Shape Chart & Finder》https://needlestyle.com/tools/nail-shape-finder
- [S52] Boudoir Nail Bar《Beyond the Polish: How to Choose the Right Nail Design in 2026》https://boudoirnailbar.com?p=3151/
- [S53] Manucurist《Choose Your Next Nail Colour With Colour Theory》http://www.manucurist.com/en/blogs/journal/quelles-couleurs-porter-ce-printemps-br-et-si-on-testait-la-colorimetrie
- [S54] U Rêve Paris《色彩诊断：不同肤色与四季型适合的指甲油颜色》https://ureve.paris/cn/blog/colour-recommendation-you-reve-paris
- [S55] 搜狐《甲色发色不好看？先判断你是春夏秋冬哪一皮》https://www.sohu.com/a/1010701197_121893291
- [S56] 伊的家《春夏秋冬四季色彩测试靠谱吗》https://www.yidejia.com/news/23408
- [S57] Insider Beauty《Best Nail Colors for Your Skin Tone》https://www.insiderbeauty.com/blog/best-nail-colors-for-your-skin-tone-1784095251739
- [S58] BTArtbox《What Color Should I Do My Nails Based on My Skin Tone?》https://btartboxnails.com/blogs/btartbox-official-guides/what-color-should-i-do-my-nails
- [S59] Makeup.com《How To Pick Nail Polish Colors for Your Skin Undertone》https://www.makeup.com/nails/nail-polish/how-to-pick-nail-polish-for-undertone
- [S60] ExpertsSay《Selecting the Nail Polish for Skin Tone》https://expertsay.blog/selecting-the-nail-polish-for-skin-tone/
- [S61] 东网问答《怎麼知道自己適合什麼顏色的指甲油》https://dongwangask.com/ask/1768162165861740
- [S62] 新浪《新娘甲定制推荐：手型决定甲型？3种手型4大场景全解析》https://www.sina.cn/news/article/comos_niupafi3788110.html
- [S63] 新浪《2026新娘美甲美睫怎么选？3个维度4种人群方案》https://www.sina.cn/news/article/comos_nisyqhi4770853.html
- [S64] 新浪《订美甲 2026全攻略：通勤婚甲一站式不踩坑》https://sina.cn/news/detail/5325578971645191.html
- [S65] GirlStyle《美甲款式全图鉴 16 款显白不过时》https://pretty.presslogic.com/article/752158
- [S66] 微信公众号《10 款绝美渐变美甲》http://mp.weixin.qq.com/s?__biz=Mzk3NTMzMTA1Mg==&mid=2247489921&idx=2&sn=f6f5dd6308a573aa73c1ff11e01f0c49

**技术方法**
- [S67] DeepWiki《MediaPipe Landmark Detection》https://deepwiki.com/sashankbanda/documentevol/4.2.1-mediapipe-landmark-detection
- [S68] Universal College of Engineering《Jewellery Tryon using AR》https://universalcollegeofengineering.edu.in/wp-content/uploads/2024/03/3.3.1-COMP-MERGED-70-76.pdf
- [S69] Zigpoll《How to Create… Virtual Try On Nail Polish Shades Using AR》https://www.zigpoll.com/content/how-can-i-create-a-mobile-app-feature-that-allows-customers-to-virtually-try-on-our-latest-nail-polish-shades-using-augmented-reality-technology
- [S70] Francesca Tabor《Conversational AI Commerce – Beauty & Cosmetics》https://www.francescatabor.com/articles/2025/10/25/conversational-ai-commerce-beauty-amp-cosmetics
- [S71] 绿翊《化妆品 AI Agent 大战：28 个对话式助手与购物智能体落地盘点》https://www.lv-1.cn/lvyi/article/635.html
- [S72] BeautyTech.jp《アモーレチャットなどが意味するアモーレパシフィックのホリスティック・ロンジェビティ》https://beautytech.jp/n/n4882ac795988
- [S73] ReelMind《Nail Art Tutorials: AI-Personalized Design Suggestions》https://reelmind.ai/blog/nail-art-tutorials-ai-personalized-design-suggestions
- [S74] Le Journal Catalan《I tried this virtual nail consultation…》https://www.le-journal-catalan.com/en/i-tried-this-virtual-nail-consultation-at-60-my-hands-look-7-years-younger-in-90-degree-summer-heat/ （低可信·SEO/营销向，仅作「虚拟美甲咨询」现象佐证）

**市场**
- [S75] 中国报告大厅《2025年美甲行业资讯与核心数据透视》https://www.chinabgao.com/finance/comments/77120.html
- [S76] 三个皮匠报告《美甲市场容量或变化趋势》https://www.sgpjbg.com.cn/searchtag/25810436.html
- [S77] 三个皮匠报告《2026年美甲行业前景分析》https://www.sgpjbg.com.cn/searchtag/25803509.html
- [S78] ZVZO《全球智能美甲行业发展与市场调查分析报告(2026)》https://www.zvzo.com/2358/view-166161-1.html （厂商报告）
- [S79] PR Newswire/Persistence Market Research《Nail Care Products Market to Reach US$37.2 Billion by 2032》https://www.prnewswire.co.uk/news-releases/nail-care-products-market-to-reach-us37-2-billion-by-2032-as-beauty-brands-compete-on-clean-formulations-digital-engagement-and-at-home-premiumization-302776307.html

---

## 8. 资料使用结论（对 v1 设计的直接输入）

1. **规则来源全部就位**：甲型×手型匹配表（§3.1）、底调配色（§3.2）、四季色彩（§3.3）、场合规则（§3.4）四张表可直接转 TS 常量规则，无需训练。
2. **肤色测量走 ITA°**：公式与 Monk 近似映射有同行评审来源 [S38]；非受控拍照偏差的缓解手段（中位数聚合/质量门/自评覆盖）有 [S39] 的依据。
3. **指甲健康只做启发式**：均匀度/高光/条纹三类观察，不做疾病分类——[S32][S34][S37] 均属需训练模型且涉医疗声明，明确排除；非医疗声明文案为硬约束。
4. **可解释性是标配不是差异点**：必须输出「为什么适合」；JiaRu 的差异在基于测得数据（ITA°/甲床长宽比）的动态解释，而非固定文案。
5. **本地处理是竞品空位**：矩阵中仅 Cutie Nails 强调照片仅本地 [S15]；JiaRu 项目原则本就是浏览器本地处理，应作为产品卖点明确宣传。
6. **手型口径降级已有依据**：Gunasekera/IEEE 的掌宽掌长口径依赖手部关键点 [S30][S31]，JiaRu v1 候选不含掌部 landmarks，用甲面派生近似比例并在 UI 注明近似——不假装精确。
