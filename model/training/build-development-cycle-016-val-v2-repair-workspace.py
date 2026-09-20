#!/usr/bin/env python3
"""从冻结修正清单物化 cycle016 验证真值 v2 的隔离 polygon 返修工作区。"""

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
        result.append(np.asarray([float(value) for value in tokens[1:]], dtype=np.float64).reshape(-1, 2))
    return result


def expanded_crop(points: np.ndarray, width: int, height: int, scale: float) -> list[int]:
    low = points.min(axis=0)
    high = points.max(axis=0)
    center = (low + high) / 2
    side = max(float(high[0] - low[0]), float(high[1] - low[1])) * scale
    side = min(max(side, 32.0), float(min(width, height)))
    rounded = max(1, int(round(side)))
    x1 = min(max(0, int(round(center[0] - side / 2))), max(0, width - rounded))
    y1 = min(max(0, int(round(center[1] - side / 2))), max(0, height - rounded))
    return [x1, y1, min(width, x1 + rounded), min(height, y1 + rounded)]


def write_crop_assets(image: Image.Image, points: np.ndarray, box: list[int], raw_path: Path, overlay_path: Path) -> None:
    x1, y1, x2, y2 = box
    raw = image.crop((x1, y1, x2, y2)).convert("RGB")
    raw.save(raw_path, format="PNG", optimize=True)
    overlay = raw.copy()
    local = [(float(x - x1), float(y - y1)) for x, y in points]
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.polygon(local, fill=(255, 40, 40, 45), outline=(255, 30, 30, 255), width=3)
    for index, point in enumerate(local, start=1):
        x, y = point
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, 255), outline=(180, 0, 0, 255), width=1)
        if index == 1:
            draw.text((x + 5, y + 3), "1", fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(160, 0, 0, 255))
    overlay.save(overlay_path, format="PNG", optimize=True)


EDITOR_HTML = r'''<!doctype html>
<meta charset="utf-8"><title>cycle016 val-v2 polygon repair</title>
<style>
body{font:14px system-ui;margin:0;background:#17191d;color:#eee}header{position:sticky;top:0;background:#23262c;padding:10px;z-index:2}button,select{margin:3px;padding:7px}main{display:grid;grid-template-columns:minmax(720px,1fr) 330px;gap:12px;padding:12px}canvas{background:#000;max-width:100%;max-height:82vh;image-rendering:auto}.panel{background:#23262c;padding:12px}.bad{color:#ff8585}.ok{color:#7ee787}pre{white-space:pre-wrap}.context{max-width:100%;max-height:230px}
</style>
<header><select id="pick"></select><button id="prev">上一枚</button><button id="next">下一枚</button><button id="undo">撤销</button><button id="reset">重置</button><button id="pass">标记视觉通过</button><button id="pending">恢复待审</button><button id="export">导出裁决 JSON</button></header>
<main><div><canvas id="canvas"></canvas><p>拖动节点；单击边界附近插点；右键删除最近节点。所有坐标按原图像素导出。</p></div><aside class="panel"><h3 id="title"></h3><div id="meta"></div><h4>全图上下文</h4><img id="context" class="context"><h4>旧边界</h4><img id="old" class="context"><pre id="state"></pre></aside></main>
<script>
let data,idx=0,img=new Image(),pts=[],history=[],drag=-1,ctx,canvas,scale=1;
const key='cycle016-val-v2-repair-decisions-v1';
const saved=()=>JSON.parse(localStorage.getItem(key)||'{}');
function persist(status){const all=saved();all[data.items[idx].id]={status:status??all[data.items[idx].id]?.status??'pending',candidatePolygon:pts.map(p=>({x:+p.x.toFixed(2),y:+p.y.toFixed(2)}))};localStorage.setItem(key,JSON.stringify(all));showState();}
function showState(){const s=saved()[data.items[idx].id]||{status:'pending'};document.querySelector('#state').textContent=`状态: ${s.status}\n节点: ${pts.length}\n完成: ${Object.values(saved()).filter(x=>x.status==='reviewed_pass').length}/${data.items.length}`;document.querySelector('#state').className=s.status==='reviewed_pass'?'ok':'bad'}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);if(!pts.length)return;ctx.beginPath();pts.forEach((p,i)=>{let x=(p.x-data.items[idx].cropBox[0])*scale,y=(p.y-data.items[idx].cropBox[1])*scale;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.closePath();ctx.fillStyle='#ff333344';ctx.fill();ctx.strokeStyle='#00ff70';ctx.lineWidth=2;ctx.stroke();pts.forEach((p,i)=>{let x=(p.x-data.items[idx].cropBox[0])*scale,y=(p.y-data.items[idx].cropBox[1])*scale;ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fillStyle=i===0?'#ff0':'#fff';ctx.fill();ctx.strokeStyle='#111';ctx.stroke()})}
function nearest(x,y){let best=-1,d=1e9;pts.forEach((p,i)=>{let dx=(p.x-data.items[idx].cropBox[0])*scale-x,dy=(p.y-data.items[idx].cropBox[1])*scale-y,q=dx*dx+dy*dy;if(q<d){d=q;best=i}});return [best,Math.sqrt(d)]}
function segDist(p,a,b){let vx=b.x-a.x,vy=b.y-a.y,wx=p.x-a.x,wy=p.y-a.y,t=Math.max(0,Math.min(1,(wx*vx+wy*vy)/(vx*vx+vy*vy||1))),dx=p.x-(a.x+t*vx),dy=p.y-(a.y+t*vy);return dx*dx+dy*dy}
function load(i){idx=(i+data.items.length)%data.items.length;const it=data.items[idx],s=saved()[it.id];pts=(s?.candidatePolygon||it.originalPolygon).map(p=>({...p}));history=[];document.querySelector('#pick').value=idx;document.querySelector('#title').textContent=`${idx+1}/57 ${it.id}`;document.querySelector('#meta').innerHTML=`<b>${it.originalVerdict}</b><br>${it.issueCodes.join(', ')}<br>${it.sourceFileName} / nail-${it.truthIndex}`;document.querySelector('#context').src=it.sourceImageAsset;document.querySelector('#old').src=it.overlayAsset;img.onload=()=>{scale=Math.min(3,Math.max(1,900/img.width));canvas.width=Math.round(img.width*scale);canvas.height=Math.round(img.height*scale);draw()};img.src=it.rawAsset;showState()}
function pos(e){const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*canvas.width/r.width,y:(e.clientY-r.top)*canvas.height/r.height}}
canvas=document.querySelector('#canvas');ctx=canvas.getContext('2d');canvas.onpointerdown=e=>{let p=pos(e),n=nearest(p.x,p.y);if(n[1]<12){drag=n[0];history.push(JSON.stringify(pts));canvas.setPointerCapture(e.pointerId)}};canvas.onpointermove=e=>{if(drag<0)return;let p=pos(e),it=data.items[idx];pts[drag]={x:Math.max(0,Math.min(it.imageWidth-1,p.x/scale+it.cropBox[0])),y:Math.max(0,Math.min(it.imageHeight-1,p.y/scale+it.cropBox[1]))};draw()};canvas.onpointerup=e=>{if(drag>=0){drag=-1;persist('pending')}};canvas.onclick=e=>{if(e.detail!==1)return;let p=pos(e),n=nearest(p.x,p.y);if(n[1]<12)return;let q={x:p.x/scale+data.items[idx].cropBox[0],y:p.y/scale+data.items[idx].cropBox[1]},best=0,d=1e99;pts.forEach((a,i)=>{let z=segDist(q,a,pts[(i+1)%pts.length]);if(z<d){d=z;best=i+1}});history.push(JSON.stringify(pts));pts.splice(best,0,q);persist('pending');draw()};canvas.oncontextmenu=e=>{e.preventDefault();let p=pos(e),n=nearest(p.x,p.y);if(n[1]<18&&pts.length>3){history.push(JSON.stringify(pts));pts.splice(n[0],1);persist('pending');draw()}};
document.querySelector('#prev').onclick=()=>load(idx-1);document.querySelector('#next').onclick=()=>load(idx+1);document.querySelector('#undo').onclick=()=>{if(history.length){pts=JSON.parse(history.pop());persist('pending');draw()}};document.querySelector('#reset').onclick=()=>{history.push(JSON.stringify(pts));pts=data.items[idx].originalPolygon.map(p=>({...p}));persist('pending');draw()};document.querySelector('#pass').onclick=()=>persist('reviewed_pass');document.querySelector('#pending').onclick=()=>persist('pending');document.querySelector('#pick').onchange=e=>load(+e.target.value);document.querySelector('#export').onclick=()=>{const all=saved(),out={schemaVersion:1,inputs:data.inputs,decision:'manual_polygon_repair_decisions',trainingUse:'prohibited_until_v2_full_review_pass',items:data.items.map(x=>({id:x.id,status:all[x.id]?.status||'pending',candidatePolygon:all[x.id]?.candidatePolygon||x.originalPolygon}))};let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,2)+'\n'],{type:'application/json'}));a.download='repair-decisions-v1.json';a.click()};
fetch('editor-data.json').then(r=>r.json()).then(x=>{data=x;let p=document.querySelector('#pick');x.items.forEach((it,i)=>p.add(new Option(`${i+1} ${it.id}`,i)));load(0)});
</script>'''


def aggregate_assets(root: Path) -> tuple[str, int]:
    rows = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file() and candidate.name != "workspace-report.json"):
        rows.append(f"{path.relative_to(root).as_posix()}\t{sha256_file(path)}")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(), len(rows)


def validate_plan_and_inputs(plan_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    bindings = (("correctionManifest", "correctionManifestSha256"), ("reviewReport", "reviewReportSha256"), ("cycle012DatasetReport", "cycle012DatasetReportSha256"))
    for name, hash_name in bindings:
        if sha256_file(Path(plan["inputs"][name])) != plan["inputs"][hash_name]:
            raise ValueError(f"输入哈希不匹配：{name}")
    manifest = json.loads(Path(plan["inputs"]["correctionManifest"]).read_text(encoding="utf-8"))
    review = json.loads(Path(plan["inputs"]["reviewReport"]).read_text(encoding="utf-8"))
    source = json.loads(Path(plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    expected = plan["expected"]
    for key in ("repairPolygonInstances", "retainInstances", "excludeSourceImageInstances", "excludedSourceImages", "excludedSourceGroups"):
        source_key = {"repairPolygonInstances":"repair_polygon", "retainInstances":"retain", "excludeSourceImageInstances":"exclude_source_image", "excludedSourceImages":"excludedSourceImages", "excludedSourceGroups":"excludedSourceGroups"}[key]
        if int(expected[key]) != int(manifest["counts"][source_key]):
            raise ValueError(f"冻结清单计数不匹配：{key}")
    if len(review["records"]) != int(expected["reviewedInstances"]):
        raise ValueError("审核报告实例数不匹配")
    if [row["id"] for row in manifest["items"]] != [row["id"] for row in review["records"]]:
        raise ValueError("冻结清单与审核报告未逐实例同构")
    return plan, manifest, review, source


def build(plan_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{output}")
    plan, manifest, review, source = validate_plan_and_inputs(plan_path)
    review_by_id = {row["id"]: row for row in review["records"]}
    source_by_key = {(row["fileName"], row["sourceGroup"]): row for row in source["records"]}
    source_root = Path(source["outputDir"])
    repair_items = [row for row in manifest["items"] if row["action"] == "repair_polygon"]
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    (temporary / "assets").mkdir()
    editor_items = []
    copied_sources: dict[str, str] = {}
    try:
        for item in repair_items:
            record = review_by_id[item["id"]]
            source_row = source_by_key[(item["sourceFileName"], item["sourceGroup"])]
            image_path = source_root / source_row["image"]
            label_path = source_root / source_row["label"]
            if sha256_file(image_path) != source_row["imageSha256"] or sha256_file(label_path) != source_row["labelSha256"]:
                raise ValueError(f"源文件哈希不匹配：{item['id']}")
            with Image.open(image_path) as opened:
                image = opened.convert("RGB")
                width, height = image.size
                polygons = parse_polygons(label_path)
                polygon = polygons[int(item["truthIndex"]) - 1] * np.asarray([width, height], dtype=np.float64)
                box = expanded_crop(polygon, width, height, float(plan["repairContract"]["cropScale"]))
                stem = item["id"]
                raw_rel = f"assets/{stem}-raw.png"
                overlay_rel = f"assets/{stem}-old-overlay.png"
                write_crop_assets(image, polygon, box, temporary / raw_rel, temporary / overlay_rel)
                if item["sourceFileName"] not in copied_sources:
                    suffix = image_path.suffix.lower()
                    source_rel = f"assets/source-{source_row['imageSha256'][:16]}{suffix}"
                    shutil.copyfile(image_path, temporary / source_rel)
                    copied_sources[item["sourceFileName"]] = source_rel
            editor_items.append({
                "id": item["id"], "sourceFileName": item["sourceFileName"], "sourceGroup": item["sourceGroup"],
                "truthIndex": item["truthIndex"], "originalVerdict": item["originalVerdict"], "issueCodes": item["issueCodes"],
                "imageWidth": width, "imageHeight": height, "sourceImageSha256": source_row["imageSha256"],
                "sourceLabelSha256": source_row["labelSha256"], "cropBox": box,
                "originalPolygon": [{"x": round(float(x), 4), "y": round(float(y), 4)} for x, y in polygon],
                "rawAsset": raw_rel, "overlayAsset": overlay_rel, "sourceImageAsset": copied_sources[item["sourceFileName"]],
                "status": "pending_original_resolution_manual_repair"
            })
        editor_data = {
            "schemaVersion": 1,
            "inputs": {
                "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
                "correctionManifest": {"path": plan["inputs"]["correctionManifest"], "sha256": plan["inputs"]["correctionManifestSha256"]},
                "reviewReport": {"path": plan["inputs"]["reviewReport"], "sha256": plan["inputs"]["reviewReportSha256"]},
                "cycle012DatasetReport": {"path": plan["inputs"]["cycle012DatasetReport"], "sha256": plan["inputs"]["cycle012DatasetReportSha256"]},
            },
            "decision": "repair_candidates_pending_manual_review", "trainingUse": plan["repairContract"]["trainingUse"],
            "counts": {"repairInstances": len(editor_items), "sourceImages": len(copied_sources)}, "items": editor_items,
        }
        (temporary / "editor-data.json").write_text(json.dumps(editor_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (temporary / "editor.html").write_text(EDITOR_HTML, encoding="utf-8")
        aggregate, file_count = aggregate_assets(temporary)
        report = {
            "schemaVersion": 1, "ok": True, "decision": "repair_workspace_ready_manual_polygon_review_required",
            "scope": {"trainingRoleOnly": True, "testOrHoldoutRead": False, "trainingUse": plan["repairContract"]["trainingUse"]},
            "inputs": {
                "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
                "correctionManifest": {"path": plan["inputs"]["correctionManifest"], "sha256": plan["inputs"]["correctionManifestSha256"]},
                "reviewReport": {"path": plan["inputs"]["reviewReport"], "sha256": plan["inputs"]["reviewReportSha256"]},
                "cycle012DatasetReport": {"path": plan["inputs"]["cycle012DatasetReport"], "sha256": plan["inputs"]["cycle012DatasetReportSha256"]},
            },
            "outputDir": str(output),
            "counts": {"repairInstances": len(editor_items), "repairSourceImages": len(copied_sources), "retainInstances": manifest["counts"]["retain"], "excludedInstances": manifest["counts"]["exclude_source_image"], "excludedSourceImages": manifest["counts"]["excludedSourceImages"], "expectedV2Instances": plan["expected"]["v2Instances"], "expectedV2SourceGroups": plan["expected"]["v2SourceGroups"]},
            "assetsSha256": aggregate, "assetFileCount": file_count,
            "editorData": {"path": str(output / "editor-data.json"), "sha256": sha256_file(temporary / "editor-data.json")},
            "repairStatus": {"pending": len(editor_items), "reviewedPass": 0}, "errors": [],
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
            raise ValueError(f"工作区输入哈希不匹配：{name}")
    output = Path(report["outputDir"])
    aggregate, file_count = aggregate_assets(output)
    if aggregate != report["assetsSha256"] or file_count != report["assetFileCount"]:
        raise ValueError("工作区资产聚合哈希不匹配")
    editor_path = output / "editor-data.json"
    if sha256_file(editor_path) != report["editorData"]["sha256"]:
        raise ValueError("编辑器数据哈希不匹配")
    data = json.loads(editor_path.read_text(encoding="utf-8"))
    if len(data["items"]) != report["counts"]["repairInstances"] or len({row["id"] for row in data["items"]}) != len(data["items"]):
        raise ValueError("返修实例数量或身份不一致")
    for item in data["items"]:
        for key in ("rawAsset", "overlayAsset", "sourceImageAsset"):
            if not (output / item[key]).is_file():
                raise ValueError(f"缺少返修资产：{item['id']} {key}")
        if item["status"] != "pending_original_resolution_manual_repair":
            raise ValueError(f"工作区不得自动批准：{item['id']}")
    return {"ok": True, "decision": "verified_repair_workspace", "counts": report["counts"], "assetsSha256": aggregate, "reportSha256": sha256_file(report_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan")
    parser.add_argument("--output-dir")
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(Path(args.verify_report).resolve()), ensure_ascii=False))
        return 0
    if not args.plan or not args.output_dir:
        raise ValueError("物化模式需要--plan与--output-dir")
    plan_path = Path(args.plan).resolve()
    output = Path(args.output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    install_guard, remove_caches = load_guards()
    install_guard()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    source_report = json.loads(Path(plan["inputs"]["cycle012DatasetReport"]).read_text(encoding="utf-8"))
    source_root = Path(source_report["outputDir"])
    remove_caches(source_root)
    try:
        report = build(plan_path, output)
    finally:
        remove_caches(source_root)
    print(json.dumps({"ok": report["ok"], "decision": report["decision"], "counts": report["counts"], "assetsSha256": report["assetsSha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
