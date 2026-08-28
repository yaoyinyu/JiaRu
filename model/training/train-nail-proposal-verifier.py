from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageFilter
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision.transforms import functional as vision


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ProposalVerifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        channels = (4, 24, 48, 96, 128)
        blocks: list[nn.Module] = []
        for index in range(len(channels) - 1):
            blocks.extend(
                [
                    nn.Conv2d(
                        channels[index], channels[index + 1], 3, stride=2, padding=1,
                        bias=False,
                    ),
                    nn.BatchNorm2d(channels[index + 1]),
                    nn.SiLU(inplace=True),
                    nn.Conv2d(
                        channels[index + 1], channels[index + 1], 3, padding=1,
                        groups=channels[index + 1], bias=False,
                    ),
                    nn.BatchNorm2d(channels[index + 1]),
                    nn.SiLU(inplace=True),
                ]
            )
        self.features = nn.Sequential(*blocks)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(channels[-1], 1))

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        features = self.features(image)
        return self.classifier(self.pool(features).flatten(1)).squeeze(1)


class ProposalDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    def __init__(self, root: Path, records: list[dict[str, Any]], augment: bool) -> None:
        self.root = root
        self.records = records
        self.augment = augment

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        record = self.records[index]
        with Image.open(self.root / record["crop"]) as source:
            image = source.convert("RGBA")
        if self.augment:
            if random.random() < 0.5:
                image = vision.hflip(image)
            rgb = image.convert("RGB")
            alpha = image.getchannel("A")
            if random.random() < 0.8:
                rgb = vision.adjust_brightness(rgb, random.uniform(0.8, 1.2))
                rgb = vision.adjust_contrast(rgb, random.uniform(0.8, 1.2))
                rgb = vision.adjust_saturation(rgb, random.uniform(0.75, 1.25))
            if random.random() < 0.15:
                rgb = rgb.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.2, 1.0)))
            rgb_array = np.asarray(rgb, dtype=np.uint8).copy()
            if random.random() < 0.35:
                height, width = rgb_array.shape[:2]
                cut_x = max(1, int(width * 0.12))
                cut_y = max(1, int(height * 0.12))
                if random.random() < 0.5:
                    rgb_array[height - cut_y :, width - cut_x :] = 0
                else:
                    patch = Image.fromarray(rgb_array[height - cut_y :, width - cut_x :])
                    patch = patch.filter(ImageFilter.GaussianBlur(radius=2.0))
                    rgb_array[height - cut_y :, width - cut_x :] = np.asarray(patch)
            rgba = np.dstack([rgb_array, np.asarray(alpha, dtype=np.uint8)])
        else:
            rgba = np.asarray(image, dtype=np.uint8)
        tensor = torch.from_numpy(rgba.copy()).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406, 0.0]).view(4, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225, 1.0]).view(4, 1, 1)
        tensor = (tensor - mean) / std
        return tensor, torch.tensor(float(record["label"]), dtype=torch.float32)


def split_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fit: list[dict[str, Any]] = []
    monitor: list[dict[str, Any]] = []
    for record in records:
        bucket = int(hashlib.sha256(record["imageSha256"].encode("ascii")).hexdigest()[:8], 16) % 10
        (monitor if bucket == 0 else fit).append(record)
    for name, subset in (("fit", fit), ("monitor", monitor)):
        labels = {int(record["label"]) for record in subset}
        if labels != {0, 1} or len(subset) < 40:
            raise ValueError(f"{name} split lacks both classes or is too small")
    return fit, monitor


def binary_auc(labels: list[int], scores: list[float]) -> float:
    positives = [score for label, score in zip(labels, scores, strict=True) if label == 1]
    negatives = [score for label, score in zip(labels, scores, strict=True) if label == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


@torch.inference_mode()
def evaluate(
    model: nn.Module, loader: DataLoader, device: torch.device
) -> dict[str, float | int]:
    model.eval()
    labels: list[int] = []
    scores: list[float] = []
    total_loss = 0.0
    criterion = nn.BCEWithLogitsLoss(reduction="sum")
    for images, targets in loader:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        logits = model(images)
        total_loss += float(criterion(logits, targets).item())
        scores.extend(torch.sigmoid(logits).cpu().tolist())
        labels.extend(targets.int().cpu().tolist())
    predictions = [int(score >= 0.5) for score in scores]
    return {
        "samples": len(labels),
        "loss": total_loss / max(1, len(labels)),
        "accuracyAt050": sum(a == b for a, b in zip(labels, predictions, strict=True)) / max(1, len(labels)),
        "auc": binary_auc(labels, scores),
        "positiveSamples": sum(labels),
        "negativeSamples": len(labels) - sum(labels),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the local nail proposal verifier.")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--seed", type=int, default=20260828)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    corpus_path = Path(args.corpus).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError(f"output must be fresh: {output}")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("decision") != "train_role_proposal_verifier_corpus_built":
        raise ValueError("proposal corpus is not approved for this training stage")
    policy = corpus.get("rolePolicy", {})
    if any(policy.get(key) is not False for key in (
        "valUsedForTraining", "testUsedForTraining", "holdoutUsedForTraining"
    )):
        raise ValueError("proposal corpus role isolation is invalid")
    records = corpus.get("records", [])
    if not isinstance(records, list) or not records:
        raise ValueError("proposal corpus records are missing")
    if corpus.get("recordsSha256") != hashlib.sha256(json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest():
        raise ValueError("proposal corpus records hash mismatch")
    for record in records:
        crop = corpus_path.parent / record["crop"]
        if sha256_file(crop) != record["cropSha256"]:
            raise ValueError(f"proposal crop drift: {crop}")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    torch.backends.cudnn.benchmark = True
    fit_records, monitor_records = split_records(records)
    fit_dataset = ProposalDataset(corpus_path.parent, fit_records, augment=True)
    monitor_dataset = ProposalDataset(corpus_path.parent, monitor_records, augment=False)
    class_counts = [
        sum(int(record["label"]) == label for record in fit_records) for label in (0, 1)
    ]
    sample_weights = [1.0 / class_counts[int(record["label"])] for record in fit_records]
    generator = torch.Generator().manual_seed(args.seed)
    sampler = WeightedRandomSampler(
        sample_weights, num_samples=len(fit_records), replacement=True, generator=generator
    )
    fit_loader = DataLoader(
        fit_dataset, batch_size=args.batch, sampler=sampler, num_workers=args.workers,
        pin_memory=True, persistent_workers=args.workers > 0,
    )
    monitor_loader = DataLoader(
        monitor_dataset, batch_size=args.batch * 2, shuffle=False, num_workers=args.workers,
        pin_memory=True, persistent_workers=args.workers > 0,
    )
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = ProposalVerifier().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))
    criterion = nn.BCEWithLogitsLoss()
    output.mkdir(parents=True)
    best_path = output / "best.pt"
    history: list[dict[str, Any]] = []
    best_auc = -math.inf
    best_epoch = 0
    stale = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        loss_sum = 0.0
        samples = 0
        for images, targets in fit_loader:
            images = images.to(device, non_blocking=True)
            targets = targets.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item()) * len(targets)
            samples += len(targets)
        scheduler.step()
        metrics = evaluate(model, monitor_loader, device)
        row = {
            "epoch": epoch,
            "fitLoss": loss_sum / max(1, samples),
            "learningRate": optimizer.param_groups[0]["lr"],
            "monitor": metrics,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))
        auc = float(metrics["auc"])
        if auc > best_auc + 1e-5:
            best_auc = auc
            best_epoch = epoch
            stale = 0
            torch.save({
                "schemaVersion": 1,
                "model": model.state_dict(),
                "architecture": "jiaru-proposal-verifier-cnn-v1",
                "inputShape": [1, 4, 96, 96],
                "epoch": epoch,
                "monitor": metrics,
                "corpusSha256": sha256_file(corpus_path),
            }, best_path)
        else:
            stale += 1
            if stale >= args.patience:
                break

    checkpoint = torch.load(best_path, map_location="cpu", weights_only=False)
    model = ProposalVerifier()
    model.load_state_dict(checkpoint["model"])
    model.eval()
    onnx_path = output / "proposal-verifier.onnx"
    torch.onnx.export(
        model,
        torch.zeros(1, 4, 96, 96),
        onnx_path,
        input_names=["image"],
        output_names=["logit"],
        dynamic_axes={"image": {0: "batch"}, "logit": {0: "batch"}},
        opset_version=18,
        dynamo=False,
    )
    report = {
        "schemaVersion": 1,
        "decision": "proposal_verifier_training_complete_requires_val30_joint_selection",
        "productionPromotion": False,
        "inputs": {
            "corpus": str(corpus_path),
            "corpusSha256": sha256_file(corpus_path),
            "recordsSha256": corpus["recordsSha256"],
        },
        "configuration": vars(args),
        "counts": {
            "fit": len(fit_records),
            "monitor": len(monitor_records),
            "fitPositive": class_counts[1],
            "fitNegative": class_counts[0],
        },
        "selection": {
            "bestEpoch": best_epoch,
            "bestMonitorAuc": best_auc,
            "internalMonitorOnly": True,
            "formalSelectionSplit": "val30-only",
        },
        "artifacts": {
            "checkpoint": str(best_path),
            "checkpointSha256": sha256_file(best_path),
            "onnx": str(onnx_path),
            "onnxSha256": sha256_file(onnx_path),
            "onnxBytes": onnx_path.stat().st_size,
        },
        "history": history,
    }
    report_path = output / "training-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "ok": True,
        "report": str(report_path),
        "reportSha256": sha256_file(report_path),
        "bestEpoch": best_epoch,
        "bestMonitorAuc": best_auc,
        "onnxSha256": report["artifacts"]["onnxSha256"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
