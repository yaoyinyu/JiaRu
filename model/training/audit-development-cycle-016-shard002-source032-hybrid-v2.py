#!/usr/bin/env python3
"""Replay source32's final four-manual, one-retained-SAM candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, Polygon


QA = {
    1: {"positive": [[400, 750], [405, 830], [414, 890]],
        "negative": [[400, 712], [448, 820], [400, 915]]},
    2: {"positive": [[521, 800], [503, 860], [466, 943]],
        "negative": [[520, 750], [558, 843], [439, 970]]},
}


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


def build(prior_path: Path, manifest_path: Path, report_path: Path,
          outline_path: Path) -> dict:
    prior, manifest, report, outline = map(
        load, (prior_path, manifest_path, report_path, outline_path))
    if (prior["decision"] != "source032_hybrid_candidate_geometry_pass_visual_pending" or
            prior["counts"]["manualPositiveInside"] != 6 or
            prior["counts"]["manualNegativeOutside"] != 6 or
            manifest["decision"] != "source032_four_manual_one_sam_candidate_only" or
            manifest["trainingUse"] != "prohibited" or
            report["decision"] != "candidate_only_not_training_or_test_truth" or
            report["retainedPolygonCount"] != 3 or
            report["manualPolygonCount"] != 2 or
            report["polygonCount"] != 5 or
            report["pairwiseOverlapCount"] != 0 or
            outline["decision"] != "source032_hybrid_outline_visual_review_pending" or
            outline["counts"]["legalPolygons"] != 5 or
            outline["counts"]["overlapPairs"] != 0):
        raise ValueError("source32 hybrid v2 contract mismatch")
    item, output = manifest["images"][0], report["outputs"][0]
    if (item["fileName"] != Path(prior["inputs"]["hybridAnnotation"]["path"]).stem + ".jpg" or
            output["fileName"] != item["fileName"] or
            Path(item["sourceAnnotationPath"]).resolve() !=
            Path(prior["inputs"]["hybridAnnotation"]["path"]).resolve() or
            len(item["nails"]) != 5):
        raise ValueError("source32 hybrid v2 image/source mismatch")
    old = load(Path(item["sourceAnnotationPath"]))
    new = load(Path(output["annotationPath"]))
    if (new["trainingUse"] != "prohibited" or len(new["annotations"]) != 5 or
            len(old["annotations"]) != 5):
        raise ValueError("source32 hybrid v2 annotation mismatch")
    if (new["image"]["fileName"] != item["fileName"] or
            new["image"]["sourceGroup"] != item["sourceGroup"]):
        raise ValueError("source32 hybrid v2 image/group mismatch")
    for index in (0, 1):
        if (new["annotations"][index]["polygon"] != item["nails"][index]["polygon"] or
                new["annotations"][index]["polygon"] == old["annotations"][index]["polygon"]):
            raise ValueError(f"manual nail {index + 1} mismatch/unchanged")
    for index in (2, 3, 4):
        if (item["nails"][index] != {"sourceIndex": index + 1} or
                new["annotations"][index]["polygon"] != old["annotations"][index]["polygon"]):
            raise ValueError(f"retained nail {index + 1} changed")
    shapes = [Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
              for nail in new["annotations"]]
    if (any(not shape.is_valid or shape.area <= 1 for shape in shapes) or
            any(shapes[i].intersection(shapes[j]).area > 0
                for i in range(5) for j in range(i + 1, 5))):
        raise ValueError("source32 hybrid v2 topology failure")
    pos, neg = 0, 0
    for index, points in QA.items():
        shape = shapes[index - 1]
        pos += sum(shape.contains(Point(x, y)) for x, y in points["positive"])
        neg += sum(not shape.covers(Point(x, y)) for x, y in points["negative"])
    if (pos, neg) != (6, 6):
        raise ValueError(f"manual nail 1/2 QA failed: {(pos, neg)}")
    crops = []
    for crop in outline["crops"]:
        crops.extend((crop["source"], crop["outline"]))
    for crop in crops:
        checked(crop)
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_hybrid_v2_geometry_pass_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "priorHybridV1": bind(prior_path),
                       "manifest": bind(manifest_path),
                       "buildReport": bind(report_path),
                       "outlineReport": bind(outline_path),
                       "sourceAnnotation": bind(Path(item["sourceAnnotationPath"])),
                       "candidateAnnotation": bind(Path(output["annotationPath"])),
                       "sourceImage": outline["inputs"]["isolatedImage"],
                       "fullOutline": outline["fullOutline"],
                       "reviewCrops": crops},
            "counts": {"historicalCanonicalRecords": 1,
                       "manualPolygonsTotal": 4,
                       "retainedDirectedSamPolygons": 1,
                       "legalPolygons": 5, "overlapPairs": 0,
                       "manualPositiveInside": pos + prior["counts"]["manualPositiveInside"],
                       "manualNegativeOutside": neg + prior["counts"]["manualNegativeOutside"],
                       "visualApproved": 0,
                       "newTrainingApprovedSources": 0},
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--build-report", type=Path)
    parser.add_argument("--outline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for item in prior["inputs"].values():
            if isinstance(item, list):
                for binding in item:
                    checked(binding)
            else:
                checked(item)
        inputs = prior["inputs"]
        current = build(Path(inputs["priorHybridV1"]["path"]),
                        Path(inputs["manifest"]["path"]),
                        Path(inputs["buildReport"]["path"]),
                        Path(inputs["outlineReport"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.prior, args.manifest, args.build_report,
                args.outline, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.prior.resolve(), args.manifest.resolve(),
                   args.build_report.resolve(), args.outline.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
