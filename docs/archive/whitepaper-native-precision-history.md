# 白皮书原生精度复验与状态叙事历史归档

> 归档说明（2026-11-08 v1.2.280）：本文件接收技术白皮书中不符合「仅保留最新口径数据与必要技术文档引用」标准的段落，含 §8.9 的逐版本实验叙事与脚本登记、§3 状态表前的逐版本叙事、§11.1 的阻塞项叙事、§4.5 的 AR 版本叙事。
> 原文逐字保留，未作改写；本文件只增不改写。历史文档中对「白皮书§8.9」「§4.5」等章节级引用仍指白皮书对应章节，章节内的历史细节见本文件。

## A. 原 §8.9 学得原尺寸候选的精度复验接口（全文）

### 8.9 学得原尺寸候选的精度复验接口

**v1.2.279固定32甲原像素轨迹。** 第128至256次曝光的轮内均值由0.746847升至0.774608，差+0.027762，31/32甲改善。原8甲+0.022228，新增24甲+0.029606。第1024步固定末态平均0.775480，严格联合25/32（原8甲8/8，新增17/24），7甲仅边界IoU低于0.75。 轮内观测分别跨508—511及1020—1023步，固定末态为1024步。已重放224份RAW与672条绑定事件。下一轮固定共同起点和预算，比较恒定0.001与退火至0.00025。

**v1.2.278固定32甲混批对照。** 以第62次权重、原损失和固定四个8甲批次对照。112对批内逐甲梯度中61对点积为负，原AdamW与投影AdamW的实际更新在32甲原损失上均无一阶反向。平均原2px Boundary IoU由初始0.589669升至0.602124和0.601935，投影相对差−0.000189，两组严格联合均0/32。关闭本版梯度投影。96份RAW、4份梯度矩阵、8份完整状态及304条事件已完成CPU重放。全634正式指标仍0/634，PRODUCT HOLD。

**v1.2.274第62次模型调整完成。** 原128轮81152输入/10240更新，264195逻辑事件、81152份RAW和321份状态独立重放通过。固定636候选终评及三基线配对已复算。匹配634/634、漏甲图0/100，Boundary IoU/F1均值0.582402/0.966976。相对第61次Boundary IoU提高0.022450，584甲改善、50甲下降、严重回归0，此前8项均改善。Boundary F1达标597/634，Boundary IoU达标0/634（最高0.747427），严格联合仍0/634。当前仅登记为训练域诊断，入口v51，PRODUCT HOLD。

**v1.2.275多尺度轮廓路线。** 冻结第62次100图634甲原像素诊断已重建636候选及全部原配对指标，并独立复算9个场景。整体质心平移和径向常数各0/634，理想修正局部33—1024谐波218/634，仍差321甲。理想修正1—8谐波或0—32合并均2/634。现有真值半径回代634/634，几何可达余量95甲。下一步用同一冻结快照，配对预检联合学习局部细节和低频形状，原2px及539门保持。 反事实使用训练域真值，现有实际联合仍0/634，PRODUCT HOLD。

**v1.2.276分频配对结论。** 第63次配对预检从第62次固定权重出发，原损失与分频组各256次更新、2048训练输入及16评估输入。两组原2px严格联合均8/8，平均Boundary IoU分别0.886997和0.873761。分频组8/8逐甲下降，平均差-0.013236，1甲触发严重回归（最大下降0.025129）。相对增益及零严重回归门未过，关闭本版分频损失分支。下一步沿用原损失，在更广的冻结训练样本上对照检验共享轮廓分支容量。全634正式训练域联合仍0/634，PRODUCT HOLD。

**v1.2.277角向容量配对结论。** 第64次在31张冻结图的32甲上配对，原损失两组各256次每甲曝光及1024更新，新增角向分支初始64份输出逐字节一致。原分支和扩展分支均25/32，平均Boundary IoU分别0.775480及0.776695。扩展增益0.001214，20改善/12下降，2甲失去严格通过；28甲、相对增益及严格集合门未过，关闭本版扩展。原8甲在等曝光的32甲共享原分支中平均Boundary IoU由0.886997降为0.800915。两次试验更新总数与批次组成不同，下一步用同一初始权重和固定批次检验梯度相互牵制。全634质量仍0/634，PRODUCT HOLD。

2026-11-05按用户要求增加独立本机业务候选：几何64轮权重SHA `161e10be562fa4becd00cbde2c7bb4fcf80611308c681afc9dfd4e6d71fbf9ea`经Python/GPU接入§5.4；仅选择已完整终评真实100源分支中的平均边界IoU最高版。原严格联合0/634、历史失败和512轮待终评状态保持。API及浏览器实际接入证据见`model/reviews/business-candidate-20261105-v1/`与[说明](nail-texture-business-candidate.md)，生产发布身份保持。

历史检查点可用性（2026-11-04用户明确分批退役）：上批删除3860个旧中间断点，逻辑16337453846字节；原清单与核验保留于`model/reviews/checkpoint-retirement-20261104-v1/`。本批继续退役已结项且后续版本已替代的全634边缘监督64轮（含续接）、几何残差64轮及早期像素径向24轮的14050个中间断点，逻辑/分配均25116758136字节（23.392GiB）；两批累计17910文件、逻辑38.607GiB。各目录首末断点、计划引用恢复接缝和全部最终权重保留，144份关键保留文件与34项历史终态/报告绑定核验通过。当前512轮训练及其已存断点、原RAW/事件/标注/报告保留；已退役历史实验的完整逐步状态重放停止保留，原已完成重放报告及质量失败保持其当时事实。当前512轮计划保存1281份完整断点，全部324608份RAW的重放合同及原发布质量门保持。逐文件清单、持久化删除事件和独立事后核验见`model/reviews/checkpoint-retirement-20261104-v2/verification.json`（SHA-256 `72addb77edc1af0b809c5cef4c4ab27017e73f0c44dcf2f3f4519f04bf254c9c`）。

新增`native-context-radial-refiner.py::NativeContextRadialRefiner`保留5x2048x129原坐标输入、2048角度/±64px及原尺寸两头，五尺度内容编码解码和160-token注意力，277108参数/77参数张量及2固定缓冲区（完整state_dict为79项）。原暂停14910输入/3739步经全账核验后，精确续接306输入/77步，合计24轮15216输入/3816步完成；第一条续接输入前模型、优化器及全部RNG逐字节恢复通过。全部15216份RAW、3816完整checkpoint及53309事件独立合并重放通过，每甲恰好24次。固定last SHA `ca304b74dc052b789e9a04c40d55859376cae48585a69b1227d0020115e7ce7a`；全634甲/636候选：IoU≥0.75匹配634/634、原2px严格联合0/634、漏甲图0/100，边界IoU/F1均值0.270805/0.655614，训练域绝对门仍未通过（需≥539甲严格联合）。本次权重保留为开发诊断，活动16轮权重保持；本轮预算已消费完毕。`radial-raw-codec.py::save/read`逐份原尺寸原头重建通过；原暂停/后处理异常保留。闭合证据`batch037/real-only100-context-radial-closeout-v2.json`，该阶段入口v14，PRODUCT HOLD。

固定8目标受控拟合已完成：同初始化/监督/每目标256次曝光、新AdamW lr0.003；共享4/8严格联合、独立7/8，原预检8/8门未通过。4096训练+24评估、2304更新及4120原头/81完整checkpoint/16988事件/120原像素指标独立重放通过。证据`batch037/real-only100-context-controlled-fit-v1/run/report.json`与`replay.json`。

新增训练接口`native-radial-boundary-loss.py::objective(mask,presence,radius,truth,target_radius,boundary_band)`保留原径向损失并加2倍radius4带BCE；`boundary_band_for_crop(full_truth,crop)`先生成完整源图边缘带再提取ROI。固定8项2048训练+16评估/256更新已完成并独立重建2064原头、64指标、9完整checkpoint、6708事件和全部原图边缘带，固定末轮严格联合5/8，原8/8门保留未通过。证据`batch037/real-only100-context-boundary-fit-closeout-v2.json`，3项相关测试保持；该控制尚未全634终评。

固定8项低学习率512步退火已完成并独立重放，7/8；继承完整末态的困难训练损失均衡固定64步后，8/8原2px三门通过，最低Boundary IoU/F1为0.754698/0.943712。均衡只按冻结训练损失>2倍中位数设权重2，其余1，保留全部8目标；该阶段512训练+16评估/64更新、528原头、48原像素指标、5完整checkpoint及1716事件独立重建一致。各阶段初始8原头与前一末态逐字节一致，完整优化器/RNG继承；全链共6656训练输入/832更新，均保持控制用途。证据`batch037/real-only100-context-boundary-capacity-closeout-v1.json`。

**全634边缘监督64轮及全量终评已完成。** 原中断/精确续接、40576有效输入/5120更新、634甲各64次、40581已存RAW及原不确定1项保持；全部RAW及5120完整优化器/RNG断点独立重放通过，原流水线5阶段均退出0。固定末轮SHA `13b7d20b3d953e3370c0f035a14ed4c852551566249b2eee9a16e56707adf393`；全100源634甲/636候选终评与独立复算一致：匹配634/634、严格联合0/634、漏甲图0/100，Boundary IoU/F1均值0.286946/0.682286，质量门失败，2未分配项待实审。保留开发诊断，活动16轮权重保持。证据`batch037/real-only100-full-boundary-closeout-v1.json`。

全634零推理核对确认训练/终评数组、候选和坐标一致，Boundary IoU单门0/634（最高0.607867）、F1单门29/634；固定8严格联合8/8→0/8，平均Boundary IoU 0.841322→0.304060。证据`batch037/real-only100-full-boundary-final-audit-v1/report.json`及`replay.json`。

新增`native-geometry-radial-refiner.py::NativeGeometryRadialRefiner`：保持5×2048×129图像条带及原坐标两头，冻结277108参数视觉基线，新增16641参数周期1D残差分支，读取预测边缘处16通道内容、粗/预测半径、相邻形状差分及角度sin/cos；直接回归半径残差并保持相对粗半径±64px约束。推理不输入真值、图片身份或样本编号。实际8项零初始化输出与旧全量终评mask/presence/radius逐字节一致，独立控制24前向/8反向/1更新后冻结基线全部状态保持，loss2.099963→2.099078，24份RAW及完整状态复核通过。3项合成结构控制通过。全634几何残差64轮、40576输入/5120更新、全部RAW/完整状态重放及全636终评已完成：匹配634/634、严格联合0/634，Boundary IoU/F1均值0.338758/0.764382；原2px/539门保留失败。固定8目标新AdamW受控512步已完成，4096训练+16评估，严格联合8/8；全部4112 RAW、17完整checkpoint、全部事件及16原像素指标独立重放通过，原8/8容量门通过。 固定末轮SHA `161e10be562fa4becd00cbde2c7bb4fcf80611308c681afc9dfd4e6d71fbf9ea`；闭合证据`batch037/real-only100-geometry-boundary-closeout-v1.json`及`real-only100-geometry-eight-fit-closeout-v1.json`。全634原指标/半径诊断逐项复现，MAE3.699191→3.266882px，537改善/97上升；同结构固定8在512次曝光达到8/8，缓存保真及全634训练实际状态见下段。当前入口v32，58调整/42完整微调、下一60展示。

新增开发分支`VisualNeighborhoodRadialRefiner(previous)`冻结旧103状态，在最终预测半径内外0/±2/±4/±8原像素读取5通道条带，加半径/角度共39通道，周期卷积学习新残差；沿用mask/presence/radius及原坐标解码。固定预检、634缓存物化和完整特征/输出字节保真通过；32轮20288输入/2560更新、20288 RAW/66051事件/81完整状态及全部RNG独立重放完成，监督退出0。固定636候选/100源634甲原2px终评和独立复算一致：匹配634/634，Boundary IoU/F1=0.559952/0.961424、严格联合0/634。较第60次bIoU+0.016097，542改善/92退步、8严重回归，F1通过571→590；+0.02诊断门与原539门保留失败，source簇为1，来源独立区间不可估。闭合`batch037/real-only100-neighborhood61-closeout-v2/`；61调整/45微调，下一70展示。

当前继续拟合合同：以第61次固定末权重初始化，先对8严重回归目标执行16前向/8反向/1更新，初始两头/半径与终评逐字节一致、旧网络冻结、20梯度有限、损失下降及16RAW/2完整状态独立重放通过。另立均衡128轮81152输入/10240更新预算，新AdamW lr0.001余弦至0.00001；完整原634缓存、角色和损失保持，预检更新权重仅控制使用。初始/每32步/末态321完整状态、每输入RAW，固定epoch128 last后全636原2px终评；已由`pipeline-v1`持有原监督活句柄接续全链，首失败停止，无自动重试。当前入口v41，训练目录`batch037/real-only100-neighborhood128-v1/`；增加曝光的收益待完整终评，商用门/业务权重保持。 原执行现已内存失败；当前状态以§3的v1.2.266及入口v42为准，旧失败/预算保留，单次续接尚待完整前缀审计。

**全634缓存512轮及内边界IoU损失16轮均已闭合。** 原512基线Boundary IoU/F1为0.541192/0.953899；新16轮10144输入/1280更新，全部10144 RAW/41完整状态和636终评独立重放通过。新Boundary IoU/F1为0.543854/0.953957，严格联合0/634；412改善/221退步/1持平，严重回归诊断2甲，F1通过568→571，事前+0.02相对门失败。末权重SHA`231c459b2438253917d4cebaf3a5f7ae388c712be90fbf43949d53744cc2b57b`。闭合`batch037/real-only100-biou60-closeout-v1/report.json`，当前入口v37；60调整/44微调，下一70展示。下一为已存RAW局部残差和视觉内容可达性诊断，原539门及PRODUCT HOLD保持。

新增`oneoff/finish-geometry-boundary-pipeline-v1.py`连接现有监督/训练PID、创建时间、命令行和两个Win32活句柄；正常64轮终态后串行执行完整40576 RAW/5120优化器断点重放、固定末轮全636推理、100源634甲原2px指标及独立复算。重放器逐断点核验79项冻结基线状态及24项训练优化器状态；全634训练/终评输入绑定一致，评估重建/分母/阈值算法与既有全量口径AST逐节点一致。阶段独占持久化开始/终态/退出码，异常停止，无自动重试。原监督和训练退出0，全部5阶段退出0并独立重放，训练预算40576及最终636推理已全部消费；原质量门失败保留，流程不重启。计划/执行见`batch037/real-only100-geometry-boundary-finish-pipeline-v1/`，源码/全634对齐及真实第1200步冻结基线/RNG核验见训练目录`finish-code-validation-v1.json`。

收尾接口`oneoff/finish-full-boundary-pipeline-v1.py`已按原训练/监督创建时间、命令行及Win32活句柄冻结单次串行流程：原64轮退出0及完整终态→全部40581已存RAW/5120优化步checkpoint与恢复账重放→固定last全636推理→全100源634甲原2px指标→独立复算。任一步异常保留并停止，不自动重试；原539联合门、来源角色、生产HOLD保持。计划和执行入口`batch037/real-only100-full-boundary-finish-pipeline-v1/`。

当前半径学习诊断：全634实际浮点半径CPU损失梯度中，774116/774118个>2px误差角度指向真值；固定8项独立参数步探针为24前向/8反向/1更新，8项末轮原头精确重现，平均半径移动0.004517px、目标误差变化-0.000285px，6改善/2上升，梯度范数0.389939未触发阈值1裁剪。只记录输出空间和一次真实参数更新，神经参数根因继续以受控拟合验证。探针保持控制用途，原24轮预算已结项；证据`batch037/real-only100-context-loss-gradient-v1/report.json`及`real-only100-context-update-probe-v1/report.json`。

标注可复用本机WeVis服务`POST /matte`：完整原图输入、原尺寸uint8 L alpha PNG，uint8>127生成候选。现行100图634甲按指定目录完整源图及逐甲原像素审核准入；batch037的165号4甲、215号5甲经原坐标人工多边形返修和完整叠线终审通过，合法、界内、严格零交叠，旧失败保留。坐标页仅在原图区外加边条，源RGB核验一致；完整mask覆盖甲根、侧缘、自由缘及附着装饰，排除皮肤、阴影和背景。失焦、裁断或局部露甲按源质量门处置。实际图片输入见batch037/actual-image-input-audit-v1.json，训练见下段。

最新可继续开发的Stage A为指定100图634甲专用候选。官方YOLO11n-seg COCO通用基础权重经官方发布文件SHA核验，从其独立项目微调，仅指定目录100图634甲；GPU FP32固定40轮、4000图输入、2000微批、500优化步，100身份各40次，固定第40轮EMA last SHA `5ef154704e36691871a50e162b8e446a12dc3211404ad014f8aceeb9d8b52b4e`。无旧23成员、旧项目权重、教师、受保护输入或新增负样本。全部RAW、曝光、40份epoch checkpoint及FP32状态独立重放通过。 固定512/mask_ratio1/批二累积四、CPU2线程/interop1，AMP/TF32及自动OOM/NaN重试关闭；自动验证输入0。证据`batch037/real-only100-stage-a-v1/train/report.json`及`train/replay.json`，官方基础文件来源`real-only100-foundation-v1/provenance.json`。机器入口`model/reviews/cycle016-wevis-real-material-v1/current-development-state.json`与不可变`batch037/current-development-state-v32.json`字节一致。

活动原尺寸精修仍为仅指定100源的16轮候选，固定last SHA `ae6be9e8dd854d187797cee03053b88f31075fd8ae890f2efc1f152a4bac3600`，10144输入/2544步、240骨干状态冻结。全634匹配、原2px边界IoU/F1均值0.324978/0.727894、联合0；实际两头/曝光/16轮checkpoint与全636评估已重放，证据`batch037/real-only100-stage-b-closeout-v1.json`。困难边缘第6轮checkpoint全100诊断为634匹配、边界IoU/F1=0.304115/0.690498、联合0，未晋升；原8轮为用户中断，精确恢复在5输入/1步后RAW差1.430511e-6而停止，原失败、13步缺口和未消费预算保持。证据`real-only100-resumed-radial-closeout-v1.json`，该阶段入口v14，55调整/39完整微调，下一60展示。

当前新路线为原像素径向位移网络：`native-pixel-radial-field.py::lattice/fit_radius/logits`定义原ROI整数像素中心、float64角度转int32格、float32距离/半径，maskLogit=radius[angleBin]-distance，仍以0阈值解码。2048角度/±64px的全634表示上限为629/634，无位移限634/634；真值仅用于训练上限，运行输入半径只来自同候选粗mask。旧连续多边形表示上限546/634原样保留。全原粗mask指标、坐标数组SHA、半径及mask位独立重放见`batch037/real-only100-pixel-radial-reachability-v1/`。

新接口`native-radial-strip-refiner.py::build_strip(rgb,coarse,center,radii)`仅依赖RGB/同候选粗mask及原坐标，float32 5x2048x129条带；`NativeRadialStripRefiner.forward(strip,coarse_radii,angle_bins,distance)`输出完整原ROI maskLogit和presence两头，训练辅助读取半径。5458参数/13张量；全634物化及原像素数组重建、新损失8项预检和独立非零控制保持。完整原尺寸BCE+Dice+0.5*SmoothL1(radius/8,targetRadius/8,beta=0.125)+0.25*presenceBCE，AdamW 0.001余弦至0.0001的唯一24轮训练已完成：15216输入/3816步，全部RAW/完整checkpoint/53307事件独立核验。固定last SHA `28530ee887e4a4285614e748ca720798325381541e9d9056e6e1159f053f4118`；全634甲/636候选：IoU≥0.75匹配634/634、原2px严格联合0/634、漏甲图0/100，边界IoU/F1均值0.266583/0.650250，训练域绝对门仍未通过（需≥539甲严格联合）。全100源/636候选原始两头及634真值指标独立复算通过；证据`batch037/real-only100-pixel-radial-closeout-v1.json`。该阶段入口v14，55调整/39完整微调，下一60展示。该阶段后续已由当前Goal承接；旧接口/部署通过不迁移，原两头1e-4/零像素差/presence和整链成本仍须另验。

`refine-mask-with-grabcut.py::refine(rgb, mask, presence_accepted, radius=8, iterations=3)`与`refine-mask-with-edgecut.py::refine(rgb, logits, presence_accepted, radius=8, weight=1)`仍为隔离开发接口，两分支关闭。旧StageA完整新3源18甲基线联合门0/18，同种子一一ROI上限13/18，固定该候选和ROI仅改StageB不可达85%完整mask要求；旧统一presence无解/固定presence仅改mask头2/5上限、紫色五甲及原8甲边界失败保持。

新StageA固定30轮的覆盖提升及整体开发门false仍见`model/reviews/cycle016-stage-a21-v1/`，149/149几何容纳不是边界通过。全22源149甲151候选原生StageB基线见`cycle016-full149-stage-b-v1/quality-report.json`/`quality-replay.json`，旧123严格联合9、新18和保留8均0，两额外候选未拒识。

新候选143输入（141完整甲面、同候选局部重复/皮肤拒识各1）另立开发训练，固定60轮/8580增强输入/2160优化步/151最终两头RAW，整数旋转翻转及光度增强逐次重放。固定最终旧123联合8（9基线中4退化、3新恢复）、新18和保留开发8均0，141正presence全部接受、两拒识零输出；开发门false、分支关闭。见`model/reviews/cycle016-newcandidate143-v2/run/report.json`、`replay.json`及完整`preview/index.html`。不更改生产权重/阈值或转授旧数值通过。

粗候选自动提示SAM2.1-L有限基线现见`model/reviews/cycle016-seeded-semantic8-v2/quality-report.json`/`quality-replay.json`及完整`preview/index.html`：先新增过滤前全量观察控制，续接原未消费单次完整8甲真图，权重/提示/公开conf不改。原控制4/8失败保留，现行全8项真实输出严格联合0/8、IoU0.58981且皮肤/缎面污染，固定分支关闭，不扩提示。峰值CUDA allocated1498892288字节、单真图主机墙钟2.805秒含RAW保存，不代表浏览器性能或完整峰值成本。

当前开发结构`model/training/native-pretrained-context-refiner.py`继承原生四通道RGB+粗mask、mask/presence两头及固定先验/阈值，在原上下文精修上复用现有StageA已训练骨干4/6/10层的stride8/16/32特征；骨干冻结、始终eval，三个零初始化1×1投影仅向mask路径添加语义残差。输入RGB从现行float32 ImageNet归一化反变换、舍入回原整数格点后/255，仅右下pad32（114/255），不缩放RGB；骨干原点0、原生quarter中心4*i+1.5显式双线性采样，禁止将pad范围压缩映射回ROI。presence仍读取原e3；60张量414802可训练参数及1365472冻结骨干参数（240状态含BN）。原完整损失和0.25距离辅助项保持，原像素真值/角色不变。8项针对性测试、独立1536非零控制/全162热启动两头精确/462梯度预检重放通过；学得图当前合成接口资格见下方；真实图片、完整产品及正式部署资格未授予，不继承旧数值通过。

历史上下文结构分支见`model/reviews/cycle016-context143-v1/run/report.json`及`training-replay.json`，原开发门false、固定分支关闭。其学得参数不用于当前100源精修初始化；下一精修参数全新、冻结骨干只取本轮100源Stage A，另冻新架构元数据与梯度/资源合同。

存档损失分析`model/reviews/cycle016-native-loss-alignment-v1/analysis/report.json`及`replay.json`已闭合：全151前后质量同构、2损失控制、143训练身份前后286次损失及完整输出梯度数组重算。旧/新最终错误32445/17224像素，完整梯度方向正确32385/17187、零梯度均0；不支持单以损失无约束解释失败，也不证明网络参数优化或泛化。保留8仅重建旧质量，无新损失。两组精细真值及12对关系已闭合，新开发全链路基线见下段；开发资格/诊断不自动改变现训练集或正式保护角色/质量门。旧粗mask数学诊断及全部历史失败保持原报告。

上一闭合训练见`model/reviews/cycle016-paired154-v1/plan.json`、`run/report.json`、`training-replay.json`与`quality-migration-replay.json`，原147/149、压力45/298和完整开发门false保持。147已通过mask的原图保持、全部154 presence及完整真值监督仍是当前配对基线；失败教师mask不蒸馏。

历史光度规范化分支见`model/reviews/cycle016-normalized154-v1/plan.json`、`training-replay.json`、`quality-migration-replay.json`和`failure-attribution-v2/report.json`。固定60轮、18480前向、2340更新及462最终RAW已重放；原图146/149、压力220/298，完整开发门false并关闭。旧147/149、各项退化/恢复及presence结果保留原报告，未转授当前100源候选。现行路径不加入该预处理；原图/纹理/坐标/真值/角色及旧参考不变，固定20/50分位零推理替代未过稳定门、未训练。

离线Qwen仅定位试验见`cycle016-qwen3-v1/localization-closure-v2.json`：冻结3整图22甲，原裸StageA资格门仍可达且未执行；重建实际接受集合22/22、0额外后，当前端到端仅定位严格增益余量0，基于目标相关收益关闭分支。Qwen图像输入0、无蒸馏/效果结论，部分官方权重下载已停止，不能据此否定像素教师或SAM能力。

当前技术实施总合同见`docs/nail-texture-local-inference-implementation-spec.md`v1.13 §6.1/§6.3：Stage A 512候选、Stage B原尺寸四通道及mask/presence双头、完整原图坐标逆映射。当前修复仅Stage B合成接口通过；真实输入、Stage A+B完整Worker/Canvas及发布身份仍须验收，旧单阶段manifest例子不构成双阶段生产合同。

上一冻结RGB基线完整执行见`model/reviews/cycle016-pretrained-context-v2/plan.json`、`preflight-replay.json`、`run/report.json`及`training-replay.json`：23源149正/5同候选拒识154训练身份、462视图，独立固定60轮/9240训练输入/2340更新，全部162最终RAW/157真值及143训练基线保留、6取证checkpoint和全部事件重放。训练域旧123/123、新17/18及新两源7/8，143基线零退化、149正presence全接受、5拒识零像素，开发门true；147/149属于训练域，不是正式准确率。原保留开发8训练0、最终诊断0/8，不用于选择。全部60训练张量改变、240骨干状态完全不变；预检与训练CUDA allocated1273385984/559591424字节不代表浏览器/完整流程成本。此前距离分支开发门false仍保持`cycle016-distance154-v1/`原报告；距离目标/损失合同见`normal-stage-b-distance-loss.py`和其`loss-value-replay.json`，不将本轮增量全归因新结构。已完成的新图独立导出/控制见下段；该阶段展示账为3次微调，当前调整计数见本轮训练段；无新成果视觉通过或生产切换。

当前完整图导出接口`export-native-trained-fullchain.py`提供真实300状态严格加载、原尺寸双头导出、严格FP32 CUDA/CPU ORT及完整RAW/事件重放。`onnx-native-fullchain-repairs.py`组合16处同epsilon的float32分块归一化、4处3×3空间分段和最终1×1分段；其后`onnx-blocked-presence-reductions.py`仅改三处Sum/Mean为同float32三级128分块累加。各变换逆序恢复原完整ONNX字节，全部原权重、偏置、阈值不变。生产接入仍须真实输入与整条链验收。

当前完整部署控制见`cycle016-presence-stable-independent-v1/report.json`和`cycle016-presence-stable-learned-v1/report.json`：独立非零及真实训练权重分别全27输入54RAW，各三后端九尺寸达到两头绝对1e-4、解码零像素差和presence一致门，包含1536方形与极端长宽比。真实模型未改300状态；同一实际图修复不因独立/学得验证重复计数。旧`cycle016-fullresolution-partition-v1/report.json`、首次学得WASM7/9及全部历史失败保持；合成通过不授正式质量、性能或发布资格。

当前边界观测接口`audit-pretrained-native-boundary.py`提供实际图只增enc1.0输出、原图字节回剥、严格CUDA捕获及`verify-cuda`/`verify-all`零推理重放；`serve-pretrained-boundary-capture.py`提供绑定完整9输入的WASM/WebGPU捕获。最终头保真按全部输入逐后端原始字节校验，全部27输入/81张量完整有限及54最终头通过后才允许层统计，否则`reconstruction_mismatch`且拒绝归因；同请求SHA/长度/身份一致的有界传输重试不重跑模型。当前完整门通过见`model/reviews/cycle016-pretrained-first-boundary-v1/report.json`：WASM首卷积全9最大差1.90735e-6，WebGPU前8为2.38419e-6，1536为8.602846。首卷积同输入隔离已完成，当前结论见下段；较小8例最终失败仍需后续定位，学得模型与正式发布资格不变。浏览器完整进程峰值与端到端成本未验收，文件/HTTP载荷字节不能冒充实际网络流量。

当前单卷积隔离接口`audit-onnx-conv-isolation.py`保留原节点/初始权重、同9输入及严格CUDA边界，提供CPU执行与完整RAW/事件重放；旧28控制及原WebGPU1536失败保持`cycle016-firstconv-isolation-v1/report.json`。现行分段转换`onnx-spatial-partition-convolution.py`对原3×3/stride1/pad1无bias卷积采用显式零padding、4个动态高度段/完整halo及Concat，全部原权重不变，原图可逐字节回剥，16..1536整数高度覆盖无丢失/重复。`audit-partitioned-conv-controls.py`及`serve-single-output-controls-v2.py`提供同9三后端单输出捕获、实际ORT设备limits及零推理重放；实际申请描述符未拦截，不把源码策略当申请实测。当前`model/reviews/cycle016-partitioned-firstconv-v1/report.json`全27数值通过，WebGPU最大3.33786e-6；实测/实际ORT设备上限65535、分段最大18432。完整图已实际验收但WebGPU未过，现行失败见上段；单算子通过不得转授完整图或学得部署。

只读诊断接口`onnx-observe-normalization-moments.py`与`onnx-observe-presence-reductions.py`仅增加既有输出，配套服务独占保存RAW；原图字节回剥、CPU/WASM全九尺寸36原最终头全字节保真后才允许层统计。当前分别18输入612RAW及18输入126RAW通过保真，首次学得WASM两项失败仅presence标量；同输入float64归约反事实不是实际模型输出。新float32归约修复实际全27通过见上段。提交原因跟踪已分开7948计算、144观察读回、2179独立上传及9空flush；原7948=8065错误合同失败不追认，原未加观察的117读回与本观察新增27读回分开，见`cycle016-submit-boundary-v1/report.json`。所有旧跟踪/缓存/准备失败及已消费预算保持。

真实训练域154保真已闭合为CPU门失败：严格CUDA与CPU ORT各154次、616份RAW，140例通过，14例仅mask数值超过1e-4，最大2.40326e-4；全部解码零像素差、presence一致，保留8未读取、300状态不变。`cpuFullGatePassed=false`，WASM/WebGPU未执行，证据`model/reviews/cycle016-learned-train154-deployment-v1/cpu/report.json`与`terminal.json`。cuda-affine完整154仍失败，语义单例介入不证明可达。

原生Resize实际算子控制已按16输入、严格CUDA/CPU ORT各16次、32调用/32RAW闭合：12个输入后端输出不同，4个精确2倍轴输入一致，最大差4.57763671875e-05；全部输出完整有限，项目像素0、学得完整图0。线性区实际斜坡与公式比较显示CUDA符合`float32(in/out)`逆比例融合乘减预测，CPU ORT符合`out/in`正比例除法，`closeout.json`据此判定坐标假设得到实际隔离算子支持；`actualLearnedRootProven=false`、`fullGraphTransformVerified=false`、`fullNineSizeIndependentControlExecuted=false`。当前`model/reviews/cycle016-native-coordinate-explicit-v1/next-execution-requirements.json`冻结四Resize主机坐标显式化：先要求权重不变、九尺寸覆盖/逆映射、逐字节逆变换及256MiB资源门，再执行独立非零控制与学得候选各9次CPU ORT，共18次并复用既有各9份严格CUDA参考；新CUDA、浏览器、154学得输入及项目像素均0，CPU通过前不启动WASM/WebGPU。

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


## B. 原 §3 功能状态总表表格前的逐版本叙事

**v1.2.279固定32甲共享拟合路线。** 第128至256次曝光仍有31/32甲改善，固定末态25/32。继续从该末态按等曝光比较恒定学习率和余弦退火。全634质量仍0/634，PRODUCT HOLD。

**v1.2.278固定32甲混批对照。** 投影更新未获得原2px边界增益，关闭本版。下一步复算原损失共享拟合轨迹，定位停滞发生在初期还是后期。原全634质量仍0/634，PRODUCT HOLD。

v1.2.268已恢复3000开发预览及实际页面交互：冷访问原164.94秒，PostCSS占133.02秒；Tailwind扫描base收紧至src后，本次重新启动首次访问30.41秒，随后三次HTTP为29—51ms。Playwright桌面、窄屏和横屏重载/辅助线切换通过，页面及资源错误0、横向溢出0；独立CSS重建约82ms。AR v5甲根/甲尖/侧边拖动、双手方向参考、手动方向预览及亮度适配保持，相关90项回归见v1.2.267记录。生产构建完整终态与真实相机贴合继续单列待验；训练Goal已恢复，见下段。本页面修复轮仅页面排障，见§4.5/§11.1及当日日志。

**v1.2.274第62次模型调整完成。** 原128轮81152输入/10240更新，264195逻辑事件、81152份RAW和321份状态独立重放通过。固定636候选终评及三基线配对已复算。匹配634/634、漏甲图0/100，Boundary IoU/F1均值0.582402/0.966976。相对第61次Boundary IoU提高0.022450，584甲改善、50甲下降、严重回归0，此前8项均改善。Boundary F1达标597/634，Boundary IoU达标0/634（最高0.747427），严格联合仍0/634。当前仅登记为训练域诊断，入口v51，PRODUCT HOLD。

**v1.2.275多尺度轮廓路线。** 冻结第62次100图634甲原像素诊断已重建636候选及全部原配对指标，并独立复算9个场景。整体质心平移和径向常数各0/634，理想修正局部33—1024谐波218/634，仍差321甲。理想修正1—8谐波或0—32合并均2/634。现有真值半径回代634/634，几何可达余量95甲。下一步用同一冻结快照，配对预检联合学习局部细节和低频形状，原2px及539门保持。 反事实使用训练域真值，现有实际联合仍0/634，PRODUCT HOLD。

**v1.2.276分频配对结论。** 第63次配对预检从第62次固定权重出发，原损失与分频组各256次更新、2048训练输入及16评估输入。两组原2px严格联合均8/8，平均Boundary IoU分别0.886997和0.873761。分频组8/8逐甲下降，平均差-0.013236，1甲触发严重回归（最大下降0.025129）。相对增益及零严重回归门未过，关闭本版分频损失分支。下一步沿用原损失，在更广的冻结训练样本上对照检验共享轮廓分支容量。全634正式训练域联合仍0/634，PRODUCT HOLD。

**v1.2.277角向容量配对结论。** 第64次在31张冻结图的32甲上配对，原损失两组各256次每甲曝光及1024更新，新增角向分支初始64份输出逐字节一致。原分支和扩展分支均25/32，平均Boundary IoU分别0.775480及0.776695。扩展增益0.001214，20改善/12下降，2甲失去严格通过；28甲、相对增益及严格集合门未过，关闭本版扩展。原8甲在等曝光的32甲共享原分支中平均Boundary IoU由0.886997降为0.800915。两次试验更新总数与批次组成不同，下一步用同一初始权重和固定批次检验梯度相互牵制。全634质量仍0/634，PRODUCT HOLD。

v1.2.265按用户最新截图继续AR贴合专项：`cuticle-fit-v4`继承甲根固定、长宽独立校准和双轴投影；纹理甲根中心改取可见高度82%—95%处，根部增加0.5—2局部像素alpha过渡。模型mask提取前可用同图手指关键点进行双向唯一配对，仅补充有向参考；25°轴差、横向/纵向距离及近邻歧义守卫失败时保留轮廓方向与复核。新增方向步骤全本地，5秒超时，换图/关闭取消，模型原mask与手工指位保持。工程及浏览器验收详见§4.5与当日日志。

v1.2.257统一识别交互：浏览器ONNX为主路径；仅浏览器降级/空结果且已有本机处理确认、服务就绪时自动补充本机识别，云端模式保持独立。参考图提取、照片编辑与分析页共享默认展开的本机面板；首次“同意并识别”直接执行，失败保留输入/结果，可重新检查服务。自研本机候选显式重新识别替换区域并提示复核；浏览器有效结果保持。浏览器历史定位诊断折叠显示，本机成功后清除旧摘要。分析页补充本机入口及取消/换图过期响应守卫。摄像头继续显式启动，原隐私确认与质量复核保持。

指定100源634甲精标与统一训练完成，持续Goal已恢复，当前会话仅训练与评估，既有业务接入保持。多尺度上下文径向候选24轮15216输入/3816步及全量独立复算完成；全634甲/636候选：IoU≥0.75匹配634/634、原2px严格联合0/634、漏甲图0/100，边界IoU/F1均值0.270805/0.655614，训练域绝对门仍未通过（需≥539甲严格联合）。本次权重保留为开发诊断，活动16轮权重保持；本轮预算已消费完毕。下一见Goal/§8.9/§11.1，PRODUCT HOLD。 固定8独立/共享对照已重放，共享4/8、独立7/8；边缘带、低学习率退火及困难损失均衡控制分别5/8、7/8、8/8，全部已独立重放；全634规范边缘带及独立重放已完成；新全量64轮及完整重放/全636终评已完成，40576有效输入/5120更新；严格联合0/634，Boundary IoU/F1均值0.286946/0.682286。全634几何残差64轮、40576输入/5120更新、全部RAW/完整状态重放及全636终评已完成：匹配634/634、严格联合0/634，Boundary IoU/F1均值0.338758/0.764382；原2px/539门保留失败。固定8目标新AdamW受控512步已完成，4096训练+16评估，严格联合8/8；全部4112 RAW、17完整checkpoint、全部事件及16原像素指标独立重放通过，原8/8容量门通过。 缓存保真及全634缓存物化已独立重放，恢复训练已完成512轮/324608逻辑输入/40960更新，监督退出0；v3原中断及未知退出码保留；v4五阶段均已退出0，324608 RAW/1281完整断点、固定636候选终评及原100源634甲2px指标独立复算完成，Boundary IoU/F1均值0.541192/0.953899、严格联合0/634。当前第60次调整（内边界IoU损失16轮）已完成10144 RAW/41完整断点重放及636候选终评，Boundary IoU/F1为0.543854/0.953957、严格联合0/634；相对512基线增益0.002662，原质量门失败。全634局部残差诊断已独立重放；邻域视觉32轮及完整20288 RAW/81状态、固定636终评已闭合，Boundary IoU/F1为0.559952/0.961424，严格联合0/634；542改善/92退步、8严重回归，F1通过590。第61次已登记；新8回归预检与重放通过，现以第61次末态继续独立128轮81152输入/10240更新，完整321状态/RAW和636终评链已接续。当前入口v41，见Goal/§8.9，PRODUCT HOLD。


## C. 原 §11.1 阻塞项叙事


**v1.2.279固定32甲共享拟合质量。** 第256次曝光仍有晚段提升，末态25/32低于28甲容量门。继续检验等曝光续训能否改善余下7甲的边界IoU。全634原2px严格联合仍0/634，正式完成保持HOLD。

**v1.2.278混批更新结论。** 实测61/112负梯度点积，但四个原AdamW更新的32个逐甲原损失方向均为下降。投影平均原2px Boundary IoU相对差−0.000189，关闭本版。此结论限于固定四批及第62次权重的一步更新；全634严格联合仍0/634。

AR v5实际页面加载与基础交互已于v1.2.268通过开发预览验收，首次编译慢已定位PostCSS并限制src扫描；自动甲根仍取手部关键点估算，完整生产构建终态与真实相机自然度继续待验。当前证据见§4.5及2026-11-05日志v1.2.268，历史超时和编译失败保留。

AR最新截图专项已补充`cuticle-fit-v4`（§4.5）：同图手指方向参照、下部甲根中心与短alpha过渡。实际摄像头根部定位、尺寸和侧转自然度继续实机验证，当前训练权重与正式发布质量合同保持。

AR贴合工程修复已接入v1.2.259：甲根锚定、可见尺寸、完整透明轮廓、连续采样、方向复核/翻转。当前手部关键点提供估算甲根，实时甲缘像素定位、遮挡及侧转贴合、用户实际相机自然度仍待验证；产品合成控制和模型原像素质量分别记录。模型权重与商用完成门沿用原状态。

浏览器业务发布及覆盖率抗锯齿已接入（§3/§6.2/§7，v1.2.258）：当前组合身份`nail-texture-seg-geometry64-browser-aa4-v2`继承v1原权重；v1经发布门全链（导出数值保真、Python↔浏览器逐实例mask对拍IoU=1.0、生产服务器端到端、全量1530测试）后登记为`deployed`，`/ar-tryon`等三站按正式模型口径展示。本机Python/GPU候选通道（§5.4）保持可用作对照与回退。商用完成门缺口保持PRODUCT HOLD：正式浏览器权重之上仍缺未见来源质量（独立val≥30校准、正/负发布留出各≥100、三变体零误检）、角标捷径消融、四类真机各≥20次、Beta人工审核≥100张与双批准权重回滚演练，completion audit `decision=complete` 前不解除HOLD。训练分布外甲面召回弱（超长淡色梯形甲等，2026-11-05探针实证）已记录为已知限制，按用户反馈经512轮版或后续权重迭代。

早期实验及已被后续512轮版本替代的全634边缘监督64轮、几何残差64轮、像素径向24轮的完整逐步checkpoint重放已停止保留，适用范围和当时已完成证据见§8.9；最终权重、首末及计划引用接缝、原RAW/事件和历史质量判决保留。当前512轮完整断点及重放合同保持。

**v1.2.274第62次模型调整完成。** 原128轮81152输入/10240更新，264195逻辑事件、81152份RAW和321份状态独立重放通过。固定636候选终评及三基线配对已复算。匹配634/634、漏甲图0/100，Boundary IoU/F1均值0.582402/0.966976。相对第61次Boundary IoU提高0.022450，584甲改善、50甲下降、严重回归0，此前8项均改善。Boundary F1达标597/634，Boundary IoU达标0/634（最高0.747427），严格联合仍0/634。当前仅登记为训练域诊断，入口v51，PRODUCT HOLD。

**v1.2.275多尺度轮廓路线。** 冻结第62次100图634甲原像素诊断已重建636候选及全部原配对指标，并独立复算9个场景。整体质心平移和径向常数各0/634，理想修正局部33—1024谐波218/634，仍差321甲。理想修正1—8谐波或0—32合并均2/634。现有真值半径回代634/634，几何可达余量95甲。下一步用同一冻结快照，配对预检联合学习局部细节和低频形状，原2px及539门保持。 反事实使用训练域真值，现有实际联合仍0/634，PRODUCT HOLD。

**v1.2.276分频配对结论。** 第63次配对预检从第62次固定权重出发，原损失与分频组各256次更新、2048训练输入及16评估输入。两组原2px严格联合均8/8，平均Boundary IoU分别0.886997和0.873761。分频组8/8逐甲下降，平均差-0.013236，1甲触发严重回归（最大下降0.025129）。相对增益及零严重回归门未过，关闭本版分频损失分支。下一步沿用原损失，在更广的冻结训练样本上对照检验共享轮廓分支容量。全634正式训练域联合仍0/634，PRODUCT HOLD。

**v1.2.277角向容量配对结论。** 第64次在31张冻结图的32甲上配对，原损失两组各256次每甲曝光及1024更新，新增角向分支初始64份输出逐字节一致。原分支和扩展分支均25/32，平均Boundary IoU分别0.775480及0.776695。扩展增益0.001214，20改善/12下降，2甲失去严格通过；28甲、相对增益及严格集合门未过，关闭本版扩展。原8甲在等曝光的32甲共享原分支中平均Boundary IoU由0.886997降为0.800915。两次试验更新总数与批次组成不同，下一步用同一初始权重和固定批次检验梯度相互牵制。全634质量仍0/634，PRODUCT HOLD。

旧微拟合学得权重与全部68候选的严格FP32复验独立通过train-only容量门：66正例全部保留、严格联合54/66（要求53）、拒识2/2且输出0像素，mean IoU/Boundary IoU/F1=0.972076/0.794394/0.978412。旧TF32容量、4096新头更新、11968分割步和全部历史失败保留。

完整内部val全50甲零推理归因已闭合：粗mask/实际精修/取消presence拒绝的反事实IoU≥0.75为47/43/47，三者原像素边界联合均0/50；4新增IoU失败来自presence拒绝，实际精修的边界IoU及F1单门各0/50，6/7拒识仍输出。四端解码完全相同，固定CUDA参考的数值修补不能恢复边界或拒识质量，该历史权重不晋升；WASM4项和全部旧失败保持，正式HOLD。

当前质量状态：原147/149仅训练域，光度规范化开发门false及旧失败保持。Stage B九尺寸合成完整图三端各9/9通过；真实训练域154随后仅完成严格CUDA/CPU ORT各154次，140例通过、14例仅mask数值超过1e-4，最大2.40326e-4，全部解码零像素差及presence一致，`cpuFullGatePassed=false`，WASM/WebGPU未执行，保留8未读取、300状态不变，见`model/reviews/cycle016-learned-train154-deployment-v1/cpu/report.json`。原生Resize实际控制32调用/32RAW已完成，12输入不同、4个精确2倍轴一致、最大4.57763671875e-05，实际输出支持CUDA融合逆乘与CPU正比例除法差异；坐标显式化完整图草案与18次CPU预算保留尚未消费，暂转为待恢复的运行时路线。未通过真实完整图保真、来源隔离质量、Stage A+B产品链或正式发布，PRODUCT HOLD。新来源val/留出、角标消融、整条链成本、真机/Beta/回滚仍缺，无批准生产身份。

两种原像素修边分支仍关闭、没有接入产品；旧GrabCut总2/141及置信度图割131/141、139候选3429像素变化保持原报告，不能因当前真值错误而改写成通过，也不能据其证明真实甲缘能力。最新完整18源训练前/最终预测/新真值对照为`model/reviews/cycle016-requalified134-training-v1/preview/index.html`。旧未终审参考预览及其错误提示原样保留作历史证据，现行训练资格只读§8.8新域报告。

正式来源独立评估尚未准入。原26差集中3源18甲开发StageA训练、1源8甲保留对照不回训、新2源8甲已消费开发诊断并加入StageB训练，余20源102甲仍禁止；原角色与全部历史失败保持，内部val不得回训。独立val≥30、新正负留出各≥100、角标消融、同身份完整数值/生产/ar-tryon、真机/Beta及双批准回滚仍缺。


## D. 原 §4.5 AR 试戴版本叙事段

**v1.2.268页面卡顿修复**：PostCSS插件按`postcss.config.mjs`中的绝对src路径扫描正式站样式，覆盖src内页面/组件，保留响应式断点。单个Next开发服务先预热再开验收浏览器，日志落盘，浏览器等待超时后检查原服务/编译日志，保持服务直至本次预览交付。基线首次HTTP164.94秒、PostCSS133.02秒；配置重载后首次30.41秒（复用既有编译缓存，属于观测对照），热访问29—51ms。桌面1440×1000、390×844与844×390实际浏览器重载、辅助线切换、样式及资源检查通过，耗时含networkidle和交互约1秒/次；相机未启动。证据`output/ar-page-hang-20261105-v1/report.json`。当前3000为已预热开发预览，完整生产构建终态仍待单独验证。

**v1.2.267贴合打磨（cuticle-fit-v5）**：开启「甲根辅助线」后，在相机画面拖动根部圆点平移、甲尖圆点调长、侧边圆点调宽；拖动撤销CSS镜像/尺寸缩放和双轴透视剪切，沿原校准范围工作，键盘沿用逐指滑杆。相机关键点过期或切换手指时停止拖动。静态模型纹理提取的方向参考扩展至两只手，各手独立排除手心/弯折候选并保持唯一身份，默认辅助定位仍为单手。手动提取若保留甲尖方向未知或方向分歧告警，同自动流程进入可翻转预览。alpha摄影纹理按本地相机亮度应用0.65—1的温和曝光系数。工程回归85项、双工程类型与局部lint通过；构建编译耗时和浏览器页面超时保留，真实相机贴合待实测，证据见`output/playwright/ar-fit-v5/verification.json`。本轮未调整模型权重或训练数据。

**v1.2.265贴合打磨（cuticle-fit-v4）**：甲根对齐改用alpha轮廓下部中心，摄影甲床宽度与完整纹理长度分别映射；根部短alpha过渡在离屏合成层完成。提取模型纹理时，通过本站MediaPipe资源对同一参考图提供方向参照，几何双向唯一配对保留模型mask与既有指位；明确手工方向优先，关键点缺失或配对含糊时沿用轮廓推断/人工复核。方向检测可取消且5秒超时；逐指180°翻转从当前解析方向起算。75项相关自动测试、双工程类型与局部lint通过；当前生产构建及浏览器验收结果见当日日志。真实相机甲根位置仍来自手部关键点估计，最终自然度继续实机复核。

v1.2.261工作区补充`cuticle-fit-v2`：独立长横轴投影、宽度校准与长度解耦、甲根锚定横移±40%和旋转±30°、甲床行宽排除甲尖装饰影响、cover反变换光照采样及待应用纹理翻转。当前为待验收修改；43项首轮相关测试修正角度环绕断言后通过，最终35项几何测试通过。首轮构建exit0，最终双工程类型检查与局部ESLint通过，宽度解耦后的最终构建/真实浏览器验证待补；已暂停3000/3100旧预览，恢复受自动审批用量额度限制。物理相机自然度待实机复核。 v1.2.263工作区补充`cuticle-fit-v3`甲根坐标平滑及完整位图离屏边界，73相关测试、双工程类型与局部lint通过；两个AR弹层宿主宽度全局规则迁入globals.css以兼容CSS Modules。默认构建CSS子进程失败、替代构建终态未知、浏览器页面验收未执行，随仅训练Goal恢复保持待验收。

**当前贴合契约（v1.2.259，`cuticle-fit-v1`）**：长度校准围绕甲根固定，摄影纹理按完整alpha的可见高度、甲床宽度及下半部中心对齐；长度滑杆同时作用于长甲设计。纹理单次连续绘制，保留自身透明轮廓，取消分条缩窄产生的缝隙；完整alpha检测替代8×8四角探针，避免尖甲被误判后再次套通用模板。摄影纹理附加高光/菲涅尔/颗粒/根部暗角降至原系数的12%，原图光影继续保留。默认隐藏轮廓高亮，校准区可切换甲根辅助线，并提供逐指「翻转纹理180°」与单级撤销。实时甲根仍由手部关键点估算，真实肤色甲缘定位及多设备自然度待实机复核。

浏览器模型纹理自v1.2.258使用4×4亚像素覆盖率抗锯齿：Worker保留原mask及独立覆盖率，原图纹理与连续alpha经提取、摆正后应用到逐指试戴。该处理针对栅格台阶；低对比甲缘偏移仍需模型/图像边界优化，自动流程和人工复核入口沿用既有设计。接口及证据见§6.4/§7。
