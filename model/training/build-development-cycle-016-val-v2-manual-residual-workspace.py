#!/usr/bin/env python3
"""为 cycle016 val-v2 的 SAM 失败残项构建原分辨率人工多边形工作区。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_base() -> Any:
    path = Path(__file__).resolve().with_name("build-development-cycle-016-val-v2-repair-workspace.py")
    spec = importlib.util.spec_from_file_location("cycle016_val_v2_workspace", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载基础返修工作区模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bounds_for(old: np.ndarray, candidate: np.ndarray, width: int, height: int) -> list[int]:
    points = np.vstack((old, candidate))
    low, high = points.min(axis=0), points.max(axis=0)
    center = (low + high) / 2
    side = max(float(high[0] - low[0]), float(high[1] - low[1]), 32.0) * 1.75
    side = min(side, float(min(width, height)))
    rounded = max(1, int(round(side)))
    x1 = min(max(0, int(round(center[0] - side / 2))), max(0, width - rounded))
    y1 = min(max(0, int(round(center[1] - side / 2))), max(0, height - rounded))
    return [x1, y1, min(width, x1 + rounded), min(height, y1 + rounded)]


def write_assets(image: Image.Image, old: np.ndarray, candidate: np.ndarray, box: list[int], raw: Path, overlay: Path) -> None:
    x1, y1, x2, y2 = box
    crop = image.crop((x1, y1, x2, y2)).convert("RGB")
    crop.save(raw, format="PNG", optimize=True)
    drawn = crop.copy()
    painter = ImageDraw.Draw(drawn, "RGBA")
    old_local = [(float(x - x1), float(y - y1)) for x, y in old]
    candidate_local = [(float(x - x1), float(y - y1)) for x, y in candidate]
    painter.polygon(old_local, fill=(255, 40, 40, 25), outline=(255, 40, 40, 255), width=3)
    painter.polygon(candidate_local, fill=(20, 230, 100, 25), outline=(20, 230, 100, 255), width=3)
    drawn.save(overlay, format="PNG", optimize=True)


def aggregate_assets(root: Path) -> tuple[str, int]:
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "workspace-report.json"):
        rows.append(f"{path.relative_to(root).as_posix()}\t{sha256_file(path)}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(), len(rows)


def build(frozen_path: Path, base_workspace_report_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    base_report = json.loads(base_workspace_report_path.read_text(encoding="utf-8"))
    if frozen.get("decision") != "sam_visual_review_frozen_manual_residual_required":
        raise ValueError("SAM视觉裁决尚未冻结")
    if sha256_file(Path(frozen["inputs"]["reviewReport"]["path"])) != frozen["inputs"]["reviewReport"]["sha256"]:
        raise ValueError("SAM审核报告哈希漂移")
    if sha256_file(Path(frozen["inputs"]["decisions"]["path"])) != frozen["inputs"]["decisions"]["sha256"]:
        raise ValueError("SAM裁决哈希漂移")
    if sha256_file(base_workspace_report_path) != base_report.get("selfSha256", sha256_file(base_workspace_report_path)):
        raise ValueError("基础工作区报告自绑定异常")
    base_editor_path = Path(base_report["editorData"]["path"])
    if sha256_file(base_editor_path) != base_report["editorData"]["sha256"]:
        raise ValueError("基础编辑器数据哈希漂移")
    base_editor = json.loads(base_editor_path.read_text(encoding="utf-8"))
    old_by_id = {row["id"]: row for row in base_editor["items"]}
    manual = [row for row in frozen["records"] if row["verdict"] == "manual_repair"]
    accepted = [row for row in frozen["records"] if row["verdict"] == "accept_sam"]
    if len(manual) != frozen["counts"]["manualRepair"] or len(accepted) != frozen["counts"]["acceptSam"]:
        raise ValueError("SAM冻结报告计数不一致")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    (temporary / "assets").mkdir()
    editor_items = []
    copied_sources: dict[str, str] = {}
    try:
        for row in manual:
            old_item = old_by_id[row["id"]]
            image_path = Path(row["sourceImage"])
            label_path = Path(row["sourceLabel"])
            if sha256_file(image_path) != row["sourceImageSha256"] or sha256_file(label_path) != row["sourceLabelSha256"]:
                raise ValueError(f"源图或标签哈希漂移：{row['id']}")
            old = np.asarray([[float(p["x"]), float(p["y"])] for p in old_item["originalPolygon"]], dtype=np.float64)
            candidate = np.asarray([[float(p["x"]), float(p["y"])] for p in row["candidatePolygon"]], dtype=np.float64)
            with Image.open(image_path) as opened:
                image = opened.convert("RGB")
            width, height = image.size
            box = bounds_for(old, candidate, width, height)
            raw_rel = f"assets/{row['id']}-raw.png"
            overlay_rel = f"assets/{row['id']}-old-red-sam-green.png"
            write_assets(image, old, candidate, box, temporary / raw_rel, temporary / overlay_rel)
            source_key = row["sourceImageSha256"]
            if source_key not in copied_sources:
                source_rel = f"assets/source-{source_key[:16]}{image_path.suffix.lower()}"
                shutil.copyfile(image_path, temporary / source_rel)
                copied_sources[source_key] = source_rel
            editor_items.append({
                "id": row["id"], "sourceFileName": row["sourceFileName"], "sourceGroup": row["sourceGroup"],
                "truthIndex": row["truthIndex"], "originalVerdict": "manual_residual_after_single_sam_attempt",
                "issueCodes": old_item["issueCodes"], "imageWidth": width, "imageHeight": height,
                "sourceImageSha256": row["sourceImageSha256"], "sourceLabelSha256": row["sourceLabelSha256"],
                "cropBox": box,
                "originalPolygon": row["candidatePolygon"],
                "preSamOriginalPolygon": old_item["originalPolygon"],
                "rawAsset": raw_rel, "overlayAsset": overlay_rel, "sourceImageAsset": copied_sources[source_key],
                "status": "pending_original_resolution_manual_repair", "samReviewNotes": row["notes"],
            })
        accepted_payload = {
            "schemaVersion": 1,
            "input": {"frozenSamReview": {"path": str(frozen_path), "sha256": sha256_file(frozen_path)}},
            "decision": "sam_candidates_visually_accepted_pending_full_v2_review",
            "trainingUse": "prohibited_until_v2_full_review_pass",
            "count": len(accepted),
            "items": accepted,
        }
        accepted_path = temporary / "accepted-sam-candidates.json"
        accepted_path.write_text(json.dumps(accepted_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        data = {
            "schemaVersion": 1,
            "inputs": {
                "frozenSamReview": {"path": str(frozen_path), "sha256": sha256_file(frozen_path)},
                "baseWorkspaceReport": {"path": str(base_workspace_report_path), "sha256": sha256_file(base_workspace_report_path)},
            },
            "decision": "manual_residual_candidates_pending_review",
            "trainingUse": "prohibited_until_v2_full_review_pass",
            "counts": {"repairInstances": len(editor_items), "sourceImages": len(copied_sources)},
            "items": editor_items,
        }
        editor_path = temporary / "editor-data.json"
        editor_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        base = load_base()
        editor_html = base.EDITOR_HTML
        editor_html = editor_html.replace("cycle016 val-v2 polygon repair", "cycle016 val-v2 manual residual repair")
        editor_html = editor_html.replace("cycle016-val-v2-repair-decisions-v1", "cycle016-val-v2-manual-residual-decisions-v1")
        editor_html = editor_html.replace("`${idx+1}/57 ${it.id}`", "`${idx+1}/${data.items.length} ${it.id}`")
        editor_html = editor_html.replace("repair-decisions-v1.json", "manual-residual-decisions-v1.json")
        editor_html = editor_html.replace('<button id="reset">重置</button>', '<button id="reset">重置</button><button id="redraw">重新描边</button>')
        editor_html = editor_html.replace("let data,idx=0,img=new Image(),pts=[],history=[],drag=-1,ctx,canvas,scale=1;", "let data,idx=0,img=new Image(),pts=[],history=[],drag=-1,ctx,canvas,scale=1,drawing=false;")
        editor_html = editor_html.replace("function load(i){idx=", "function load(i){drawing=false;idx=")
        editor_html = editor_html.replace("canvas.onclick=e=>{if(e.detail!==1)return;", "canvas.onclick=e=>{if(e.detail!==1)return;if(drawing){let p=pos(e),it=data.items[idx];pts.push({x:Math.max(0,Math.min(it.imageWidth-1,p.x/scale+it.cropBox[0])),y:Math.max(0,Math.min(it.imageHeight-1,p.y/scale+it.cropBox[1]))});persist('pending');draw();return;}")
        editor_html = editor_html.replace("document.querySelector('#pass').onclick=()=>persist('reviewed_pass');", "document.querySelector('#redraw').onclick=()=>{history.push(JSON.stringify(pts));pts=[];drawing=true;persist('pending');draw()};document.querySelector('#pass').onclick=()=>{if(pts.length<3){alert('至少需要3个节点');return}drawing=false;persist('reviewed_pass')};")
        (temporary / "editor.html").write_text(editor_html, encoding="utf-8")
        aggregate, file_count = aggregate_assets(temporary)
        report = {
            "schemaVersion": 1, "ok": True,
            "decision": "manual_residual_workspace_ready_original_resolution_edit_required",
            "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "trainingUse": "prohibited_until_v2_full_review_pass"},
            "inputs": data["inputs"], "outputDir": str(output),
            "counts": {"samAcceptedFrozen": len(accepted), "manualResidual": len(editor_items), "manualResidualSourceImages": len(copied_sources)},
            "assetsSha256": aggregate, "assetFileCount": file_count,
            "editorData": {"path": str(output / "editor-data.json"), "sha256": sha256_file(editor_path)},
            "acceptedSamCandidates": {"path": str(output / "accepted-sam-candidates.json"), "sha256": sha256_file(accepted_path)},
            "errors": [],
        }
        (temporary / "workspace-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)
        return report
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"残项工作区输入哈希漂移：{name}")
    output = Path(report["outputDir"])
    aggregate, file_count = aggregate_assets(output)
    if aggregate != report["assetsSha256"] or file_count != report["assetFileCount"]:
        raise ValueError("残项工作区资产聚合哈希漂移")
    for name in ("editorData", "acceptedSamCandidates"):
        binding = report[name]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"残项工作区文件哈希漂移：{name}")
    editor = json.loads(Path(report["editorData"]["path"]).read_text(encoding="utf-8"))
    if len(editor["items"]) != report["counts"]["manualResidual"] or len({row["id"] for row in editor["items"]}) != len(editor["items"]):
        raise ValueError("人工残项身份或数量异常")
    if any(row["status"] != "pending_original_resolution_manual_repair" for row in editor["items"]):
        raise ValueError("人工残项不得自动通过")
    return {"ok": True, "decision": "verified_manual_residual_workspace", "counts": report["counts"], "assetsSha256": aggregate, "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-sam-review")
    parser.add_argument("--base-workspace-report")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not all((args.frozen_sam_review, args.base_workspace_report, args.output_dir)):
        raise ValueError("物化模式需要--frozen-sam-review、--base-workspace-report与--output-dir")
    output = Path(args.output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build(Path(args.frozen_sam_review).resolve(), Path(args.base_workspace_report).resolve(), output)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "assetsSha256": report["assetsSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
