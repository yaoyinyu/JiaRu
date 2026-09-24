#!/usr/bin/env python3
"""冻结循环016完整train ROI来源图清单，供原分辨率逐图重审。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_module(name: str):
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载：{path}")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def read_bound(binding: dict) -> dict:
    path = Path(binding["path"])
    if not path.is_file() or sha256(path) != binding["sha256"]:
        raise ValueError(f"冻结输入漂移：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(plan_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if (Path(plan["auditorSource"]["path"]).resolve() != Path(__file__).resolve() or
            sha256(Path(__file__).resolve()) != plan["auditorSource"]["sha256"]):
        raise ValueError("盘点脚本哈希漂移")
    roi_report = read_bound(plan["inputs"]["roiMaterializationReport"])
    manifest = read_bound(plan["inputs"]["roiManifest"])
    source_report = read_bound(plan["inputs"]["cycle012MaterializationReport"])
    selected_audit = read_bound(plan["inputs"]["selected32VisualAuditReport"])
    if (selected_audit["decision"] != "train_truth_review_detected_defects_full_split_reaudit_before_more_training" or
            selected_audit["counts"]["confirmedDefects"] != 2 or
            roi_report["datasetFilesSha256"] != plan["roiDatasetFilesSha256"] or
            roi_report["manifest"]["sha256"] != plan["inputs"]["roiManifest"]["sha256"]):
        raise ValueError("上游冻结裁决或ROI身份漂移")
    source_root, roi_root = Path(source_report["outputDir"]), Path(roi_report["outputDir"])
    guards = load_module("train-yolo-seg.py")
    guards.install_read_only_ultralytics_image_check()
    guards.remove_ultralytics_label_caches(source_root)
    guards.remove_ultralytics_label_caches(roi_root)
    cycle012 = load_module("materialize-development-cycle-012-dataset.py")
    roi_v2 = load_module("materialize-development-cycle-016-roi-dataset-v2.py")
    cycle012.verify_report(Path(plan["inputs"]["cycle012MaterializationReport"]["path"]))
    replay = roi_v2.verify(Path(plan["inputs"]["roiMaterializationReport"]["path"]))
    if not replay["ok"] or replay["datasetFilesSha256"] != plan["roiDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树重放失败")
    by_source = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    train_rows = [row for row in manifest["records"] if row["split"] == "train"]
    if len(train_rows) != plan["expectedTrainRoiInstances"]:
        raise ValueError("完整train ROI分母漂移")
    for row in train_rows:
        key = (row["sourceFileName"], row["sourceGroup"])
        source = by_source.get(key)
        if source is None or source["developmentSplit"] != "train" or source["maskCount"] < 1:
            raise ValueError(f"train来源角色漂移：{row['id']}")
        grouped[key].append(row)
    images = []
    for index, key in enumerate(sorted(grouped, key=lambda item: (item[1], item[0])), start=1):
        rows = grouped[key]
        source = by_source[key]
        if len(rows) != source["maskCount"] or sorted(row["truthIndex"] for row in rows) != list(range(1, source["maskCount"] + 1)):
            raise ValueError(f"来源图逐甲分母不闭合：{key}")
        image_path, label_path = source_root / source["image"], source_root / source["label"]
        if sha256(image_path) != source["imageSha256"] or sha256(label_path) != source["labelSha256"]:
            raise ValueError(f"源图/标签哈希漂移：{key}")
        images.append({"ordinal": index, "sourceFileName": key[0], "sourceGroup": key[1],
                       "sourceImage": {"path": str(image_path), "sha256": source["imageSha256"]},
                       "sourceLabel": {"path": str(label_path), "sha256": source["labelSha256"]},
                       "maskCount": source["maskCount"],
                       "roiIds": [row["id"] for row in sorted(rows, key=lambda row: row["truthIndex"])],
                       "visualStatus": "pending_full_source_and_every_nail_original_resolution_review"})
    if len({row["sourceGroup"] for row in images}) != plan["expectedTrainSourceGroups"]:
        raise ValueError("完整train来源组数量漂移")
    shards = []
    size = plan["reviewShardSourceImages"]
    for start in range(0, len(images), size):
        batch = images[start:start + size]
        shards.append({"shard": len(shards) + 1, "startOrdinal": batch[0]["ordinal"],
                       "endOrdinal": batch[-1]["ordinal"], "sourceImages": len(batch),
                       "roiInstances": sum(row["maskCount"] for row in batch),
                       "sourceGroups": len({row["sourceGroup"] for row in batch})})
    guards.remove_ultralytics_label_caches(source_root)
    guards.remove_ultralytics_label_caches(roi_root)
    return {"schemaVersion": 1, "ok": True,
            "decision": "full_train_truth_inventory_frozen_pending_original_resolution_review",
            "inputs": {"plan": {"path": str(plan_path), "sha256": sha256(plan_path)}, **plan["inputs"]},
            "datasetFilesSha256": {"source": source_report["datasetFilesSha256"], "roi": replay["datasetFilesSha256"]},
            "counts": {"trainSourceImages": len(images), "trainRoiInstances": len(train_rows),
                       "trainSourceGroups": len({row["sourceGroup"] for row in images}),
                       "reviewShards": len(shards), "visualApprovals": 0},
            "sourceImages": images, "reviewShards": shards,
            "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False,
                      "fullTrainSplitVisualReview": "pending", "trainingUse": "unchanged",
                      "priorFailuresAndMetrics": "frozen_unchanged"}, "errors": []}


def verify(report_path: Path) -> dict:
    current = json.loads(report_path.read_text(encoding="utf-8"))
    expected = analyze(Path(current["inputs"]["plan"]["path"]))
    if current != expected:
        raise ValueError("完整train清单无法逐项重放")
    return {"ok": True, "decision": "verified_full_train_truth_inventory",
            "counts": current["counts"], "datasetFilesSha256": current["datasetFilesSha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if args.output.exists():
            raise FileExistsError(args.output)
        result = analyze(args.plan)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result if args.verify_report else {key: result[key] for key in ("ok", "decision", "counts", "datasetFilesSha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
