#!/usr/bin/env python3
"""冻结第十轮权重，零优化步审计单变量边界权重的错误像素梯度。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(file_name: str, name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gradient_mass(gradient: np.ndarray, truth: np.ndarray, error: np.ndarray) -> tuple[float, float]:
    desired = np.where(truth, -1.0, 1.0)
    values = gradient[error]
    directions = desired[error]
    return float(np.abs(values).sum()), float(np.abs(values[directions * values > 0]).sum())


def measure(plan_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schemaVersion") != 1 or plan["scope"] != {"trainOnly": True, "optimizerSteps": 0, "valTestHoldoutRead": False}:
        raise ValueError("审计范围合同不符")
    for name, binding in plan["inputs"].items():
        if not Path(binding["path"]).is_file() or sha256_file(Path(binding["path"])) != binding["sha256"]:
            raise ValueError(f"冻结输入哈希漂移：{name}")
    microfit = json.loads(Path(plan["inputs"]["microfitReport"]["path"]).read_text(encoding="utf-8"))
    topology = json.loads(Path(plan["inputs"]["errorTopologyReport"]["path"]).read_text(encoding="utf-8"))
    microfit_plan = json.loads(Path(plan["inputs"]["microfitPlan"]["path"]).read_text(encoding="utf-8"))
    if microfit.get("decision") != "soft_boundary_iou_train_only_microfit_fail_no_full_pilot" or topology.get("decision") != "train_only_error_topology_diagnostic":
        raise ValueError("前序失败或拓扑证据身份不符")
    if microfit["inputs"]["finalWeights"]["sha256"] != plan["inputs"]["finalWeights"]["sha256"]:
        raise ValueError("冻结权重不符")
    selected_ids = microfit["dataset"]["selectedTrainIds"]
    if selected_ids != topology["dataset"]["selectedTrainIds"] or selected_ids != microfit_plan["dataset"]["selectedTrainIds"] or len(selected_ids) != 32:
        raise ValueError("32例名单不一致")
    baseline_weight = float(microfit_plan["loss"]["boundaryWeight"])
    candidate_weight = float(plan["singleChangedVariable"]["candidateBoundaryWeight"])
    if baseline_weight != 0.2 or candidate_weight != 1.0 or plan["singleChangedVariable"]["name"] != "boundaryWeight":
        raise ValueError("唯一变量不是预注册0.2→1.0")
    if microfit_plan["training"]["scoreThreshold"] != 0.5:
        raise ValueError("冻结阈值漂移")
    materialization_path = Path(plan["inputs"]["materializationReport"]["path"])
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    root = Path(materialization["outputDir"])
    guards = load_module("train-yolo-seg.py", "cycle016_weight_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_weight_materializer")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(root)
    atexit.register(cleanup)
    before = materializer.verify(materialization_path)
    if not before["ok"] or before["datasetFilesSha256"] != microfit_plan["dataset"]["datasetFilesSha256"]:
        raise ValueError("ROI v2输入树重放失败")
    rows = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["records"]
    by_id = {row["id"]: row for row in rows if row["split"] == "train"}
    if any(identity not in by_id for identity in selected_ids):
        raise ValueError("train-only身份缺失")
    selected = [by_id[identity] for identity in selected_ids]
    if len({row["sourceGroup"] for row in selected}) != 32:
        raise ValueError("来源组不互异")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_weight_base")
    loss_module = load_module("development-cycle-016-soft-boundary-iou.py", "cycle016_weight_loss")
    auditor = load_module("audit-development-cycle-016-bidirectional-highres-feasibility.py", "cycle016_weight_model")
    dataset = base.RoiDataset(root, selected, training=False, seed=int(microfit_plan["training"]["seed"]))
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0)
    model = auditor.load_model(microfit_plan).cuda().eval()
    checkpoint = torch.load(Path(plan["inputs"]["finalWeights"]["path"]), map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint["model"], strict=True)
    torch.cuda.reset_peak_memory_stats()
    per_instance: list[dict[str, Any]] = []
    for images, masks, identities in loader:
        truth = masks.cuda()
        with torch.no_grad(), torch.amp.autocast(device_type="cuda"):
            frozen_logits = model(images.cuda())
        logits = frozen_logits.detach().float().requires_grad_(True)
        probability = torch.sigmoid(logits)
        dimensions = (1, 2, 3)
        bce = F.binary_cross_entropy_with_logits(logits, truth)
        intersection = (probability * truth).sum(dim=dimensions)
        dice = 1.0 - ((2.0 * intersection + 1.0) / (probability.sum(dim=dimensions) + truth.sum(dim=dimensions) + 1.0)).mean()
        boundary = 1.0 - loss_module.soft_boundary_iou_per_instance(probability, truth, microfit_plan["loss"]).mean()
        gradient_base = torch.autograd.grad(bce + dice, logits, retain_graph=True)[0]
        gradient_boundary = torch.autograd.grad(boundary, logits)[0]
        if not torch.isfinite(gradient_base).all() or not torch.isfinite(gradient_boundary).all():
            raise ValueError("梯度非有限")
        # 保真门必须沿用微拟合原评估的半精度 sigmoid，再独立以 fp32 求梯度。
        predictions = (torch.sigmoid(frozen_logits) >= 0.5).cpu().numpy()[:, 0]
        truths = truth.cpu().numpy()[:, 0] >= 0.5
        base_gradients = gradient_base.detach().cpu().numpy()[:, 0]
        boundary_gradients = gradient_boundary.detach().cpu().numpy()[:, 0]
        for identity, target, prediction, grad_base, grad_boundary in zip(
            identities, truths, predictions, base_gradients, boundary_gradients, strict=True
        ):
            expected = topology["perInstance"][len(per_instance)]
            if identity != expected["id"]:
                raise ValueError("reconstruction_mismatch: 逐例顺序")
            union = int(np.logical_or(target, prediction).sum())
            iou = float(np.logical_and(target, prediction).sum() / union) if union else 1.0
            boundary_iou, boundary_f1 = base.boundary_metrics(target, prediction, 2)
            disagreement = np.logical_xor(target, prediction)
            if any(abs(current - expected[key]) > 1e-8 for current, key in ((iou, "iou"), (boundary_iou, "boundaryIou"), (boundary_f1, "boundaryF1"))) or int(disagreement.sum()) != expected["error"]["disagreementPixels"]:
                raise ValueError(f"reconstruction_mismatch: {identity}指标/错分像素")
            base_abs, base_aligned = gradient_mass(grad_base, target, disagreement)
            boundary_abs, boundary_aligned = gradient_mass(grad_boundary, target, disagreement)
            old_abs, old_aligned = gradient_mass(grad_base + baseline_weight * grad_boundary, target, disagreement)
            new_abs, new_aligned = gradient_mass(grad_base + candidate_weight * grad_boundary, target, disagreement)
            per_instance.append({"id": identity, "jointFailure": not bool(microfit["perInstance"][len(per_instance)]["jointPass"]),
                                 "disagreementPixels": int(disagreement.sum()),
                                 "baseAbsoluteOnError": base_abs, "baseAlignedOnError": base_aligned,
                                 "boundaryAbsoluteOnError": boundary_abs, "boundaryAlignedOnError": boundary_aligned,
                                 "baselineAbsoluteOnError": old_abs, "baselineAlignedOnError": old_aligned,
                                 "candidateAbsoluteOnError": new_abs, "candidateAlignedOnError": new_aligned})
    after = materializer.verify(materialization_path)
    removed_after = guards.remove_ultralytics_label_caches(root)
    atexit.unregister(cleanup)
    if not after["ok"] or after["datasetFilesSha256"] != before["datasetFilesSha256"]:
        raise ValueError("ROI v2输出树重放失败")
    failures = [row for row in per_instance if row["jointFailure"]]
    if len(failures) != topology["summary"]["jointFailures"] or len(failures) != 19:
        raise ValueError("失败分母漂移")
    total = lambda key: sum(float(row[key]) for row in failures)
    old_aligned = total("baselineAlignedOnError")
    new_aligned = total("candidateAlignedOnError")
    boundary_abs = total("boundaryAbsoluteOnError")
    base_abs = total("baseAbsoluteOnError")
    new_abs = total("candidateAbsoluteOnError")
    improved_instances = sum(row["candidateAlignedOnError"] >= 1.1 * row["baselineAlignedOnError"] for row in failures)
    signal = {"jointFailureInstances": len(failures), "failedDisagreementPixels": sum(row["disagreementPixels"] for row in failures),
              "baselineBoundaryShareOnErrors": baseline_weight * boundary_abs / (base_abs + baseline_weight * boundary_abs),
              "candidateBoundaryShareOnErrors": candidate_weight * boundary_abs / (base_abs + candidate_weight * boundary_abs),
              "boundaryAlignedFractionOnErrors": total("boundaryAlignedOnError") / boundary_abs,
              "candidateAlignedFractionOnErrors": new_aligned / new_abs,
              "candidateAlignedGradientGain": new_aligned / old_aligned,
              "instancesWithAtLeast1p1AlignedGain": improved_instances,
              "cudaPeakAllocatedBytesBatch2": int(torch.cuda.max_memory_allocated())}
    gates = plan["gates"]
    passed = (signal["candidateBoundaryShareOnErrors"] >= gates["minimumCandidateBoundaryShareOnErrors"] and
              signal["boundaryAlignedFractionOnErrors"] >= gates["minimumBoundaryAlignedFractionOnErrors"] and
              signal["candidateAlignedFractionOnErrors"] >= gates["minimumCandidateAlignedFractionOnErrors"] and
              signal["candidateAlignedGradientGain"] >= gates["minimumAlignedGradientGain"] and
              improved_instances >= gates["minimumImprovedFailureInstances"] and
              signal["cudaPeakAllocatedBytesBatch2"] <= gates["maximumCudaPeakAllocatedBytesBatch2"])
    return {"schemaVersion": 1, "ok": passed,
            "decision": "boundary_weight_feasible_for_one_train_only_microfit" if passed else "boundary_weight_signal_gate_fail_no_training",
            "scope": plan["scope"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]},
            "singleChangedVariable": plan["singleChangedVariable"], "gates": gates,
            "dataset": {"selectedTrainIds": selected_ids, "sourceGroups": 32, "datasetFilesSha256After": after["datasetFilesSha256"],
                        "removedCachesBefore": removed_before, "removedCachesAfter": removed_after},
            "signal": signal, "perInstance": per_instance, "optimizerSteps": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = measure(Path(recorded["inputs"]["plan"]["path"]))
        ok = current == recorded
        print(json.dumps({"ok": ok, "decision": "verified_boundary_weight_gradient" if ok else "reconstruction_mismatch",
                          "auditDecision": current["decision"], "signal": current["signal"]}, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)
        return
    if not args.plan or not args.output:
        parser.error("--plan and --output are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    result = measure(args.plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "decision": result["decision"], "signal": result["signal"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
