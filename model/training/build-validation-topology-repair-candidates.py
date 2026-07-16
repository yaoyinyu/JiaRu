#!/usr/bin/env python3
"""Build isolated YOLO validation-truth topology repair candidates.

The source labels are never modified. Every invalid polygon must be declared by
the bound score-threshold calibration report, and the output remains a review
candidate until its original-resolution overlays are explicitly accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from _training_common import load_dataset_config, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def parse_line(raw: str, path: Path, line_number: int) -> tuple[str, Polygon]:
    parts = raw.split()
    if len(parts) < 7:
        raise ValueError(f"{path}: line {line_number} is too short")
    class_id = parts[0]
    values = [float(value) for value in parts[1:]]
    if len(values) < 6 or len(values) % 2:
        raise ValueError(f"{path}: line {line_number} has invalid coordinates")
    if any(value < 0 or value > 1 for value in values):
        raise ValueError(f"{path}: line {line_number} escapes normalized bounds")
    return class_id, Polygon(list(zip(values[0::2], values[1::2])))


def select_repair(shape: Any, maximum_discard_ratio: float, label: str) -> tuple[Polygon, float]:
    repaired = shape.buffer(0)
    if repaired.is_empty:
        raise ValueError(f"{label} repair produced an empty geometry")
    if repaired.geom_type == "Polygon":
        return repaired, 0.0
    if repaired.geom_type != "MultiPolygon":
        raise ValueError(f"{label} repair produced unsupported {repaired.geom_type}")
    parts = sorted(repaired.geoms, key=lambda item: item.area, reverse=True)
    kept = parts[0]
    discarded = sum(item.area for item in parts[1:])
    ratio = discarded / repaired.area if repaired.area else 1.0
    if ratio > maximum_discard_ratio:
        raise ValueError(
            f"{label} discarded area ratio {ratio:.6f} exceeds {maximum_discard_ratio:.6f}"
        )
    return kept, ratio


def format_line(class_id: str, shape: Polygon) -> str:
    coordinates = [value for point in list(shape.exterior.coords)[:-1] for value in point]
    return " ".join([class_id, *(f"{value:.8f}" for value in coordinates)])


def image_for_stem(image_root: Path, stem: str) -> Path:
    matches = [path for path in image_root.glob(f"{stem}.*") if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one validation image for {stem}, found {len(matches)}")
    return matches[0]


def pixel_points(shape: Polygon, width: int, height: int) -> list[tuple[float, float]]:
    return [(x * width, y * height) for x, y in list(shape.exterior.coords)[:-1]]


def emit_evidence(
    image_path: Path,
    shapes: list[Polygon],
    repaired_indices: set[int],
    overlay_dir: Path,
    crop_dir: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    with Image.open(image_path) as source_image:
        source = source_image.convert("RGB")
    overlay = source.copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    for index, shape in enumerate(shapes, start=1):
        coords = pixel_points(shape, source.width, source.height)
        repaired = index in repaired_indices
        fill = (255, 145, 0, 88) if repaired else (0, 220, 90, 70)
        outline = (255, 80, 0, 255) if repaired else (0, 180, 70, 255)
        draw.polygon(coords, fill=fill, outline=outline, width=3)
        draw.text(coords[0], str(index), fill=(255, 20, 20, 255), stroke_width=2, stroke_fill="white")
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = overlay_dir / f"{image_path.stem}-validation-topology-candidate.png"
    overlay.save(overlay_path)

    crop_dir.mkdir(parents=True, exist_ok=True)
    crops: list[dict[str, Any]] = []
    for index in sorted(repaired_indices):
        shape = shapes[index - 1]
        min_x, min_y, max_x, max_y = shape.bounds
        padding = 32
        bounds = (
            max(0, int(min_x * source.width) - padding),
            max(0, int(min_y * source.height) - padding),
            min(source.width, int(max_x * source.width) + padding + 1),
            min(source.height, int(max_y * source.height) + padding + 1),
        )
        source_crop = source.crop(bounds)
        overlay_crop = overlay.crop(bounds)
        doubled = (source_crop.width * 2, source_crop.height * 2)
        source_crop = source_crop.resize(doubled, Image.Resampling.LANCZOS)
        overlay_crop = overlay_crop.resize(doubled, Image.Resampling.LANCZOS)
        source_path = crop_dir / f"{image_path.stem}-source-n{index}-2x.png"
        candidate_path = crop_dir / f"{image_path.stem}-candidate-n{index}-2x.png"
        source_crop.save(source_path)
        overlay_crop.save(candidate_path)
        crops.append(
            {
                "nailIndex": index,
                "source": str(source_path.resolve()),
                "candidate": str(candidate_path.resolve()),
            }
        )
    return overlay_path, crops


def build(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = Path(args.dataset).resolve()
    dataset = load_dataset_config(dataset_path)
    calibration_path = Path(args.calibration_report).resolve()
    calibration = read_json(calibration_path)
    if calibration.get("decision") != "diagnostic_only_validation_truth_requires_repair":
        raise ValueError("calibration report does not require validation truth repair")
    if calibration.get("calibrationEligible") is not False or calibration.get("manifestScoreThreshold") is not None:
        raise ValueError("repair candidates require an ineligible calibration with a null manifest threshold")
    inputs = calibration.get("inputs", {})
    if inputs.get("split") != "val":
        raise ValueError("repair candidates are restricted to split=val")
    if Path(str(inputs.get("datasetYaml", ""))).resolve() != dataset_path:
        raise ValueError("calibration dataset path does not match")
    if inputs.get("datasetYamlSha256") != sha256(dataset_path):
        raise ValueError("calibration dataset hash does not match current input")
    source_report_path = Path(str(inputs.get("datasetReport", ""))).resolve()
    if not source_report_path.is_file() or inputs.get("datasetReportSha256") != sha256(source_report_path):
        raise ValueError("calibration source-isolation report hash does not match")
    source_report = read_json(source_report_path)
    if source_report.get("decision") != "experiment_only_source_isolated_real_dataset":
        raise ValueError("source report is not an isolated real-data experiment")
    if Path(str(source_report.get("outputDir", ""))).resolve() != dataset.dataset_root:
        raise ValueError("source report outputDir does not match dataset root")

    labels_root = dataset.dataset_root / "labels" / "val"
    images_root = dataset.dataset_root / "images" / "val"
    output_labels = Path(args.output_labels).resolve()
    if output_labels == labels_root or labels_root in output_labels.parents:
        raise ValueError("candidate labels must be outside the source validation label directory")
    output_labels.mkdir(parents=True, exist_ok=True)
    overlay_dir = Path(args.overlay_dir).resolve()
    crop_dir = Path(args.crop_dir).resolve()
    maximum_discard_ratio = float(args.maximum_discard_ratio)

    declared: dict[str, set[int]] = {}
    for record in calibration.get("repairedTruthRecords", []):
        declared.setdefault(str(record["fileName"]), set()).add(int(record["line"]))
    if sum(map(len, declared.values())) != int(calibration.get("counts", {}).get("repairedTruthPolygons", -1)):
        raise ValueError("calibration repaired-truth count does not match its records")

    outputs: list[dict[str, Any]] = []
    overlap_blockers: list[dict[str, Any]] = []
    actual_invalid: set[tuple[str, int]] = set()
    for source_path in sorted(labels_root.glob("*.txt")):
        raw_lines = source_path.read_text(encoding="utf-8").splitlines()
        parsed: list[tuple[str, Polygon]] = []
        for line_number, raw in enumerate(raw_lines, start=1):
            if not raw.strip():
                continue
            item = parse_line(raw, source_path, line_number)
            parsed.append(item)
            if not item[1].is_valid or item[1].area <= 0:
                actual_invalid.add((source_path.name, line_number))
        requested = declared.get(source_path.name, set())
        repairs: list[dict[str, Any]] = []
        candidate_lines: list[str] = []
        shapes: list[Polygon] = []
        for line_number, (class_id, before) in enumerate(parsed, start=1):
            after = before
            if line_number in requested:
                after, discarded_ratio = select_repair(
                    before, maximum_discard_ratio, f"{source_path.name}:{line_number}"
                )
                repairs.append(
                    {
                        "nailIndex": line_number,
                        "beforeArea": before.area,
                        "afterArea": after.area,
                        "relativeAreaDelta": abs(after.area - before.area) / max(after.area, 1e-12),
                        "discardedAreaRatio": discarded_ratio,
                    }
                )
            if not after.is_valid or after.is_empty or after.area <= 0:
                raise ValueError(f"{source_path.name}:{line_number} remains invalid")
            shapes.append(after)
            candidate_lines.append(format_line(class_id, after) if line_number in requested else raw_lines[line_number - 1])

        overlaps = []
        for left_index, left in enumerate(shapes, start=1):
            for right_index in range(left_index + 1, len(shapes) + 1):
                area = left.intersection(shapes[right_index - 1]).area
                if area > 1e-10:
                    overlaps.append({"left": left_index, "right": right_index, "area": area})
        if overlaps:
            overlap_blockers.append({"fileName": source_path.name, "overlaps": overlaps})

        output_path = output_labels / source_path.name
        output_path.write_text("\n".join(candidate_lines) + ("\n" if candidate_lines else ""), encoding="utf-8")
        image_path = image_for_stem(images_root, source_path.stem)
        overlay_path, crops = emit_evidence(
            image_path, shapes, requested, overlay_dir, crop_dir
        )
        outputs.append(
            {
                "fileName": source_path.name,
                "imagePath": str(image_path.resolve()),
                "sourceLabelSha256": sha256(source_path),
                "candidateLabelPath": str(output_path.resolve()),
                "candidateLabelSha256": sha256(output_path),
                "overlayPath": str(overlay_path.resolve()),
                "polygonCount": len(shapes),
                "pairwiseOverlapCount": len(overlaps),
                "pairwiseOverlaps": overlaps,
                "repairs": repairs,
                "zoomPaths": crops,
            }
        )

    expected_invalid = {(name, line) for name, lines in declared.items() for line in lines}
    if actual_invalid != expected_invalid:
        raise ValueError(
            f"invalid polygon declaration mismatch: expected={sorted(expected_invalid)} actual={sorted(actual_invalid)}"
        )
    unknown_files = sorted(set(declared) - {path.name for path in labels_root.glob("*.txt")})
    if unknown_files:
        raise ValueError(f"calibration declares missing validation labels: {unknown_files}")
    return {
        "ok": not overlap_blockers,
        "schemaVersion": 1,
        "decision": (
            "candidate_only_requires_original_resolution_review"
            if not overlap_blockers
            else "blocked_undeclared_validation_truth_overlaps"
        ),
        "inputs": {
            "datasetYaml": str(dataset_path),
            "datasetYamlSha256": sha256(dataset_path),
            "sourceIsolationReport": str(source_report_path),
            "sourceIsolationReportSha256": sha256(source_report_path),
            "calibrationReport": str(calibration_path),
            "calibrationReportSha256": sha256(calibration_path),
            "split": "val",
        },
        "counts": {
            "validationLabels": len(list(labels_root.glob("*.txt"))),
            "affectedImages": sum(bool(item["repairs"]) for item in outputs),
            "reviewImages": len(outputs),
            "repairedPolygons": sum(len(item["repairs"]) for item in outputs),
        },
        "maximumDiscardedAreaRatio": maximum_discard_ratio,
        "sourceLabelsUnmodified": True,
        "overlapBlockers": overlap_blockers,
        "outputs": outputs,
        "reviewRequirement": "Inspect every full-resolution overlay and every repaired-nail source/candidate 2x crop before approval.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build isolated validation topology repair candidates.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--calibration-report", required=True)
    parser.add_argument("--output-labels", required=True)
    parser.add_argument("--overlay-dir", required=True)
    parser.add_argument("--crop-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--maximum-discard-ratio", type=float, default=0.05)
    args = parser.parse_args()
    if args.maximum_discard_ratio < 0 or args.maximum_discard_ratio > 0.10:
        raise ValueError("maximum discard ratio must be between 0 and 0.10")
    report = build(args)
    output = Path(args.report).resolve()
    write_json(output, report)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "overlapBlockers": report["overlapBlockers"], "report": str(output)}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
