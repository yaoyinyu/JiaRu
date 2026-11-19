#!/usr/bin/env python3
"""循环095：在 Stage B 原生半径上扫描 RMS 界 τ，找出真正的标定点。

094 结论：τ=0.7（在「重拟合轮廓半径」上标定）到原生半径上只有 3/634 触发平滑、增益 0。
本脚本保持算子与解码口径不变，只把 τ 扫一遍，回答「原生半径自身的抖动有多大、
要多大 τ 才既触发平滑又不损伤指标」。
只读冻结证据；不改模型、不改门。
"""

from __future__ import annotations

import importlib.util
import json
import math
import tempfile
import os
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(r"E:\AI Project\Codex\JiaRu")
EVAL = ROOT / "model/reviews/cycle016-wevis-real-material-v1/batch037/real-only100-neighborhood90-side634-evaluation-v1"
CODEC = ROOT / "model/training/radial-raw-codec.py"
METRICS = ROOT / "model/training/audit-development-cycle-092-contour-smoothing-prior.py"
EXPORTER = ROOT / "model/training/export-runtime-radius-smoothing-parity-fixture.py"
OUTPUT = ROOT / "model/reports/cycle095-native-radius-tau-sweep-v1/report.json"

GATE = {"maskIoU": 0.75, "boundaryIoU": 0.75, "boundaryF1": 0.9}
TAUS = [0.7, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode(radius: np.ndarray, bins: np.ndarray, distance: np.ndarray) -> np.ndarray:
    values = radius[bins].astype(np.float32)
    return (values - distance).astype(np.float32) >= np.float32(0.0)


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temp_path = Path(temporary)
    try:
        temp_path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> None:
    metrics = load(METRICS, "cycle092_metrics")
    codec = load(CODEC, "radial_raw_codec")
    exporter = load(EXPORTER, "runtime_exporter")

    report = json.loads((EVAL / "report.json").read_text(encoding="utf-8"))
    plan = json.loads((EVAL / "plan.json").read_text(encoding="utf-8"))
    execution = json.loads((EVAL / "execution.json").read_text(encoding="utf-8"))

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    raw_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for item in plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
        raw_by_key[(int(item["sourceOrdinal"]), int(item["candidateIndex"]))] = item
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))
    execution_by_ordinal = {int(record["ordinal"]): record for record in execution["records"]}

    # 阶段一：把 634 甲的半径、roi 几何、真值一次性装进内存
    nails: list[dict[str, Any]] = []
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
                continue
            payloads.append((item, payload))

        for truth_index, (item, payload) in enumerate(payloads):
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = metrics.unpack_bits(payload["truthPacked"], payload_shape)

            scores = [metrics.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            candidate_input = raw_by_key[(source_ordinal, best + 1)]
            arrays = np.load(Path(candidate_input["arrays"]["path"]))
            bins = arrays["angleBins"]
            distance = arrays["distance"]
            identity = {
                "ordinal": candidate_input["ordinal"],
                "identity": candidate_input["identity"],
                "candidateIndex": candidate_input["candidateIndex"],
                "crop": candidate_input["crop"],
            }
            _, _, radius = codec.read(
                Path(execution_by_ordinal[int(candidate_input["ordinal"])]["raw"]["path"]), bins, distance, identity
            )

            native = np.zeros((height, width), dtype=bool)
            native[crop[1]:crop[3], crop[0]:crop[2]] = decode(radius, bins, distance)
            base_iou = metrics.mask_iou(truth, native)
            base_biou, base_bf1 = metrics.boundary_metrics(truth, native, 2)
            base_joint = base_iou >= GATE["maskIoU"] and base_biou >= GATE["boundaryIoU"] and base_bf1 >= GATE["boundaryF1"]

            nails.append(
                {
                    "sourceOrdinal": source_ordinal,
                    "truthIndex": truth_index + 1,
                    "truth": truth,
                    "crop": crop,
                    "frame": (height, width),
                    "bins": bins,
                    "distance": distance,
                    "radius": np.float32(radius),
                    "native": native,
                    "base": (base_iou, base_biou, base_bf1, bool(base_joint)),
                }
            )
    print(json.dumps({"stage": "loaded", "nails": len(nails)}), flush=True)

    rows = []
    for tau in TAUS:
        exporter.DEVIATION_RMS_ARC = tau
        applied = 0
        gained = lost = joint = 0
        sum_iou = sum_biou = sum_bf1 = 0.0
        for nail in nails:
            smoothed = exporter.smooth_like_runtime(nail["radius"], nail["bins"], nail["distance"])
            if smoothed["applied"]:
                applied += 1
            crop = nail["crop"]
            frame = nail["frame"]
            after = np.zeros(frame, dtype=bool)
            after[crop[1]:crop[3], crop[0]:crop[2]] = decode(np.float32(smoothed["radius"]), nail["bins"], nail["distance"])
            iou = metrics.mask_iou(nail["truth"], after)
            biou, bf1 = metrics.boundary_metrics(nail["truth"], after, 2)
            is_joint = iou >= GATE["maskIoU"] and biou >= GATE["boundaryIoU"] and bf1 >= GATE["boundaryF1"]
            if is_joint:
                joint += 1
            if is_joint and not nail["base"][3]:
                gained += 1
            if nail["base"][3] and not is_joint:
                lost += 1
            sum_iou += iou
            sum_biou += biou
            sum_bf1 += bf1
        total = len(nails)
        rows.append(
            {
                "tau": tau,
                "applied": applied,
                "joint": joint,
                "gained": gained,
                "lost": lost,
                "meanMaskIoU": sum_iou / total,
                "meanBoundaryIoU": sum_biou / total,
                "meanBoundaryF1": sum_bf1 / total,
            }
        )
        print(json.dumps(rows[-1]), flush=True)

    baseline = {
        "joint": sum(1 for nail in nails if nail["base"][3]),
        "meanMaskIoU": sum(nail["base"][0] for nail in nails) / len(nails),
        "meanBoundaryIoU": sum(nail["base"][1] for nail in nails) / len(nails),
        "meanBoundaryF1": sum(nail["base"][2] for nail in nails) / len(nails),
    }
    write_atomic(
        OUTPUT,
        {
            "schemaVersion": 1,
            "ok": True,
            "okSemantics": "diagnostic_sweep",
            "purpose": "在 Stage B 原生半径上扫描 RMS 界 τ，判定运行时平滑的真实标定点与增益。",
            "gate": GATE,
            "nails": len(nails),
            "baseline": baseline,
            "rows": rows,
        },
    )
    print(json.dumps({"baseline": baseline, "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
