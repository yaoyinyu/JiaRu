# WeVisOne-VL 本地抠图服务

把 Web 端「精细抠图」这条可选路径接在本机：浏览器端小模型做快速识别，用户在需要更精细的
指甲边缘时主动选择上传，由本机 GPU 上的 WeVisOne-VL 生成像素级 alpha 蒙版（matting），
不是二值 mask。

- 模型：`WeVisOne-VL-4B`（腾讯微信视觉，Apache-2.0），Qwen3-VL 底座 + 独立像素解码器
- 量化：optimum-quanto **int4**（TinyGemm），8 GB 显存可跑
- 服务：本机常驻 HTTP，仅监听 `127.0.0.1:8008`

---

## 1. 目录

```
model/VlM_Model/
├── matting.py            引擎：加载 + int4 量化 + 推理（也可单图命令行跑）
├── server.py             常驻 HTTP 服务（/health /stats /matte）
├── render_preview.py     把输出整成框选图 / 抠图 / 归一化纹理
├── shard_weights.py      把单文件权重切成分片（重下模型后必须跑）
├── client_example.mjs    Node 调用示例（/api/nail-matte 转发层的写法参考）
├── requirements.txt      已验证的依赖版本
├── models/
│   └── WeVisOne-VL-4B-bf16/   权重（不入库，见 .gitignore）
│       ├── model-0000{1..5}-of-00005.safetensors   5 个分片，各约 2.2 GB
│       ├── model.safetensors.index.json            分片索引
│       └── model.safetensors.unused                原单文件备份（9.2 GB，可删）
├── src/WeVisOne-VL-main/      上游 vendored 源码（随仓库入库，21 MB）
└── out/                  运行日志与调试产物（不入库）
```

**权重为什么是分片**：9.66 GB 单文件在本机内存紧张时，safetensors 的 `get_tensor` 会直接
触发 Windows 访问冲突（`0xC0000005`，崩在 `torch/storage.py __getitem__`），连 4.7 MB 的
小张量都读不出来；内存宽松时同一个文件又能读。切成 5 个 ~2.2 GB 分片后稳定复现为成功，
`transformers` 原生支持按 `model.safetensors.index.json` 分片加载。

### 1.1 入库范围与重建

只版本化自写的接入层：`matting.py`、`server.py`、`client_example.mjs`、`requirements.txt`、`README.md`（合计约 870 行）。

以下三类由本目录 `.gitignore` 排除，均为可重建内容：

| 排除项 | 体积 | 重建方式 |
| --- | --- | --- |
| `models/WeVisOne-VL-4B-bf16/` | 18.0 GB（分片 9.1 + 原文件备份 9.2） | 从 Hugging Face `tencent/WeVisOne-VL-4B` 下载权重与 `mask_decoder.pt`，然后 `python shard_weights.py models\WeVisOne-VL-4B-bf16\model.safetensors models\WeVisOne-VL-4B-bf16 2400000000` 切片，最后删掉原单文件 |
| `src/WeVisOne-VL-main/` | 21 MB | `git clone https://github.com/Tencent/WeVisOne-VL.git`（Apache-2.0），目录改名为 `WeVisOne-VL-main` |
| `out/` | 与运行次数相关 | 运行日志与调试产物，自动生成 |

权重确认可用后，`model.safetensors.unused` 可以直接删掉省 9.2 GB；分片本身不再依赖它。

`matting.py` 通过 `sys.path` + `import wevisone_vl.engine` 依赖 `src/`；克隆后无需改代码即可运行，只有 `src/` 缺失时才报导入错误。

---

## 2. 环境

已验证组合（Windows 11 + RTX 4060 Laptop 8 GB + CUDA 12.8 驱动）：

| 包 | 版本 |
| --- | --- |
| Python | 3.11.12 |
| torch / torchvision | 2.11.0+cu128 / 0.26.0+cu128 |
| transformers | 5.12.1 |
| accelerate / safetensors | 1.14.0 / 0.8.0 |
| optimum-quanto | 0.2.7 |
| qwen-vl-utils / Pillow / numpy | 0.0.14 / 12.3.0 / 2.2.6 |

**当前解释器**（本机已验证可用）：

```
C:\Users\YaoYinyu\.qbot-dsh\runtime\python\python.exe
PYTHONUSERBASE=C:\Users\YaoYinyu\.qbot-dsh\python-user
```

这个解释器由 Qbot 托管，卸载该工具链后会消失。要脱离它，见第 8 节。

---

## 3. 启动

```powershell
cd "E:\AI Project\Codex\JiaRu\model\VlM_Model"
$env:PYTHONUSERBASE="$env:USERPROFILE\.qbot-dsh\python-user"
$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"; $env:PYTHONUNBUFFERED="1"

python server.py                        # 默认 127.0.0.1:8008，像素预算 589824
python server.py --port 8010             # 换端口
python server.py --max-pixels 589824     # 与默认一致，显式写法便于日志核对
python server.py --max-pixels 1048576    # 实测会少解 `<OBJ>`，不作为默认
```

就绪日志形如：

```
[08:42:47] 就绪：WeVisOne-VL-4B-bf16 | quant=int4 | 总加载 9.5s
[08:42:47] 监听 http://127.0.0.1:8008 | 端点 /health /stats /matte | 鉴权 开/关
```

**加载阶段会占满一次显存（约 9.5s），此后常驻 5.26 GiB，不要反复重启。**

单图命令行调试（不需要起服务）：

```powershell
python matting.py --image "某张手部照片.jpg" --query "指甲" --out out
# 输出 out/<图名>/alpha-0.png ... 与 result.json
```

要看得懂的产物（框选图、单枚抠图、旋正纹理）：

```powershell
python render_preview.py out\nail-01 out\input\nail-01.jpg out\nail-result
# boxes.jpg / cutout-<i>.png / texture-<i>.png / cutouts-sheet.png / nails.json
```

---

## 4. 连接

### 4.1 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8008/health
```

```json
{
  "ok": true, "ready": true, "busy": false,
  "model": "WeVisOne-VL-4B-bf16", "quant": "int4", "device": "cuda",
  "maxPixels": 589824, "loadSeconds": 81.2,
  "requests": 0, "failures": 0, "lastLatencySeconds": null, "uptimeSeconds": 14.1
}
```

### 4.2 抠图 `POST /matte`

请求：

```json
{
  "image": "data:image/jpeg;base64,...",
  "query": "指甲",
  "task": "matting",
  "boxes": [[284,470,411,540], [396,763,494,890]]
}
```

| 字段 | 说明 |
| --- | --- |
| `image` | base64 data URI；也接受纯 base64。调试可用 `imagePath` 传本地路径 |
| `query` | 文本描述，默认「指甲」；`task=visual_prompt` 时配合 `boxes` 使用 |
| `task` | `matting`（默认）/ `segmentation` / `visual_prompt` |
| `boxes` | 仅 `visual_prompt` 使用，像素坐标 `[x1,y1,x2,y2]` |

> 本权重下 `visual_prompt`（带框四种写法）实测恒定返回 0 实例，业务侧 refine 统一走 `task=matting`；`segmentation` 与 `matting` 的上游提示词完全相同。

响应（节选）：

```json
{
  "ok": true,
  "prompt": "Locate the instances that match the following description and provide the alpha mattes: 指甲.",
  "response": "<ref>指甲</ref><box><263><327><381><375><OBJ>,...",
  "width": 1080, "height": 1440,
  "instances": [
    {
      "index": 0,
      "box": [284.0, 470.9, 411.5, 540.0],
      "box01": [0.263, 0.327, 0.381, 0.375],
      "bbox": [285, 471, 412, 540],
      "area": 3972,
      "alphaPng": "data:image/png;base64,...",
      "width": 1080, "height": 1440
    }
  ],
  "metrics": { "inference_s": 14.05, "instance_count": 4, "load_s": 9.5 },
  "model": "WeVisOne-VL-4B-bf16", "quant": "int4"
}
```

- `box` 是**像素坐标**（已由上游 0..1 归一化值换算），可直接和前端候选框算 IoU
- `bbox` 是 alpha > 127 的外接框，用于校验 `box` 是否对得上
- `alphaPng` 是单通道 PNG，值 0–255，不是二值 mask

### 4.3 状态码

| 码 | 含义 | 调用方动作 |
| --- | --- | --- |
| 200 | 成功 | 用返回的 alpha |
| 400 | 参数/图片不合法、长边超 4096 | 提示用户换图 |
| 401 | 设置了 `--token` 但没带 | 检查 `Authorization` |
| 413 | 请求体 > 12 MB | 前端先压缩 |
| **503** | **GPU 正在处理另一张** | **回退浏览器本地结果，不要重试** |
| 504 | 超过 120s | 同上 |
| 500 | 推理异常 | 记录 `failures`，回退本地 |

### 4.4 Node 侧调用

见 `client_example.mjs`：

```powershell
node client_example.mjs "某张手部照片.jpg" "指甲"
```

它同时给出 `matchByIou()`：把服务端返回的实例按框 IoU 对回浏览器候选。

---

## 5. 实测资源与耗时

显存/内存为 `torch.cuda.max_memory_allocated` 与进程工作集实测值。

| 项目 | 数值 |
| --- | --- |
| 显存（加载完成后） | 5.26 GiB / 8.00 GiB |
| 显存峰值（设备级，nvidia-smi） | 7817 MiB @589824（8 GiB 卡余量约 370 MiB） |
| 进程内存峰值 | 10.1 GiB（含 CPU 端 bf16 权重复制） |
| 磁盘 | 18.0 GB（分片 9.1 GB + 原文件备份 9.2 GB；删备份后 9.1 GB） |
| 启动到就绪 | 72–81s（本轮 5 分片 int4 实测；`torch.cuda.max_memory_allocated` 在 Windows 会因显存超售报 9+ GiB，不能当设备峰值） |

单图耗时（实测，全部 int4）：

| 场景 | 实例数 | 推理 |
| --- | --- | --- |
| `hero-hand` 1200×1499（单手 5 甲） | 5 | 14.5s |
| `ai-look-1/2/4/5` 1024×1024（各 5 甲） | 5 | 12.3–13.0s |
| `ai-look-3` 1024×1024（双手 9 甲） | 9 | 18.7s |
| `ai-look-6` 1024×1024（5 甲，中间指 3D 珠宝甲漏 1） | 4 | 11.8s |

（2026-10-28，int4、`max_pixels=589824`、业务同款 1600 长边 JPEG q0.85；`ai-look-6` 在 262144/1638400 同样 4/5，属语义限制而非分辨率。）

**耗时主要取决于生成的 `<OBJ>` 数量，不是图片大小**：每个实例多 4–5 个自回归 token，
所以「十枚长甲」的双手照比「一个人」慢 4–5 倍。前端做等待提示时按实例数分档估：
1 枚约 6s、4–5 枚约 12–16s、8 枚以上 20–30s。

`--max-pixels` 默认 589824 由 2026-10-28 参数扫描确定：262144/589824/1638400 在 7 张业务图上实例数与 `<OBJ>` 一致，589824 单图 11.8–18.7s；1048576 档对 `hero-hand` 只解出 1 个 `<OBJ>`（响应文本含 5 个框，独立复跑可复现）；2359296 需 21.8s 且无额外收益。分辨率对 mask 几何影响有限（相邻档二值 alpha IoU 0.96–0.99、面积差 ±3%），瓶颈在自回归解码。bf16 卸载（`--quant none --device-map 5`）虽 5/5，但单图 51–55s，只作对照。

---

## 6. 与前端对接的四条硬约束

1. **N 进 N 出，不要按 index 对齐。**
   前端的指位是按「候选数量 + 顺序」推出来的（`finger-assignment.ts`：4 枚 → `[1,2,3,4]`，
   ≥5 枚 → `[0..4]`）。服务端多返或少返一个实例，所有指位就整体错位。
   → 用 `matchMasksToCandidates()` 按「实例中心落入候选框优先、IoU≥0.15 兜底」匹配；匹配不到就**保留本地掩膜**，候选数量永不改变。2026-10-28 UI 实测 `hero-hand` 服务返回 5 实例但只替换 3/5：两个本地 MediaPipe 候选框偏移且偏小（与服务实例框 IoU 0.075/0.049），按该规则保守跳过，未错误替换。

2. **坐标系要反变换。**
   浏览器端 `NailMask{width,height,data,originX,originY,scale}` 是**局部裁剪**坐标；
   服务端 alpha 是**全图**尺寸。替换前必须按 `originX/originY/scale` 映射回去。

3. **alpha 不是二值 mask。**
   `NailMask.data` 是 `Uint8Array(0-255)`，放 alpha 类型上没问题，但下游
   `extract-mask-texture.ts` 若按阈值二值化处理，透明甲尖的软边会被吃掉——
   那正是这条路径的价值所在，接入前必须确认。

4. **503 就是降级信号。**
   GPU 并发固定 1，忙时立即 503。前端应静默回退本地结果，不要排队、不要重试。

---

## 7. 已知问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `0xC0000005` 访问冲突，崩在 `transformers/core_model_loading.py` → `torch/storage.py __getitem__` | 单文件 9.66 GB 权重在内存紧张时，safetensors 读张量会崩（同一文件内存宽松时正常） | 已改用 5 个 ~2.2 GB 分片；重下模型后跑 `shard_weights.py`。`HF_DEACTIVATE_ASYNC_LOAD=1` 已在 `matting.py` 里默认设置，避免多线程同时读 mmap |
| `OSError: 页面文件太小 (1455)` | 本机页面文件固定 16 GB，加载瞬间提交峰值偶尔打满 | 重试一次即可；必要时调大页面文件 |
| `AcceleratorError: CUDA error: unknown error` + `fatal : Memory allocation failure` | quantized 模型在**非加载线程**推理 | 已在 `server.py` 里固定「主线程推理、HTTP 子线程只收发」，不要改成线程池推理 |
| 首次请求比后续慢 2–4s | CUDA kernel 首次编译/预热 | 正常，可在部署后先打一张热身图 |
| 同图两次返回实例数不同（4 vs 5） | 自回归生成对分辨率敏感 | 固定 `--max-pixels` 后基本稳定；不要靠它做「必得几枚」的断言 |
| 模型给出的框数 > alpha 数 | 没有 `<OBJ>` 标记的框不产生掩膜（实测双手 10 枚甲：10 个框、9 张 alpha；`hero-hand` 在 1048576 档：5 个框、1 个 `<OBJ>`） | 前端必须按几何匹配、匹配不到就保留本地掩膜，**不能假定 N 进 N 出**；`<OBJ>` 数才是实例数，框数只是候选框 |

---

## 8. 脱离 Qbot 解释器（可选）

当前解释器属于 Qbot 工具链，卸载后会消失。要在项目内自持：

```powershell
# 用项目自己的 Python 3.13 建 venv（torch/transformers 已在该解释器里）
& "C:\Users\YaoYinyu\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv --system-site-packages
.\.venv\Scripts\python.exe -m pip install optimum-quanto==0.2.7
.\.venv\Scripts\python.exe server.py
```

注意：该解释器是 torch 2.12.1+cu126，**int4 的 TinyGemm 内核尚未在该 torch 版本上验证**。
切换前先用 `matting.py` 跑一张图确认 int4 正常；若不正常，回退到第 2 节 3.11 环境，
或在 `.venv` 里安装 `requirements.txt` 的 torch 2.11.0+cu128。

---

## 9. 许可与使用边界

- 模型许可 Apache-2.0，官方限定研究用途，不得用于识别特定个人
- 本服务只做「指甲/手部/物体抠图」，不做人脸识别、不做身份推断
- 图片只在内存中解码，不落盘、不入库、不转发第三方；日志只记方法、路径、状态与耗时
