#!/usr/bin/env python3
"""Isolate source24 from the next train candidate without rewriting old data.

The visible corner logo is an untested shortcut risk, not evidence that any
model has learned it. The incomplete old mask and unpromoted repair remain
separate, hash-bound facts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon, box


WATERMARK_BBOX = (1033, 1053, 1076, 1075)
CROP_BBOX = (1000, 1020, 1080, 1080)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(binding: dict) -> None:
    path = Path(binding["path"])
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(progress_path: Path, candidate_path: Path, crop_path: Path) -> dict:
    progress, candidate = load(progress_path), load(candidate_path)
    row = next((item for item in progress["sourceDispositions"] if item["ordinal"] == 24), None)
    peer = next((item for item in progress["sourceDispositions"] if item["ordinal"] == 21), None)
    if (progress.get("schemaVersion") != 6 or not progress.get("ok") or
            row is None or peer is None or
            row["decision"] != "confirmed_label_rework" or row["oldLabelNails"] != 5 or
            row["everyNailVisualApproval"] or row["trainingUse"] != "prohibited" or
            peer["sourceGroup"] != row["sourceGroup"] or
            peer["decision"] != "historical_truth_correction_visual_pass_pending_full_split" or
            not peer["everyNailVisualApproval"] or
            candidate.get("decision") != "source024_hybrid_candidate_geometry_pass_visual_pending" or
            candidate["sourceOrdinal"] != 24 or
            candidate["sourceFileName"] != row["sourceFileName"] or
            candidate["sourceGroup"] != row["sourceGroup"] or
            candidate["sourceImage"] != row["sourceImage"] or
            candidate["counts"]["visualApproved"] != 0 or
            candidate["counts"]["trainingApproved"] != 0 or
            candidate["trainingUse"] != "prohibited" or
            candidate["inputs"]["progressV6"]["sha256"] != sha(progress_path)):
        raise ValueError("source24/peer/candidate contract mismatch")
    for binding in candidate["inputs"].values():
        if isinstance(binding, list):
            for item in binding:
                checked(item)
        else:
            checked(binding)
    if sha(Path(row["sourceImage"]["path"])) != row["sourceImage"]["sha256"]:
        raise ValueError("frozen original source image drift")
    annotation = load(Path(candidate["inputs"]["candidateAnnotation"]["path"]))
    if (annotation["image"]["fileName"] != row["sourceFileName"] or
            annotation["image"]["sourceGroup"] != row["sourceGroup"] or
            len(annotation["annotations"]) != 5 or
            annotation["trainingUse"] != "prohibited"):
        raise ValueError("candidate annotation drift")
    mark = box(*WATERMARK_BBOX)
    if any(mark.intersection(Polygon([(p["x"], p["y"]) for p in nail["polygon"]])).area > 0
           for nail in annotation["annotations"]):
        raise ValueError("corner logo overlaps candidate nail mask")
    # Reconstruct the visual evidence from the isolated, hash-identical source.
    with Image.open(candidate["inputs"]["isolatedSourceImage"]["path"]) as image:
        if image.size != (1080, 1080):
            raise ValueError("unexpected source dimensions")
        crop = image.crop(CROP_BBOX).resize((640, 480))
        stream = io.BytesIO()
        crop.save(stream, format="PNG")
    if not crop_path.is_file() or sha(crop_path) != hashlib.sha256(stream.getvalue()).hexdigest():
        raise ValueError("watermark evidence crop mismatch")
    return {
        "schemaVersion": 1, "ok": True,
        "decision": "source024_isolate_from_next_train_candidate_unproven_corner_logo_shortcut",
        "inputs": {"sourceScript": bind(Path(__file__)), "progressV6": bind(progress_path),
                   "hybridCandidate": bind(candidate_path), "watermarkCrop": bind(crop_path),
                   "frozenSourceImage": row["sourceImage"]},
        "sourceOrdinal": 24, "sourceFileName": row["sourceFileName"],
        "sourceGroup": row["sourceGroup"], "sameGroupReviewedPeerOrdinal": 21,
        "watermark": {"type": "visible_xiaohongshu_corner_logo_on_black_background",
                      "bboxPixels": list(WATERMARK_BBOX), "overlapsCandidateNailMasks": False,
                      "shortcutAbsenceProven": False},
        "oldLabelDefect": "fifth_nail_contains_only_decoration_segment",
        "repairCandidateDisposition": "geometry_pass_visual_not_promoted",
        "nextTrainCandidateDisposition": "isolate_source_and_all_derivatives",
        "historicalSnapshotChanged": False, "newTrainingApprovedSources": 0,
        "fullShardCleanTruthComplete": False, "trainingUse": "prohibited",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--watermark-crop", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["progressV6"]["path"]),
                        Path(inputs["hybridCandidate"]["path"]),
                        Path(inputs["watermarkCrop"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "watermark": current["watermark"]}))
        return
    if not all((args.progress, args.candidate, args.watermark_crop, args.output)):
        parser.error("--progress, --candidate, --watermark-crop and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.progress.resolve(), args.candidate.resolve(),
                   args.watermark_crop.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "watermark": report["watermark"]}))


if __name__ == "__main__":
    main()
