#!/usr/bin/env python3
"""Create deterministic magnified review crops for source32 logo variants."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image


CORNER = (1010, 1385, 1080, 1440)
MOVED = (110, 885, 185, 945)
NAMES = ("original", "remove", "occlude", "blur", "move_position")


def install_read_only_ultralytics_image_check() -> None:
    from ultralytics.data import utils as data_utils

    def check_image_read_only(im_file: str) -> tuple[str, tuple[int, int]]:
        with Image.open(im_file) as image:
            image.verify()
        with Image.open(im_file) as image:
            image.load()
            shape = (int(image.height), int(image.width))
            image_format = str(image.format or "").lower()
        if shape[0] <= 9 or shape[1] <= 9 or image_format not in data_utils.IMG_FORMATS:
            raise AssertionError(f"invalid read-only image: {im_file}")
        return "", shape

    data_utils.check_image = check_image_read_only
    if data_utils.verify_image.__globals__.get("check_image") is not check_image_read_only:
        raise RuntimeError("failed to install read-only image check")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> None:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build(variant_path: Path, output_dir: Path, *, verify: bool) -> dict:
    install_read_only_ultralytics_image_check()
    variant = load(variant_path)
    if (variant.get("decision") !=
            "source032_four_logo_variants_built_visual_and_model_ablation_pending" or
            variant["sourceOrdinal"] != 32 or variant["nailPixelsChanged"] != 0 or
            variant["trainingUse"] != "prohibited"):
        raise ValueError("source32 variant contract mismatch")
    if not verify:
        output_dir.mkdir(parents=True, exist_ok=True)
    crops = {}
    for name in NAMES:
        checked(variant["variants"][name])
        with Image.open(variant["variants"][name]["path"]) as image:
            if image.size != (1080, 1440):
                raise ValueError("variant image size drift")
            crop = image.crop(CORNER).resize((560, 440))
            stream = io.BytesIO()
            crop.save(stream, format="PNG")
        path = output_dir / f"review-{name}-corner-8x.png"
        if verify:
            if not path.is_file() or sha(path) != hashlib.sha256(stream.getvalue()).hexdigest():
                raise ValueError(f"crop drift: {name}")
        else:
            if path.exists():
                raise FileExistsError(path)
            path.write_bytes(stream.getvalue())
        crops[name] = bind(path)
    with Image.open(variant["variants"]["move_position"]["path"]) as image:
        crop = image.crop(MOVED).resize((600, 480))
        stream = io.BytesIO()
        crop.save(stream, format="PNG")
    moved_path = output_dir / "review-move-position-target-8x.png"
    if verify:
        if not moved_path.is_file() or sha(moved_path) != hashlib.sha256(stream.getvalue()).hexdigest():
            raise ValueError("moved target crop drift")
    else:
        if moved_path.exists():
            raise FileExistsError(moved_path)
        moved_path.write_bytes(stream.getvalue())
    return {"schemaVersion": 1, "ok": True,
            "decision": "source032_variant_review_crops_bound_visual_decision_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "variantReport": bind(variant_path)},
            "cornerCrops": crops, "movedTargetCrop": bind(moved_path),
            "sourceOrdinal": 32, "originalResolutionVisualApproval": False,
            "shortcutAbsenceProven": False, "trainingUse": "prohibited"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        prior = load(args.verify_report)
        for binding in prior["inputs"].values():
            checked(binding)
        current = build(Path(prior["inputs"]["variantReport"]["path"]),
                        Path(prior["cornerCrops"]["original"]["path"]).parent,
                        verify=True)
        if current != prior:
            raise SystemExit("reconstruction_mismatch")
        print(json.dumps({"ok": True, "decision": current["decision"]}))
        return
    if not all((args.variant_report, args.output_dir, args.report)):
        parser.error("--variant-report, --output-dir and --report required")
    if args.report.exists():
        raise FileExistsError(args.report)
    report = build(args.variant_report.resolve(), args.output_dir.resolve(), verify=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"ok": True, "decision": report["decision"]}))


if __name__ == "__main__":
    main()
