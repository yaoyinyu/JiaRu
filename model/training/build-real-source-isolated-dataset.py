from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a real-only dataset with collection-isolated val/test splits.")
    parser.add_argument("--old-images", required=True)
    parser.add_argument("--old-annotations", required=True)
    parser.add_argument("--new-images", required=True)
    parser.add_argument("--new-annotations", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--val-prefix", action="append", default=["more_", "more_more_"])
    parser.add_argument("--test-prefix", action="append", default=["deerplanet.tw_"])
    return parser


def choose_split(file_name: str, val_prefixes: list[str], test_prefixes: list[str]) -> str:
    lowered = file_name.lower()
    if any(lowered.startswith(prefix.lower()) for prefix in test_prefixes):
        return "test"
    if any(lowered.startswith(prefix.lower()) for prefix in val_prefixes):
        return "val"
    return "train"


def yolo_lines(document: dict) -> list[str]:
    width = float(document["image"]["width"])
    height = float(document["image"]["height"])
    lines: list[str] = []
    for annotation in document.get("annotations", []):
        coords: list[str] = []
        for point in annotation["polygon"]:
            coords.extend([f'{float(point["x"]) / width:.6f}', f'{float(point["y"]) / height:.6f}'])
        lines.append(" ".join(["0", *coords]))
    return lines


def main() -> None:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).resolve()
    sources = [
        (Path(args.old_images).resolve(), Path(args.old_annotations).resolve(), "old-authorized-batch"),
        (Path(args.new_images).resolve(), Path(args.new_annotations).resolve(), "new-authorized-batch"),
    ]
    records: dict[str, tuple[Path, Path, str]] = {}
    for image_dir, annotation_dir, batch in sources:
        for annotation_path in sorted(annotation_dir.glob("*.json")):
            document = json.loads(annotation_path.read_text(encoding="utf-8"))
            file_name = document["image"]["fileName"]
            image_path = image_dir / file_name
            if not image_path.is_file():
                raise FileNotFoundError(f"Missing image for {annotation_path}: {image_path}")
            if file_name in records:
                raise ValueError(f"Duplicate file name across reviewed batches: {file_name}")
            records[file_name] = (image_path, annotation_path, batch)

    split_counts = {"train": 0, "val": 0, "test": 0}
    mask_counts = {"train": 0, "val": 0, "test": 0}
    group_counts: dict[str, dict[str, int]] = {}
    for file_name, (image_path, annotation_path, batch) in sorted(records.items()):
        split = choose_split(file_name, args.val_prefix, args.test_prefix)
        document = json.loads(annotation_path.read_text(encoding="utf-8"))
        lines = yolo_lines(document)
        image_target = output_dir / "images" / split / file_name
        label_target = output_dir / "labels" / split / f"{Path(file_name).stem}.txt"
        image_target.parent.mkdir(parents=True, exist_ok=True)
        label_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, image_target)
        label_target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        split_counts[split] += 1
        mask_counts[split] += len(lines)
        group = "deerplanet" if file_name.lower().startswith("deerplanet.tw_") else (
            "more" if file_name.lower().startswith(("more_", "more_more_")) else batch
        )
        group_counts.setdefault(group, {"train": 0, "val": 0, "test": 0})[split] += 1

    yaml = "\n".join([
        f'path: {str(output_dir).replace(chr(92), "/")}',
        "train: images/train", "val: images/val", "test: images/test", "", "names:", "  0: nail_texture",
        "", "task: segment", "class_count: 1", "image_size: 512", "",
    ])
    (output_dir / "dataset.yaml").write_text(yaml, encoding="utf-8")
    report = {
        "ok": all(split_counts[name] > 0 for name in ("train", "val", "test")),
        "decision": "experiment_only_source_isolated_real_dataset",
        "outputDir": str(output_dir),
        "imageCount": len(records),
        "splitCounts": split_counts,
        "maskCounts": mask_counts,
        "groupCounts": group_counts,
        "valPrefixes": args.val_prefix,
        "testPrefixes": args.test_prefix,
        "invariants": {
            "deerplanetOnlyTest": group_counts.get("deerplanet", {}).get("test", 0) > 0 and group_counts.get("deerplanet", {}).get("train", 0) == 0,
            "moreOnlyVal": group_counts.get("more", {}).get("val", 0) > 0 and group_counts.get("more", {}).get("train", 0) == 0,
        },
    }
    (output_dir / "source-isolated-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"] or not all(report["invariants"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
