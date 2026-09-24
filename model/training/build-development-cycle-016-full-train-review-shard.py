#!/usr/bin/env python3
"""按冻结完整train清单生成逐源图/逐甲原分辨率审核分片。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(name: str):
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载：{path}")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def polygons(path: Path) -> list[np.ndarray]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        tokens = line.split()
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法标签：{path}")
        result.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float32).reshape(-1, 2))
    return result


def load_plan(plan_path: Path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source = Path(plan["builderSource"]["path"])
    if source.resolve() != Path(__file__).resolve() or sha256(source) != plan["builderSource"]["sha256"]:
        raise ValueError("构建器哈希漂移")
    inventory_path = Path(plan["inventoryReport"]["path"])
    if sha256(inventory_path) != plan["inventoryReport"]["sha256"]:
        raise ValueError("完整train清单哈希漂移")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not load_module("audit-development-cycle-016-full-train-truth-inventory.py").verify(inventory_path)["ok"]:
        raise ValueError("完整train清单重放失败")
    shard = next((row for row in inventory["reviewShards"] if row["shard"] == plan["shard"]), None)
    if shard is None or shard != plan["expectedShard"]:
        raise ValueError("分片身份或预注册计数漂移")
    images = inventory["sourceImages"][shard["startOrdinal"]-1:shard["endOrdinal"]]
    if (len(images) != shard["sourceImages"] or
            sum(row["maskCount"] for row in images) != shard["roiInstances"] or
            [row["ordinal"] for row in images] != list(range(shard["startOrdinal"], shard["endOrdinal"]+1))):
        raise ValueError("分片与完整train清单不闭合")
    return plan, inventory, images


def overlay(image: Image.Image, vertices: list[tuple[float, float]], fill: tuple[int, int, int, int]):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.polygon(vertices, fill=fill)
    draw.line(vertices + vertices[:1], fill=(255, 28, 20, 255), width=2)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def build(plan_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    plan, inventory, sources = load_plan(plan_path)
    guards = load_module("train-yolo-seg.py")
    guards.install_read_only_ultralytics_image_check()
    source_root = Path(inventory["sourceImages"][0]["sourceImage"]["path"]).parents[2]
    guards.remove_ultralytics_label_caches(source_root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(source_root)
    atexit.register(cleanup)
    roi_module = load_module("materialize-development-cycle-016-roi-dataset.py")
    output.mkdir(parents=True)
    records = []
    for source in sources:
        ordinal = source["ordinal"]
        image_path = Path(source["sourceImage"]["path"])
        label_path = Path(source["sourceLabel"]["path"])
        if sha256(image_path) != source["sourceImage"]["sha256"] or sha256(label_path) != source["sourceLabel"]["sha256"]:
            raise ValueError(f"源图/标签哈希漂移：{ordinal}")
        with Image.open(image_path) as opened:
            original = opened.convert("RGB")
        width, height = original.size
        labels = polygons(label_path)
        if len(labels) != source["maskCount"]:
            raise ValueError(f"来源甲数漂移：{ordinal}")
        overview = original.copy()
        nails = []
        for truth_index, (polygon, roi_id) in enumerate(zip(labels, source["roiIds"], strict=True), start=1):
            pixels = polygon * np.asarray([width, height], dtype=np.float32)
            if not np.isfinite(pixels).all() or np.any(pixels[:, 0] < 0) or np.any(pixels[:, 0] >= width) or np.any(pixels[:, 1] < 0) or np.any(pixels[:, 1] >= height):
                raise ValueError(f"来源polygon坐标非法：{roi_id}")
            overview = overlay(overview, [(float(x), float(y)) for x, y in pixels], (0, 255, 0, 30))
            x1, y1, x2, y2 = roi_module.crop_box(polygon, width, height, 1.6)
            native = original.crop((x1, y1, x2, y2))
            local = pixels - np.asarray([x1, y1], dtype=np.float32)
            native_overlay = overlay(native, [(float(x), float(y)) for x, y in local], (0, 255, 0, 45))
            native_path = output / f"source-{ordinal:03d}-nail-{truth_index:02d}.png"
            native_overlay.save(native_path, format="PNG")
            nails.append({"truthIndex": truth_index, "roiId": roi_id, "cropBox": [x1, y1, x2, y2],
                          "nativeOverlay": {"path": str(native_path), "sha256": sha256(native_path)},
                          "visualDecision": "pending_original_resolution_review"})
        overview_path = output / f"source-{ordinal:03d}-overview.png"
        overview.save(overview_path, format="PNG")
        records.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                        "sourceLabel": source["sourceLabel"], "overview": {"path": str(overview_path), "sha256": sha256(overview_path)},
                        "nails": nails, "sourceVisualDecision": "pending_full_original_resolution_review"})
    guards.remove_ultralytics_label_caches(source_root)
    integrity = load_module("audit-development-cycle-016-full-train-truth-inventory.py").verify(
        Path(plan["inventoryReport"]["path"]))
    if integrity["datasetFilesSha256"] != inventory["datasetFilesSha256"]:
        raise ValueError("审核后数据文件树漂移")
    atexit.unregister(cleanup)
    result = {"schemaVersion": 1, "ok": True, "decision": "full_train_review_shard_pending_visual_decisions",
              "inputs": {"plan": {"path": str(plan_path), "sha256": sha256(plan_path)},
                         "inventoryReport": plan["inventoryReport"]},
              "shard": plan["expectedShard"], "sourceImages": records,
              "counts": {"sourceImages": len(records), "roiInstances": sum(len(row["nails"]) for row in records),
                         "visualApprovals": 0}, "datasetFilesSha256": integrity["datasetFilesSha256"],
              "scope": {"testOrHoldoutRead": False, "trainingUse": "unchanged"}, "errors": []}
    (output / "shard-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def verify(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan_path = Path(report["inputs"]["plan"]["path"])
    if sha256(plan_path) != report["inputs"]["plan"]["sha256"]:
        raise ValueError("分片计划哈希漂移")
    plan, inventory, sources = load_plan(plan_path)
    if (report["inputs"]["inventoryReport"] != plan["inventoryReport"] or
            report["shard"] != plan["expectedShard"] or len(report["sourceImages"]) != len(sources) or
            report["counts"] != {"sourceImages": len(sources), "roiInstances": sum(row["maskCount"] for row in sources), "visualApprovals": 0}):
        raise ValueError("分片计数或身份漂移")
    for source, record in zip(sources, report["sourceImages"], strict=True):
        if (record["ordinal"] != source["ordinal"] or record["sourceFileName"] != source["sourceFileName"] or
                record["sourceGroup"] != source["sourceGroup"] or record["sourceImage"] != source["sourceImage"] or
                record["sourceLabel"] != source["sourceLabel"] or
                record["sourceVisualDecision"] != "pending_full_original_resolution_review" or
                [nail["roiId"] for nail in record["nails"]] != source["roiIds"]):
            raise ValueError(f"分片来源行漂移：{source['ordinal']}")
        for binding in [record["overview"], *(nail["nativeOverlay"] for nail in record["nails"])]:
            if sha256(Path(binding["path"])) != binding["sha256"]:
                raise ValueError(f"分片图像哈希漂移：{source['ordinal']}")
        if any(nail["visualDecision"] != "pending_original_resolution_review" for nail in record["nails"]):
            raise ValueError("构建包不得自动批准甲面")
    return {"ok": True, "decision": "verified_full_train_review_shard_pending_visual_decisions", "counts": report["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    result = verify(args.verify_report) if args.verify_report else build(args.plan, args.output)
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
