#!/usr/bin/env python3
"""Bind five frozen train-source logo windows before choosing mask repair effort.

This is a read-only source review on isolated copies. It neither infers with a
model nor grants source, mask, or training approval.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, box


ORDINALS = (25, 27, 30, 32, 40)


def install_read_only_ultralytics_image_check() -> None:
    """Prevent Ultralytics from rewriting hash-bound JPEGs if imported later."""
    from ultralytics.data import utils as data_utils

    def check_image_read_only(im_file: str) -> tuple[str, tuple[int, int]]:
        with Image.open(im_file) as image:
            image.verify()
        with Image.open(im_file) as image:
            image.load()
            shape = (int(image.height), int(image.width))
            image_format = str(image.format or "").lower()
        if shape[0] <= 9 or shape[1] <= 9 or image_format not in data_utils.IMG_FORMATS:
            raise AssertionError(f"invalid read-only image: {im_file}")
        return "", shape

    data_utils.check_image = check_image_read_only
    if data_utils.verify_image.__globals__.get("check_image") is not check_image_read_only:
        raise RuntimeError("failed to install read-only image check")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def crop_bytes(image_path: Path, crop_box: list[int], scale: int) -> tuple[bytes, tuple[int, int]]:
    with Image.open(image_path) as image:
        image.load()
        size = image.size
        crop = image.crop(tuple(crop_box))
        crop = crop.resize(((crop_box[2] - crop_box[0]) * scale,
                            (crop_box[3] - crop_box[1]) * scale))
        stream = io.BytesIO()
        crop.save(stream, format="PNG")
    return stream.getvalue(), size


def old_shapes(label_path: Path, width: int, height: int) -> list[Polygon]:
    lines = label_path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 5:
        raise ValueError("expected five old train polygons")
    shapes = []
    for line in lines:
        values = [float(value) for value in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2 or len(values) < 7:
            raise ValueError("old label class/vertices invalid")
        shape = Polygon([(values[index] * width, values[index + 1] * height)
                         for index in range(1, len(values), 2)])
        if not shape.is_valid or shape.area <= 1:
            raise ValueError("old label polygon topology invalid")
        shapes.append(shape)
    return shapes


def build(plan_path: Path, progress_path: Path, shard_path: Path,
          index_path: Path, output_dir: Path, *, verify: bool) -> dict:
    install_read_only_ultralytics_image_check()
    plan, progress, shard, index = map(load, (plan_path, progress_path, shard_path, index_path))
    if (plan.get("schemaVersion") != 1 or plan.get("trainingUse") != "prohibited" or
            progress.get("schemaVersion") != 9 or not progress.get("ok") or
            shard.get("ok") is not True or shard["counts"]["sourceImages"] != 20 or
            shard["counts"]["roiInstances"] != 104 or
            tuple(item["ordinal"] for item in plan["items"]) != ORDINALS):
        raise ValueError("frozen shard/plan/progress mismatch")
    checked(shard["inputs"]["inventoryReport"])
    if not verify:
        output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in plan["items"]:
        ordinal = item["ordinal"]
        row = next(r for r in progress["sourceDispositions"] if r["ordinal"] == ordinal)
        frozen = next(r for r in shard["sourceImages"] if r["ordinal"] == ordinal)
        if (row["decision"] != "confirmed_label_rework" or row["oldLabelNails"] != 5 or
                row["trainingUse"] != "prohibited" or row["everyNailVisualApproval"] or
                row["sourceFileName"] != frozen["sourceFileName"] or
                row["sourceGroup"] != frozen["sourceGroup"] or
                row["sourceImage"] != frozen["sourceImage"] or
                row["sourceLabel"] != frozen["sourceLabel"]):
            raise ValueError(f"source {ordinal} identity/status mismatch")
        checked(row["sourceImage"])
        checked(row["sourceLabel"])
        copy_path = output_dir / "images" / row["sourceFileName"]
        if not verify:
            copy_path.parent.mkdir(parents=True, exist_ok=True)
            if not copy_path.exists():
                shutil.copyfile(row["sourceImage"]["path"], copy_path)
        if not copy_path.is_file() or sha(copy_path) != row["sourceImage"]["sha256"]:
            raise ValueError(f"isolated source {ordinal} drift")
        crop_box, mark_box, scale = item["cropBox"], item["markBox"], item["scale"]
        data, (width, height) = crop_bytes(copy_path, crop_box, scale)
        if (not (0 <= crop_box[0] < mark_box[0] < mark_box[2] <= crop_box[2] <= width and
                 0 <= crop_box[1] < mark_box[1] < mark_box[3] <= crop_box[3] <= height) or
                scale not in (4, 8)):
            raise ValueError(f"source {ordinal} crop/logo bounds invalid: "
                             f"image={(width, height)}, crop={crop_box}, mark={mark_box}")
        crop_path = output_dir / f"source-{ordinal:03d}-logo-{scale}x.png"
        if verify:
            if not crop_path.is_file() or sha(crop_path) != hashlib.sha256(data).hexdigest():
                raise ValueError(f"source {ordinal} crop drift")
        else:
            if not crop_path.exists():
                crop_path.write_bytes(data)
            elif sha(crop_path) != hashlib.sha256(data).hexdigest():
                raise ValueError(f"source {ordinal} existing crop differs")
        shapes = old_shapes(Path(row["sourceLabel"]["path"]), width, height)
        mark = box(*mark_box)
        overlaps = [number for number, shape in enumerate(shapes, 1)
                    if mark.intersection(shape).area > 0]
        distance = min(mark.distance(shape) for shape in shapes)
        canonical = [truth for truth in index["canonicalTruths"]
                     if truth["fileName"] == row["sourceFileName"]]
        if len(canonical) > 1:
            raise ValueError(f"duplicate historical canonical truth: {ordinal}")
        if canonical and (canonical[0]["imageSha256"] != row["sourceImage"]["sha256"] or
                          canonical[0]["sourceGroup"] != row["sourceGroup"] or
                          canonical[0]["completeMaskCount"] != 5):
            raise ValueError(f"conflicting historical canonical truth: {ordinal}")
        peer_visual = [r["ordinal"] for r in progress["sourceDispositions"]
                       if r["sourceGroup"] == row["sourceGroup"] and
                       r["everyNailVisualApproval"]]
        rows.append({"ordinal": ordinal, "sourceFileName": row["sourceFileName"],
                     "sourceGroup": row["sourceGroup"],
                     "sourceImage": row["sourceImage"], "sourceLabel": row["sourceLabel"],
                     "isolatedSourceImage": bind(copy_path), "logoCrop": bind(crop_path),
                     "dimensions": [width, height], "cropBoxPixels": crop_box,
                     "markBoxPixels": mark_box, "markType": item["markType"],
                     "overlappingOldMaskIndices": overlaps,
                     "minimumOldMaskDistancePixels": round(distance, 3),
                     "historicalCanonicalCount": len(canonical),
                     "sameGroupVisualPassOrdinals": peer_visual,
                     "oldMaskQuality": "confirmed_label_rework",
                     "visibleLogoVisualReviewPending": True,
                     "watermarkAblationComplete": False, "trainingUse": "prohibited"})
    if len(rows) != 5 or sum(r["historicalCanonicalCount"] for r in rows) != 1:
        raise ValueError("five-source batch/history count drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "five_rework_sources_logo_windows_bound_visual_review_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "cropPlan": bind(plan_path),
                       "progressV9": bind(progress_path), "shardReport": bind(shard_path),
                       "canonicalIndex": bind(index_path)},
            "sources": rows,
            "counts": {"sourceImages": 5, "oldLabelNails": 25,
                       "distinctSourceGroups": len({r["sourceGroup"] for r in rows}),
                       "historicalCanonicalRecords": 1,
                       "newTrainingApprovedSources": 0},
            "fullShardCleanTruthComplete": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--canonical-index", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--inspect-dimensions", action="store_true")
    args = parser.parse_args()
    if args.inspect_dimensions:
        if not args.progress:
            parser.error("--progress required for --inspect-dimensions")
        install_read_only_ultralytics_image_check()
        progress = load(args.progress)
        for row in progress["sourceDispositions"]:
            if row["ordinal"] in ORDINALS:
                checked(row["sourceImage"])
                with Image.open(row["sourceImage"]["path"]) as image:
                    print(json.dumps({"ordinal": row["ordinal"], "size": image.size}))
        return
    if args.verify_report:
        prior = load(args.verify_report)
        for binding in prior["inputs"].values():
            checked(binding)
        current = build(Path(prior["inputs"]["cropPlan"]["path"]),
                        Path(prior["inputs"]["progressV9"]["path"]),
                        Path(prior["inputs"]["shardReport"]["path"]),
                        Path(prior["inputs"]["canonicalIndex"]["path"]),
                        Path(prior["sources"][0]["logoCrop"]["path"]).parent,
                        verify=True)
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.plan, args.progress, args.shard, args.canonical_index,
                args.output_dir, args.report)):
        parser.error("all inputs and --output-dir/--report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.plan.resolve(), args.progress.resolve(), args.shard.resolve(),
                   args.canonical_index.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
