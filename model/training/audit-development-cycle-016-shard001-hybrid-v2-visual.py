#!/usr/bin/env python3
"""Freeze original-resolution visual decisions for shard-001 repaired nails.

The reviewed image/crop evidence is hash-bound. A visual pass here grants no
training role while watermark and full-train-split gates remain pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Point, Polygon


VISUAL_REASONS = {
    8: [
        "完整甲根弧线及左右侧缘由原像素人工复核，透明甲尖保留；无邻指或戒指污染。",
        "甲根自然甲板、蝴蝶结装饰和长甲尖由单一mask完整覆盖；无皮肤污染。",
        "侧向短甲的甲根、装饰及甲尖完整；未越入皮包。",
        "宝石覆盖的整枚可见甲板与甲尖完整；未并入邻指。",
        "拇指甲下缘沿甲面/皮包带分界闭合，皮包带及缝线未入mask。",
    ],
    18: [
        "拇指透明粉色甲面从甲根到甲尖完整，边界未跨入皮肤。",
        "低对比甲尖与左右侧缘已覆盖，旧锯齿及内缩缺陷不再可见。",
        "低对比甲尖、侧缘和甲根完整，旧内缩缺陷不再可见。",
        "短甲完整覆盖，甲根与皮肤分界保持清晰。",
        "上方甲尖外缘已覆盖，旧锯齿缺陷不再可见。",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bind(path: Path) -> dict[str, str]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": sha256(path)}


def checked(binding: dict[str, str]) -> None:
    if sha256(Path(binding["path"])) != binding["sha256"]:
        raise ValueError(f"input drift: {binding['path']}")


def build(inputs: dict[str, dict[str, str]]) -> dict:
    for binding in inputs.values():
        checked(binding)
    preflight = json.loads(Path(inputs["preflight"]["path"]).read_text(encoding="utf-8"))
    prompts = json.loads(Path(inputs["prompts"]["path"]).read_text(encoding="utf-8"))
    manifest = json.loads(Path(inputs["hybridManifest"]["path"]).read_text(encoding="utf-8"))
    hybrid = json.loads(Path(inputs["hybridReport"]["path"]).read_text(encoding="utf-8"))
    geometry = json.loads(Path(inputs["promptGeometry"]["path"]).read_text(encoding="utf-8"))
    if preflight["decision"] != "repair_queue_bound_no_masks_approved" or prompts["preflight"]["sha256"] != inputs["preflight"]["sha256"]:
        raise ValueError("preflight/prompt identity drift")
    if manifest["decision"] != "hybrid_v2_candidate_only_original_resolution_review_required" or hybrid["ok"] is not True:
        raise ValueError("hybrid candidate is invalid")
    if manifest["trainingUse"] != "prohibited" or hybrid["polygonCount"] != 10 or hybrid["pairwiseOverlapCount"] != 0:
        raise ValueError("hybrid candidate quality/role drift")
    if geometry["summary"]["cycle016-shard001-repair-v1"] != {"pass": 10, "suspect": 0, "missing": 0}:
        raise ValueError("base SAM prompt geometry drift")
    outputs = {row["fileName"]: row for row in hybrid["outputs"]}
    preflight_rows = {row["sourceFileName"]: row for row in preflight["repairSources"]}
    prompt_rows = {row["fileName"]: row for row in prompts["images"]}
    if len(outputs) != 2 or set(outputs) != set(preflight_rows) or set(outputs) != set(prompt_rows):
        raise ValueError("source set drift")
    reviewed = []
    for file_name, output in outputs.items():
        prior = preflight_rows[file_name]
        prompt = prompt_rows[file_name]
        ordinal = prior["ordinal"]
        if output["sourceGroup"] != prior["sourceGroup"] or prompt["sourceGroup"] != prior["sourceGroup"]:
            raise ValueError("source group drift")
        checked(prior["sourceImage"])
        annotation_path = Path(output["annotationPath"])
        overlay_path = Path(output["overlayPath"])
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        source_copy = Path(inputs["prompts"]["path"]).parent / "images" / file_name
        if sha256(source_copy) != prior["sourceImage"]["sha256"]:
            raise ValueError("source copy drift")
        if annotation["trainingUse"] != "prohibited" or annotation["image"]["sourceGroup"] != prior["sourceGroup"]:
            raise ValueError("annotation role/group drift")
        with Image.open(source_copy) as image, Image.open(overlay_path) as overlay:
            width, height = image.size
            if overlay.size != image.size:
                raise ValueError("full overlay size drift")
        polygons = annotation["annotations"]
        if len(polygons) != 5 or len(output["zoomPaths"]) != 5:
            raise ValueError("nail/crop count drift")
        nail_rows = []
        shapes = []
        for index, (nail, crop) in enumerate(zip(polygons, output["zoomPaths"], strict=True), start=1):
            if nail["id"] != f"n{index}":
                raise ValueError("nail index drift")
            shape = Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
            if not shape.is_valid or shape.area <= 16:
                raise ValueError("invalid polygon")
            shapes.append(shape)
            plus = prompt["positivePoints"][index - 1]
            minus = prompt["negativePoints"][index - 1]
            if any(not shape.covers(Point(x * width, y * height)) for x, y in plus):
                raise ValueError(f"positive prompt outside mask: {ordinal}/{index}")
            if any(shape.covers(Point(x * width, y * height)) for x, y in minus):
                raise ValueError(f"negative prompt inside mask: {ordinal}/{index}")
            source_crop, overlay_crop = bind(Path(crop["source"])), bind(Path(crop["overlay"]))
            nail_rows.append({"truthIndex": index, "visualDecision": "pass_original_resolution",
                              "reason": VISUAL_REASONS[ordinal][index - 1],
                              "polygonAreaPixels": round(shape.area, 3),
                              "sourceCrop2x": source_crop, "overlayCrop2x": overlay_crop})
        for i in range(5):
            for j in range(i + 1, 5):
                if shapes[i].intersection(shapes[j]).area != 0:
                    raise ValueError("same-image polygon overlap")
        reviewed.append({"ordinal": ordinal, "fileName": file_name,
                         "sourceGroup": prior["sourceGroup"], "sourceImage": prior["sourceImage"],
                         "annotation": bind(annotation_path), "fullOverlay": bind(overlay_path),
                         "nails": nail_rows, "visualDecision": "pass_original_resolution",
                         "trainingUse": "prohibited_pending_full_split_and_watermark_ablation"})
    reviewed.sort(key=lambda row: row["ordinal"])
    return {"schemaVersion": 1, "ok": True,
            "decision": "two_repaired_sources_visual_pass_training_still_prohibited",
            "inputs": inputs,
            "counts": {"repairedSources": 2, "repairedNails": 10, "visualPassSources": 2,
                       "visualPassNails": 10, "legalPolygons": 10, "overlapPairs": 0,
                       "newTrainingApprovedSources": 0},
            "repairedSources": reviewed, "fullShardMaskReviewComplete": True,
            "fullTrainSplitApproved": False, "watermarkAblationComplete": False,
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("preflight", "prompts", "hybrid-manifest", "hybrid-report", "prompt-geometry"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = build(recorded["inputs"])
        ok = current == recorded
        print(json.dumps({"ok": ok, "decision": current["decision"] if ok else "reconstruction_mismatch",
                          "counts": current["counts"]}, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)
        return
    names = {"preflight": args.preflight, "prompts": args.prompts,
             "hybridManifest": args.hybrid_manifest, "hybridReport": args.hybrid_report,
             "promptGeometry": args.prompt_geometry}
    if any(value is None for value in (*names.values(), args.output)):
        parser.error("all input paths and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build({name: bind(path) for name, path in names.items()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
