#!/usr/bin/env python3
"""循环093零推理判决：面积补偿平滑 + 有界偏移自适应核宽。

复用 092 审计模块的度量与核函数（运行前校验哈希），把 092 的增益拆成
「去抖动」与「整体收缩」两部分，并在面积偏置≈0 的约束下给出无偏天花板。
只读冻结产物；不产生模型输入、不训练、不改门。
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

import cv2
import numpy as np

EVIDENCE_ROOT = Path(r"E:\AI Project\Codex\JiaRu\model\reviews")


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


def load_metric_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("cycle092_metrics", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载度量模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def boundary_pixels(mask: np.ndarray) -> np.ndarray:
    u8 = mask.astype(np.uint8)
    return (u8 - cv2.erode(u8, np.ones((3, 3), np.uint8))).astype(bool)


def symmetric_boundary_distance(truth: np.ndarray, prediction: np.ndarray) -> tuple[float, float]:
    truth_edge = boundary_pixels(truth)
    prediction_edge = boundary_pixels(prediction)
    if not truth_edge.any() or not prediction_edge.any():
        return float("nan"), float("nan")
    to_truth = cv2.distanceTransform((~truth_edge).astype(np.uint8), cv2.DIST_L2, 5)
    to_prediction = cv2.distanceTransform((~prediction_edge).astype(np.uint8), cv2.DIST_L2, 5)
    merged = np.concatenate([to_truth[prediction_edge], to_prediction[truth_edge]])
    return float(merged.mean()), float(np.percentile(merged, 95))


def normalized_gradient(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    scale = float(np.percentile(magnitude, 99)) or 1.0
    return magnitude / scale


def gradient_support_at(gradient_map: np.ndarray, mask_crop: np.ndarray, offset_y: int, offset_x: int) -> float:
    """在整图归一化梯度图上取轮廓像素（裁片坐标 -> 整图坐标）的均值。"""
    edge = boundary_pixels(mask_crop)
    edge[:3, :] = False
    edge[-3:, :] = False
    edge[:, :3] = False
    edge[:, -3:] = False
    if not edge.any():
        return float("nan")
    ys, xs = np.nonzero(edge)
    full_y = ys + offset_y
    full_x = xs + offset_x
    inside = (full_y >= 0) & (full_y < gradient_map.shape[0]) & (full_x >= 0) & (full_x < gradient_map.shape[1])
    if not inside.any():
        return float("nan")
    return float(gradient_map[full_y[inside], full_x[inside]].mean())


def perimeter_from_radius(vector: np.ndarray, median_radius: float) -> float:
    arc = 2 * np.pi * max(1.0, median_radius) / vector.size
    delta = np.diff(np.concatenate([vector, vector[:1]]))
    return float(np.sum(np.hypot(arc, delta)))


def smooth_vector(vector: np.ndarray, operator: str, arc_per_bin: float, module: Any, sigma_arc: float = 0.0, width_arc: float = 0.0) -> np.ndarray:
    if operator == "none":
        return vector
    if operator == "gaussian":
        kernel = module.gaussian_kernel(sigma_arc / arc_per_bin)
        return vector if kernel is None else module.circular_convolve(vector, kernel)
    if operator == "median":
        width_bins = max(3, int(round(width_arc / arc_per_bin)))
        if width_bins % 2 == 0:
            width_bins += 1
        return module.circular_median(vector, width_bins)
    raise ValueError(f"未知算子：{operator}")


def adaptive_vector(
    vector: np.ndarray,
    grid: list[float],
    deviation_rms: float,
    arc_per_bin: float,
    module: Any,
) -> tuple[np.ndarray, float]:
    """取满足 RMS(r_smoothed - r) <= deviation_rms 的最大核宽；不使用真值。"""
    best_vector = vector
    best_sigma = 0.0
    for sigma in grid:
        kernel = module.gaussian_kernel(sigma / arc_per_bin)
        if kernel is None:
            continue
        candidate = module.circular_convolve(vector, kernel)
        if float(np.sqrt(np.mean((candidate - vector) ** 2))) <= deviation_rms:
            best_vector, best_sigma = candidate, float(sigma)
    return best_vector, best_sigma


def compensate_area(
    vector: np.ndarray,
    distance: np.ndarray,
    bin_index: np.ndarray,
    target_area: int,
    module: Any,
) -> tuple[np.ndarray, int]:
    radius_median = float(np.median(vector))
    perimeter = perimeter_from_radius(vector, radius_median)
    current = module.decode(distance, bin_index, vector).sum()
    delta = (target_area - current) / max(1.0, perimeter)
    compensated = vector + delta
    residual_area = int(module.decode(distance, bin_index, compensated).sum())
    correction = (target_area - residual_area) / max(1.0, perimeter)
    compensated = compensated + correction
    return compensated, int(module.decode(distance, bin_index, compensated).sum())


def summarize(entries: list[dict[str, Any]], gate: dict[str, float], baseline_flags: list[bool]) -> dict[str, Any]:
    biou = [entry["boundaryIoU"] for entry in entries]
    joint = [entry["iou"] >= gate["maskIoU"] and entry["boundaryIoU"] >= gate["boundaryIoU"] and entry["boundaryF1"] >= gate["boundaryF1"] for entry in entries]
    gained = sum(1 for now, was in zip(joint, baseline_flags, strict=True) if now and not was)
    lost = sum(1 for now, was in zip(joint, baseline_flags, strict=True) if was and not now)
    ordered = sorted(biou)
    return {
        "truthNails": len(entries),
        "matchedIoU075": int(sum(1 for entry in entries if entry["iou"] >= gate["maskIoU"])),
        "jointPassingNails": int(sum(joint)),
        "gainedFromBaseline": int(gained),
        "lostFromBaseline": int(lost),
        "netFromBaseline": int(gained - lost),
        "meanBoundaryIoU": round(float(np.mean(biou)), 9),
        "meanMaskIoU": round(float(np.mean([entry["iou"] for entry in entries])), 9),
        "meanBoundaryF1": round(float(np.mean([entry["boundaryF1"] for entry in entries])), 9),
        "boundaryIoUPercentiles": {str(q): round(float(ordered[min(len(ordered) - 1, int(len(ordered) * q / 100))]), 9) for q in (15, 50, 75)},
        "areaBiasPxPerPerimeter": round(float(np.mean([entry["areaBias"] for entry in entries])), 6),
        "meanSymmetricBoundaryDistance": round(float(np.nanmean([entry["boundaryDistance"] for entry in entries])), 6),
        "hd95": round(float(np.nanmean([entry["hd95"] for entry in entries])), 6),
        "gradientSupport": round(float(np.nanmean([entry["gradientSupport"] for entry in entries])), 6),
    }


def analyze(plan: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    for label in ("evaluationReport", "evaluationPlan", "closeoutReport", "previousSmoothingAuditV2", "metricModule"):
        binding = plan["inputs"][label]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{label}")

    module = load_metric_module(Path(plan["inputs"]["metricModule"]["path"]))
    evaluation = json.loads(Path(plan["inputs"]["evaluationReport"]["path"]).read_text(encoding="utf-8"))
    evaluation_plan = json.loads(Path(plan["inputs"]["evaluationPlan"]["path"]).read_text(encoding="utf-8"))
    closeout = json.loads(Path(plan["inputs"]["closeoutReport"]["path"]).read_text(encoding="utf-8"))
    previous = json.loads(Path(plan["inputs"]["previousSmoothingAuditV2"]["path"]).read_text(encoding="utf-8"))
    if int(closeout["summary"]["jointPassingNails"]) != int(plan["frozenBaseline"]["strictJointPulling"]):
        raise ValueError("结项联合通过数与计划绑定不一致")
    if previous["decision"] != plan["frozenBaseline"]["previousDecision"]:
        raise ValueError("上一轮判决与计划绑定不一致")

    gate = plan["gate"]
    variants = plan["variants"]
    variant_keys = [variant["key"] for variant in variants]

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    for item in evaluation_plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))

    per_instance: list[dict[str, Any]] = []
    reconstruction_ious: list[float] = []
    truth_gradient: list[float] = []
    skipped_total = 0
    failed_fits = 0
    margin = 12

    records = evaluation["records"] if limit is None else evaluation["records"][:limit]
    for source_index, record in enumerate(records):
        source_ordinal = source_index + 1
        bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in bundle["maskShape"])
        predictions = module.unpack_bits(bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]

        payloads: list[tuple[dict[str, Any], Any]] = []
        gradient_map = np.zeros((height, width), dtype=np.float32)
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                skipped_total += 1
                continue
            payloads.append((item, payload))
            crop_rect = [int(v) for v in item["crop"]]
            gradient_map[crop_rect[1]:crop_rect[3], crop_rect[0]:crop_rect[2]] = normalized_gradient(payload["rgb"])

        for truth_index, (item, payload) in enumerate(payloads):
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = module.unpack_bits(payload["truthPacked"], payload_shape)
            scores = [module.mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            prediction = predictions[best]
            baseline_iou = scores[best]
            baseline_biou, baseline_bf1 = module.boundary_metrics(truth, prediction, 2)

            ys, xs = np.nonzero(truth)
            py, px = np.nonzero(prediction)
            expanded = (
                max(0, min(int(ys.min()), int(py.min())) - margin),
                min(height, max(int(ys.max()), int(py.max())) + margin + 1),
                max(0, min(int(xs.min()), int(px.min())) - margin),
                min(width, max(int(xs.max()), int(px.max())) + margin + 1),
            )
            truth_crop = truth[expanded[0]:expanded[1], expanded[2]:expanded[3]]
            prediction_crop = prediction[expanded[0]:expanded[1], expanded[2]:expanded[3]]

            entry: dict[str, Any] = {
                "sourceOrdinal": source_ordinal,
                "truthIndex": truth_index + 1,
                "fileName": record["identity"]["fileName"],
                "iou": round(baseline_iou, 9),
                "boundaryIoU": round(baseline_biou, 9),
                "boundaryF1": round(baseline_bf1, 9),
                "joint": bool(baseline_iou >= gate["maskIoU"] and baseline_biou >= gate["boundaryIoU"] and baseline_bf1 >= gate["boundaryF1"]),
                "variants": {},
            }
            try:
                vector, center_y, center_x = module.contour_radius(prediction_crop)
            except ValueError:
                failed_fits += 1
                entry["fitFailed"] = True
                per_instance.append(entry)
                continue

            radius_median = float(np.median(vector))
            arc_per_bin = 2 * np.pi * max(1.0, radius_median) / module.ANGULAR_BINS
            crop_height, crop_width = truth_crop.shape
            grid_y = np.arange(crop_height, dtype=np.float64)[:, None] - center_y
            grid_x = np.arange(crop_width, dtype=np.float64)[None, :] - center_x
            distance = np.hypot(grid_y, grid_x)
            theta = np.arctan2(grid_y, grid_x)
            bin_index = np.floor((theta + np.pi) / (2 * np.pi) * module.ANGULAR_BINS).astype(np.int64) % module.ANGULAR_BINS

            reconstruction = module.decode(distance, bin_index, vector)
            reconstruction_ious.append(module.mask_iou(prediction_crop, reconstruction))
            reconstruction_area = int(reconstruction.sum())

            truth_gradient.append(gradient_support_at(gradient_map, truth_crop, expanded[0], expanded[2]))

            for variant in variants:
                key = variant["key"]
                operator = variant["operator"]
                sigma_chosen = 0.0
                if operator == "adaptive":
                    smoothed, sigma_chosen = adaptive_vector(
                        vector, [float(v) for v in variant["gridArc"]], float(variant["deviationRmsArc"]), arc_per_bin, module
                    )
                else:
                    smoothed = smooth_vector(vector, operator, arc_per_bin, module, float(variant.get("sigmaArc", 0.0)), float(variant.get("widthArc", 0.0)))
                if variant["areaCompensated"]:
                    smoothed, _ = compensate_area(smoothed, distance, bin_index, reconstruction_area, module)
                reconstructed = module.decode(distance, bin_index, smoothed)
                variant_iou = module.mask_iou(truth_crop, reconstructed)
                variant_biou, variant_bf1 = module.boundary_metrics(truth_crop, reconstructed, 2)
                contours = cv2.findContours(reconstructed.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]
                perimeter = max(1.0, float(sum(cv2.arcLength(contour, True) for contour in contours)))
                boundary_distance, hd95 = symmetric_boundary_distance(truth_crop, reconstructed)
                entry["variants"][key] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(variant_iou >= gate["maskIoU"] and variant_biou >= gate["boundaryIoU"] and variant_bf1 >= gate["boundaryF1"]),
                    "areaBias": float((reconstructed.sum() - truth_crop.sum()) / perimeter),
                    "boundaryDistance": boundary_distance,
                    "hd95": hd95,
                    "gradientSupport": gradient_support_at(gradient_map, reconstructed, expanded[0], expanded[2]),
                    "sigmaArcChosen": round(float(sigma_chosen), 4),
                }
            per_instance.append(entry)

    usable = [row for row in per_instance if "fitFailed" not in row]
    baseline_entries = [
        {
            "iou": row["iou"],
            "boundaryIoU": row["boundaryIoU"],
            "boundaryF1": row["boundaryF1"],
            "areaBias": float("nan"),
            "boundaryDistance": float("nan"),
            "hd95": float("nan"),
            "gradientSupport": float("nan"),
        }
        for row in usable
    ]
    baseline_flags = [row["joint"] for row in usable]

    rows: list[dict[str, Any]] = []
    for key in variant_keys:
        entries = [row["variants"][key] | {"iou": row["variants"][key]["iou"]} for row in usable]
        summary = summarize(entries, gate, baseline_flags)
        summary["variant"] = key
        summary["meanSigmaArc"] = round(float(np.mean([row["variants"][key]["sigmaArcChosen"] for row in usable])), 4)
        rows.append(summary)

    control = next(row for row in rows if row["variant"] == "recon")
    reconstruction_mean = float(np.mean(reconstruction_ious)) if reconstruction_ious else 0.0
    reconstruction_min = float(np.min(reconstruction_ious)) if reconstruction_ious else 0.0
    reconstruction_fraction = float(np.mean([value >= plan["fidelityGate"]["minimumPerNailIou"] for value in reconstruction_ious])) if reconstruction_ious else 0.0
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

    control_area_bias = control["areaBiasPxPerPerimeter"]
    for row in rows:
        row["areaBiasRelativeToControl"] = round(float(row["areaBiasPxPerPerimeter"] - control_area_bias), 6)
    eligible = [row for row in rows if row["variant"] != "recon" and abs(row["areaBiasRelativeToControl"]) <= 0.10]
    best_eligible = max(eligible, key=lambda row: row["jointPassingNails"]) if eligible else None
    best_overall = max(rows, key=lambda row: row["jointPassingNails"])

    oracle_entries: list[dict[str, Any]] = []
    oracle_keys: dict[str, int] = {}
    eligible_keys = [row["variant"] for row in eligible] or variant_keys
    for row in usable:
        options = [(key, row["variants"][key]) for key in eligible_keys if row["variants"][key]["joint"]]
        if not options:
            oracle_keys["none"] = oracle_keys.get("none", 0) + 1
            oracle_entries.append({"iou": row["iou"], "boundaryIoU": row["boundaryIoU"], "boundaryF1": row["boundaryF1"], "areaBias": float("nan"), "boundaryDistance": float("nan"), "hd95": float("nan"), "gradientSupport": float("nan")})
            continue
        key, value = max(options, key=lambda pair: pair[1]["boundaryIoU"])
        oracle_keys[key] = oracle_keys.get(key, 0) + 1
        oracle_entries.append(value | {"iou": value["iou"]})
    oracle = summarize(oracle_entries, gate, baseline_flags)
    oracle["chosenVariantDistribution"] = dict(sorted(oracle_keys.items()))

    minimum_joint = int(gate["minimumJoint"])
    partial_threshold = int(plan["frozenBaseline"]["strictJointPulling"]) + 30
    if not fidelity["passed"]:
        decision = "reconstruction_invalid"
    elif int(control["jointPassingNails"]) < int(plan["fidelityGate"]["minimumControlJoint"]):
        decision = "operator_control_degraded"
    elif best_eligible and int(best_eligible["jointPassingNails"]) >= minimum_joint:
        decision = "bias_neutral_reachable"
    elif best_eligible and int(best_eligible["jointPassingNails"]) >= partial_threshold:
        decision = "bias_neutral_partial_effective"
    elif int(best_overall["jointPassingNails"]) >= partial_threshold:
        decision = "gain_requires_shrink_bias"
    else:
        decision = "bias_neutral_insufficient"

    return {
        "decision": decision,
        "fidelity": fidelity,
        "coverage": {"sources": len(records), "truthNails": len(per_instance), "usableNails": len(usable), "skippedInputsWithoutTruth": skipped_total},
        "baselineJoint": int(plan["frozenBaseline"]["strictJointPulling"]),
        "truthGradientSupport": round(float(np.nanmean(truth_gradient)), 6),
        "control": control,
        "variants": rows,
        "bestEligible": best_eligible,
        "bestOverall": best_overall,
        "oracle": oracle,
        "eligibleKeys": [row["variant"] for row in eligible],
        "partialThreshold": partial_threshold,
        "perInstance": per_instance,
    }


def run(plan_path: Path, output_path: Path, limit: int | None = None) -> dict[str, Any]:
    guard_output(output_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = analyze(plan, limit)
    report = {
        "schemaVersion": 1,
        "ok": analysis["decision"] in {"bias_neutral_reachable", "bias_neutral_partial_effective", "gain_requires_shrink_bias", "bias_neutral_insufficient"},
        "okSemantics": "ok 只表示分析与 fidelity/control 门有效并落在预注册判决集合内；ok=true 不代表质量门通过、路线可行或发布资格。",
        "decision": analysis["decision"],
        "purpose": plan["purpose"],
        "scope": plan["scope"],
        "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}},
        "gate": plan["gate"],
        "analysis": analysis,
        "analysisSha256": canonical_sha256(analysis),
        "interpretation": "本审计只判定无偏（面积偏置<=0.10px/周长）前提下轮廓平滑的可达性，并把增益拆成去抖动与整体收缩两部分。不授权训练、导出或改生产阈值；采纳须另立合同并重跑全634 + Python↔浏览器逐实例对拍 + 独立来源重标定。",
        "errors": [],
    }
    write_atomic(output_path, report)
    return {
        "ok": report["ok"],
        "decision": report["decision"],
        "analysisSha256": report["analysisSha256"],
        "baseline": analysis["baselineJoint"],
        "control": analysis["control"]["jointPassingNails"],
        "bestEligible": None if analysis["bestEligible"] is None else {"variant": analysis["bestEligible"]["variant"], "joint": analysis["bestEligible"]["jointPassingNails"], "areaBias": analysis["bestEligible"]["areaBiasPxPerPerimeter"]},
        "bestOverall": {"variant": analysis["bestOverall"]["variant"], "joint": analysis["bestOverall"]["jointPassingNails"], "areaBias": analysis["bestOverall"]["areaBiasPxPerPerimeter"]},
        "oracle": analysis["oracle"]["jointPassingNails"],
        "eligibleKeys": analysis["eligibleKeys"],
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
    return {"ok": True, "decision": "verified_bias_neutral_smoothing", "result": report["decision"], "analysisSha256": digest}


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
