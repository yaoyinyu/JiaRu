#!/usr/bin/env python3
"""循环091前零推理可达性判决：冻结第90次634甲预测的轮廓径向校准天花板。

只读冻结终评产物（预测 npz、真值 payload、终评报告），不产生模型输入、不训练、
不改写任何既有失败判定。结论只判定路线可达性，不构成正式候选或发布证据。
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
    resolved = path.resolve()
    if EVIDENCE_ROOT.resolve() in resolved.parents:
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


def radial(mask: np.ndarray, iterations: int) -> np.ndarray:
    """正数腐蚀（向内收缩），负数膨胀（向外扩张），单位为整数像素。"""
    if iterations == 0:
        return mask
    kernel = np.ones((3, 3), dtype=np.uint8)
    source = mask.astype(np.uint8)
    if iterations > 0:
        return cv2.erode(source, kernel, iterations=iterations).astype(bool)
    return cv2.dilate(source, kernel, iterations=-iterations).astype(bool)


def translate(mask: np.ndarray, shift: tuple[int, int]) -> np.ndarray:
    dy, dx = shift
    matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
    shifted = cv2.warpAffine(mask.astype(np.uint8), matrix, (mask.shape[1], mask.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)
    return shifted.astype(bool)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * q / 100)))
    return float(ordered[index])


def joint_pass(gate: dict[str, float], iou: float, biou: float, bf1: float) -> bool:
    return iou >= gate["maskIoU"] and biou >= gate["boundaryIoU"] and bf1 >= gate["boundaryF1"]


def summarize(rows: list[dict[str, Any]], gate: dict[str, float]) -> dict[str, Any]:
    truth_nails = len(rows)
    matched = sum(1 for row in rows if row["iou"] >= gate["maskIoU"])
    joint = sum(1 for row in rows if joint_pass(gate, row["iou"], row["boundaryIoU"], row["boundaryF1"]))
    biou = [row["boundaryIoU"] for row in rows]
    unmatched = sum(1 for row in rows if not row["matched"])
    return {
        "truthNails": truth_nails,
        "matchedIoU075": matched,
        "jointPassingNails": joint,
        "meanMaskIoU": round(float(np.mean([row["iou"] for row in rows])), 9),
        "meanBoundaryIoU": round(float(np.mean(biou)), 9),
        "meanBoundaryF1": round(float(np.mean([row["boundaryF1"] for row in rows])), 9),
        "boundaryIoUPercentiles": {str(q): round(percentile(biou, q), 9) for q in (5, 10, 15, 25, 50, 75, 90, 95)},
        "unmatchedNails": unmatched,
    }


def analyze(plan: dict[str, Any]) -> dict[str, Any]:
    evaluation_path = Path(plan["inputs"]["evaluationReport"]["path"])
    evaluation_plan_path = Path(plan["inputs"]["evaluationPlan"]["path"])
    closeout_path = Path(plan["inputs"]["closeoutReport"]["path"])
    for label in ("evaluationReport", "evaluationPlan", "truthIndex", "closeoutReport"):
        binding = plan["inputs"][label]
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{label}")

    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    evaluation_plan = json.loads(evaluation_plan_path.read_text(encoding="utf-8"))
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    if closeout["decision"] != "closed_completed_quality_failed":
        raise ValueError("结项状态与预期不一致")
    if int(closeout["summary"]["jointPassingNails"]) != int(plan["frozenBaseline"]["strictJointPulling"]):
        raise ValueError("结项联合通过数与计划绑定不一致")

    gate = plan["gate"]
    radial_grid = [int(v) for v in plan["experiments"]["E1_globalRadial"]["erosionIterations"]]
    shifts = [tuple(int(v) for v in s) for s in plan["experiments"]["E4_globalTranslation"]["shifts"]]

    inputs_by_source: dict[int, list[dict[str, Any]]] = {}
    for item in evaluation_plan["inputs"]:
        inputs_by_source.setdefault(int(item["sourceOrdinal"]), []).append(item)
    for value in inputs_by_source.values():
        value.sort(key=lambda entry: int(entry["candidateIndex"]))

    per_instance: list[dict[str, Any]] = []
    fidelity_mismatches: list[dict[str, Any]] = []
    max_abs_delta = {"iou": 0.0, "boundaryIoU": 0.0, "boundaryF1": 0.0}
    skipped_total = 0

    for source_index, record in enumerate(evaluation["records"]):
        source_ordinal = source_index + 1
        prediction_bundle = np.load(Path(record["candidate"]["prediction"]["path"]))
        shape = tuple(int(v) for v in prediction_bundle["maskShape"])
        predictions = unpack_bits(prediction_bundle["masksPacked"], shape)
        height, width = shape[1], shape[2]
        truths: list[np.ndarray] = []
        skipped_inputs = 0
        for item in inputs_by_source[source_ordinal]:
            payload = np.load(Path(item["payload"]["path"]))
            if "truthPacked" not in payload.files:
                # 终评636输入中2项无真值（即报告里的未分配候选），不计入真值分母。
                skipped_inputs += 1
                continue
            payload_shape = tuple(int(v) for v in payload["shape"])
            crop = [int(v) for v in item["crop"]]
            truth = np.zeros((height, width), dtype=bool)
            truth[crop[1]:crop[3], crop[0]:crop[2]] = unpack_bits(payload["truthPacked"], payload_shape)
            truths.append(truth)
        skipped_total += skipped_inputs

        recomputed: list[tuple[float, float, float]] = []
        for truth_index, truth in enumerate(truths):
            scores = [mask_iou(truth, predictions[j]) for j in range(predictions.shape[0])]
            best = int(np.argmax(scores))
            prediction = predictions[best]
            iou = scores[best]
            biou, bf1 = boundary_metrics(truth, prediction, 2)
            recomputed.append((iou, biou, bf1))

            ys, xs = np.nonzero(truth)
            py, px = np.nonzero(prediction)
            margin = 8
            y0 = max(0, min(int(ys.min()), int(py.min())) - margin)
            y1 = min(height, max(int(ys.max()), int(py.max())) + margin + 1)
            x0 = max(0, min(int(xs.min()), int(px.min())) - margin)
            x1 = min(width, max(int(xs.max()), int(px.max())) + margin + 1)
            truth_crop = truth[y0:y1, x0:x1]
            prediction_crop = prediction[y0:y1, x0:x1]

            per_k: dict[str, dict[str, float]] = {}
            for iterations in radial_grid:
                variant = radial(prediction_crop, iterations)
                variant_iou = mask_iou(truth_crop, variant)
                variant_biou, variant_bf1 = boundary_metrics(truth_crop, variant, 2)
                per_k[str(iterations)] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(joint_pass(gate, variant_iou, variant_biou, variant_bf1)),
                }
            per_shift: dict[str, dict[str, float]] = {}
            for shift in shifts:
                variant = translate(prediction_crop, shift)
                variant_iou = mask_iou(truth_crop, variant)
                variant_biou, variant_bf1 = boundary_metrics(truth_crop, variant, 2)
                per_shift[f"{shift[0]},{shift[1]}"] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(joint_pass(gate, variant_iou, variant_biou, variant_bf1)),
                }
            truth_perturbation: dict[str, dict[str, float]] = {}
            for label, iterations in (("erode1", 1), ("dilate1", -1)):
                perturbed = radial(truth_crop, iterations)
                variant_biou, variant_bf1 = boundary_metrics(perturbed, prediction_crop, 2)
                variant_iou = mask_iou(perturbed, prediction_crop)
                truth_perturbation[label] = {
                    "iou": round(variant_iou, 9),
                    "boundaryIoU": round(variant_biou, 9),
                    "boundaryF1": round(variant_bf1, 9),
                    "joint": bool(joint_pass(gate, variant_iou, variant_biou, variant_bf1)),
                }

            per_instance.append(
                {
                    "sourceOrdinal": source_ordinal,
                    "truthIndex": truth_index + 1,
                    "fileName": record["identity"]["fileName"],
                    "truthArea": int(truth.sum()),
                    "predictionArea": int(prediction.sum()),
                    "iou": round(iou, 9),
                    "boundaryIoU": round(biou, 9),
                    "boundaryF1": round(bf1, 9),
                    "matched": bool(iou >= gate["maskIoU"]),
                    "joint": bool(joint_pass(gate, iou, biou, bf1)),
                    "perK": per_k,
                    "perShift": per_shift,
                    "truthPerturbation": truth_perturbation,
                }
            )

        reported = sorted(
            (float(e["iou"]), float(e["boundaryIoU"]), float(e["boundaryF1"]))
            for e in record["candidate"]["boundary"]
            if float(e.get("iou", 0.0)) > 0.0
        )
        mine = sorted(recomputed)
        if len(reported) != len(mine):
            fidelity_mismatches.append({"sourceOrdinal": source_ordinal, "reason": "count", "reported": len(reported), "recomputed": len(mine)})
            continue
        for left, right in zip(mine, reported, strict=True):
            for slot, name in enumerate(("iou", "boundaryIoU", "boundaryF1")):
                delta = abs(left[slot] - right[slot])
                max_abs_delta[name] = max(max_abs_delta[name], delta)

    fidelity_ok = not fidelity_mismatches and max(max_abs_delta.values()) <= 1e-9

    base_rows = [
        {"iou": row["iou"], "boundaryIoU": row["boundaryIoU"], "boundaryF1": row["boundaryF1"], "matched": row["matched"]}
        for row in per_instance
    ]
    base = summarize(base_rows, gate)
    fidelity_ok = fidelity_ok and base["jointPassingNails"] == int(plan["frozenBaseline"]["strictJointPulling"])

    e1_rows: list[dict[str, Any]] = []
    for iterations in radial_grid:
        rows = [
            {
                "iou": row["perK"][str(iterations)]["iou"],
                "boundaryIoU": row["perK"][str(iterations)]["boundaryIoU"],
                "boundaryF1": row["perK"][str(iterations)]["boundaryF1"],
                "matched": row["perK"][str(iterations)]["iou"] >= gate["maskIoU"],
            }
            for row in per_instance
        ]
        summary = summarize(rows, gate)
        summary["erosionIterations"] = iterations
        e1_rows.append(summary)

    e2_rows: list[dict[str, Any]] = []
    best_slots: dict[str, int] = {}
    for row in per_instance:
        candidates = [key for key, value in row["perK"].items() if value["joint"]]
        if candidates:
            best = min(candidates, key=lambda key: abs(int(key)))
            best_slots[best] = best_slots.get(best, 0) + 1
            entry = row["perK"][best]
        else:
            best = None
            entry = {"iou": row["iou"], "boundaryIoU": row["boundaryIoU"], "boundaryF1": row["boundaryF1"]}
        e2_rows.append({"iou": entry["iou"], "boundaryIoU": entry["boundaryIoU"], "boundaryF1": entry["boundaryF1"], "matched": True})
        row["bestK"] = best
    e2 = summarize(e2_rows, gate)
    e2["chosenKDistribution"] = dict(sorted(best_slots.items(), key=lambda item: abs(int(item[0]))))

    e3_rows: list[dict[str, Any]] = []
    for label in ("erode1", "dilate1"):
        rows = [
            {
                "iou": row["truthPerturbation"][label]["iou"],
                "boundaryIoU": row["truthPerturbation"][label]["boundaryIoU"],
                "boundaryF1": row["truthPerturbation"][label]["boundaryF1"],
                "matched": row["truthPerturbation"][label]["iou"] >= gate["maskIoU"],
            }
            for row in per_instance
        ]
        summary = summarize(rows, gate)
        summary["perturbation"] = label
        e3_rows.append(summary)

    e4_rows: list[dict[str, Any]] = []
    for shift in shifts:
        key = f"{shift[0]},{shift[1]}"
        rows = [
            {
                "iou": row["perShift"][key]["iou"],
                "boundaryIoU": row["perShift"][key]["boundaryIoU"],
                "boundaryF1": row["perShift"][key]["boundaryF1"],
                "matched": row["perShift"][key]["iou"] >= gate["maskIoU"],
            }
            for row in per_instance
        ]
        summary = summarize(rows, gate)
        summary["shift"] = list(shift)
        e4_rows.append(summary)

    minimum_joint = int(gate["minimumJoint"])
    best_global = max(int(row["jointPassingNails"]) for row in e1_rows)
    best_per_instance = int(e2["jointPassingNails"])
    half_gap = (minimum_joint - int(plan["frozenBaseline"]["strictJointPulling"])) / 2.0
    truth_flag = any(abs(int(row["jointPassingNails"]) - int(plan["frozenBaseline"]["strictJointPulling"])) >= half_gap for row in e3_rows)

    if not fidelity_ok:
        decision = "fidelity_mismatch"
    elif best_global >= minimum_joint:
        decision = "global_radial_bias_reachable"
    elif best_per_instance >= minimum_joint:
        decision = "per_instance_radial_required"
    else:
        decision = "radial_family_insufficient"

    return {
        "decision": decision,
        "fidelity": {
            "passed": bool(fidelity_ok),
            "maxAbsoluteDelta": {key: float(value) for key, value in max_abs_delta.items()},
            "perImageMismatches": fidelity_mismatches,
            "recomputedJoint": int(base["jointPassingNails"]),
            "baselineJoint": int(plan["frozenBaseline"]["strictJointPulling"]),
        },
        "coverage": {"sources": len(evaluation["records"]), "truthNails": len(per_instance), "skippedInputsWithoutTruth": skipped_total},
        "baseline": base,
        "E1_globalRadial": {"rows": e1_rows, "bestJoint": best_global},
        "E2_perInstanceRadial": e2,
        "E3_truthAmbiguity": {"rows": e3_rows, "flagged": bool(truth_flag), "halfGap": half_gap},
        "E4_globalTranslation": {"rows": e4_rows, "bestJoint": max(int(row["jointPassingNails"]) for row in e4_rows)},
        "gapToGate": {"strictJoint": int(plan["frozenBaseline"]["strictJointPulling"]), "gate": minimum_joint, "remaining": minimum_joint - int(plan["frozenBaseline"]["strictJointPulling"])},
        "perInstance": per_instance,
    }


def run(plan_path: Path, output_path: Path) -> dict[str, Any]:
    guard_output(output_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = analyze(plan)
    report = {
        "schemaVersion": 1,
        "ok": analysis["decision"] in {"global_radial_bias_reachable", "per_instance_radial_required", "radial_family_insufficient"},
        "okSemantics": "ok 只表示分析与 fidelity 有效并给出预注册判决之一；ok=true 不代表质量门通过、路线可行或发布资格。",
        "decision": analysis["decision"],
        "purpose": plan["purpose"],
        "scope": plan["scope"],
        "inputs": {
            "plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)},
            **{label: {"path": binding["path"], "sha256": binding["sha256"]} for label, binding in plan["inputs"].items() if "sha256" in binding and label != "metricDefinition"},
        },
        "gate": plan["gate"],
        "analysis": analysis,
        "analysisSha256": canonical_sha256(analysis),
        "interpretation": "本审计只判定路线可达性：E1为全局单参数上限，E2为每甲径向参数上限，E3为真值±1px歧义敏感度，E4区分尺度偏置与位置偏置。任何结论都不授权训练、导出、改生产阈值或改写既有失败；采纳须另立预注册合同并重跑全634验收。",
        "errors": [],
    }
    write_atomic(output_path, report)
    return {key: report[key] for key in ("ok", "decision", "analysisSha256")} | {
        "baseline": analysis["baseline"]["jointPassingNails"],
        "E1": analysis["E1_globalRadial"]["bestJoint"],
        "E2": analysis["E2_perInstanceRadial"]["jointPassingNails"],
        "E3": [row["jointPassingNails"] for row in analysis["E3_truthAmbiguity"]["rows"]],
        "E4": analysis["E4_globalTranslation"]["bestJoint"],
        "fidelity": analysis["fidelity"],
    }


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        if sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    plan_path = Path(report["inputs"]["plan"]["path"])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    replay = analyze(plan)
    digest = canonical_sha256(replay)
    if digest != report["analysisSha256"]:
        raise ValueError("重放分析哈希不一致")
    return {"ok": True, "decision": "verified_contour_calibration_ceiling", "result": report["decision"], "analysisSha256": digest}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.output:
            parser.error("运行审计需要--plan与--output")
        print(json.dumps(run(args.plan, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
