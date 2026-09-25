#!/usr/bin/env python3
"""Bind source32's three retained SAM polygons and two manual residuals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, Polygon


QA = {
    3: {"positive": [[615, 905], [577, 960], [540, 1024]],
        "negative": [[650, 874], [660, 945], [500, 1029]]},
    4: {"positive": [[647, 995], [700, 998], [748, 987]],
        "negative": [[620, 955], [785, 980], [720, 1045]]},
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


def build(canonical_path: Path, retry_path: Path, manifest_path: Path,
          build_path: Path, outline_path: Path) -> dict:
    canonical, retry, manifest, report, outline = map(
        load, (canonical_path, retry_path, manifest_path, build_path, outline_path))
    if (canonical["decision"] != "historical_approved_truth_is_same_defective_cycle012_polygon" or
            canonical["sourceOrdinal"] != 32 or
            retry["decision"] != "source032_directed_retry_geometry_pass_original_resolution_visual_pending" or
            retry["counts"]["legalPolygons"] != 5 or
            retry["counts"]["overlapPairs"] != 0 or
            retry["counts"]["visualApproved"] != 0 or
            manifest["decision"] != "source032_directed_sam_plus_two_manual_polygon_candidate_only" or
            manifest["trainingUse"] != "prohibited" or
            report["decision"] != "candidate_only_not_training_or_test_truth" or
            report["retainedPolygonCount"] != 3 or
            report["manualPolygonCount"] != 2 or
            report["polygonCount"] != 5 or
            report["pairwiseOverlapCount"] != 0 or
            outline["decision"] != "source032_hybrid_outline_visual_review_pending" or
            outline["counts"]["legalPolygons"] != 5 or
            outline["counts"]["overlapPairs"] != 0):
        raise ValueError("source32 hybrid candidate contract mismatch")
    item, output = manifest["images"][0], report["outputs"][0]
    if (item["fileName"] != canonical["sourceFileName"] or
            item["sourceGroup"] != canonical["sourceGroup"] or
            output["fileName"] != item["fileName"] or
            output["sourceGroup"] != item["sourceGroup"] or
            Path(item["sourceAnnotationPath"]).resolve() !=
            Path(retry["inputs"]["annotation"]["path"]).resolve() or
            len(item["nails"]) != 5):
        raise ValueError("source32 hybrid file/group/source mismatch")
    old = load(Path(item["sourceAnnotationPath"]))
    new = load(Path(output["annotationPath"]))
    if (new["trainingUse"] != "prohibited" or len(new["annotations"]) != 5 or
            len(old["annotations"]) != 5 or
            new["image"]["fileName"] != canonical["sourceFileName"] or
            new["image"]["sourceGroup"] != canonical["sourceGroup"]):
        raise ValueError("source32 hybrid annotation identity mismatch")
    for index in (0, 1, 4):
        if (item["nails"][index] != {"sourceIndex": index + 1} or
                new["annotations"][index]["polygon"] != old["annotations"][index]["polygon"]):
            raise ValueError(f"retained SAM nail {index + 1} changed")
    for index in (2, 3):
        if (new["annotations"][index]["polygon"] != item["nails"][index]["polygon"] or
                new["annotations"][index]["polygon"] == old["annotations"][index]["polygon"]):
            raise ValueError(f"manual nail {index + 1} mismatch or unchanged")
    shapes = [Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
              for nail in new["annotations"]]
    if (any(not shape.is_valid or shape.area <= 1 for shape in shapes) or
            any(shapes[i].intersection(shapes[j]).area > 0
                for i in range(5) for j in range(i + 1, 5))):
        raise ValueError("source32 hybrid topology failure")
    pos, neg = 0, 0
    for index, points in QA.items():
        shape = shapes[index - 1]
        pos += sum(shape.contains(Point(x, y)) for x, y in points["positive"])
        neg += sum(not shape.covers(Point(x, y)) for x, y in points["negative"])
    if (pos, neg) != (6, 6):
        raise ValueError(f"source32 manual QA failed: {(pos, neg)}")
    crops = []
    for item_crop in outline["crops"]:
        crops.extend((item_crop["source"], item_crop["outline"]))
    for item_crop in crops:
        checked(item_crop)
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_hybrid_candidate_geometry_pass_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "canonicalIdentity": bind(canonical_path),
                       "retryCandidateAudit": bind(retry_path),
                       "manifest": bind(manifest_path),
                       "buildReport": bind(build_path),
                       "outlineReport": bind(outline_path),
                       "isolatedImage": outline["inputs"]["isolatedImage"],
                       "oldLabel": canonical["inputs"]["cycle012Label"],
                       "sourceAnnotation": bind(Path(item["sourceAnnotationPath"])),
                       "hybridAnnotation": bind(Path(output["annotationPath"])),
                       "fullOutline": outline["fullOutline"],
                       "reviewCrops": crops},
            "counts": {"historicalCanonicalRecords": 1,
                       "retainedDirectedSamPolygons": 3,
                       "manualPolygons": 2, "legalPolygons": 5,
                       "overlapPairs": 0, "manualPositiveInside": pos,
                       "manualNegativeOutside": neg,
                       "visualApproved": 0, "newTrainingApprovedSources": 0},
            "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path)
    parser.add_argument("--retry", type=Path)
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
        current = build(Path(inputs["canonicalIdentity"]["path"]),
                        Path(inputs["retryCandidateAudit"]["path"]),
                        Path(inputs["manifest"]["path"]),
                        Path(inputs["buildReport"]["path"]),
                        Path(inputs["outlineReport"]["path"]))
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "counts": current["counts"]}))
        return
    if not all((args.canonical, args.retry, args.manifest,
                args.build_report, args.outline, args.output)):
        parser.error("all inputs and --output required")
    if args.output.exists():
        raise FileExistsError(args.output)
    report = build(args.canonical.resolve(), args.retry.resolve(),
                   args.manifest.resolve(), args.build_report.resolve(),
                   args.outline.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "counts": report["counts"]}))


if __name__ == "__main__":
    main()
