#!/usr/bin/env python3
"""把candidate58b开发正样本逐图原分辨率决定终结为哈希绑定的train真值候选。

相对candidate51版本的差异（均为2026-09-08开发正样本快速信号测试所需）：
1. 源清单契约改为 development-positive 选集审计
   （decision=development_positive_annotation_workspace_ready_candidate_only）。
2. 允许决策文件记录 expectedFullyVisibleNails 修正
   （visibleNailCountCorrection）：源图筛选阶段高估的"完全可见甲数"
   以本轮原分辨率复核实测为准；修正必须给出原因代码与证据说明，
   且 originalExpected 必须与选集条目一致，防止静默放宽。
3. 几何审计 suspect 豁免规则：弯月形侧视甲（bbox 中心天然落在凹侧
   甲面外）允许在决策文件中按甲豁免，条件是该行
   reasons 含 prompt_center_outside_polygon、boundsContainment==1.0、
   maximumPeerPolygonIntersectionArea==0，且该甲已通过原分辨率视觉
   终审；其余 suspect 一律拒绝。
"""

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
    if not path.is_absolute():
        path = base / path
    return path.resolve()


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
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = Path.cwd().resolve()
    decision_path = args.decision.resolve()
    selection_path = args.source_selection.resolve()
    authorization_path = args.standing_commercial_authorization.resolve()
    decision = load_json(decision_path, "原分辨率决定")
    selection = load_json(selection_path, "开发正样本选集审计")
    authorization = load_json(authorization_path, "项目长期商业授权")

    if (
        decision.get("decision") != "candidate58b_original_resolution_complete_nail_review_pass"
        or decision.get("reviewStatus") != "pass"
        or decision.get("issueCodes") not in (None, [])
        or decision.get("originalResolutionWholeImageReviewed") is not True
        or decision.get("originalResolutionPerNailCropsReviewed") is not True
    ):
        raise ValueError("原分辨率决定未通过完整视觉门")
    if (
        selection.get("ok") is not True
        or selection.get("decision") != "development_positive_annotation_workspace_ready_candidate_only"
        or selection.get("policy", {}).get("originalResolutionSourceReviewRequired") is not True
        or selection.get("policy", {}).get("completeNailMaskReviewRequired") is not True
        or selection.get("trainingUse") != "prohibited"
    ):
        raise ValueError("开发正样本选集审计契约无效")
    if sha256_file(selection_path) != require_sha(decision.get("sourceSelectionSha256"), "选集审计SHA"):
        raise ValueError("选集审计与决定绑定不一致")
    if (
        authorization.get("decision") != "standing_project_commercial_resource_authorization_granted"
        or authorization.get("scope", {}).get("itemizedTrainingAuthorizationRequired") is not False
    ):
        raise ValueError("项目长期商业授权无效")

    file_name = str(decision.get("fileName", ""))
    selected = [item for item in selection.get("items", []) if item.get("fileName") == file_name]
    if len(selected) != 1:
        raise ValueError("决定文件不在选集审计中或身份重复")
    selected_item = selected[0]
    complete_count = decision.get("finalCompleteMaskCount")
    if isinstance(complete_count, bool) or not isinstance(complete_count, int) or complete_count < 1:
        raise ValueError("最终完整mask数无效")

    # 期望数修正：必须显式记录且与选集条目一致
    correction = decision.get("visibleNailCountCorrection")
    original_expected = selected_item.get("expectedFullyVisibleNails")
    if correction is None:
        if complete_count != original_expected:
            raise ValueError("mask数与选集期望不一致且缺少修正记录")
        correction_record: dict[str, Any] = {}
    else:
        if not isinstance(correction, dict):
            raise ValueError("修正记录无效")
        recorded_original = correction.get("originalExpectedFullyVisibleNails")
        corrected = correction.get("correctedVisibleNailCount")
        reason_code = correction.get("reasonCode")
        evidence_note = correction.get("evidenceNote")
        if recorded_original != original_expected or corrected != complete_count:
            raise ValueError("修正记录与选集期望或最终mask数不一致")
        if reason_code not in ("nail-not-fully-visible-on-recheck",) or not isinstance(evidence_note, str) or not evidence_note.strip():
            raise ValueError("修正记录缺少有效原因代码或证据说明")
        correction_record = dict(correction)

    image_path = Path(str(selected_item.get("imagePath", ""))).resolve() if selected_item.get("imagePath") else None
    if image_path is None:
        image_dir = resolve_path(selection.get("imageDir", ""), selection_path.parent, "选集图像目录")
        image_path = image_dir / file_name
    manifest_path = resolve_path(decision.get("manualManifestPath"), root, "返修manifest")
    report_path = resolve_path(decision.get("manualReportPath"), root, "返修报告")
    geometry_path = resolve_path(decision.get("geometryAuditPath"), root, "几何报告")
    annotation_path = resolve_path(decision.get("annotationPath"), root, "annotation")
    overlay_path = resolve_path(decision.get("reviewedOverlayPath"), root, "overlay")
    assert_hash(image_path, selected_item.get("sha256"), "图片SHA")
    assert_hash(manifest_path, decision.get("manualManifestSha256"), "返修manifest SHA")
    assert_hash(report_path, decision.get("manualReportSha256"), "返修报告SHA")
    assert_hash(geometry_path, decision.get("geometryAuditSha256"), "几何报告SHA")
    assert_hash(annotation_path, decision.get("annotationSha256"), "annotation SHA")
    assert_hash(overlay_path, decision.get("reviewedOverlaySha256"), "overlay SHA")

    report = load_json(report_path, "返修报告")
    outputs = [item for item in report.get("outputs", []) if item.get("fileName") == file_name]
    if (
        report.get("ok") is not True
        or report.get("decision") != "candidate_only_not_training_or_test_truth"
        or report.get("completedCount") != len(report.get("outputs", []))
        or report.get("pairwiseOverlapCount") != 0
        or len(outputs) != 1
    ):
        raise ValueError("返修报告批次状态无效")
    output = outputs[0]
    if (
        output.get("polygonCount") != complete_count
        or output.get("validPolygonCount") != complete_count
        or output.get("pairwiseOverlapCount") != 0
        or Path(str(output.get("annotationPath", ""))).resolve() != annotation_path
        or Path(str(output.get("overlayPath", ""))).resolve() != overlay_path
    ):
        raise ValueError("返修报告未通过完整mask与零交叠合同")
    zoom_paths = output.get("zoomPaths", [])
    if len(zoom_paths) != complete_count:
        raise ValueError("逐甲2倍视觉证据数量不完整")
    for row in zoom_paths:
        for key in ("source", "overlay"):
            if not Path(str(row.get(key, ""))).resolve().is_file():
                raise ValueError("逐甲2倍视觉证据缺失")

    geometry = load_json(geometry_path, "几何报告")
    geometry_source = str(decision.get("geometrySource", ""))
    summary = geometry.get("summary", {}).get(geometry_source, {})
    rows = [
        row
        for row in geometry.get("rows", [])
        if row.get("fileName") == file_name and row.get("source") == geometry_source
    ]
    if geometry.get("decision") != "candidate_only_not_training_truth" or len(rows) != complete_count:
        raise ValueError("几何审计决策无效或条目不完整")
    if summary.get("missing") != 0:
        raise ValueError("几何审计存在missing条目")
    exempt_indices = {int(index) for index in decision.get("crescentProfileExemptNails", [])}
    suspect_rows = [row for row in rows if row.get("status") == "suspect"]
    for row in suspect_rows:
        nail_index = int(row.get("nailIndex", -1))
        exempt = (
            nail_index in exempt_indices
            and "prompt_center_outside_polygon" in [str(reason) for reason in row.get("reasons", [])]
            and float(row.get("boundsContainment", 0)) == 1.0
            and float(row.get("maximumPeerPolygonIntersectionArea", 1)) == 0
        )
        if not exempt:
            raise ValueError(f"几何审计suspect条目未获有效豁免：{file_name} 第{nail_index}甲")
    passing_rows = [
        row
        for row in rows
        if row.get("status") == "pass"
        or (
            row.get("status") == "suspect"
            and int(row.get("nailIndex", -1)) in exempt_indices
        )
    ]
    if len(passing_rows) != complete_count or any(
        float(row.get("maximumPeerPolygonIntersectionArea", 1)) != 0 for row in passing_rows
    ):
        raise ValueError("几何审计未全部通过或存在同图交叠面积")

    annotation = load_json(annotation_path, "annotation")
    image_meta = annotation.get("image", {})
    annotations = annotation.get("annotations", [])
    with Image.open(image_path) as image:
        width, height = image.size
    if (
        image_meta.get("fileName") != file_name
        or image_meta.get("sourceGroup") != decision.get("sourceGroup")
        or (image_meta.get("width"), image_meta.get("height")) != (width, height)
        or len(annotations) != complete_count
    ):
        raise ValueError("annotation图片身份、尺寸或mask数不一致")
    polygons: list[Polygon] = []
    for index, item in enumerate(annotations, start=1):
        raw_points = item.get("polygon", [])
        points = [(float(point["x"]), float(point["y"])) for point in raw_points]
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
            "developmentPurpose": "cycle009-single-variable-signal-test",
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
            "visibleNailCountCorrectionRecorded": bool(correction_record),
            "crescentProfileGeometryExemptionApplied": bool(exempt_indices),
            "watermarkMayNotBeUsedAsRecognitionShortcut": True,
            "datasetMaterializationAndSourceIsolationStillRequired": True,
            "trainingUse": "prohibited-until-materialization-audit",
        },
        "visibleNailCountCorrection": correction_record,
        "crescentProfileExemptNails": sorted(exempt_indices),
        "item": {
            "fileName": file_name,
            "sha256": sha256_file(image_path),
            "sourceGroup": decision["sourceGroup"],
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
