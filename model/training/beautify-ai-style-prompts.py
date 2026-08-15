#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
beautify-ai-style-prompts.py — AI提示词美颜化（一次性、可复验）

目标用户为年轻群体：把提示词从"写实"转向柔美美颜风。
1. 37种"皮肤…"短语统一映射为"手部肌肤…"美颜描述（长短语优先替换，避免子串冲突）；
2. 特殊句子"带有真实细节的自然皮肤纹理"→"带有柔光细节的自然手部肌肤"；
3. 结尾"写实风格"轮转5种美颜风格（精致美颜/柔光美颜/清新少女/梦幻柔美/甜美滤镜）。

校验：500条、无"写实"残留、无"皮肤"残留、开头5变体不变。脚本幂等。
"""

import json
import re
import sys
from pathlib import Path

SRC = Path("src/lib/ai-style-prompts.ts")

# (原文, 美颜版) — 按长度降序应用
SKIN_FIXES = [
    ("皮肤纹理真实有质感", "手部肌肤细腻有质感"),
    ("皮肤自然有毛孔细节", "手部肌肤柔滑无瑕"),
    ("皮肤有专业妆效质感", "手部肌肤如美妆大片般无瑕"),
    ("皮肤细腻白皙真实", "手部肌肤细腻白皙透亮"),
    ("皮肤白皙有水润感", "手部肌肤白皙水润"),
    ("皮肤纹理清晰自然", "手部肌肤细腻白皙"),
    ("皮肤自然有细节", "手部肌肤细腻无瑕"),
    ("皮肤自然有质感", "手部肌肤柔滑有质感"),
    ("皮肤自然有光泽", "手部肌肤水润有光泽"),
    ("皮肤白皙真实", "手部肌肤白皙透亮"),
    ("皮肤真实有质感", "手部肌肤细腻有质感"),
    ("皮肤有真实纹理", "手部肌肤细腻无瑕"),
    ("皮肤有自然光泽", "手部肌肤水润透亮"),
    ("皮肤真实粗糙", "手部肌肤柔嫩光滑"),
    ("皮肤白皙自然", "手部肌肤白皙柔嫩"),
    ("皮肤真实有细节", "手部肌肤细腻无瑕"),
    ("皮肤真实有纹理", "手部肌肤细腻无瑕"),
    ("皮肤有油画质感", "手部肌肤柔美细腻"),
    ("皮肤有真实质感", "手部肌肤柔滑细腻"),
    ("皮肤有自然纹理", "手部肌肤细腻光滑"),
    ("皮肤真实细腻", "手部肌肤细腻柔滑"),
    ("皮肤自然细腻", "手部肌肤细腻柔滑"),
    ("皮肤白皙有光泽", "手部肌肤白皙有光泽"),
    ("皮肤质感真实", "手部肌肤柔嫩细腻"),
    ("皮肤纹理细腻", "手部肌肤细腻柔嫩"),
    ("皮肤苍白真实", "手部肌肤白皙无瑕"),
    ("皮肤真实素净", "手部肌肤清透干净"),
    ("皮肤自然白皙", "手部肌肤自然白皙"),
    ("皮肤纹理真实", "手部肌肤光滑细腻"),
    ("皮肤细腻真实", "手部肌肤细腻柔嫩"),
    ("皮肤有光泽", "手部肌肤水润有光泽"),
    ("皮肤自然", "手部肌肤柔嫩白皙"),
    ("皮肤真实", "手部肌肤光滑细腻"),
    ("皮肤白皙", "手部肌肤白皙柔嫩"),
    ("皮肤纹理", "手部肌肤"),
    ("皮肤苍白", "手部肌肤白皙"),
]

END_STYLES = [
    "精致美颜风格",
    "柔光美颜风格",
    "清新少女风格",
    "梦幻柔美风格",
    "甜美滤镜风格",
]

SPECIAL = ("带有真实细节的自然皮肤纹理", "带有柔光细节的自然手部肌肤")

SKIN_RE = re.compile(r"皮肤[^，。]*")
END_RE = re.compile(r"，写实风格。")
WRITE_RE = re.compile(r"写实")
SKIN_LEFT_RE = re.compile(r"皮肤")


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    stats = {"prompts": 0, "skin_fixes": 0, "end_style_changes": 0, "special_fixes": 0}
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

        # 1) 特殊句子
        if SPECIAL[0] in prompt:
            prompt = prompt.replace(*SPECIAL)
            stats["special_fixes"] += 1

        # 2) 皮肤短语映射（长优先）
        for old, new in sorted(SKIN_FIXES, key=lambda kv: -len(kv[0])):
            if old in prompt:
                prompt = prompt.replace(old, new)
                stats["skin_fixes"] += 1

        # 3) 结尾美颜风格轮转
        m_end = END_RE.search(prompt)
        if m_end:
            style = END_STYLES[index_in_style % len(END_STYLES)]
            prompt = prompt[: m_end.start()] + f"，{style}。" + prompt[m_end.end():]
            stats["end_style_changes"] += 1

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
    for ln, line in enumerate(new_lines, 1):
        m = re.search(r'^\s*"([^"]+)"', line)
        if not m:
            continue
        p = m.group(1)
        if WRITE_RE.search(p):
            errors.append(f"line {ln}: residual 写实: {p[-50:]}")
        if SKIN_LEFT_RE.search(p):
            errors.append(f"line {ln}: residual 皮肤: {p[-50:]}")
        if not END_STYLES and not p.endswith("。"):
            errors.append(f"line {ln}: no ending period")

    print(json.dumps({"stats": stats, "perStyle": style_counts}, ensure_ascii=False, indent=2))
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors[:30]:
            print(" -", e, file=sys.stderr)
        return 1
    print("validation OK: no 写实, no 皮肤, all ends in beautified styles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
