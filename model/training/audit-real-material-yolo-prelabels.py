from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def polygon_area(points: list[dict[str, float]]) -> float:
    contour = np.asarray([[point["x"], point["y"]] for point in points], dtype=np.float32)
    return float(abs(cv2.contourArea(contour)))


def polygon_iou(first: list[dict[str, float]], second: list[dict[str, float]]) -> float:
    first_points = np.asarray([[round(point["x"]), round(point["y"])] for point in first], dtype=np.int32)
    second_points = np.asarray([[round(point["x"]), round(point["y"])] for point in second], dtype=np.int32)
    all_points = np.concatenate([first_points, second_points])
    x1, y1 = np.maximum(all_points.min(axis=0) - 1, 0)
    x2, y2 = all_points.max(axis=0) + 2
    shape = (int(y2 - y1), int(x2 - x1))
    if shape[0] <= 0 or shape[1] <= 0:
        return 0.0
    offset = np.asarray([x1, y1], dtype=np.int32)
    first_mask = np.zeros(shape, dtype=np.uint8)
    second_mask = np.zeros(shape, dtype=np.uint8)
    cv2.fillPoly(first_mask, [first_points - offset], 1)
    cv2.fillPoly(second_mask, [second_points - offset], 1)
    intersection = int(np.logical_and(first_mask, second_mask).sum())
    union = int(np.logical_or(first_mask, second_mask).sum())
    return intersection / union if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit hash-bound YOLO prelabels and build an original-resolution review queue."
    )
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-report", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duplicate-iou", type=float, default=0.5)
    args = parser.parse_args()

    workspace_path = Path(args.workspace_manifest).resolve()
    prelabel_path = Path(args.prelabel_report).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    prelabel = json.loads(prelabel_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if workspace.get("ok") is not True or workspace.get("decision") != "annotation_workspace_ready_candidate_only":
        errors.append("annotation workspace must pass")
    if prelabel.get("ok") is not True or prelabel.get("decision") != "candidate_only_not_training_truth":
        errors.append("YOLO prelabel report must be candidate-only and pass")
    if prelabel.get("workspaceManifestSha256") != sha256_file(workspace_path):
        errors.append("YOLO prelabel report does not bind the current workspace")

    workspace_items = {str(item.get("fileName", "")): item for item in workspace.get("items", [])}
    prelabel_items = {str(item.get("fileName", "")): item for item in prelabel.get("items", [])}
    if len(workspace_items) != len(workspace.get("items", [])):
        errors.append("workspace contains duplicate fileName values")
    if set(workspace_items) != set(prelabel_items):
        errors.append("YOLO prelabel report does not exactly cover the workspace")

    rows: list[dict[str, object]] = []
    total_expected = 0
    total_candidates = 0
    capped_candidates = 0
    duplicate_pairs = 0
    geometry_errors = 0
    for file_name in sorted(workspace_items):
        workspace_item = workspace_items[file_name]
        prelabel_item = prelabel_items.get(file_name, {})
        expected = int(workspace_item.get("expectedFullyVisibleNails") or 0)
        candidate_count = int(prelabel_item.get("candidateCount") or 0)
        total_expected += expected
        total_candidates += candidate_count
        capped_candidates += min(expected, candidate_count)
        item_errors: list[str] = []
        item_warnings: list[str] = []
        if prelabel_item.get("sha256") != workspace_item.get("sha256"):
            item_errors.append("image-sha-mismatch")
        if prelabel_item.get("sourceGroup") != workspace_item.get("sourceGroup"):
            item_errors.append("source-group-mismatch")
        annotation_path = Path(str(prelabel_item.get("annotationPath", ""))).resolve()
        if not annotation_path.is_file():
            item_errors.append("annotation-missing")
            annotations: list[dict[str, object]] = []
        else:
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            image = annotation.get("image", {})
            annotations = annotation.get("annotations", [])
            if annotation.get("decision") != "candidate_only_not_training_truth":
                item_errors.append("unsafe-annotation-decision")
            if image.get("fileName") != file_name or image.get("sourceGroup") != workspace_item.get("sourceGroup"):
                item_errors.append("annotation-identity-mismatch")
            width, height = int(image.get("width", 0)), int(image.get("height", 0))
            if len(annotations) != candidate_count:
                item_errors.append("candidate-count-mismatch")
            for index, candidate in enumerate(annotations, start=1):
                points = candidate.get("polygon", [])
                if len(points) < 4:
                    item_errors.append(f"polygon-{index}-too-short")
                    continue
                if any(
                    float(point.get("x", -1)) < 0
                    or float(point.get("x", -1)) > width
                    or float(point.get("y", -1)) < 0
                    or float(point.get("y", -1)) > height
                    for point in points
                ):
                    item_errors.append(f"polygon-{index}-out-of-bounds")
                if polygon_area(points) < 16:
                    item_errors.append(f"polygon-{index}-too-small")
            for first_index, first in enumerate(annotations):
                for second in annotations[first_index + 1 :]:
                    if polygon_iou(first["polygon"], second["polygon"]) >= args.duplicate_iou:
                        duplicate_pairs += 1
                        item_warnings.append("suspect-duplicate-overlap")
        geometry_errors += len(item_errors)
        if candidate_count == 0:
            priority = "critical-zero"
        elif candidate_count < expected:
            priority = "high-under"
        elif candidate_count > expected:
            priority = "medium-over"
        else:
            priority = "normal-count-match"
        rows.append(
            {
                "fileName": file_name,
                "sha256": workspace_item.get("sha256"),
                "sourceGroup": workspace_item.get("sourceGroup"),
                "expectedFullyVisibleNails": expected,
                "candidateCount": candidate_count,
                "countDelta": candidate_count - expected,
                "reviewPriority": priority,
                "machineGeometryStatus": "pass" if not item_errors else "error",
                "machineIssueCodes": ";".join(sorted(set(item_errors + item_warnings))),
                "reviewStatus": "",
                "note": "",
            }
        )
    if geometry_errors:
        errors.append(f"YOLO prelabels contain {geometry_errors} machine geometry or identity errors")

    priority_order = {"critical-zero": 0, "high-under": 1, "medium-over": 2, "normal-count-match": 3}
    rows.sort(key=lambda row: (priority_order[str(row["reviewPriority"])], int(row["countDelta"]), str(row["fileName"])))
    output_dir.mkdir(parents=True)
    review_csv = output_dir / "prelabel-original-resolution-review.csv"
    with review_csv.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "schemaVersion": 1,
        "ok": not errors,
        "decision": "prelabel_candidate_audit_pass_original_resolution_review_required" if not errors else "rejected_prelabel_candidate_audit",
        "inputs": {
            "workspaceManifest": str(workspace_path),
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelReport": str(prelabel_path),
            "prelabelReportSha256": sha256_file(prelabel_path),
            "reviewCsv": str(review_csv),
            "reviewCsvSha256": sha256_file(review_csv),
        },
        "policy": {
            "countCoverageIsDiagnosticOnly": True,
            "originalResolutionReviewRequired": True,
            "candidateAnnotationsAreNotTrainingTruth": True,
        },
        "counts": {
            "images": len(rows),
            "expectedFullyVisibleNails": total_expected,
            "candidates": total_candidates,
            "cappedCountCoverage": round(capped_candidates / total_expected, 6) if total_expected else 0,
            "zeroCandidateImages": sum(row["candidateCount"] == 0 for row in rows),
            "underCandidateImages": sum(row["candidateCount"] < row["expectedFullyVisibleNails"] for row in rows),
            "exactCandidateImages": sum(row["candidateCount"] == row["expectedFullyVisibleNails"] for row in rows),
            "overCandidateImages": sum(row["candidateCount"] > row["expectedFullyVisibleNails"] for row in rows),
            "duplicateOverlapPairs": duplicate_pairs,
            "machineErrors": geometry_errors,
        },
        "errors": errors,
    }
    report_path = output_dir / "prelabel-audit-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], **report["counts"]}, ensure_ascii=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
