#!/usr/bin/env python3
"""零推理可达性判决：真值半径 vs 模型原生半径的角度域抖动差距。

目的：训练侧「半径平滑正则」能不能成立，取决于真值本身是否平滑。
若真值半径抖动 ~预测抖动，则正则项会与监督信号对抗（不可行）；
若真值明显更平滑，则差距就是可达空间，且给出目标上界。

只读冻结证据，不写任何 evidence 目录。
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(r"E:\AI Project\Codex\JiaRu")
EVAL = ROOT / "model/reviews/cycle016-wevis-real-material-v1/batch037/real-only100-neighborhood90-side634-evaluation-v1"
CODEC = ROOT / "model/training/radial-raw-codec.py"
METRICS = ROOT / "model/training/audit-development-cycle-092-contour-smoothing-prior.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jitter(vector: np.ndarray) -> dict[str, float]:
    values = vector.astype(np.float64)
    previous = np.concatenate([values[-1:], values[:-1]])
    following = np.concatenate([values[1:], values[:1]])
    first = np.abs(following - values)
    second = np.abs(previous - 2 * values + following)
    return {
        "diffStd": float(np.std(first)),
        "diffMedian": float(np.median(first)),
        "secondDiffStd": float(np.std(second)),
        "secondDiffMedian": float(np.median(second)),
    }


def main() -> None:
    metrics = load(METRICS, "cycle092_metrics")
    codec = load(CODEC, "radial_raw_codec")

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

    truth_rows: list[dict[str, float]] = []
    prediction_rows: list[dict[str, float]] = []
    margin = 12

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

        for item, payload in payloads:
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = metrics.unpack_bits(payload["truthPacked"], payload_shape)

            scores = [metrics.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            prediction = predictions[best]

            ys, xs = np.nonzero(truth)
            py, px = np.nonzero(prediction)
            if py.size == 0:
                continue
            expanded = (
                max(0, min(int(ys.min()), int(py.min())) - margin),
                min(height, max(int(ys.max()), int(py.max())) + margin + 1),
                max(0, min(int(xs.min()), int(px.min())) - margin),
                min(width, max(int(xs.max()), int(px.max())) + margin + 1),
            )
            truth_crop = truth[expanded[0]:expanded[1], expanded[2]:expanded[3]]
            try:
                truth_vector, _, _ = metrics.contour_radius(truth_crop)
            except ValueError:
                continue
            truth_rows.append(jitter(truth_vector))

            candidate_input = raw_by_key[(source_ordinal, best + 1)]
            arrays = np.load(Path(candidate_input["arrays"]["path"]))
            identity = {
                "ordinal": candidate_input["ordinal"],
                "identity": candidate_input["identity"],
                "candidateIndex": candidate_input["candidateIndex"],
                "crop": candidate_input["crop"],
            }
            _, _, radius = codec.read(
                Path(execution_by_ordinal[int(candidate_input["ordinal"])]["raw"]["path"]),
                arrays["angleBins"],
                arrays["distance"],
                identity,
            )
            prediction_rows.append(jitter(radius))

    def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
        keys = rows[0].keys()
        return {key: float(np.median([row[key] for row in rows])) for key in keys}

    truth_summary = aggregate(truth_rows)
    prediction_summary = aggregate(prediction_rows)
    result = {
        "ok": True,
        "okSemantics": "zero_inference_reachability",
        "nails": len(truth_rows),
        "truth": truth_summary,
        "prediction": prediction_summary,
        "ratioDiffStd": prediction_summary["diffStd"] / max(1e-9, truth_summary["diffStd"]),
        "gapDiffPixels": prediction_summary["diffStd"] - truth_summary["diffStd"],
        "decision": "regularization_reachable" if prediction_summary["diffStd"] > 2 * truth_summary["diffStd"] else "no_gap",
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))
    (ROOT / "output" / "cycle096-radius-jitter-reachability.json").write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    )


if __name__ == "__main__":
    main()
