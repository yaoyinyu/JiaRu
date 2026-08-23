#!/usr/bin/env python3
"""终结candidate9强教师首轮视觉审核；未列入PASS的图片全部保持返修。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象：{path}")
    return value


def bound_path(record: dict[str, Any], path_key: str, hash_key: str, label: str) -> Path:
    path = Path(str(record.get(path_key) or "")).resolve()
    if not path.is_file() or sha256_file(path) != record.get(hash_key):
        raise ValueError(f"{label}缺失或哈希漂移：{path}")
    return path


def validate_polygons(annotation: dict[str, Any], expected: int, file_name: str) -> None:
    shapes = list(annotation.get("annotations") or [])
    if len(shapes) != expected:
        raise ValueError(f"{file_name}候选数不等于完整可见甲面数")
    polygons: list[Polygon] = []
    for index, shape in enumerate(shapes, start=1):
        points = shape.get("polygon") or []
        polygon = Polygon([(float(point["x"]), float(point["y"])) for point in points])
        if len(points) < 3 or not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"{file_name}第{index}个polygon无效")
        polygons.append(polygon)
    for first in range(len(polygons)):
        for second in range(first + 1, len(polygons)):
            if polygons[first].intersection(polygons[second]).area > 0:
                raise ValueError(f"{file_name}第{first + 1}/{second + 1}个polygon交叠")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-manifest", required=True, type=Path)
    parser.add_argument("--prompts", required=True, type=Path)
    parser.add_argument("--sam-report", required=True, type=Path)
    parser.add_argument("--geometry-audit", required=True, type=Path)
    parser.add_argument("--visual-evidence", required=True, type=Path)
    parser.add_argument("--pass-list", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    paths = {name: Path(value).resolve() for name, value in {
        "workspace": args.workspace_manifest,
        "prompts": args.prompts,
        "sam": args.sam_report,
        "geometry": args.geometry_audit,
        "visual": args.visual_evidence,
        "passList": args.pass_list,
    }.items()}
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError(f"输出目录已存在：{output_dir}")
    workspace = read_json(paths["workspace"], "candidate9工作区")
    prompts = read_json(paths["prompts"], "SAM提示")
    sam = read_json(paths["sam"], "SAM报告")
    geometry = read_json(paths["geometry"], "几何审计")
    visual = read_json(paths["visual"], "视觉证据")
    pass_list = read_json(paths["passList"], "教师PASS清单")
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") != "candidate9_annotation_workspace_ready_candidate_only"
        or workspace.get("trainingUse") != "prohibited"
        or prompts.get("decision") != "sam_candidate_only_not_training_truth"
        or prompts.get("trainingUse") != "prohibited"
        or sam.get("ok") is not True
        or sam.get("completedCount") != 75
        or sam.get("promptCount") != 552
        or sam.get("errors") != []
        or visual.get("ok") is not True
        or visual.get("decision") != "sam_visual_review_evidence_ready_not_truth"
        or visual.get("summary", {}).get("images") != 75
        or visual.get("summary", {}).get("polygons") != 552
        or pass_list.get("decision") != "candidate9_teacher_review_pass_list_original_resolution"
        or pass_list.get("policy", {}).get("sourceOverlayAnd2xCropsReviewed") is not True
    ):
        raise ValueError("candidate9教师审核输入状态不安全")
    if prompts.get("inputs", {}).get("workspaceManifestSha256") != sha256_file(paths["workspace"]):
        raise ValueError("SAM提示未绑定当前工作区")
    visual_inputs = visual.get("inputs") or {}
    for key, path_key in (("prompts", "prompts"), ("samReport", "sam"), ("geometryAudit", "geometry")):
        if Path(str(visual_inputs.get(key) or "")).resolve() != paths[path_key] or visual_inputs.get(f"{key}Sha256") != sha256_file(paths[path_key]):
            raise ValueError(f"视觉证据未绑定当前{key}")

    workspace_items = {str(item["fileName"]): item for item in workspace.get("items", [])}
    visual_items = {str(item["fileName"]): item for item in visual.get("items", [])}
    prompt_items = {str(item["fileName"]): item for item in prompts.get("images", [])}
    geometry_rows: dict[str, list[dict[str, Any]]] = {}
    for row in geometry.get("rows", []):
        geometry_rows.setdefault(str(row.get("fileName") or ""), []).append(row)
    if not (len(workspace_items) == len(visual_items) == len(prompt_items) == 75):
        raise ValueError("工作区/提示/视觉证据覆盖不一致")
    passed = list(pass_list.get("passFiles") or [])
    if len(passed) != len(set(passed)) or not set(passed).issubset(workspace_items):
        raise ValueError("教师PASS清单重复或越界")
    repair_evidence = pass_list.get("repairEvidence") or {}
    if not isinstance(repair_evidence, dict) or not set(repair_evidence).issubset(set(passed)):
        raise ValueError("返修证据必须是PASS项的文件名映射")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        reports_dir = staging / "truth-reports"
        reports_dir.mkdir()
        canonical_truths: list[dict[str, Any]] = []
        reviewed: list[dict[str, Any]] = []
        final_output = output_dir / "truth-reports"
        for file_name in sorted(workspace_items):
            source = workspace_items[file_name]
            evidence = visual_items[file_name]
            decision = "pass" if file_name in set(passed) else "rework"
            reviewed.append({
                "fileName": file_name,
                "imageSha256": source["imageSha256"],
                "sourceGroup": source["sourceGroup"],
                "expectedFullyVisibleNails": source["expectedFullyVisibleNails"],
                "candidateMaskCount": evidence["polygonCount"],
                "geometrySuspectCount": evidence["geometrySuspectCount"],
                "decision": decision,
                "trainingUse": "prohibited-until-materialization-audit",
            })
            if decision != "pass":
                continue
            expected = int(source["expectedFullyVisibleNails"])
            image_path = bound_path(evidence, "imagePath", "imageSha256", f"{file_name}源图")
            visual_review_path = paths["visual"]
            visual_review_sha256 = sha256_file(paths["visual"])
            visual_review_type = "candidate9-strong-teacher-original-resolution"
            repair_geometry_path: Path | None = None
            repair_geometry_sha256: str | None = None
            repair_visual_files: list[dict[str, str]] = []
            if file_name in repair_evidence:
                repair = repair_evidence[file_name]
                if not isinstance(repair, dict):
                    raise ValueError(f"{file_name}返修证据不是对象")
                repair_report_path = Path(str(repair.get("reportPath") or "")).resolve()
                repair_geometry_path = Path(str(repair.get("geometryAuditPath") or "")).resolve()
                if (
                    not repair_report_path.is_file()
                    or sha256_file(repair_report_path) != repair.get("reportSha256")
                    or not repair_geometry_path.is_file()
                    or sha256_file(repair_geometry_path) != repair.get("geometryAuditSha256")
                ):
                    raise ValueError(f"{file_name}返修报告或几何审计缺失/漂移")
                repair_report = read_json(repair_report_path, f"{file_name}返修报告")
                repair_geometry = read_json(repair_geometry_path, f"{file_name}返修几何审计")
                outputs = [item for item in repair_report.get("outputs", []) if item.get("fileName") == file_name]
                summary = repair_geometry.get("summary") or {}
                geometry_pass = sum(int(item.get("pass", 0)) for item in summary.values() if isinstance(item, dict))
                geometry_suspect = sum(int(item.get("suspect", 0)) for item in summary.values() if isinstance(item, dict))
                geometry_missing = sum(int(item.get("missing", 0)) for item in summary.values() if isinstance(item, dict))
                if (
                    repair_report.get("ok") is not True
                    or repair_report.get("decision") != "candidate_only_not_training_or_test_truth"
                    or repair_report.get("completedCount") != 1
                    or repair_report.get("errors") != []
                    or len(outputs) != 1
                    or outputs[0].get("polygonCount") != expected
                    or outputs[0].get("validPolygonCount") != expected
                    or outputs[0].get("pairwiseOverlapCount") != 0
                    or int(outputs[0].get("manualPolygonCount", 0)) < 1
                    or geometry_pass != expected
                    or geometry_suspect != 0
                    or geometry_missing != 0
                ):
                    raise ValueError(f"{file_name}返修机器门未通过")
                annotation_path = Path(str(outputs[0].get("annotationPath") or "")).resolve()
                overlay_path = Path(str(outputs[0].get("overlayPath") or "")).resolve()
                if not annotation_path.is_file() or not overlay_path.is_file():
                    raise ValueError(f"{file_name}返修标注或整图叠加缺失")
                zoom_paths = list(outputs[0].get("zoomPaths") or [])
                if len(zoom_paths) != expected:
                    raise ValueError(f"{file_name}返修逐甲证据数量错误")
                repair_visual_files.append({"path": str(overlay_path), "sha256": sha256_file(overlay_path)})
                for crop in zoom_paths:
                    for key in ("source", "overlay"):
                        crop_path = Path(str(crop.get(key) or "")).resolve()
                        if not crop_path.is_file():
                            raise ValueError(f"{file_name}返修逐甲{key}证据缺失")
                        repair_visual_files.append({"path": str(crop_path), "sha256": sha256_file(crop_path)})
                visual_review_path = repair_report_path
                visual_review_sha256 = sha256_file(repair_report_path)
                visual_review_type = "candidate9-strong-teacher-repair-original-resolution"
                repair_geometry_sha256 = sha256_file(repair_geometry_path)
            else:
                if evidence.get("polygonCount") != expected or evidence.get("geometrySuspectCount") != 0:
                    raise ValueError(f"PASS项数量或几何状态不安全：{file_name}")
                if len(evidence.get("crops") or []) != expected or any(crop.get("geometryStatus") != "pass" for crop in evidence["crops"]):
                    raise ValueError(f"PASS项逐甲视觉证据不完整：{file_name}")
                annotation_path = bound_path(evidence, "annotationPath", "annotationSha256", f"{file_name}标注")
                bound_path(evidence, "overlayPath", "overlaySha256", f"{file_name}叠加图")
                for crop in evidence["crops"]:
                    bound_path(crop, "sourceCrop", "sourceCropSha256", f"{file_name}源图裁片")
                    bound_path(crop, "overlayCrop", "overlayCropSha256", f"{file_name}叠加裁片")
            annotation = read_json(annotation_path, f"{file_name}标注")
            if annotation.get("decision") not in {"candidate_only_not_training_truth", "candidate_only_not_training_or_test_truth"} or annotation.get("trainingUse") != "prohibited":
                raise ValueError(f"{file_name}候选标注门漂移")
            validate_polygons(annotation, expected, file_name)
            report_path = final_output / f"training-truth-{len(canonical_truths) + 1:03d}.json"
            report = {
                "schemaVersion": 1,
                "ok": True,
                "decision": "approved_as_training_truth_candidate_pending_dataset_materialization",
                "reviewedBy": pass_list["reviewedBy"],
                "inputs": {
                    "truthRole": "train",
                    "visualReviewType": visual_review_type,
                    "visualReviewFinal": str(visual_review_path),
                    "visualReviewFinalSha256": visual_review_sha256,
                    "repairGeometryAudit": str(repair_geometry_path) if repair_geometry_path else None,
                    "repairGeometryAuditSha256": repair_geometry_sha256,
                    "repairVisualFiles": repair_visual_files,
                    "image": str(image_path),
                    "imageSha256": source["imageSha256"],
                    "annotation": str(annotation_path),
                    "annotationSha256": sha256_file(annotation_path),
                    "roleManifest": None,
                    "roleManifestSha256": None,
                },
                "policy": {
                    "targetRole": "train",
                    "originalResolutionVisualReviewRequired": True,
                    "polygonTopologyMustBeValid": True,
                    "pairwisePolygonIntersectionArea": 0,
                    "datasetMaterializationAndSourceIsolationStillRequired": True,
                    "snapshotFreezeAndSourceIsolationStillRequired": False,
                    "trainingUse": "prohibited-until-materialization-audit",
                    "validationUse": None,
                    "evaluationUse": None,
                },
                "item": {
                    "fileName": file_name,
                    "sha256": source["imageSha256"],
                    "sourceGroup": source["sourceGroup"],
                    "completeMaskCount": expected,
                    "invalidPolygonCount": 0,
                    "overlapPairCount": 0,
                    "annotationTruthStatus": "approved-as-training-truth-candidate",
                    "trainingUse": "prohibited-until-materialization-audit",
                    "validationUse": None,
                    "evaluationUse": None,
                },
                "errors": [],
            }
            staged_report = reports_dir / report_path.name
            staged_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            canonical_truths.append({
                "reportPath": str(report_path),
                "reportName": report_path.name,
                "reportSha256": sha256_file(staged_report),
                "sequence": len(canonical_truths) + 1,
                "fileName": file_name,
                "imageSha256": source["imageSha256"],
                "sourceGroup": source["sourceGroup"],
                "completeMaskCount": expected,
                "annotationPath": str(annotation_path),
                "annotationSha256": sha256_file(annotation_path),
            })
        total_masks = sum(int(item["completeMaskCount"]) for item in canonical_truths)
        index = {
            "schemaVersion": 1,
            "ok": True,
            "decision": "approved_unique_training_truth_index",
            "inputs": {key: {"path": str(path), "sha256": sha256_file(path)} for key, path in paths.items()},
            "policy": {
                "semanticTeacherDoesNotAutoApprove": True,
                "sourceOverlayAnd2xCropsReviewed": True,
                "polygonValidityAndZeroOverlapRequired": True,
                "trainingUse": "prohibited-until-materialization-audit",
            },
            "summary": {
                "approvedReportCount": len(canonical_truths), "rejectedReportCount": 0,
                "uniqueImageCount": len(canonical_truths), "completeMaskCount": total_masks,
                "redundantReportCount": 0, "redundantImageCount": 0, "conflictingImageCount": 0,
                "sourceGroupCount": len({item["sourceGroup"] for item in canonical_truths}),
                "reviewedImages": len(reviewed), "reworkImages": len(reviewed) - len(canonical_truths),
            },
            "canonicalTruthsSha256": canonical_sha256(canonical_truths),
            "canonicalTruths": canonical_truths,
            "rejectedReports": [], "redundantReports": [], "conflicts": [], "errors": [],
        }
        (staging / "teacher-review.json").write_text(json.dumps({
            "schemaVersion": 1, "ok": True, "decision": "candidate9_teacher_review_complete",
            "counts": {"reviewed": len(reviewed), "pass": len(canonical_truths), "rework": len(reviewed) - len(canonical_truths), "masks": total_masks},
            "itemsSha256": canonical_sha256(reviewed), "items": reviewed,
            "trainingUse": "prohibited-until-materialization-audit", "errors": [],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "candidate9-training-truth-index-v1.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"ok": True, "images": len(canonical_truths), "masks": total_masks, "rework": len(reviewed) - len(canonical_truths), "canonicalTruthsSha256": index["canonicalTruthsSha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
