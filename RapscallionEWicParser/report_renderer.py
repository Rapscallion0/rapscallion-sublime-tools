"""Report Renderer for RapscallionEWicParser.

Transforms Markdown audit reports into standalone GitHub-styled HTML documents
with responsive tables, deduction badges, and print styling for web browser viewing.
"""

import os
import re
import tempfile
import webbrowser

STANDALONE_BROWSER_CSS = """<style>
    :root {
        --bg-color: #ffffff;
        --text-color: #24292f;
        --border-color: #d0d7de;
        --table-header-bg: #f6f8fa;
        --table-alt-row: #fbfcfd;
        --code-bg: #eff2f5;
        --badge-bg: #dafbe1;
        --badge-text: #1a7f37;
        --primary: #0969da;
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --bg-color: #0d1117;
            --text-color: #e6edf3;
            --border-color: #30363d;
            --table-header-bg: #161b22;
            --table-alt-row: #11151c;
            --code-bg: #1e242c;
            --badge-bg: rgba(46, 160, 67, 0.2);
            --badge-text: #3fb950;
            --primary: #58a6ff;
        }
    }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
        font-size: 14px;
        line-height: 1.6;
        color: var(--text-color);
        background-color: var(--bg-color);
        padding: 2.5rem 3rem;
        max-width: 1040px;
        margin: 0 auto;
    }
    h1 {
        font-size: 1.85rem;
        border-bottom: 2px solid var(--border-color);
        padding-bottom: 0.4rem;
        margin-top: 0;
        margin-bottom: 1rem;
    }
    h2 {
        font-size: 1.4rem;
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 0.3rem;
        margin-top: 1.8rem;
        margin-bottom: 0.8rem;
    }
    h3 {
        font-size: 1.15rem;
        margin-top: 1.4rem;
        margin-bottom: 0.6rem;
    }
    hr {
        border: 0;
        border-top: 1px solid var(--border-color);
        margin: 2rem 0;
    }
    ul {
        padding-left: 1.5rem;
        margin: 0.5rem 0 1rem 0;
    }
    li {
        margin: 0.25rem 0;
    }
    code {
        font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
        font-size: 0.88em;
        padding: 0.2em 0.4em;
        border-radius: 4px;
        background-color: var(--code-bg);
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 1.2rem 0 1.8rem 0;
        border: 1px solid var(--border-color);
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        border-radius: 6px;
        overflow: hidden;
    }
    th {
        background-color: var(--table-header-bg);
        font-weight: 600;
        padding: 10px 14px;
        border: 1px solid var(--border-color);
        text-align: left;
    }
    td {
        padding: 9px 14px;
        border: 1px solid var(--border-color);
        vertical-align: middle;
    }
    tr:nth-child(even) td {
        background-color: var(--table-alt-row);
    }
    .text-center {
        text-align: center;
    }
    .text-right {
        text-align: right;
    }
    .pill-deducted {
        font-weight: 600;
        padding: 0.2rem 0.5rem;
        border-radius: 12px;
        background-color: var(--badge-bg);
        color: var(--badge-text);
        display: inline-block;
    }
    .btn-bar {
        position: fixed;
        top: 15px;
        right: 25px;
        display: flex;
        gap: 8px;
    }
    .action-btn {
        background-color: var(--primary);
        color: #fff;
        border: none;
        padding: 6px 14px;
        font-size: 12px;
        font-weight: 600;
        border-radius: 6px;
        cursor: pointer;
        box-shadow: 0 2px 4px rgba(0,0,0,0.15);
    }
    @media print {
        .btn-bar { display: none; }
        body { padding: 0; max-width: 100%; }
    }
</style>
"""


def _markdown_to_browser_html_body(markdown_text: str) -> str:
    """Convert Markdown audit report to standard <table> markup for web browsers."""
    lines = markdown_text.splitlines()
    html_lines = []
    in_table = False
    table_header_parsed = False
    alignments = []
    in_list = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Headings
        if stripped.startswith("# "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{_format_inline(stripped[2:])}</h1>")
            i += 1
            continue

        if stripped.startswith("## "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{_format_inline(stripped[3:])}</h2>")
            i += 1
            continue

        if stripped.startswith("### "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{_format_inline(stripped[4:])}</h3>")
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
            i += 1
            continue

        # Bullet list item
        if stripped.startswith("- ") or stripped.startswith("* "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_format_inline(stripped[2:])}</li>")
            i += 1
            continue

        # If not a bullet item but was in a list, close list
        if in_list and not (stripped.startswith("- ") or stripped.startswith("* ")):
            html_lines.append("</ul>")
            in_list = False

        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            raw_cells = [c.strip() for c in stripped[1:-1].split("|")]

            if not in_table:
                in_table = True
                table_header_parsed = False
                alignments = []
                html_lines.append("<table>")

            # Check if alignment row (e.g. | :---: | :--- | :---: |)
            if all(re.match(r"^:?-+:?$", cell) for cell in raw_cells):
                alignments = []
                for cell in raw_cells:
                    if cell.startswith(":") and cell.endswith(":"):
                        alignments.append("text-center")
                    elif cell.endswith(":"):
                        alignments.append("text-right")
                    else:
                        alignments.append("")
                i += 1
                table_header_parsed = True
                continue

            # Header row
            if not table_header_parsed:
                th_cells = []
                for idx, cell in enumerate(raw_cells):
                    align = alignments[idx] if idx < len(alignments) else ""
                    cls = f' class="{align}"' if align else ""
                    th_cells.append(f"<th{cls}>{_format_inline(cell)}</th>")
                html_lines.append("<tr>" + "".join(th_cells) + "</tr>")
            else:
                # Body row
                td_cells = []
                for idx, cell in enumerate(raw_cells):
                    align = alignments[idx] if idx < len(alignments) else ""
                    cls = f' class="{align}"' if align else ""
                    formatted_cell = _format_inline(cell)
                    td_cells.append(f"<td{cls}>{formatted_cell}</td>")
                html_lines.append("<tr>" + "".join(td_cells) + "</tr>")

            i += 1
            continue

        # Non-table line
        if in_table:
            html_lines.append("</table>")
            in_table = False

        if stripped:
            html_lines.append(f"<p>{_format_inline(stripped)}</p>")

        i += 1

    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append("</table>")

    return "\n".join(html_lines)


def _format_inline(text: str) -> str:
    """Format inline markdown elements: bold, code, links, and deduction pills."""
    # Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Highlighted deductions e.g. **-$18.00** or **18.00**
    text = re.sub(
        r'\*\*(-?\$?\d+(?:\.\d{2})?)\*\*',
        r'<span class="pill-deducted">\1</span>',
        text
    )

    # General bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # Inline code `code`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    return text


def markdown_to_standalone_html(markdown_text: str, title: str = "WIC Audit Report") -> str:
    """Produce a complete standalone HTML document suitable for web browsers."""
    body_content = _markdown_to_browser_html_body(markdown_text)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {STANDALONE_BROWSER_CSS}
</head>
<body>
    <div class="btn-bar">
        <button class="action-btn" onclick="window.print()">Print / Save PDF</button>
    </div>
{body_content}
</body>
</html>"""


def open_in_browser(markdown_text: str, title: str = "WIC Audit Report") -> str:
    """Save standalone HTML to a temporary file and launch system default browser."""
    html_content = markdown_to_standalone_html(markdown_text, title=title)
    temp_dir = tempfile.gettempdir()
    clean_title = re.sub(r'[^\w\-_\.]', '_', title)
    file_path = os.path.join(temp_dir, f"{clean_title}.html")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    webbrowser.open(f"file://{os.path.abspath(file_path)}")
    return file_path
