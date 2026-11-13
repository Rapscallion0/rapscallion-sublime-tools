import sublime
import sublime_plugin
import sqlite3
import re
import csv
import io
import os
import itertools
import time
import threading

try:
    from .sil_field_hover import parse_row_at_point, parse_csv_column_at_point, get_header_fields, is_sil_or_csv_view, show_field_popup
except Exception:
    parse_row_at_point = None
    parse_csv_column_at_point = None
    get_header_fields = None
    is_sil_or_csv_view = lambda view: False
    show_field_popup = None

ACTIVE_COMPLETIONS = {
    "columns": [],
    "tables": [],
    "table": "DATA"
}

QUERY_HISTORY = []
SCRATCHPAD_SESSIONS = {}
SCRATCHPAD_PHANTOMS = {}
SCRATCHPAD_PANEL_NAME = "sil_sql_scratchpad"


def format_sql_identifier(name):
    """Returns an unquoted SQL identifier when safe, or double-quoted otherwise."""
    if name and re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
        return name
    escaped = str(name).replace('"', '""')
    return f'"{escaped}"'

PRESET_QUERIES = [
    ("Find Duplicate Values in Column", 'SELECT "{col}", COUNT(*) AS "Count" FROM "{table}" GROUP BY "{col}" HAVING COUNT(*) > 1 ORDER BY "Count" DESC;'),
    ("Find Null or Empty Rows", 'SELECT * FROM "{table}" WHERE "{col}" IS NULL OR "{col}" = \'\';'),
    ("Distinct Value Count for Column", 'SELECT COUNT(DISTINCT "{col}") AS "Distinct Values", COUNT(*) AS "Total Rows" FROM "{table}";'),
    ("Top 20 Most Frequent Values", 'SELECT "{col}", COUNT(*) AS "Count" FROM "{table}" GROUP BY "{col}" ORDER BY "Count" DESC LIMIT 20;'),
    ("Column Numeric Summary (Min, Max, Avg, Sum)", 'SELECT MIN(CAST("{col}" AS NUMERIC)) AS "Min", MAX(CAST("{col}" AS NUMERIC)) AS "Max", ROUND(AVG(CAST("{col}" AS NUMERIC)), 2) AS "Avg", ROUND(SUM(CAST("{col}" AS NUMERIC)), 2) AS "Sum" FROM "{table}";'),
    ("Sample First 50 Rows", 'SELECT * FROM "{table}" LIMIT 50;'),
    ("Count Total Rows in Table", 'SELECT COUNT(*) AS "Total Rows" FROM "{table}";'),
]

BASE_SQL_KEYWORDS = [
    ("SELECT", "SELECT "),
    ("WHERE", "WHERE "),
    ("GROUP BY", "GROUP BY "),
    ("ORDER BY", "ORDER BY "),
    ("HAVING", "HAVING "),
    ("LIMIT", "LIMIT "),
    ("LIKE", "LIKE '%${1}%'"),
    ("IN", "IN (${1})"),
    ("IS NULL", "IS NULL"),
    ("IS NOT NULL", "IS NOT NULL"),
    ("COUNT()", "COUNT(${1:*})"),
    ("SUM()", "SUM(${1})"),
    ("AVG()", "AVG(${1})"),
    ("MIN()", "MIN(${1})"),
    ("MAX()", "MAX(${1})"),
    ("ROUND()", "ROUND(${1}, ${2:2})"),
    ("COALESCE()", "COALESCE(${1}, ${2})"),
    ("CAST AS NUMERIC", "CAST(${1} AS NUMERIC)"),
    ("DISTINCT", "DISTINCT "),
    ("ASC", "ASC"),
    ("DESC", "DESC"),
    ("AND", "AND "),
    ("OR", "OR "),
    ("NOT", "NOT "),
    ("BETWEEN", "BETWEEN ${1} AND ${2}")
]


def record_query_history(query):
    """Adds executed query to session history (deduplicated, newest first)."""
    q = query.strip()
    if not q:
        return
    if q in QUERY_HISTORY:
        QUERY_HISTORY.remove(q)
    QUERY_HISTORY.insert(0, q)
    if len(QUERY_HISTORY) > 25:
        del QUERY_HISTORY[25:]


def format_as_markdown_table(headers, rows):
    """Formats headers and rows into an aligned GitHub Flavored Markdown table."""
    if not headers:
        return ""
    col_count = len(headers)
    clean_headers = [str(h).replace("|", "\\|").replace("\n", " ").strip() for h in headers]

    col_widths = [len(h) for h in clean_headers]
    clean_rows = []
    for r in rows:
        row_vals = []
        for c in range(col_count):
            v = r[c] if c < len(r) else ""
            if v is None:
                s = ""
            else:
                s = str(v).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").strip()
            row_vals.append(s)
            col_widths[c] = max(col_widths[c], len(s))
        clean_rows.append(row_vals)

    header_line = "| " + " | ".join(h.ljust(col_widths[c]) for c, h in enumerate(clean_headers)) + " |"
    sep_line = "| " + " | ".join("-" * max(3, col_widths[c]) for c in range(col_count)) + " |"

    lines = [header_line, sep_line]
    for row in clean_rows:
        lines.append("| " + " | ".join(val.ljust(col_widths[c]) for c, val in enumerate(row)) + " |")

    return "\n".join(lines) + "\n"


def export_query_results(window, table_name, headers, rows, elapsed, query_name="Results"):
    """Exports SQL query results as either CSV or Markdown table based on user settings."""
    settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
    fmt = settings.get("default_result_format", "csv").lower()

    new_view = window.new_file()
    new_view.set_scratch(True)

    if fmt == "markdown":
        new_view.set_name(f"{table_name} {query_name}.md")
        content = format_as_markdown_table(headers, rows)
        syntax_candidates = [
            "Packages/Markdown/Markdown.sublime-syntax",
            "Packages/Markdown/MultiMarkdown.sublime-syntax"
        ]
        assigned = False
        for cand in syntax_candidates:
            if cand and sublime.find_resources(cand.split("/")[-1]):
                try:
                    new_view.assign_syntax(cand)
                    assigned = True
                    break
                except Exception:
                    continue
        if not assigned:
            try:
                new_view.assign_syntax("scope:text.html.markdown")
            except Exception:
                pass
    else:
        new_view.set_name(f"{table_name} {query_name}.csv")
        delimiter = settings.get("export_delimiter", ",")
        output_buffer = io.StringIO()
        writer = csv.writer(output_buffer, delimiter=delimiter, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
        content = output_buffer.getvalue()

        preferred = settings.get("preferred_csv_syntax", "").strip()
        syntax_candidates = []
        if preferred:
            syntax_candidates.append(preferred)

        syntax_candidates.extend([
            "Packages/rainbow_csv/pregenerated_grammars/CSV (Rainbow).sublime-syntax",
            "Packages/Rainbow CSV/CSV (Rainbow).sublime-syntax",
            "Packages/CSV/CSV.sublime-syntax"
        ])

        assigned = False
        for candidate in syntax_candidates:
            if candidate and (sublime.find_resources(candidate.split("/")[-1]) or candidate == preferred):
                try:
                    new_view.assign_syntax(candidate)
                    assigned = True
                    break
                except Exception:
                    continue

        if not assigned:
            try:
                new_view.assign_syntax("scope:text.csv")
            except Exception:
                pass

    new_view.run_command("append", {"characters": content})
    sublime.status_message(f"Rapscallion Tools: SIL - {len(rows)} rows returned in {elapsed}ms.")
    return new_view


def extract_row_tokens(line_str):
    """Extracts raw token strings and their character spans (start, end, text) on a line."""
    lstripped = line_str.lstrip()
    indent_offset = len(line_str) - len(lstripped)

    if lstripped.startswith('('):
        open_paren = line_str.find('(')
        close_paren = line_str.rfind(')')
        content_start = open_paren + 1
        content_end = close_paren if close_paren != -1 else len(line_str)
        inside = line_str[content_start:content_end]

        spans = []
        token_start = 0
        in_squote = False
        in_dquote = False
        i = 0
        length = len(inside)
        while i < length:
            ch = inside[i]
            if in_squote:
                if ch == "'" and i + 1 < length and inside[i + 1] == "'":
                    i += 2
                    continue
                elif ch == "'":
                    in_squote = False
                i += 1
                continue
            if in_dquote:
                if ch == '"' and i + 1 < length and inside[i + 1] == '"':
                    i += 2
                    continue
                elif ch == '"':
                    in_dquote = False
                i += 1
                continue
            if ch == "'":
                in_squote = True
                i += 1
            elif ch == '"':
                in_dquote = True
                i += 1
            elif ch == ',':
                raw_tok = inside[token_start:i].strip()
                spans.append((content_start + token_start, content_start + i, raw_tok))
                token_start = i + 1
                i += 1
            else:
                i += 1
        raw_tok = inside[token_start:].strip()
        spans.append((content_start + token_start, content_start + len(inside), raw_tok))
        return spans
    else:
        spans = []
        token_start = 0
        in_quotes = False
        for i, ch in enumerate(line_str):
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == ',' and not in_quotes:
                raw_tok = line_str[token_start:i].strip()
                spans.append((token_start, i, raw_tok))
                token_start = i + 1
        raw_tok = line_str[token_start:].strip()
        spans.append((token_start, len(line_str), raw_tok))
        return spans


# ==============================================================================
# Progress Indicator (Animated Spinner)
# ==============================================================================

class SilProgressIndicator:
    def __init__(self, view, label="Processing"):
        self.view = view
        self.label = label
        self.step = 0
        self.is_running = False
        self.spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def start(self):
        self.is_running = True
        self._animate()

    def _animate(self):
        if not self.is_running or not self.view.is_valid():
            return
        frame = self.spinner[self.step % len(self.spinner)]
        self.view.set_status("sil_query_progress", f"{frame} {self.label}...")
        self.step += 1
        sublime.set_timeout(self._animate, 80)

    def stop(self, final_msg=""):
        self.is_running = False
        if self.view.is_valid():
            self.view.erase_status("sil_query_progress")
        if final_msg:
            sublime.status_message(final_msg)


# ==============================================================================
# Stateful Lexer & Type Inference
# ==============================================================================

def parse_sil_tuples(chunk, expected_col_count):
    """
    Parses a block of SQL tuples like:
    ('val1', 'val2', 123, , 'val with , comma', 'escaped ''quote'''),
    Yields list of cleaned Python values (str, int, float, or None).
    """
    length = len(chunk)
    i = 0
    while i < length:
        while i < length and chunk[i] != '(':
            i += 1
        if i >= length:
            break
        i += 1

        row = []
        current_token = []
        is_quoted = False
        in_squote = False
        in_dquote = False

        while i < length:
            ch = chunk[i]

            if in_squote:
                next_q = chunk.find("'", i)
                if next_q == -1:
                    current_token.append(chunk[i:])
                    i = length
                    continue
                if next_q > i:
                    current_token.append(chunk[i:next_q])
                if next_q + 1 < length and chunk[next_q + 1] == "'":
                    current_token.append("'")
                    i = next_q + 2
                    continue
                in_squote = False
                i = next_q + 1
                continue

            if in_dquote:
                next_q = chunk.find('"', i)
                if next_q == -1:
                    current_token.append(chunk[i:])
                    i = length
                    continue
                if next_q > i:
                    current_token.append(chunk[i:next_q])
                if next_q + 1 < length and chunk[next_q + 1] == '"':
                    current_token.append('"')
                    i = next_q + 2
                    continue
                in_dquote = False
                i = next_q + 1
                continue

            if ch == "'":
                in_squote = True
                is_quoted = True
                i += 1
            elif ch == '"':
                in_dquote = True
                is_quoted = True
                i += 1
            elif ch == ',':
                raw = "".join(current_token).strip()
                if not raw and not is_quoted:
                    row.append(None)
                elif raw.upper() == 'NULL' and not is_quoted:
                    row.append(None)
                else:
                    row.append(raw)
                current_token = []
                is_quoted = False
                i += 1
            elif ch == ')':
                raw = "".join(current_token).strip()
                if not raw and not is_quoted and len(row) < expected_col_count:
                    row.append(None)
                elif raw.upper() == 'NULL' and not is_quoted:
                    row.append(None)
                elif raw or is_quoted:
                    row.append(raw)
                i += 1
                break
            elif ch in ('\r', '\n'):
                i += 1
            else:
                current_token.append(ch)
                i += 1

        if row:
            while len(row) < expected_col_count:
                row.append(None)
            yield row


def infer_column_types(cols, rows, sample_size=100):
    """Inspects sample rows to infer INTEGER, REAL, or TEXT column types."""
    sample = rows[:sample_size]
    types = []
    int_re = re.compile(r'^-?\d+$')
    real_re = re.compile(r'^-?\d+\.\d+$')

    for col_idx in range(len(cols)):
        values = [r[col_idx] for r in sample if r[col_idx] is not None and str(r[col_idx]).strip() != '']
        if not values:
            types.append("TEXT")
            continue

        is_int = all(int_re.match(str(v)) for v in values)
        if is_int:
            types.append("INTEGER")
            continue

        is_real = all(real_re.match(str(v)) or int_re.match(str(v)) for v in values)
        if is_real:
            types.append("REAL")
            continue

        types.append("TEXT")

    return types


# ==============================================================================
# Auto-Completions Listener for SQL Query Input Panel & Scratchpad
# ==============================================================================

class SilSqliteCompletionListener(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        try:
            is_panel = view.settings().get("is_sil_sql_panel", False)
            is_scratch = view.settings().get("is_sil_scratchpad", False)
            if not is_panel and not is_scratch:
                return None

            tbl = ACTIVE_COMPLETIONS.get("table", "DATA")
            items = []

            for t in ACTIVE_COMPLETIONS.get("tables", [tbl]):
                items.append(
                    sublime.CompletionItem(
                        trigger=t,
                        annotation="Table",
                        completion=t,
                        kind=sublime.KIND_TYPE
                    )
                )

            from_snippet = f"FROM ${{1:{tbl}}} "
            items.append(
                sublime.CompletionItem.snippet_completion(
                    trigger="FROM",
                    snippet=from_snippet,
                    annotation="SQL",
                    kind=sublime.KIND_KEYWORD
                )
            )

            for col in ACTIVE_COMPLETIONS.get("columns", []):
                items.append(
                    sublime.CompletionItem(
                        trigger=col,
                        annotation="Column",
                        completion=col,
                        kind=sublime.KIND_VARIABLE
                    )
                )

            for trigger, snippet in BASE_SQL_KEYWORDS:
                is_func = trigger.endswith("()")
                items.append(
                    sublime.CompletionItem.snippet_completion(
                        trigger=trigger,
                        snippet=snippet,
                        annotation="SQL Func" if is_func else "SQL",
                        kind=sublime.KIND_FUNCTION if is_func else sublime.KIND_KEYWORD
                    )
                )

            return sublime.CompletionList(
                items,
                sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS
            )
        except Exception as e:
            print(f"[Rapscallion Tools: SIL] Error in on_query_completions: {e}")
            return None

    def on_modified_async(self, view):
        try:
            if not view.settings().get("is_sil_sql_panel"):
                return

            sel = view.sel()
            if not sel:
                return

            pt = sel[0].b
            if pt == 0:
                return

            text_before = view.substr(sublime.Region(max(0, pt - 5), pt))
            prev_char = text_before[-1]

            should_trigger = (
                prev_char.isalnum()
                or prev_char == "_"
                or text_before.upper().endswith("FROM ")
            )

            if should_trigger:
                view.run_command("auto_complete", {
                    "disable_auto_insert": True,
                    "api_completions_only": True,
                    "next_completion_if_showing": False,
                    "auto_complete_commit_on_tab": True
                })
        except Exception as e:
            print(f"[Rapscallion Tools: SIL] Error in on_modified_async: {e}")


# ==============================================================================
# Shared SQLite Ingestion Engine
# ==============================================================================

def ingest_view_data(view, settings, progress=None):
    """Parses active SIL or CSV view and populates an in-memory SQLite database."""
    file_name = view.file_name() or ""
    tab_name = view.name() or ""
    syntax = view.settings().get("syntax", "")
    sample = view.substr(sublime.Region(0, min(view.size(), 2048))).strip()

    is_sil = (
        "SIL" in syntax
        or file_name.lower().endswith(".sil")
        or sample.upper().startswith("@CREATE(")
        or "CREATE VIEW" in sample.upper()
    )
    is_csv = (
        "CSV" in syntax
        or file_name.lower().endswith(".csv")
        or "Results.csv" in tab_name
        or "Results.md" in tab_name
    )

    if not is_sil and not is_csv:
        return None, None, None

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -64000;")
    use_disk = bool(
        file_name
        and not view.is_dirty()
        and view.size() > 5 * 1024 * 1024
        and os.path.isfile(file_name)
    )

    if use_disk:
        with open(file_name, "r", encoding="utf-8", errors="replace") as stream:
            parsed_tables = _ingest_sil_stream(conn, stream, settings) if is_sil else _ingest_csv_stream(conn, stream, tab_name, settings)
    else:
        stream = io.StringIO(view.substr(sublime.Region(0, view.size())))
        parsed_tables = _ingest_sil_stream(conn, stream, settings) if is_sil else _ingest_csv_stream(conn, stream, tab_name, settings)

    return conn, parsed_tables, is_sil


def extract_headers_fast(view):
    """Quickly extracts table name and column headers from the head of a SIL or CSV view."""
    syntax = view.settings().get("syntax", "")
    file_name = view.file_name() or ""
    tab_name = view.name() or ""

    head_size = min(view.size(), 262144)
    head_text = view.substr(sublime.Region(0, head_size))
    sample_upper = head_text[:2048].strip().upper()

    is_sil = (
        "SIL" in syntax
        or file_name.lower().endswith(".sil")
        or sample_upper.startswith("@CREATE(")
        or "CREATE VIEW" in sample_upper
    )
    is_csv = (
        "CSV" in syntax
        or file_name.lower().endswith(".csv")
        or "Results.csv" in tab_name
        or "Results.md" in tab_name
    )

    if not is_sil and not is_csv:
        return None

    if is_sil:
        view_pattern = re.compile(
            r'CREATE\s+VIEW\s+(\w+)\s+AS\s+SELECT\s+([^;]+?)\s+FROM\b',
            re.IGNORECASE
        )
        parsed = {}
        for m in view_pattern.finditer(head_text):
            tname = m.group(1).strip()
            cols = [c.strip().strip("\"'[]").upper() for c in m.group(2).split(",") if c.strip()]
            if tname and cols and tname not in parsed:
                parsed[tname] = cols
        return parsed or None

    # CSV fast header
    first_nl = head_text.find("\n")
    first_line = head_text[:first_nl] if first_nl != -1 else head_text
    header = next(csv.reader([first_line]), None)
    if not header:
        return None

    if "Results." in tab_name:
        base_name = re.sub(r'\s+Results\.(csv|md)$', '', tab_name, flags=re.IGNORECASE).strip()
        table_name = (base_name + "_SUB") if base_name else "DATA"
    else:
        table_name = "DATA"

    seen_counts = {}
    cols = []
    for i, h in enumerate(header):
        raw_name = h.strip().strip('"').strip("'")
        if not raw_name:
            raw_name = f"COL_{i + 1}"
        cleaned = re.sub(r'[^\w]', '_', raw_name)
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"COL_{cleaned}"
        if cleaned in seen_counts:
            seen_counts[cleaned] += 1
            final_name = f"{cleaned}_{seen_counts[cleaned]}"
        else:
            seen_counts[cleaned] = 1
            final_name = cleaned
        cols.append(final_name.upper())

    return {table_name: cols} if cols else None


def _convert_row(row, col_types, col_count):
    row_len = len(row)
    conv_row = []
    for idx in range(col_count):
        val = row[idx] if idx < row_len else None
        ctype = col_types[idx]
        if val is None or val == "":
            conv_row.append(None)
        elif ctype == "INTEGER":
            try:
                conv_row.append(int(val))
            except ValueError:
                conv_row.append(val)
        elif ctype == "REAL":
            try:
                conv_row.append(float(val))
            except ValueError:
                conv_row.append(val)
        else:
            conv_row.append(val)
    return conv_row


def _create_and_populate_table(cursor, table_name, cols, rows_iter, settings):
    sample_size = settings.get("type_inference_sample_size", 100)
    peek_count = sample_size if sample_size > 0 else 1
    sample_rows = list(itertools.islice(rows_iter, peek_count))
    if not sample_rows:
        return False

    col_types = infer_column_types(cols, sample_rows, sample_size) if sample_size > 0 else ["TEXT"] * len(cols)
    cols_def = ", ".join([f'"{c}" {t}' for c, t in zip(cols, col_types)])
    cursor.execute(f'CREATE TABLE "{table_name}" ({cols_def});')

    placeholders = ", ".join(["?"] * len(cols))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'
    batch_size = settings.get("ingestion_batch_size", 5000)
    col_count = len(cols)

    all_rows = itertools.chain(sample_rows, rows_iter)
    while True:
        batch = list(itertools.islice(all_rows, batch_size))
        if not batch:
            break
        converted_batch = [_convert_row(row, col_types, col_count) for row in batch]
        cursor.executemany(insert_sql, converted_batch)

    return True


def _iter_sil_section_rows(initial_tail, text_stream, expected_col_count, pushback):
    """Streams SIL tuple rows from text_stream until the next directive or EOF."""
    directive_re = re.compile(r'^\s*(@|CREATE\s+VIEW\b)', re.IGNORECASE)
    buf = [initial_tail] if initial_tail else []
    line_count = 0

    for line in text_stream:
        if directive_re.match(line):
            pushback.append(line)
            break
        buf.append(line)
        line_count += 1
        if line_count >= 2000 and line.rstrip().endswith(("),", ");", ")")):
            yield from parse_sil_tuples("".join(buf), expected_col_count)
            buf.clear()
            line_count = 0

    if buf:
        yield from parse_sil_tuples("".join(buf), expected_col_count)


def _ingest_sil_stream(conn, text_stream, settings):
    cursor = conn.cursor()
    parsed = {}

    view_pattern = re.compile(
        r'CREATE\s+VIEW\s+(\w+)\s+AS\s+SELECT\s+([^;]+?)\s+FROM\b',
        re.IGNORECASE
    )
    values_pattern = re.compile(r'\bVALUES\b', re.IGNORECASE)
    multi_behavior = settings.get("multi_table_behavior", "prompt")

    pushback = []
    header_buf = []

    def _next_line():
        if pushback:
            return pushback.pop(0)
        return next(text_stream, None)

    while True:
        line = _next_line()
        if line is None:
            break

        if not header_buf and "CREATE" not in line.upper():
            continue

        header_buf.append(line)
        header_text = "".join(header_buf)
        match = view_pattern.search(header_text)
        if not match:
            if len(header_buf) > 500:
                header_buf.clear()
            continue

        val_match = values_pattern.search(header_text, match.end())
        if not val_match:
            continue

        table_name = match.group(1).strip()
        raw_cols = [c.strip().strip("\"'[]").upper() for c in match.group(2).split(',') if c.strip()]
        tail = header_text[val_match.end():]
        header_buf.clear()

        if "(" not in tail:
            # Scan forward until the opening '(' of the first tuple or a directive
            pre_buf = [tail]
            found_paren = False
            while True:
                nxt = _next_line()
                if nxt is None:
                    break
                if re.match(r'^\s*(@|CREATE\s+VIEW\b)', nxt, re.IGNORECASE):
                    pushback.append(nxt)
                    break
                pre_buf.append(nxt)
                if "(" in nxt:
                    found_paren = True
                    break
            if not found_paren:
                continue
            tail = "".join(pre_buf)

        rows_iter = _iter_sil_section_rows(tail, text_stream, len(raw_cols), pushback)
        if _create_and_populate_table(cursor, table_name, raw_cols, rows_iter, settings):
            parsed[table_name] = raw_cols
            if multi_behavior == "first":
                break

    conn.commit()
    return parsed


def _ingest_csv_stream(conn, text_stream, tab_name, settings):
    if "Results." in tab_name:
        base_name = re.sub(r'\s+Results\.(csv|md)$', '', tab_name, flags=re.IGNORECASE).strip()
        table_name = (base_name + "_SUB") if base_name else "DATA"
    else:
        table_name = "DATA"

    reader = csv.reader(text_stream)
    header = next(reader, None)
    if not header:
        return {}

    seen_counts = {}
    cols = []
    for i, h in enumerate(header):
        raw_name = h.strip().strip('"').strip("'")
        if not raw_name:
            raw_name = f"COL_{i + 1}"
        cleaned = re.sub(r'[^\w]', '_', raw_name)
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"COL_{cleaned}"

        if cleaned in seen_counts:
            seen_counts[cleaned] += 1
            final_name = f"{cleaned}_{seen_counts[cleaned]}"
        else:
            seen_counts[cleaned] = 1
            final_name = cleaned
        cols.append(final_name.upper())

    if not _create_and_populate_table(conn.cursor(), table_name, cols, reader, settings):
        return {}

    conn.commit()
    return {table_name: cols}


# ==============================================================================
# Feature: Interactive SQLite Query Command (Alt + Q)
# ==============================================================================

class SilSqliteQueryCommand(sublime_plugin.TextCommand):
    last_query = None
    last_table = None

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        sample = self.view.substr(sublime.Region(0, min(self.view.size(), 2048))).strip()
        if not sample:
            sublime.status_message("Rapscallion Tools: SIL - Buffer is empty.")
            return

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        is_async = settings.get("async_ingestion", True)

        progress = SilProgressIndicator(self.view, "Ingesting SIL Data")
        progress.start()

        if is_async:
            threading.Thread(
                target=self._run_ingestion_thread,
                args=(settings, progress),
                daemon=True
            ).start()
        else:
            self._run_ingestion_thread(settings, progress)

    def _run_ingestion_thread(self, settings, progress):
        conn = None
        try:
            conn, parsed_tables, _ = ingest_view_data(self.view, settings, progress)

            if not parsed_tables:
                if conn:
                    conn.close()
                sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - No valid tables or rows parsed."), 0)
                return

            sublime.set_timeout(lambda: progress.stop(), 0)

            ACTIVE_COMPLETIONS["tables"] = list(parsed_tables.keys())

            multi_behavior = settings.get("multi_table_behavior", "prompt")
            table_names = list(parsed_tables.keys())

            if len(table_names) > 1 and multi_behavior == "prompt":
                sublime.set_timeout(
                    lambda: self.view.window().show_quick_panel(
                        table_names,
                        lambda idx: self._on_table_selected(idx, conn, parsed_tables, table_names)
                    ),
                    0
                )
            else:
                primary_table = table_names[0]
                self._dispatch_query_panel(conn, primary_table, parsed_tables[primary_table])

        except Exception as e:
            self.safe_close(conn)
            err_msg = str(e)
            sublime.set_timeout(lambda: progress.stop(), 0)
            sublime.set_timeout(lambda: sublime.error_message(f"Ingestion Failed:\n{err_msg}"), 0)

    def _on_table_selected(self, idx, conn, parsed_tables, table_names):
        if idx == -1:
            self.safe_close(conn)
            return
        table_name = table_names[idx]
        self._dispatch_query_panel(conn, table_name, parsed_tables[table_name])

    def _dispatch_query_panel(self, conn, table_name, columns):
        ACTIVE_COMPLETIONS["columns"] = columns
        ACTIVE_COMPLETIONS["table"] = table_name

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        if SilSqliteQueryCommand.last_query and SilSqliteQueryCommand.last_table == table_name:
            initial_query = SilSqliteQueryCommand.last_query
        else:
            template = settings.get("default_query_template", "SELECT * FROM {table}")
            cols_str = ", ".join(columns) if columns else "*"
            initial_query = (
                template
                .replace("{table}", format_sql_identifier(table_name))
                .replace("{columns}", cols_str)
            )
        initial_query = " ".join(initial_query.split())

        def _do_prompt():
            try:
                self.prompt_query(conn, table_name, initial_query)
            except Exception as e:
                self.safe_close(conn)
                print(f"[Rapscallion Tools: SIL] Failed to open query input panel: {e}")

        sublime.set_timeout(_do_prompt, 0)

    def prompt_query(self, conn, table_name, query_text):
        window = self.view.window() or sublime.active_window()
        if not window:
            self.safe_close(conn)
            return

        panel = window.show_input_panel(
            f"SQL Query [{table_name}]:",
            query_text,
            lambda q: self.execute_sql(conn, table_name, q),
            None,
            lambda: self.safe_close(conn)
        )

        if not panel:
            self.safe_close(conn)
            return

        p_settings = panel.settings()
        p_settings.set("is_sil_sql_panel", True)
        p_settings.set("auto_complete", True)
        p_settings.set("auto_complete_use_history", False)
        p_settings.set("auto_complete_commit_on_tab", True)
        p_settings.set("auto_complete_selector", "source")
        p_settings.set("word_wrap", False)

        try:
            panel.assign_syntax("Packages/SQL/SQL.sublime-syntax")
        except Exception:
            pass

        panel.sel().clear()
        panel.sel().add(sublime.Region(panel.size(), panel.size()))

    def safe_close(self, conn):
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    def execute_sql(self, conn, table_name, query):
        if not query.strip():
            self.safe_close(conn)
            return

        start_time = time.time()
        record_query_history(query)
        SilSqliteQueryCommand.last_query = query
        SilSqliteQueryCommand.last_table = table_name

        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            headers = [desc[0] for desc in cursor.description] if cursor.description else []
            self.safe_close(conn)
        except Exception as e:
            sublime.error_message(f"SQL Syntax/Execution Error:\n{e}")
            sublime.set_timeout(lambda: self.prompt_query(conn, table_name, query), 50)
            return

        elapsed = round((time.time() - start_time) * 1000, 1)
        window = self.view.window() or sublime.active_window()
        if not window:
            return

        export_query_results(window, table_name, headers, rows, elapsed)


# ==============================================================================
# Feature: 1-Click Column Value Frequency Analysis (Alt + F)
# ==============================================================================

class SilColumnFrequencyCommand(sublime_plugin.TextCommand):
    """Generates a value frequency distribution report on the current column."""

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        view = self.view
        window = view.window() or sublime.active_window()
        if not window:
            return

        sel = view.sel()
        pt = sel[0].b if sel else 0

        target_col = None
        tab_name = view.name() or ""
        file_name = view.file_name() or ""

        if parse_row_at_point:
            col_idx, field_name, _ = parse_row_at_point(view, pt)
            if field_name and not field_name.startswith("Col "):
                target_col = field_name

        if not target_col and parse_csv_column_at_point:
            if "Results." in tab_name or file_name.lower().endswith(".csv"):
                c_idx, c_name = parse_csv_column_at_point(view, pt)
                if c_name and not c_name.startswith("Col "):
                    target_col = c_name

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        progress = SilProgressIndicator(view, "Analyzing Column Frequency")
        progress.start()

        def _do_analyze():
            conn = None
            try:
                conn, parsed_tables, is_sil = ingest_view_data(view, settings, progress)
                if not parsed_tables:
                    if conn:
                        conn.close()
                    sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - No valid data to analyze."), 0)
                    return

                table_name = list(parsed_tables.keys())[0]
                available_cols = parsed_tables[table_name]

                sublime.set_timeout(lambda: progress.stop(), 0)

                if target_col and target_col.upper() in [c.upper() for c in available_cols]:
                    matched = [c for c in available_cols if c.upper() == target_col.upper()][0]
                    self._execute_frequency(conn, table_name, matched)
                else:
                    def _on_col_selected(idx):
                        if idx == -1:
                            if conn:
                                conn.close()
                            return
                        chosen = available_cols[idx]
                        threading.Thread(
                            target=self._execute_frequency,
                            args=(conn, table_name, chosen),
                            daemon=True
                        ).start()

                    sublime.set_timeout(
                        lambda: window.show_quick_panel(
                            available_cols,
                            _on_col_selected,
                            flags=sublime.MONOSPACE_FONT
                        ),
                        0
                    )
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                err_msg = str(e)
                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(lambda: sublime.error_message(f"Frequency Analysis Failed:\n{err_msg}"), 0)

        threading.Thread(target=_do_analyze, daemon=True).start()

    def _execute_frequency(self, conn, table_name, column_name):
        try:
            cursor = conn.cursor()
            freq_query = f'''
            SELECT
                COALESCE("{column_name}", '(NULL)') AS "{column_name}",
                COUNT(*) AS "Count",
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM "{table_name}"), 2) AS "Percentage %"
            FROM "{table_name}"
            GROUP BY "{column_name}"
            ORDER BY "Count" DESC;
            '''
            start_time = time.time()
            cursor.execute(freq_query)
            rows = cursor.fetchall()
            headers = [desc[0] for desc in cursor.description]

            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            total_records = cursor.fetchone()[0]

            conn.close()
            elapsed = round((time.time() - start_time) * 1000, 1)

            window = self.view.window() or sublime.active_window()
            if not window:
                return

            sublime.set_timeout(
                lambda: export_query_results(
                    window,
                    table_name,
                    headers,
                    rows,
                    elapsed,
                    query_name=f"{column_name} Frequency"
                ),
                0
            )
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            sublime.set_timeout(lambda: sublime.error_message(f"Query Error:\n{e}"), 0)


# ==============================================================================
# Feature: "Goto Column N" & Schema Inspector (Alt + G)
# ==============================================================================

class SilGotoColumnCommand(sublime_plugin.TextCommand):
    """Displays table schema & column jump navigator directly in the editor."""

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        view = self.view
        window = view.window() or sublime.active_window()
        if not window:
            return

        sel = view.sel()
        pt = sel[0].b if sel else 0

        # 1. Retrieve headers for view
        headers = None
        if get_header_fields:
            headers = get_header_fields(view, pt)

        if not headers:
            # Check if CSV
            first_line = view.substr(view.line(0))
            try:
                reader = csv.reader([first_line])
                row = next(reader, None)
                if row and len(row) > 1:
                    headers = [c.strip() for c in row if c.strip()]
            except Exception:
                pass

        if not headers:
            # Fallback search for first SELECT ... FROM
            first_header = view.find(r'(?is)SELECT\s+([^;]+?)\s+FROM\b', 0)
            if first_header:
                txt = view.substr(first_header)
                m = re.search(r'(?is)SELECT\s+(.*?)\s+FROM\b', txt)
                if m:
                    headers = [re.sub(r'["\'\[\]\s]', '', f) for f in m.group(1).split(',') if f.strip()]

        if not headers:
            sublime.status_message("Rapscallion Tools: SIL - No table schema or headers found.")
            return

        # 2. Inspect sample tokens from current line (or first data row)
        cur_line = view.line(pt)
        cur_line_text = view.substr(cur_line)
        spans = extract_row_tokens(cur_line_text)

        target_line = cur_line
        if not spans or (not cur_line_text.lstrip().startswith('(') and len(spans) <= 1):
            # Locate first data row in buffer
            first_data = view.find(r'^\s*\(', 0)
            if first_data:
                target_line = view.line(first_data.begin())
                spans = extract_row_tokens(view.substr(target_line))
            elif view.line(0).end() < view.size():
                # Second row for CSV
                target_line = view.line(view.text_point(1, 0))
                spans = extract_row_tokens(view.substr(target_line))

        # 3. Build quick panel list
        items = []
        for i, h in enumerate(headers):
            val = spans[i][2] if spans and i < len(spans) else ""
            if len(val) > 50:
                val = val[:47] + "..."
            sample_str = f"Value: {val}" if val else "(empty)"
            items.append([f"Col {i + 1}: {h}", sample_str])

        def _on_col_selected(idx):
            if idx == -1:
                return

            col_name = headers[idx]
            line_str = view.substr(target_line)
            line_spans = extract_row_tokens(line_str)

            if line_spans and idx < len(line_spans):
                start_offset, end_offset, tok_text = line_spans[idx]
                col_start = target_line.begin() + start_offset
                col_end = target_line.begin() + end_offset

                settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
                select_inner = settings.get("goto_column_select_inner_value", False)
                if select_inner and len(tok_text) >= 2 and (
                    (tok_text.startswith("'") and tok_text.endswith("'")) or
                    (tok_text.startswith('"') and tok_text.endswith('"'))
                ):
                    sel_region = sublime.Region(col_start + 1, col_end - 1)
                else:
                    sel_region = sublime.Region(col_start, col_end)

                view.sel().clear()
                view.sel().add(sel_region)
                view.show_at_center(sel_region)
                sublime.status_message(f"Rapscallion Tools: SIL - Selected Col {idx + 1}: {col_name}")

                if settings.get("goto_column_show_popup", True) and show_field_popup:
                    sublime.set_timeout(
                        lambda: show_field_popup(view, col_start, idx, col_name, tok_text),
                        80
                    )
            else:
                view.sel().clear()
                view.sel().add(target_line.begin())
                view.show_at_center(target_line.begin())
                sublime.status_message(f"Rapscallion Tools: SIL - Selected Col {idx + 1}: {col_name}")

        window.show_quick_panel(items, _on_col_selected, flags=sublime.MONOSPACE_FONT)


# ==============================================================================
# Feature: Multi-Line SQL Query Scratchpad Tab (Ctrl + Alt + Q)
# ==============================================================================

class SilOpenScratchpadCommand(sublime_plugin.TextCommand):
    """Opens a dedicated multi-line SQL scratchpad tab for querying the active SIL/CSV view."""

    def is_visible(self):
        return is_sil_or_csv_view(self.view) or self.view.settings().get("is_sil_scratchpad", False)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        view = self.view
        window = view.window() or sublime.active_window()
        if not window:
            return

        source_id = view.id()
        current_cc = view.change_count()
        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")

        # Fast-path: extract headers from the head of the buffer (< 50 ms even on 90 MB files)
        fast_headers = extract_headers_fast(view)
        existing = SCRATCHPAD_SESSIONS.get(source_id)

        if existing and existing.get("change_count") == current_cc:
            ready_ev = existing.get("ready_event")
            if existing.get("conn") is not None or (ready_ev and not ready_ev.is_set()):
                tables = existing.get("tables") or fast_headers
                if tables:
                    self._open_scratchpad_view(window, source_id, tables)
                    sublime.status_message("Rapscallion Tools: SIL - Reusing cached SQLite session.")
                    return

        if fast_headers:
            # Open the scratchpad immediately and pre-warm SQLite in the background
            if existing and existing.get("conn"):
                try:
                    existing["conn"].close()
                except Exception:
                    pass

            ready_event = threading.Event()
            session = {
                "conn": None,
                "table_name": list(fast_headers.keys())[0],
                "tables": fast_headers,
                "source_view": view,
                "change_count": current_cc,
                "ready_event": ready_event,
                "error": None,
            }
            SCRATCHPAD_SESSIONS[source_id] = session
            self._open_scratchpad_view(window, source_id, fast_headers)

            progress = SilProgressIndicator(view, "Indexing SIL Data in Background")
            progress.start()

            def _prewarm():
                conn = None
                try:
                    conn, parsed_tables, _ = ingest_view_data(view, settings, progress)
                    if not parsed_tables:
                        if conn:
                            conn.close()
                        session["error"] = "No valid data found."
                        sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - No valid data found."), 0)
                        return
                    session["conn"] = conn
                    session["tables"] = parsed_tables
                    session["table_name"] = list(parsed_tables.keys())[0]
                    ACTIVE_COMPLETIONS["columns"] = parsed_tables[session["table_name"]]
                    ACTIVE_COMPLETIONS["table"] = session["table_name"]
                    ACTIVE_COMPLETIONS["tables"] = list(parsed_tables.keys())
                    sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - SQLite ready for Ctrl+Enter."), 0)
                except Exception as e:
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass
                    session["error"] = str(e)
                    err_msg = str(e)
                    sublime.set_timeout(lambda: progress.stop(), 0)
                    sublime.set_timeout(lambda: sublime.status_message(f"Rapscallion Tools: SIL - Background ingestion error: {err_msg}"), 0)
                finally:
                    ready_event.set()

            threading.Thread(target=_prewarm, daemon=True).start()
            return

        # Fallback if fast header scan didn't find headers
        progress = SilProgressIndicator(view, "Preparing SQL Scratchpad")
        progress.start()

        def _do_open():
            conn = None
            try:
                conn, parsed_tables, _ = ingest_view_data(view, settings, progress)
                if not parsed_tables:
                    if conn:
                        conn.close()
                    sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - No valid data found."), 0)
                    return

                sublime.set_timeout(lambda: progress.stop(), 0)

                old_session = SCRATCHPAD_SESSIONS.get(source_id)
                if old_session and old_session.get("conn"):
                    try:
                        old_session["conn"].close()
                    except Exception:
                        pass
                ready_event = threading.Event()
                ready_event.set()
                SCRATCHPAD_SESSIONS[source_id] = {
                    "conn": conn,
                    "table_name": list(parsed_tables.keys())[0],
                    "tables": parsed_tables,
                    "source_view": view,
                    "change_count": current_cc,
                    "ready_event": ready_event,
                    "error": None,
                }
                sublime.set_timeout(lambda: self._open_scratchpad_view(window, source_id, parsed_tables), 0)
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                err_msg = str(e)
                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(lambda: sublime.error_message(f"Scratchpad Error:\n{err_msg}"), 0)

        threading.Thread(target=_do_open, daemon=True).start()

    def _open_scratchpad_view(self, window, source_id, parsed_tables):
        table_name = list(parsed_tables.keys())[0]
        columns = parsed_tables[table_name]

        ACTIVE_COMPLETIONS["columns"] = columns
        ACTIVE_COMPLETIONS["table"] = table_name
        ACTIVE_COMPLETIONS["tables"] = list(parsed_tables.keys())

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        mode = str(settings.get("scratchpad_mode", "panel")).lower()

        cols_comment = ", ".join(columns[:15]) + ("..." if len(columns) > 15 else "")
        default_sp_tmpl = settings.get("scratchpad_default_query_template", "SELECT *\nFROM {table}\nLIMIT 100;")
        cols_str = ", ".join(columns) if columns else "*"
        default_sql = (
            default_sp_tmpl
            .replace("{table}", format_sql_identifier(table_name))
            .replace("{columns}", cols_str)
        )
        if not default_sql.endswith("\n"):
            default_sql += "\n"

        if mode == "panel":
            initial_sql = (
                f"\n"
                f"-- Table: {table_name} ({len(columns)} columns)\n"
                f"-- Columns: {cols_comment}\n\n"
                f"{default_sql}"
            )
        else:
            initial_sql = (
                f"-- Rapscallion SIL SQL Scratchpad\n"
                f"-- Press Ctrl+Enter to execute query (or selected SQL)\n"
                f"-- Table: {table_name} ({len(columns)} columns)\n"
                f"-- Columns: {cols_comment}\n\n"
                f"{default_sql}"
            )

        if mode == "panel":
            panel = window.find_output_panel(SCRATCHPAD_PANEL_NAME)
            is_same_source = (
                panel is not None
                and panel.settings().get("sil_source_view_id") == source_id
                and panel.size() > 0
            )
            if not is_same_source:
                panel = window.create_output_panel(SCRATCHPAD_PANEL_NAME)
                panel.set_read_only(False)
                panel.settings().set("is_sil_scratchpad", True)
                panel.settings().set("sil_source_view_id", source_id)
                panel.settings().set("sil_table_name", table_name)
                panel.settings().set("auto_complete", True)
                panel.settings().set("auto_complete_commit_on_tab", True)
                panel.settings().set("gutter", True)
                panel.settings().set("line_numbers", True)
                try:
                    panel.assign_syntax("Packages/SQL/SQL.sublime-syntax")
                except Exception:
                    pass
                panel.run_command("append", {"characters": initial_sql})
                self._attach_panel_toolbar(window, panel, table_name)

            window.run_command("show_panel", {"panel": f"output.{SCRATCHPAD_PANEL_NAME}"})
            window.focus_view(panel)
            sublime.status_message(f"Rapscallion Tools: SIL - Scratchpad panel ready for '{table_name}'. Press Ctrl+Enter to run, Esc to close.")
            return

        if mode == "split":
            if window.num_groups() == 1:
                ratio = float(settings.get("scratchpad_split_ratio", 0.35))
                ratio = max(0.15, min(0.70, ratio))
                window.settings().set("sil_scratchpad_saved_layout", window.layout())
                window.set_layout({
                    "cols": [0.0, 1.0],
                    "rows": [0.0, round(1.0 - ratio, 4), 1.0],
                    "cells": [[0, 0, 1, 1], [0, 1, 1, 2]],
                })
            window.focus_group(min(1, window.num_groups() - 1))

        scratch = window.new_file()
        scratch.set_name(f"[{table_name} Query.sql]")
        scratch.set_scratch(True)

        s_settings = scratch.settings()
        s_settings.set("is_sil_scratchpad", True)
        if mode == "split":
            s_settings.set("is_sil_split_scratchpad", True)
        s_settings.set("sil_source_view_id", source_id)
        s_settings.set("sil_table_name", table_name)
        s_settings.set("auto_complete", True)
        s_settings.set("auto_complete_commit_on_tab", True)

        try:
            scratch.assign_syntax("Packages/SQL/SQL.sublime-syntax")
        except Exception:
            pass

        scratch.run_command("append", {"characters": initial_sql})
        sublime.status_message(f"Rapscallion Tools: SIL - Opened scratchpad for '{table_name}'. Press Ctrl+Enter to run.")

    def _attach_panel_toolbar(self, window, panel, table_name):
        import html as _html
        safe_table = _html.escape(table_name)
        toolbar_html = f"""
        <body id="sil-scratchpad-bar">
            <style>
                div.bar {{
                    padding: 3px 8px;
                    background-color: color-mix(in srgb, var(--background) 88%, var(--foreground));
                    border-bottom: 1px solid color-mix(in srgb, var(--foreground) 18%, transparent);
                    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
                    font-size: 11px;
                }}
                span.title {{
                    font-weight: bold;
                    color: var(--foreground);
                    margin-right: 12px;
                }}
                a.btn-run {{
                    color: var(--bluish);
                    text-decoration: none;
                    font-weight: bold;
                    margin-right: 10px;
                }}
                a.btn-close {{
                    color: var(--redish);
                    text-decoration: none;
                    font-weight: bold;
                }}
            </style>
            <div class="bar">
                <span class="title">SIL SQL Scratchpad ({safe_table})</span>
                <a class="btn-run" href="action:run">▶ Run (Ctrl+Enter)</a>
                <a class="btn-close" href="action:close">✕ Close (Esc)</a>
            </div>
        </body>
        """

        def _on_navigate(href):
            if href == "action:run" and panel.is_valid():
                panel.run_command("sil_execute_scratchpad")
            elif href == "action:close" and window.is_valid():
                window.run_command("hide_panel", {"cancel": True})

        p_set = sublime.PhantomSet(panel, "sil_scratchpad_toolbar")
        p_set.update([
            sublime.Phantom(sublime.Region(0, 0), toolbar_html, sublime.LAYOUT_INLINE, _on_navigate)
        ])
        SCRATCHPAD_PHANTOMS[panel.id()] = p_set


class SilExecuteScratchpadCommand(sublime_plugin.TextCommand):
    """Executes SQL in the active scratchpad buffer and outputs results."""

    def is_visible(self):
        return self.view.settings().get("is_sil_scratchpad", False)

    def is_enabled(self):
        return self.view.settings().get("is_sil_scratchpad", False)

    def run(self, edit):
        view = self.view
        window = view.window() or sublime.active_window()
        if not window:
            return

        source_id = view.settings().get("sil_source_view_id")
        table_name = view.settings().get("sil_table_name", "DATA")

        sel = view.sel()
        selected_text = ""
        if sel and not sel[0].empty():
            selected_text = view.substr(sel[0]).strip()

        if selected_text:
            query = selected_text
        else:
            query = view.substr(sublime.Region(0, view.size())).strip()

        clean_lines = []
        for line in query.splitlines():
            stripped = line.strip()
            if not stripped.startswith("--"):
                clean_lines.append(line)
        query = "\n".join(clean_lines).strip()

        if not query:
            sublime.status_message("Rapscallion Tools: SIL - Scratchpad query is empty.")
            return

        session = SCRATCHPAD_SESSIONS.get(source_id)

        progress = SilProgressIndicator(view, "Executing SQL")
        progress.start()

        def _do_execute():
            try:
                cur_session = SCRATCHPAD_SESSIONS.get(source_id)
                if cur_session and cur_session.get("ready_event"):
                    cur_session["ready_event"].wait()

                conn = cur_session.get("conn") if cur_session else None
                is_conn_alive = False
                if conn:
                    try:
                        conn.execute("SELECT 1")
                        is_conn_alive = True
                    except Exception:
                        is_conn_alive = False

                # Check if source view was modified since last ingestion
                source_view = cur_session.get("source_view") if cur_session else None
                if source_view and source_view.is_valid():
                    if cur_session and cur_session.get("change_count") != source_view.change_count():
                        is_conn_alive = False

                if not is_conn_alive:
                    if not source_view or not source_view.is_valid():
                        source_view = None
                        for w in sublime.windows():
                            for v in w.views():
                                if v.id() == source_id:
                                    source_view = v
                                    break
                            if source_view:
                                break
                    if not source_view:
                        sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - Source SIL/CSV file closed."), 0)
                        return

                    if cur_session and cur_session.get("conn"):
                        try:
                            cur_session["conn"].close()
                        except Exception:
                            pass

                    settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
                    conn, parsed_tables, _ = ingest_view_data(source_view, settings, progress)
                    if not parsed_tables:
                        if conn:
                            conn.close()
                        sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - Re-ingestion failed."), 0)
                        return
                    ready_event = threading.Event()
                    ready_event.set()
                    SCRATCHPAD_SESSIONS[source_id] = {
                        "conn": conn,
                        "table_name": table_name,
                        "tables": parsed_tables,
                        "source_view": source_view,
                        "change_count": source_view.change_count(),
                        "ready_event": ready_event,
                        "error": None,
                    }

                record_query_history(query)
                SilSqliteQueryCommand.last_query = query
                SilSqliteQueryCommand.last_table = table_name

                start_time = time.time()
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                headers = [desc[0] for desc in cursor.description] if cursor.description else []
                elapsed = round((time.time() - start_time) * 1000, 1)

                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(
                    lambda: export_query_results(window, table_name, headers, rows, elapsed),
                    0
                )
            except Exception as e:
                err_msg = str(e)
                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(lambda: sublime.error_message(f"SQL Execution Error:\n{err_msg}"), 0)

        threading.Thread(target=_do_execute, daemon=True).start()


# ==============================================================================
# Feature: Query History & Analytical Presets
# ==============================================================================

class SilQueryPresetsCommand(sublime_plugin.TextCommand):
    """Executes preset analytical queries or recalls query history."""

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        view = self.view
        window = view.window() or sublime.active_window()
        if not window:
            return

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        progress = SilProgressIndicator(view, "Preparing Ingestion")
        progress.start()

        def _do_prepare():
            conn = None
            try:
                conn, parsed_tables, _ = ingest_view_data(view, settings, progress)
                if not parsed_tables:
                    if conn:
                        conn.close()
                    sublime.set_timeout(lambda: progress.stop("Rapscallion Tools: SIL - No valid data found."), 0)
                    return

                table_name = list(parsed_tables.keys())[0]
                available_cols = parsed_tables[table_name]
                sublime.set_timeout(lambda: progress.stop(), 0)

                items = []
                for label, sql_tmpl in PRESET_QUERIES:
                    items.append([f"Preset: {label}", sql_tmpl.replace('{table}', table_name)])

                for q in QUERY_HISTORY:
                    items.append(["Recent Query", q])

                def _on_select(idx):
                    if idx == -1:
                        if conn:
                            conn.close()
                        return

                    if idx < len(PRESET_QUERIES):
                        label, tmpl = PRESET_QUERIES[idx]
                        if "{col}" in tmpl:
                            def _on_col_pick(c_idx):
                                if c_idx == -1:
                                    if conn:
                                        conn.close()
                                    return
                                chosen_col = available_cols[c_idx]
                                sql = tmpl.replace("{table}", table_name).replace("{col}", chosen_col)
                                threading.Thread(
                                    target=self._run_query_thread,
                                    args=(conn, table_name, sql),
                                    daemon=True
                                ).start()

                            sublime.set_timeout(
                                lambda: window.show_quick_panel(
                                    available_cols,
                                    _on_col_pick,
                                    flags=sublime.MONOSPACE_FONT
                                ),
                                0
                            )
                        else:
                            sql = tmpl.replace("{table}", table_name)
                            threading.Thread(
                                target=self._run_query_thread,
                                args=(conn, table_name, sql),
                                daemon=True
                            ).start()
                    else:
                        history_idx = idx - len(PRESET_QUERIES)
                        sql = QUERY_HISTORY[history_idx]
                        threading.Thread(
                            target=self._run_query_thread,
                            args=(conn, table_name, sql),
                            daemon=True
                        ).start()

                sublime.set_timeout(
                    lambda: window.show_quick_panel(
                        items,
                        _on_select
                    ),
                    0
                )
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                err_msg = str(e)
                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(lambda: sublime.error_message(f"Presets Error:\n{err_msg}"), 0)

        threading.Thread(target=_do_prepare, daemon=True).start()

    def _run_query_thread(self, conn, table_name, sql):
        record_query_history(sql)
        SilSqliteQueryCommand.last_query = sql
        SilSqliteQueryCommand.last_table = table_name

        start_time = time.time()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            headers = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            elapsed = round((time.time() - start_time) * 1000, 1)

            window = self.view.window() or sublime.active_window()
            if window:
                sublime.set_timeout(
                    lambda: export_query_results(window, table_name, headers, rows, elapsed),
                    0
                )
        except Exception as e:
            err_msg = str(e)
            try:
                conn.close()
            except Exception:
                pass
            sublime.set_timeout(lambda: sublime.error_message(f"Query Execution Error:\n{err_msg}"), 0)


class SilScratchpadLifecycleListener(sublime_plugin.EventListener):
    def on_pre_close(self, view):
        try:
            if view.settings().get("is_sil_split_scratchpad"):
                window = view.window()
                if window and window.settings().has("sil_scratchpad_saved_layout"):
                    sublime.set_timeout(lambda: self._check_collapse_split(window), 50)
        except Exception as e:
            print(f"[RapscallionSILTools] Error in on_pre_close: {e}")

    def _check_collapse_split(self, window):
        try:
            if not window or not window.is_valid():
                return
            if not window.settings().has("sil_scratchpad_saved_layout"):
                return
            has_split_scratchpad = any(
                v.settings().get("is_sil_split_scratchpad", False)
                for v in window.views()
            )
            if not has_split_scratchpad and window.num_groups() > 1:
                # Only collapse if the secondary group is empty
                if len(window.views_in_group(1)) == 0:
                    saved = window.settings().get("sil_scratchpad_saved_layout")
                    window.settings().erase("sil_scratchpad_saved_layout")
                    if saved and isinstance(saved, dict) and "cols" in saved:
                        window.set_layout(saved)
                    else:
                        window.set_layout({"cols": [0.0, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1]]})
                else:
                    window.settings().erase("sil_scratchpad_saved_layout")
        except Exception as e:
            print(f"[RapscallionSILTools] Error collapsing split layout: {e}")

    def on_close(self, view):
        try:
            vid = view.id()
            SCRATCHPAD_PHANTOMS.pop(vid, None)
            if vid in SCRATCHPAD_SESSIONS:
                session = SCRATCHPAD_SESSIONS.pop(vid, None)
                if session and session.get("conn"):
                    try:
                        session["conn"].close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[RapscallionSILTools] Error in on_close: {e}")


# ==============================================================================
# Feature: Markdown Table Result Formatter Toggle
# ==============================================================================

class SilToggleResultFormatCommand(sublime_plugin.TextCommand):
    """Toggles default query result format between CSV and Markdown table"""

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view)

    def run(self, edit):
        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        current_fmt = settings.get("default_result_format", "csv").lower()
        new_fmt = "markdown" if current_fmt == "csv" else "csv"
        settings.set("default_result_format", new_fmt)
        sublime.save_settings("RapscallionSILTools.sublime-settings")
        sublime.status_message(f"Rapscallion Tools: SIL - Default result format set to {new_fmt.upper()}.")