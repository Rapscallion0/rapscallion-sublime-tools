import sublime
import sublime_plugin
import sqlite3
import re
import csv
import io
import time
import threading

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
    ("CAST AS NUMERIC", "CAST(${1} AS NUMERIC)"),
    ("DISTINCT", "DISTINCT "),
    ("ASC", "ASC"),
    ("DESC", "DESC"),
    ("AND", "AND "),
    ("OR", "OR "),
    ("NOT", "NOT "),
    ("BETWEEN", "BETWEEN ${1} AND ${2}")
]


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
        self.view.set_status("sil_query_progress", "{0} {1}...".format(frame, self.label))
        self.step += 1
        sublime.set_timeout(self._animate, 80)

    def stop(self, final_msg=""):
        self.is_running = False
        self.view.erase_status("sil_query_progress")
        if final_msg:
            sublime.status_message(final_msg)


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

            from_snippet = "FROM ${{1:{0}}} ".format(tbl)
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


class SilSqliteQueryCommand(sublime_plugin.TextCommand):
    last_query = None
    last_table = None

    def is_enabled(self):
        return self.view.size() > 0

    def run(self, edit):
        sample = self.view.substr(sublime.Region(0, min(self.view.size(), 2048))).strip()
        if not sample:
            sublime.status_message("Rapscallion Tools: SIL - Buffer is empty.")
            return

        file_name = self.view.file_name() or ""
        tab_name = self.view.name() or ""
        syntax = self.view.settings().get("syntax", "")

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
            sublime.status_message("Rapscallion Tools: SIL - Active file is not a SIL view or CSV table.")
            return

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        is_async = settings.get("async_ingestion", True)

        progress = SilProgressIndicator(self.view, "Ingesting SIL Data")
        progress.start()

        if is_async:
            threading.Thread(
                target=self._run_ingestion,
                args=(is_sil, tab_name, settings, progress)
            ).start()
        else:
            self._run_ingestion(is_sil, tab_name, settings, progress)

    def _run_ingestion(self, is_sil, tab_name, settings, progress):
        try:
            full_text = self.view.substr(sublime.Region(0, self.view.size()))
            # check_same_thread=False allows query panel to access this DB from the main UI thread
            conn = sqlite3.connect(":memory:", check_same_thread=False)

            if is_sil:
                parsed_tables = self._ingest_sil(conn, full_text, settings)
            else:
                parsed_tables = self._ingest_csv(conn, full_text, tab_name)

            if not parsed_tables:
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
            sublime.set_timeout(lambda: sublime.error_message("Ingestion Failed:\n" + str(e)), 0)

    def _ingest_sil(self, conn, text, settings):
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

            semi_idx = chunk.rfind(";")
            if semi_idx != -1:
                tuples_blob = chunk[:semi_idx + 1].strip()
            else:
                last_paren = chunk.rfind(")")
                if last_paren == -1:
                    continue
                tuples_blob = chunk[:last_paren + 1].strip() + ";"

            cleaned_blob = tuples_blob
            prev_blob = ""
            while prev_blob != cleaned_blob:
                prev_blob = cleaned_blob
                cleaned_blob = re.sub(r',\s*(?=,)', ',NULL', cleaned_blob)
                cleaned_blob = re.sub(r'\(\s*,', '(NULL,', cleaned_blob)
                cleaned_blob = re.sub(r',\s*\)', ',NULL)', cleaned_blob)

            cols_def = ", ".join(['"{0}" TEXT'.format(c) for c in raw_cols])
            cursor.execute('CREATE TABLE "{0}" ({1});'.format(table_name, cols_def))
            cursor.execute('INSERT INTO "{0}" VALUES\n{1}'.format(table_name, cleaned_blob))

            parsed[table_name] = raw_cols

            multi_behavior = settings.get("multi_table_behavior", "prompt")
            if multi_behavior == "first":
                break

        conn.commit()
        return parsed

    def _ingest_csv(self, conn, text, tab_name):
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
            name = raw_name if raw_name else "col_" + str(i + 1)
            if name in seen_counts:
                seen_counts[name] += 1
                deduped_name = "{0}_{1}".format(name, seen_counts[name])
            else:
                seen_counts[name] = 0
                deduped_name = name
            cols.append(deduped_name)

        cursor = conn.cursor()
        cols_def = ", ".join(['"{0}" TEXT'.format(c) for c in cols])
        cursor.execute('CREATE TABLE "{0}" ({1});'.format(table_name, cols_def))

        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = 'INSERT INTO "{0}" VALUES ({1})'.format(table_name, placeholders)

        data_rows = []
        col_count = len(cols)
        for row in reader:
            if not row:
                continue
            if len(row) < col_count:
                row.extend([None] * (col_count - len(row)))
            elif len(row) > col_count:
                row = row[:col_count]
            data_rows.append(row)

        cursor.executemany(insert_sql, data_rows)
        conn.commit()
        return {table_name: cols}

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
            "SQL Query [" + table_name + "]:",
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
            sublime.error_message("SQL Syntax/Execution Error:\n" + str(e))
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
        new_view.set_name(table_name + " Results.csv")
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
        sublime.status_message("Rapscallion Tools: SIL - " + str(len(rows)) + " rows returned in " + str(elapsed) + "ms.")