# -*- coding: utf-8 -*-
"""重建标题衬线字体子集 public/fonts/jiaru-editorial-serif.woff2。

用法（先手动下载 Noto Serif SC 可变字体，见 URL 参数默认值）：
  python scripts/build-editorial-font-subset.py --vf output/font-subset-work/NotoSerifSC-VF.ttf

步骤：可变字体把 wght 轴限制到 400–600（与 @font-face 声明一致）→
按「旧子集字符 ∪ src 全量文本字符 ∪ ASCII 与常用标点」子集化 →
写回名称记录（JiaRu Editorial Serif）→ 输出 woff2 并验证覆盖。

字符来源取 src/**/*.{ts,tsx,css} 的全文（含 JSX 文本节点、字符串与注释），
注释字符一并纳入以避免遗漏；正文（非衬线）即使多收字符也只影响体积。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

REPO = Path(__file__).resolve().parents[1]
OLD_WOFF2 = REPO / "public" / "fonts" / "jiaru-editorial-serif.woff2"
OUT_WOFF2 = OLD_WOFF2
SRC_DIRS = [REPO / "src"]
SRC_EXTS = {".ts", ".tsx", ".css"}

FAMILY = "JiaRu Editorial Serif"
POSTSCRIPT = "JiaRuEditorialSerif"

# 始终纳入：ASCII 可打印区 + 旧子集已覆盖的标点（省略号、破折号、箭头、全角标点等）
ALWAYS_CODEPOINTS = list(range(0x20, 0x7F)) + [
    0x00B7,  # ·
    0x2013,  # –
    0x2014,  # —
    0x2018,  # '
    0x2019,  # '
    0x201C,  # "
    0x201D,  # "
    0x2026,  # …
    0x2192,  # →
    0x3001,  # 、
    0x3002,  # 。
] + list(range(0xFF01, 0xFF20)) + [0xFF08, 0xFF09]  # ！＂…：；＜＝＞？＠（）


def collect_source_chars() -> set[int]:
    chars: set[int] = set()
    for src_dir in SRC_DIRS:
        for path in src_dir.rglob("*"):
            if path.suffix.lower() not in SRC_EXTS or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                print(f"[warn] 跳过非 UTF-8 文件：{path}", file=sys.stderr)
                continue
            chars.update(ord(c) for c in text)
    return chars


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vf",
        required=True,
        help="Noto Serif SC 可变字体 TTF 路径（下载：https://github.com/google/fonts/raw/main/ofl/notoserifsc/NotoSerifSC%%5Bwght%%5D.ttf）",
    )
    parser.add_argument("--out", default=str(OUT_WOFF2), help="输出 woff2 路径")
    parser.add_argument(
        "--keep-ttf",
        default=None,
        help="可选：同时保留限制字轴后的实例 TTF（供 Pillow 渲染样张）",
    )
    args = parser.parse_args()

    vf_path = Path(args.vf)
    out_path = Path(args.out)
    if not vf_path.is_file():
        print(f"[error] 可变字体不存在：{vf_path}", file=sys.stderr)
        return 2
    if not OLD_WOFF2.is_file():
        print(f"[error] 旧子集不存在：{OLD_WOFF2}", file=sys.stderr)
        return 2

    # 1) 目标字符集：旧子集字符（继承历史覆盖）∪ src 文本 ∪ 固定标点
    old_chars = set(TTFont(str(OLD_WOFF2)).getBestCmap().keys())
    src_chars = collect_source_chars()
    target = (old_chars | src_chars | set(ALWAYS_CODEPOINTS)) - {0x0A, 0x0D, 0x09}
    target_text = "".join(sorted(chr(c) for c in target))
    text_file = vf_path.parent / "jiaru-editorial-subset-chars.txt"
    text_file.write_text(target_text, encoding="utf-8")
    print(f"[info] 目标字符数：{len(target)}（旧子集 {len(old_chars)}，src 采集 {len(src_chars)}）")

    # 2) 先子集化（在原始 200–900 全轴上进行，避免先限制字轴后 gvar 与字形表不一致）
    font = TTFont(str(vf_path))
    if "fvar" not in font:
        print("[error] 输入不是可变字体", file=sys.stderr)
        return 2
    from fontTools import subset

    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    options.drop_tables = []
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=target_text)
    subsetter.subset(font)

    # 3) 再把 wght 轴限制到 400–600（部分实例化，保留可变轴与 @font-face 声明一致）
    if "fvar" not in font:
        print("[error] 输入不是可变字体", file=sys.stderr)
        return 2
    instancer.instantiateVariableFont(font, {"wght": (400, 600)}, inplace=True)

    # 4) 名称记录改回项目字体名（@font-face 按声明匹配，内部名仅为一致性）
    name = font["name"]
    for name_id, value in ((1, FAMILY), (4, FAMILY), (6, POSTSCRIPT), (16, FAMILY)):
        name.setName(value, name_id, 3, 1, 0x409)

    font.flavor = "woff2"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(out_path))
    size = out_path.stat().st_size
    print(f"[info] 已写出：{out_path}（{size:,} 字节）")
    if args.keep_ttf:
        font.flavor = None
        font.save(str(args.keep_ttf))
        print(f"[info] 实例 TTF：{args.keep_ttf}")

    # 5) 验证：重新加载，覆盖、字轴、名称
    check = TTFont(str(out_path))
    cmap = set(check.getBestCmap().keys())
    axes = {a.axisTag: (a.minValue, a.maxValue) for a in check["fvar"].axes}
    missing_required = [c for c in target if c in old_chars and c not in cmap]
    missing_src = sorted(c for c in src_chars if c not in cmap and chr(c).isprintable())
    print(f"[info] 字轴：{axes}；名称：{check['name'].getDebugName(1)}")
    print(f"[info] 新子集字符数：{len(cmap)}")
    if missing_required:
        print(f"[error] 旧子集字符丢失 {len(missing_required)} 个：{[hex(c) for c in missing_required[:20]]}", file=sys.stderr)
        return 1
    if axes.get("wght") != (400.0, 600.0):
        print(f"[error] 字轴异常：{axes}", file=sys.stderr)
        return 1
    if missing_src:
        sample = "".join(chr(c) for c in missing_src[:40])
        print(f"[warn] src 中 {len(missing_src)} 个字符不在思源宋体内（自动跳过），示例：{sample}", file=sys.stderr)

    # 6) 关键缺字抽样断言（本批 17 处标题的缺字）
    for probe in "肤员句套临跑基册优掌追踪三政策—":
        if ord(probe) not in cmap:
            print(f"[error] 探针字符缺失：{probe}", file=sys.stderr)
            return 1
    print("[info] 探针字符全部覆盖：肤员句套临跑基册优掌追踪三政策—")
    return 0


if __name__ == "__main__":
    sys.exit(main())
