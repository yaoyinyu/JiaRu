#!/usr/bin/env python3
"""循环094保真审计：把运行时算子直接作用在 **Stage B 原生半径** 上，重测严格联合。

动机：093 的 420 是在「从预测 mask 重新拟合的轮廓半径」上测得的代理指标，重拟合本身
有约 0.5px 外扩（重建 IoU 仅 0.998）。而运行时平滑的是模型自己的 radius 输出。两者不是
同一个向量，因此必须单独判定：原生半径上是否仍有增益。

口径：
- 原生解码 `float32(radius[bin]) − distance ≥ 0`（与 codec / TS radialMaskLogits 一致）。
- 平滑算子直接复用 `export-runtime-radius-smoothing-parity-fixture.py` 的
  `smooth_like_runtime`（已与 TS 逐位对拍的运行时实现），不用 093 的 Python 变体。
- 保真门：①原生解码必须与评估存下的 `masksPacked` 逐像素相同；②基线严格联合必须复现 248。
只读冻结证据；不改模型、不改门、不产生新标注。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(r"E:\AI Project\Codex\JiaRu")
EVAL = ROOT / "model/reviews/cycle016-wevis-real-material-v1/batch037/real-only100-neighborhood90-side634-evaluation-v1"
CODEC = ROOT / "model/training/radial-raw-codec.py"
METRICS = ROOT / "model/training/audit-development-cycle-092-contour-smoothing-prior.py"
EXPORTER = ROOT / "model/training/export-runtime-radius-smoothing-parity-fixture.py"
OUTPUT = ROOT / "model/reports/cycle094-native-radius-smoothing-v1/report.json"

GATE = {"maskIoU": 0.75, "boundaryIoU": 0.75, "boundaryF1": 0.9}
BASELINE_JOINT = 248
FROZEN = {
    "report": "161f18447bff",
    "codec": "radial-raw-codec.py",
}


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    import os

    os.close(descriptor)
    temp_path = Path(temporary)
    try:
        temp_path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def decode(radius: np.ndarray, bins: np.ndarray, distance: np.ndarray) -> np.ndarray:
    """运行时口径：float32 相减后与 0 比较。"""
    values = radius[bins].astype(np.float32)
    return (values - distance).astype(np.float32) >= np.float32(0.0)


def main() -> None:
    metrics = load(METRICS, "cycle092_metrics")
    codec = load(CODEC, "radial_raw_codec")
    exporter = load(EXPORTER, "runtime_exporter")

    report = json.loads((EVAL / "report.json").read_text(encoding="utf-8"))
    plan = json.loads((EVAL / "plan.json").read_text(encoding="utf-8"))
    execution = json.loads((EVAL / "execution.json").read_text(encoding="utf-8"))
    if sha256_bytes((EVAL / "report.json").read_bytes())[:12] != FROZEN["report"]:
        raise ValueError("评估报告哈希漂移")

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    for item in plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))

    raw_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for item in plan["inputs"]:
        raw_by_key[(int(item["sourceOrdinal"]), int(item["candidateIndex"]))] = item
    execution_by_ordinal: dict[int, dict[str, Any]] = {}
    for record in execution["records"]:
        execution_by_ordinal[int(record["ordinal"])] = record

    per_nail: list[dict[str, Any]] = []
    fidelity_mismatch = 0
    failures: list[str] = []
    skipped = 0
    smoothed_applied = 0

    for index, record in enumerate(report["records"]):
        source_ordinal = index + 1
        bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in bundle["maskShape"])
        predictions = metrics.unpack_bits(bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]

        payloads = []
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                skipped += 1
                continue
            payloads.append((item, payload))

        for truth_index, (item, payload) in enumerate(payloads):
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = metrics.unpack_bits(payload["truthPacked"], payload_shape)

            scores = [metrics.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            stored_mask = predictions[best]

            key = (source_ordinal, best + 1)
            if key not in raw_by_key:
                failures.append(f"缺失候选输入：source {source_ordinal} cand {best + 1}")
                continue
            candidate_input = raw_by_key[key]
            if int(candidate_input["ordinal"]) not in execution_by_ordinal:
                failures.append(f"缺失 raw：ordinal {candidate_input['ordinal']}")
                continue
            arrays = np.load(Path(candidate_input["arrays"]["path"]))
            # codec 要求 int32 2D 原生 bins（形状即 ROI），不要转成 1D/64 位
            bins = arrays["angleBins"]
            distance = arrays["distance"]
            identity = {
                "ordinal": candidate_input["ordinal"],
                "identity": candidate_input["identity"],
                "candidateIndex": candidate_input["candidateIndex"],
                "crop": candidate_input["crop"],
            }
            raw_path = Path(execution_by_ordinal[int(candidate_input["ordinal"])]["raw"]["path"])
            radius_mask, presence, radius = codec.read(raw_path, bins, distance, identity)

            native_roi = decode(radius, bins, distance)
            native = np.zeros((height, width), dtype=bool)
            native[crop[1]:crop[3], crop[0]:crop[2]] = native_roi
            if not np.array_equal(native, stored_mask):
                fidelity_mismatch += 1

            base_iou = metrics.mask_iou(truth, native)
            base_biou, base_bf1 = metrics.boundary_metrics(truth, native, 2)
            base_joint = base_iou >= GATE["maskIoU"] and base_biou >= GATE["boundaryIoU"] and base_bf1 >= GATE["boundaryF1"]

            smoothed = exporter.smooth_like_runtime(np.float32(radius), bins, distance)
            after_roi = decode(np.float32(smoothed["radius"]), bins, distance)
            after = np.zeros((height, width), dtype=bool)
            after[crop[1]:crop[3], crop[0]:crop[2]] = after_roi
            after_iou = metrics.mask_iou(truth, after)
            after_biou, after_bf1 = metrics.boundary_metrics(truth, after, 2)
            after_joint = after_iou >= GATE["maskIoU"] and after_biou >= GATE["boundaryIoU"] and after_bf1 >= GATE["boundaryF1"]
            if smoothed["applied"]:
                smoothed_applied += 1

            per_nail.append(
                {
                    "sourceOrdinal": source_ordinal,
                    "truthIndex": truth_index + 1,
                    "fileName": record["identity"]["fileName"],
                    "sigma": float(smoothed["sigmaArcPixels"]),
                    "applied": bool(smoothed["applied"]),
                    "base": {"maskIoU": base_iou, "boundaryIoU": base_biou, "boundaryF1": base_bf1, "joint": bool(base_joint)},
                    "after": {"maskIoU": after_iou, "boundaryIoU": after_biou, "boundaryF1": after_bf1, "joint": bool(after_joint)},
                }
            )

    total = len(per_nail)
    base_joint = sum(1 for row in per_nail if row["base"]["joint"])
    after_joint = sum(1 for row in per_nail if row["after"]["joint"])
    gained = sum(1 for row in per_nail if row["after"]["joint"] and not row["base"]["joint"])
    lost = sum(1 for row in per_nail if row["base"]["joint"] and not row["after"]["joint"])
    mean = lambda key: sum(row["after"][key] for row in per_nail) / max(1, total)
    mean_base = lambda key: sum(row["base"][key] for row in per_nail) / max(1, total)

    report_value = {
        "schemaVersion": 1,
        "ok": bool(fidelity_mismatch == 0 and base_joint == BASELINE_JOINT and not failures),
        "okSemantics": "fidelity_gate_only",
        "purpose": "判定运行时平滑算子作用在 Stage B 原生半径上是否仍有严格联合增益（093 的 420 是重拟合半径上的代理指标）。",
        "gate": GATE,
        "fidelity": {
            "decodedNativeMismatchPixels": fidelity_mismatch,
            "baselineJoint": base_joint,
            "baselineJointExpected": BASELINE_JOINT,
            "nails": total,
            "skippedWithoutTruth": skipped,
            "smoothedApplied": smoothed_applied,
        },
        "result": {
            "baselineJoint": base_joint,
            "smoothedJoint": after_joint,
            "gained": gained,
            "lost": lost,
            "delta": after_joint - base_joint,
            "baselineMeanMaskIoU": mean_base("maskIoU"),
            "smoothedMeanMaskIoU": mean("maskIoU"),
            "baselineMeanBoundaryIoU": mean_base("boundaryIoU"),
            "smoothedMeanBoundaryIoU": mean("boundaryIoU"),
            "baselineMeanBoundaryF1": mean_base("boundaryF1"),
            "smoothedMeanBoundaryF1": mean("boundaryF1"),
        },
        "errors": failures[:20],
        "perNail": per_nail,
    }
    write_atomic(OUTPUT, report_value)
    print(
        json.dumps(
            {
                "fidelity": report_value["fidelity"],
                "result": report_value["result"],
                "ok": report_value["ok"],
                "output": str(OUTPUT),
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
