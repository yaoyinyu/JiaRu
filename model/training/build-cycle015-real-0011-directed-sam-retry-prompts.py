#!/usr/bin/env python3
"""构建 0011 顶部拇指一次定向 SAM 重试提示（prompts v2）。

背景（2026-09-19 原分辨率复核）：
- cycle015_real_0011 机器计数 exact（5/5），但 overlay 原分辨率复核发现：
  1) src3（conf 0.25）外接框完全落入 src5（conf 0.79）外接框内，为同一甲面的
     碎片框，不是独立甲面；
  2) 顶部拇指甲（琥珀透明、斜向、甲面完整可见、无触边无遮挡）完全漏检，
     v1 预标注无任何候选。
- 等效漏检 1 枚完整甲：按 under-count 纪律锁定完整甲分母 5，执行恰好一次
  定向 SAM 重试——删除 src3 碎片提示（其甲面由 src5 覆盖，真甲覆盖数不变），
  以原分辨率复核裁片目测框补充 src6 拇指提示，提示总数保持 55。

证据：review-crops/0011-top-crop.png（x:675-1800, y:0-562, 1.5x 放大）；
v3勘误：v2 目测框换算错误（误框指腹+袖口），经 review-crops/0011-thumb-grid-check.png
网格叠加复核更正为真甲面边界，v2 重试产物（n05 渔网噪声 mask）保留作废证据。

v1 prompts 及其来源链保持原样；v2 记录 v1 哈希与重试元数据。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

IMAGE_W = 2250
IMAGE_H = 2250

# 手工目测 v3（0011-thumb-grid-check.png 网格复核更正：v2 目测框 [920,45,1220,198]
# 误框指腹+袖口，SAM 输出渔网噪声片段；真甲面外接 x[1150,1460] y[92,275]），
# 0.15 padding 与 center-negative-corners 四角内缩 2% 与 PCA 生成器同构。
MEASURED = {
    "nailPolygonBoundsPx": [1150, 92, 1460, 275],
    "boxPx": [1103, 64, 1507, 303],
    "positivePointsPx": [[1230, 185], [1310, 190], [1400, 165]],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value: float, span: int) -> float:
    return round(min(1.0, max(0.0, value / span)), 6)


def build_added_prompt() -> tuple[list[float], list[list[float]], list[list[float]]]:
    bx1, by1, bx2, by2 = MEASURED["boxPx"]
    inset_x = (bx2 - bx1) * 0.02
    inset_y = (by2 - by1) * 0.02
    box = [normalize(bx1, IMAGE_W), normalize(by1, IMAGE_H), normalize(bx2, IMAGE_W), normalize(by2, IMAGE_H)]
    positives = [[normalize(x, IMAGE_W), normalize(y, IMAGE_H)] for x, y in MEASURED["positivePointsPx"]]
    negatives = [
        [normalize(bx1 + inset_x, IMAGE_W), normalize(by1 + inset_y, IMAGE_H)],
        [normalize(bx2 - inset_x, IMAGE_W), normalize(by1 + inset_y, IMAGE_H)],
        [normalize(bx1 + inset_x, IMAGE_W), normalize(by2 - inset_y, IMAGE_H)],
        [normalize(bx2 - inset_x, IMAGE_W), normalize(by2 - inset_y, IMAGE_H)],
    ]
    return box, positives, negatives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts-v1", required=True)
    parser.add_argument("--review-crop", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    v1_path = Path(args.prompts_v1)
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    if v1.get("decision") != "sam_candidate_only_not_training_truth" or v1.get("promptCount") != 52:
        raise ValueError("v1 prompts 合同无效")
    if v1.get("imageCount") != 11:
        raise ValueError("v1 prompts 图片数漂移（期望11图，0002已排除）")

    target = next((item for item in v1["images"] if "0011" in item["fileName"]), None)
    if target is None:
        raise ValueError("v1 prompts 缺少 0011")
    if target["sourceIndices"] != [1, 2, 3, 4, 5] or len(target["boxes"]) != 5:
        raise ValueError(f"0011 提示结构漂移：{target['sourceIndices']}")

    keep = [i for i in range(5) if target["sourceIndices"][i] != 3]
    if len(keep) != 4:
        raise ValueError("碎片提示删除后数量异常")
    box, positives, negatives = build_added_prompt()
    new_image = {
        "fileName": target["fileName"],
        "sha256": target["sha256"],
        "sourceGroup": target["sourceGroup"],
        "expectedFullyVisibleNails": target["expectedFullyVisibleNails"],
        "sourceIndices": [target["sourceIndices"][i] for i in keep] + [6],
        "boxes": [target["boxes"][i] for i in keep] + [box],
        "positivePoints": [target["positivePoints"][i] for i in keep] + [positives],
        "negativePoints": [target["negativePoints"][i] for i in keep] + [negatives],
        "promptModes": ["center-negative-corners"] * 5,
        "boundedOverpredictionTrim": target["boundedOverpredictionTrim"],
        "directedRetry": {
            "applied": True,
            "droppedFragmentSourceIndex": 3,
            "droppedFragmentReason": "src3 外接框完全落入 src5 外接框内，为同一甲面碎片框（原分辨率 overlay 复核）；该甲面由 src5 提示继续覆盖，真甲覆盖数不变",
            "addedSourceIndex": 6,
            "addedReason": "顶部拇指甲完整可见但 v1 预标注完全漏检，按 under-count 一次定向重试纪律补充人工目测提示；完整甲分母锁定 5",
            "addedPromptMeasurement": MEASURED,
            "addedPromptMeasurementSource": "原分辨率复核裁片 1.5x 放大目测",
            "promptCountAfterRetry": 5,
            "expectedFullyVisibleNails": 5,
        },
    }

    document: dict[str, Any] = {
        "schemaVersion": 1,
        "source": "hash-bound YOLO coarse polygons with PCA long-axis internal multipoints; 0011 one directed SAM retry (fragment drop + manual measured thumb prompt)",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "promptsV1": {"path": str(v1_path), "sha256": sha256_file(v1_path)},
            "reviewCrop": {"path": str(args.review_crop), "sha256": sha256_file(Path(args.review_crop))},
        },
        "settings": dict(v1.get("settings") or {}),
        "imageCount": v1["imageCount"],
        "promptCount": v1["promptCount"] - 1 + 1,
        "trimmedOverpredictionCandidateCount": v1.get("trimmedOverpredictionCandidateCount"),
        "images": [new_image if item["fileName"] == target["fileName"] else item for item in v1["images"]],
        "skippedImages": v1.get("skippedImages"),
        "policy": dict(v1.get("policy") or {}),
        "trainingUse": "prohibited",
        "formalPromotionAllowed": False,
        "releaseState": "hold",
        "productState": "hold",
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "decision": document["decision"],
        "promptCount": document["promptCount"],
        "directedRetry": new_image["directedRetry"]["applied"],
        "sourceIndices0011": new_image["sourceIndices"],
        "output": str(out_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
