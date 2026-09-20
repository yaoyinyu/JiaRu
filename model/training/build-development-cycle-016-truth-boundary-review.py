#!/usr/bin/env python3
"""重建 cycle016 固定36例原分辨率真值边界审核包。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_guards() -> tuple[Any, Any]:
    path = Path(__file__).resolve().with_name("train-yolo-seg.py")
    spec = importlib.util.spec_from_file_location("nail_texture_train_yolo_seg", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载只读图片守卫")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_read_only_ultralytics_image_check, module.remove_ultralytics_label_caches


def parse_polygons(path: Path) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.strip().split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法标签：{path}:{line_number}")
        result.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float32).reshape(-1, 2))
    return result


def crop_box(polygon: np.ndarray, width: int, height: int, scale: float) -> tuple[int, int, int, int]:
    pixels = polygon * np.asarray([width, height], dtype=np.float32)
    minimum = pixels.min(axis=0)
    maximum = pixels.max(axis=0)
    center = (minimum + maximum) / 2
    side = min(max(maximum[0] - minimum[0], maximum[1] - minimum[1]) * scale, min(width, height))
    side = max(float(side), 8.0)
    rounded = int(round(side))
    x1 = min(max(0, int(round(center[0] - side / 2))), max(0, width - rounded))
    y1 = min(max(0, int(round(center[1] - side / 2))), max(0, height - rounded))
    return x1, y1, min(width, x1 + rounded), min(height, y1 + rounded)


def rebuilt_roi_hashes(image: np.ndarray, polygon: np.ndarray, box: tuple[int, int, int, int], size: int) -> tuple[str, str]:
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2]
    height, width = image.shape[:2]
    pixels = polygon * np.asarray([width, height], dtype=np.float32) - np.asarray([x1, y1], dtype=np.float32)
    mask = np.zeros((y2 - y1, x2 - x1), dtype=np.uint8)
    cv2.fillPoly(mask, [np.rint(pixels).astype(np.int32)], 255)
    crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)
    mask = cv2.resize(mask, (size, size), interpolation=cv2.INTER_NEAREST)
    image_bytes = io.BytesIO()
    mask_bytes = io.BytesIO()
    Image.fromarray(crop).save(image_bytes, format="JPEG", quality=95, subsampling=0)
    Image.fromarray(mask).save(mask_bytes, format="PNG", optimize=True)
    return hashlib.sha256(image_bytes.getvalue()).hexdigest(), hashlib.sha256(mask_bytes.getvalue()).hexdigest()


def panel(image: np.ndarray, polygon: np.ndarray, box: tuple[int, int, int, int], title: str) -> Image.Image:
    x1, y1, x2, y2 = box
    height, width = image.shape[:2]
    pixels = polygon * np.asarray([width, height], dtype=np.float32)
    local = pixels - np.asarray([x1, y1], dtype=np.float32)
    crop = Image.fromarray(image[y1:y2, x1:x2])
    raw = crop.resize((360, 360), Image.Resampling.LANCZOS)
    overlay = raw.copy()
    draw = ImageDraw.Draw(overlay)
    sx = 360 / max(1, x2 - x1)
    sy = 360 / max(1, y2 - y1)
    points = [(float(point[0] * sx), float(point[1] * sy)) for point in local]
    draw.line(points + [points[0]], fill=(0, 255, 0), width=4, joint="curve")
    canvas = Image.new("RGB", (736, 404), "white")
    canvas.paste(raw, (4, 4))
    canvas.paste(overlay, (372, 4))
    text = ImageDraw.Draw(canvas)
    text.text((6, 370), title[:108], fill="black")
    text.text((6, 386), "left=raw source crop | right=canonical polygon edge", fill="black")
    return canvas


def build(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    for name, key in (("attributionReport", "attributionReportSha256"), ("roiDatasetReport", "roiDatasetReportSha256"), ("cycle012DatasetReport", "cycle012DatasetReportSha256")):
        if sha256_file(Path(plan["inputs"][name])) != plan["inputs"][key]:
            raise ValueError(f"输入哈希不匹配：{name}")
    if "fixed36FinalReview" in plan["inputs"] and sha256_file(Path(plan["inputs"]["fixed36FinalReview"])) != plan["inputs"]["fixed36FinalReviewSha256"]:
        raise ValueError("固定36例最终报告哈希不匹配")
    attribution = json.loads(Path(plan["inputs"]["attributionReport"]).read_text(encoding="utf-8"))
    roi_report = json.loads(Path(plan["inputs"]["roiDatasetReport"]).read_text(encoding="utf-8"))
    source_report = json.loads(Path(plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    if roi_report["inputs"]["cycle012MaterializationReport"]["sha256"] != plan["inputs"]["cycle012DatasetReportSha256"]:
        raise ValueError("ROI报告未绑定同一cycle012报告")
    if plan["selection"].get("mode") == "all_attribution_records":
        ordered = sorted(attribution["records"], key=lambda row: (row["sourceGroup"], row["id"]))
        selected = [("all", index + 1, row) for index, row in enumerate(ordered)]
    else:
        worst = sorted(attribution["records"], key=lambda row: (row["boundaryF1"], row["iou"]))[: int(plan["selection"]["worst"])]
        best = sorted(attribution["records"], key=lambda row: (row["boundaryF1"], row["iou"]), reverse=True)[: int(plan["selection"]["best"])]
        selected = [("worst", index + 1, row) for index, row in enumerate(worst)] + [("best", index + 1, row) for index, row in enumerate(best)]
    if len({row[2]["id"] for row in selected}) != int(plan["selection"]["expectedInstances"]):
        raise ValueError("固定清单存在重复或数量不一致")
    roi_root = Path(roi_report["outputDir"])
    roi_manifest = json.loads((roi_root / "manifest.json").read_text(encoding="utf-8"))["records"]
    roi_by_id = {row["id"]: row for row in roi_manifest}
    source_root = Path(source_report["outputDir"])
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    (temporary / "pages").mkdir()
    review_records: list[dict[str, Any]] = []
    panels: list[Image.Image] = []
    try:
        for cohort, rank, metric in selected:
            roi = roi_by_id[metric["id"]]
            source_row = source_by_key[(roi["sourceFileName"], roi["sourceGroup"])]
            image_path = source_root / source_row["image"]
            label_path = source_root / source_row["label"]
            if sha256_file(image_path) != source_row["imageSha256"] or sha256_file(label_path) != source_row["labelSha256"]:
                raise ValueError(f"cycle012源文件哈希不匹配：{metric['id']}")
            if sha256_file(roi_root / roi["image"]) != roi["imageSha256"] or sha256_file(roi_root / roi["mask"]) != roi["maskSha256"]:
                raise ValueError(f"ROI文件哈希不匹配：{metric['id']}")
            with Image.open(image_path) as source:
                image = np.asarray(source.convert("RGB"))
            polygons = parse_polygons(label_path)
            polygon = polygons[int(roi["truthIndex"]) - 1]
            box = crop_box(polygon, image.shape[1], image.shape[0], float(roi_report["contract"]["cropScale"]))
            if list(box) != roi["cropBox"]:
                raise ValueError(f"cropBox重建不一致：{metric['id']}")
            rebuilt_image, rebuilt_mask = rebuilt_roi_hashes(image, polygon, box, int(roi_report["contract"]["size"]))
            if rebuilt_image != roi["imageSha256"] or rebuilt_mask != roi["maskSha256"]:
                raise ValueError(f"ROI字节重建不一致：{metric['id']}")
            title = f"{cohort}{rank:02d} {metric['id']} BF1={metric['boundaryF1']:.3f} IoU={metric['iou']:.3f}"
            panels.append(panel(image, polygon, box, title))
            review_records.append({
                "id": metric["id"], "cohort": cohort, "rank": rank,
                "boundaryF1": metric["boundaryF1"], "iou": metric["iou"],
                "sourceFileName": roi["sourceFileName"], "sourceGroup": roi["sourceGroup"],
                "truthIndex": roi["truthIndex"], "cropBox": roi["cropBox"],
                "sourceImage": str(image_path), "sourceImageSha256": source_row["imageSha256"],
                "sourceLabel": str(label_path), "sourceLabelSha256": source_row["labelSha256"],
                "verdict": None, "regions": {"root": None, "leftSide": None, "rightSide": None, "tip": None}, "notes": ""
            })
        page_bindings = []
        for offset in range(0, len(panels), 4):
            page = Image.new("RGB", (1472, 808), "white")
            for position, item in enumerate(panels[offset : offset + 4]):
                page.paste(item, ((position % 2) * 736, (position // 2) * 404))
            page_path = temporary / "pages" / f"review-{offset // 4 + 1:02d}.png"
            page.save(page_path, format="PNG", optimize=True)
            page_bindings.append({"path": page_path.relative_to(temporary).as_posix(), "sha256": sha256_file(page_path), "recordIds": [row["id"] for row in review_records[offset : offset + 4]]})
        input_bindings = {name: {"path": plan["inputs"][name], "sha256": plan["inputs"][key]} for name, key in (("attributionReport", "attributionReportSha256"), ("roiDatasetReport", "roiDatasetReportSha256"), ("cycle012DatasetReport", "cycle012DatasetReportSha256"))}
        if "fixed36FinalReview" in plan["inputs"]:
            input_bindings["fixed36FinalReview"] = {"path": plan["inputs"]["fixed36FinalReview"], "sha256": plan["inputs"]["fixed36FinalReviewSha256"]}
        report = {
            "schemaVersion": 1, "ok": True, "decision": "review_package_ready_manual_verdict_required",
            "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "modelSelection": False},
            "inputs": input_bindings,
            "reconstruction": {"expected": int(plan["selection"]["expectedInstances"]), "matched": len(review_records), "cropBoxesExact": len(review_records), "roiBytesExact": len(review_records)},
            "pages": page_bindings, "records": review_records, "errors": []
        }
        (temporary / "review-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify(output: Path) -> dict[str, Any]:
    report_path = output / "review-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for binding in report["inputs"].values():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError("输入绑定哈希不一致")
    for page in report["pages"]:
        if sha256_file(output / page["path"]) != page["sha256"]:
            raise ValueError(f"审核页哈希不一致：{page['path']}")
    expected = int(report["reconstruction"]["expected"])
    if report["reconstruction"] != {"expected": expected, "matched": expected, "cropBoxesExact": expected, "roiBytesExact": expected}:
        raise ValueError("重建保真门未通过")
    return {"ok": True, "decision": "verified", "reconstruction": report["reconstruction"], "reportSha256": sha256_file(report_path)}


def finalize(review_dir: Path, decisions_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise ValueError(f"最终报告已存在，禁止覆盖：{output_path}")
    verification = verify(review_dir)
    review_path = review_dir / "review-report.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    if decisions["reviewReportSha256"] != verification["reportSha256"]:
        raise ValueError("裁决未绑定当前审核报告")
    expected_ids = [row["id"] for row in review["records"]]
    rows = decisions["decisions"]
    if [row["id"] for row in rows] != expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ValueError("裁决清单与固定审核报告顺序或身份不一致")
    shard_bindings = decisions.get("shardBindings", [])
    if shard_bindings:
        bound_rows: list[dict[str, Any]] = []
        expected_start = 1
        for binding in shard_bindings:
            shard_path = Path(binding["path"])
            if sha256_file(shard_path) != binding["sha256"]:
                raise ValueError(f"分片输入哈希不一致：{shard_path}")
            shard = json.loads(shard_path.read_text(encoding="utf-8"))
            start = int(shard["range"]["startOneBased"])
            end = int(shard["range"]["endOneBased"])
            if start != expected_start or end < start:
                raise ValueError("分片范围不连续")
            bound_rows.extend(shard["decisions"])
            expected_start = end + 1
        if expected_start != len(expected_ids) + 1 or bound_rows != rows:
            raise ValueError("分片裁决未完整同构为最终裁决")
    allowed = {"pass", "oversegmented", "undersegmented", "mixed_error", "ambiguous_source"}
    region_keys = {"root", "leftSide", "rightSide", "tip"}
    for row in rows:
        if row["verdict"] not in allowed or set(row["regions"]) != region_keys:
            raise ValueError(f"非法裁决：{row['id']}")
    counts = {name: sum(row["verdict"] == name for row in rows) for name in sorted(allowed)}
    issue_counts: dict[str, int] = {}
    for row in rows:
        for issue in row.get("issueCodes", []):
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    systematic = sorted(name for name, count in issue_counts.items() if count >= 4)
    next_action = "full_validation_truth_reaudit_and_correction_before_training" if systematic else "change_boundary_supervision_only"
    inputs = {
        "reviewReport": {"path": str(review_path), "sha256": verification["reportSha256"]},
        "decisions": {"path": str(decisions_path), "sha256": sha256_file(decisions_path)},
    }
    for index, binding in enumerate(shard_bindings, start=1):
        inputs[f"reviewShard{index:03d}"] = binding
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": next_action,
        "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "pilotMetricsRemainDiagnostic": True},
        "inputs": inputs,
        "counts": {"instances": len(rows), **counts, "sourceGroups": len({row["sourceGroup"] for row in review["records"]})},
        "issueCounts": issue_counts,
        "systematicIssueCodes": systematic,
        "rationale": f"固定{len(rows)}例审核发现验证真值缺陷；按验证集真值规则，完成缺陷修正和v2重建前，该折不得继续用于模型选择或阈值校准。" if systematic else "固定样本未发现系统真值缺陷。",
        "decisions": rows,
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.tmp-", dir=output_path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return report


def verify_final(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    for binding in report["inputs"].values():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError("最终报告输入哈希不一致")
    review = json.loads(Path(report["inputs"]["reviewReport"]["path"]).read_text(encoding="utf-8"))
    if report["counts"]["instances"] != len(review["records"]):
        raise ValueError("最终裁决实例数不一致")
    return {"ok": True, "decision": report["decision"], "counts": report["counts"], "systematicIssueCodes": report["systematicIssueCodes"], "reportSha256": sha256_file(path)}


def build_correction_manifest(final_path: Path, output_path: Path) -> dict[str, Any]:
    verification = verify_final(final_path)
    final = json.loads(final_path.read_text(encoding="utf-8"))
    review_path = Path(final["inputs"]["reviewReport"]["path"])
    review = json.loads(review_path.read_text(encoding="utf-8"))
    records = {row["id"]: row for row in review["records"]}
    decisions = final["decisions"]
    ambiguous_sources = {
        records[row["id"]]["sourceFileName"]
        for row in decisions
        if row["verdict"] == "ambiguous_source"
    }
    items = []
    for decision in decisions:
        record = records[decision["id"]]
        if record["sourceFileName"] in ambiguous_sources:
            action = "exclude_source_image"
        elif decision["verdict"] == "pass":
            action = "retain"
        else:
            action = "repair_polygon"
        items.append({
            "id": decision["id"],
            "sourceFileName": record["sourceFileName"],
            "sourceGroup": record["sourceGroup"],
            "truthIndex": record["truthIndex"],
            "action": action,
            "originalVerdict": decision["verdict"],
            "issueCodes": decision.get("issueCodes", []),
        })
    action_counts = {
        name: sum(row["action"] == name for row in items)
        for name in ("exclude_source_image", "repair_polygon", "retain")
    }
    report = {
        "schemaVersion": 1,
        "ok": True,
        "decision": "frozen_correction_and_exclusion_manifest",
        "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "trainingUse": "prohibited_until_v2_review_pass"},
        "inputs": {
            "finalReviewReport": {"path": str(final_path), "sha256": verification["reportSha256"]},
            "reviewReport": {"path": str(review_path), "sha256": sha256_file(review_path)},
        },
        "counts": {
            "instances": len(items),
            **action_counts,
            "excludedSourceImages": len(ambiguous_sources),
            "excludedSourceGroups": len({records[row["id"]]["sourceGroup"] for row in decisions if records[row["id"]]["sourceFileName"] in ambiguous_sources}),
        },
        "excludedSourceImages": sorted(ambiguous_sources),
        "items": items,
        "errors": [],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def verify_correction_manifest(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    for binding in report["inputs"].values():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError("修正清单输入哈希不一致")
    final = json.loads(Path(report["inputs"]["finalReviewReport"]["path"]).read_text(encoding="utf-8"))
    review = json.loads(Path(report["inputs"]["reviewReport"]["path"]).read_text(encoding="utf-8"))
    records = {row["id"]: row for row in review["records"]}
    items = report["items"]
    if [row["id"] for row in items] != [row["id"] for row in final["decisions"]]:
        raise ValueError("修正清单未覆盖最终裁决顺序")
    ambiguous_sources = {
        records[row["id"]]["sourceFileName"]
        for row in final["decisions"]
        if row["verdict"] == "ambiguous_source"
    }
    for item, decision in zip(items, final["decisions"], strict=True):
        expected = "exclude_source_image" if item["sourceFileName"] in ambiguous_sources else ("retain" if decision["verdict"] == "pass" else "repair_polygon")
        if item["action"] != expected:
            raise ValueError(f"修正动作不一致：{item['id']}")
    counts = {
        name: sum(row["action"] == name for row in items)
        for name in ("exclude_source_image", "repair_polygon", "retain")
    }
    if report["counts"]["instances"] != len(items) or any(report["counts"][name] != count for name, count in counts.items()):
        raise ValueError("修正清单计数不一致")
    return {"ok": True, "decision": report["decision"], "counts": report["counts"], "reportSha256": sha256_file(path)}


def verify_shard(path: Path) -> dict[str, Any]:
    shard = json.loads(path.read_text(encoding="utf-8"))
    review_path = Path(shard["reviewReport"])
    if sha256_file(review_path) != shard["reviewReportSha256"]:
        raise ValueError("分片未绑定当前全量审核报告")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    start = int(shard["range"]["startOneBased"]) - 1
    end = int(shard["range"]["endOneBased"])
    expected = [row["id"] for row in review["records"][start:end]]
    rows = shard["decisions"]
    if [row["id"] for row in rows] != expected:
        raise ValueError("分片裁决身份或顺序与全量报告不一致")
    allowed = {"pass", "oversegmented", "undersegmented", "mixed_error", "ambiguous_source"}
    for row in rows:
        if row["verdict"] not in allowed or set(row["regions"]) != {"root", "leftSide", "rightSide", "tip"}:
            raise ValueError(f"非法分片裁决：{row['id']}")
    counts = {name: sum(row["verdict"] == name for row in rows) for name in sorted(allowed)}
    return {"ok": True, "decision": "verified_review_shard", "range": shard["range"], "counts": counts, "reportSha256": sha256_file(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    parser.add_argument("--review-dir")
    parser.add_argument("--decisions")
    parser.add_argument("--final-output")
    parser.add_argument("--verify-final")
    parser.add_argument("--verify-shard")
    parser.add_argument("--final-review-report")
    parser.add_argument("--correction-manifest-output")
    parser.add_argument("--verify-correction-manifest")
    args = parser.parse_args()
    if args.verify_correction_manifest:
        print(json.dumps(verify_correction_manifest(Path(args.verify_correction_manifest).resolve()), ensure_ascii=False))
        return 0
    if args.final_review_report or args.correction_manifest_output:
        if not args.final_review_report or not args.correction_manifest_output:
            raise ValueError("修正清单模式需要--final-review-report和--correction-manifest-output")
        report = build_correction_manifest(Path(args.final_review_report).resolve(), Path(args.correction_manifest_output).resolve())
        print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
        return 0
    if args.verify_shard:
        print(json.dumps(verify_shard(Path(args.verify_shard).resolve()), ensure_ascii=False))
        return 0
    if args.verify_final:
        print(json.dumps(verify_final(Path(args.verify_final).resolve()), ensure_ascii=False))
        return 0
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if args.review_dir or args.decisions or args.final_output:
        if not args.review_dir or not args.decisions or not args.final_output:
            raise ValueError("最终裁决模式需要--review-dir、--decisions和--final-output")
        report = finalize(Path(args.review_dir).resolve(), Path(args.decisions).resolve(), Path(args.final_output).resolve())
        print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "systematicIssueCodes": report["systematicIssueCodes"]}, ensure_ascii=False))
        return 0
    if not args.plan or not args.output_dir:
        raise ValueError("构建模式需要--plan和--output-dir")
    plan_path = Path(args.plan).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source_report = json.loads(Path(plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    install_guard, remove_caches = load_guards()
    install_guard()
    remove_caches(source_root)
    try:
        report = build(plan_path, Path(args.output_dir).resolve())
    finally:
        remove_caches(source_root)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "reconstruction": report["reconstruction"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
