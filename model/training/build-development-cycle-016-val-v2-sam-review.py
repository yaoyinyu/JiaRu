#!/usr/bin/env python3
"""构建 cycle016 val-v2 单次SAM返修候选的哈希绑定原分辨率审核包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_yolo(path: Path) -> list[np.ndarray]:
    polygons = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = line.strip().split()
        if not tokens:
            continue
        if len(tokens) < 7 or (len(tokens) - 1) % 2:
            raise ValueError(f"非法YOLO标签：{path}:{line_number}")
        polygons.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float64).reshape(-1, 2))
    return polygons


def candidate_points(annotation: dict[str, Any]) -> np.ndarray:
    points = np.asarray([[float(row["x"]), float(row["y"])] for row in annotation["polygon"]], dtype=np.float64)
    if len(points) < 4 or not np.isfinite(points).all():
        raise ValueError("SAM候选polygon少于4点或含非有限坐标")
    return points


def bounds_for(old: np.ndarray, new: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
    points = np.vstack((old, new))
    low, high = points.min(axis=0), points.max(axis=0)
    span = max(float(high[0] - low[0]), float(high[1] - low[1]), 32.0)
    padding = max(18.0, span * 0.35)
    x1, y1 = max(0, int(np.floor(low[0] - padding))), max(0, int(np.floor(low[1] - padding)))
    x2, y2 = min(width, int(np.ceil(high[0] + padding + 1))), min(height, int(np.ceil(high[1] + padding + 1)))
    return x1, y1, x2, y2


def draw_polygon(image: Image.Image, points: np.ndarray, box: tuple[int, int, int, int], color: tuple[int, int, int]) -> Image.Image:
    x1, y1, x2, y2 = box
    crop = image.crop(box).convert("RGB")
    local = [(float(x - x1), float(y - y1)) for x, y in points]
    draw = ImageDraw.Draw(crop, "RGBA")
    draw.polygon(local, fill=(*color, 42), outline=(*color, 255), width=3)
    return crop


def fit(image: Image.Image, width: int = 340, height: int = 340) -> Image.Image:
    scale = min(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "#101114")
    canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def panel(image: Image.Image, old: np.ndarray, new: np.ndarray, box: tuple[int, int, int, int], title: str, note: str) -> Image.Image:
    raw = fit(image.crop(box).convert("RGB"))
    old_view = fit(draw_polygon(image, old, box, (255, 45, 45)))
    new_view = fit(draw_polygon(image, new, box, (20, 230, 100)))
    canvas = Image.new("RGB", (1020, 390), "white")
    canvas.paste(raw, (0, 0)); canvas.paste(old_view, (340, 0)); canvas.paste(new_view, (680, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((4, 344), title[:145], fill="black")
    draw.text((4, 362), note[:160], fill="black")
    draw.text((4, 378), "left=raw | middle=old red | right=single SAM2.1-L candidate green", fill="black")
    return canvas


def build(plan_path: Path, prompts_path: Path, sam_report_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    sam_report = json.loads(sam_report_path.read_text(encoding="utf-8"))
    if sha256_file(Path(plan["inputs"]["workspaceReport"])) != plan["inputs"]["workspaceReportSha256"]:
        raise ValueError("工作区报告哈希漂移")
    if prompts["inputs"]["plan"]["sha256"] != sha256_file(plan_path):
        raise ValueError("提示未绑定当前计划")
    if prompts["imageCount"] != 25 or prompts["promptCount"] != 57:
        raise ValueError("提示覆盖数量不一致")
    if not sam_report.get("ok") or sam_report.get("imageCount") != 25 or sam_report.get("promptCount") != 57:
        raise ValueError("SAM运行未完整覆盖固定清单")
    if sam_report.get("boxOnlyFallbackPromptCount") != 0 or sam_report.get("errors") != []:
        raise ValueError("SAM运行存在fallback或错误")
    workspace = json.loads(Path(plan["inputs"]["workspaceReport"]).read_text(encoding="utf-8"))
    editor = json.loads(Path(plan["inputs"]["editorData"]).read_text(encoding="utf-8"))
    editor_by_id = {row["id"]: row for row in editor["items"]}
    source_report_path = Path(workspace["inputs"]["cycle012DatasetReport"]["path"])
    if sha256_file(source_report_path) != workspace["inputs"]["cycle012DatasetReport"]["sha256"]:
        raise ValueError("cycle012报告哈希漂移")
    source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source_report["records"]}
    sam_by_name = {row["fileName"]: row for row in sam_report["outputs"]}
    if len(sam_by_name) != 25:
        raise ValueError("SAM输出文件身份重复")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    (temporary / "pages").mkdir()
    records = []
    panels = []
    try:
        for prompt_image in prompts["images"]:
            file_name, source_group = prompt_image["fileName"], prompt_image["sourceGroup"]
            source_row = source_by_key[(file_name, source_group)]
            image_path, label_path = source_root / source_row["image"], source_root / source_row["label"]
            if sha256_file(image_path) != source_row["imageSha256"] or sha256_file(label_path) != source_row["labelSha256"]:
                raise ValueError(f"源图或标签哈希漂移：{file_name}")
            sam_binding = sam_by_name[file_name]
            annotation_path = Path(sam_binding["annotationPath"])
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            candidates = annotation["annotations"]
            if len(candidates) != len(prompt_image["repairIds"]):
                raise ValueError(f"SAM候选数与提示不一致：{file_name}")
            with Image.open(image_path) as opened:
                image = opened.convert("RGB")
            width, height = image.size
            source_polygons = [polygon * np.asarray([width, height], dtype=np.float64) for polygon in parse_yolo(label_path)]
            for local_index, repair_id in enumerate(prompt_image["repairIds"]):
                item = editor_by_id[repair_id]
                old = np.asarray([[float(row["x"]), float(row["y"])] for row in item["originalPolygon"]], dtype=np.float64)
                new = candidate_points(candidates[local_index])
                old_shape, new_shape = Polygon(old), Polygon(new)
                truth_index = int(item["truthIndex"])
                overlaps = []
                if new_shape.is_valid and new_shape.area > 1:
                    for other_index, other in enumerate(source_polygons, start=1):
                        if other_index == truth_index:
                            continue
                        other_shape = Polygon(other)
                        area = new_shape.intersection(other_shape).area if other_shape.is_valid else 0.0
                        if area > 0:
                            overlaps.append({"truthIndex": other_index, "areaPixels": round(area, 4)})
                intersection = old_shape.intersection(new_shape).area if old_shape.is_valid and new_shape.is_valid else 0.0
                union = old_shape.union(new_shape).area if old_shape.is_valid and new_shape.is_valid else 0.0
                metrics = {
                    "valid": bool(new_shape.is_valid and new_shape.area > 1),
                    "oldAreaPixels": round(old_shape.area, 4),
                    "candidateAreaPixels": round(new_shape.area, 4),
                    "areaRatio": round(new_shape.area / old_shape.area, 6) if old_shape.area else None,
                    "iouWithOld": round(intersection / union, 6) if union else 0.0,
                    "otherTruthOverlapCount": len(overlaps),
                    "otherTruthOverlaps": overlaps,
                }
                box = bounds_for(old, new, width, height)
                title = f"{len(records)+1:02d}/57 {repair_id} {item['originalVerdict']} issues={','.join(item['issueCodes'])}"
                note = prompt_image["reviewNotes"][local_index]
                panels.append(panel(image, old, new, box, title, note))
                records.append({
                    "id": repair_id, "sourceFileName": file_name, "sourceGroup": source_group,
                    "truthIndex": truth_index, "issueCodes": item["issueCodes"],
                    "originalVerdict": item["originalVerdict"], "reviewRegions": prompt_image["reviewRegions"][local_index],
                    "reviewNote": note, "sourceImage": str(image_path), "sourceImageSha256": source_row["imageSha256"],
                    "sourceLabel": str(label_path), "sourceLabelSha256": source_row["labelSha256"],
                    "samAnnotation": str(annotation_path), "samAnnotationSha256": sha256_file(annotation_path),
                    "candidateIndex": local_index + 1, "candidatePolygon": candidates[local_index]["polygon"],
                    "metrics": metrics, "verdict": None, "notes": "",
                })
        page_bindings = []
        for offset in range(0, len(panels), 4):
            page = Image.new("RGB", (2040, 780), "white")
            for position, item in enumerate(panels[offset:offset+4]):
                page.paste(item, ((position % 2) * 1020, (position // 2) * 390))
            page_path = temporary / "pages" / f"review-{offset // 4 + 1:02d}.png"
            page.save(page_path, format="PNG", optimize=True)
            page_bindings.append({"path": page_path.relative_to(temporary).as_posix(), "sha256": sha256_file(page_path), "recordIds": [row["id"] for row in records[offset:offset+4]]})
        counts = {
            "instances": len(records),
            "validCandidates": sum(row["metrics"]["valid"] for row in records),
            "candidatesWithOtherTruthOverlap": sum(row["metrics"]["otherTruthOverlapCount"] > 0 for row in records),
        }
        report = {
            "schemaVersion": 1, "ok": len(records) == 57,
            "decision": "sam_candidates_ready_original_resolution_manual_review_required",
            "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "trainingUse": "prohibited"},
            "inputs": {
                "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
                "prompts": {"path": str(prompts_path), "sha256": sha256_file(prompts_path)},
                "samReport": {"path": str(sam_report_path), "sha256": sha256_file(sam_report_path)},
                "workspaceReport": {"path": plan["inputs"]["workspaceReport"], "sha256": plan["inputs"]["workspaceReportSha256"]},
            },
            "counts": counts, "pages": page_bindings, "records": records,
            "allowedVerdicts": ["accept_sam", "manual_repair"],
            "stopLoss": "manual_repair verdict prohibits any additional SAM retry for that instance",
            "errors": [],
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
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"审核包输入哈希不匹配：{name}")
    for page in report["pages"]:
        if sha256_file(output / page["path"]) != page["sha256"]:
            raise ValueError(f"审核页哈希漂移：{page['path']}")
    if report["counts"]["instances"] != 57 or len(report["records"]) != 57:
        raise ValueError("审核记录不完整")
    if len({row["id"] for row in report["records"]}) != 57 or any(row["verdict"] is not None for row in report["records"]):
        raise ValueError("审核身份重复或候选被自动裁决")
    return {"ok": True, "decision": "verified_sam_candidate_review_package", "counts": report["counts"], "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--prompts")
    parser.add_argument("--sam-report")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not all((args.plan, args.prompts, args.sam_report, args.output_dir)):
        raise ValueError("构建模式需要plan、prompts、sam-report和output-dir")
    report = build(Path(args.plan).resolve(), Path(args.prompts).resolve(), Path(args.sam_report).resolve(), Path(args.output_dir).resolve())
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
