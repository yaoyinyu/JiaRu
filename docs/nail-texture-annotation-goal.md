# 美甲真实素材审核与标注目标

更新日期：2026-11-05  
当前状态：ACTIVE

## 目标

持续审核指定真实素材目录，完成可审核正样本的完整甲面精确标注与逐图复核，并按批次交付可追溯的冻结清单。

本轮活动目标：核实剩余素材的身份、来源与既有处置，完成首批原图源质量审核及精标准备。

## 核心要求

- 素材范围为 `E:\AI Project\Codex\JiaRu_image\真实素材\美甲图片素材`；继承已审100图634甲及其证据，当前不开展负样本工作。
- 逐张核对完整原图及全部可见甲面，准确标示甲缘并区分皮肤、阴影与装饰，检查漏标、重复、交叠和多边形合法性；疑难项单列待审。
- 保留来源、父血缘、数据角色与受保护隔离；源质量、逐甲原像素审核与来源资格均完成后方可给出准入结论。
- 每批完整审核结束后另立冻结版本，绑定原图、标注、来源、角色、准入结论和SHA-256；既有训练快照保持原样，返修另立版本。
- 本会话负责审核、标注、返修及训练数据交接，训练和模型调整由训练会话负责。

## 当前状态

- 现行 `model/reviews/cycle016-wevis-real-material-v1/batch037/cumulative-training-truth-index-v4.json` 含100张634甲；100份原图、标注和审核报告的SHA-256已核对。原图按哈希与指定目录匹配，100个身份各唯一。
- `batch037/current-source-disposition-v1.json` 记录444张已处置及779张未审；本轮核对指定目录共有1223张、1223个唯一SHA，444条处置均有对应文件。未审清单仍需来源与角色审核。
- 首张 `1/265.jpg` 已按完整原图初看，观察到五处甲面；拇指侧缘、遮挡与来源血缘待审。
- 另按未审身份SHA顺序初看 `2/760.jpg`、`2/692.jpg`、`2/454.jpg`：前后两图有局部露甲疑点，中间图观察到五甲；三图的原尺寸显示及来源角色需复核。初审见 `model/reviews/annotation-session-20261104-v1/source-screen-v3.json`。
- 四图已与scope、角色台账、现行处置及规范真值索引按SHA连接：3条有历史来源线索、1条来源未解；旧台账记录均无直接角色命中，当前受保护角色复核仍待完成。证据 `model/reviews/annotation-session-20261104-v1/four-source-metadata-audit-v1.json`。`2/692.jpg` 查看工具返回原文件哈希与2250×2250尺寸，实际显示原像素证据待核。该图已生成5个CPU候选轮廓，合法、界内且无正面积交叠；结合整图初看与坐标定位，发现戒指区域疑似误标、拇指甲疑似漏标及一枚花纹甲疑似局部覆盖，见 `model/reviews/annotation-session-20261104-v1/candidate-692-initial-correspondence-v1.json`。已另立五轮廓返修候选 `model/reviews/annotation-session-20261104-v1/candidate-692-repair-v1.json`：三个原候选及拇指、花纹甲的两个新SAM候选均待审，几何检查合法、界内且无正面积交叠。其余三甲已另生成SAM候选并组成 `candidate-692-repair-v2.json`，与旧轮廓的逐项IoU为0.955、0.928、0.835，两版均待审。历史冻结清单已按SHA确认 `2/692.jpg` 路径及来源组；第三甲的主要分歧区域已按原图坐标登记于 `candidate-692-difference-and-lineage-v1.json`。仍须完成逐甲原像素及来源角色复核；尚无新增通过精标或冻结交接。

- 新增完整原图初看 `3/1078.jpg`：四枚完整甲面及一处受遮挡的疑似甲面，原像素、遮挡范围与来源角色待审；清单与记录见 `model/reviews/annotation-session-20261104-v1/input-manifest-v3.json` 和 `source-screen-1078-v1.json`。历史冻结清单按完整SHA唯一绑定该图来源组 `real-material:2026-09-19:cycle015b5:0650`；现行真值索引和已读取角色台账无直接命中，完整父血缘与受保护角色仍待核，证据为 `source-1078-lineage-role-v1.json`。第三甲已另次捕获二值掩膜，生成多边形与既有结果逐点一致；相对该掩膜，填充多边形少覆盖316像素、额外覆盖197像素，真实甲缘仍待原图审核。证据 `sam-692-third-mask-report-v1.json`。

- 五图已对既有受保护参考清单的995个图片身份及所登记来源组做精确比对，均无直接命中；`1/265.jpg` 来源组未知，其余图的父血缘及感知近重复仍待核。证据 `model/reviews/annotation-session-20261104-v1/five-protected-reference-check-v1.json`。

- 新增完整原图初看 `3/1219.jpg` 与 `2/737.jpg`：前者拇指仅露侧边，待作整源排除复核；后者可见五处甲面，侧视拇指及半透明甲尖边界待审。历史冻结清单已按完整SHA唯一绑定两图来源组，既有受保护参考身份及已知来源组均无直接命中；父血缘与近重复仍待核。原尺寸显示与来源角色均待核；证据分别为 `model/reviews/annotation-session-20261104-v1/source-screen-1219-v1.json`、`source-screen-737-v1.json`。

- `2/737.jpg` 已生成五甲返修候选 `model/reviews/annotation-session-20261104-v1/candidate-737-repair-v1.json`：原四个候选加侧视拇指SAM候选；五多边形合法、界内且两两无正面积交叠，完整甲面、甲根、透明尖端、皮肤污染及来源角色仍待审核。几何记录为 `candidate-737-geometry-v1.json`。

- `3/1219.jpg` 与 `2/737.jpg` 的历史冻结来源及受保护参考精确比对记录：`model/reviews/annotation-session-20261104-v1/two-protected-reference-check-v1.json`。

- `2/692.jpg` 第三甲另存未简化外轮廓候选 `model/reviews/annotation-session-20261104-v1/candidate-692-repair-v3.json`：363点，栅格覆盖二值掩膜全部前景；二值掩膜的两处孔洞共67像素被外轮廓填入，含义及真实甲缘待审核。几何记录 `candidate-692-dense-contour-v1.json`。

- 完整原图初看 `2/714.jpg` 观察到十处甲面，右手拇指侧视待核；11个初始候选中两处位于戒指附近，另补一个拇指候选，组合为10个待审多边形 `model/reviews/annotation-session-20261104-v1/candidate-714-repair-v1.json`。十多边形合法、界内且45对零正面积交叠；完整甲缘、戒指误检、来源角色和显示链路待审核。

- `2/714.jpg` 历史冻结来源组已按完整SHA唯一绑定，既有受保护参考身份及已知组无直接命中，父血缘和近重复待核，记录 `source-714-protected-reference-check-v1.json`。新增完整原图初看 `3/1132.jpg`，观察五甲、边缘偏柔，甲根及源清晰度待原像素复核，记录 `source-screen-1132-v1.json`；两文件位于 `model/reviews/annotation-session-20261104-v1/`。

- 完整原图初看 `3/967.jpg`：双手八枚完整甲面可见，上方另有一处受遮挡的深色甲面边缘，待核是否整源排除；来源角色与原像素显示待核。记录 `model/reviews/annotation-session-20261104-v1/source-screen-967-v1.json`。

- 完整原图初看 `2/488.jpg`、`1/295.jpg`、`2/731.jpg`，分别登记裸色甲低对比、手机边缘甲缘及交叉遮挡疑点；原像素与来源角色待核。记录 `model/reviews/annotation-session-20261104-v1/source-screen-batch-v1.json`。

- `2/488.jpg` 已生成五个待审轮廓 `model/reviews/annotation-session-20261104-v1/candidate-488-v1/annotations/488.json`；五多边形合法、界内、两两零正面积交叠，裸色低对比甲缘及拇指侧缘仍待逐甲原图复核。几何证据 `candidate-488-geometry-v1.json`。

- `2/488.jpg` 历史来源组已按完整SHA唯一绑定，受保护参考身份及已知组无直接命中；父血缘与近重复待核。新增完整原图初看 `2/536.jpg` 十处甲面、`2/506.jpg` 七处甲面及一处受遮挡局部甲面；来源角色与原像素待核。记录 `model/reviews/annotation-session-20261104-v1/source-488-protected-reference-check-v1.json`、`source-screen-batch-v2.json`。

- `2/536.jpg` 初始候选12项达到预设上限，发现n8/n11及n10/n12两对正面积交叠；须回到完整原图核查重复、污染与漏检。记录 `model/reviews/annotation-session-20261104-v1/candidate-536-geometry-v1.json`。

- `2/536.jpg` 已按原图SHA唯一绑定历史来源组 `real-material:2026-09-19:cycle015b5:0108`；995项参考身份、现行真值及处置中无直接身份或已知组命中，父血缘、近重复与原像素逐甲审核待核。记录 `model/reviews/annotation-session-20261104-v1/source-536-protected-reference-check-v1.json`。

- 已初看15图统一做原图SHA、现行真值/处置与995项参考身份及已知来源组精确比对：均无直接命中；其中 `1/265.jpg` 和 `1/295.jpg` 的scope来源组为空，须另查父血缘，其余13图也待近重复与完整血缘核验。证据 `model/reviews/annotation-session-20261104-v1/screened-15-identity-crosscheck-v1.json`。

- `1/265.jpg` 与 `1/295.jpg` 的角色台账均缺来源组和血缘证据；现行100张真值均记录 `purchased-real-material:1` 采集集合，目录层级可作为追查线索，两图的具体来源关系仍未裁决。证据 `model/reviews/annotation-session-20261104-v1/folder1-lineage-leads-v1.json`。

- 显示链合成整图盲测：2250×2250图中央14像素高对比数字识读与事先冻结答案哈希一致；低对比甲缘与整图逐像素保真仍待验证。证据 `model/reviews/annotation-session-20261104-v1/native-display-blind-v1.json`。

- 显示链进一步盲测：2250×3000合成整图的中央与四角16像素低对比数字识读均与冻结答案一致；真实照片边界判读和整图像素保真仍待验证。记录 `model/reviews/annotation-session-20261104-v1/native-display-blind-v2-guess.json`。

- 重看 `2/692.jpg` 完整原图：五个返修候选的外接位置与五枚甲面大致对应；两枚花纹甲透明甲根、拇指甲根和两枚白甲侧缘继续列待精审，原像素传输与来源血缘仍待核。逐项记录 `model/reviews/annotation-session-20261104-v1/candidate-692-whole-revisit-v1.json`。

- 当前显示工具返回整图，但缺少模型实际原像素呈现的验证；合成盲测和整图初看尚未闭合逐甲精审。需可验证原像素呈现的审核工具或人工逐甲审核结果，才能作精标准入和冻结交接。

- `2/692.jpg` 的 `view_image` 返回载荷在工具侧解码后为1408777字节，SHA与原文件一致；本次未向模型发送图片，下游原像素呈现仍待核。记录 `model/reviews/annotation-session-20261104-v1/view-image-692-payload-verification-v1.json`。

- 2250×2250合成整图五处7像素低对比数字盲测与冻结答案一致；该控制覆盖文字识读，真实甲缘与完整原像素链路仍待核。证据 `model/reviews/annotation-session-20261104-v1/native-display-blind-v3-guess.json`。

- `2/692.jpg` 第三甲候选中的两处掩膜孔洞已定位至原图坐标 `[800,414,806,419]` 和 `[811,424,814,435]`，分别30和37像素；语义仍待逐甲审核。记录 `model/reviews/annotation-session-20261104-v1/candidate-692-n3-hole-locations-v1.json`。

- `2/692.jpg` 第三甲两处孔洞的原图RGB均值与相邻候选区域接近；已保存逐孔像素统计，孔洞所属语义与甲缘仍须视觉裁决。记录 `model/reviews/annotation-session-20261104-v1/candidate-692-n3-hole-rgb-v1.json`。

- `2/536.jpg` 完整原图复看后，暂排两处覆盖手指并与甲面候选交叠的大轮廓，另存10甲候选 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v1.json`；沿用原几何检查投影，10项界内合法、45对无正面积交叠，逐甲边缘和来源资格待审。

- `2/536.jpg` 返修候选 `n7` 对应左下拇指，右侧延伸进入指腹，列为必须返修；原图RGB与候选像素定位记录 `model/reviews/annotation-session-20261104-v1/candidate-536-n7-contamination-v1.json`。

- `2/536.jpg` 左下拇指已另用原图提示生成替换候选，存为 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v2.json`；n7右界由772收至670，10个轮廓合法界内、45对无正面积交叠。十甲的边缘、完整性及来源角色仍待审核。

- `2/536.jpg` 其余九甲已生成独立SAM对照候选；与现有候选逐甲IoU为0.796—0.925，`n11` 差异最大，须优先核对皮肤污染及完整甲缘。记录 `model/reviews/annotation-session-20261104-v1/candidate-536-nine-comparison-v1.json`；两组均待视觉裁决。

- `2/536.jpg` 的 `n11` 旧轮廓独有4923个栅格像素、RGB均值偏红；另存采用SAM对照轮廓的候选 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v3.json`，10项合法界内、45对无正面积交叠，实际甲缘和整图逐甲审核待完成。

- `2/536.jpg` 的 `n10` 旧轮廓独有2439像素整体偏肤色，另存采用对照轮廓的 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v4.json`；十轮廓合法界内且45对无正面积交叠。浅色 `n3` 两版差异及全部甲缘仍待逐甲审。

- `2/536.jpg` 已另存采用 `n1/n5/n6` 深色甲面对照轮廓的候选 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v5.json`；十项合法界内、45对无正面积交叠，逐甲精审及来源角色仍待完成。

- `2/536.jpg` 红色甲面 n2/n9 另存 SAM 对照返修候选 `model/reviews/annotation-session-20261104-v1/candidate-536-repair-v6.json`；十项合法界内、45对无正面积交叠，逐甲边缘及来源角色待审。

- 15张待审图已按SHA对照历史准入v2报告：13张关联 `historicalCycle015TrainAllocation`，含 `2/536.jpg`；另2张来源与真值待审。该记录为历史分配线索，实际消费、完整血缘和当前角色仍须核实；证据 `model/reviews/annotation-session-20261104-v1/screened-15-historical-allocation-crosscheck-v1.json`。此前995项参考清单无直接命中的结论仅覆盖该清单。

- 历史五批物化报告哈希核验后，15张中13张有原图SHA直接分配记录；`2/536.jpg` 为第五批 `train-positive`，历史标签SHA匹配、共9行，现候选为10项。数量差异及具体甲面须逐图核对；见 `model/reviews/annotation-session-20261104-v1/screened-15-exact-materialization-v1.json`。

- `2/536.jpg` 历史9项与现候选10项的原图尺寸网格对应已记录：n10与历史标签均无重叠，历史第8/9项与n11/n7的IoU分别0.187/0.215；均待完整原图逐甲裁决。证据 `model/reviews/annotation-session-20261104-v1/candidate-536-historical-correspondence-v1.json`。

- 1223个指定目录身份扣除444条现行处置后，779条均可按SHA连接历史准入v2：762条关联历史Cycle015训练分配，17条来源与真值待审。记录 `model/reviews/annotation-session-20261104-v1/undisposed-779-historical-admission-crosscheck-v1.json`；实际消费、当前角色与逐图审核仍须核实。

## 下一步计划

1. 核实十五张待审素材的原尺寸完整可视性、来源组及受保护角色，形成可复核的源质量裁决；继续按相同方式处理剩余素材。
2. 逐甲核对 `2/536.jpg` 新版十甲候选的甲根、侧缘、甲尖及皮肤污染，再处理 `2/692.jpg`、`2/737.jpg` 等疑难候选。
3. 批次全部通过后建立不可覆盖的新版本交接清单，核验逐文件哈希、角色和来源，供训练会话读取。
