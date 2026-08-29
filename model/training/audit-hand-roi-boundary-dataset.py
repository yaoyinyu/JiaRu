#!/usr/bin/env python3
"""Independently replay a train-only all-nails ROI candidate dataset."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any


APPROVED_DECISION = "approved_hand_roi_candidate_training_input"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def load_script(name: str, file_name: str) -> ModuleType:
    path = Path(__file__).with_name(file_name)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inventory(root: Path, excluded: set[Path]) -> list[dict[str, str]]:
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.name.endswith(".cache")
        and path.resolve() not in excluded
    ]


def count_nonempty_labels(directory: Path) -> tuple[int, int]:
    positive_images = 0
    masks = 0
    for path in sorted(directory.glob("*.txt")):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            positive_images += 1
            masks += len(lines)
    return positive_images, masks


def build_report(materialization_path: Path) -> dict[str, Any]:
    materialization = read_json(materialization_path)
    if materialization.get("decision") != "candidate_hand_roi_dataset_materialized_pending_independent_audit":
        raise ValueError("materialization report has an unexpected decision")
    output_root = Path(str(materialization.get("outputDir", ""))).resolve()
    dataset_yaml = Path(str(materialization.get("datasetYaml", ""))).resolve()
    if dataset_yaml != output_root / "dataset.yaml" or not dataset_yaml.is_file():
        raise ValueError("materialized dataset.yaml is missing or outside output root")
    inputs = materialization.get("inputs") or {}
    parent_root = Path(str(inputs.get("datasetRoot", ""))).resolve()
    parent_audit_path = Path(str(inputs.get("candidateInputAudit", ""))).resolve()
    if sha256_file(parent_audit_path) != inputs.get("candidateInputAuditSha256"):
        raise ValueError("parent candidate-input audit hash drift")

    parent_auditor = load_script("candidate_input_auditor", "audit-candidate-training-input.py")
    parent_audit = parent_auditor.verify_approved_report(
        parent_audit_path, parent_root / "dataset.yaml"
    )
    if parent_audit.get("datasetFilesSha256") != inputs.get("parentDatasetFilesSha256"):
        raise ValueError("parent dataset inventory digest drift")

    lineage_evidence = materialization.get("lineage") or {}
    lineage_path = Path(str(lineage_evidence.get("path", ""))).resolve()
    if lineage_path != output_root / "metadata" / "hand-roi-lineage-v1.json":
        raise ValueError("lineage path is not canonical")
    if sha256_file(lineage_path) != lineage_evidence.get("sha256"):
        raise ValueError("lineage hash drift")
    lineage = read_json(lineage_path)
    items = lineage.get("items")
    if not isinstance(items, list) or canonical_sha256(items) != lineage.get("itemsSha256"):
        raise ValueError("lineage items digest drift")
    if lineage.get("itemsSha256") != lineage_evidence.get("itemsSha256"):
        raise ValueError("materialization does not bind lineage items")

    # Every non-YAML parent artifact must remain byte-identical in the derived dataset.
    for parent in sorted(parent_root.rglob("*")):
        if not parent.is_file() or parent.name.endswith(".cache") or parent.name == "dataset.yaml":
            continue
        relative = parent.relative_to(parent_root)
        derived = output_root / relative
        if not derived.is_file() or sha256_file(derived) != sha256_file(parent):
            raise ValueError(f"parent artifact is missing or changed: {relative.as_posix()}")

    materializer = load_script("hand_roi_materializer", "materialize-hand-roi-boundary-dataset.py")
    parameters = lineage.get("parameters") or {}
    output_stems: set[str] = set()
    total_roi_masks = 0
    scale_gains: list[float] = []
    with tempfile.TemporaryDirectory(prefix="candidate30-roi-replay-") as temporary_name:
        temporary = Path(temporary_name)
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError(f"lineage item {index} is not an object")
            parent_image = Path(str(item.get("parentImage", ""))).resolve()
            parent_label = Path(str(item.get("parentLabel", ""))).resolve()
            if parent_image.parent != parent_root / "images" / "train":
                raise ValueError(f"lineage item {index} parent image is not train-only")
            if parent_label.parent != parent_root / "labels" / "train":
                raise ValueError(f"lineage item {index} parent label is not train-only")
            if sha256_file(parent_image) != item.get("parentImageSha256"):
                raise ValueError(f"lineage item {index} parent image drift")
            if sha256_file(parent_label) != item.get("parentLabelSha256"):
                raise ValueError(f"lineage item {index} parent label drift")
            output_stem = str(item.get("outputStem", ""))
            if not output_stem or output_stem in output_stems:
                raise ValueError(f"lineage item {index} duplicate output stem")
            output_stems.add(output_stem)
            output_image = output_root / "images" / "train" / f"{output_stem}.png"
            output_label = output_root / "labels" / "train" / f"{output_stem}.txt"
            if sha256_file(output_image) != item.get("outputImageSha256"):
                raise ValueError(f"lineage item {index} output image drift")
            if sha256_file(output_label) != item.get("outputLabelSha256"):
                raise ValueError(f"lineage item {index} output label drift")
            expected_image = temporary / "expected.png"
            expected_label = temporary / "expected.txt"
            replay = materializer.build_roi(
                parent_image,
                parent_label,
                expected_image,
                expected_label,
                float(parameters.get("paddingRatio")),
                float(parameters.get("maximumCropAreaRatio")),
                int(parameters.get("minimumPolygonMarginPixels")),
            )
            if replay is None:
                raise ValueError(f"lineage item {index} no longer qualifies for an ROI")
            if sha256_file(expected_image) != sha256_file(output_image):
                raise ValueError(f"lineage item {index} image replay mismatch")
            if expected_label.read_bytes() != output_label.read_bytes():
                raise ValueError(f"lineage item {index} label replay mismatch")
            for key in ("cropBox", "cropSize", "polygonCount", "cropAreaRatio", "pixelScaleGain"):
                if replay.get(key) != item.get(key):
                    raise ValueError(f"lineage item {index} replay field mismatch: {key}")
            total_roi_masks += int(item.get("polygonCount", 0))
            scale_gains.append(float(item.get("pixelScaleGain", 0)))

    actual_roi_images = {
        path.stem
        for path in (output_root / "images" / "train").glob("*__handroi_v1.png")
    }
    actual_roi_labels = {
        path.stem
        for path in (output_root / "labels" / "train").glob("*__handroi_v1.txt")
    }
    if actual_roi_images != output_stems or actual_roi_labels != output_stems:
        raise ValueError("derived ROI files are missing or contain unbound extras")

    materialization_inventory = materialization.get("datasetFiles")
    if not isinstance(materialization_inventory, list):
        raise ValueError("materialization dataset inventory is missing")
    current_inventory = inventory(output_root, {materialization_path.resolve()})
    if current_inventory != materialization_inventory:
        raise ValueError("materialized dataset inventory changed")
    if canonical_sha256(current_inventory) != materialization.get("datasetFilesSha256"):
        raise ValueError("materialized dataset inventory digest mismatch")

    parent_counts = parent_audit.get("counts") or {}
    original_positive_images, original_masks = count_nonempty_labels(parent_root / "labels" / "train")
    derived_positive_images, derived_masks = count_nonempty_labels(output_root / "labels" / "train")
    hard_negatives = int(parent_counts.get("hardNegativeImages", -1))
    val_images = len(list((output_root / "images" / "val").glob("*")))
    test_images = len(list((output_root / "images" / "test").glob("*")))
    if original_positive_images != int(parent_counts.get("trainPositiveImages", -1)):
        raise ValueError("parent positive-image count disagrees with approved audit")
    if derived_positive_images != original_positive_images + len(items):
        raise ValueError("derived positive-image count is inconsistent")
    if derived_masks != original_masks + total_roi_masks:
        raise ValueError("derived mask count is inconsistent")
    if val_images != int(parent_counts.get("validationImages", -1)) or test_images != 0:
        raise ValueError("validation or test role changed")

    identities = [
        {
            "parentImageSha256": item["parentImageSha256"],
            "outputImageSha256": item["outputImageSha256"],
            "outputLabelSha256": item["outputLabelSha256"],
        }
        for item in items
    ]
    return {
        "schemaVersion": 1,
        "ok": True,
        "status": "PASS",
        "decision": APPROVED_DECISION,
        "candidateTrainingEligible": True,
        "trainingUse": "approved-for-candidate-training-only",
        "inputs": {
            "materializationReport": {
                "path": str(materialization_path),
                "sha256": sha256_file(materialization_path),
            },
            "parentCandidateInputReport": {
                "path": str(parent_audit_path),
                "sha256": sha256_file(parent_audit_path),
            },
            "validationDatasetYaml": parent_audit["inputs"]["validationDatasetYaml"],
        },
        "outputDir": str(output_root),
        "datasetYaml": str(dataset_yaml),
        "counts": {
            "trainImages": derived_positive_images + hard_negatives,
            "trainPositiveImages": derived_positive_images,
            "originalPositiveImages": original_positive_images,
            "derivedRoiImages": len(items),
            "hardNegativeImages": hard_negatives,
            "validationImages": val_images,
            "testImages": test_images,
            "positiveMasks": derived_masks,
            "originalPositiveMasks": original_masks,
            "derivedRoiMasks": total_roi_masks,
            "orphanFiles": 0,
        },
        "roi": {
            "itemsSha256": lineage["itemsSha256"],
            "identitiesSha256": canonical_sha256(identities),
            "minimumPixelScaleGain": round(min(scale_gains), 8) if scale_gains else None,
            "meanPixelScaleGain": round(sum(scale_gains) / len(scale_gains), 8) if scale_gains else None,
        },
        "datasetFilesSha256": materialization["datasetFilesSha256"],
        "allRolesSha256": canonical_sha256(
            {
                "parentAllRolesSha256": parent_audit["allRolesSha256"],
                "roiIdentities": identities,
            }
        ),
        "invariants": {
            "parentCandidateInputDeepReplayPassed": True,
            "allOriginalArtifactsByteIdenticalExceptDatasetYaml": True,
            "allParentPolygonsPreservedExactlyOnce": True,
            "roiImagesAndLabelsDeterministicallyReplayed": True,
            "validationUnchanged": True,
            "testSplitEmpty": True,
            "modelOutputNotUsed": True,
            "noOrphans": True,
        },
        "errors": [],
    }


def verify_approved_report(report_path: Path, dataset_yaml: Path) -> dict[str, Any]:
    existing = read_json(report_path)
    if existing.get("decision") != APPROVED_DECISION:
        raise ValueError("hand-ROI report is not approved")
    materialization_path = Path(str(existing["inputs"]["materializationReport"]["path"])).resolve()
    replay = build_report(materialization_path)
    if replay != existing:
        raise ValueError("hand-ROI candidate-input report does not match deep replay")
    if Path(str(replay["datasetYaml"])).resolve() != dataset_yaml.resolve():
        raise ValueError("hand-ROI report does not bind the requested dataset.yaml")
    return replay


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a candidate30 train-only hand ROI dataset.")
    parser.add_argument("--materialization-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--verify-report")
    args = parser.parse_args()
    if args.verify_report:
        report_path = Path(args.verify_report).resolve()
        report = read_json(report_path)
        verified = verify_approved_report(report_path, Path(str(report["datasetYaml"])))
        print(json.dumps({"ok": True, "decision": verified["decision"]}))
        return
    output = Path(args.output).resolve()
    report = build_report(Path(args.materialization_report).resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "decision": report["decision"], "output": str(output)}))


if __name__ == "__main__":
    main()
