#!/usr/bin/env python3
"""Fixed 512-input, one-pass source-32 watermark sensitivity probe.

This is train-role diagnostic evidence only; no test/holdout or threshold search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def infer(model: YOLO, path: Path) -> tuple[dict, np.ndarray]:
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"undecodable {path}")
    result = model.predict(source=image, imgsz=512, conf=0.25, iou=0.7,
                           device="cpu", retina_masks=True, verbose=False)[0]
    boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else np.empty((0, 4))
    confidences = result.boxes.conf.cpu().numpy() if result.boxes is not None else np.empty(0)
    masks = result.masks.data.cpu().numpy() > 0.5 if result.masks is not None else np.zeros((0, *image.shape[:2]), bool)
    if masks.shape[1:] != image.shape[:2]:
        raise ValueError("mask dimensions differ from source")
    union = np.any(masks, axis=0) if len(masks) else np.zeros(image.shape[:2], bool)
    return {"instanceCount": len(boxes),
            "boxesXyxy": np.round(boxes, 3).tolist(),
            "confidences": np.round(confidences, 6).tolist(),
            "maskPixelCounts": [int(m.sum()) for m in masks],
            "unionMaskPixels": int(union.sum())}, union


def build(variant_report_path: Path, visual_audit_path: Path,
          weight_path: Path) -> dict:
    variants = json.loads(variant_report_path.read_text(encoding="utf-8"))
    visual = json.loads(visual_audit_path.read_text(encoding="utf-8"))
    if (not variants["ok"] or variants["nailPixelsChanged"] != 0 or
            variants["sourceOrdinal"] != 32 or
            visual["decision"] !=
            "five_logos_verified_source032_v3_visual_variants_only_model_and_masks_pending" or
            visual["inputs"]["variantReports"][2]["sha256"] != sha(variant_report_path) or
            visual["source32ModelAblationComplete"] or
            visual["source32ShortcutAbsenceProven"] or
            visual["trainingUse"] != "prohibited"):
        raise ValueError("variant contract mismatch")
    for item in variants["variants"].values():
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("variant bytes drift")
    model = YOLO(str(weight_path))
    rows = {}
    unions = {}
    for name in ("original", "remove", "occlude", "blur", "move_position"):
        rows[name], unions[name] = infer(model, Path(variants["variants"][name]["path"]))
    original = unions["original"]
    comparisons = {}
    for name in ("remove", "occlude", "blur", "move_position"):
        union = unions[name]
        total = int((original | union).sum())
        comparisons[name] = {
            "instanceCountDelta": rows[name]["instanceCount"] - rows["original"]["instanceCount"],
            "originalUnionIoU": round(float((original & union).sum() / total), 8) if total else 1.0,
            "unionSymmetricDifferencePixels": int((original ^ union).sum()),
        }
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_frozen_development_weight_watermark_probe_diagnostic_only",
            "inputs": {"sourceScript": bind(Path(__file__)),
                       "variantBuild": bind(variant_report_path),
                       "visualAudit": bind(visual_audit_path),
                       "frozenWeight": bind(weight_path)},
            "contract": {"imgsz": 512, "conf": 0.25, "iou": 0.7,
                         "device": "cpu", "retinaMasks": True, "oneInferencePerVariant": True},
            "variantPredictions": rows, "comparisonsToOriginal": comparisons,
            "independentWatermarkShortcutExclusionProven": False,
            "newTrainingApprovedSources": 0, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-report", type=Path)
    parser.add_argument("--visual-audit", type=Path)
    parser.add_argument("--weight", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        old = json.loads(args.verify_report.read_text(encoding="utf-8"))
        for item in old["inputs"].values():
            if sha(Path(item["path"])) != item["sha256"]:
                raise ValueError("bound input drift")
        current = build(Path(old["inputs"]["variantBuild"]["path"]),
                        Path(old["inputs"]["visualAudit"]["path"]),
                        Path(old["inputs"]["frozenWeight"]["path"]))
        if current != old:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"],
                          "comparisonsToOriginal": current["comparisonsToOriginal"]}))
        return
    if not all((args.variant_report, args.visual_audit, args.weight, args.report)):
        parser.error("--variant-report, --visual-audit, --weight, --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.variant_report.resolve(), args.visual_audit.resolve(),
                   args.weight.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"],
                      "comparisonsToOriginal": report["comparisonsToOriginal"]}))


if __name__ == "__main__":
    main()
