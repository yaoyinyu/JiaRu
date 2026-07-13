from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert reviewed YOLO prelabel polygons into normalized SAM box prompts."
    )
    parser.add_argument("--intake", required=True)
    parser.add_argument("--annotation-dir", required=True)
    parser.add_argument("--decision", action="append", default=["core"])
    parser.add_argument("--padding", type=float, default=0.04)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.padding < 0 or args.padding > 0.25:
        raise ValueError("padding must be between 0 and 0.25")
    intake = read_json(Path(args.intake).resolve())
    annotation_dir = Path(args.annotation_dir).resolve()
    output = Path(args.output).resolve()
    selected_decisions = set(args.decision)
    images: list[dict[str, object]] = []

    for entry in intake["entries"]:
        if entry["decision"] not in selected_decisions:
            continue
        annotation_path = annotation_dir / f"{Path(entry['fileName']).stem}.json"
        annotation = read_json(annotation_path)
        width = float(annotation["image"]["width"])
        height = float(annotation["image"]["height"])
        boxes = []
        for candidate in annotation["annotations"]:
            points = candidate["polygon"]
            xs = [float(point["x"]) for point in points]
            ys = [float(point["y"]) for point in points]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            pad_x = (x2 - x1) * args.padding
            pad_y = (y2 - y1) * args.padding
            boxes.append(
                [
                    max(0.0, (x1 - pad_x) / width),
                    max(0.0, (y1 - pad_y) / height),
                    min(1.0, (x2 + pad_x) / width),
                    min(1.0, (y2 + pad_y) / height),
                ]
            )
        images.append(
            {
                "fileName": entry["fileName"],
                "sourceGroup": entry["sourceGroup"],
                "boxes": boxes,
                "promptModes": ["box"] * len(boxes),
            }
        )

    document = {
        "schemaVersion": 1,
        "source": "review-only-v6-prelabel-polygon-bounds",
        "decision": "sam_candidate_only_not_test_truth",
        "paddingFraction": args.padding,
        "selectedIntakeDecisions": sorted(selected_decisions),
        "imageCount": len(images),
        "promptCount": sum(len(item["boxes"]) for item in images),
        "images": images,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: document[key] for key in ("decision", "imageCount", "promptCount")}, indent=2))


if __name__ == "__main__":
    main()
