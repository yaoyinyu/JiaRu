from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build auditable pair sheets for real-material near-duplicate review.")
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--corpus-audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--pairs-per-page", type=int, default=8)
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pixel_mae(left: Path, right: Path) -> tuple[float, float]:
    with Image.open(left) as image:
        left_ratio = image.width / image.height
        left_array = np.asarray(ImageOps.fit(image.convert("RGB"), (128, 128)), dtype=np.float32) / 255.0
    with Image.open(right) as image:
        right_ratio = image.width / image.height
        right_array = np.asarray(ImageOps.fit(image.convert("RGB"), (128, 128)), dtype=np.float32) / 255.0
    return float(np.abs(left_array - right_array).mean()), abs(left_ratio - right_ratio)


def thumbnail(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def draw_pair_page(path: Path, pairs: list[dict[str, object]], page_index: int) -> None:
    canvas = Image.new("RGB", (1800, 2200), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((24, 16), f"Near-duplicate review page {page_index:03d}", fill="black", font=font)
    for index, pair in enumerate(pairs):
        row = index // 2
        column = index % 2
        x = 24 + column * 888
        y = 60 + row * 525
        for side, key in enumerate(("leftPath", "rightPath")):
            image_path = Path(str(pair[key]))
            thumb = thumbnail(image_path, (410, 390))
            tx = x + side * 430 + (410 - thumb.width) // 2
            ty = y + (390 - thumb.height) // 2
            canvas.paste(thumb, (tx, ty))
        label = (
            f"{pair['pairId']} {pair['kind']} d={pair['distance']} mae={float(pair['pixelMae']):.4f}\n"
            f"L {pair['leftName'][:58]}\nR {pair['rightName'][:58]}"
        )
        draw.multiline_text((x, y + 400), label, fill="black", font=font, spacing=4)
    canvas.save(path, quality=92)


def main() -> None:
    args = build_parser().parse_args()
    if args.pairs_per_page <= 0 or args.pairs_per_page > 8:
        raise ValueError("--pairs-per-page must be between 1 and 8")
    authorization_path = Path(args.authorization).resolve()
    corpus_path = Path(args.corpus_audit).resolve()
    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {output_dir}")
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if authorization.get("ok") is not True or authorization.get("authorization", {}).get("decision") != "A":
        errors.append("near-duplicate review requires passing A authorization")
    candidate_root = Path(str(authorization.get("root", ""))).resolve()
    if corpus.get("ok") is not True or Path(str(corpus.get("root", ""))).resolve() != candidate_root:
        errors.append("corpus audit must pass and match the authorized candidate root")
    by_file = {str(entry.get("fileName")): entry for entry in authorization.get("entries", []) if isinstance(entry, dict)}
    if int(corpus.get("totals", {}).get("validImages", -1)) != len(by_file):
        errors.append("corpus audit count does not match authorization entries")

    pairs: list[dict[str, object]] = []
    raw_pairs: list[tuple[str, str, str, Path, int, str | None]] = []
    for item in corpus.get("nearDuplicatePairs", []):
        left_name = str(item.get("left", ""))
        right_name = str(item.get("right", ""))
        raw_pairs.append(("batch", left_name, right_name, candidate_root / right_name, int(item.get("distance", -1)), None))
    for item in corpus.get("comparisons", {}).get("nearMatches", []):
        left_name = str(item.get("candidate", ""))
        reference_root = Path(str(item.get("referenceRoot", ""))).resolve()
        right_name = str(item.get("reference", ""))
        raw_pairs.append(("cross-corpus", left_name, right_name, reference_root / right_name, int(item.get("distance", -1)), str(reference_root)))
    raw_pairs.sort(key=lambda item: (0 if item[0] == "cross-corpus" else 1, item[4], item[1], item[2]))

    for index, (kind, left_name, right_name, right_path, distance, reference_root) in enumerate(raw_pairs, start=1):
        left_entry = by_file.get(left_name)
        left_path = (candidate_root / left_name).resolve()
        if left_entry is None or not left_path.is_file() or not right_path.is_file():
            errors.append(f"near-duplicate pair path missing: {left_name} <-> {right_path}")
            continue
        if sha256_file(left_path) != left_entry.get("sha256"):
            errors.append(f"authorized candidate changed: {left_name}")
            continue
        mae, ratio_delta = pixel_mae(left_path, right_path)
        high_similarity = distance == 0 and mae <= 0.025 and ratio_delta <= 0.02
        right_entry = by_file.get(right_name) if kind == "batch" else None
        pairs.append(
            {
                "pairId": f"near-{index:04d}",
                "kind": kind,
                "leftName": left_name,
                "rightName": right_name,
                "leftPath": str(left_path),
                "rightPath": str(right_path.resolve()),
                "leftSourceGroup": left_entry.get("sourceGroup"),
                "rightSourceGroup": right_entry.get("sourceGroup") if right_entry else reference_root,
                "distance": distance,
                "pixelMae": mae,
                "aspectRatioDelta": ratio_delta,
                "highSimilarity": high_similarity,
                "recommendedReview": (
                    "exclude-new-candidate-if-visual-match-confirms-existing-corpus-duplicate"
                    if kind == "cross-corpus" and high_similarity
                    else "keep-one-if-visual-match-confirms-batch-duplicate"
                    if kind == "batch" and high_similarity
                    else "manual-visual-review"
                ),
                "decision": "",
                "note": "",
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    if errors:
        report = {"ok": False, "decision": "rejected_near_duplicate_review_build", "errors": errors}
        (output_dir / "near-duplicate-review-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise SystemExit(1)

    csv_path = output_dir / "near-duplicate-review.csv"
    fieldnames = [
        "pairId", "kind", "leftName", "rightName", "leftSourceGroup", "rightSourceGroup",
        "distance", "pixelMae", "aspectRatioDelta", "highSimilarity", "recommendedReview", "decision", "note",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: pair[key] for key in fieldnames} for pair in pairs)

    page_paths: list[dict[str, object]] = []
    for start in range(0, len(pairs), args.pairs_per_page):
        page_index = start // args.pairs_per_page + 1
        page_path = output_dir / f"near-duplicate-page-{page_index:03d}.jpg"
        draw_pair_page(page_path, pairs[start : start + args.pairs_per_page], page_index)
        page_paths.append({"path": str(page_path), "sha256": sha256_file(page_path), "pairs": min(args.pairs_per_page, len(pairs) - start)})

    unique_candidates = sorted({str(pair["leftName"]) for pair in pairs} | {str(pair["rightName"]) for pair in pairs if pair["kind"] == "batch"})
    report = {
        "ok": True,
        "decision": "near_duplicate_visual_review_required",
        "inputs": {
            "authorization": str(authorization_path),
            "authorizationSha256": sha256_file(authorization_path),
            "corpusAudit": str(corpus_path),
            "corpusAuditSha256": sha256_file(corpus_path),
        },
        "counts": {
            "pairs": len(pairs),
            "batchPairs": sum(pair["kind"] == "batch" for pair in pairs),
            "crossCorpusPairs": sum(pair["kind"] == "cross-corpus" for pair in pairs),
            "highSimilarityPairs": sum(bool(pair["highSimilarity"]) for pair in pairs),
            "flaggedCandidates": len(unique_candidates),
            "pages": len(page_paths),
        },
        "policy": {
            "dhashAloneCannotExclude": True,
            "originalResolutionVisualConfirmationRequired": True,
            "existingReleaseTestAndTrainingSourcesMustRemainIsolated": True,
        },
        "reviewCsv": str(csv_path),
        "reviewCsvSha256": sha256_file(csv_path),
        "pages": page_paths,
        "errors": [],
    }
    (output_dir / "near-duplicate-review-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputDir": str(output_dir), "ok": True, **report["counts"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
