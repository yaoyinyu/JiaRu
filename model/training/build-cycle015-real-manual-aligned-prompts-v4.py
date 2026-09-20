#!/usr/bin/env python3
"""构建循环015真实素材首批人工多边形对齐提示（prompts v4）。

背景：
- 13枚REWORK甲经人工多边形返修（annotations v3）。人工多边形修正了YOLO候选框
  的位置/大小偏差，因此与原始SAM提示框的bounds containment下降（0004-n4、
  0009-n2、0011-n5、0008-n5中心擦线）——为满足AGENTS.md「人工多边形须通过
  提示/外接框几何审计」，对这13枚以人工多边形为基准重新生成同构提示：
  box=polygon外接框+0.15padding；positive=PCA长轴三点（与PCA生成器同构）；
  negative=四角内缩2%。
- 其余39枚提示保持v3不变（SAM输出未变，审计语义保持mask-提示一致性）。
- 同时登记两处终审修正：0005-n3右缘回缩（消除与n1的36.25px²交叠）、
  0008-n5上缘贴合反光线（消除提示框中心0.5px擦线）。0011-n4错位重绘
  （v3人工多边形误描到中指/无名指之间的错误位置）已改由返修脚本
  build-development-cycle-015-real-manual-polygon-repair.py 直接承载
  重测后的正确多边形（0011-n4-zoom-2x.png证据），本脚本不再登记override。

prompts v4仅用于几何审计与证据链绑定；SAM标注已由annotations v3承载。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

WS = Path(r"E:\AI Project\Codex\JiaRu_image\审核工作区\2026_9_19_cycle015_real_material_annotation_workspace_v3")
ANN_V3 = WS / "sam-annotations-v3-repaired" / "annotations"
IMAGES = WS / "images"

# 终审修正（prompt对齐之外的多边形微调）：(图号, 甲id, 修正后多边形)
# 注：0011-n4错位重绘原在此处登记，现改由返修脚本直接承载正确多边形
#（0011-n4-zoom-2x.png重测），此处仅保留0005-n3与0008-n5两处微调。
FINAL_POLYGON_OVERRIDES: dict[tuple[str, str], list[tuple[int, int]]] = {
    ("0005", "n3"): [(1035, 2298), (1092, 2280), (1145, 2278), (1185, 2290), (1198, 2312), (1216, 2352), (1226, 2396), (1216, 2442), (1180, 2468), (1120, 2482), (1068, 2480), (1028, 2460), (998, 2428), (978, 2392), (972, 2350), (984, 2315), (1010, 2298)],
    ("0008", "n5"): [(1255, 488), (1300, 500), (1360, 503), (1430, 500), (1485, 494), (1525, 480), (1560, 452), (1588, 415), (1608, 362), (1618, 300), (1618, 232), (1602, 188), (1585, 183), (1555, 230), (1500, 285), (1445, 335), (1410, 362), (1355, 425), (1288, 470)],
}

# 13枚人工返修甲（prompt对齐对象）
MANUAL_REPAIRED = [
    ("0001", "n4"), ("0003", "n2"), ("0003", "n4"), ("0004", "n3"), ("0004", "n4"),
    ("0005", "n3"), ("0006", "n5"), ("0007", "n5"), ("0008", "n5"), ("0009", "n2"),
    ("0009", "n4"), ("0011", "n4"), ("0011", "n5"),
]

BOX_PADDING = 0.15


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(value: float, span: int) -> float:
    return round(min(1.0, max(0.0, value / span)), 6)


def pca_prompts(poly: list[tuple[float, float]], width: int, height: int) -> tuple[list[float], list[list[float]], list[list[float]]]:
    points = np.asarray(poly, dtype=np.float64)
    x1, y1 = np.floor(points.min(axis=0)).astype(int)
    x2, y2 = np.ceil(points.max(axis=0)).astype(int)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width - 1, x2), min(height - 1, y2)
    local = np.rint(points - np.asarray([x1, y1])).astype(np.int32)
    mask = np.zeros((y2 - y1 + 1, x2 - x1 + 1), dtype=np.uint8)
    cv2.fillPoly(mask, [local], 1)
    ys, xs = np.nonzero(mask)
    foreground = np.column_stack((xs + x1, ys + y1)).astype(np.float64)
    center = foreground.mean(axis=0)
    covariance = np.cov(foreground - center, rowvar=False)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    projections = (foreground - center) @ axis
    targets = [0.0, float(np.quantile(projections, 0.25)), float(np.quantile(projections, 0.75))]
    positive_pixels: list[np.ndarray] = []
    orthogonal = foreground - center - np.outer(projections, axis)
    orthogonal_sq = np.square(orthogonal).sum(axis=1)
    projection_span = max(1.0, float(np.ptp(projections)))
    for target in targets:
        score = np.square((projections - target) / projection_span) + orthogonal_sq / (projection_span ** 2)
        positive_pixels.append(foreground[int(np.argmin(score))])
    span_x, span_y = x2 - x1 + 1, y2 - y1 + 1
    pad_x, pad_y = span_x * BOX_PADDING, span_y * BOX_PADDING
    bx1, by1 = max(0.0, x1 - pad_x), max(0.0, y1 - pad_y)
    bx2, by2 = min(float(width - 1), x2 + pad_x), min(float(height - 1), y2 + pad_y)
    inset_x, inset_y = max(1.0, (bx2 - bx1) * 0.02), max(1.0, (by2 - by1) * 0.02)
    box = [normalized(bx1, width), normalized(by1, height), normalized(bx2, width), normalized(by2, height)]
    positives = [[normalized(p[0], width), normalized(p[1], height)] for p in positive_pixels]
    negatives = [
        [normalized(bx1 + inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by1 + inset_y, height)],
        [normalized(bx1 + inset_x, width), normalized(by2 - inset_y, height)],
        [normalized(bx2 - inset_x, width), normalized(by2 - inset_y, height)],
    ]
    return box, positives, negatives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts-v3", required=True)
    parser.add_argument("--annotations-v3-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    v3_path = Path(args.prompts_v3)
    doc = json.loads(v3_path.read_text(encoding="utf-8"))
    if doc.get("promptCount") != 52:
        raise ValueError("prompts v3 合同无效")

    aligned: list[str] = []
    for item in doc["images"]:
        ann_path = ANN_V3 / (Path(item["fileName"]).stem + ".json")
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        width, height = int(ann["image"]["width"]), int(ann["image"]["height"])
        source_image = Image.open(IMAGES / item["fileName"])
        if source_image.size != (width, height):
            raise ValueError(f"尺寸漂移：{item['fileName']}")
        for idx, nail in enumerate(item["sourceIndices"]):
            nail_id = f"n{idx + 1}"
            sub = item["fileName"][14:18]
            target = next(a for a in ann["annotations"] if a["id"] == nail_id)
            poly = [(p["x"], p["y"]) for p in target["polygon"]]
            if (sub, nail_id) in FINAL_POLYGON_OVERRIDES:
                poly = [(float(x), float(y)) for x, y in FINAL_POLYGON_OVERRIDES[(sub, nail_id)]]
                target["polygon"] = [{"x": x, "y": y} for x, y in poly]
                target["manualRepair"]["finalAdjustment"] = "2026-09-19终审修正（交叠消除/中心对齐/错位重绘）"
            if (sub, nail_id) in MANUAL_REPAIRED:
                box, positives, negatives = pca_prompts(poly, width, height)
                item["boxes"][idx] = box
                item["positivePoints"][idx] = positives
                item["negativePoints"][idx] = negatives
                item.setdefault("manualAlignedPrompts", {})[nail_id] = {
                    "alignedTo": "manual polygon after per-nail review",
                    "reason": "人工多边形修正YOLO候选框偏差；提示框按PCA同构规则对齐以通过提示/外接框几何审计",
                }
                aligned.append(f"{sub}:{nail_id}")
        (ANN_V3 / (Path(item["fileName"]).stem + ".json")).write_text(
            json.dumps(ann, ensure_ascii=False, indent=2), encoding="utf-8")

    doc["source"] = doc.get("source", "") + "; v4: 13 manual-repaired nails re-aligned to manual polygons (PCA-isomorphic), 3 final polygon adjustments"
    doc["inputs"]["promptsV3"] = {"path": str(v3_path), "sha256": sha256_file(v3_path)}
    doc["manualAlignedNails"] = aligned
    out_path = Path(args.output)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "promptCount": doc["promptCount"], "manualAlignedCount": len(aligned),
                      "output": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
