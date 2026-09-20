#!/usr/bin/env python3
"""构建 cycle016 MediaPipe+YOLO 固定规则 ROI 召回浏览器审计页。

该工具只读取 clean98 已物化标签与既有质量报告，生成浏览器审计清单；
不修改证据数据，不生成训练真值，也不产生候选模型。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote


def load_training_guards() -> tuple[Any, Any]:
    training_script = Path(__file__).resolve().with_name("train-yolo-seg.py")
    spec = importlib.util.spec_from_file_location("nail_texture_train_yolo_seg", training_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载只读图片守卫：{training_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.install_read_only_ultralytics_image_check, module.remove_ultralytics_label_caches


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path: Path, text: str) -> None:
    if path.exists():
        raise ValueError(f"输出已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_polygons(label_path: Path) -> list[list[list[float]]]:
    polygons: list[list[list[float]]] = []
    for line_number, raw in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        values = raw.strip().split()
        if not values:
            continue
        if len(values) < 7 or (len(values) - 1) % 2:
            raise ValueError(f"非法YOLO分割标签：{label_path}:{line_number}")
        coordinates = [float(value) for value in values[1:]]
        polygon = [[coordinates[index], coordinates[index + 1]] for index in range(0, len(coordinates), 2)]
        polygons.append(polygon)
    return polygons


def url_for_image(workspace_parent: Path, image_path: Path) -> str:
    relative = image_path.resolve().relative_to(workspace_parent.resolve()).as_posix()
    return "/" + quote(relative, safe="/-._~")


def build_manifest(dataset_root: Path, quality_report: Path, workspace_parent: Path) -> dict[str, Any]:
    report = json.loads(quality_report.read_text(encoding="utf-8"))
    images_by_stem = {path.stem: path for path in (dataset_root / "images" / "val").iterdir() if path.is_file()}
    items: list[dict[str, Any]] = []
    label_hashes: list[str] = []
    for row in report["images"]:
        if int(row["truthCount"]) == 0:
            continue
        stem = str(row["stem"])
        image_path = images_by_stem.get(stem)
        if image_path is None:
            raise ValueError(f"质量报告图片未在clean98物化目录找到：{stem}")
        label_path = dataset_root / "labels" / "val" / f"{stem}.txt"
        polygons = parse_polygons(label_path)
        if len(polygons) != int(row["truthCount"]):
            raise ValueError(f"真值数量不一致：{stem}")
        label_hashes.append(f"{stem}:{sha256_file(label_path)}")
        items.append(
            {
                "stem": stem,
                "imageUrl": url_for_image(workspace_parent, image_path),
                "truthPolygons": polygons,
                "yoloMatchedTruthIndices": sorted(int(match["truthIndex"]) for match in row["matchedInstances"]),
            }
        )
    if len(items) != int(report["summary"]["positiveImages"]):
        raise ValueError("正样本图片数量与质量报告不一致")
    return {
        "schemaVersion": 1,
        "contract": {
            "maxNumHands": 2,
            "modelComplexity": 1,
            "minDetectionConfidence": 0.35,
            "minTrackingConfidence": 0.35,
            "roiHalfLengthFactor": 1.25,
            "roiHalfWidthFactor": 0.95,
            "roiCenterBackoffFactor": 0.18,
            "truthBoxCoverageGate": 0.98,
            "candidateCap": 10,
        },
        "inputs": {
            "datasetRoot": str(dataset_root.resolve()),
            "qualityReportPath": str(quality_report.resolve()),
            "qualityReportSha256": sha256_file(quality_report),
            "labelAggregateSha256": hashlib.sha256("\n".join(sorted(label_hashes)).encode("utf-8")).hexdigest(),
        },
        "expected": {
            "positiveImages": len(items),
            "truthInstances": sum(len(item["truthPolygons"]) for item in items),
            "yoloMatchedInstances": sum(len(item["yoloMatchedTruthIndices"]) for item in items),
        },
        "items": items,
    }


def build_html(manifest: dict[str, Any]) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<meta charset=\"utf-8\">
<title>cycle016 MediaPipe ROI audit</title>
<pre id=\"output\">running</pre>
<script src=\"/JiaRu/public/vendor/mediapipe/hands/hands.js\"></script>
<script>
const manifest = {manifest_json};
const contract = manifest.contract;
const output = document.getElementById('output');
const tips = [4, 8, 12, 16, 20];
const dips = [3, 7, 11, 15, 19];
const pips = [2, 6, 10, 14, 18];

function loadImage(url) {{
  return new Promise((resolve, reject) => {{
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`image load failed: ${{url}}`));
    image.src = url;
  }});
}}

function candidateFromFinger(landmarks, finger) {{
  const tip = landmarks[tips[finger]];
  const dip = landmarks[dips[finger]];
  const pip = landmarks[pips[finger]];
  const ux = tip.x - dip.x;
  const uy = tip.y - dip.y;
  const first = Math.hypot(ux, uy);
  const second = Math.hypot(dip.x - pip.x, dip.y - pip.y);
  const length = Math.max(first, second, 0.001);
  const cx = tip.x - contract.roiCenterBackoffFactor * ux;
  const cy = tip.y - contract.roiCenterBackoffFactor * uy;
  const halfLength = contract.roiHalfLengthFactor * length;
  const halfWidth = contract.roiHalfWidthFactor * length;
  const norm = Math.max(first, 0.001);
  const ax = ux / norm;
  const ay = uy / norm;
  const bx = -ay;
  const by = ax;
  const corners = [
    [cx + ax * halfLength + bx * halfWidth, cy + ay * halfLength + by * halfWidth],
    [cx + ax * halfLength - bx * halfWidth, cy + ay * halfLength - by * halfWidth],
    [cx - ax * halfLength + bx * halfWidth, cy - ay * halfLength + by * halfWidth],
    [cx - ax * halfLength - bx * halfWidth, cy - ay * halfLength - by * halfWidth],
  ];
  return {{
    x1: Math.max(0, Math.min(...corners.map(point => point[0]))),
    y1: Math.max(0, Math.min(...corners.map(point => point[1]))),
    x2: Math.min(1, Math.max(...corners.map(point => point[0]))),
    y2: Math.min(1, Math.max(...corners.map(point => point[1]))),
  }};
}}

function truthBox(polygon) {{
  return {{
    x1: Math.min(...polygon.map(point => point[0])),
    y1: Math.min(...polygon.map(point => point[1])),
    x2: Math.max(...polygon.map(point => point[0])),
    y2: Math.max(...polygon.map(point => point[1])),
  }};
}}

function coverage(truth, candidate) {{
  const area = Math.max(0, truth.x2 - truth.x1) * Math.max(0, truth.y2 - truth.y1);
  const intersection = Math.max(0, Math.min(truth.x2, candidate.x2) - Math.max(truth.x1, candidate.x1))
    * Math.max(0, Math.min(truth.y2, candidate.y2) - Math.max(truth.y1, candidate.y1));
  return area > 0 ? intersection / area : 0;
}}

let pendingResolve;
const hands = new Hands({{locateFile: file => `/JiaRu/public/vendor/mediapipe/hands/${{file}}`}});
hands.setOptions({{
  maxNumHands: contract.maxNumHands,
  modelComplexity: contract.modelComplexity,
  minDetectionConfidence: contract.minDetectionConfidence,
  minTrackingConfidence: contract.minTrackingConfidence,
  selfieMode: false,
}});
hands.onResults(results => {{
  if (pendingResolve) {{
    const resolve = pendingResolve;
    pendingResolve = null;
    resolve(results);
  }}
}});

async function detect(image) {{
  const resultPromise = new Promise(resolve => {{ pendingResolve = resolve; }});
  await hands.send({{image}});
  return await resultPromise;
}}

async function run() {{
  const started = performance.now();
  const items = [];
  let mediaPipeCovered = 0;
  let unionCovered = 0;
  let allUnionCoveredImages = 0;
  let detectedHands = 0;
  let maximumCandidates = 0;
  for (let index = 0; index < manifest.items.length; index += 1) {{
    const item = manifest.items[index];
    output.textContent = `running ${{index + 1}}/${{manifest.items.length}} ${{item.stem}}`;
    const image = await loadImage(item.imageUrl);
    const results = await detect(image);
    const handsFound = results.multiHandLandmarks || [];
    detectedHands += handsFound.length;
    const candidates = handsFound.flatMap(landmarks => tips.map((_, finger) => candidateFromFinger(landmarks, finger)));
    maximumCandidates = Math.max(maximumCandidates, candidates.length);
    const mediaPipeIndices = [];
    const mediaPipeCoverage = [];
    item.truthPolygons.forEach((polygon, truthOffset) => {{
      const best = candidates.reduce((value, candidate) => Math.max(value, coverage(truthBox(polygon), candidate)), 0);
      mediaPipeCoverage.push(Number(best.toFixed(6)));
      if (best >= contract.truthBoxCoverageGate) mediaPipeIndices.push(truthOffset + 1);
    }});
    const union = [...new Set([...item.yoloMatchedTruthIndices, ...mediaPipeIndices])].sort((a, b) => a - b);
    mediaPipeCovered += mediaPipeIndices.length;
    unionCovered += union.length;
    if (union.length === item.truthPolygons.length) allUnionCoveredImages += 1;
    items.push({{
      stem: item.stem,
      truthCount: item.truthPolygons.length,
      detectedHands: handsFound.length,
      candidateCount: candidates.length,
      yoloMatchedTruthIndices: item.yoloMatchedTruthIndices,
      mediaPipeCoveredTruthIndices: mediaPipeIndices,
      unionCoveredTruthIndices: union,
      mediaPipeCoverage,
      unionMissingTruthIndices: item.truthPolygons.map((_, offset) => offset + 1).filter(value => !union.includes(value)),
    }});
  }}
  const truth = manifest.expected.truthInstances;
  const result = {{
    schemaVersion: 1,
    ok: unionCovered === truth && maximumCandidates <= contract.candidateCap,
    decision: unionCovered === truth && maximumCandidates <= contract.candidateCap
      ? 'stage_a_fixed_union_reachability_pass'
      : 'stage_a_fixed_union_reachability_fail',
    manifest,
    browser: {{userAgent: navigator.userAgent, webgpuExposed: Boolean(navigator.gpu)}},
    summary: {{
      positiveImages: manifest.items.length,
      truthInstances: truth,
      yoloMatchedInstances: manifest.expected.yoloMatchedInstances,
      yoloRecall: manifest.expected.yoloMatchedInstances / truth,
      mediaPipeCoveredInstances: mediaPipeCovered,
      mediaPipeRecall: mediaPipeCovered / truth,
      unionCoveredInstances: unionCovered,
      unionRecall: unionCovered / truth,
      allUnionCoveredImages,
      allUnionCoveredImageRate: allUnionCoveredImages / manifest.items.length,
      detectedHands,
      maximumCandidates,
      elapsedMilliseconds: performance.now() - started,
    }},
    failures: items.filter(item => item.unionMissingTruthIndices.length > 0),
    items,
  }};
  window.__cycle016Audit = result;
  output.textContent = JSON.stringify(result, null, 2);
}}

run().catch(error => {{
  const failure = {{schemaVersion: 1, ok: false, decision: 'runtime_error', error: String(error), stack: error.stack}};
  window.__cycle016Audit = failure;
  output.textContent = JSON.stringify(failure, null, 2);
}});
</script>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--quality-report", required=True)
    parser.add_argument("--workspace-parent", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    dataset_root = Path(args.dataset_root).resolve()
    quality_report = Path(args.quality_report).resolve()
    output = Path(args.output).resolve()
    install_guard, remove_caches = load_training_guards()
    install_guard()
    remove_caches(dataset_root)
    try:
        manifest = build_manifest(dataset_root, quality_report, Path(args.workspace_parent).resolve())
        write_atomic(output, build_html(manifest))
    finally:
        remove_caches(dataset_root)
    print(
        json.dumps(
            {
                "ok": True,
                "decision": "browser_audit_harness_built",
                "output": str(output),
                "outputSha256": sha256_file(output),
                "expected": manifest["expected"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
