#!/usr/bin/env python3
"""One directed SAM retry with tight complete-nail boxes and skin negatives."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROMPTS = [
    ([361, 721, 447, 910], [[401, 750], [407, 830], [410, 891]],
     [[397, 706], [447, 810], [388, 918]]),
    ([440, 756, 555, 969], [[518, 795], [502, 865], [466, 951]],
     [[523, 741], [560, 850], [443, 975]]),
    ([537, 833, 670, 1043], [[641, 866], [612, 949], [565, 1019]],
     [[641, 814], [674, 938], [541, 1048]]),
    ([650, 950, 778, 1035], [[740, 980], [696, 997], [661, 1016]],
     [[790, 981], [711, 1042], [643, 953]]),
    ([225, 895, 433, 995], [[257, 921], [343, 950], [401, 970]],
     [[257, 888], [340, 1002], [442, 973]]),
]


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


def build(v1_path: Path, stoploss_path: Path) -> dict:
    first, stoploss = load(v1_path), load(stoploss_path)
    if (first["decision"] != "source032_one_sam_candidate_pass_only" or
            first["trainingUse"] != "prohibited" or
            stoploss["decision"] !=
            "source032_old_and_sam_masks_rejected_frozen_probe_diagnostic_only" or
            stoploss["counts"]["manualReworkRequired"] != 5 or
            stoploss["trainingUse"] != "prohibited" or
            len(first["images"]) != 1):
        raise ValueError("source32 first-pass/retry stop-loss mismatch")
    item = first["images"][0]
    width, height = 1080, 1440
    boxes, positives, negatives = [], [], []
    for index, (box, plus, minus) in enumerate(PROMPTS, start=1):
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"retry box {index} invalid")
        if any(not (0 <= x < width and 0 <= y < height) for x, y in plus + minus):
            raise ValueError(f"retry point {index} outside image")
        if any(not (x1 <= x <= x2 and y1 <= y <= y2) for x, y in plus):
            raise ValueError(f"retry positive {index} outside box")
        boxes.append([x1 / width, y1 / height, x2 / width, y2 / height])
        positives.append([[x / width, y / height] for x, y in plus])
        negatives.append([[x / width, y / height] for x, y in minus])
    return {"schemaVersion": 1,
            "decision": "source032_one_directed_sam_retry_candidate_only",
            "trainingUse": "prohibited",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "firstPrompts": bind(v1_path),
                       "firstVisualStoploss": bind(stoploss_path),
                       "isolatedImage": first["inputs"]["isolatedImage"]},
            "images": [{"fileName": item["fileName"],
                        "sourceGroup": item["sourceGroup"],
                        "sourceImageSha256": item["sourceImageSha256"],
                        "boxes": boxes, "positivePoints": positives,
                        "negativePoints": negatives,
                        "promptModes": ["box-center"] * 5}]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-prompts", type=Path)
    parser.add_argument("--first-stoploss", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            checked(item)
        current = build(Path(prior["inputs"]["firstPrompts"]["path"]),
                        Path(prior["inputs"]["firstVisualStoploss"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.first_prompts, args.first_stoploss, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.first_prompts.resolve(), args.first_stoploss.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
