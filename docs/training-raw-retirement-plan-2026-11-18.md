# 被取代轮次训练过程 RAW 退役候选清单（2026-11-18）

状态：**已批准并于 2026-11-18 执行完成**（用户条件批准「若不影响记录完整性则批准执行」，条件已满足：7,503 个保留文件全量重验字节一致）。执行登记、逐文件冻结清单、删除事件与重验报告在 `model/reviews/training-raw-retirement-20261118-v1/`；批准时原文字节快照存于该登记 `plan-as-approved-20261118.md`（SHA-256 与冻结绑定一致）。

## 1. 口径依据

2026-11-18 用户批准分层保留口径：机制保留、评估级证据和发布绑定证据保留，只退役被取代轮次的训练过程；每轮记录报告和判决信息保留，只清理旧的训练过程。执行细则已写入 [冻结证据与重放](agent-rules/evidence-replay.md)「捕获保留与存储维护」，白皮书§11.1 同步（v1.2.324）。

体积快照：2026-11-18 09:35 实测（`output/retirement-scan-20261118.json`，本地不入库）。batch037 共 190 个目录、98.8GB，其中训练过程 RAW 64.5GB、逐步事件 2.5GB、checkpoint 14.4GB。快照后队列仍在写入，执行时以冻结清单的实测字节为准。

## 2. 分类定义

| 类别 | 判定 | 处置 |
| --- | --- | --- |
| 发布绑定 | 目录内权重 SHA 被当前发布身份或导出验证引用 | 完整保留 |
| 在途阶段链 | 第81—90次阶段链与第92次三臂队列（含其 precheck/evaluation/closeout/results 目录） | 完整保留 |
| 评估级/诊断保留 | 逐甲预测、评估合同、终评/结项/可达性判决、pack/fit 诊断、缓存构建报告、真值修复产物 | 完整保留 |
| 可退役 | 被取代轮次：不在发布绑定与在途阶段链内，且在途合同零引用其训练过程文件 | 仅退役训练过程（§3 范围），报告/判决/末权重/首末接缝保留 |

## 3. 退役范围（每个候选目录统一适用）

退役：`train/raw/**`（逐步 RAW .npz）、`train/events/**`（逐步事件流水）、`train/checkpoints/**` 中的中间 checkpoint、`train/ultralytics/` 运行时残留；嵌套 recovery/resume 训练目录同样适用。

保留：目录内全部计划/认领/终态/重放/结项/评估报告与文档快照（plan、claim、terminal、replay、report、first-loss、initial-parity、closeout*、evaluation*、*-snapshot* 等）；末权重（last-weights.pt / last-fp32.pt）；每个 checkpoints 目录的首、末文件及 reconstructed-*/restored-* 恢复接缝；全部评估级子目录。

## 4. 退役候选（16 个目录，含 5 个嵌套训练目录，合计约 47.5GB）

| # | 目录（batch037 下） | 被取代依据 | 退役估算 |
| --- | --- | --- | --- |
| 1 | real-only100-pixel-radial-training-v1 | 像素径向24轮，白皮书§11.1 明列被取代；checkpoint 已于11-04退役至首末接缝 | RAW 13475MB + 事件 48MB ≈ 13.5GB |
| 2 | real-only100-stage-b-v1 | 原 Stage B 16轮；发布 Stage B 源权重在 geometry-boundary-training-v1（SHA 实测匹配） | RAW 8008MB + 事件 13MB ≈ 8.0GB |
| 3 | stage-b123-native-training-v2 | native 分支8轮实验，几何64组合取代 | RAW 4715MB + 事件 6MB ≈ 4.7GB |
| 4 | real-only100-geometry-cached-training-v1（含 interruption-recovery-v1） | 几何缓存训练中断于 step-07456 及恢复段，geometry-boundary-training（几何64末权重）取代 | 主目录 RAW 479 + 事件 85 + 中间cp约320；恢复段 RAW 2150 + 事件 416 + 中间cp约1440 ≈ 4.9GB |
| 5 | real-only100-hard-boundary-v1 | 硬边界监督分支，邻域系列取代 | RAW 3049MB + 事件 5MB ≈ 3.1GB |
| 6 | real-only100-neighborhood-capacity-continue256-v1 | 容量探针256轮，结论已登记（92计划引用累计暴露512 epochs 为历史口径，仅引用脚本SHA） | RAW 1326 + 事件 240 + 中间cp约1322 ≈ 2.9GB |
| 7 | real-only100-neighborhood-capacity-full256-v1 | 同上 | ≈ 2.9GB |
| 8 | real-only100-neighborhood-constant256-v1 | 恒定学习率探针256轮，结论已登记 | RAW 1327 + 事件 237 + 中间cp约903 ≈ 2.5GB |
| 9 | real-only100-neighborhood74-balanced256-v1 | 74系均衡采样探针，81+系列取代 | RAW 752 + 事件 134 + 中间cp约749 ≈ 1.6GB |
| 10 | real-only100-neighborhood74-recovery-v1 | 74系恢复段，同上 | RAW 575 + 事件 103 + 中间cp约569 ≈ 1.2GB |
| 11 | real-only100-neighborhood128-v1（含 recovery-v2/v3） | 早期128轮探针及两次恢复，81+系列取代 | 主目录约440 + recovery-v2约206 + recovery-v3约578 ≈ 1.2GB |
| 12 | real-only100-visual-neighborhood-v1 | 视觉邻域32轮探针，被取代 | RAW 165 + 事件 29 + 中间cp约111 ≈ 0.3GB |
| 13 | real-only100-context-radial-training-v1（含 resume-v1） | 上下文径向23轮探针，被取代；唯一 checkpoint step-03739 按首末接缝保留 | RAW 121 + 事件 48 + resume约4 ≈ 0.17GB |
| 14 | real-only100-full-boundary-training-v1（含 resume-v1） | 全634边缘监督64轮，白皮书§11.1 明列被取代；首末 checkpoint 保留 | RAW 84 + 事件 16 + resume RAW 244 + 事件 51 + 中间cp ≈ 0.4GB |
| 15 | real-only100-biou-cached-training-v2 | Boundary IoU 缓存16轮探针，被取代 | RAW 82 + 事件 14 + 中间cp约53 ≈ 0.15GB |
| 16 | real-only100-hard-boundary-recovery-v1 | hard-boundary 恢复片段，随主分支取代 | RAW 约3MB |

## 5. 保留清单（要点）

- **发布绑定（完整保留）**：`real-only100-stage-a-v1`（23.9GB，Stage A 源权重 `5ef15470…` = train/last-fp32.pt，导出验证实测绑定；其 21.8GB RAW 本轮不动，如需退役另行单独决策）；`real-only100-geometry-boundary-training-v1`（0.44GB，Stage B 源权重 `161e10be…` = train/last-weights.pt）。
- **在途阶段链（完整保留）**：neighborhood81-auxiliary-full128-v2、85-image-order、86-joint634、87-differential634-v2、88-continuation634、89-truthv5、90-side634、92-smoothness-lambda0/lambda005/lambda010 及各自 precheck/evaluation/closeout/results/failure-diagnostic 目录。
- **评估级/诊断（完整保留）**：全部 *-evaluation-*、*-closeout-*、*-results-*、reachability/fit/pack/coordinate-bars 目录；geometry-cache-v1（在途计划引用其 build/report.json 与缓存输入）；fixed512-cache、dataset、shared52-71 真值修复产物；stage-a123-clean/paired。
- **batch037 之外本轮一律不动**：数值诊断捕获批次（layerwise、upstream-math、feature-cross 等约60GB，属另一类证据，另行决策）、geometry64-browser-parity-v1 与 edge-refine-geometry64-v1（发布对拍证据）、checkpoint-retirement 登记、VlM_Model（用户明确不动）、qwen3vl8b-official-v1。

## 6. 执行流程（批准后）

1. **冻结清单**：逐目录实测退役子路径的文件数、字节数、SHA-256 与目录终态，生成不可覆盖的退役计划并绑定本清单 SHA；候选目录若被队列新写入（终态变化）即剔除并更新清单。
2. **引用复核**：重跑在途合同引用检查（92 三臂 plan/evaluation-contract、cycle097 基线、导出验证、发布 manifest 链），确认零引用候选训练过程文件后方可执行。
3. **退役登记**：在 `model/reviews/training-raw-retirement-20261118-v1/` 写入计划、删除事件（逐文件路径/字节/SHA）、终态观察与验证报告；原子操作、拒绝越界与并发写，操作事件持久化后执行。
4. **执行后重验**：全量重验保留路径/SHA 与权威报告一致；分别报告逻辑体积、实际分配空间与磁盘剩余变化。
5. **重放缺失登记**：退役目录写入 `TRAINING-PROCESS-RETIRED` 登记（退役范围、日期、批准依据）；后续对这些轮次的完整重放须如实输出输入缺失失败并保留，历史判决、旧失败与原分母原样保留。
6. **文档同步**：白皮书§11.1 登记执行结果（版本顺延），当日 dev-log 记录版本标记与退役登记 SHA。

## 7. 代价与风险

- 退役轮次永久失去训练过程完整重放能力；其结论仍可由保留的评估级预测、报告与判决复核。
- 发布链与在途训练零影响（引用核查通过）；门有效性审计所需的 634 甲评估预测在 89/90 evaluation 目录内，完整保留。
- 若未来质疑某退役轮次"训练过程是否按记录发生"，只能依据终态报告与事件汇总，无法逐步独立复核——此为本口径的已接受代价。

## 8. 验证方式

- 清单字节与 `output/retirement-scan-20261118.json` 快照一致（执行时重新冻结）；
- 引用核查脚本输出零命中（在途合同对候选 raw/checkpoints/events 的引用）；
- 执行后保留路径 SHA 全量重验 ok=true，退役登记与删除事件逐文件可对照。