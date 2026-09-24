#!/usr/bin/env python3
"""Build hash-bound, isolated SAM repair prompts for a reviewed train source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> Path:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def build(shard_path: Path, progress_path: Path, spec_path: Path,
          image_dir: Path) -> dict:
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    ordinal = spec["sourceOrdinal"]
    if spec["trainingUse"] != "prohibited" or not progress["ok"] or shard["shard"]["shard"] != 2:
        raise ValueError("frozen shard/role mismatch")
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == ordinal)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == ordinal)
    if (row["decision"] != "confirmed_label_rework" or
            row["sourceFileName"] != source["sourceFileName"] or
            row["sourceGroup"] != source["sourceGroup"] or
            row["sourceImage"] != source["sourceImage"] or
            row["sourceLabel"] != source["sourceLabel"] or
            len(source["nails"]) != len(spec["prompts"]) or
            len(spec["prompts"]) != 5):
        raise ValueError("source identity/rework/nail count drift")
    source_path = checked(source["sourceImage"])
    checked(source["sourceLabel"])
    checked(source["overview"])
    for nail in source["nails"]:
        checked(nail["nativeOverlay"])
    image_dir.mkdir(parents=True, exist_ok=True)
    copy_path = image_dir / source["sourceFileName"]
    if not copy_path.exists():
        shutil.copyfile(source_path, copy_path)
    if sha(copy_path) != source["sourceImage"]["sha256"]:
        raise ValueError("isolated source copy drift")
    # Decode only the isolated copy, never the hash-bound training image.
    with Image.open(copy_path) as image:
        width, height = image.size
    if [width, height] != spec["expectedDimensions"]:
        raise ValueError(f"source image dimensions drift: {(width, height)}")
    boxes, positives, negatives = [], [], []
    for index, prompt in enumerate(spec["prompts"], start=1):
        if prompt["truthIndex"] != index:
            raise ValueError("prompt order must match frozen truth indices")
        x1, y1, x2, y2 = prompt["box"]
        plus, minus = prompt["positivePoints"], prompt["negativePoints"]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height and plus and minus):
            raise ValueError(f"invalid prompt box/points at {index}")
        if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
            raise ValueError(f"prompt point outside image at {index}")
        if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
            raise ValueError(f"positive point outside box at {index}")
        if set(map(tuple, plus)) & set(map(tuple, minus)):
            raise ValueError(f"opposing labels at same point at {index}")
        boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
        positives.append([[x / width, y / height] for x, y in plus])
        negatives.append([[x / width, y / height] for x, y in minus])
    return {"schemaVersion": 1, "decision": "shard002_sam_candidates_only",
            "trainingUse": "prohibited", "sourceOrdinal": ordinal,
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "shardReport": bind(shard_path), "progressV4": bind(progress_path),
                       "manualPromptSpec": bind(spec_path), "sourceImage": bind(source_path),
                       "sourceLabel": bind(Path(source["sourceLabel"]["path"])),
                       "isolatedImage": bind(copy_path),
                       "sourceOverview": bind(Path(source["overview"]["path"])),
                       "nativeOverlays": [bind(Path(nail["nativeOverlay"]["path"]))
                                          for nail in source["nails"]]},
            "images": [{"fileName": source["sourceFileName"],
                        "sourceGroup": source["sourceGroup"],
                        "sourceImageSha256": source["sourceImage"]["sha256"],
                        "boxes": boxes, "positivePoints": positives,
                        "negativePoints": negatives,
                        "promptModes": ["box-center"] * 5}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-report", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--image-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for binding in old["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["progressV4"]["path"]),
                        Path(inputs["manualPromptSpec"]["path"]),
                        Path(inputs["isolatedImage"]["path"]).parent)
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "sourceOrdinal": current["sourceOrdinal"]}))
        return
    if not all((args.shard_report, args.progress, args.spec, args.image_dir, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard_report.resolve(), args.progress.resolve(), args.spec.resolve(),
                   args.image_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "sourceOrdinal": report["sourceOrdinal"]}))


if __name__ == "__main__":
    main()
