#!/usr/bin/env python3
"""Rebuild untinted original-pixel old/new crops for shard-003 SAM second pass."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Polygon


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound file drift: {path}")
    return path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def polygons(path: Path, width: int, height: int) -> list[Polygon]:
    shapes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = [float(x) for x in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2:
            raise ValueError("old label structure drift")
        shapes.append(Polygon([(values[i] * width, values[i + 1] * height)
                               for i in range(1, len(values), 2)]))
    return shapes


def render(image: Image.Image, old: Polygon, new: Polygon, box: list[int]) -> tuple[Image.Image, Image.Image]:
    raw = image.crop(tuple(box))
    outline = raw.copy()
    pen = ImageDraw.Draw(outline)
    for polygon, color in ((old, (255, 20, 20)), (new, (20, 255, 20))):
        pen.line([(x - box[0], y - box[1]) for x, y in polygon.exterior.coords],
                 fill=color, width=2)
    size = (raw.width * 3, raw.height * 3)
    return (raw.resize(size, Image.Resampling.NEAREST),
            outline.resize(size, Image.Resampling.NEAREST))


def save_exact(image: Image.Image, path: Path) -> dict:
    if not path.exists():
        image.save(path, format="PNG")
    with Image.open(path) as previous:
        actual = previous.convert("RGB")
    if actual.size != image.size or actual.tobytes() != image.tobytes():
        raise ValueError(f"rendered crop drift: {path}")
    return bind(path)


def build(native_path: Path, secondary_prompt: Path, secondary_sam: Path,
          retry_prompt: Path, retry_sam: Path, output: Path) -> dict:
    native, sec_prompt, sec_sam, ret_prompt, ret_sam = map(
        load, (native_path, secondary_prompt, secondary_sam, retry_prompt, retry_sam))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            sec_prompt["decision"] != "source047_053_secondary_old_mask_repair_candidate_only" or
            ret_prompt["decision"] != "source053_nail5_final_tight_sam_retry_candidate_only" or
            sec_sam["decision"] != ret_sam["decision"] != "sam_candidate_only_not_training_truth" or
            not sec_sam["ok"] or not ret_sam["ok"] or sec_sam["promptCount"] != 3 or
            ret_sam["promptCount"] != 1 or sec_sam["errors"] or ret_sam["errors"]):
        raise ValueError("second-pass input contract drift")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for prompt_doc, sam_doc in ((sec_prompt, sec_sam), (ret_prompt, ret_sam)):
        for prompt_image, sam_output in zip(prompt_doc["images"], sam_doc["outputs"], strict=True):
            ordinal = prompt_image["sourceOrdinal"]
            source = next(row for row in native["sources"] if row["ordinal"] == ordinal)
            if (prompt_image["fileName"] != sam_output["fileName"] != source["sourceFileName"] or
                    prompt_image["sourceGroup"] != sam_output["sourceGroup"] != source["sourceGroup"] or
                    prompt_image["sourceImageSha256"] != source["sourceImage"]["sha256"]):
                raise ValueError("prompt/source/SAM identity drift")
            for key in ("sourceImage", "sourceLabel", "isolatedImage"):
                checked(source[key])
            if sha(Path(source["sourceImage"]["path"])) != sha(Path(source["isolatedImage"]["path"])):
                raise ValueError("isolated image mismatch")
            with Image.open(checked(source["isolatedImage"])) as original:
                image = original.convert("RGB")
            width, height = image.size
            old = polygons(Path(source["sourceLabel"]["path"]), width, height)
            annotation_path = Path(sam_output["annotationPath"])
            annotation = load(annotation_path)
            if (annotation["image"]["fileName"] != source["sourceFileName"] or
                    annotation["image"]["sourceGroup"] != source["sourceGroup"] or
                    annotation["trainingUse"] != "prohibited" or
                    len(annotation["annotations"]) != len(prompt_image["promptTruthIndices"])):
                raise ValueError("annotation contract drift")
            for prompt_index, (truth, nail) in enumerate(zip(prompt_image["promptTruthIndices"],
                                                              annotation["annotations"], strict=True), start=1):
                shape = Polygon([(p["x"], p["y"]) for p in nail["polygon"]])
                if not shape.is_valid or shape.area <= 1:
                    raise ValueError("SAM polygon invalid")
                old_shape = old[truth - 1]
                bounds = old_shape.union(shape).bounds
                box = [max(0, int(bounds[0] - 28)), max(0, int(bounds[1] - 28)),
                       min(width, int(bounds[2] + 29)), min(height, int(bounds[3] + 29))]
                raw, outline = render(image, old_shape, shape, box)
                prefix = f"source-{ordinal:03d}-nail-{truth:02d}"
                rows.append({"ordinal": ordinal, "sourceFileName": source["sourceFileName"],
                             "sourceGroup": source["sourceGroup"], "truthIndex": truth,
                             "promptIndex": prompt_index, "cropBox": box,
                             "sourceImage": source["sourceImage"],
                             "sourceLabel": source["sourceLabel"],
                             "isolatedImage": source["isolatedImage"],
                             "samAnnotation": bind(annotation_path),
                             "samOverlay": bind(Path(sam_output["overlayPath"])),
                             "raw3x": save_exact(raw, output / f"{prefix}-raw-3x.png"),
                             "oldRedNewGreen3x": save_exact(outline, output / f"{prefix}-old-red-new-green-3x.png"),
                             "oldNewIoU": round(old_shape.intersection(shape).area / old_shape.union(shape).area, 8),
                             "visualDecision": "pending_original_resolution_review",
                             "trainingUse": "prohibited"})
    if [(r["ordinal"], r["truthIndex"]) for r in rows] != [(47, 1), (47, 4), (53, 3), (53, 5)]:
        raise ValueError("second-pass focus order drift")
    return {"schemaVersion": 1, "ok": True,
            "decision": "secondpass_original_resolution_visual_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                       "secondaryPrompts": bind(secondary_prompt), "secondarySam": bind(secondary_sam),
                       "retryPrompts": bind(retry_prompt), "retrySam": bind(retry_sam)},
            "counts": {"sourceImages": 2, "focusCandidates": 4, "visualApprovals": 0},
            "nails": rows, "trainingUse": "prohibited"}


def verify(report_path: Path) -> dict:
    saved = load(report_path)
    for item in saved["inputs"].values():
        checked(item)
    for nail in saved["nails"]:
        for key in ("sourceImage", "sourceLabel", "isolatedImage", "samAnnotation", "samOverlay", "raw3x", "oldRedNewGreen3x"):
            checked(nail[key])
    output = Path(saved["nails"][0]["raw3x"]["path"]).parent
    current = build(*(Path(saved["inputs"][key]["path"]) for key in
                      ("nativeReview", "secondaryPrompts", "secondarySam", "retryPrompts", "retrySam")), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_secondpass_original_resolution_crops",
            "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--secondary-prompts", type=Path)
    parser.add_argument("--secondary-sam", type=Path)
    parser.add_argument("--retry-prompts", type=Path)
    parser.add_argument("--retry-sam", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.native_review, args.secondary_prompts, args.secondary_sam,
                    args.retry_prompts, args.retry_sam, args.output_dir, args.report)):
            parser.error("all inputs and --output-dir/--report required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.secondary_prompts.resolve(),
                       args.secondary_sam.resolve(), args.retry_prompts.resolve(),
                       args.retry_sam.resolve(), args.output_dir.resolve())
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
