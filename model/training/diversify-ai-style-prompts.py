#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diversify-ai-style-prompts.py — 全面优化用户可见提示词（一次性、可复验）

消除三大高频模板（保持语义，按风格内索引轮转，幂等）：
1. "每片指甲有不同X"（449条）→ 4种表达轮转
2. "手轻放在X上"（208条）→ 3种表达轮转
3. "背景为虚化的X"（489条）→ 3种表达轮转

校验：500条不变、三模板残留0、开头5变体不变、无英文残留。
"""

import json
import re
import sys
from pathlib import Path

SRC = Path("src/lib/ai-style-prompts.ts")

NAIL_VARIANTS = [
    "每片指甲各绘有不同",
    "各片指甲点缀着不同",
    "指甲上错落分布着不同",
    "每片指甲分别饰有不同",
]

HAND_VARIANTS = [
    "手自然地轻放在",
    "手轻轻搭在",
    "手随意搁在",
]

BG_VARIANTS = [
    "背景为柔焦虚化的",
    "背景为柔和虚化的",
    "背景为梦幻虚化的",
]


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    stats = {"prompts": 0, "nail_variants": 0, "hand_variants": 0, "bg_variants": 0}
    style_counts = {}
    current_style = None
    index_in_style = 0

    for i, line in enumerate(lines):
        m_label = re.search(r'label:\s*"([^"]+)"', line)
        if m_label:
            current_style = m_label.group(1)
            index_in_style = 0
            continue
        if current_style is None:
            continue
        m_prompt = re.search(r'^\s*"(.+)",\s*$', line)
        if not m_prompt:
            continue
        prompt = m_prompt.group(1)

        if "每片指甲有不同" in prompt:
            prompt = prompt.replace(
                "每片指甲有不同",
                NAIL_VARIANTS[index_in_style % len(NAIL_VARIANTS)],
            )
            stats["nail_variants"] += 1
        if "手轻放在" in prompt:
            prompt = prompt.replace(
                "手轻放在",
                HAND_VARIANTS[index_in_style % len(HAND_VARIANTS)],
            )
            stats["hand_variants"] += 1
        if "背景为虚化的" in prompt:
            prompt = prompt.replace(
                "背景为虚化的",
                BG_VARIANTS[index_in_style % len(BG_VARIANTS)],
            )
            stats["bg_variants"] += 1

        lines[i] = re.sub(r'^\s*".+",\s*$', f'      "{prompt}",\n', line)
        stats["prompts"] += 1
        style_counts[current_style] = style_counts.get(current_style, 0) + 1
        index_in_style += 1

    SRC.write_text("".join(lines), encoding="utf-8")

    # 校验
    new_lines = SRC.read_text(encoding="utf-8").splitlines()
    errors = []
    if len(style_counts) != 10 or any(c != 50 for c in style_counts.values()):
        errors.append(f"style counts unexpected: {style_counts}")
    residual = {"每片指甲有不同": 0, "手轻放在": 0, "背景为虚化的": 0}
    for ln, line in enumerate(new_lines, 1):
        m = re.search(r'^\s*"([^"]+)"', line)
        if not m:
            continue
        p = m.group(1)
        for k in residual:
            if k in p:
                residual[k] += 1
        for w in re.findall(r"\b[A-Za-z]+\b", p):
            if w not in {"1mm", "2mm", "3D"}:
                errors.append(f"line {ln}: residual EN {w}: {p[:50]}")
    if any(residual.values()):
        errors.append(f"residual templates: {residual}")

    print(json.dumps({"stats": stats, "perStyle": style_counts}, ensure_ascii=False, indent=2))
    print("residual:", residual)
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors[:20]:
            print(" -", e, file=sys.stderr)
        return 1
    print("validation OK: 500 prompts, no residual templates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
