#!/usr/bin/env python3
"""Freeze source-bound SAM prompts for the two shard-001 repair images.

The output is only a candidate-generation input. It never approves a mask.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


# Original-pixel prompts, ordered by the frozen five-nail label index.
# Positive points cover proximal plate and distal decoration/tip; negative points
# target adjacent skin, jewellery, or the handbag. All remain subject to review.
PROMPTS = {
    8: [
        ([577, 410, 744, 735], [[670, 450], [666, 540], [631, 679]], [[579, 490], [742, 520], [615, 727]]),
        ([380, 410, 518, 773], [[459, 435], [448, 525], [424, 696]], [[383, 480], [513, 540], [475, 767]]),
        ([699, 805, 901, 916], [[738, 869], [828, 853]], [[711, 812], [851, 911]]),
        ([703, 578, 891, 832], [[825, 623], [783, 703], [747, 791]], [[710, 610], [881, 782]]),
        ([534, 905, 885, 1088], [[583, 987], [678, 978], [824, 989]], [[561, 915], [786, 1066], [853, 1062]]),
    ],
    18: [
        ([875, 730, 974, 867], [[925, 764], [925, 818]], [[879, 786], [969, 806]]),
        ([340, 211, 435, 347], [[384, 246], [386, 309]], [[345, 263], [431, 283]]),
        ([499, 148, 597, 292], [[547, 185], [544, 254]], [[505, 205], [590, 229]]),
        ([141, 440, 220, 562], [[177, 476], [181, 527]], [[146, 486], [214, 498]]),
        ([661, 237, 754, 370], [[708, 272], [708, 336]], [[668, 286], [749, 310]]),
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(preflight_path: Path, image_dir: Path) -> dict:
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("ok") is not True or preflight.get("decision") != "repair_queue_bound_no_masks_approved":
        raise ValueError("repair preflight is not approved as an input")
    images = []
    for source in preflight["repairSources"]:
        ordinal = source["ordinal"]
        if ordinal not in PROMPTS or len(source["nails"]) != 5:
            raise ValueError("unexpected repair source")
        source_path = Path(source["sourceImage"]["path"])
        if sha256(source_path) != source["sourceImage"]["sha256"]:
            raise ValueError(f"source image drift: {source_path}")
        with Image.open(source_path) as image:
            width, height = image.size
        copy_path = image_dir / source["sourceFileName"]
        if copy_path.exists():
            if sha256(copy_path) != source["sourceImage"]["sha256"]:
                raise ValueError(f"existing isolated image drift: {copy_path}")
        else:
            shutil.copyfile(source_path, copy_path)
        boxes, positive, negative = [], [], []
        for box, plus, minus in PROMPTS[ordinal]:
            if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
                raise ValueError(f"invalid box: {ordinal}")
            for points in (plus, minus):
                if any(not (0 <= x < width and 0 <= y < height) for x, y in points):
                    raise ValueError(f"point out of image: {ordinal}")
            boxes.append([box[0] / width, box[1] / height, box[2] / width, box[3] / height])
            positive.append([[x / width, y / height] for x, y in plus])
            negative.append([[x / width, y / height] for x, y in minus])
        images.append({"fileName": source["sourceFileName"], "sourceGroup": source["sourceGroup"],
                       "sourceImageSha256": source["sourceImage"]["sha256"],
                       "boxes": boxes, "positivePoints": positive, "negativePoints": negative,
                       "promptModes": ["box-center"] * 5})
    if {source["ordinal"] for source in preflight["repairSources"]} != set(PROMPTS):
        raise ValueError("repair source set drift")
    return {"schemaVersion": 1, "decision": "sam_prompt_candidates_only",
            "trainingUse": "prohibited", "preflight": {"path": str(preflight_path), "sha256": sha256(preflight_path)},
            "images": images}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        recorded = json.loads(args.output.read_text(encoding="utf-8"))
        actual = build(args.preflight, args.image_dir)
        if actual != recorded:
            raise ValueError("prompt reconstruction mismatch")
        print(json.dumps({"ok": True, "decision": "prompts_replayed", "images": len(actual["images"]) }))
        return
    if args.output.exists():
        raise FileExistsError(args.output)
    args.image_dir.mkdir(parents=True, exist_ok=True)
    report = build(args.preflight.resolve(), args.image_dir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "images": len(report["images"])}))


if __name__ == "__main__":
    main()
