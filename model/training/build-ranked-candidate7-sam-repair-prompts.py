from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def polygon_box(candidate: dict[str, Any], width: float, height: float, padding: float) -> list[float]:
    points = candidate.get("polygon", [])
    if not points:
        raise ValueError("candidate polygon is empty")
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    pad_x = (x2 - x1) * padding
    pad_y = (y2 - y1) * padding
    return [
        max(0.0, (x1 - pad_x) / width),
        max(0.0, (y1 - pad_y) / height),
        min(1.0, (x2 + pad_x) / width),
        min(1.0, (y2 + pad_y) / height),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rank low-threshold candidate7 prelabels to the human-reviewed expected count "
            "and build candidate-only SAM repair prompts."
        )
    )
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-report", required=True)
    parser.add_argument("--prelabel-audit", required=True)
    parser.add_argument("--mask-review-reports", nargs="+", required=True)
    parser.add_argument("--manual-completions")
    parser.add_argument("--padding", type=float, default=0.02)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.padding <= 0.25:
        raise ValueError("padding must be between 0 and 0.25")

    workspace_path = Path(args.workspace_manifest).resolve()
    prelabel_path = Path(args.prelabel_report).resolve()
    audit_path = Path(args.prelabel_audit).resolve()
    output_path = Path(args.output).resolve()
    review_paths = [Path(path).resolve() for path in args.mask_review_reports]
    manual_path = Path(args.manual_completions).resolve() if args.manual_completions else None
    workspace = read_json(workspace_path)
    prelabel = read_json(prelabel_path)
    audit = read_json(audit_path)
    if workspace.get("ok") is not True or workspace.get("decision") != "candidate7_annotation_workspace_ready_candidate_only":
        raise ValueError("candidate7 annotation workspace must pass")
    if prelabel.get("ok") is not True or prelabel.get("decision") != "candidate_only_not_training_truth":
        raise ValueError("prelabels must pass and remain candidate-only")
    if audit.get("ok") is not True or audit.get("decision") != "prelabel_candidate_audit_pass_original_resolution_review_required":
        raise ValueError("prelabel audit must pass")
    if audit.get("inputs", {}).get("workspaceManifestSha256") != sha256_file(workspace_path):
        raise ValueError("prelabel audit does not bind the current workspace")
    if audit.get("inputs", {}).get("prelabelReportSha256") != sha256_file(prelabel_path):
        raise ValueError("prelabel audit does not bind the current prelabels")

    rework_files: set[str] = set()
    reviewed_files: set[str] = set()
    for review_path in review_paths:
        review = read_json(review_path)
        if review.get("ok") is not True or review.get("decision") != "mask_review_shard_complete_final_truth_audit_still_required":
            raise ValueError(f"mask review report did not pass: {review_path}")
        for item in review.get("items", []):
            file_name = str(item["fileName"])
            if file_name in reviewed_files:
                raise ValueError(f"duplicate mask review identity: {file_name}")
            reviewed_files.add(file_name)
            if item.get("reviewStatus") == "rework":
                rework_files.add(file_name)

    workspace_items = {str(item["fileName"]): item for item in workspace.get("items", [])}
    prelabel_items = {str(item["fileName"]): item for item in prelabel.get("items", [])}
    if reviewed_files != set(workspace_items):
        raise ValueError("mask review reports must exactly cover the workspace")
    if set(prelabel_items) != set(workspace_items):
        raise ValueError("prelabels must exactly cover the workspace")

    images: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for file_name in sorted(rework_files):
        workspace_item = workspace_items[file_name]
        expected = int(workspace_item["expectedFullyVisibleNails"])
        annotation_path = Path(str(prelabel_items[file_name]["annotationPath"])).resolve()
        annotation = read_json(annotation_path)
        if annotation.get("image", {}).get("fileName") != file_name:
            raise ValueError(f"prelabel annotation identity differs: {file_name}")
        candidates = list(annotation.get("annotations", []))
        candidates.sort(
            key=lambda candidate: float(candidate.get("attributes", {}).get("confidence", 0.0)),
            reverse=True,
        )
        if len(candidates) < expected:
            unresolved.append(
                {
                    "fileName": file_name,
                    "expectedFullyVisibleNails": expected,
                    "candidateCount": len(candidates),
                    "reason": "low_threshold_candidates_still_below_expected_manual_boxes_required",
                }
            )
            continue
        selected = candidates[:expected]
        width = float(annotation["image"]["width"])
        height = float(annotation["image"]["height"])
        images.append(
            {
                "fileName": file_name,
                "sha256": workspace_item.get("sha256") or workspace_item["imageSha256"],
                "sourceGroup": workspace_item["sourceGroup"],
                "expectedFullyVisibleNails": expected,
                "boxes": [polygon_box(candidate, width, height, args.padding) for candidate in selected],
                "promptModes": ["center-negative-corners"] * expected,
                "rankedCandidateConfidences": [
                    float(candidate.get("attributes", {}).get("confidence", 0.0))
                    for candidate in selected
                ],
                "selectionPolicy": "top_expected_by_candidate6_confidence_candidate_only",
            }
        )

    if manual_path is not None:
        manual = read_json(manual_path)
        if manual.get("schemaVersion") != 1 or manual.get("decision") != "candidate7_manual_candidate_completion":
            raise ValueError("manual completion manifest has an unsupported contract")
        manual_inputs = manual.get("inputs", {})
        expected_bindings = {
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelReportSha256": sha256_file(prelabel_path),
            "prelabelAuditSha256": sha256_file(audit_path),
        }
        for key, value in expected_bindings.items():
            if manual_inputs.get(key) != value:
                raise ValueError(f"manual completion manifest does not bind {key}")
        manual_items = manual.get("items", [])
        if not isinstance(manual_items, list):
            raise ValueError("manual completion items must be a list")
        manual_by_file: dict[str, dict[str, Any]] = {}
        for item in manual_items:
            file_name = str(item.get("fileName", ""))
            if not file_name or file_name in manual_by_file:
                raise ValueError(f"duplicate or empty manual completion identity: {file_name}")
            manual_by_file[file_name] = item
        unresolved_files = {str(item["fileName"]) for item in unresolved}
        if set(manual_by_file) != unresolved_files:
            raise ValueError("manual completions must exactly cover unresolved images")

        manually_completed: list[dict[str, Any]] = []
        for unresolved_item in unresolved:
            file_name = str(unresolved_item["fileName"])
            item = manual_by_file[file_name]
            workspace_item = workspace_items[file_name]
            expected = int(workspace_item["expectedFullyVisibleNails"])
            annotation_path = Path(str(prelabel_items[file_name]["annotationPath"])).resolve()
            annotation = read_json(annotation_path)
            if annotation.get("image", {}).get("fileName") != file_name:
                raise ValueError(f"manual completion annotation identity differs: {file_name}")
            candidates = list(annotation.get("annotations", []))
            keep_indices = item.get("keepCandidateIndices", [])
            add_boxes = item.get("addBoxes", [])
            if (
                not isinstance(keep_indices, list)
                or any(not isinstance(index, int) for index in keep_indices)
                or len(set(keep_indices)) != len(keep_indices)
                or any(index < 1 or index > len(candidates) for index in keep_indices)
            ):
                raise ValueError(f"invalid 1-based keepCandidateIndices: {file_name}")
            if not isinstance(add_boxes, list):
                raise ValueError(f"addBoxes must be a list: {file_name}")
            for box in add_boxes:
                if (
                    not isinstance(box, list)
                    or len(box) != 4
                    or any(not isinstance(value, (int, float)) for value in box)
                    or not (0 <= float(box[0]) < float(box[2]) <= 1)
                    or not (0 <= float(box[1]) < float(box[3]) <= 1)
                ):
                    raise ValueError(f"invalid normalized manual box: {file_name}")
            if len(keep_indices) + len(add_boxes) != expected:
                raise ValueError(f"manual completion count differs from expected: {file_name}")
            width = float(annotation["image"]["width"])
            height = float(annotation["image"]["height"])
            kept = [candidates[index - 1] for index in keep_indices]
            boxes = [polygon_box(candidate, width, height, args.padding) for candidate in kept]
            boxes.extend([[float(value) for value in box] for box in add_boxes])
            manually_completed.append(
                {
                    "fileName": file_name,
                    "sha256": workspace_item.get("sha256") or workspace_item["imageSha256"],
                    "sourceGroup": workspace_item["sourceGroup"],
                    "expectedFullyVisibleNails": expected,
                    "boxes": boxes,
                    "promptModes": ["center-negative-corners"] * expected,
                    "keptCandidateIndices": keep_indices,
                    "manualAddedBoxCount": len(add_boxes),
                    "selectionPolicy": "original_resolution_manual_completion_candidate_only",
                    "note": str(item.get("note", "")),
                }
            )
        images.extend(manually_completed)
        unresolved = []

    document = {
        "schemaVersion": 1,
        "source": "candidate7-low-threshold-ranked-repair",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "workspaceManifest": str(workspace_path),
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelReport": str(prelabel_path),
            "prelabelReportSha256": sha256_file(prelabel_path),
            "prelabelAudit": str(audit_path),
            "prelabelAuditSha256": sha256_file(audit_path),
            "maskReviewReports": [
                {"path": str(path), "sha256": sha256_file(path)} for path in review_paths
            ],
            "manualCompletions": (
                {"path": str(manual_path), "sha256": sha256_file(manual_path)}
                if manual_path is not None
                else None
            ),
        },
        "paddingFraction": args.padding,
        "promptMode": "center-negative-corners",
        "imageCount": len(images),
        "promptCount": sum(len(item["boxes"]) for item in images),
        "unresolvedImageCount": len(unresolved),
        "unresolved": unresolved,
        "policy": {
            "confidenceRankingIsCandidateSelectionOnly": True,
            "originalResolutionReviewRequired": True,
            "trainingUse": "prohibited",
        },
        "images": images,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": document["decision"],
                "imageCount": document["imageCount"],
                "promptCount": document["promptCount"],
                "unresolvedImageCount": document["unresolvedImageCount"],
            }
        )
    )


if __name__ == "__main__":
    main()
