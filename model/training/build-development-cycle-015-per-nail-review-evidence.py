#!/usr/bin/env python3
"""合并循环015逐甲候选并物化85槽位逐甲2倍原分辨率终审证据。

合并清单（merge manifest）逐图逐槽位声明候选来源与状态：

- merged：进入同图零交叠合并组（Shapely合法性+两两交叠面积=0，合同校验）；
- provisional：有候选但待视觉仲裁（如候选间交叠、皮肤污染），照常物化2倍
  裁片，并测量其与同图其他候选的两两交叠面积作为仲裁直接输入；
- pending-rework：尚无候选（如缺甲待补标），只登记原因。

脚本同时校验工作区manifest绑定、逐图imageSha256与各来源文件SHA-256、
每图槽位数恰等于expectedFullyVisibleNails，输出哈希绑定报告并支持
--verify-report权威重放。

输出始终是候选级终审证据：不批准mask真值、不授予训练资格、不解除HOLD。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.geometry import Polygon

DECISION = "cycle015_per_nail_review_evidence_candidate_only_not_training_truth"

STATUS_COLORS = {
    "merged": ((0, 220, 90, 80), (0, 190, 70, 255)),
    "provisional": ((255, 165, 0, 90), (230, 120, 0, 255)),
}


def install_read_only_ultralytics_image_check() -> None:
    """安装与训练器一致的只读图片守卫，保护哈希绑定源图。"""

    from ultralytics.data import utils as data_utils

    def check_image_read_only(im_file: str) -> tuple[str, tuple[int, int]]:
        with Image.open(im_file) as image:
            image.verify()
        with Image.open(im_file) as image:
            image.load()
            shape = (int(image.height), int(image.width))
            image_format = str(image.format or "").lower()
        if shape[0] <= 9 or shape[1] <= 9:
            raise AssertionError(f"image size {shape} <10 pixels")
        if image_format not in data_utils.IMG_FORMATS:
            raise AssertionError(f"Invalid image format {image_format}")
        return "", shape

    data_utils.check_image = check_image_read_only
    if data_utils.verify_image.__globals__.get("check_image") is not check_image_read_only:
        raise RuntimeError("failed to install read-only Ultralytics image verifier")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_object(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{label}不存在：{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}不是JSON对象")
    return value


def load_annotation_document(path: Path, label: str) -> dict[str, Any]:
    document = read_object(path, label)
    if document.get("trainingUse") != "prohibited":
        raise ValueError(f"{label}trainingUse角色漂移：{path}")
    if document.get("masksApprovedAsTruth") is True:
        raise ValueError(f"{label}越权批准真值：{path}")
    if not isinstance(document.get("annotations"), list):
        raise ValueError(f"{label}缺少annotations数组：{path}")
    return document


def normalize_point(point: dict[str, Any], width: int, height: int, label: str) -> dict[str, float]:
    if not isinstance(point, dict) or "x" not in point or "y" not in point:
        raise ValueError(f"{label}多边形点缺少x/y")
    x = float(point["x"])
    y = float(point["y"])
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"{label}多边形点越界：({x}, {y})")
    return {"x": int(x) if x.is_integer() else x, "y": int(y) if y.is_integer() else y}


def normalize_polygon(raw: Any, width: int, height: int, label: str) -> list[dict[str, float]]:
    if not isinstance(raw, list) or len(raw) < 3:
        raise ValueError(f"{label}多边形至少需要三个点")
    return [normalize_point(point, width, height, label) for point in raw]


def validate_candidate(entries: list[dict[str, Any]]) -> list[Polygon]:
    """逐甲合法性（所有有polygon的槽位，无论状态）。"""

    shapes: list[Polygon] = []
    for entry in entries:
        shape = Polygon([(point["x"], point["y"]) for point in entry["polygon"]])
        if not shape.is_valid:
            raise ValueError(f"{entry['label']}多边形非法（自交或退化）")
        if shape.area <= 1:
            raise ValueError(f"{entry['label']}多边形面积为空")
        entry["shape"] = shape
        shapes.append(shape)
    return shapes


def check_merged_zero_overlap(entries: list[dict[str, Any]]) -> None:
    """merged组合同校验：两两交叠面积必须为0。"""

    merged = [entry for entry in entries if entry["status"] == "merged"]
    for first_index, first in enumerate(merged):
        for second in merged[first_index + 1 :]:
            overlap = first["shape"].intersection(second["shape"]).area
            if overlap > 0:
                raise ValueError(
                    f"{first['label']}与{second['label']}在merged组交叠{overlap:.4f}平方像素"
                )


def measure_overlaps(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """测量同图所有候选两两交叠（merged组内应为0；含provisional参与的对）。"""

    observations: list[dict[str, Any]] = []
    candidates = [entry for entry in entries if entry["status"] in ("merged", "provisional")]
    for first_index, first in enumerate(candidates):
        for second in candidates[first_index + 1 :]:
            overlap = first["shape"].intersection(second["shape"]).area
            if overlap > 0:
                observations.append({
                    "slotA": first["slot"],
                    "slotB": second["slot"],
                    "statusA": first["status"],
                    "statusB": second["status"],
                    "overlapPixels": round(overlap, 4),
                })
    return observations


def draw_overlay(
    image_path: Path,
    entries: list[dict[str, Any]],
    output_path: Path,
) -> None:
    with Image.open(image_path) as source:
        overlay = source.convert("RGB")
    draw = ImageDraw.Draw(overlay, "RGBA")
    for entry in entries:
        fill, outline = STATUS_COLORS[entry["status"]]
        points = [(point["x"], point["y"]) for point in entry["polygon"]]
        draw.polygon(points, fill=fill, outline=outline, width=3)
        anchor = points[0]
        draw.text(anchor, str(entry["slot"]), fill=(255, 30, 30, 255), stroke_width=2, stroke_fill="white")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)


def write_nail_crops(
    image_path: Path,
    overlay_path: Path,
    entries: list[dict[str, Any]],
    crop_dir: Path,
) -> dict[int, dict[str, str]]:
    crop_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as source:
        original = source.convert("RGB")
    with Image.open(overlay_path) as source:
        overlay = source.convert("RGB")
    outputs: dict[int, dict[str, str]] = {}
    padding = 24
    for entry in entries:
        xs = [float(point["x"]) for point in entry["polygon"]]
        ys = [float(point["y"]) for point in entry["polygon"]]
        bounds = (
            max(0, int(min(xs)) - padding),
            max(0, int(min(ys)) - padding),
            min(overlay.width, int(max(xs)) + padding + 1),
            min(overlay.height, int(max(ys)) + padding + 1),
        )
        stem = Path(image_path).stem
        slot = entry["slot"]
        overlay_crop = overlay.crop(bounds)
        source_crop = original.crop(bounds)
        size = (overlay_crop.width * 2, overlay_crop.height * 2)
        overlay_output = crop_dir / f"{stem}-slot{slot:02d}-overlay-2x.png"
        source_output = crop_dir / f"{stem}-slot{slot:02d}-source-2x.png"
        overlay_crop.resize(size, Image.Resampling.LANCZOS).save(overlay_output)
        source_crop.resize(size, Image.Resampling.LANCZOS).save(source_output)
        outputs[slot] = {
            "source": str(source_output.resolve()),
            "overlay": str(overlay_output.resolve()),
        }
    return outputs


def resolve_merge_path(value: str, workspace_root: Path) -> Path:
    """合并清单内的相对路径一律相对工作区根目录解析。"""

    path = Path(value)
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve()


def build_slot_entries(
    merge_manifest: dict[str, Any],
    workspace_root: Path,
    prelabel_by_name: dict[str, dict[str, Any]],
    image_sizes: dict[str, tuple[int, int]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """按合并清单逐图逐槽位装配候选；返回(逐图entries, 来源绑定记录)。"""

    entries_by_name: dict[str, list[dict[str, Any]]] = {}
    source_bindings: list[dict[str, Any]] = []
    loaded_documents: dict[str, dict[str, Any]] = {}
    for image_entry in merge_manifest.get("images") or []:
        name = str(image_entry.get("fileName") or "")
        if name not in image_sizes:
            raise ValueError(f"合并清单引用了工作区之外的图：{name}")
        width, height = image_sizes[name]
        entries: list[dict[str, Any]] = []
        seen_slots: set[int] = set()
        for nail in image_entry.get("nails") or []:
            slot = int(nail["slot"])
            if slot < 1 or slot in seen_slots:
                raise ValueError(f"{name}槽位编号非法或重复：{slot}")
            seen_slots.add(slot)
            source = nail.get("source") or {}
            kind = str(source.get("kind") or "")
            declared_status = str(nail.get("status") or "")
            if kind == "pending-rework":
                if declared_status not in ("", "pending"):
                    raise ValueError(f"{name}槽位{slot}pending-rework不允许声明其他状态")
                entries.append({
                    "slot": slot,
                    "status": "pending",
                    "reason": str(source.get("reason") or "unspecified"),
                })
                continue
            if kind not in ("prelabel", "repair"):
                raise ValueError(f"{name}槽位{slot}来源类型未知：{kind}")
            if declared_status not in ("", "merged", "provisional"):
                raise ValueError(f"{name}槽位{slot}状态非法：{declared_status}")
            status = declared_status or "merged"
            if kind == "prelabel":
                prelabel_item = prelabel_by_name.get(name)
                if prelabel_item is None:
                    raise ValueError(f"{name}缺少prelabel处置条目")
                document_path = Path(str(prelabel_item["annotationPath"])).resolve()
                label = f"{name}槽位{slot}prelabel"
            else:
                document_path = resolve_merge_path(str(source["path"]), workspace_root)
                label = f"{name}槽位{slot}repair"
            annotation_index = int(source.get("annotationIndex") or 0)
            if annotation_index < 1:
                raise ValueError(f"{label}annotationIndex必须从1起")
            cache_key = str(document_path)
            if cache_key not in loaded_documents:
                document = load_annotation_document(document_path, f"{label}来源文档")
                loaded_documents[cache_key] = document
                source_bindings.append({
                    "path": str(document_path),
                    "sha256": sha256_file(document_path),
                    "decision": str(document.get("decision") or ""),
                })
            document = loaded_documents[cache_key]
            annotations = document["annotations"]
            if annotation_index > len(annotations):
                raise ValueError(f"{label}annotationIndex越界：{annotation_index}>{len(annotations)}")
            annotation = annotations[annotation_index - 1]
            polygon = normalize_polygon(annotation.get("polygon"), width, height, label)
            entries.append({
                "slot": slot,
                "status": status,
                "label": f"{name}槽位{slot}",
                "polygon": polygon,
                "origin": {
                    "kind": kind,
                    "path": str(document_path),
                    "annotationIndex": annotation_index,
                    "annotationId": str(annotation.get("id") or ""),
                    "annotationMethod": str((annotation.get("attributes") or {}).get("annotationMethod") or ""),
                    "declaredOrigin": str(source.get("origin") or ""),
                },
            })
        expected = int(image_entry.get("expectedFullyVisibleNails") or 0)
        if expected <= 0 or seen_slots != set(range(1, expected + 1)):
            missing = sorted(set(range(1, expected + 1)) - seen_slots)
            raise ValueError(f"{name}合并清单槽位不完整，缺失：{missing}")
        entries_by_name[name] = entries
    if not entries_by_name:
        raise ValueError("合并清单没有覆盖任何图")
    return entries_by_name, source_bindings


def build_report(
    workspace_path: Path,
    disposition_path: Path,
    merge_path: Path,
    image_dir: Path,
    output_dir: Path,
    materialize: bool,
) -> dict[str, Any]:
    """构建（或重放校验）逐甲终审证据报告。

    materialize=True 时写overlay与裁片；False 时仅读取既有输出文件计算SHA，
    用于 --verify-report 权威重放。
    """

    workspace_path = workspace_path.resolve()
    disposition_path = disposition_path.resolve()
    merge_path = merge_path.resolve()
    image_dir = image_dir.resolve()
    output_dir = output_dir.resolve()
    workspace = read_object(workspace_path, "标注工作区manifest")
    disposition = read_object(disposition_path, "首轮mask审核处置报告")
    merge_manifest = read_object(merge_path, "逐甲合并清单")
    if (
        workspace.get("ok") is not True
        or workspace.get("decision") != "development_cycle_015_generated_annotation_workspace_ready_candidate_only"
        or workspace.get("trainingUse") != "prohibited"
    ):
        raise ValueError("循环015标注工作区合同无效")
    disposition_inputs = disposition.get("inputs") or {}
    if (
        disposition.get("ok") is not True
        or disposition.get("trainingUse") != "prohibited"
        or disposition.get("masksApprovedAsTruth") is not False
        or disposition_inputs.get("workspace", {}).get("sha256") != sha256_file(workspace_path)
    ):
        raise ValueError("首轮处置报告未绑定当前工作区或角色漂移")
    if merge_manifest.get("decision") != DECISION:
        raise ValueError("逐甲合并清单decision不符")
    if merge_manifest.get("trainingUse") != "prohibited":
        raise ValueError("逐甲合并清单trainingUse必须为prohibited")
    merge_inputs = merge_manifest.get("inputs") or {}
    if (
        merge_inputs.get("workspace", {}).get("sha256") != sha256_file(workspace_path)
        or merge_inputs.get("disposition", {}).get("sha256") != sha256_file(disposition_path)
    ):
        raise ValueError("逐甲合并清单未绑定当前工作区或处置报告")

    workspace_by_name = {str(item["fileName"]): item for item in workspace.get("items") or []}
    prelabel_by_name = {
        str(item["fileName"]): item for item in disposition.get("items") or []
    }

    image_sizes: dict[str, tuple[int, int]] = {}
    image_bindings: list[dict[str, Any]] = []
    for name, workspace_item in workspace_by_name.items():
        image_path = (image_dir / name).resolve()
        if not image_path.is_file() or image_path.parent != image_dir:
            raise ValueError(f"工作区图缺失或越界：{name}")
        actual_sha = sha256_file(image_path)
        if actual_sha != workspace_item.get("sha256"):
            raise ValueError(f"工作区图SHA-256漂移：{name}")
        with Image.open(image_path) as image:
            width, height = image.size
        image_sizes[name] = (width, height)
        image_bindings.append({"fileName": name, "sha256": actual_sha})

    entries_by_name, source_bindings = build_slot_entries(
        merge_manifest, workspace_path.parent, prelabel_by_name, image_sizes
    )

    if set(entries_by_name) - set(workspace_by_name):
        raise ValueError("合并清单覆盖了工作区之外的图")
    missing_images = sorted(set(workspace_by_name) - set(entries_by_name))
    if missing_images:
        raise ValueError(f"合并清单未覆盖全部工作区图：{missing_images}")

    items: list[dict[str, Any]] = []
    for name in sorted(workspace_by_name):
        workspace_item = workspace_by_name[name]
        expected = int(workspace_item["expectedFullyVisibleNails"])
        entries = entries_by_name[name]
        merged = [entry for entry in entries if entry["status"] == "merged"]
        provisional = [entry for entry in entries if entry["status"] == "provisional"]
        pending = [entry for entry in entries if entry["status"] == "pending"]
        if len(merged) + len(provisional) + len(pending) != expected:
            raise ValueError(f"{name}槽位总数不等于预期完整甲面数")
        drawable = [entry for entry in entries if entry["status"] in ("merged", "provisional")]
        validate_candidate(drawable)
        check_merged_zero_overlap(entries)
        overlap_observations = measure_overlaps(entries)
        overlay_path = output_dir / "overlays" / f"{Path(name).stem}-per-nail-merge-overlay.png"
        if materialize and drawable:
            draw_overlay(image_dir / name, drawable, overlay_path)
        if drawable and not overlay_path.is_file():
            raise ValueError(f"整图overlay缺失（先物化再重放）：{overlay_path}")
        crops: dict[int, dict[str, str]] = {}
        if materialize and drawable:
            crops = write_nail_crops(image_dir / name, overlay_path, drawable, output_dir / "crops")
        elif not materialize:
            stem = Path(name).stem
            for entry in drawable:
                slot = entry["slot"]
                crops[slot] = {
                    "source": str((output_dir / "crops" / f"{stem}-slot{slot:02d}-source-2x.png").resolve()),
                    "overlay": str((output_dir / "crops" / f"{stem}-slot{slot:02d}-overlay-2x.png").resolve()),
                }
        nail_records: list[dict[str, Any]] = []
        for entry in drawable:
            slot = entry["slot"]
            source_crop = Path(crops[slot]["source"])
            overlay_crop = Path(crops[slot]["overlay"])
            if not source_crop.is_file() or not overlay_crop.is_file():
                raise ValueError(f"{name}槽位{slot}裁片缺失（先物化再重放）")
            nail_records.append({
                "slot": slot,
                "status": entry["status"],
                "sourcePath": str(source_crop),
                "sourceSha256": sha256_file(source_crop),
                "overlayPath": str(overlay_crop),
                "overlaySha256": sha256_file(overlay_crop),
                "origin": entry["origin"],
            })
        pending_records = [
            {"slot": entry["slot"], "reason": entry["reason"]} for entry in pending
        ]
        items.append({
            "fileName": name,
            "imageSha256": workspace_item["sha256"],
            "sourceGroup": workspace_item["sourceGroup"],
            "expectedFullyVisibleNails": expected,
            "mergedNailCount": len(merged),
            "provisionalNailCount": len(provisional),
            "pendingNailCount": len(pending),
            "nails": nail_records,
            "pendingSlots": pending_records,
            "overlapObservations": overlap_observations,
            "overlayPath": str(overlay_path) if drawable else None,
            "overlaySha256": sha256_file(overlay_path) if drawable and overlay_path.is_file() else None,
            "trainingUse": "prohibited",
        })

    return {
        "schemaVersion": 1,
        "ok": True,
        "decision": DECISION,
        "inputs": {
            "workspace": {"path": str(workspace_path), "sha256": sha256_file(workspace_path)},
            "disposition": {"path": str(disposition_path), "sha256": sha256_file(disposition_path)},
            "mergeManifest": {"path": str(merge_path), "sha256": sha256_file(merge_path)},
            "images": image_bindings,
            "annotationSources": source_bindings,
        },
        "counts": {
            "images": len(items),
            "expectedFullyVisibleNails": sum(item["expectedFullyVisibleNails"] for item in items),
            "mergedNails": sum(item["mergedNailCount"] for item in items),
            "provisionalNails": sum(item["provisionalNailCount"] for item in items),
            "pendingNails": sum(item["pendingNailCount"] for item in items),
            "imagesWithOverlapObservations": sum(
                bool(item["overlapObservations"]) for item in items
            ),
        },
        "policy": {
            "countMatchDoesNotApproveBoundaries": True,
            "fullImageOverlayReviewDoesNotReplacePerNailCropReview": True,
            "perNailEvidenceDoesNotApproveMasks": True,
            "provisionalOverlapsAreArbitrationInputNotContractFailure": True,
            "reworkMustRestoreEveryFullyVisibleNail": True,
            "originalResolutionPerNailReviewStillRequired": True,
        },
        "items": items,
        "trainingUse": "prohibited",
        "masksApprovedAsTruth": False,
        "formalPromotionAllowed": False,
        "nextAction": "review_merged_and_provisional_nails_at_2x_original_resolution_then_converge_pending_slots",
        "releaseState": "hold",
        "productState": "hold",
        "errors": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--disposition", required=True)
    parser.add_argument("--merge", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    install_read_only_ultralytics_image_check()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        existing = read_object(report_path, "待重放逐甲终审证据报告")
        inputs = existing.get("inputs") or {}
        replay = build_report(
            Path(inputs["workspace"]["path"]),
            Path(inputs["disposition"]["path"]),
            Path(inputs["mergeManifest"]["path"]),
            Path(args.image_dir).resolve(),
            Path(args.output_dir).resolve(),
            materialize=False,
        )
        if replay != existing:
            raise ValueError("逐甲终审证据报告与绑定输入重放不一致")
        print(json.dumps({
            "ok": True,
            "decision": existing["decision"],
            "reportSha256": sha256_file(report_path),
        }, ensure_ascii=False))
        return 0
    report_path = Path(args.report).resolve()
    if report_path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{report_path}")
    report = build_report(
        Path(args.workspace),
        Path(args.disposition),
        Path(args.merge),
        Path(args.image_dir),
        Path(args.output_dir),
        materialize=True,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "decision": report["decision"],
        "counts": report["counts"],
        "reportSha256": sha256_file(report_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
