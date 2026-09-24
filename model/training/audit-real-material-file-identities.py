from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_report(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    files: list[dict[str, object]] = []
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_top: Counter[str] = Counter()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest})
        by_hash[digest].append(relative)
        by_top[relative.split("/", 1)[0]] += 1
    duplicate_groups = [paths for paths in by_hash.values() if len(paths) > 1]
    return {
        "schemaVersion": 1,
        "purpose": "Read-only byte-identity inventory; not a training eligibility or role approval",
        "root": str(root),
        "sourceSha256": sha256_file(Path(__file__)),
        "counts": {
            "imageFiles": len(files),
            "uniqueByteIdentities": len(by_hash),
            "duplicateByteGroups": len(duplicate_groups),
            "additionalExactCopies": sum(len(paths) - 1 for paths in duplicate_groups),
            "byTopDirectory": dict(sorted(by_top.items())),
        },
        "files": files,
        "exactDuplicateGroups": sorted(duplicate_groups, key=lambda paths: paths[0]),
        "trainingUse": "prohibited_until_role_and_visual_truth_review",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-report", type=Path)
    args = parser.parse_args()
    if args.verify_report:
        recorded = json.loads(args.verify_report.read_text(encoding="utf-8"))
        current = build_report(Path(recorded["root"]))
        ok = current == recorded
        print(json.dumps({"ok": ok, "decision": "verified" if ok else "inventory_mismatch", "counts": current["counts"]}, ensure_ascii=False))
        if not ok:
            raise SystemExit(1)
        return
    if not args.root or not args.output:
        parser.error("--root and --output are required unless --verify-report is set")
    report = build_report(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error("output must be outside the scanned root")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "decision": "byte_identity_inventory_only", "counts": report["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
