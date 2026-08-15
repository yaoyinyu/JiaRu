#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimize-ai-style-prompts.py — 优化 src/lib/ai-style-prompts.ts 提示词（一次性、可复验）

1. 开头句式多样化：每风格 50 段按索引轮转 5 种开头（含原句式），消除 500 段同句模板；
2. 中英混杂统一为中文：medium/tiny/confetti/swirl/cameos/henna/Art Deco/Gatsby风；
3. 修正少量语病/冗余（重复桌面、语序颠倒、错字）。

输出：变更统计；校验 10 风格×50 段、开头属于 5 变体之一、无残留英文词（允许 1mm/2mm 等尺寸写法）。
"""

import json
import re
import sys
from pathlib import Path

SRC = Path("src/lib/ai-style-prompts.ts")

STYLE_PHRASE = {
    "甜美风": "甜美少女风美甲",
    "欧美风": "欧美大胆前卫风美甲",
    "日系": "日系和风美甲",
    "极简": "极简主义美甲",
    "复古": "复古怀旧风美甲",
    "节日": "节日庆典风美甲",
    "水墨": "水墨写意风美甲",
    "几何": "几何抽象风美甲",
    "花草": "花草自然风美甲",
    "金属": "金属质感风美甲",
}

OPENERS = [
    "展现{S}的女性手部近景生活照。",
    "展现{S}的女性手部特写镜头。",
    "女性手部近景特写，展示{S}。",
    "微距视角下，展现{S}的女性手部。",
    "自然光中的女性手部近景，展示{S}。",
]

# (literal text, replacement) — 中英统一（中文字符属于\\w，不能用\\b边界，直接字面替换）
WORD_FIXES = [
    ("medium", "中等"),
    ("tiny", "细小"),
    ("confetti", "彩纸"),
    ("swirl", "旋纹"),
    ("cameos", "浮雕人像"),
    ("henna", "海娜"),
    ("Art Deco", "装饰艺术"),
    ("Gatsby风", "盖茨比风"),
]

# (exact old, new) — 语病/冗余修正
SENTENCE_FIXES = [
    ("背景为带碎花桌布的桌面。", "背景为虚化的碎花桌布。"),
    ("背景为都市混凝土墙面虚化。", "背景为虚化的都市混凝土墙面。"),
    ("手轻扇香烟。", "手轻轻扇动线香。"),
    ("白色雪点的大杏仁甲。", "白色雪点的长杏仁甲。"),
]

OPEN_RE = re.compile(r"展现[^。]+美甲的女性手部近景生活照。")
EN_WORD_RE = re.compile(r"\b[A-Za-z]+\b")
SIZE_OK = {"1mm", "2mm"}


def main() -> int:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    stats = {"styles": 0, "prompts": 0, "openers_changed": 0, "word_fixes": 0, "sentence_fixes": 0}
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
        phrase = STYLE_PHRASE.get(current_style)
        if phrase is None:
            print(f"line {i + 1}: unknown style {current_style}", file=sys.stderr)
            return 1

        # 1) 开头句式多样化（轮转）
        m_open = OPEN_RE.search(prompt)
        if m_open:
            opener = OPENERS[index_in_style % len(OPENERS)].replace("{S}", phrase)
            if m_open.group(0) != opener:
                prompt = prompt[: m_open.start()] + opener + prompt[m_open.end():]
                stats["openers_changed"] += 1

        # 2) 中英统一（字面替换）
        for pat, rep in WORD_FIXES:
            prompt, n = re.subn(re.escape(pat), rep, prompt)
            stats["word_fixes"] += n

        # 3) 语病修正
        for old, new in SENTENCE_FIXES:
            if old in prompt:
                prompt = prompt.replace(old, new)
                stats["sentence_fixes"] += 1

        lines[i] = re.sub(r'^\s*".+",\s*$', f'      "{prompt}",\n', line)
        stats["prompts"] += 1
        style_counts[current_style] = style_counts.get(current_style, 0) + 1
        index_in_style += 1

    SRC.write_text("".join(lines), encoding="utf-8")

    # 校验
    new_text = SRC.read_text(encoding="utf-8")
    new_lines = new_text.splitlines()
    errors = []
    warnings = []
    if len(style_counts) != 10:
        errors.append(f"styles={len(style_counts)} expected 10")
    # 按 label 顺序记录每个风格的 prompt 行区间
    cur = None
    spans = {}
    for i, line in enumerate(new_lines):
        m_label = re.search(r'label:\s*"([^"]+)"', line)
        if m_label:
            cur = m_label.group(1)
            spans.setdefault(cur, [])
            continue
        if cur is None:
            continue
        m_prompt = re.search(r'^\s*"([^"]+)"', line)
        if m_prompt:
            spans[cur].append((i, m_prompt.group(1)))
    for name, items in spans.items():
        count = len(items)
        if count < 49 or count > 50:
            errors.append(f"{name}: {count} prompts, expected 50")
        elif count == 49:
            warnings.append(f"{name}: {count} prompts (expected 50, missing 1)")
        phrase = STYLE_PHRASE[name]
        allowed = [o.replace("{S}", phrase) for o in OPENERS]
        for ln, p in items:
            if not any(p.startswith(a) for a in allowed):
                errors.append(f"{name} line {ln + 1}: opener not in variants: {p[:40]}")
    # 残留英文词（允许尺寸写法）
    for i, line in enumerate(new_lines):
        m_prompt = re.search(r'^\s*"([^"]+)"', line)
        if not m_prompt:
            continue
        for w in EN_WORD_RE.findall(m_prompt.group(1)):
            if w not in SIZE_OK:
                errors.append(f"residual EN word: {w} line {i + 1}: {m_prompt.group(1)[:60]}")

    stats["styles"] = len(style_counts)
    print(json.dumps({"stats": stats, "perStyle": style_counts}, ensure_ascii=False, indent=2))
    for w in warnings:
        print("WARN:", w, file=sys.stderr)
    if errors:
        print("ERRORS:", file=sys.stderr)
        for e in errors[:30]:
            print(" -", e, file=sys.stderr)
        return 1
    print("validation OK: openers all in 5 variants, no residual EN words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
