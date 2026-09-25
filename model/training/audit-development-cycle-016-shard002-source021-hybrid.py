#!/usr/bin/env python3
"""Replay source21's hash-bound mixed manual/SAM candidate without promotion."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image
from shapely.geometry import Point, Polygon


TARGET = "nail_01085_69a5ad16000000002303ba31_0.jpg"


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


def build(shard_path: Path, progress_path: Path, canonical_path: Path,
          rejected_path: Path, manifest_path: Path, builder_path: Path,
          hybrid_path: Path) -> dict:
    shard, progress, canonical, rejected, manifest, hybrid = map(
        load, (shard_path, progress_path, canonical_path, rejected_path,
               manifest_path, hybrid_path))
    source = next(item for item in shard["sourceImages"] if item["ordinal"] == 21)
    row = next(item for item in progress["sourceDispositions"] if item["ordinal"] == 21)
    if (shard["shard"]["shard"] != 2 or not progress["ok"] or
            row["decision"] != "confirmed_label_rework" or
            row["sourceImage"] != source["sourceImage"] or
            row["sourceLabel"] != source["sourceLabel"] or
            row["sourceFileName"] != TARGET or
            canonical["decision"] != "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["sourceImageSha256"] != source["sourceImage"]["sha256"] or
            canonical["newImageCount"] != 0 or
            rejected["decision"] != "shard002_sam_candidate_geometry_rejected" or
            rejected["sourceOrdinal"] != 21 or
            rejected["sourceFileName"] != TARGET or
            rejected["counts"]["legalPolygons"] != 5 or
            rejected["counts"]["positivePointRowsInside"] != 4 or
            rejected["counts"]["visualApproved"] != 0 or
            manifest["decision"] != "source021_hybrid_repair_candidate_only" or
            manifest["trainingUse"] != "prohibited" or
            not manifest["reviewBasis"] or
            len(manifest["images"]) != 1 or
            not hybrid["ok"] or hybrid["imageCount"] != 1 or
            hybrid["completedCount"] != 1 or hybrid["polygonCount"] != 5 or
            hybrid["retainedPolygonCount"] != 4 or hybrid["manualPolygonCount"] != 1 or
            hybrid["pairwiseOverlapCount"] != 0 or hybrid["errors"]):
        raise ValueError("frozen source/canonical/SAM/hybrid contract mismatch")
    for report in (canonical, rejected):
        for binding in report["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
    item, output = manifest["images"][0], hybrid["outputs"][0]
    source_copy = Path(rejected["inputs"]["sourceCopy"]["path"])
    sam_annotation_path = Path(rejected["inputs"]["annotation"]["path"])
    hybrid_annotation_path = Path(output["annotationPath"])
    overlay_path = Path(output["overlayPath"])
    if (item["fileName"] != TARGET or output["fileName"] != TARGET or
            item["sourceGroup"] != source["sourceGroup"] or
            output["sourceGroup"] != source["sourceGroup"] or
            Path(item["sourceAnnotationPath"]).resolve() != sam_annotation_path.resolve() or
            sha(source_copy) != source["sourceImage"]["sha256"] or
            [nail.get("sourceIndex") for nail in item["nails"]] != [1, None, 3, 4, 5]):
        raise ValueError("hybrid source identity/nail mapping mismatch")
    sam, annotation = load(sam_annotation_path), load(hybrid_annotation_path)
    if (annotation["decision"] != "candidate_only_not_training_or_test_truth" or
            annotation["trainingUse"] != "prohibited" or
            annotation["image"]["fileName"] != TARGET or
            annotation["image"]["sourceGroup"] != source["sourceGroup"] or
            len(annotation["annotations"]) != 5 or len(sam["annotations"]) != 5):
        raise ValueError("hybrid annotation role/count mismatch")
    with Image.open(source_copy) as source_image, Image.open(overlay_path) as overlay:
        if source_image.size != (1080, 1080) or overlay.size != source_image.size:
            raise ValueError("source/overlay dimensions drift")
    shapes = []
    for index, (new, old) in enumerate(zip(annotation["annotations"], sam["annotations"], strict=True), start=1):
        if new["id"] != f"n{index}" or new["label"] != "nail_texture":
            raise ValueError("hybrid nail ordering drift")
        if index == 2:
            if new["polygon"] == old["polygon"] or new["polygon"] != item["nails"][1]["polygon"]:
                raise ValueError("nail2 was not independently redrawn")
            if new["attributes"]["annotationMethod"] != "codex-original-resolution-manual":
                raise ValueError("nail2 manual provenance missing")
        elif new["polygon"] != old["polygon"]:
            raise ValueError(f"retained nail {index} changed from SAM v2")
        shape = Polygon([(float(point["x"]), float(point["y"])) for point in new["polygon"]])
        if not shape.is_valid or shape.area <= 16:
            raise ValueError(f"hybrid nail {index} invalid")
        shapes.append(shape)
    overlap_pairs = sum(shapes[i].intersection(shapes[j]).area > 1e-10
                        for i in range(5) for j in range(i + 1, 5))
    if overlap_pairs:
        raise ValueError("hybrid nails overlap")
    x1, y1, x2, y2 = manifest["qaBox"]
    if (not (0 <= x1 < x2 <= 1080 and 0 <= y1 < y2 <= 1080) or
            not (x1 <= shapes[1].bounds[0] and y1 <= shapes[1].bounds[1] and
                 shapes[1].bounds[2] <= x2 and shapes[1].bounds[3] <= y2) or
            len(manifest["qaPositivePoints"]) < 3 or
            len(manifest["qaNegativePoints"]) < 3):
        raise ValueError("manual nail2 QA box/point count mismatch")
    positive_inside = sum(shapes[1].covers(Point(x, y)) for x, y in manifest["qaPositivePoints"])
    negative_outside = sum(not shapes[1].covers(Point(x, y)) for x, y in manifest["qaNegativePoints"])
    if positive_inside != len(manifest["qaPositivePoints"]) or negative_outside != len(manifest["qaNegativePoints"]):
        raise ValueError("manual nail2 QA point geometry mismatch")
    if len(output["zoomPaths"]) != 5:
        raise ValueError("original-resolution review crops missing")
    crop_bindings = []
    for crop in output["zoomPaths"]:
        for key in ("source", "overlay"):
            crop_bindings.append(bind(Path(crop[key])))
    return {"schemaVersion": 1, "ok": True,
            "decision": "source021_hybrid_candidate_geometry_pass_visual_pending",
            "trainingUse": "prohibited", "sourceOrdinal": 21,
            "sourceFileName": TARGET, "sourceGroup": source["sourceGroup"],
            "inputs": {"sourceScript": bind(Path(__file__)), "shardReport": bind(shard_path),
                       "progressV5": bind(progress_path), "canonicalIdentityAudit": bind(canonical_path),
                       "rejectedSamV2Audit": bind(rejected_path), "manualManifest": bind(manifest_path),
                       "hybridBuilder": bind(builder_path), "hybridBuildReport": bind(hybrid_path),
                       "isolatedSource": bind(source_copy), "sourceAnnotation": bind(sam_annotation_path),
                       "candidateAnnotation": bind(hybrid_annotation_path),
                       "candidateOverlay": bind(overlay_path), "reviewCrops": crop_bindings},
            "counts": {"sources": 1, "nails": 5, "retainedReviewedSamPolygons": 4,
                       "redrawnManualPolygons": 1, "legalPolygons": 5, "overlapPairs": 0,
                       "manualQaPositiveInside": positive_inside,
                       "manualQaNegativeOutside": negative_outside,
                       "visualApproved": 0, "trainingApproved": 0,
                       "newImageCount": 0}}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("shard", "progress", "canonical", "rejected", "manifest", "builder", "hybrid-report", "output", "verify-report"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = load(args.verify_report)
        for binding in old["inputs"].values():
            if isinstance(binding, list):
                for item in binding:
                    checked(item)
            else:
                checked(binding)
        inputs = old["inputs"]
        current = build(Path(inputs["shardReport"]["path"]),
                        Path(inputs["progressV5"]["path"]),
                        Path(inputs["canonicalIdentityAudit"]["path"]),
                        Path(inputs["rejectedSamV2Audit"]["path"]),
                        Path(inputs["manualManifest"]["path"]),
                        Path(inputs["hybridBuilder"]["path"]),
                        Path(inputs["hybridBuildReport"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"], "counts": current["counts"]}))
        return
    if not all((args.shard, args.progress, args.canonical, args.rejected,
                args.manifest, args.builder, args.hybrid_report, args.output)):
        parser.error("all source inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.shard.resolve(), args.progress.resolve(), args.canonical.resolve(),
                   args.rejected.resolve(), args.manifest.resolve(), args.builder.resolve(),
                   args.hybrid_report.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
