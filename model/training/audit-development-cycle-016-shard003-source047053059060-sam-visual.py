#!/usr/bin/env python3
"""Bind one-pass SAM candidates to isolated original pixels and visual stoploss."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon


VISUAL = {
    47: ("focus_candidate_pending_full_image_review",
         "第5枚SAM候选扩至透明甲尖；需在无填充原像素终审边缘及其余四甲，右下小红书来源标记另欠消融。"),
    53: ("reject_skin_contamination",
         "第5枚SAM候选沿绿色甲尖延伸到近端后继续侵入指腹，超出可见甲根；不能因提示几何通过而批准。"),
    59: ("reject_decoration_only",
         "第1枚SAM候选仍以金箔为主体，遗漏近端完整可见裸粉甲面。"),
    60: ("reject_skin_and_ornament_contamination",
         "第5枚SAM候选近端形状沿指腹/衣袖并贴入侧边钻饰，透明裸粉甲身边界未可靠复原。"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bind(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha(path)}


def checked(item: dict) -> Path:
    path = Path(item["path"])
    if not path.is_file() or sha(path) != item["sha256"]:
        raise ValueError(f"bound evidence drift: {path}")
    return path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def old_polygons(path: Path, width: int, height: int) -> list[Polygon]:
    shapes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        values = [float(x) for x in line.split()]
        if values[0] != 0 or (len(values) - 1) % 2:
            raise ValueError("old label structure drift")
        shapes.append(Polygon([(values[i] * width, values[i + 1] * height)
                               for i in range(1, len(values), 2)]))
    return shapes


def historical_delta(row: dict) -> float | None:
    if not row["historicalCanonicalTruths"]:
        return None
    canonical = row["historicalCanonicalTruths"][0]
    annotation = load(checked({"path": canonical["annotationPath"],
                               "sha256": canonical["annotationSha256"]}))
    checked({"path": canonical["reportPath"], "sha256": canonical["reportSha256"]})
    width, height = row["imageSize"]
    lines = checked(row["sourceLabel"]).read_text(encoding="utf-8").splitlines()
    if (annotation["image"]["fileName"] != row["sourceFileName"] or
            len(annotation["annotations"]) != len(lines)):
        raise ValueError("historical/current truth structure differs")
    delta = 0.0
    for nail, line in zip(annotation["annotations"], lines, strict=True):
        values = [float(x) for x in line.split()]
        points = nail["polygon"]
        if len(values) != 1 + len(points) * 2:
            raise ValueError("historical/current truth point count differs")
        for index, point in enumerate(points):
            delta = max(delta, abs(point["x"] / width - values[1 + index * 2]),
                        abs(point["y"] / height - values[2 + index * 2]))
    if delta > 5e-9:
        raise ValueError("historical/current polygon identity differs")
    return delta


def render(source: Image.Image, box: list[int], old: Polygon, new: Polygon) -> tuple[Image.Image, Image.Image]:
    raw = source.crop(tuple(box))
    outline = raw.copy()
    pen = ImageDraw.Draw(outline)
    for polygon, color in ((old, (255, 20, 20)), (new, (20, 255, 20))):
        points = [(x - box[0], y - box[1]) for x, y in polygon.exterior.coords]
        pen.line(points, fill=color, width=2)
    size = (raw.width * 3, raw.height * 3)
    return raw.resize(size, Image.Resampling.NEAREST), outline.resize(size, Image.Resampling.NEAREST)


def build(native_path: Path, prompt_path: Path, sam_path: Path, geometry_path: Path,
          output: Path) -> dict:
    native, prompts, sam, geometry = map(load, (native_path, prompt_path, sam_path, geometry_path))
    if (native["decision"] != "isolated_original_resolution_repair_crops_pending_visual" or
            prompts["decision"] != "source047053059060_one_directed_sam_pass_candidate_only" or
            sam["decision"] != "sam_candidate_only_not_training_truth" or
            not sam["ok"] or sam["completedCount"] != 4 or sam["promptCount"] != 4 or sam["errors"] or
            geometry["summary"].get("shard003-047053059060") != {"pass": 4, "suspect": 0, "missing": 0}):
        raise ValueError("SAM visual input contract drift")
    if [row["sourceOrdinal"] for row in prompts["images"]] != list(VISUAL):
        raise ValueError("prompt source order drift")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source, prompt, sam_output in zip(native["sources"], prompts["images"], sam["outputs"], strict=True):
        ordinal = source["ordinal"]
        if (ordinal != prompt["sourceOrdinal"] or source["sourceFileName"] != prompt["fileName"] != sam_output["fileName"] or
                source["sourceGroup"] != prompt["sourceGroup"] != sam_output["sourceGroup"] or
                source["sourceImage"]["sha256"] != prompt["sourceImageSha256"]):
            raise ValueError("SAM/source identity differs")
        checked(source["sourceImage"])
        checked(source["isolatedImage"])
        checked({"path": sam_output["overlayPath"], "sha256": sha(Path(sam_output["overlayPath"]))})
        with Image.open(checked(source["isolatedImage"])) as image:
            rgb = image.convert("RGB")
        width, height = rgb.size
        if [width, height] != source["imageSize"]:
            raise ValueError("source image size drift")
        old = old_polygons(checked(source["sourceLabel"]), width, height)
        annotation_path = Path(sam_output["annotationPath"])
        annotation = load(annotation_path)
        if (annotation["image"]["fileName"] != source["sourceFileName"] or
                annotation["image"]["sourceGroup"] != source["sourceGroup"] or
                annotation["trainingUse"] != "prohibited" or
                len(annotation["annotations"]) != 1 or len(old) != len(source["nails"])):
            raise ValueError("SAM annotation structure drift")
        focus = prompt["promptTruthIndices"][0]
        points = [(float(p["x"]), float(p["y"])) for p in annotation["annotations"][0]["polygon"]]
        candidate = Polygon(points)
        if not candidate.is_valid or candidate.area <= 1:
            raise ValueError("SAM polygon invalid")
        prompt_positive = [Point(x * width, y * height) for x, y in prompt["positivePoints"][0]]
        prompt_negative = [Point(x * width, y * height) for x, y in prompt["negativePoints"][0]]
        plus_hits = sum(candidate.covers(point) for point in prompt_positive)
        minus_hits = sum(candidate.covers(point) for point in prompt_negative)
        overlaps = sum(candidate.intersection(peer).area > 0 for i, peer in enumerate(old, start=1) if i != focus)
        old_bounds = old[focus - 1].bounds
        new_bounds = candidate.bounds
        box = [max(0, int(min(old_bounds[0], new_bounds[0]) - 32)),
               max(0, int(min(old_bounds[1], new_bounds[1]) - 32)),
               min(width, int(max(old_bounds[2], new_bounds[2]) + 33)),
               min(height, int(max(old_bounds[3], new_bounds[3]) + 33))]
        raw, outlined = render(rgb, box, old[focus - 1], candidate)
        raw_path = output / f"source-{ordinal:03d}-focus-raw-3x.png"
        outline_path = output / f"source-{ordinal:03d}-focus-old-red-new-green-3x.png"
        raw.save(raw_path)
        outlined.save(outline_path)
        decision, reason = VISUAL[ordinal]
        rows.append({"ordinal": ordinal, "fileName": source["sourceFileName"],
                     "sourceGroup": source["sourceGroup"], "focusTruthIndex": focus,
                     "sourceImage": source["sourceImage"], "sourceLabel": source["sourceLabel"],
                     "isolatedImage": source["isolatedImage"],
                     "samAnnotation": bind(annotation_path), "samOverlay": bind(Path(sam_output["overlayPath"])),
                     "cropBox": box, "raw3x": bind(raw_path), "oldRedNewGreen3x": bind(outline_path),
                     "oldNewIoU": round(old[focus - 1].intersection(candidate).area /
                                        old[focus - 1].union(candidate).area, 8),
                     "positiveHits": plus_hits, "positiveCount": len(prompt_positive),
                     "negativeHits": minus_hits, "negativeCount": len(prompt_negative),
                     "overlapWithOtherOldNails": overlaps,
                     "historicalMaxNormalizedDelta": historical_delta(source),
                     "visualDecision": decision, "reason": reason,
                     "trainingUse": "prohibited"})
    return {"schemaVersion": 1, "ok": True,
            "decision": "one_pass_sam_visual_stoploss_three_rejected_one_pending",
            "inputs": {"sourceScript": bind(Path(__file__)), "nativeReview": bind(native_path),
                       "prompts": bind(prompt_path), "samReport": bind(sam_path),
                       "geometry": bind(geometry_path)},
            "counts": {"sourceImages": 4, "focusCandidates": 4, "geometryPass": 4,
                       "visualRejected": 3, "visualPending": 1, "trainingApproved": 0},
            "sources": rows, "trainingUse": "prohibited"}


def verify(path: Path) -> dict:
    saved = load(path)
    for item in saved["inputs"].values():
        checked(item)
    for row in saved["sources"]:
        for name in ("sourceImage", "sourceLabel", "isolatedImage", "samAnnotation", "samOverlay", "raw3x", "oldRedNewGreen3x"):
            checked(row[name])
    output = Path(saved["sources"][0]["raw3x"]["path"]).parent
    current = build(*(Path(saved["inputs"][key]["path"]) for key in
                      ("nativeReview", "prompts", "samReport", "geometry")), output)
    if current != saved:
        raise SystemExit("reconstruction_mismatch")
    return {"ok": True, "decision": "verified_one_pass_sam_visual_stoploss", "counts": saved["counts"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-review", type=Path)
    parser.add_argument("--prompts", type=Path)
    parser.add_argument("--sam-report", type=Path)
    parser.add_argument("--geometry", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        result = verify(args.verify_report)
    else:
        if not all((args.native_review, args.prompts, args.sam_report, args.geometry, args.output_dir, args.report)):
            parser.error("all input paths and --output-dir/--report are required")
        if args.report.exists():
            raise FileExistsError(args.report)
        result = build(args.native_review.resolve(), args.prompts.resolve(),
                       args.sam_report.resolve(), args.geometry.resolve(), args.output_dir.resolve())
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("ok", "decision", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
