# -*- coding: utf-8 -*-
"""
将 docs/technical-whitepaper.md（v1.1.465）渲染为与
JiaRu_whitepaper_v1.1.269_updated.html 相同视觉风格的独立 HTML。

策略：
- 复用 v1.1.269 HTML 的 <head>（全部 CSS）与两个 <script>（交互/语义搜索 JS），
  因为两个脚本完全通过 DOM 类名与 data-* 属性自驱动。
- 重新生成 body：sidebar（品牌/版本/搜索/主题/TOC/footer）、utility-bar、
  hero（标题/摘要/元数据/统计）、document 正文、back-to-top。

用法：python scripts/build-whitepaper-html.py
输出：C:\\Users\\YaoYinyu\\Downloads\\JiaRu_whitepaper_v1.1.465_updated.html
"""

from __future__ import annotations

import html
import re
from pathlib import Path

MD_PATH = Path(r"E:\AI Project\Codex\JiaRu\docs\technical-whitepaper.md")
TPL_PATH = Path(r"C:\Users\YaoYinyu\Downloads\JiaRu_whitepaper_v1.1.269_updated.html")
OUT_PATH = Path(r"C:\Users\YaoYinyu\Downloads\JiaRu_whitepaper_v1.1.467_updated.html")

VERSION = "v1.1.467"
BASE_DATE = "2026-07-12"
REVIEW_DATE = "2026-08-15"
STATUS = "持续维护"
SUMMARY = "产品页面、前端组件、浏览器端识别、AR 试戴、服务端 API、数据集、训练、模型发布与验证"


# ---------------------------------------------------------------- slug ----

def slugify(title: str) -> str:
    """生成与 v1.1.269 一致的锚点 id（如 4-2-editor-图片试色 / 5-http-api-契约）。"""
    t = title.strip()
    t = t.replace("`", "")
    t = t.replace("（", "-").replace("）", "")
    t = t.lower()
    t = re.sub(r"[.\s/\u2013\u2014\u3001、]+", "-", t)
    t = re.sub(r"-+", "-", t)
    return t.strip("-")


# ---------------------------------------------------------------- inline ---

INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def inline(text: str) -> str:
    """段落/单元格/列表行内格式化：先转义，再还原 code 与加粗。"""
    esc = html.escape(text, quote=False)

    def code_repl(m):
        return "<code>" + m.group(1) + "</code>"

    esc = INLINE_CODE_RE.sub(code_repl, esc)

    def bold_repl(m):
        return "<strong>" + m.group(1) + "</strong>"

    esc = BOLD_RE.sub(bold_repl, esc)
    return esc


# ---------------------------------------------------------------- status ---

STATUS_WORDS = (
    "已完成", "进行中", "待验证", "占位", "未完成", "阻塞", "暂停",
    "历史记录", "审计完成", "评估完成", "独立留出拒绝", "验证阈值拒绝",
    "PASS", "训练完成", "已用于本次训练", "逐实例门失败", "已完成筛查", "通过",
)


def parse_status(text: str):
    """状态单元格 -> (主文本, detail 或 None, badge 类, 是否标准状态词)。"""
    t = text.strip()
    main = t
    detail = None
    if "（" in t and "）" in t:
        idx = t.rfind("（")
        if idx > 0:
            detail = t[idx + 1 : t.rfind("）")]
            main = t[:idx].strip()
    main_clean = main.replace("✅", "").replace("❌", "").strip()
    if not main_clean:
        main_clean = main
    recognized = any(w in main_clean for w in STATUS_WORDS)
    if any(k in main_clean for k in ("已完成", "PASS", "训练完成", "已用于本次训练", "通过", "逐实例门失败")):
        cls = "blocked" if "失败" in main_clean or "拒绝" in main_clean else "done"
    elif "进行中" in main_clean:
        cls = "progress"
    elif any(k in main_clean for k in ("待验证", "暂停")):
        cls = "pending"
    elif "占位" in main_clean:
        cls = "placeholder"
    elif "未完成" in main_clean:
        cls = "incomplete"
    elif any(k in main_clean for k in ("阻塞", "拒绝", "否决", "失败")):
        cls = "blocked"
    else:
        cls = "history"
    return main_clean, detail, cls, recognized


def status_cell(text: str) -> str:
    main, detail, cls, recognized = parse_status(text)
    if not recognized:
        return f"<td>{inline(text)}</td>"
    if detail:
        aria = html.escape(text.strip(), quote=True)
        return (
            f'<td class="status-stack-cell"><span aria-label="{aria}" class="status-stack">'
            f'<span class="status-badge status-{cls}">{html.escape(main)}</span>'
            f'<span class="status-badge status-detail status-{cls}">{html.escape(detail)}</span>'
            f"</span></td>"
        )
    return f'<td><span class="status-badge status-{cls}">{html.escape(main)}</span></td>'


# ---------------------------------------------------------------- table ----

TABLE_NO = [0]


def next_table_no() -> int:
    TABLE_NO[0] += 1
    return TABLE_NO[0]


def render_table(rows, label: str, table_class: str = ""):
    """普通表格。rows: list[list[str]]，首行为表头。"""
    no = next_table_no()
    header = rows[0]
    body = rows[1:]
    cls = "table-shell" + ((" " + table_class) if table_class else "")
    out = [
        f'<div aria-label="表格 {no}" class="{cls}" role="region" tabindex="0">',
        '<div class="table-toolbar"><span class="table-label">'
        + html.escape(label)
        + '</span><span class="table-hint">横向滚动查看完整内容</span></div><table>',
        "<thead><tr>",
    ]
    for h in header:
        out.append(f"<th>{inline(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def collapse_candidate6_rows(rows):
    """展示层压缩：将『候选6正样本补强』系列行（含全部 batch 增量行）合并为 1 行摘要。

    仅作用于 HTML 展示，不改动 MD 原文；最终张数/mask 与索引 SHA 从最后一条
    batch 行结论中自动提取，摘要保留关键事实并指向 §13 变更记录。
    """
    if not rows or len(rows) < 2:
        return rows
    c6_idx = None
    c6_count = 0
    last_conclusion = ""
    for idx, row in enumerate(rows[1:], start=1):
        if not row:
            continue
        cell0 = row[0].strip()
        if re.match(r"^候选6正样本补强（batch|^候选6正样本补强$", cell0):
            if c6_idx is None:
                c6_idx = idx
            c6_count += 1
            if len(row) >= 4:
                last_conclusion = row[3].strip()
        elif c6_idx is not None:
            break
    if c6_idx is None:
        return rows
    m = re.search(r"(\d+)\s*张/(\d+)\s*mask", last_conclusion)
    n_img = m.group(1) if m else "120"
    n_mask = m.group(2) if m else "636"
    # 取结论中最后一个 SHA-256（索引哈希；前面的可能是图片/标注哈希）
    shas = re.findall(r"SHA-256\s*`?([0-9a-f]{8})", last_conclusion)
    sha8 = shas[-1] if shas else "77714474"
    summary = [
        "候选6正样本补强（已完结）",
        "Git外`candidate6-manual-polygon-batch-*`与`training-truths-v1/training-truth-index-v1.json`",
        "已完成（候选被冻结test100否决）",
        (
            f"candidate6 正样本逐批返修（batch001—110，含查重审计与源图止损）已完结：最终权威训练真值索引"
            f"{n_img}张/{n_mask} mask、0拒绝/冗余/冲突，索引SHA-256 `{sha8}…`；该索引已用于candidate6训练并经"
            f"val30校准候选阈值0.50，冻结test100逐实例门否决结论见本表“candidate6冻结test100”行，"
            f"逐批明细与哈希见§13版本与变更记录。"
        ),
    ]
    return rows[:c6_idx] + [summary] + rows[c6_idx + c6_count:]


def render_status_table(rows, label: str):
    """功能状态总表：状态列（第 3 列）徽章化；首列日期行 date-title-cell。"""
    rows = collapse_candidate6_rows(rows)
    no = next_table_no()
    header = rows[0]
    body = rows[1:]
    out = [
        f'<div aria-label="表格 {no}" class="table-shell table-status" role="region" tabindex="0">',
        '<div class="table-toolbar"><span class="table-label">'
        + html.escape(label)
        + '</span><span class="table-hint">横向滚动查看完整内容</span></div><table>',
        "<thead><tr>",
    ]
    for h in header:
        out.append(f"<th>{inline(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for i, cell in enumerate(row):
            cell = cell.strip()
            if i == 0:
                m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$", cell)
                if m:
                    out.append(
                        '<td class="date-title-cell"><span class="table-date">'
                        + m.group(1)
                        + '</span><span class="table-entry-title">'
                        + inline(m.group(2))
                        + "</span></td>"
                    )
                    continue
                m2 = re.match(r"^(\d{4}-\d{2}-\d{2})$", cell)
                if m2:
                    out.append(
                        '<td class="date-title-cell"><span class="table-date">'
                        + m2.group(1)
                        + '</span><span class="table-entry-title">最新变更</span></td>'
                    )
                    continue
                out.append(f"<td>{inline(cell)}</td>")
            elif i == 2:  # 状态列
                out.append(status_cell(cell))
            else:
                out.append(f"<td>{inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render_intro_status_table(rows, label: str):
    """1.1 状态定义表：第一列徽章，intro-status-table 类。"""
    no = next_table_no()
    header = rows[0]
    body = rows[1:]
    out = [
        f'<div aria-label="表格 {no}" class="table-shell intro-status-table" role="region" tabindex="0">',
        '<div class="table-toolbar"><span class="table-label">'
        + html.escape(label)
        + '</span><span class="table-hint">横向滚动查看完整内容</span></div><table>',
        "<thead><tr>",
    ]
    for h in header:
        out.append(f"<th>{inline(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        for i, cell in enumerate(row):
            cell = cell.strip()
            if i == 0:
                main, detail, cls, _ = parse_status(cell)
                out.append(f'<td><span class="status-badge status-{cls}">{html.escape(main)}</span></td>')
            else:
                out.append(f"<td>{inline(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


# ---------------------------------------------------------------- code -----

LANG_EXT = {
    "text": "txt",
    "powershell": "ps1",
    "ts": "ts",
    "env": "env",
    "http": "http",
    "json": "json",
    "md": "md",
}
LANG_LABEL = {
    "text": "Plain Text",
    "powershell": "PowerShell",
    "ts": "TypeScript",
    "env": "Environment",
    "http": "HTTP",
    "json": "JSON",
    "md": "Markdown",
}

TS_KEYWORDS = {
    "async", "function", "const", "let", "var", "interface", "type", "enum",
    "import", "export", "from", "extends", "implements", "new", "return",
    "if", "else", "for", "while", "switch", "case", "break", "continue",
    "throw", "try", "catch", "finally", "default", "public", "private",
    "protected", "readonly", "static", "abstract", "class", "void", "null",
    "undefined", "true", "false", "this", "of", "in", "keyof", "typeof",
    "instanceof", "yield", "await", "declare", "namespace", "module", "as",
}
TS_BUILTIN = {
    "Promise", "Array", "Map", "Set", "File", "ImageBitmap", "Uint8ClampedArray",
    "ArrayLike", "number", "string", "boolean", "object", "any", "unknown",
    "never", "Date", "Error", "RegExp", "NodeJS", "globalThis", "console",
}

TOKEN_RE = re.compile(
    r"""(
        \/\*[\s\S]*?\*\/       # 块注释
      | \/\/[^\n]*            # 行注释
      | "(?:\\.|[^"\\])*"     # 双引号字符串
      | '(?:\\.|[^'\\])*'     # 单引号字符串
      | `(?:\\.|[^`\\])*`     # 反引号字符串
      | \b\d+(?:\.\d+)?\b     # 数字
      | [A-Za-z_$][\w$]*      # 标识符
      | \s+                   # 空白
      | [^\sA-Za-z0-9_$"']+   # 标点/操作符
    )""",
    re.VERBOSE,
)


def highlight_ts(line: str) -> str:
    parts = []
    pos = 0
    for m in TOKEN_RE.finditer(line):
        if m.start() > pos:
            parts.append(html.escape(line[pos : m.start()]))
        tok = m.group(0)
        pos = m.end()
        if tok.startswith("//") or tok.startswith("/*"):
            parts.append(f'<span class="c1">{html.escape(tok)}</span>')
        elif tok.startswith('"') or tok.startswith("'") or tok.startswith("`"):
            parts.append(f'<span class="s2">{html.escape(tok)}</span>')
        elif re.fullmatch(r"\d+(\.\d+)?", tok):
            parts.append(f'<span class="mi">{tok}</span>')
        elif re.fullmatch(r"[A-Za-z_$][\w$]*", tok):
            if tok in TS_KEYWORDS:
                cls = "kd" if tok in ("function", "interface", "type", "class", "const", "let", "var") else "k"
                parts.append(f'<span class="{cls}">{tok}</span>')
            elif tok in TS_BUILTIN:
                parts.append(f'<span class="nb">{tok}</span>')
            else:
                parts.append(f'<span class="nx">{tok}</span>')
        elif re.fullmatch(r"\s+", tok):
            parts.append(f'<span class="w">{html.escape(tok)}</span>')
        elif re.fullmatch(r"[{}()[\],;]", tok):
            parts.append(f'<span class="p">{html.escape(tok)}</span>')
        else:
            parts.append(f'<span class="o">{html.escape(tok)}</span>')
    if pos < len(line):
        parts.append(html.escape(line[pos:]))
    return "".join(parts)


def highlight_json(line: str) -> str:
    out = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == '"':
            j = i + 1
            while j < n and line[j] != '"':
                if line[j] == "\\":
                    j += 1
                j += 1
            j = min(j + 1, n)
            token = line[i:j]
            rest = line[j:].lstrip()
            if rest.startswith(":"):
                out.append(f'<span class="nt">{html.escape(token)}</span>')
            else:
                out.append(f'<span class="s2">{html.escape(token)}</span>')
            i = j
        elif ch.isdigit() or (ch == "-" and i + 1 < n and line[i + 1].isdigit()):
            m = re.match(r"-?\d+(\.\d+)?", line[i:])
            out.append(f'<span class="mi">{m.group(0)}</span>')
            i += len(m.group(0))
        elif ch in "{}[],:":
            out.append(f'<span class="p">{ch}</span>')
            i += 1
        elif ch.isspace():
            j = i
            while j < n and line[j].isspace():
                j += 1
            out.append(f'<span class="w">{html.escape(line[i:j])}</span>')
            i = j
        else:
            out.append(html.escape(ch))
            i += 1
    return "".join(out)


def highlight_env(line: str) -> str:
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(=)(.*)$", line)
    if m:
        return (
            f'<span class="na">{m.group(1)}</span><span class="o">=</span>'
            f'<span class="s">{html.escape(m.group(3))}</span>'
        )
    return html.escape(line)


def highlight_powershell(line: str) -> str:
    out = []
    i = 0
    n = len(line)
    first_word = True
    while i < n:
        ch = line[i]
        if ch == '"' or ch == "'":
            j = i + 1
            while j < n and line[j] != ch:
                if line[j] == "\\":
                    j += 1
                j += 1
            j = min(j + 1, n)
            out.append(f'<span class="s2">{html.escape(line[i:j])}</span>')
            i = j
            first_word = False
        elif re.match(r"[A-Za-z_]", ch):
            m = re.match(r"[A-Za-z_][\w.-]*", line[i:])
            word = m.group(0)
            if first_word and word.lower() in ("cd", "dir", "ls", "echo", "write-output"):
                out.append(f'<span class="nb">{word}</span>')
            else:
                out.append(f'<span class="n">{word}</span>')
            i += len(word)
            first_word = False
        elif ch.isspace():
            j = i
            while j < n and line[j].isspace():
                j += 1
            out.append(f'<span class="w">{html.escape(line[i:j])}</span>')
            i = j
        elif ch in ".:;(),":
            out.append(f'<span class="p">{ch}</span>')
            i += 1
            first_word = False
        else:
            out.append(html.escape(ch))
            i += 1
            first_word = False
    return "".join(out)


def highlight_http(line: str) -> str:
    if line.strip():
        return f'<span class="err">{html.escape(line)}</span>'
    return ""


def highlight_md(line: str) -> str:
    if line.startswith("###") or line.startswith("##") or line.startswith("#"):
        return f'<span class="gu">{html.escape(line)}</span>'
    if line.startswith("-"):
        return f'<span class="k">-</span><span class="w"> </span>{html.escape(line[1:])}'
    return html.escape(line)


def highlight_text(line: str) -> str:
    return html.escape(line)


HIGHLIGHTERS = {
    "ts": highlight_ts,
    "json": highlight_json,
    "env": highlight_env,
    "powershell": highlight_powershell,
    "http": highlight_http,
    "md": highlight_md,
    "text": highlight_text,
}

SNIPPET_NO = [0]


def render_code(lang: str, code: str) -> str:
    SNIPPET_NO[0] += 1
    no = SNIPPET_NO[0]
    ext = LANG_EXT.get(lang, "txt")
    label = LANG_LABEL.get(lang, "Plain Text")
    lines = code.split("\n")
    while lines and lines[0] == "":
        lines.pop(0)
    # 原版风格：文件末尾总是有一个空行，标记为 terminal-blank
    if lines and lines[-1] != "":
        lines.append("")
    hl = HIGHLIGHTERS.get(lang, highlight_text)
    line_html = []
    for idx, ln in enumerate(lines, start=1):
        content = hl(ln) if ln else ""
        cls = "code-line"
        if idx == len(lines) and ln == "":
            cls += " code-line-terminal-blank"
        line_html.append(
            f'<span class="{cls}" data-line="{idx}"><span class="code-line-content">{content}</span></span>'
        )
    return (
        f'<figure aria-label="snippet-{no:02d}.{ext} 代码编辑器" class="code-card" data-language="{lang}" '
        f'data-line-count="{len(lines)}"><figcaption class="code-toolbar">'
        f'<span aria-hidden="true" class="code-window-controls"><i></i><i></i><i></i></span>'
        f'<span class="code-tab" title="snippet-{no:02d}.{ext}">'
        f'<span aria-hidden="true" class="code-file-icon">◇</span>'
        f'<span class="code-filename">snippet-{no:02d}.{ext}</span>'
        f'<span aria-hidden="true" class="code-tab-close">×</span></span>'
        f'<span class="code-actions"><button aria-label="复制代码" class="icon-button copy-code" title="复制代码" type="button">复制</button></span>'
        f'</figcaption><div class="code-editor"><pre><code class="highlight language-{lang}">'
        + "".join(line_html)
        + f'</code></pre></div><footer class="code-statusbar"><span>{label}</span><span>UTF-8</span><span>LF</span>'
        f'<span>空格: 2</span><span>{len(lines)} 行</span></footer></figure>'
    )


# ---------------------------------------------------------------- md parse --

def parse_md(text: str):
    """返回元素列表。"""
    elements = []
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            elements.append((f"h{level}", title))
            i += 1
            continue
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            j = i + 1
            buf = []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            elements.append(("code", lang, "\n".join(buf)))
            i = j + 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if cells and cells[0] == "":
                    cells = cells[1:]
                if cells and cells[-1] == "":
                    cells = cells[:-1]
                rows.append(cells)
                i += 1
            if len(rows) >= 2 and re.match(r"^[\s:|-]+$", rows[1][0] if rows[1] else ""):
                rows.pop(1)
            elements.append(("table", rows))
            continue
        if stripped.startswith("- ") or re.match(r"^\d+\.\s", stripped):
            items = []
            ordered = bool(re.match(r"^\d+\.\s", stripped))
            while i < n:
                s = lines[i].strip()
                if ordered:
                    mm = re.match(r"^(\d+)\.\s+(.*)$", s)
                    if not mm:
                        break
                    items.append(inline(mm.group(2)))
                else:
                    if not s.startswith("- "):
                        break
                    items.append(inline(s[2:]))
                i += 1
            elements.append(("ol" if ordered else "ul", items))
            continue
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            elements.append(("callout", inline(" ".join(buf))))
            continue
        buf = []
        while i < n and lines[i].strip():
            buf.append(lines[i].strip())
            i += 1
        elements.append(("p", inline(" ".join(buf))))
    return elements


# ---------------------------------------------------------------- build -----

def h2_heading(no: int, title: str) -> str:
    slug = slugify(title)
    # 去掉 "N. " 编号前缀
    m = re.match(r"^(\d+)\.\s+(.*)$", title)
    display = m.group(2) if m else title
    anchor = heading_label(title)
    if no == 5:
        # 第 5 章：HTTP API 拉丁标题
        inner = '<span class="chapter-title"><span class="heading-latin">HTTP API</span> 契约'
    else:
        inner = f'<span class="chapter-title">{html.escape(display)}'
    return (
        f'<h2 data-chapter="{no:02d}" id="{slug}" tabindex="-1">{inner}'
        f'<a aria-label="{anchor}" class="heading-anchor" href="#{slug}">#</a></span></h2>'
    )


def h3_heading(title: str) -> str:
    slug = slugify(title)
    anchor = heading_label(title)
    return (
        f'<h3 data-level="3" id="{slug}" tabindex="-1">{inline(title)}'
        f'<a aria-label="{anchor}" class="heading-anchor" href="#{slug}">#</a></h3>'
    )


def h4_heading(title: str) -> str:
    slug = slugify(title)
    anchor = heading_label(title)
    return (
        f'<h4 data-level="4" id="{slug}" tabindex="-1">{inline(title)}'
        f'<a aria-label="{anchor}" class="heading-anchor" href="#{slug}">#</a></h4>'
    )


def heading_label(title: str) -> str:
    plain = title.replace("`", "")
    return f"链接到{plain.strip()}"


def table_kind(rows):
    header = " ".join(rows[0])
    if "模块" in header and "用户入口" in header:
        return "status"
    if "日期" in header and "版本" in header and "变更摘要" in header:
        return "history"
    if "状态" in header and "含义" in header:
        return "intro-status"
    return "plain"


def table_label_for(rows, chapter_title: str = ""):
    header = " ".join(rows[0])
    kind = table_kind(rows)
    if kind == "status":
        return "功能状态总表"
    if kind == "history":
        return "版本与变更记录"
    if kind == "intro-status":
        return "1.1 状态定义"
    if "层级" in header and "技术" in header:
        return "2.1 技术栈"
    if "HTTP 状态" in header:
        return "5.1 POST /api/generate-ai"
    if "指标" in header and "当前值" in header:
        return "8.1 数据集契约"
    if "类别" in header and "主要入口" in header:
        return "8.2 训练主流程"
    return chapter_title or "表格"


def render_element(el, chapter_title: str = ""):
    kind = el[0]
    if kind == "p":
        return f"<p>{el[1]}</p>"
    if kind == "ul":
        return "<ul>" + "".join(f"<li>{it}</li>" for it in el[1]) + "</ul>"
    if kind == "ol":
        return "<ol>" + "".join(f"<li>{it}</li>" for it in el[1]) + "</ol>"
    if kind == "callout":
        return f'<div class="callout"><p>{el[1]}</p></div>'
    if kind == "table":
        rows = el[1]
        label = table_label_for(rows, chapter_title)
        k = table_kind(rows)
        if k == "status":
            return render_status_table(rows, label)
        if k == "history":
            return render_table(rows, label, "table-history table-dense")
        if k == "intro-status":
            return render_intro_status_table(rows, label)
        return render_table(rows, label)
    if kind == "code":
        return render_code(el[1], el[2])
    return ""


def build_document(elements):
    """生成 document 正文。返回 (document_html, stats)。"""
    out = []
    h2_count = 0
    h3_count = 0
    h4_count = 0
    code_count = SNIPPET_NO[0]
    # 第一章特殊布局：intro-chapter-layout
    # 收集第 1 章元素直到 h2(2)
    ch1 = []
    i = 0
    n = len(elements)
    # 跳过 h2(1)
    while i < n and elements[i][0] != "h2":
        i += 1
    if i < n:
        h2_count += 1
        ch1_start = i
        i += 1
        while i < n and elements[i][0] != "h2":
            ch1.append(elements[i])
            if elements[i][0] == "h3":
                h3_count += 1
            elif elements[i][0] == "h4":
                h4_count += 1
            i += 1
        out.append(build_chapter1(elements[ch1_start], ch1))
    # 其余章节
    chapter_title = ""
    while i < n:
        el = elements[i]
        if el[0] == "h2":
            h2_count += 1
            no = h2_count
            title = el[1]
            out.append(h2_heading(no, title))
            chapter_title = title
            i += 1
            continue
        if el[0] == "h3":
            h3_count += 1
            out.append(h3_heading(el[1]))
        elif el[0] == "h4":
            h4_count += 1
            out.append(h4_heading(el[1]))
        else:
            out.append(render_element(el, chapter_title))
        i += 1
    return "".join(out), {"h2": h2_count, "h3": h3_count, "h4": h4_count, "codes": SNIPPET_NO[0] - code_count}


def build_chapter1(h2_el, ch1_items):
    """第 1 章：intro-chapter-layout（intro-copy 内 1.1/1.2，1.3/1.4 在布局外）。"""
    _, title = h2_el
    h2_html = h2_heading(1, title)
    copy = []
    after = []
    in_layout = True
    for el in ch1_items:
        if el[0] == "h3" and el[1].startswith("1.3"):
            in_layout = False
        if in_layout:
            if el[0] == "h3":
                copy.append(h3_heading(el[1]))
            elif el[0] == "table":
                copy.append(render_intro_status_table(el[1], "1.1 状态定义"))
            else:
                copy.append(render_element(el, "1. 文档定位与维护规则"))
        else:
            if el[0] == "h3":
                after.append(h3_heading(el[1]))
            elif el[0] == "h4":
                after.append(h4_heading(el[1]))
            else:
                after.append(render_element(el, "1. 文档定位与维护规则"))
    dashboard = DASHBOARD_TEMPLATE  # 由组装时填充
    return (
        h2_html
        + f'<div class="intro-chapter-layout"><div class="intro-copy">{"".join(copy)}</div>{dashboard}</div>'
        + "".join(after)
    )


DASHBOARD_TEMPLATE = (
    '<aside aria-label="首屏速览面板" class="intro-dashboard">'
    '<div class="intro-dashboard-head"><div><div class="intro-dashboard-kicker">Overview panel</div>'
    '<div class="intro-dashboard-title">文档速览与阅读建议</div></div>'
    '<span class="intro-dashboard-badge">首屏导读</span></div>'
    '<div class="intro-dashboard-grid">'
    '<div class="intro-metric"><strong>{h2}</strong><span>一级章节<br/>覆盖产品、接口、模型与数据</span></div>'
    '<div class="intro-metric"><strong>{h3}</strong><span>二级目录<br/>支持侧栏自动展开定位</span></div>'
    '<div class="intro-metric"><strong>{tables}</strong><span>结构化表格<br/>用于状态、契约和变更记录</span></div>'
    '<div class="intro-metric"><strong>{codes}</strong><span>IDE 代码块<br/>带行号、复制与状态栏</span></div>'
    "</div>"
    '<div class="intro-panel"><div class="intro-panel-title"><span>功能状态分布</span><span>共 {total} 项</span></div>'
    '<div class="intro-chart">{bars}</div></div>'
    '<div class="intro-panel"><div class="intro-panel-title"><span>推荐阅读路径</span><span>从总览到细节</span></div>'
    '<div class="intro-flow">'
    '<div class="intro-step" data-step="01">先查看功能状态总表，快速识别哪些能力已完成、待验证、进行中或处于发布阻断状态。</div>'
    '<div class="intro-step" data-step="02">再按页面接口、HTTP API、浏览器识别、模型产物和数据集章节逐步深入实现细节。</div>'
    '<div class="intro-step" data-step="03">最后回看已知限制与版本变更记录，确认当前风险、发布门和最近修订背景。</div>'
    "</div></div>"
    '<div class="intro-dashboard-note">面板数据由当前白皮书结构与功能状态总表自动汇总；正文仍是接口、状态与验证结论的唯一详细来源。</div>'
    "</aside>"
)


def build_stats_bars(rows):
    counts = {"done": 0, "progress": 0, "pending": 0, "placeholder": 0, "blocked": 0, "history": 0}
    for row in rows[1:]:
        if len(row) < 3:
            continue
        _, _, cls, _ = parse_status(row[2])
        counts[cls] = counts.get(cls, 0) + 1
    total = sum(counts.values())
    labels = [
        ("已完成", "done"),
        ("进行中", "progress"),
        ("待验证", "pending"),
        ("占位", "placeholder"),
        ("未完成", "incomplete"),
        ("阻断/拒绝", "blocked"),
        ("其他记录", "history"),
    ]
    bars = []
    for label, key in labels:
        val = counts.get(key, 0)
        fill = (val / total * 100) if total else 0
        bars.append(
            f'<div class="intro-bar-row"><label>{label}</label>'
            f'<div class="intro-bar-track" style="--fill: {fill:.0f}%"></div>'
            f"<span>{val}</span></div>"
        )
    return "".join(bars), total


# ---------------------------------------------------------------- toc ------

def build_toc(chapters):
    out = []
    for ch in chapters:
        no = ch["no"]
        slug = ch["slug"]
        title = ch["title"]
        # 去掉 h2 编号前缀（"1. " / "5. "）
        m = re.match(r"^(\d+)\.\s+(.*)$", title)
        label = m.group(2) if m else title
        subs = ch["subs"]
        if subs:
            out.append(
                f'<div class="toc-group has-children" data-chapter="{slug}">'
                f'<a aria-controls="toc-submenu-{no:02d}" aria-expanded="false" class="toc-link" data-target="{slug}" href="#{slug}">'
                f'<span class="toc-number">{no:02d}</span><span class="toc-label">{html.escape(label)}</span>'
                f'<span aria-hidden="true" class="toc-chevron">›</span><span aria-hidden="true" class="toc-indicator"></span></a>'
                f'<div class="toc-submenu" id="toc-submenu-{no:02d}"><div class="toc-submenu-inner"><div class="toc-submenu-list">'
            )
            for num, sub_label, sub_slug in subs:
                out.append(
                    f'<a class="toc-sublink" data-parent="{slug}" data-target="{sub_slug}" href="#{sub_slug}">'
                    f'<span class="toc-subnumber">{num}</span><span class="toc-sublabel">{html.escape(sub_label)}</span>'
                    f'<span aria-hidden="true" class="toc-subindicator"></span></a>'
                )
            out.append("</div></div></div></div>")
        else:
            out.append(
                f'<div class="toc-group" data-chapter="{slug}">'
                f'<a class="toc-link" data-target="{slug}" href="#{slug}">'
                f'<span class="toc-number">{no:02d}</span><span class="toc-label">{html.escape(label)}</span>'
                f'<span aria-hidden="true" class="toc-indicator"></span></a></div>'
            )
    return "".join(out)


# ---------------------------------------------------------------- main ------

def main():
    md_text = MD_PATH.read_text(encoding="utf-8")
    tpl = TPL_PATH.read_text(encoding="utf-8")

    elements = parse_md(md_text)

    # 章节结构
    h2_entries = []
    current_h2 = None
    for el in elements:
        if el[0] == "h2":
            current_h2 = {"no": len(h2_entries) + 1, "title": el[1], "slug": slugify(el[1]), "subs": []}
            h2_entries.append(current_h2)
        elif el[0] == "h3" and current_h2 is not None:
            title = el[1]
            num = re.match(r"^([\d.]+)\s+(.*)$", title)
            if num:
                label_plain = num.group(2).replace("`", "")
                current_h2["subs"].append((num.group(1), label_plain, slugify(title)))
            else:
                label_plain = title.replace("`", "")
                current_h2["subs"].append(("", label_plain, slugify(title)))

    toc_html = build_toc(h2_entries)

    doc_html, stats = build_document(elements)

    # 功能状态总表行（用于分布统计；展示层先合并候选6正样本补强系列行）
    status_rows = None
    for el in elements:
        if el[0] == "table":
            rows = el[1]
            if table_kind(rows) == "status":
                status_rows = rows
                break
    raw_status_total = (len(status_rows) - 1) if status_rows else 0
    status_rows = collapse_candidate6_rows(status_rows) if status_rows else None
    c6_collapsed = raw_status_total - ((len(status_rows) - 1) if status_rows else 0)
    bars_html, total_items = build_stats_bars(status_rows) if status_rows else ("", 0)

    h2_count = stats["h2"]
    h3_count = stats["h3"]
    h4_count = stats["h4"]
    code_count = stats["codes"]
    table_count = TABLE_NO[0]
    content_levels = h2_count + h3_count + h4_count

    dashboard = DASHBOARD_TEMPLATE.format(
        h2=h2_count, h3=h3_count, tables=table_count, codes=code_count, total=total_items, bars=bars_html
    )
    # 将 dashboard 注入 doc_html（替换占位）
    doc_html = doc_html.replace(DASHBOARD_TEMPLATE, dashboard)

    hero_stats = (
        f'<div class="stat-card"><span class="stat-value">{h2_count}</span><span class="stat-label">核心章节</span></div>'
        f'<div class="stat-card"><span class="stat-value">{content_levels}</span><span class="stat-label">内容层级</span></div>'
        f'<div class="stat-card"><span class="stat-value">{table_count}</span><span class="stat-label">结构化表格</span></div>'
        f'<div class="stat-card"><span class="stat-value">{code_count}</span><span class="stat-label">代码与命令块</span></div>'
    )

    body = build_body(toc_html, doc_html, hero_stats)

    head = extract_head(tpl)
    scripts = extract_scripts(tpl)

    out_html = (
        "<!DOCTYPE html>\n\n"
        f'<html data-theme="anthropic" lang="zh-CN">\n<head>\n{head}\n'
        f"<title>甲如（JiaRu）技术白皮书 · {VERSION}</title>\n</head>\n<body>\n{body}\n{scripts}\n</body>\n</html>\n"
    )

    OUT_PATH.write_text(out_html, encoding="utf-8")
    print(f"OK -> {OUT_PATH}")
    print(f"h2={h2_count} h3={h3_count} h4={h4_count} tables={table_count} codes={code_count} levels={content_levels} status_total={total_items} (candidate6 collapsed: {c6_collapsed})")
    print(f"toc groups={len(h2_entries)}")


def extract_head(tpl: str) -> str:
    start = tpl.index("<head>") + len("<head>")
    end = tpl.index("</head>")
    head = tpl[start:end]
    head = re.sub(r"<title>.*?</title>", "", head, flags=re.S)
    head = re.sub(
        r'content="v1\.1\.\d+-markdown-authoritative"',
        f'content="{VERSION}-markdown-authoritative"',
        head,
    )
    return head.strip()


def extract_scripts(tpl: str) -> str:
    start = tpl.index("<script>")
    end = tpl.index("</html>")
    chunk = tpl[start:end]
    # 去掉原模板中的 </body>（由新模板统一输出）
    chunk = chunk.replace("</body>", "")
    return chunk.rstrip()


def build_body(toc_html, doc_html, hero_stats):
    v = VERSION
    return f"""<a class="skip-link" href="#documentContent">跳到正文</a>
<div aria-hidden="true" class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
<div class="sidebar-overlay" id="sidebarOverlay"></div>
<div class="app-shell">
<aside aria-label="文档导航" class="sidebar">
<header class="sidebar-head">
<a aria-label="返回文档顶部" class="brand" href="#top">
<span class="brand-mark">甲</span>
<span class="brand-copy">
<span class="brand-name">甲如技术白皮书</span>
<span class="brand-subtitle">JiaRu Engineering</span>
</span>
</a>
<div class="version-line"><span class="version-dot"></span><span>{v} · 持续维护</span></div>
</header>
<div class="sidebar-tools">
<div class="search-wrap">
<span aria-hidden="true" class="search-icon"><svg fill="none" viewbox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="10.75" cy="10.75" r="6.25"></circle><path d="m15.4 15.4 4.1 4.1"></path></svg></span>
<input aria-label="语义搜索白皮书" autocomplete="off" class="search-input" id="docSearch" placeholder="你想知道的这里都有" type="search"/>
<button aria-label="清除搜索" class="search-clear" id="searchClear" type="button">×</button>
</div>
<div aria-live="polite" class="search-status" id="searchStatus"><span class="semantic-search-badge">智能</span><span>本地语义增强搜索</span></div>
<div aria-label="选择页面主题" class="theme-switcher">
<button aria-pressed="true" class="theme-button active" data-theme-value="anthropic" type="button">暖陶</button>
<button aria-pressed="false" class="theme-button" data-theme-value="kimi" type="button">冷蓝</button>
<button aria-pressed="false" class="theme-button" data-theme-value="dark" type="button">深色</button>
</div>
</div>
<div class="toc-title"><span>目录</span><span>13 章</span></div>
<nav aria-label="章节目录" class="toc">{toc_html}</nav>
<footer class="sidebar-footer">内容来自 <strong>technical-whitepaper.md</strong><br/>页面展示不改变项目接口与状态结论。<br/><span style="opacity:.72">内容同步：{v}</span></footer>
</aside>
<main class="main" id="top">
<div class="utility-bar">
<div class="utility-left">
<button aria-label="打开目录" class="icon-button mobile-menu" id="menuButton" type="button">☰</button>
<span class="document-label">技术白皮书</span><span class="separator">/</span><span class="utility-current" id="currentSection">概览</span>
</div>
<div class="utility-actions">
<button class="icon-button focus-button" id="focusToggle" title="隐藏或显示侧栏" type="button"><span aria-hidden="true" class="icon-glyph">◫</span><span class="text-label">专注阅读</span></button>
<button class="icon-button" id="printButton" title="打印或导出 PDF" type="button"><span aria-hidden="true" class="icon-glyph">⎙</span><span class="text-label">打印</span></button>
</div>
</div>
<div class="content-wrap">
<header aria-labelledby="heroTitle" class="hero">
<div class="hero-grid">
<div>
<div class="eyebrow">Technical Whitepaper</div>
<h1 id="heroTitle">甲如（JiaRu）技术白皮书</h1>
<p class="hero-summary">{SUMMARY}</p>
</div>
<aside aria-label="文档元数据" class="hero-panel">
<dl class="meta-list">
<div class="meta-row"><dt>版本</dt><dd>{v}</dd></div>
<div class="meta-row"><dt>基线日期</dt><dd>{BASE_DATE}</dd></div>
<div class="meta-row"><dt>最近审查</dt><dd>{REVIEW_DATE}</dd></div>
<div class="meta-row"><dt>状态</dt><dd>{STATUS}</dd></div>
</dl>
</aside>
</div>
<div aria-label="文档统计" class="hero-stats">
{hero_stats}
</div>
</header>
<article class="document" id="documentContent"><div class="no-results" id="noResults">没有找到匹配内容，请尝试更短或不同的关键词。</div>
{doc_html}
</article>
</div>
</main>
</div>
<button aria-label="返回顶部" class="back-to-top" id="backToTop" type="button">↑</button>
"""


if __name__ == "__main__":
    main()
