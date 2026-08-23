#!/usr/bin/env python3
"""按置信度与空间去重生成candidate8候选SAM提示；输出不得直接用于训练。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE_DECISIONS = {
    "candidate8_annotation_workspace_ready_candidate_only",
    "candidate9_annotation_workspace_ready_candidate_only",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON不是对象：{path}")
    return value


def candidate_box(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
    points = candidate.get("polygon") or []
    if len(points) < 4:
        raise ValueError("候选polygon少于4点")
    xs = [float(point["x"]) for point in points]
    ys = [float(point["y"]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def box_iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def normalized_box(
    box: tuple[float, float, float, float], width: float, height: float, padding: float
) -> list[float]:
    pad_x = (box[2] - box[0]) * padding
    pad_y = (box[3] - box[1]) * padding
    return [
        max(0.0, (box[0] - pad_x) / width),
        max(0.0, (box[1] - pad_y) / height),
        min(1.0, (box[2] + pad_x) / width),
        min(1.0, (box[3] + pad_y) / height),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-report", required=True)
    parser.add_argument("--padding", type=float, default=0.02)
    parser.add_argument("--dedupe-box-iou", type=float, default=0.35)
    parser.add_argument("--exclude-file", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.padding <= 0.25:
        raise ValueError("padding必须位于0到0.25")
    if not 0 < args.dedupe_box_iou <= 1:
        raise ValueError("dedupe-box-iou必须位于0到1")

    workspace_path = Path(args.workspace_manifest).resolve()
    prelabel_path = Path(args.prelabel_report).resolve()
    output_path = Path(args.output).resolve()
    workspace = read_json(workspace_path)
    prelabel = read_json(prelabel_path)
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") not in WORKSPACE_DECISIONS
        or workspace.get("trainingUse") != "prohibited"
    ):
        raise ValueError("candidate8/9工作区状态不安全")
    if (
        prelabel.get("ok") is not True
        or prelabel.get("decision") != "candidate_only_not_training_truth"
        or prelabel.get("trainingUse") != "prohibited"
        or prelabel.get("originalResolutionReviewRequired") is not True
        or prelabel.get("workspaceManifestSha256") != sha256_file(workspace_path)
    ):
        raise ValueError("candidate8预标注未绑定当前工作区或候选门失效")

    workspace_items = {str(item["fileName"]): item for item in workspace.get("items", [])}
    prelabel_items = {str(item["fileName"]): item for item in prelabel.get("items", [])}
    if len(workspace_items) != len(workspace.get("items", [])) or set(workspace_items) != set(prelabel_items):
        raise ValueError("candidate8预标注未精确覆盖工作区")
    excluded = set(args.exclude_file)
    if not excluded.issubset(workspace_items):
        raise ValueError("exclude-file包含工作区外身份")

    images: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for file_name in sorted(workspace_items):
        if file_name in excluded:
            continue
        workspace_item = workspace_items[file_name]
        prelabel_item = prelabel_items[file_name]
        if (
            prelabel_item.get("sha256")
            != (workspace_item.get("sha256") or workspace_item.get("imageSha256"))
            or prelabel_item.get("sourceGroup") != workspace_item.get("sourceGroup")
        ):
            raise ValueError(f"预标注身份漂移：{file_name}")
        annotation_path = Path(str(prelabel_item.get("annotationPath") or "")).resolve()
        annotation = read_json(annotation_path)
        image = annotation.get("image") or {}
        if (
            image.get("fileName") != file_name
            or image.get("sourceGroup") != workspace_item.get("sourceGroup")
        ):
            raise ValueError(f"预标注annotation身份漂移：{file_name}")
        candidates = list(annotation.get("annotations") or [])
        expected = int(workspace_item["expectedFullyVisibleNails"])
        if len(candidates) < expected:
            unresolved.append(
                {
                    "fileName": file_name,
                    "expectedFullyVisibleNails": expected,
                    "candidateCount": len(candidates),
                    "reason": "candidate_count_below_source_review_expected_manual_prompt_required",
                }
            )
            continue
        ranked = sorted(
            enumerate(candidates, start=1),
            key=lambda pair: float(pair[1].get("attributes", {}).get("confidence", 0.0)),
            reverse=True,
        )
        selected: list[tuple[int, dict[str, Any], tuple[float, float, float, float]]] = []
        deferred: list[tuple[int, dict[str, Any], tuple[float, float, float, float]]] = []
        for index, candidate in ranked:
            box = candidate_box(candidate)
            if any(box_iou(box, current[2]) >= args.dedupe_box_iou for current in selected):
                deferred.append((index, candidate, box))
            else:
                selected.append((index, candidate, box))
            if len(selected) == expected:
                break
        if len(selected) < expected:
            selected.extend(deferred[: expected - len(selected)])
        if len(selected) != expected:
            raise ValueError(f"候选去重后无法达到应标数量：{file_name}")
        width = float(image["width"])
        height = float(image["height"])
        images.append(
            {
                "fileName": file_name,
                "sha256": workspace_item.get("sha256") or workspace_item["imageSha256"],
                "sourceGroup": workspace_item["sourceGroup"],
                "expectedFullyVisibleNails": expected,
                "boxes": [normalized_box(item[2], width, height, args.padding) for item in selected],
                "promptModes": ["center-negative-corners"] * expected,
                "selectedCandidateIndices": [item[0] for item in selected],
                "selectedCandidateConfidences": [
                    float(item[1].get("attributes", {}).get("confidence", 0.0)) for item in selected
                ],
                "selectionPolicy": "confidence_ranked_spatially_deduplicated_candidate_only",
            }
        )

    document = {
        "schemaVersion": 1,
        "source": "candidate-low-threshold-ranked-spatial-deduplication",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "workspaceManifest": str(workspace_path),
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelReport": str(prelabel_path),
            "prelabelReportSha256": sha256_file(prelabel_path),
        },
        "paddingFraction": args.padding,
        "dedupeBoxIou": args.dedupe_box_iou,
        "excludedFiles": sorted(excluded),
        "imageCount": len(images),
        "promptCount": sum(len(item["boxes"]) for item in images),
        "unresolvedImageCount": len(unresolved),
        "unresolved": unresolved,
        "policy": {
            "machineRankingIsCandidateSelectionOnly": True,
            "originalResolutionReviewRequired": True,
            "trainingUse": "prohibited",
        },
        "images": images,
        "trainingUse": "prohibited",
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
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
