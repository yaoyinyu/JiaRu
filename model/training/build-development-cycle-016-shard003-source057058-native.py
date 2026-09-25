#!/usr/bin/env python3
"""Create isolated original-pixel repair review crops for shard-003 sources."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


TARGETS = (57, 58)
EXPECTED_NAILS = {57: 5, 58: 5}
CANONICAL_INDEX = Path(
    r"E:\AI Project\Codex\JiaRu_image\审核工作区\2026_7_14_A_v1"
    r"\positive-reinforcement-annotation-workspace-v1\training-truths-v1"
    r"\training-truth-index-v1.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bound(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha256(path) != binding["sha256"]:
        raise ValueError(f"绑定证据漂移：{path}")
    return path


def load_script(name: str):
    path = Path(__file__).resolve().with_name(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs(shard_path: Path, triage_path: Path) -> tuple[dict, dict]:
    builder = load_script("build-development-cycle-016-full-train-review-shard.py")
    triage_module = load_script("audit-development-cycle-016-shard003-source-triage.py")
    if not builder.verify(shard_path)["ok"]:
        raise ValueError("冻结分片报告重放失败")
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    for binding in triage["inputs"].values():
        checked(binding)
    if triage_module.build(shard_path) != triage:
        raise ValueError("分流报告重建不一致")
    if [row["ordinal"] for row in shard["sourceImages"]] != list(range(41, 61)):
        raise ValueError("冻结分片序号漂移")
    if not set(TARGETS).issubset({row["ordinal"] for row in triage["sourceTriage"]
                                   if row["decision"] == "pending_every_nail_review"}):
        raise ValueError("逐甲待审源图清单漂移")
    return shard, triage


def old_polygons(path: Path, width: int, height: int) -> list[list[tuple[float, float]]]:
    polygons = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 7 or (len(parts) - 1) % 2:
            raise ValueError(f"旧polygon非法：{path}")
        xy = [float(value) for value in parts[1:]]
        polygons.append([(xy[i] * width, xy[i + 1] * height) for i in range(0, len(xy), 2)])
    return polygons


def render(image: Image.Image, box: list[int], polygon: list[tuple[float, float]]) -> tuple[Image.Image, Image.Image]:
    source = image.crop(tuple(box))
    outline = source.copy()
    draw = ImageDraw.Draw(outline)
    local = [(x - box[0], y - box[1]) for x, y in polygon]
    draw.line(local + local[:1], fill=(255, 20, 20), width=2)
    size = (source.width * 3, source.height * 3)
    return (source.resize(size, Image.Resampling.NEAREST),
            outline.resize(size, Image.Resampling.NEAREST))


def verify_images(report: dict) -> None:
    if report["counts"] != {"sourceImages": 2, "oldLabelNails": 10, "visualApprovals": 0}:
        raise ValueError("隔离裁块计数漂移")
    if [row["ordinal"] for row in report["sources"]] != list(TARGETS):
        raise ValueError("隔离裁块源图序号漂移")
    for row in report["sources"]:
        image_path = checked(row["sourceImage"])
        label_path = checked(row["sourceLabel"])
        copy_path = checked(row["isolatedImage"])
        if sha256(image_path) != sha256(copy_path):
            raise ValueError("隔离原图字节与冻结原图不一致")
        with Image.open(copy_path) as opened:
            image = opened.convert("RGB")
        if list(image.size) != row["imageSize"]:
            raise ValueError("隔离原图尺寸漂移")
        polygons = old_polygons(label_path, image.width, image.height)
        if len(polygons) != EXPECTED_NAILS[row["ordinal"]] or len(row["nails"]) != len(polygons):
            raise ValueError("隔离裁块旧甲数漂移")
        for index, (nail, polygon) in enumerate(zip(row["nails"], polygons, strict=True), start=1):
            if nail["truthIndex"] != index or nail["cropBox"] != row["boundNailCropBoxes"][index - 1]:
                raise ValueError("裁块甲序号或冻结框漂移")
            raw, outline = render(image, nail["cropBox"], polygon)
            for binding, expected in ((nail["raw3x"], raw), (nail["oldOutline3x"], outline)):
                path = checked(binding)
                with Image.open(path) as opened:
                    actual = opened.convert("RGB")
                if actual.size != expected.size or actual.tobytes() != expected.tobytes():
                    raise ValueError(f"原像素裁块重建失败：{path}")


def build(shard_path: Path, triage_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    shard, _ = inputs(shard_path, triage_path)
    canonical_index = json.loads(CANONICAL_INDEX.read_text(encoding="utf-8"))
    if len(canonical_index["canonicalTruths"]) != 120:
        raise ValueError("历史规范真值索引规模漂移")
    (output / "images").mkdir(parents=True)
    (output / "crops").mkdir()
    records = []
    for ordinal in TARGETS:
        source = shard["sourceImages"][ordinal - 41]
        historical = [row for row in canonical_index["canonicalTruths"]
                      if row["fileName"] == source["sourceFileName"]]
        if (len(historical) != 1 or
                any(row["imageSha256"] != source["sourceImage"]["sha256"] or
                    row["sourceGroup"] != source["sourceGroup"] for row in historical)):
            raise ValueError(f"历史真值身份冲突：{ordinal}")
        for row in historical:
            if (sha256(Path(row["annotationPath"])) != row["annotationSha256"] or
                    sha256(Path(row["reportPath"])) != row["reportSha256"]):
                raise ValueError(f"历史真值绑定漂移：{ordinal}")
        image_path = checked(source["sourceImage"])
        label_path = checked(source["sourceLabel"])
        copy_path = output / "images" / source["sourceFileName"]
        shutil.copyfile(image_path, copy_path)
        if sha256(copy_path) != source["sourceImage"]["sha256"]:
            raise ValueError(f"隔离源图复制不一致：{ordinal}")
        with Image.open(copy_path) as opened:
            image = opened.convert("RGB")
        polygons = old_polygons(label_path, image.width, image.height)
        if len(polygons) != EXPECTED_NAILS[ordinal] or len(source["nails"]) != len(polygons):
            raise ValueError(f"旧甲数漂移：{ordinal}")
        nails = []
        for index, (nail, polygon) in enumerate(zip(source["nails"], polygons, strict=True), start=1):
            box = nail["cropBox"]
            raw, outline = render(image, box, polygon)
            raw_path = output / "crops" / f"source-{ordinal:03d}-nail-{index:02d}-raw-3x.png"
            outline_path = output / "crops" / f"source-{ordinal:03d}-nail-{index:02d}-outline-3x.png"
            raw.save(raw_path, format="PNG")
            outline.save(outline_path, format="PNG")
            nails.append({"truthIndex": index, "cropBox": box, "raw3x": bound(raw_path),
                          "oldOutline3x": bound(outline_path), "visualDecision": "pending_every_nail_visual_review"})
        records.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"], "sourceImage": source["sourceImage"],
                        "sourceLabel": source["sourceLabel"], "isolatedImage": bound(copy_path),
                        "historicalCanonicalTruths": historical,
                        "imageSize": list(image.size),
                        "boundNailCropBoxes": [nail["cropBox"] for nail in source["nails"]],
                        "nails": nails, "sourceQualityDecision": "pending_full_nail_review"})
    report = {"schemaVersion": 1, "ok": True,
              "decision": "isolated_original_resolution_repair_crops_pending_visual",
              "inputs": {"sourceScript": bound(Path(__file__)),
                         "shardReport": bound(shard_path), "sourceTriage": bound(triage_path),
                         "canonicalIndex": bound(CANONICAL_INDEX)},
              "counts": {"sourceImages": 2, "oldLabelNails": 10, "visualApprovals": 0},
              "sources": records,
              "scope": {"sourceImagesModified": False, "trainingUse": "prohibited",
                        "protectedTestOrHoldoutRead": False}}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify_images(report)
    return report


def verify(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for binding in report["inputs"].values():
        checked(binding)
    shard, _ = inputs(Path(report["inputs"]["shardReport"]["path"]),
                      Path(report["inputs"]["sourceTriage"]["path"]))
    if report["decision"] != "isolated_original_resolution_repair_crops_pending_visual":
        raise ValueError("裁块报告决定漂移")
    canonical_index = json.loads(checked(report["inputs"]["canonicalIndex"]).read_text(encoding="utf-8"))
    for row in report["sources"]:
        source = shard["sourceImages"][row["ordinal"] - 41]
        if (row["sourceFileName"] != source["sourceFileName"] or
                row["sourceGroup"] != source["sourceGroup"] or
                row["sourceImage"] != source["sourceImage"] or
                row["sourceLabel"] != source["sourceLabel"] or
                row["historicalCanonicalTruths"] != [truth for truth in canonical_index["canonicalTruths"]
                                                      if truth["fileName"] == source["sourceFileName"]] or
                row["boundNailCropBoxes"] != [nail["cropBox"] for nail in source["nails"]] or
                row["sourceQualityDecision"] != "pending_full_nail_review" or
                any(nail["visualDecision"] != "pending_every_nail_visual_review" for nail in row["nails"])):
            raise ValueError("裁块报告源图身份或决策漂移")
    verify_images(report)
    return {"ok": True, "decision": "verified_isolated_original_resolution_repair_crops_pending_visual",
            "counts": report["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-report", type=Path)
    parser.add_argument("--source-triage", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not args.shard_report or not args.source_triage or not args.output:
            parser.error("--shard-report, --source-triage, --output required")
        result = build(args.shard_report.resolve(), args.source_triage.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
