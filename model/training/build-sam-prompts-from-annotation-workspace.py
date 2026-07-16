from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert hash-bound workspace YOLO candidates into per-image SAM prompts."
    )
    parser.add_argument("--workspace-manifest", required=True)
    parser.add_argument("--prelabel-report", required=True)
    parser.add_argument("--prelabel-audit", required=True)
    parser.add_argument("--padding", type=float, default=0.04)
    parser.add_argument(
        "--prompt-mode",
        choices=["box", "center", "box-center", "center-negative-corners"],
        default="box-center",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 0 <= args.padding <= 0.25:
        raise ValueError("padding must be between 0 and 0.25")

    workspace_path = Path(args.workspace_manifest).resolve()
    prelabel_path = Path(args.prelabel_report).resolve()
    audit_path = Path(args.prelabel_audit).resolve()
    output_path = Path(args.output).resolve()
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    prelabel = json.loads(prelabel_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if workspace.get("ok") is not True or workspace.get("decision") != "annotation_workspace_ready_candidate_only":
        raise ValueError("annotation workspace must pass")
    if prelabel.get("ok") is not True or prelabel.get("decision") != "candidate_only_not_training_truth":
        raise ValueError("YOLO prelabel report must pass and remain candidate-only")
    if audit.get("ok") is not True or audit.get("decision") != "prelabel_candidate_audit_pass_original_resolution_review_required":
        raise ValueError("prelabel audit must pass")
    if audit.get("inputs", {}).get("workspaceManifestSha256") != sha256_file(workspace_path):
        raise ValueError("prelabel audit does not bind the current workspace")
    if audit.get("inputs", {}).get("prelabelReportSha256") != sha256_file(prelabel_path):
        raise ValueError("prelabel audit does not bind the current prelabel report")

    workspace_items = {str(item["fileName"]): item for item in workspace.get("items", [])}
    prelabel_items = {str(item["fileName"]): item for item in prelabel.get("items", [])}
    if set(workspace_items) != set(prelabel_items):
        raise ValueError("prelabel report must exactly cover the annotation workspace")

    images: list[dict[str, object]] = []
    for file_name in sorted(workspace_items):
        workspace_item = workspace_items[file_name]
        annotation_path = Path(str(prelabel_items[file_name]["annotationPath"])).resolve()
        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        width = float(annotation["image"]["width"])
        height = float(annotation["image"]["height"])
        boxes: list[list[float]] = []
        for candidate in annotation.get("annotations", []):
            points = candidate["polygon"]
            xs = [float(point["x"]) for point in points]
            ys = [float(point["y"]) for point in points]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            pad_x = (x2 - x1) * args.padding
            pad_y = (y2 - y1) * args.padding
            boxes.append(
                [
                    max(0.0, (x1 - pad_x) / width),
                    max(0.0, (y1 - pad_y) / height),
                    min(1.0, (x2 + pad_x) / width),
                    min(1.0, (y2 + pad_y) / height),
                ]
            )
        images.append(
            {
                "fileName": file_name,
                "sha256": workspace_item["sha256"],
                "sourceGroup": workspace_item["sourceGroup"],
                "expectedFullyVisibleNails": workspace_item.get("expectedFullyVisibleNails"),
                "boxes": boxes,
                "promptModes": [args.prompt_mode] * len(boxes),
            }
        )

    document = {
        "schemaVersion": 1,
        "source": "hash-bound-yolo-prelabel-polygon-bounds",
        "decision": "sam_candidate_only_not_training_truth",
        "inputs": {
            "workspaceManifest": str(workspace_path),
            "workspaceManifestSha256": sha256_file(workspace_path),
            "prelabelReport": str(prelabel_path),
            "prelabelReportSha256": sha256_file(prelabel_path),
            "prelabelAudit": str(audit_path),
            "prelabelAuditSha256": sha256_file(audit_path),
        },
        "paddingFraction": args.padding,
        "promptMode": args.prompt_mode,
        "imageCount": len(images),
        "promptCount": sum(len(item["boxes"]) for item in images),
        "policy": {
            "promptsAreMachineCandidates": True,
            "originalResolutionReviewRequired": True,
            "trainingUse": "prohibited",
        },
        "images": images,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": document["decision"], "imageCount": document["imageCount"], "promptCount": document["promptCount"]}))


if __name__ == "__main__":
    main()
