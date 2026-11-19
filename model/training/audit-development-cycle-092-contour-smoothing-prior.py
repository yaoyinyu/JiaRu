#!/usr/bin/env python3
"""循环092前零推理可达性判决：轮廓光滑性先验（角度域循环低通）天花板。

从每个冻结预测 mask 取最大外轮廓，以质心为极点拟合 2048-bin 半径向量，
沿角度做循环低通后按模型同款规则 radius[bin] >= distance 重新解码，
再与冻结真值复算同一 boundary_metrics(...,2)。只读冻结产物；不生成模型输入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

EVIDENCE_ROOT = Path(r"E:\AI Project\Codex\JiaRu\model\reviews")
ANGULAR_BINS = 2048


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"报告已存在，禁止覆盖：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def guard_output(path: Path) -> None:
    if EVIDENCE_ROOT.resolve() in path.resolve().parents:
        raise ValueError("禁止写入冻结证据目录")


def unpack_bits(packed: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    bits = np.unpackbits(packed, bitorder="little", count=int(np.prod(shape)))
    return bits.reshape(shape).astype(bool)


def boundary_metrics(truth: np.ndarray, prediction: np.ndarray, tolerance: int = 2) -> tuple[float, float]:
    kernel = np.ones((3, 3), dtype=np.uint8)
    truth_u8 = truth.astype(np.uint8)
    prediction_u8 = prediction.astype(np.uint8)
    truth_boundary = truth_u8 - cv2.erode(truth_u8, kernel, iterations=1)
    prediction_boundary = prediction_u8 - cv2.erode(prediction_u8, kernel, iterations=1)
    dilation = np.ones((2 * tolerance + 1, 2 * tolerance + 1), dtype=np.uint8)
    truth_near = cv2.dilate(truth_boundary, dilation, iterations=1).astype(bool)
    prediction_near = cv2.dilate(prediction_boundary, dilation, iterations=1).astype(bool)
    truth_boundary_b = truth_boundary.astype(bool)
    prediction_boundary_b = prediction_boundary.astype(bool)
    precision = np.logical_and(prediction_boundary_b, truth_near).sum() / max(1, prediction_boundary_b.sum())
    recall = np.logical_and(truth_boundary_b, prediction_near).sum() / max(1, truth_boundary_b.sum())
    f1 = float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    truth_band = np.logical_and(truth, truth_near)
    prediction_band = np.logical_and(prediction, prediction_near)
    union = np.logical_or(truth_band, prediction_band).sum()
    boundary_iou = float(np.logical_and(truth_band, prediction_band).sum() / union) if union else 1.0
    return boundary_iou, f1


def mask_iou(truth: np.ndarray, prediction: np.ndarray) -> float:
    union = np.logical_or(truth, prediction).sum()
    if not union:
        return 1.0
    return float(np.logical_and(truth, prediction).sum() / union)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * q / 100)))
    return float(ordered[index])


def contour_radius(mask: np.ndarray) -> tuple[np.ndarray, float, float]:
    """用最大外轮廓点拟合 2048-bin 半径向量；返回 (vector, cy, cx)。"""
    contours = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
    if not contours:
        raise ValueError("空轮廓")
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    ys, xs = np.nonzero(mask)
    cy = float(ys.mean())
    cx = float(xs.mean())
    dy = contour[:, 1].astype(np.float64) - cy
    dx = contour[:, 0].astype(np.float64) - cx
    radius = np.hypot(dy, dx)
    theta = np.arctan2(dy, dx)
    index = np.floor((theta + np.pi) / (2 * np.pi) * ANGULAR_BINS).astype(np.int64) % ANGULAR_BINS
    order = np.argsort(index, kind="stable")
    sorted_index = index[order]
    sorted_radius = radius[order]
    unique, starts = np.unique(sorted_index, return_index=True)
    maxima = np.maximum.reduceat(sorted_radius, starts)
    vector = np.full(ANGULAR_BINS, np.nan, dtype=np.float64)
    vector[unique] = maxima
    filled = np.nonzero(~np.isnan(vector))[0]
    if filled.size < 16:
        raise ValueError("轮廓覆盖的角度bin过少")
    positions = np.concatenate([filled - ANGULAR_BINS, filled, filled + ANGULAR_BINS])
    values = np.concatenate([vector[filled], vector[filled], vector[filled]])
    return np.interp(np.arange(ANGULAR_BINS), positions, values), cy, cx


def gaussian_kernel(sigma_bins: float) -> np.ndarray | None:
    if sigma_bins <= 0:
        return None
    half = max(1, int(np.ceil(3 * sigma_bins)))
    offsets = np.arange(-half, half + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma_bins) ** 2)
    return kernel / kernel.sum()


def circular_convolve(vector: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    half = kernel.size // 2
    extended = np.concatenate([vector[-half:], vector, vector[:half]])
    return np.convolve(extended, kernel, mode="valid")


def circular_median(vector: np.ndarray, width_bins: int) -> np.ndarray:
    half = width_bins // 2
    offsets = np.arange(-half, half + 1)
    indices = (np.arange(vector.size)[:, None] + offsets[None, :]) % vector.size
    return np.median(vector[indices], axis=1)


def decode(distance: np.ndarray, bin_index: np.ndarray, radius: np.ndarray) -> np.ndarray:
    return distance <= radius[bin_index]


def joint_pass(gate: dict[str, float], iou: float, biou: float, bf1: float) -> bool:
    return iou >= gate["maskIoU"] and biou >= gate["boundaryIoU"] and bf1 >= gate["boundaryF1"]


def summarize(entries: list[dict[str, Any]], gate: dict[str, float], baseline_flags: list[bool] | None = None) -> dict[str, Any]:
    biou = [entry["boundaryIoU"] for entry in entries]
    joint = [joint_pass(gate, entry["iou"], entry["boundaryIoU"], entry["boundaryF1"]) for entry in entries]
    summary = {
        "truthNails": len(entries),
        "matchedIoU075": sum(1 for entry in entries if entry["iou"] >= gate["maskIoU"]),
        "jointPassingNails": int(sum(joint)),
        "meanMaskIoU": round(float(np.mean([entry["iou"] for entry in entries])), 9),
        "meanBoundaryIoU": round(float(np.mean(biou)), 9),
        "meanBoundaryF1": round(float(np.mean([entry["boundaryF1"] for entry in entries])), 9),
        "boundaryIoUPercentiles": {str(q): round(percentile(biou, q), 9) for q in (5, 15, 25, 50, 75, 90)},
    }
    if baseline_flags is not None:
        gained = sum(1 for now, was in zip(joint, baseline_flags, strict=True) if now and not was)
        lost = sum(1 for now, was in zip(joint, baseline_flags, strict=True) if was and not now)
        summary["gainedFromBaseline"] = int(gained)
        summary["lostFromBaseline"] = int(lost)
        summary["netFromBaseline"] = int(gained - lost)
    return summary


def analyze(plan: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    for label in ("evaluationReport", "evaluationPlan", "closeoutReport", "previousCeilingAudit"):
        binding = plan["inputs"][label]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{label}")

    evaluation = json.loads(Path(plan["inputs"]["evaluationReport"]["path"]).read_text(encoding="utf-8"))
    evaluation_plan = json.loads(Path(plan["inputs"]["evaluationPlan"]["path"]).read_text(encoding="utf-8"))
    closeout = json.loads(Path(plan["inputs"]["closeoutReport"]["path"]).read_text(encoding="utf-8"))
    previous = json.loads(Path(plan["inputs"]["previousCeilingAudit"]["path"]).read_text(encoding="utf-8"))
    if int(closeout["summary"]["jointPassingNails"]) != int(plan["frozenBaseline"]["strictJointPulling"]):
        raise ValueError("结项联合通过数与计划绑定不一致")
    if previous["decision"] != plan["frozenBaseline"]["previousDecision"]:
        raise ValueError("上一轮判决与计划绑定不一致")

    gate = plan["gate"]
    sigmas = [float(v) for v in plan["variants"]["gaussianSigmaArcPixels"]]
    medians = [float(v) for v in plan["variants"]["medianWidthArcPixels"]]
    variant_keys = [f"gaussian:{sigma:g}" for sigma in sigmas] + [f"median:{width:g}" for width in medians]

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    for item in evaluation_plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))

    per_instance: list[dict[str, Any]] = []
    reconstruction_ious: list[float] = []
    skipped_total = 0
    failed_fits = 0
    margin = 12

    records = evaluation["records"] if limit is None else evaluation["records"][:limit]
    for source_index, record in enumerate(records):
        source_ordinal = source_index + 1
        bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in bundle["maskShape"])
        predictions = unpack_bits(bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]

        truths: list[np.ndarray] = []
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                skipped_total += 1
                continue
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = unpack_bits(payload["truthPacked"], payload_shape)
            truths.append(truth)

        for truth_index, truth in enumerate(truths):
            scores = [mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            prediction = predictions[best]
            baseline_iou = scores[best]
            baseline_biou, baseline_bf1 = boundary_metrics(truth, prediction, 2)

            ys, xs = np.nonzero(truth)
            py, px = np.nonzero(prediction)
            y0 = max(0, min(int(ys.min()), int(py.min())) - margin)
            y1 = min(height, max(int(ys.max()), int(py.max())) + margin + 1)
            x0 = max(0, min(int(xs.min()), int(px.min())) - margin)
            x1 = min(width, max(int(xs.max()), int(px.max())) + margin + 1)
            truth_crop = truth[y0:y1, x0:x1]
            prediction_crop = prediction[y0:y1, x0:x1]

            entry: dict[str, Any] = {
                "sourceOrdinal": source_ordinal,
                "truthIndex": truth_index + 1,
                "fileName": record["identity"]["fileName"],
                "iou": round(baseline_iou, 9),
                "boundaryIoU": round(baseline_biou, 9),
                "boundaryF1": round(baseline_bf1, 9),
                "matched": bool(baseline_iou >= gate["maskIoU"]),
                "joint": bool(joint_pass(gate, baseline_iou, baseline_biou, baseline_bf1)),
                "variants": {},
            }

            try:
                vector, center_y, center_x = contour_radius(prediction_crop)
            except ValueError:
                failed_fits += 1
                entry["fitFailed"] = True
                per_instance.append(entry)
                continue

            radius_median = float(np.median(vector))
            arc_per_bin = 2 * np.pi * max(1.0, radius_median) / ANGULAR_BINS
            crop_height, crop_width = truth_crop.shape
            grid_y = np.arange(crop_height, dtype=np.float64)[:, None] - center_y
            grid_x = np.arange(crop_width, dtype=np.float64)[None, :] - center_x
            distance = np.hypot(grid_y, grid_x)
            theta = np.arctan2(grid_y, grid_x)
            bin_index = np.floor((theta + np.pi) / (2 * np.pi) * ANGULAR_BINS).astype(np.int64) % ANGULAR_BINS

            entry["radiusMedian"] = round(radius_median, 4)
            entry["arcPerBin"] = round(float(arc_per_bin), 5)

            for sigma in sigmas:
                sigma_bins = sigma / arc_per_bin if arc_per_bin > 0 else 0.0
                kernel = gaussian_kernel(sigma_bins)
                smoothed = vector if kernel is None else circular_convolve(vector, kernel)
                reconstructed = decode(distance, bin_index, smoothed)
                if sigma == 0:
                    reconstruction_ious.append(mask_iou(prediction_crop, reconstructed))
                variant_iou = mask_iou(truth_crop, reconstructed)
                variant_biou, variant_bf1 = boundary_metrics(truth_crop, reconstructed, 2)
                entry["variants"][f"gaussian:{sigma:g}"] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(joint_pass(gate, variant_iou, variant_biou, variant_bf1)),
                    "sigmaBins": round(float(sigma_bins), 4),
                }
            for width_arc in medians:
                width_bins = max(3, int(round(width_arc / arc_per_bin))) if arc_per_bin > 0 else 3
                if width_bins % 2 == 0:
                    width_bins += 1
                smoothed = circular_median(vector, width_bins)
                reconstructed = decode(distance, bin_index, smoothed)
                variant_iou = mask_iou(truth_crop, reconstructed)
                variant_biou, variant_bf1 = boundary_metrics(truth_crop, reconstructed, 2)
                entry["variants"][f"median:{width_arc:g}"] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(joint_pass(gate, variant_iou, variant_biou, variant_bf1)),
                    "widthBins": int(width_bins),
                }
            per_instance.append(entry)

    usable = [row for row in per_instance if "fitFailed" not in row]
    baseline_entries = [{"iou": row["iou"], "boundaryIoU": row["boundaryIoU"], "boundaryF1": row["boundaryF1"]} for row in usable]
    baseline = summarize(baseline_entries, gate)
    baseline_flags = [row["joint"] for row in usable]

    rows: list[dict[str, Any]] = []
    for key in variant_keys:
        entries = [
            {
                "iou": row["variants"][key]["iou"],
                "boundaryIoU": row["variants"][key]["boundaryIoU"],
                "boundaryF1": row["variants"][key]["boundaryF1"],
            }
            for row in usable
        ]
        summary = summarize(entries, gate, baseline_flags)
        summary["variant"] = key
        rows.append(summary)

    control = next(row for row in rows if row["variant"] == "gaussian:0")

    oracle_entries: list[dict[str, Any]] = []
    oracle_keys: dict[str, int] = {}
    for row in usable:
        options = [(key, value) for key, value in row["variants"].items() if value["joint"]]
        if not options:
            oracle_keys["none"] = oracle_keys.get("none", 0) + 1
            oracle_entries.append({"iou": row["iou"], "boundaryIoU": row["boundaryIoU"], "boundaryF1": row["boundaryF1"]})
            continue
        key, value = max(options, key=lambda item: item[1]["boundaryIoU"])
        oracle_keys[key] = oracle_keys.get(key, 0) + 1
        oracle_entries.append({"iou": value["iou"], "boundaryIoU": value["boundaryIoU"], "boundaryF1": value["boundaryF1"]})
    oracle = summarize(oracle_entries, gate, baseline_flags)
    oracle["chosenVariantDistribution"] = dict(sorted(oracle_keys.items()))

    reconstruction_mean = float(np.mean(reconstruction_ious)) if reconstruction_ious else 0.0
    reconstruction_min = float(np.min(reconstruction_ious)) if reconstruction_ious else 0.0
    reconstruction_fraction = (
        float(np.mean([value >= plan["fidelityGate"]["minimumPerNailIou"] for value in reconstruction_ious])) if reconstruction_ious else 0.0
    )
    fidelity = {
        "meanReconstructionIou": round(reconstruction_mean, 9),
        "minimumReconstructionIou": round(reconstruction_min, 9),
        "fractionAbovePerNailIou": round(reconstruction_fraction, 9),
        "reconstructedJoint": int(control["jointPassingNails"]),
        "baselineJoint": int(plan["frozenBaseline"]["strictJointPulling"]),
        "failedFits": int(failed_fits),
    }
    fidelity["passed"] = bool(
        reconstruction_mean >= plan["fidelityGate"]["minimumMeanReconstructionIou"]
        and reconstruction_min >= plan["fidelityGate"]["minimumPerNailIou"]
        and reconstruction_fraction >= plan["fidelityGate"]["minimumFractionNailsAbovePerNailIou"]
    )

    minimum_joint = int(gate["minimumJoint"])
    partial_threshold = int(plan["frozenBaseline"]["strictJointPulling"]) + 30
    best_row = max(rows, key=lambda row: int(row["jointPassingNails"]))
    if not fidelity["passed"]:
        decision = "reconstruction_invalid"
    elif int(control["jointPassingNails"]) < int(plan["fidelityGate"]["minimumControlJoint"]):
        decision = "operator_control_degraded"
    elif int(best_row["jointPassingNails"]) >= minimum_joint:
        decision = "smoothing_prior_reachable"
    elif int(best_row["jointPassingNails"]) >= partial_threshold:
        decision = "smoothing_prior_partial_effective"
    elif int(oracle["jointPassingNails"]) >= partial_threshold:
        decision = "smoothing_prior_per_instance_only"
    else:
        decision = "smoothing_prior_insufficient"

    return {
        "decision": decision,
        "fidelity": fidelity,
        "coverage": {"sources": len(records), "truthNails": len(per_instance), "usableNails": len(usable), "skippedInputsWithoutTruth": skipped_total},
        "baseline": baseline,
        "control": control,
        "variants": rows,
        "best": best_row,
        "oracle": oracle,
        "partialThreshold": partial_threshold,
        "perInstance": per_instance,
    }


def run(plan_path: Path, output_path: Path, limit: int | None = None) -> dict[str, Any]:
    guard_output(output_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = analyze(plan, limit)
    report = {
        "schemaVersion": 1,
        "ok": analysis["decision"]
        in {"smoothing_prior_reachable", "smoothing_prior_partial_effective", "smoothing_prior_per_instance_only", "smoothing_prior_insufficient"},
        "okSemantics": "ok 只表示分析与 fidelity/control 门有效并落在预注册判决集合内；ok=true 不代表质量门通过、路线可行或发布资格。",
        "decision": analysis["decision"],
        "purpose": plan["purpose"],
        "scope": plan["scope"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}},
        "gate": plan["gate"],
        "analysis": analysis,
        "analysisSha256": canonical_sha256(analysis),
        "interpretation": "本审计只判定轮廓光滑性先验的可达性：单变体结果给出可量产的一致算子，每甲最优给出上限，sigma=0 列为算子自身对照。任何结论都不授权训练、导出或改生产阈值；采纳须另立预注册合同并重跑全634验收与 Python↔浏览器逐实例对拍。",
        "errors": [],
    }
    write_atomic(output_path, report)
    return {
        "ok": report["ok"],
        "decision": report["decision"],
        "analysisSha256": report["analysisSha256"],
        "baseline": analysis["baseline"]["jointPassingNails"],
        "control": analysis["control"]["jointPassingNails"],
        "best": {
            "variant": analysis["best"]["variant"],
            "joint": analysis["best"]["jointPassingNails"],
            "gained": analysis["best"]["gainedFromBaseline"],
            "lost": analysis["best"]["lostFromBaseline"],
        },
        "oracle": analysis["oracle"]["jointPassingNails"],
        "fidelity": analysis["fidelity"],
    }


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan_path = Path(report["inputs"]["plan"]["path"])
    if sha256_file(plan_path) != report["inputs"]["plan"]["sha256"]:
        raise ValueError("计划哈希漂移")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    replay = analyze(plan)
    digest = canonical_sha256(replay)
    if digest != report["analysisSha256"]:
        raise ValueError("重放分析哈希不一致")
    return {"ok": True, "decision": "verified_contour_smoothing_prior", "result": report["decision"], "analysisSha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.output:
            parser.error("运行审计需要--plan与--output")
        print(json.dumps(run(args.plan, args.output, args.limit), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
