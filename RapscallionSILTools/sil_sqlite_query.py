import sublime
import sublime_plugin
import sqlite3
import re
import csv
import io
import time
import threading

try:
    from .sil_field_hover import parse_row_at_point, parse_csv_column_at_point, get_header_fields, is_sil_or_csv_view
except Exception:
    parse_row_at_point = None
    parse_csv_column_at_point = None
    get_header_fields = None
    is_sil_or_csv_view = lambda view: False

ACTIVE_COMPLETIONS = {
    "columns": [],
    "tables": [],
    "table": "DATA"
}

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
        if not self.is_running:
            return
        frame = self.spinner[self.step % len(self.spinner)]
        self.view.set_status("sil_query_progress", f"{frame} {self.label}...")
        self.step += 1
        sublime.set_timeout(self._animate, 80)

    def stop(self, final_msg=""):
        self.is_running = False
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
    ('next', ...)
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
                if ch == "'":
                    if i + 1 < length and chunk[i + 1] == "'":
                        current_token.append("'")
                        i += 2
                        continue
                    else:
                        in_squote = False
                        i += 1
                        continue
                else:
                    current_token.append(ch)
                    i += 1
                    continue

            if in_dquote:
                if ch == '"':
                    if i + 1 < length and chunk[i + 1] == '"':
                        current_token.append('"')
                        i += 2
                        continue
                    else:
                        in_dquote = False
                        i += 1
                        continue
                else:
                    current_token.append(ch)
                    i += 1
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
# Auto-Completions Listener for SQL Query Input Panel
# ==============================================================================

class SilSqliteCompletionListener(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        try:
            if not view.settings().get("is_sil_sql_panel"):
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

            text_before = view.substr(sublime.Region(0, pt))
            prev_char = view.substr(pt - 1)

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
    full_text = view.substr(sublime.Region(0, view.size()))
    file_name = view.file_name() or ""
    tab_name = view.name() or ""
    syntax = view.settings().get("syntax", "")
    sample = full_text[:2048].strip()

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
    )

    if not is_sil and not is_csv:
        return None, None, None

    conn = sqlite3.connect(":memory:", check_same_thread=False)

    if is_sil:
        parsed_tables = _ingest_sil(conn, full_text, settings)
    else:
        parsed_tables = _ingest_csv(conn, full_text, tab_name, settings)

    return conn, parsed_tables, is_sil


def _ingest_sil(conn, text, settings):
    cursor = conn.cursor()
    parsed = {}

    view_pattern = re.compile(
        r'CREATE\s+VIEW\s+(\w+)\s+AS\s+SELECT\s+([^;]+?)\s+FROM',
        re.IGNORECASE
    )

    for match in view_pattern.finditer(text):
        table_name = match.group(1).strip()
        raw_cols = [c.strip().upper() for c in match.group(2).split(',') if c.strip()]

        values_idx = text.upper().find("VALUES", match.end())
        if values_idx == -1:
            continue

        blob_start = text.find("(", values_idx)
        if blob_start == -1:
            continue

        subsequent_directive = re.search(r'[\r\n]+\s*(@|CREATE\s+VIEW)', text[blob_start:], re.IGNORECASE)
        if subsequent_directive:
            chunk = text[blob_start : blob_start + subsequent_directive.start()]
        else:
            chunk = text[blob_start:]

        # Fast stateful lexer parses row tuples without regex string replacement
        parsed_rows = list(parse_sil_tuples(chunk, len(raw_cols)))
        if not parsed_rows:
            continue

        # Dynamic type inference
        sample_size = settings.get("type_inference_sample_size", 100)
        col_types = infer_column_types(raw_cols, parsed_rows, sample_size) if sample_size > 0 else ["TEXT"] * len(raw_cols)

        cols_def = ", ".join([f'"{c}" {t}' for c, t in zip(raw_cols, col_types)])
        cursor.execute(f'CREATE TABLE "{table_name}" ({cols_def});')

        placeholders = ", ".join(["?"] * len(raw_cols))
        insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'

        # Batch insertion with typed value conversion
        batch_size = settings.get("ingestion_batch_size", 5000)
        for i in range(0, len(parsed_rows), batch_size):
            batch = parsed_rows[i : i + batch_size]
            converted_batch = []
            for row in batch:
                conv_row = []
                for val, ctype in zip(row, col_types):
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
                converted_batch.append(conv_row)
            cursor.executemany(insert_sql, converted_batch)

        parsed[table_name] = raw_cols

        multi_behavior = settings.get("multi_table_behavior", "prompt")
        if multi_behavior == "first":
            break

    conn.commit()
    return parsed


def _ingest_csv(conn, text, tab_name, settings):
    if "Results.csv" in tab_name:
        base_name = tab_name.replace(" Results.csv", "").strip()
        table_name = (base_name + "_SUB") if base_name else "DATA"
    else:
        table_name = "DATA"

    reader = csv.reader(io.StringIO(text))
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

    rows = list(reader)

    # Dynamic type inference for CSV tables
    sample_size = settings.get("type_inference_sample_size", 100)
    col_types = infer_column_types(cols, rows, sample_size) if sample_size > 0 else ["TEXT"] * len(cols)

    cursor = conn.cursor()
    cols_def = ", ".join([f'"{c}" {t}' for c, t in zip(cols, col_types)])
    cursor.execute(f'CREATE TABLE "{table_name}" ({cols_def});')

    placeholders = ", ".join(["?"] * len(cols))
    insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders})'

    batch_size = settings.get("ingestion_batch_size", 5000)
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        converted_batch = []
        for r in batch:
            row_len = len(r)
            conv_row = []
            for col_idx in range(len(cols)):
                val = r[col_idx] if col_idx < row_len else None
                ctype = col_types[col_idx]
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
            converted_batch.append(conv_row)
        cursor.executemany(insert_sql, converted_batch)

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
                args=(settings, progress)
            ).start()
        else:
            self._run_ingestion_thread(settings, progress)

    def _run_ingestion_thread(self, settings, progress):
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
            sublime.set_timeout(lambda: progress.stop(), 0)
            sublime.set_timeout(lambda: sublime.error_message(f"Ingestion Failed:\n{e}"), 0)

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
            initial_query = template.replace("{table}", table_name)

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

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        delimiter = settings.get("export_delimiter", ",")

        output_buffer = io.StringIO()
        writer = csv.writer(output_buffer, delimiter=delimiter, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
        csv_text = output_buffer.getvalue()

        window = self.view.window() or sublime.active_window()
        if not window:
            sublime.status_message("Rapscallion Tools: SIL - Window is no longer available.")
            return

        new_view = window.new_file()
        new_view.set_name(f"{table_name} Results.csv")
        new_view.set_scratch(True)

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

        new_view.run_command("append", {"characters": csv_text})
        sublime.status_message(f"Rapscallion Tools: SIL - {len(rows)} rows returned in {elapsed}ms.")


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
        window = view.window()
        if not window:
            return

        sel = view.sel()
        pt = sel[0].b if sel else 0

        target_col = None
        tab_name = view.name() or ""
        file_name = view.file_name() or ""

        # 1. Attempt detection via SIL row parser
        if parse_row_at_point:
            col_idx, field_name, _ = parse_row_at_point(view, pt)
            if field_name and not field_name.startswith("Col "):
                target_col = field_name

        # 2. Attempt detection via CSV column parser
        if not target_col and parse_csv_column_at_point:
            if "Results.csv" in tab_name or file_name.lower().endswith(".csv"):
                c_idx, c_name = parse_csv_column_at_point(view, pt)
                if c_name and not c_name.startswith("Col "):
                    target_col = c_name

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        progress = SilProgressIndicator(view, "Analyzing Column Frequency")
        progress.start()

        def _do_analyze():
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
                    # Exact column already detected under cursor
                    matched = [c for c in available_cols if c.upper() == target_col.upper()][0]
                    self._execute_frequency(conn, table_name, matched)
                else:
                    # Prompt user to select column via Quick Panel
                    def _on_col_selected(idx):
                        if idx == -1:
                            if conn:
                                conn.close()
                            return
                        chosen = available_cols[idx]
                        self._execute_frequency(conn, table_name, chosen)

                    sublime.set_timeout(
                        lambda: window.show_quick_panel(
                            available_cols,
                            _on_col_selected,
                            flags=sublime.MONOSPACE_FONT
                        ),
                        0
                    )
            except Exception as e:
                sublime.set_timeout(lambda: progress.stop(), 0)
                sublime.set_timeout(lambda: sublime.error_message(f"Frequency Analysis Failed:\n{e}"), 0)

        threading.Thread(target=_do_analyze).start()

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

            output_buffer = io.StringIO()
            writer = csv.writer(output_buffer, delimiter=",", lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)
            csv_text = output_buffer.getvalue()

            window = self.view.window() or sublime.active_window()
            if not window:
                return

            def _show_results():
                new_view = window.new_file()
                new_view.set_name(f"{table_name} - {column_name} Frequency.csv")
                new_view.set_scratch(True)

                syntax_candidates = [
                    "Packages/rainbow_csv/pregenerated_grammars/CSV (Rainbow).sublime-syntax",
                    "Packages/Rainbow CSV/CSV (Rainbow).sublime-syntax",
                    "Packages/CSV/CSV.sublime-syntax"
                ]
                for candidate in syntax_candidates:
                    if sublime.find_resources(candidate.split("/")[-1]):
                        try:
                            new_view.assign_syntax(candidate)
                            break
                        except Exception:
                            continue

                new_view.run_command("append", {"characters": csv_text})
                sublime.status_message(
                    f"Rapscallion Tools: SIL - {column_name}: {len(rows)} unique values across {total_records} rows ({elapsed}ms)."
                )

            sublime.set_timeout(_show_results, 0)
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            sublime.set_timeout(lambda: sublime.error_message(f"Query Error:\n{e}"), 0)