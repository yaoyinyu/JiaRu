from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from torch import nn

from nail_proposal_features import FEATURE_NAMES, extract_proposal_features


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_bucket(image_sha256: str) -> int:
    return int(hashlib.sha256(image_sha256.encode("ascii")).hexdigest()[:8], 16) % 10


class LinearFeatureVerifier(nn.Module):
    def __init__(self, mean: np.ndarray, scale: np.ndarray, weight: np.ndarray, bias: float) -> None:
        super().__init__()
        self.register_buffer("mean", torch.from_numpy(mean.astype(np.float32)))
        self.register_buffer("scale", torch.from_numpy(scale.astype(np.float32)))
        self.linear = nn.Linear(len(FEATURE_NAMES), 1)
        with torch.no_grad():
            self.linear.weight.copy_(torch.from_numpy(weight.astype(np.float32)).view(1, -1))
            self.linear.bias.copy_(torch.tensor([bias], dtype=torch.float32))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.linear((features - self.mean) / self.scale).squeeze(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train an interpretable nail proposal feature verifier.")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--c", type=float, default=0.25)
    args = parser.parse_args()
    corpus_path = Path(args.corpus).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output must be fresh: {output}")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    policy = corpus.get("rolePolicy", {})
    if policy.get("valUsedForTraining") is not False or policy.get("testUsedForTraining") is not False or policy.get("holdoutUsedForTraining") is not False:
        raise ValueError("corpus role isolation is invalid")
    features: list[np.ndarray] = []
    labels: list[int] = []
    buckets: list[int] = []
    for record in corpus["records"]:
        crop_path = corpus_path.parent / record["crop"]
        if sha256_file(crop_path) != record["cropSha256"]:
            raise ValueError(f"crop drift: {crop_path}")
        with Image.open(crop_path) as source:
            rgba = np.asarray(source.convert("RGBA"), dtype=np.uint8)
        features.append(extract_proposal_features(rgba, float(record["predictionScore"])))
        labels.append(int(record["label"]))
        buckets.append(split_bucket(record["imageSha256"]))
    matrix = np.stack(features)
    target = np.asarray(labels, dtype=np.int64)
    monitor = np.asarray(buckets) == 0
    fit = ~monitor
    scaler = StandardScaler().fit(matrix[fit])
    classifier = LogisticRegression(
        C=args.c, class_weight="balanced", max_iter=2000, random_state=20260828
    ).fit(scaler.transform(matrix[fit]), target[fit])
    monitor_scores = classifier.predict_proba(scaler.transform(matrix[monitor]))[:, 1]
    monitor_auc = float(roc_auc_score(target[monitor], monitor_scores))
    monitor_accuracy = float(accuracy_score(target[monitor], monitor_scores >= 0.5))
    output.mkdir(parents=True)
    model = LinearFeatureVerifier(
        scaler.mean_, scaler.scale_, classifier.coef_[0], float(classifier.intercept_[0])
    ).eval()
    onnx_path = output / "proposal-feature-verifier.onnx"
    torch.onnx.export(
        model, torch.zeros(2, len(FEATURE_NAMES)), onnx_path,
        input_names=["features"], output_names=["logit"],
        dynamic_axes={"features": {0: "batch"}, "logit": {0: "batch"}},
        opset_version=18, dynamo=False,
    )
    coefficients = dict(zip(FEATURE_NAMES, classifier.coef_[0].tolist(), strict=True))
    report = {
        "schemaVersion": 1,
        "decision": "candidate27_feature_verifier_training_complete_requires_val30_joint_selection",
        "productionPromotion": False,
        "inputs": {"corpus": str(corpus_path), "corpusSha256": sha256_file(corpus_path)},
        "configuration": {"C": args.c, "classWeight": "balanced", "seed": 20260828},
        "features": FEATURE_NAMES,
        "fit": {"samples": int(fit.sum()), "positives": int(target[fit].sum()), "negatives": int(fit.sum() - target[fit].sum())},
        "monitor": {"samples": int(monitor.sum()), "auc": monitor_auc, "accuracyAt050": monitor_accuracy, "internalOnly": True},
        "model": {
            "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
            "coefficients": coefficients, "bias": float(classifier.intercept_[0]),
            "onnx": str(onnx_path), "onnxSha256": sha256_file(onnx_path), "onnxBytes": onnx_path.stat().st_size,
        },
        "formalSelectionSplit": "val30-only",
    }
    report_path = output / "training-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "report": str(report_path), "reportSha256": sha256_file(report_path), "monitor": report["monitor"], "onnxSha256": report["model"]["onnxSha256"], "onnxBytes": report["model"]["onnxBytes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
