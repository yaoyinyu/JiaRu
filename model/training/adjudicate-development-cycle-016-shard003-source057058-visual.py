#!/usr/bin/env python3
"""Bind source-57 quality stoploss and source-58 five-nail visual adjudication."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, box


REASONS_58 = {
    1: "Retained gray-to-pink extension covers the full visible nail to the distal edge without adjacent skin.",
    2: "V2 manual cuticle contour removes the old step while retaining the full floral and nude distal surface.",
    3: "Retained nude contour covers the complete visible plate, ornament, and distal extension.",
    4: "V1 manual contour removes proximal skinward spikes and covers the full pink-to-clear extension.",
    5: "Retained thumb contour covers the visible cuticle-to-tip nail without finger-pad contamination.",
}
MARKER_BOX_58 = [1035, 1408, 1078, 1438]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def check_marker_crop(source: dict, output: Path) -> dict:
    path = checked(source["isolatedImage"])
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    crop = image.crop((width - 180, height - 140, width, height))
    crop = crop.resize((540, 420), Image.Resampling.NEAREST)
    if not output.exists():
        crop.save(output, format="PNG")
    with Image.open(output) as opened:
        actual = opened.convert("RGB")
    if actual.size != crop.size or actual.tobytes() != crop.tobytes():
        raise ValueError("source-marker crop pixel drift")
    return bind(output)


def build(v1_path: Path, v2_path: Path) -> dict:
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    if (v1["decision"] != "source057058_five_nail_candidates_geometry_pass_visual_pending"
            or v2["decision"] != "source058_five_nail_candidate_v2_geometry_pass_visual_pending"
            or v1["counts"] != {"sourceImages": 2, "nails": 10,
                                "legalPolygons": 10, "overlapPairs": 0,
                                "visualApprovals": 0, "trainingApproved": 0}
            or v2["counts"] != {"sourceImages": 1, "nails": 5,
                                "legalPolygons": 5, "overlapPairs": 0,
                                "visualApprovals": 0, "trainingApproved": 0}):
        raise ValueError("candidate state drift")
    for document in (v1, v2):
        for item in document["inputs"].values():
            checked(item)
    source57, source58_v1 = v1["sources"]
    source58_v2 = v2["source"]
    if ([source57["ordinal"], source58_v1["ordinal"], source58_v2["ordinal"]]
            != [57, 58, 58]
            or source57["sourceGroup"] != source58_v2["sourceGroup"]
            or source58_v1["sourceImage"] != source58_v2["sourceImage"]
            or source58_v1["sourceLabel"] != source58_v2["sourceLabel"]
            or source58_v1["historicalCanonicalTruthCount"] != 1
            or source58_v2["historicalCanonicalTruthCount"] != 1):
        raise ValueError("source identity or historical canonical drift")
    for source in (source57, source58_v1, source58_v2):
        if source["trainingUse"] != "prohibited" or len(source["nails"]) != 5:
            raise ValueError("premature training approval or nail count drift")
        for key in ("sourceImage", "sourceLabel", "isolatedImage",
                    "candidateAnnotation", "fullOutline"):
            checked(source[key])
        for nail in source["nails"]:
            checked(nail["raw3x"])
            checked(nail["outline3x"])
    original58 = json.loads(checked(source58_v1["candidateAnnotation"]).read_text(encoding="utf-8"))
    final58 = json.loads(checked(source58_v2["candidateAnnotation"]).read_text(encoding="utf-8"))
    for index in (0, 2, 3, 4):
        if final58["annotations"][index] != original58["annotations"][index]:
            raise ValueError(f"non-target nail {index + 1} changed in v2")
    if [nail["method"] for nail in source58_v2["nails"]] != [
        "retained_old", "manual_original_resolution", "retained_old",
        "manual_original_resolution", "retained_old"]:
        raise ValueError("final hybrid method roster drift")
    shapes = [Polygon([(point["x"], point["y"]) for point in nail["polygon"]])
              for nail in final58["annotations"]]
    if any(not shape.is_valid or shape.area <= 1 for shape in shapes):
        raise ValueError("invalid final polygon")
    marker = box(*MARKER_BOX_58)
    if any(shape.intersection(marker).area > 0 for shape in shapes):
        raise ValueError("source marker overlaps a nail mask")
    marker_crop57 = check_marker_crop(
        source57, Path(source57["candidateAnnotation"]["path"]).parent.parent /
        "source-057-bottom-right-raw-3x.png")
    marker_crop58 = check_marker_crop(
        source58_v2, Path(source58_v2["candidateAnnotation"]["path"]).parent.parent /
        "source-058-bottom-right-raw-3x.png")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source057_quality_stoploss_source058_five_masks_visual_pass_roles_pending",
        "inputs": {"sourceScript": bind(Path(__file__)),
                   "rejectedCandidateV1": bind(v1_path),
                   "source058CandidateV2": bind(v2_path)},
        "source057": {
            "ordinal": 57, "sourceFileName": source57["sourceFileName"],
            "sourceGroup": source57["sourceGroup"],
            "sourceImage": source57["sourceImage"],
            "sourceLabel": source57["sourceLabel"],
            "rejectedCandidateAnnotation": source57["candidateAnnotation"],
            "fullOutline": source57["fullOutline"],
            "thumbRaw3x": source57["nails"][3]["raw3x"],
            "thumbOutline3x": source57["nails"][3]["outline3x"],
            "markerCrop3x": marker_crop57,
            "reason": "Thumb nail-4 proximal translucent surface blends into finger skin; the old polygon extends into an unconfirmable skin boundary. Nail-5 tip repair does not make the whole image acceptable.",
            "decision": "source_quality_excluded_next_train_only",
            "historicalCanonicalTruthCount": 1,
            "oldLabelNailsPreserved": 5, "trainingUse": "prohibited",
        },
        "source058": {
            "ordinal": 58, "sourceFileName": source58_v2["sourceFileName"],
            "sourceGroup": source58_v2["sourceGroup"],
            "sourceImage": source58_v2["sourceImage"],
            "sourceLabel": source58_v2["sourceLabel"],
            "candidateAnnotation": source58_v2["candidateAnnotation"],
            "fullOutline": source58_v2["fullOutline"],
            "nails": [{"truthIndex": nail["truthIndex"], "method": nail["method"],
                       "decision": "pass_original_resolution_complete_surface",
                       "reason": REASONS_58[nail["truthIndex"]],
                       "raw3x": nail["raw3x"], "outline3x": nail["outline3x"]}
                      for nail in source58_v2["nails"]],
            "sourceMarker": {"kind": "faint_bottom_right_platform_glyph",
                             "bboxOriginalPixels": MARKER_BOX_58,
                             "crop3x": marker_crop58,
                             "nailMaskOverlapArea": 0,
                             "futureModelShortcutAblation": "pending"},
            "decision": "five_complete_masks_visual_pass_role_and_marker_pending",
            "historicalCanonicalTruthCount": 1,
            "trainingUse": "prohibited",
        },
        "counts": {"sourceImagesQualityExcludedNextTrain": 1,
                   "sourceImagesMaskVisualPassRolePending": 1,
                   "maskVisualPassNails": 5, "newTrainingApproved": 0},
        "historicalSnapshotChanged": False,
        "historicalCanonicalChanged": False,
        "protectedRolesChanged": False,
        "limitations": [
            "Original-pixel visual judgments remain human judgments; hash replay binds source pixels and decisions.",
            "The historical canonical records and cycle012 training snapshots are retained without rewriting past failures.",
            "The faint source glyph is outside all five masks, but future-model four-variant shortcut ablation and full-split role checks remain open.",
        ],
        "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rejected-candidate-v1", type=Path)
    parser.add_argument("--source058-candidate-v2", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in saved["inputs"].values():
            checked(item)
        current = build(Path(saved["inputs"]["rejectedCandidateV1"]["path"]),
                        Path(saved["inputs"]["source058CandidateV2"]["path"]))
        if current != saved:
            raise SystemExit("reconstruction_mismatch")
        result = {"ok": True, "decision": "verified_source057058_visual_adjudication",
                  "counts": saved["counts"]}
    else:
        if not all((args.rejected_candidate_v1, args.source058_candidate_v2, args.report)):
            parser.error("all inputs and --report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.rejected_candidate_v1.resolve(),
                       args.source058_candidate_v2.resolve())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
