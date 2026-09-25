#!/usr/bin/env python3
"""Bind source33's historical defective label and isolate its untested logo risk."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, box


TARGET = "nail_00357_69eda4b9000000003502a7b8_4.jpg"
CROP_BOX = (1010, 1385, 1080, 1440)
LOGO_BOX = (1034, 1411, 1075, 1437)


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


def build(progress_path: Path, focused_path: Path, historical_path: Path,
          index_path: Path, crop_path: Path) -> dict:
    progress, focused, historical, index = map(
        load, (progress_path, focused_path, historical_path, index_path))
    row = next((item for item in progress["sourceDispositions"]
                if item["ordinal"] == 33), None)
    if (progress.get("schemaVersion") != 8 or not progress.get("ok") or row is None or
            row["sourceFileName"] != TARGET or row["decision"] != "confirmed_label_rework" or
            row["oldLabelNails"] != 5 or row["everyNailVisualApproval"] or
            row["trainingUse"] != "prohibited" or
            focused["decision"] != "confirmed_label_rework" or
            focused["sourceOrdinal"] != 33 or focused["sourceFileName"] != TARGET or
            focused["sourceGroup"] != row["sourceGroup"] or
            focused["sourceImage"] != row["sourceImage"] or
            focused["sourceLabel"] != row["sourceLabel"] or
            focused["humanDecision"]["focusTruthIndices"] != [1, 3, 4, 5] or
            not focused["humanDecision"]["watermarkReviewRequired"] or
            focused["trainingUse"] != "prohibited" or
            historical["decision"] !=
            "approved_as_training_truth_candidate_pending_dataset_materialization" or
            historical["inputs"]["truthRole"] != "train" or
            historical["item"]["fileName"] != TARGET or
            historical["item"]["sha256"] != row["sourceImage"]["sha256"] or
            historical["item"]["sourceGroup"] != row["sourceGroup"] or
            historical["item"]["completeMaskCount"] != 5 or
            historical["item"]["trainingUse"] != "prohibited-until-materialization-audit"):
        raise ValueError("source33 current/historical identity or role mismatch")
    for binding in focused["inputs"].values():
        checked(binding)
    for binding in (row["sourceImage"], row["sourceLabel"]):
        checked(binding)
    annotation_path = Path(historical["inputs"]["annotation"])
    if (sha(annotation_path) != historical["inputs"]["annotationSha256"] or
            sha(Path(historical["inputs"]["visualReviewFinal"])) !=
            historical["inputs"]["visualReviewFinalSha256"] or
            sha(Path(historical["inputs"]["image"])) !=
            historical["inputs"]["imageSha256"]):
        raise ValueError("historical approval evidence drift")
    annotation = load(annotation_path)
    if (annotation["image"]["fileName"] != TARGET or
            annotation["image"]["sourceGroup"] != row["sourceGroup"] or
            len(annotation["annotations"]) != 5):
        raise ValueError("historical annotation structure mismatch")
    width, height = annotation["image"]["width"], annotation["image"]["height"]
    if (width, height) != (1080, 1440):
        raise ValueError("source33 dimensions drifted")
    lines = Path(row["sourceLabel"]["path"]).read_text(encoding="utf-8").splitlines()
    if len(lines) != 5:
        raise ValueError("cycle012 label count drifted")
    counts, maximum = [], 0.0
    for number, (nail, line) in enumerate(zip(annotation["annotations"], lines, strict=True), 1):
        values = [float(value) for value in line.split()]
        points = nail["polygon"]
        if values[0] != 0 or len(values) != 1 + 2 * len(points):
            raise ValueError(f"historical/cycle012 nail {number} vertex mismatch")
        counts.append(len(points))
        for vertex, point in enumerate(points):
            maximum = max(maximum,
                          abs(point["x"] / width - values[1 + 2 * vertex]),
                          abs(point["y"] / height - values[2 + 2 * vertex]))
    if maximum > 5e-9:
        raise ValueError(f"historical/cycle012 polygon mismatch: {maximum}")
    same_name = [item for item in index["canonicalTruths"] if item["fileName"] == TARGET]
    if same_name:
        raise ValueError("unexpected older canonical truth for source33")
    with Image.open(row["sourceImage"]["path"]) as image:
        if image.size != (width, height):
            raise ValueError("source image size drifted")
        crop = image.crop(CROP_BOX).resize((560, 440))
        stream = io.BytesIO()
        crop.save(stream, format="PNG")
    if not crop_path.is_file() or sha(crop_path) != hashlib.sha256(stream.getvalue()).hexdigest():
        raise ValueError("logo crop mismatch")
    logo = box(*LOGO_BOX)
    polygons = [Polygon([(point["x"], point["y"]) for point in nail["polygon"]])
                for nail in annotation["annotations"]]
    if any(logo.intersection(polygon).area > 0 for polygon in polygons):
        raise ValueError("logo overlaps a historical nail polygon")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source033_isolate_from_next_train_candidate_defective_old_masks_unproven_logo_shortcut",
        "inputs": {"sourceScript": bind(Path(__file__)), "progressV8": bind(progress_path),
                   "focusedAudit": bind(focused_path), "historicalTrainingTruthReport": bind(historical_path),
                   "historicalAnnotation": bind(annotation_path), "historicalVisualFinal":
                   bind(Path(historical["inputs"]["visualReviewFinal"])),
                   "canonicalIndex": bind(index_path), "sourceImage": row["sourceImage"],
                   "cycle012Label": row["sourceLabel"], "watermarkCrop": bind(crop_path)},
        "sourceOrdinal": 33, "sourceFileName": TARGET, "sourceGroup": row["sourceGroup"],
        "historicalTruthReportDecision": historical["decision"],
        "historicalCandidateSameAsCycle012Label": True,
        "counts": {"historicalCanonicalRecordsWithSameFileName": 0,
                   "historicalTrainingCandidateReports": 1, "polygons": 5,
                   "vertexCounts": counts, "maxNormalizedVertexDelta": maximum,
                   "newTrainingApprovedSources": 0},
        "oldMaskDefects": "indices_1_3_4_5_root_jagged_or_skin_intrusion",
        "watermark": {"type": "visible_xiaohongshu_corner_logo",
                      "bboxPixels": list(LOGO_BOX), "cropPixels": list(CROP_BOX),
                      "overlapsHistoricalNailMasks": False,
                      "fourVariantAblationComplete": False,
                      "shortcutAbsenceProven": False},
        "nextTrainCandidateDisposition": "isolate_source_and_all_derivatives",
        "historicalSnapshotChanged": False, "fullShardCleanTruthComplete": False,
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--focused", type=Path)
    parser.add_argument("--historical-report", type=Path)
    parser.add_argument("--canonical-index", type=Path)
    parser.add_argument("--watermark-crop", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        previous = load(args.verify_report)
        for binding in previous["inputs"].values():
            checked(binding)
        current = build(Path(previous["inputs"]["progressV8"]["path"]),
                        Path(previous["inputs"]["focusedAudit"]["path"]),
                        Path(previous["inputs"]["historicalTrainingTruthReport"]["path"]),
                        Path(previous["inputs"]["canonicalIndex"]["path"]),
                        Path(previous["inputs"]["watermarkCrop"]["path"]))
        if current != previous:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.progress, args.focused, args.historical_report,
                args.canonical_index, args.watermark_crop, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.focused.resolve(),
                   args.historical_report.resolve(), args.canonical_index.resolve(),
                   args.watermark_crop.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
