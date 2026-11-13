# -*- coding: utf-8 -*-
"""Zero-dependency Markdown parser for Sublime Text 4 (Python 3.8).

Converts Markdown into:
  1. ST4 minihtml (for HtmlSheet side-panel preview with subl: action links)
  2. Clean HTML5 fragments (for the localhost SSE browser preview & static export)
"""

import html
import re
from typing import Dict, List, Optional, Tuple


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_FENCE_RE = re.compile(r"^([`~]{3,})(.*)$")
_HR_RE = re.compile(r"^(?:[-*_]\s*){3,}$")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s*(.*)$")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_CALLOUT_RE = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", re.IGNORECASE)
_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")

# Inline patterns (applied in safe order after escaping or tokenizing code spans)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_BOLD_ITALIC_RE = re.compile(r"(\*\*\*|___)(.+?)\1")
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_STRIKE_RE = re.compile(r"~~(.+?)~~")


def slugify(text: str) -> str:
    """Create a GitHub-style heading anchor slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[\s]+", "-", cleaned)


def extract_headings(markdown_text: str) -> List[Tuple[int, str, int, str]]:
    """Return list of (level, title, line_number_1based, slug) outside code fences."""
    headings: List[Tuple[int, str, int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    for idx, raw_line in enumerate(markdown_text.splitlines(), start=1):
        line = raw_line.rstrip("\r")
        fence_m = _FENCE_RE.match(line.lstrip())
        if fence_m:
            marker = fence_m.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
                continue
            elif marker[0] == fence_char and len(marker) >= fence_len and not fence_m.group(2).strip():
                in_fence = False
                continue
        if in_fence:
            continue

        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, title, idx, slugify(title)))
    return headings


def _render_inline(text: str, mode: str, source_path: Optional[str] = None) -> str:
    """Render inline Markdown (code, images, links, bold, italic, strike) safely."""
    tokens: List[str] = []

    def stash(html_chunk: str) -> str:
        idx = len(tokens)
        tokens.append(html_chunk)
        return f"\x00TOK{idx}\x00"

    # 1. Extract inline code spans first so inner syntax is never interpreted
    def _code_sub(m: re.Match) -> str:
        escaped = html.escape(m.group(1))
        return stash(f"<code>{escaped}</code>")

    work = _INLINE_CODE_RE.sub(_code_sub, text)

    # 2. Extract images
    def _img_sub(m: re.Match) -> str:
        alt = html.escape(m.group(1), quote=True)
        src = m.group(2).strip()
        title_attr = f' title="{html.escape(m.group(3), quote=True)}"' if m.group(3) else ""
        if mode == "minihtml":
            # ST4 minihtml has limited image support; show a clean badge + alt
            label = alt or html.escape(src)
            return stash(f'<span class="md-img-badge">[img: {label}]</span>')
        if not src.startswith(("http://", "https://", "data:")):
            from urllib.parse import quote
            src_url = f"/asset?path={quote(src)}"
        else:
            src_url = html.escape(src, quote=True)
        return stash(f'<img src="{src_url}" alt="{alt}"{title_attr} />')

    work = _IMAGE_RE.sub(_img_sub, work)

    # 3. Extract links
    def _link_sub(m: re.Match) -> str:
        label_raw = m.group(1)
        href_raw = m.group(2).strip()
        title_attr = f' title="{html.escape(m.group(3), quote=True)}"' if m.group(3) else ""
        label_html = _render_inline_formatting_only(html.escape(label_raw))

        if mode == "minihtml":
            import json
            args_json = html.escape(json.dumps({"href": href_raw, "source_path": source_path or ""}), quote=True)
            subl_href = f"subl:rapscallion_markdown_open_link {args_json}"
            return stash(f'<a href="{subl_href}"{title_attr}>{label_html}</a>')

        safe_href = html.escape(href_raw, quote=True)
        extra = ' target="_blank" rel="noopener"' if href_raw.startswith(("http://", "https://")) else ""
        return stash(f'<a href="{safe_href}"{title_attr}{extra}>{label_html}</a>')

    work = _LINK_RE.sub(_link_sub, work)

    # 4. Escape remaining plain text and apply emphasis
    escaped = html.escape(work)
    formatted = _render_inline_formatting_only(escaped)

    # 5. Restore stashed HTML tokens
    def _restore(m: re.Match) -> str:
        return tokens[int(m.group(1))]

    return re.sub(r"\x00TOK(\d+)\x00", _restore, formatted)


def _render_inline_formatting_only(escaped_text: str) -> str:
    """Apply bold, italic, and strikethrough on already-escaped text."""
    out = _BOLD_ITALIC_RE.sub(r"<strong><em>\2</em></strong>", escaped_text)
    out = _BOLD_RE.sub(r"<strong>\2</strong>", out)
    out = _ITALIC_RE.sub(
        lambda m: f"<em>{m.group(1) if m.group(1) is not None else m.group(2)}</em>",
        out,
    )
    out = _STRIKE_RE.sub(r"<del>\1</del>", out)
    return out


def _split_table_row(line: str) -> List[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _parse_alignments(sep_line: str) -> List[str]:
    cells = _split_table_row(sep_line)
    aligns: List[str] = []
    for c in cells:
        c = c.strip()
        if c.startswith(":") and c.endswith(":"):
            aligns.append("center")
        elif c.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


def _is_active(start_line: int, end_line: int, cursor_line: Optional[int]) -> bool:
    return cursor_line is not None and start_line <= cursor_line <= end_line


def _render_blocks(
    markdown_text: str,
    mode: str,
    source_path: Optional[str] = None,
    cursor_line: Optional[int] = None,
) -> str:
    """Parse Markdown lines into HTML blocks for either 'minihtml' or 'browser'."""
    lines = markdown_text.splitlines()
    n = len(lines)
    i = 0
    out: List[str] = []

    while i < n:
        line = lines[i].rstrip("\r")
        stripped = line.strip()

        # Blank line
        if not stripped:
            i += 1
            continue

        # Fenced code block
        fence_m = _FENCE_RE.match(line.lstrip())
        if fence_m:
            marker = fence_m.group(1)
            fence_char = marker[0]
            fence_len = len(marker)
            lang = fence_m.group(2).strip().split()[0] if fence_m.group(2).strip() else ""
            start_line = i + 1
            i += 1
            code_lines: List[str] = []
            while i < n:
                cur = lines[i].rstrip("\r")
                close_m = _FENCE_RE.match(cur.lstrip())
                if (
                    close_m
                    and close_m.group(1)[0] == fence_char
                    and len(close_m.group(1)) >= fence_len
                    and not close_m.group(2).strip()
                ):
                    i += 1
                    break
                code_lines.append(cur)
                i += 1

            code_escaped = html.escape("\n".join(code_lines))
            lang_escaped = html.escape(lang)
            end_line = i
            active_cls = " active-block" if (mode == "minihtml" and _is_active(start_line, end_line, cursor_line)) else ""
            if mode == "minihtml":
                badge = f'<div class="code-lang">{lang_escaped}</div>' if lang_escaped else ""
                out.append(f'<div class="code-block{active_cls}">{badge}<pre><code>{code_escaped}</code></pre></div>')
            else:
                lang_cls = f' class="language-{lang_escaped}"' if lang_escaped else ""
                badge = f'<span class="code-lang">{lang_escaped}</span>' if lang_escaped else '<span class="code-lang">text</span>'
                out.append(
                    f'<div class="code-block" data-line="{start_line}">'
                    f'<div class="code-header">{badge}<button class="copy-btn" type="button">Copy</button></div>'
                    f'<pre><code{lang_cls}>{code_escaped}</code></pre></div>'
                )
            continue

        # Heading
        head_m = _HEADING_RE.match(line)
        if head_m:
            level = len(head_m.group(1))
            raw_title = head_m.group(2).strip()
            line_num = i + 1
            slug = html.escape(slugify(raw_title), quote=True)
            title_html = _render_inline(raw_title, mode, source_path)
            if mode == "minihtml":
                import json
                args_json = html.escape(json.dumps({"line": line_num}), quote=True)
                jump_href = f"subl:rapscallion_markdown_jump_line {args_json}"
                active_cls = ' class="active-block"' if _is_active(line_num, line_num, cursor_line) else ""
                out.append(f'<h{level} id="{slug}"{active_cls}><a class="heading-link" href="{jump_href}">{title_html}</a></h{level}>')
            else:
                out.append(f'<h{level} id="{slug}" data-line="{line_num}">{title_html}</h{level}>')
            i += 1
            continue

        # Horizontal rule
        if _HR_RE.match(stripped):
            out.append("<hr />")
            i += 1
            continue

        # Table (header + separator row)
        if i + 1 < n and "|" in line and _TABLE_SEP_RE.match(lines[i + 1].rstrip("\r")):
            start_line = i + 1
            headers = _split_table_row(line)
            aligns = _parse_alignments(lines[i + 1].rstrip("\r"))
            i += 2
            rows: List[List[str]] = []
            while i < n:
                rline = lines[i].rstrip("\r")
                if not rline.strip() or "|" not in rline:
                    break
                rows.append(_split_table_row(rline))
                i += 1

            tbl: List[str] = [f'<table data-line="{start_line}">' if mode != "minihtml" else "<table>"]
            tbl.append("<thead><tr>")
            for idx_c, hcell in enumerate(headers):
                align = aligns[idx_c] if idx_c < len(aligns) else "left"
                tbl.append(f'<th style="text-align:{align}">{_render_inline(hcell, mode, source_path)}</th>')
            tbl.append("</tr></thead><tbody>")
            for row in rows:
                tbl.append("<tr>")
                for idx_c in range(len(headers)):
                    val = row[idx_c] if idx_c < len(row) else ""
                    align = aligns[idx_c] if idx_c < len(aligns) else "left"
                    tbl.append(f'<td style="text-align:{align}">{_render_inline(val, mode, source_path)}</td>')
                tbl.append("</tr>")
            tbl.append("</tbody></table>")
            out.append("".join(tbl))
            continue

        # Blockquote / Callout
        if _BLOCKQUOTE_RE.match(line):
            start_line = i + 1
            bq_lines: List[str] = []
            while i < n:
                cur = lines[i].rstrip("\r")
                bm = _BLOCKQUOTE_RE.match(cur)
                if not bm:
                    break
                bq_lines.append(bm.group(1))
                i += 1

            callout_m = _CALLOUT_RE.match(bq_lines[0].strip()) if bq_lines else None
            end_line = i
            active_cls = " active-block" if (mode == "minihtml" and _is_active(start_line, end_line, cursor_line)) else ""
            if callout_m:
                kind = callout_m.group(1).upper()
                first_rest = callout_m.group(2).strip()
                body_lines = ([first_rest] if first_rest else []) + bq_lines[1:]
                body_html = _render_blocks("\n".join(body_lines), mode, source_path)
                kind_lower = kind.lower()
                out.append(
                    f'<div class="callout callout-{kind_lower}{active_cls}" data-line="{start_line}">'
                    f'<div class="callout-title">{html.escape(kind)}</div>'
                    f'<div class="callout-body">{body_html}</div></div>'
                )
            else:
                inner_html = _render_blocks("\n".join(bq_lines), mode, source_path)
                if mode == "minihtml":
                    cls_attr = ' class="active-block"' if active_cls else ""
                    out.append(f"<blockquote{cls_attr}>{inner_html}</blockquote>")
                else:
                    out.append(f'<blockquote data-line="{start_line}">{inner_html}</blockquote>')
            continue

        # Unordered or Ordered List
        ul_m = _UL_RE.match(line)
        ol_m = _OL_RE.match(line)
        if ul_m or ol_m:
            list_html, i = _parse_list(lines, i, mode, source_path, cursor_line)
            out.append(list_html)
            continue

        # Paragraph (collect contiguous non-block lines)
        start_line = i + 1
        para_lines: List[str] = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].rstrip("\r")
            nxt_s = nxt.strip()
            if (
                not nxt_s
                or _HEADING_RE.match(nxt)
                or _FENCE_RE.match(nxt.lstrip())
                or _HR_RE.match(nxt_s)
                or _BLOCKQUOTE_RE.match(nxt)
                or _UL_RE.match(nxt)
                or _OL_RE.match(nxt)
            ):
                break
            para_lines.append(nxt_s)
            i += 1

        end_line = i
        para_text = " ".join(para_lines)
        if mode == "minihtml":
            cls_attr = ' class="active-block"' if _is_active(start_line, end_line, cursor_line) else ""
            out.append(f"<p{cls_attr}>{_render_inline(para_text, mode, source_path)}</p>")
        else:
            out.append(f'<p data-line="{start_line}">{_render_inline(para_text, mode, source_path)}</p>')

    return "\n".join(out)


def _parse_list(
    lines: List[str],
    start_idx: int,
    mode: str,
    source_path: Optional[str],
    cursor_line: Optional[int] = None,
) -> Tuple[str, int]:
    """Parse flat or nested Markdown lists (including task checkboxes)."""
    n = len(lines)
    first_line = lines[start_idx].rstrip("\r")
    first_ul = _UL_RE.match(first_line)
    first_ol = _OL_RE.match(first_line)
    base_indent = len((first_ul or first_ol).group(1))
    tag = "ul" if first_ul else "ol"

    items: List[str] = []
    i = start_idx

    while i < n:
        cur = lines[i].rstrip("\r")
        if not cur.strip():
            # Peek ahead: if next non-blank line is a list item at >= base_indent, continue
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n:
                nm_u = _UL_RE.match(lines[j].rstrip("\r"))
                nm_o = _OL_RE.match(lines[j].rstrip("\r"))
                if (nm_u and len(nm_u.group(1)) >= base_indent) or (nm_o and len(nm_o.group(1)) >= base_indent):
                    i = j
                    continue
            break

        m_u = _UL_RE.match(cur)
        m_o = _OL_RE.match(cur)
        m = m_u or m_o
        if not m:
            break

        indent = len(m.group(1))
        if indent < base_indent:
            break
        if indent > base_indent:
            nested_html, i = _parse_list(lines, i, mode, source_path, cursor_line)
            if items:
                items[-1] = items[-1][:-5] + nested_html + "</li>"
            else:
                items.append(f"<li>{nested_html}</li>")
            continue

        # Same level, check if list type switched
        cur_tag = "ul" if m_u else "ol"
        if cur_tag != tag:
            break

        line_num = i + 1
        item_text = m.group(3)
        task_m = _TASK_RE.match(item_text)
        active_cls = " active-block" if (mode == "minihtml" and _is_active(line_num, line_num, cursor_line)) else ""
        if task_m:
            checked = task_m.group(1).lower() == "x"
            body = _render_inline(task_m.group(2), mode, source_path)
            if mode == "minihtml":
                import json
                args_json = html.escape(json.dumps({"line": line_num}), quote=True)
                toggle_href = f"subl:rapscallion_markdown_toggle_task_from_sheet {args_json}"
                box = "[x]" if checked else "[ ]"
                cls = "task-done" if checked else "task-open"
                items.append(
                    f'<div class="task-item {cls}{active_cls}">'
                    f'<a class="task-box" href="{toggle_href}">{box}</a> {body}</div>'
                )
            else:
                chk_attr = " checked" if checked else ""
                cls = "task-item task-done" if checked else "task-item"
                items.append(
                    f'<li class="{cls}" data-line="{line_num}">'
                    f'<input type="checkbox" class="task-checkbox" data-line="{line_num}"{chk_attr} /> '
                    f'<span>{body}</span></li>'
                )
        else:
            if mode == "minihtml":
                cls_attr = ' class="active-block"' if active_cls else ""
                items.append(f"<li{cls_attr}>{_render_inline(item_text, mode, source_path)}</li>")
            else:
                items.append(f'<li data-line="{line_num}">{_render_inline(item_text, mode, source_path)}</li>')
        i += 1

    if mode == "minihtml" and items and all('class="task-item' in it for it in items):
        return '<div class="task-list">\n' + "\n".join(items) + "\n</div>", i
    return f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>", i


def render_minihtml(
    markdown_text: str,
    source_path: Optional[str] = None,
    title: str = "Markdown Preview",
    cursor_line: Optional[int] = None,
) -> str:
    """Render complete ST4 minihtml document using theme CSS variables."""
    body = _render_blocks(markdown_text, mode="minihtml", source_path=source_path, cursor_line=cursor_line)
    safe_title = html.escape(title)
    if not body.strip():
        body = '<p class="empty-hint"><em>Empty Markdown document. Start typing to preview.</em></p>'

    return f"""<html>
<head>
<style>
body {{
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 1.0rem;
    line-height: 1.55;
    margin: 0;
    padding: 14px 18px;
    color: var(--foreground);
    background-color: var(--background);
}}
.md-header {{
    font-size: 0.85rem;
    color: color-mix(in srgb, var(--foreground) 65%, transparent);
    border-bottom: 1px solid color-mix(in srgb, var(--foreground) 18%, transparent);
    padding-bottom: 6px;
    margin-bottom: 12px;
}}
h1, h2, h3, h4, h5, h6 {{
    margin-top: 1.1rem;
    margin-bottom: 0.45rem;
    font-weight: 600;
    color: var(--bluish);
}}
h1 {{ font-size: 1.55rem; border-bottom: 1px solid color-mix(in srgb, var(--foreground) 18%, transparent); padding-bottom: 4px; }}
h2 {{ font-size: 1.3rem; }}
h3 {{ font-size: 1.12rem; color: var(--cyanish); }}
a {{ color: var(--bluish); text-decoration: none; }}
a.heading-link {{ color: inherit; }}
p {{ margin: 0.55rem 0; }}
code {{
    font-family: Consolas, "Courier New", monospace;
    font-size: 0.92em;
    background-color: color-mix(in srgb, var(--foreground) 10%, var(--background));
    padding: 1px 4px;
    border-radius: 3px;
}}
.code-block {{
    background-color: color-mix(in srgb, var(--foreground) 7%, var(--background));
    border: 1px solid color-mix(in srgb, var(--foreground) 16%, transparent);
    border-radius: 5px;
    padding: 8px 10px;
    margin: 8px 0;
}}
.code-lang {{
    font-size: 0.78rem;
    color: var(--yellowish);
    margin-bottom: 4px;
}}
pre {{
    margin: 0;
    font-family: Consolas, "Courier New", monospace;
    font-size: 0.9em;
}}
pre code {{
    background-color: transparent;
    padding: 0;
}}
blockquote {{
    margin: 8px 0;
    padding: 4px 12px;
    border-left: 3px solid var(--bluish);
    color: color-mix(in srgb, var(--foreground) 80%, transparent);
    background-color: color-mix(in srgb, var(--bluish) 6%, var(--background));
}}
.callout {{
    margin: 8px 0;
    padding: 8px 12px;
    border-left: 3px solid var(--bluish);
    background-color: color-mix(in srgb, var(--bluish) 8%, var(--background));
    border-radius: 3px;
}}
.callout-tip {{ border-left-color: var(--greenish); background-color: color-mix(in srgb, var(--greenish) 8%, var(--background)); }}
.callout-important {{ border-left-color: var(--purplish); background-color: color-mix(in srgb, var(--purplish) 8%, var(--background)); }}
.callout-warning {{ border-left-color: var(--yellowish); background-color: color-mix(in srgb, var(--yellowish) 8%, var(--background)); }}
.callout-caution {{ border-left-color: var(--redish); background-color: color-mix(in srgb, var(--redish) 8%, var(--background)); }}
.callout-title {{ font-weight: bold; font-size: 0.85rem; margin-bottom: 2px; }}
ul, ol {{ margin: 6px 0; padding-left: 20px; }}
li {{ margin: 3px 0; }}
.task-list {{ margin: 6px 0; padding-left: 6px; }}
.task-item {{ margin: 4px 0; }}
a.task-box {{
    font-family: Consolas, monospace;
    font-weight: bold;
    color: var(--greenish);
    background-color: color-mix(in srgb, var(--greenish) 12%, var(--background));
    padding: 0 4px;
    border-radius: 3px;
}}
.task-open a.task-box {{
    color: var(--yellowish);
    background-color: color-mix(in srgb, var(--yellowish) 12%, var(--background));
}}
.task-done {{ color: color-mix(in srgb, var(--foreground) 55%, transparent); }}
table {{
    border-collapse: collapse;
    margin: 10px 0;
    width: 100%;
}}
th, td {{
    border: 1px solid color-mix(in srgb, var(--foreground) 22%, transparent);
    padding: 5px 8px;
}}
th {{
    background-color: color-mix(in srgb, var(--foreground) 9%, var(--background));
    font-weight: bold;
}}
hr {{
    border: none;
    border-top: 1px solid color-mix(in srgb, var(--foreground) 22%, transparent);
    margin: 12px 0;
}}
.md-img-badge {{
    color: var(--yellowish);
    font-family: Consolas, monospace;
    font-size: 0.88em;
}}
.active-block {{
    background-color: color-mix(in srgb, var(--bluish) 12%, var(--background));
    border-left: 3px solid var(--bluish);
    padding-left: 8px;
    border-radius: 3px;
}}
</style>
</head>
<body>
<div class="md-header">{safe_title}</div>
{body}
</body>
</html>"""


def render_browser_fragment(markdown_text: str, source_path: Optional[str] = None) -> str:
    """Render clean HTML5 body fragment for SSE browser updates and static export."""
    body = _render_blocks(markdown_text, mode="browser", source_path=source_path)
    if not body.strip():
        return '<p class="empty-hint"><em>Empty Markdown document. Start typing in Sublime Text to preview.</em></p>'
    return body
