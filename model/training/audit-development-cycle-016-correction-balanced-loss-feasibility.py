#!/usr/bin/env python3
"""审计训练期修正平衡BCE是否把梯度集中到粗预测错误像素。"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.util
import json
import os
import tempfile
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


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_module(file_name: str, module_name: str) -> Any:
    path = Path(__file__).resolve().with_name(file_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def validate_plan(plan: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    for label, binding in plan["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希不一致：{label}")
    ninth = json.loads(Path(plan["inputs"]["ninthReport"]["path"]).read_text(encoding="utf-8"))
    gain = json.loads(Path(plan["inputs"]["ninthGainAudit"]["path"]).read_text(encoding="utf-8"))
    feasibility = json.loads(Path(plan["inputs"]["staticFeasibilityReport"]["path"]).read_text(encoding="utf-8"))
    if ninth.get("decision") != "roi_dinov2_local_boundary_refiner_internal_pilot_fail" or ninth.get("completedEpochs") != 30:
        raise ValueError("第九轮冻结失败报告不一致")
    if gain.get("decision") != "local_boundary_refiner_not_broadly_effective_close_branch" or not gain.get("ok"):
        raise ValueError("第九轮逐实例关闭判决不一致")
    if feasibility.get("decision") != "local_boundary_refiner_static_feasible_pending_browser_runtime" or not feasibility.get("ok"):
        raise ValueError("局部边界修正器静态身份不一致")
    dataset_report = json.loads(Path(plan["inputs"]["datasetMaterializationReport"]["path"]).read_text(encoding="utf-8"))
    if dataset_report.get("datasetFilesSha256") != plan["datasetContract"]["requiredDatasetFilesSha256"]:
        raise ValueError("ROI v2文件树哈希不一致")
    review = json.loads(Path(plan["inputs"]["finalReview"]["path"]).read_text(encoding="utf-8"))
    if review.get("decision") != plan["datasetContract"]["requiredFinalReviewDecision"]:
        raise ValueError("ROI v2原分辨率全量审核未通过")
    return dataset_report, Path(dataset_report["outputDir"])


def correction_balanced_bce(final_logits: torch.Tensor, coarse_logits: torch.Tensor, truth: torch.Tensor, band: torch.Tensor) -> tuple[torch.Tensor, dict[str, Any]]:
    disagreement = band & ((coarse_logits >= 0) != (truth >= 0.5))
    agreement = band & ~disagreement
    per_pixel = F.binary_cross_entropy_with_logits(final_logits, truth, reduction="none")
    disagreement_count = disagreement.sum().clamp_min(1)
    agreement_count = agreement.sum().clamp_min(1)
    disagreement_mean = (per_pixel * disagreement).sum() / disagreement_count
    agreement_mean = (per_pixel * agreement).sum() / agreement_count
    loss = 0.5 * (disagreement_mean + agreement_mean)
    return loss, {
        "disagreementPixels": int(disagreement.sum()),
        "agreementPixels": int(agreement.sum()),
        "disagreementMeanBce": float(disagreement_mean.detach()),
        "agreementMeanBce": float(agreement_mean.detach()),
    }


def gradient_masses(gradient: torch.Tensor, disagreement: torch.Tensor, agreement: torch.Tensor, band: torch.Tensor) -> dict[str, float]:
    absolute = gradient.abs()
    disagreement_mass = float(absolute[disagreement].sum())
    agreement_mass = float(absolute[agreement].sum())
    band_mass = float(absolute[band].sum())
    return {
        "disagreement": disagreement_mass,
        "agreement": agreement_mass,
        "band": band_mass,
        "outsideBand": float(absolute[~band].sum()),
    }


def compute(plan: dict[str, Any]) -> dict[str, Any]:
    dataset_report, dataset_root = validate_plan(plan)
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    records = [row for row in manifest["records"] if row["split"] == "val"]
    required = int(plan["datasetContract"]["requiredValidationInstances"])
    if len(records) != required:
        raise ValueError("ROI v2验证实例数不一致")
    guards = load_module("train-yolo-seg.py", "cycle016_correction_loss_guard")
    materializer = load_module("materialize-development-cycle-016-roi-dataset-v2.py", "cycle016_correction_loss_materializer")
    base = load_module("train-development-cycle-016-roi-segformer-pilot.py", "cycle016_correction_loss_dataset")
    architecture = load_module("audit-development-cycle-016-local-boundary-refiner-feasibility.py", "cycle016_correction_loss_architecture")
    soft_loss = load_module("audit-development-cycle-016-soft-boundary-f1-feasibility.py", "cycle016_correction_loss_base")
    guards.install_read_only_ultralytics_image_check()
    removed_before = guards.remove_ultralytics_label_caches(dataset_root)
    cleanup = lambda: guards.remove_ultralytics_label_caches(dataset_root)
    atexit.register(cleanup)
    feasibility_plan = json.loads(Path(plan["inputs"]["staticFeasibilityPlan"]["path"]).read_text(encoding="utf-8"))
    model = architecture.load_model(feasibility_plan)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("梯度归因预注册为CUDA")
    coarse_model = model.coarse.to(device).eval()
    dataset = base.RoiDataset(dataset_root, records, training=False, seed=1605)
    loader = DataLoader(dataset, batch_size=2, shuffle=False, num_workers=0, pin_memory=True)
    base_masses = {key: 0.0 for key in ("disagreement", "agreement", "band", "outsideBand")}
    proposed_masses = {key: 0.0 for key in base_masses}
    disagreement_pixels = 0
    agreement_pixels = 0
    perfect_losses: list[float] = []
    identities: list[str] = []
    try:
        for images, truth, batch_identities in loader:
            images = images.to(device, non_blocking=True)
            truth = truth.to(device, non_blocking=True)
            with torch.no_grad(), torch.amp.autocast(device_type="cuda"):
                coarse = coarse_model(pixel_values=images).float()
            band = architecture.fixed_boundary_band(coarse, int(feasibility_plan["architecture"]["bandRadiusPixels"]))
            disagreement = band & ((coarse >= 0) != (truth >= 0.5))
            agreement = band & ~disagreement
            disagreement_pixels += int(disagreement.sum())
            agreement_pixels += int(agreement.sum())
            base_logits = coarse.detach().requires_grad_(True)
            base_value, _ = soft_loss.soft_boundary_f1_loss(base_logits, truth, plan["loss"])
            base_gradient = torch.autograd.grad(base_value, base_logits)[0]
            for key, value in gradient_masses(base_gradient, disagreement, agreement, band).items():
                base_masses[key] += value
            proposed_logits = coarse.detach().requires_grad_(True)
            proposed_base, _ = soft_loss.soft_boundary_f1_loss(proposed_logits, truth, plan["loss"])
            correction, _ = correction_balanced_bce(proposed_logits, coarse, truth, band)
            proposed_value = proposed_base + float(plan["loss"]["correctionBalancedWeight"]) * correction
            proposed_gradient = torch.autograd.grad(proposed_value, proposed_logits)[0]
            for key, value in gradient_masses(proposed_gradient, disagreement, agreement, band).items():
                proposed_masses[key] += value
            perfect_logits = torch.where(truth >= 0.5, torch.full_like(truth, 20.0), torch.full_like(truth, -20.0))
            perfect_correction, _ = correction_balanced_bce(perfect_logits, coarse, truth, band)
            perfect_losses.append(float(perfect_correction))
            identities.extend(str(value) for value in batch_identities)
    finally:
        del coarse_model, model
        torch.cuda.empty_cache()
        removed_after = guards.remove_ultralytics_label_caches(dataset_root)
    identity_match = len(identities) == required and identities == [str(row["id"]) for row in records]
    if not identity_match:
        return {"decision": "reconstruction_mismatch", "identityOrderMatches": False, "recordCount": len(identities)}
    base_fraction = base_masses["disagreement"] / max(base_masses["band"], 1.0e-20)
    proposed_fraction = proposed_masses["disagreement"] / max(proposed_masses["band"], 1.0e-20)
    concentration_ratio = proposed_fraction / max(base_fraction, 1.0e-20)
    gate = plan["gradientGate"]
    checks = {
        "proposedGradientConcentrated": proposed_fraction >= float(gate["minimumProposedGradientFractionOnDisagreementPixelsWithinBand"]),
        "concentrationRatio": concentration_ratio >= float(gate["minimumConcentrationRatioVersusBase"]),
        "agreementPreservationGradient": proposed_masses["agreement"] > 0,
        "allGradientsFinite": all(np.isfinite(value) for value in [*base_masses.values(), *proposed_masses.values(), base_fraction, proposed_fraction, concentration_ratio]),
        "perfectTarget": max(perfect_losses) <= float(gate["maximumPerfectTargetCorrectionBalancedBce"]),
        "allValidationInstances": len(identities) == int(gate["requiredEveryValidationInstanceCovered"]),
    }
    integrity = materializer.verify(Path(plan["inputs"]["datasetMaterializationReport"]["path"]))
    checks["datasetIntegrity"] = integrity["ok"] and integrity["datasetFilesSha256"] == plan["datasetContract"]["requiredDatasetFilesSha256"]
    decision = "correction_balanced_loss_gradient_reachable_for_tenth_pilot" if all(checks.values()) else "correction_balanced_loss_not_reachable_no_training"
    atexit.unregister(cleanup)
    return {
        "decision": decision,
        "identityOrderMatches": True,
        "recordCount": len(identities),
        "identityOrderSha256": canonical_sha256(identities),
        "pixels": {"disagreementWithinBand": disagreement_pixels, "agreementWithinBand": agreement_pixels, "disagreementFractionWithinBand": disagreement_pixels / (disagreement_pixels + agreement_pixels)},
        "baseGradientMass": base_masses,
        "proposedGradientMass": proposed_masses,
        "baseGradientFractionOnDisagreement": base_fraction,
        "proposedGradientFractionOnDisagreement": proposed_fraction,
        "concentrationRatio": concentration_ratio,
        "perfectTargetCorrectionBalancedBceMaximum": max(perfect_losses),
        "perfectTargetCorrectionBalancedBceMean": float(np.mean(perfect_losses)),
        "checks": checks,
        "datasetIntegrity": {"removedCachesBefore": removed_before, "removedCachesAfter": removed_after, "datasetFilesSha256After": integrity["datasetFilesSha256"], "verified": integrity["ok"]},
    }


def run(plan_path: Path, report_path: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    analysis = compute(plan)
    report = {"schemaVersion": 1, "ok": analysis["decision"] == "correction_balanced_loss_gradient_reachable_for_tenth_pilot", "decision": analysis["decision"], "inputs": {"plan": {"path": str(plan_path), "sha256": sha256_file(plan_path)}, **plan["inputs"]}, "singleChangedVariable": plan["singleChangedVariable"], "loss": plan["loss"], "gradientGate": plan["gradientGate"], "analysis": analysis, "analysisSha256": canonical_sha256(analysis), "errors": []}
    write_atomic(report_path, report)
    return report


def verify(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for label, binding in report["inputs"].items():
        path = Path(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise ValueError(f"输入哈希漂移：{label}")
    plan = json.loads(Path(report["inputs"]["plan"]["path"]).read_text(encoding="utf-8"))
    replay = compute(plan)
    if replay != report["analysis"] or canonical_sha256(replay) != report["analysisSha256"]:
        raise ValueError("修正平衡损失梯度归因重放不一致")
    allowed = {"correction_balanced_loss_gradient_reachable_for_tenth_pilot", "correction_balanced_loss_not_reachable_no_training"}
    if report.get("decision") not in allowed or bool(report.get("ok")) != (report.get("decision") == "correction_balanced_loss_gradient_reachable_for_tenth_pilot"):
        raise ValueError("修正平衡损失报告结论与合同不一致")
    return {"ok": True, "decision": f"verified_{report['decision']}", "analysis": replay}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        print(json.dumps(verify(args.verify_report.resolve()), ensure_ascii=False, indent=2))
    else:
        if not args.plan or not args.report:
            parser.error("审计需要--plan与--report")
        result = run(args.plan.resolve(), args.report.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
