from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


SPLITS = ("train", "val", "test")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extend an audited source-isolated YOLO dataset without changing its frozen test split."
    )
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--dataset-images", required=True)
    parser.add_argument("--dataset-annotations", required=True)
    parser.add_argument("--split-json", required=True)
    parser.add_argument("--intake-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_split_digest(root: Path, split: str = "test") -> tuple[str, list[dict[str, str]]]:
    records: list[dict[str, str]] = []
    for kind in ("images", "labels"):
        folder = root / kind / split
        if not folder.is_dir():
            raise FileNotFoundError(f"Missing frozen split directory: {folder}")
        for path in sorted((item for item in folder.iterdir() if item.is_file()), key=lambda item: item.name):
            if path.suffix.lower() == ".cache":
                continue
            records.append({"path": f"{kind}/{split}/{path.name}", "sha256": file_sha256(path)})
    digest = hashlib.sha256()
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest(), records


def yolo_lines(document: dict[str, Any]) -> list[str]:
    image = document.get("image")
    if not isinstance(image, dict):
        raise ValueError("Annotation document is missing image metadata")
    width = float(image.get("width", 0))
    height = float(image.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError("Annotation image dimensions must be positive")

    annotations = document.get("annotations", [])
    if not isinstance(annotations, list):
        raise ValueError("annotations must be an array")
    lines: list[str] = []
    for index, annotation in enumerate(annotations, start=1):
        if not isinstance(annotation, dict) or annotation.get("label") != "nail_texture":
            raise ValueError(f"Annotation {index} must use label nail_texture")
        polygon = annotation.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError(f"Annotation {index} polygon must contain at least 3 points")
        coords: list[str] = []
        for point_index, point in enumerate(polygon, start=1):
            if not isinstance(point, dict):
                raise ValueError(f"Annotation {index} point {point_index} must be an object")
            x = float(point.get("x", -1))
            y = float(point.get("y", -1))
            if not 0 <= x <= width or not 0 <= y <= height:
                raise ValueError(f"Annotation {index} point {point_index} is outside the image")
            coords.extend([f"{x / width:.6f}", f"{y / height:.6f}"])
        lines.append(" ".join(["0", *coords]))
    if not lines:
        raise ValueError("Reviewed positive image must contain at least one annotation")
    return lines


def inventory(root: Path) -> tuple[dict[str, int], dict[str, int], set[str], set[str]]:
    image_counts = {split: 0 for split in SPLITS}
    mask_counts = {split: 0 for split in SPLITS}
    image_names: set[str] = set()
    label_stems: set[str] = set()
    for split in SPLITS:
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        if not image_dir.is_dir() or not label_dir.is_dir():
            raise FileNotFoundError(f"Missing images/labels directory for split {split}")
        images = [path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() != ".cache"]
        labels = [path for path in label_dir.glob("*.txt") if path.is_file()]
        for image_path in images:
            if image_path.name in image_names:
                raise ValueError(f"Duplicate image file name in base dataset: {image_path.name}")
            image_names.add(image_path.name)
        for label_path in labels:
            if label_path.stem in label_stems:
                raise ValueError(f"Duplicate label stem in base dataset: {label_path.stem}")
            label_stems.add(label_path.stem)
            mask_counts[split] += sum(1 for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip())
        image_counts[split] = len(images)
        if len(images) != len(labels):
            raise ValueError(f"Base split {split} has {len(images)} images but {len(labels)} labels")
    return image_counts, mask_counts, image_names, label_stems


def main() -> None:
    args = build_parser().parse_args()
    base_dir = Path(args.base_dir).resolve()
    dataset_images = Path(args.dataset_images).resolve()
    dataset_annotations = Path(args.dataset_annotations).resolve()
    split_path = Path(args.split_json).resolve()
    manifest_path = Path(args.intake_manifest).resolve()
    output_dir = Path(args.output_dir).resolve()

    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists: {output_dir}")
    base_report_path = base_dir / "source-isolated-report.json"
    base_report = read_json(base_report_path)
    if base_report.get("ok") is not True:
        raise ValueError("Base source-isolated report is not passing")
    base_image_counts, base_mask_counts, base_names, base_label_stems = inventory(base_dir)
    if base_report.get("splitCounts") != base_image_counts or base_report.get("maskCounts") != base_mask_counts:
        raise ValueError("Base report counts do not match the current base dataset")
    frozen_before, frozen_files_before = frozen_split_digest(base_dir)

    split_document = read_json(split_path)
    split_by_name: dict[str, str] = {}
    for split in SPLITS:
        names = split_document.get(split)
        if not isinstance(names, list):
            raise ValueError(f"Split metadata is missing array: {split}")
        for name in names:
            if not isinstance(name, str) or not name:
                raise ValueError(f"Invalid file name in split {split}")
            if name in split_by_name:
                raise ValueError(f"File occurs in more than one split: {name}")
            split_by_name[name] = split

    manifest = read_json(manifest_path)
    if manifest.get("version") != "nail-texture-intake-batch/v1":
        raise ValueError("Unsupported intake manifest version")
    license_name = manifest.get("license")
    if license_name != "user-authorized-commercial-training-and-long-term-regression":
        raise ValueError("Intake manifest is not authorized for commercial training and long-term regression")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Intake manifest must contain at least one item")

    additions: list[dict[str, Any]] = []
    item_names: set[str] = set()
    group_splits: dict[str, set[str]] = {}
    for raw_item in items:
        if not isinstance(raw_item, dict):
            raise ValueError("Intake manifest item must be an object")
        file_name = raw_item.get("fileName")
        source_group = raw_item.get("sourceGroup")
        if not isinstance(file_name, str) or not file_name or Path(file_name).name != file_name:
            raise ValueError("Intake item has an invalid fileName")
        if not isinstance(source_group, str) or not source_group.strip():
            raise ValueError(f"Intake item has an invalid sourceGroup: {file_name}")
        if file_name in item_names or file_name in base_names:
            raise ValueError(f"Duplicate or already-present image file name: {file_name}")
        if Path(file_name).stem in base_label_stems:
            raise ValueError(f"Label stem collides with base dataset: {Path(file_name).stem}")
        split = split_by_name.get(file_name)
        if split is None:
            raise ValueError(f"Intake item is absent from formal split metadata: {file_name}")
        if split == "test":
            raise ValueError(f"New intake item cannot enter the frozen test split: {file_name}")
        image_path = dataset_images / file_name
        annotation_path = dataset_annotations / f"{Path(file_name).stem}.json"
        if not image_path.is_file() or not annotation_path.is_file():
            raise FileNotFoundError(f"Missing formal dataset image or annotation for {file_name}")
        document = read_json(annotation_path)
        if document.get("image", {}).get("fileName") != file_name:
            raise ValueError(f"Annotation image fileName mismatch: {annotation_path}")
        if document.get("image", {}).get("sourceGroup") != source_group:
            raise ValueError(f"Annotation sourceGroup mismatch: {annotation_path}")
        lines = yolo_lines(document)
        additions.append({
            "fileName": file_name,
            "sourceGroup": source_group,
            "split": split,
            "maskCount": len(lines),
            "imagePath": image_path,
            "lines": lines,
        })
        item_names.add(file_name)
        group_splits.setdefault(source_group, set()).add(split)
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise ValueError("A sourceGroup would cross train/val splits")

    shutil.copytree(base_dir, output_dir, ignore=shutil.ignore_patterns("*.cache"))
    try:
        for addition in additions:
            split = addition["split"]
            file_name = addition["fileName"]
            shutil.copy2(addition["imagePath"], output_dir / "images" / split / file_name)
            label_path = output_dir / "labels" / split / f"{Path(file_name).stem}.txt"
            label_path.write_text("\n".join(addition["lines"]) + "\n", encoding="utf-8")

        yaml = "\n".join([
            f'path: {str(output_dir).replace(chr(92), "/")}',
            "train: images/train", "val: images/val", "test: images/test", "", "names:",
            "  0: nail_texture", "", "task: segment", "class_count: 1", "image_size: 512", "",
        ])
        (output_dir / "dataset.yaml").write_text(yaml, encoding="utf-8")
        result_image_counts, result_mask_counts, _, _ = inventory(output_dir)
        frozen_after, frozen_files_after = frozen_split_digest(output_dir)
        if frozen_before != frozen_after or frozen_files_before != frozen_files_after:
            raise ValueError("Frozen test split changed while extending the dataset")

        added_split_counts = {split: 0 for split in SPLITS}
        added_mask_counts = {split: 0 for split in SPLITS}
        report_additions: list[dict[str, Any]] = []
        for addition in additions:
            split = addition["split"]
            added_split_counts[split] += 1
            added_mask_counts[split] += addition["maskCount"]
            report_additions.append({key: addition[key] for key in ("fileName", "sourceGroup", "split", "maskCount")})
        report = {
            "ok": True,
            "version": "nail-texture-source-isolated-extension/v1",
            "decision": "experiment_only_source_isolated_real_dataset",
            "baseDir": str(base_dir),
            "outputDir": str(output_dir),
            "intakeManifest": str(manifest_path),
            "license": license_name,
            "base": {"imageCount": sum(base_image_counts.values()), "splitCounts": base_image_counts, "maskCounts": base_mask_counts},
            "added": {"imageCount": len(additions), "maskCount": sum(item["maskCount"] for item in additions), "splitCounts": added_split_counts, "maskCounts": added_mask_counts, "items": report_additions},
            "result": {"imageCount": sum(result_image_counts.values()), "splitCounts": result_image_counts, "maskCounts": result_mask_counts},
            "frozenTest": {"imageCount": result_image_counts["test"], "maskCount": result_mask_counts["test"], "sha256": frozen_after, "files": frozen_files_after},
            "invariants": {"testHashUnchanged": True, "additionsExcludedFromTest": added_split_counts["test"] == 0, "sourceGroupsSingleSplit": True, "noFilenameCollisions": True},
        }
        (output_dir / "source-isolated-extension-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
