#!/usr/bin/env python3
"""把candidate52生成正样本逐图终审决定终结为哈希绑定的train真值候选。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image
from shapely.geometry import Polygon


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label}无效")
    int(value, 16)
    return value.lower()


def resolve_path(raw: Any, base: Path, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label}为空")
    path = Path(raw)
    return (path if path.is_absolute() else base / path).resolve()


def assert_hash(path: Path, expected: Any, label: str) -> None:
    if not path.is_file() or sha256_file(path) != require_sha(expected, label):
        raise ValueError(f"{label}缺失或发生漂移：{path}")


def write_atomic(path: Path, value: dict[str, Any], protected: set[Path]) -> None:
    resolved = path.resolve()
    if resolved.exists() or resolved in protected:
        raise ValueError("输出不得覆盖既有证据")
    snapshot = {item: sha256_file(item) for item in protected}
    resolved.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{resolved.name}.tmp-", dir=resolved.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for item, expected in snapshot.items():
            if sha256_file(item) != expected:
                raise ValueError(f"输入证据在终结期间变化：{item}")
        os.replace(temporary, resolved)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", required=True, type=Path)
    parser.add_argument("--source-selection", required=True, type=Path)
    parser.add_argument("--standing-commercial-authorization", required=True, type=Path)
    parser.add_argument("--file-name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = Path.cwd().resolve()
    decision_path = args.decision.resolve()
    selection_path = args.source_selection.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    decision = load_json(decision_path, "原分辨率决定")
    selection = load_json(selection_path, "源图冻结清单")
    authorization = load_json(authorization_path, "项目长期商业授权")
    if (
        decision.get("decision") != "candidate52_generated_positive_original_resolution_complete_nail_review_pass"
        or decision.get("reviewStatus") != "pass"
        or decision.get("issueCodes") not in (None, [])
        or decision.get("originalResolutionWholeImageReviewed") is not True
        or decision.get("originalResolutionPerNailCropsReviewed") is not True
    ):
        raise ValueError("原分辨率决定未通过完整视觉门")
    if (
        selection.get("decision") != "selected_for_original_resolution_annotation_only"
        or selection.get("roleIsolation", {}).get("trainingUse") != "prohibited"
        or selection.get("authorization", {}).get("commercialUseAuthorized") is not True
    ):
        raise ValueError("candidate52源图冻结清单契约无效")
    if sha256_file(selection_path) != require_sha(decision.get("sourceSelectionSha256"), "源图清单SHA"):
        raise ValueError("源图冻结清单与决定绑定不一致")
    if (
        authorization.get("decision") != "standing_project_commercial_resource_authorization_granted"
        or authorization.get("scope", {}).get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("项目长期商业授权无效")

    file_name = args.file_name
    review_items = [item for item in decision.get("items", []) if item.get("fileName") == file_name]
    selected_items = [item for item in selection.get("items", []) if item.get("fileName") == file_name]
    if len(review_items) != 1 or len(selected_items) != 1:
        raise ValueError("文件不在终审决定或冻结清单中，或身份重复")
    review = review_items[0]
    selected = selected_items[0]
    complete_count = review.get("finalCompleteMaskCount")
    if isinstance(complete_count, bool) or not isinstance(complete_count, int) or complete_count < 1:
        raise ValueError("最终完整mask数无效")
    if (
        selected.get("sha256") != review.get("imageSha256")
        or selected.get("sourceGroup") != review.get("sourceGroup")
        or selected.get("expectedFullyVisibleNails") != complete_count
    ):
        raise ValueError("冻结源图身份、来源组或完整甲数不一致")

    source_root = Path(str(selection.get("sourceRoot", ""))).resolve()
    image_path = (source_root / file_name).resolve()
    if image_path.parent != source_root:
        raise ValueError("图片路径逃逸源图目录")
    manifest_path = resolve_path(decision.get("manualManifestPath"), root, "返修manifest")
    report_path = resolve_path(decision.get("manualReportPath"), root, "返修报告")
    geometry_path = resolve_path(decision.get("geometryAuditPath"), root, "几何报告")
    annotation_path = resolve_path(review.get("annotationPath"), root, "annotation")
    overlay_path = resolve_path(review.get("reviewedOverlayPath"), root, "overlay")
    assert_hash(image_path, review.get("imageSha256"), "图片SHA")
    assert_hash(manifest_path, decision.get("manualManifestSha256"), "返修manifest SHA")
    assert_hash(report_path, decision.get("manualReportSha256"), "返修报告SHA")
    assert_hash(geometry_path, decision.get("geometryAuditSha256"), "几何报告SHA")
    assert_hash(annotation_path, review.get("annotationSha256"), "annotation SHA")
    assert_hash(overlay_path, review.get("reviewedOverlaySha256"), "overlay SHA")

    report = load_json(report_path, "返修报告")
    outputs = [item for item in report.get("outputs", []) if item.get("fileName") == file_name]
    if (
        report.get("ok") is not True
        or report.get("decision") != "candidate_only_not_training_or_test_truth"
        or report.get("imageCount") != 3
        or report.get("completedCount") != 3
        or report.get("polygonCount") != 20
        or report.get("pairwiseOverlapCount") != 0
        or len(outputs) != 1
        or outputs[0].get("validPolygonCount") != complete_count
        or outputs[0].get("pairwiseOverlapCount") != 0
        or Path(str(outputs[0].get("annotationPath", ""))).resolve() != annotation_path
        or Path(str(outputs[0].get("overlayPath", ""))).resolve() != overlay_path
    ):
        raise ValueError("返修报告未通过完整mask与零交叠合同")
    zoom_paths = outputs[0].get("zoomPaths", [])
    if len(zoom_paths) != complete_count:
        raise ValueError("逐甲2倍视觉证据数量不完整")
    for row in zoom_paths:
        for key in ("source", "overlay"):
            if not Path(str(row.get(key, ""))).resolve().is_file():
                raise ValueError("逐甲2倍视觉证据缺失")

    geometry = load_json(geometry_path, "几何报告")
    source = str(decision.get("geometrySource", ""))
    total_summary = geometry.get("summary", {}).get(source, {})
    rows = [row for row in geometry.get("rows", []) if row.get("fileName") == file_name and row.get("source") == source]
    if (
        geometry.get("decision") != "candidate_only_not_training_truth"
        or total_summary != {"pass": 20, "suspect": 0, "missing": 0}
        or len(rows) != complete_count
        or any(row.get("status") != "pass" or float(row.get("maximumPeerPolygonIntersectionArea", 1)) != 0 for row in rows)
    ):
        raise ValueError("几何审计未通过或条目不完整")

    annotation = load_json(annotation_path, "annotation")
    image_meta = annotation.get("image", {})
    annotations = annotation.get("annotations", [])
    with Image.open(image_path) as image:
        width, height = image.size
    if (
        image_meta.get("fileName") != file_name
        or image_meta.get("sourceGroup") != review.get("sourceGroup")
        or (image_meta.get("width"), image_meta.get("height")) != (width, height)
        or len(annotations) != complete_count
    ):
        raise ValueError("annotation图片身份、尺寸或mask数不一致")
    polygons: list[Polygon] = []
    for index, item in enumerate(annotations, start=1):
        points = [(float(point["x"]), float(point["y"])) for point in item.get("polygon", [])]
        polygon = Polygon(points) if len(points) >= 3 else Polygon()
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 1:
            raise ValueError(f"第{index}个polygon拓扑无效")
        if any(x < 0 or x >= width or y < 0 or y >= height for x, y in points):
            raise ValueError(f"第{index}个polygon越界")
        polygons.append(polygon)
    for left, polygon in enumerate(polygons):
        for right in range(left + 1, len(polygons)):
            if polygon.intersection(polygons[right]).area > 0:
                raise ValueError(f"第{left + 1}/{right + 1}个polygon存在交叠")

    protected = {
        decision_path, selection_path, authorization_path, image_path, manifest_path,
        report_path, geometry_path, annotation_path, overlay_path,
    }
    result = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "approved_as_training_truth_candidate_pending_dataset_materialization",
        "inputs": {
            "truthRole": "train",
            "decision": str(decision_path),
            "decisionSha256": sha256_file(decision_path),
            "sourceSelection": str(selection_path),
            "sourceSelectionSha256": sha256_file(selection_path),
            "standingCommercialAuthorization": str(authorization_path),
            "standingCommercialAuthorizationSha256": sha256_file(authorization_path),
            "image": str(image_path),
            "imageSha256": sha256_file(image_path),
            "annotation": str(annotation_path),
            "annotationSha256": sha256_file(annotation_path),
            "manualReport": str(report_path),
            "manualReportSha256": sha256_file(report_path),
            "geometryAudit": str(geometry_path),
            "geometryAuditSha256": sha256_file(geometry_path),
            "reviewedOverlay": str(overlay_path),
            "reviewedOverlaySha256": sha256_file(overlay_path),
        },
        "policy": {
            "originalResolutionWholeImageAndPerNailReviewRequired": True,
            "completeVisibleNailSurfaceRequired": True,
            "polygonTopologyMustBeValid": True,
            "pairwisePolygonIntersectionArea": 0,
            "watermarkMayNotBeUsedAsRecognitionShortcut": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited-until-materialization-audit",
        },
        "item": {
            "fileName": file_name,
            "sha256": sha256_file(image_path),
            "sourceGroup": review["sourceGroup"],
            "completeMaskCount": complete_count,
            "invalidPolygonCount": 0,
            "overlapPairCount": 0,
            "annotationTruthStatus": "approved-as-training-truth-candidate",
            "trainingUse": "prohibited-until-materialization-audit",
        },
        "errors": [],
    }
    write_atomic(args.output, result, protected)
    print(json.dumps({"ok": True, "fileName": file_name, "completeMaskCount": complete_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
