from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promote visually reviewed candidate annotations into training truth.")
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--annotation-method", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    review_csv = Path(args.review_csv).resolve()
    candidate_dir = Path(args.candidate_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with review_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        pass_files = {
            row["fileName"]
            for row in csv.DictReader(handle)
            if row.get("status", "").strip().lower() == "pass"
        }

    promoted = []
    for candidate_path in sorted(candidate_dir.glob("*.json")):
        document = json.loads(candidate_path.read_text(encoding="utf-8"))
        file_name = document.get("image", {}).get("fileName")
        if file_name not in pass_files:
            continue
        document.pop("decision", None)
        for annotation in document.get("annotations", []):
            attributes = annotation.setdefault("attributes", {})
            attributes["annotationMethod"] = args.annotation_method
            attributes["reviewRequired"] = False
        output_path = output_dir / candidate_path.name
        output_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        promoted.append({
            "fileName": file_name,
            "annotationPath": str(output_path),
            "annotationCount": len(document.get("annotations", [])),
        })

    report = {
        "ok": True,
        "reviewCsv": str(review_csv),
        "candidateDir": str(candidate_dir),
        "outputDir": str(output_dir),
        "annotationMethod": args.annotation_method,
        "promotedCount": len(promoted),
        "annotationCount": sum(item["annotationCount"] for item in promoted),
        "items": promoted,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
