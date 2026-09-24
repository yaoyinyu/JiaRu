#!/usr/bin/env python3
"""Freeze original-pixel SAM candidate prompts for shard-002 source 28."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


# Ordered by the five frozen old-label indices; these are candidate prompts only.
# Distal positives for nails 1 and 4 deliberately cover the transparent tips
# missed by the old polygons. Negative points target adjacent finger/paper/nail.
PROMPTS = [
    ([138, 969, 515, 1095], [[200, 1030], [330, 1035], [480, 1025]], [[150, 945], [400, 965], [510, 1085]]),
    ([247, 637, 409, 982], [[290, 680], [316, 800], [365, 935]], [[239, 710], [410, 795], [412, 985]]),
    ([420, 618, 572, 990], [[480, 665], [484, 815], [460, 950]], [[413, 700], [578, 790], [500, 997]]),
    ([527, 800, 688, 1140], [[620, 850], [595, 965], [552, 1105]], [[520, 845], [690, 970], [530, 1142]]),
    ([647, 803, 885, 960], [[680, 930], [760, 875], [850, 840]], [[647, 800], [880, 910], [760, 969]]),
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def build(shard_path: Path, progress_path: Path, focus_path: Path,
          image_dir: Path) -> dict:
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    focus = json.loads(focus_path.read_text(encoding="utf-8"))
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 28)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == 28)
    if (shard["shard"]["shard"] != 2 or not progress["ok"] or
            row["decision"] != "confirmed_label_rework" or
            focus["decision"] != "confirmed_label_rework" or
            focus["sourceOrdinal"] != 28 or
            row["sourceImage"] != source["sourceImage"] or
            row["sourceLabel"] != source["sourceLabel"] or
            focus["sourceImage"] != source["sourceImage"] or
            focus["sourceLabel"] != source["sourceLabel"] or
            len(source["nails"]) != 5):
        raise ValueError("frozen source28 identity/rework status drift")
    source_path = Path(source["sourceImage"]["path"])
    if sha(source_path) != source["sourceImage"]["sha256"]:
        raise ValueError("original image drift")
    image_dir.mkdir(parents=True, exist_ok=True)
    copy_path = image_dir / source["sourceFileName"]
    if not copy_path.exists():
        shutil.copyfile(source_path, copy_path)
    if sha(copy_path) != source["sourceImage"]["sha256"]:
        raise ValueError("isolated copy drift")
    # Decode only the isolated copy, never the hash-bound source dataset.
    with Image.open(copy_path) as image:
        width, height = image.size
    if (width, height) != (1080, 1352):
        raise ValueError("source28 image dimensions drift")
    boxes, positives, negatives = [], [], []
    for index, (box, plus, minus) in enumerate(PROMPTS, start=1):
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"box {index} outside image")
        if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
            raise ValueError(f"point {index} outside image")
        if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
            raise ValueError(f"positive point {index} outside its box")
        boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
        positives.append([[x / width, y / height] for x, y in plus])
        negatives.append([[x / width, y / height] for x, y in minus])
    return {"schemaVersion": 1, "decision": "source028_sam_candidates_only",
            "trainingUse": "prohibited", "inputs": {"sourceScript": bind(Path(__file__)),
                "shardReport": bind(shard_path), "progressV3": bind(progress_path),
                "source28FocusedReview": bind(focus_path), "isolatedImage": bind(copy_path)},
            "images": [{"fileName": source["sourceFileName"], "sourceGroup": source["sourceGroup"],
                        "sourceImageSha256": source["sourceImage"]["sha256"],
                        "boxes": boxes, "positivePoints": positives,
                        "negativePoints": negatives, "promptModes": ["box-center"] * 5}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-report", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--focus", type=Path)
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            if sha(Path(binding["path"])) != binding["sha256"]:
                raise ValueError("bound file drift")
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["progressV3"]["path"]),
                        Path(inputs["source28FocusedReview"]["path"]),
                        Path(inputs["isolatedImage"]["path"]).parent)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.shard_report, args.progress, args.focus, args.image_dir, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard_report.resolve(), args.progress.resolve(),
                   args.focus.resolve(), args.image_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "images": len(report["images"]) }))


if __name__ == "__main__":
    main()
