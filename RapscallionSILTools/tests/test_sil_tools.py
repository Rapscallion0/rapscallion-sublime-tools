import os
import re
import sys
import tempfile
import types
import unittest


def _install_sublime_stubs():
    """Install minimal sublime and sublime_plugin stubs for standalone testing."""
    if "sublime" not in sys.modules:
        sublime_mod = types.ModuleType("sublime")

        class Region:
            def __init__(self, a, b=None):
                self.a = a
                self.b = a if b is None else b

            def begin(self):
                return min(self.a, self.b)

            def end(self):
                return max(self.a, self.b)

        class _Settings(dict):
            def get(self, key, default=None):
                return super().get(key, default)

        sublime_mod.Region = Region
        sublime_mod.HOVER_TEXT = 1
        sublime_mod.HIDE_ON_MOUSE_MOVE_AWAY = 1
        sublime_mod.load_settings = lambda _name: _Settings()
        sublime_mod.status_message = lambda _msg: None
        sublime_mod.windows = lambda: []
        sys.modules["sublime"] = sublime_mod

    if "sublime_plugin" not in sys.modules:
        sp_mod = types.ModuleType("sublime_plugin")
        sp_mod.TextCommand = object
        sp_mod.WindowCommand = object
        sp_mod.ApplicationCommand = object
        sp_mod.EventListener = object
        sys.modules["sublime_plugin"] = sp_mod


_install_sublime_stubs()

import sublime  # noqa: E402

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PKG_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from RapscallionSILTools import sil_field_hover  # noqa: E402
from RapscallionSILTools import sil_sqlite_query  # noqa: E402


class FakeView:
    def __init__(self, text, file_name="", name="", syntax="", view_id=1, dirty=False, virtual_size=None):
        self._text = text
        self._file_name = file_name
        self._name = name
        self._settings = {"syntax": syntax}
        self._id = view_id
        self._dirty = dirty
        self._change_count = 1
        self._virtual_size = virtual_size
        self.find_all_calls = 0

    def id(self):
        return self._id

    def is_valid(self):
        return True

    def is_dirty(self):
        return self._dirty

    def change_count(self):
        return self._change_count

    def bump_change_count(self):
        self._change_count += 1

    def size(self):
        return self._virtual_size if self._virtual_size is not None else len(self._text)

    def file_name(self):
        return self._file_name

    def name(self):
        return self._name

    def settings(self):
        return self._settings

    def score_selector(self, _pt, scope):
        return 1 if ("SIL" in self._settings.get("syntax", "") and scope == "text.rainbow.sil") else 0

    def substr(self, region):
        if isinstance(region, int):
            return self._text[region]
        return self._text[region.begin():region.end()]

    def line(self, pt):
        start = self._text.rfind("\n", 0, pt) + 1
        end = self._text.find("\n", pt)
        if end == -1:
            end = len(self._text)
        return sublime.Region(start, end)

    def find_all(self, pattern):
        self.find_all_calls += 1
        return [sublime.Region(m.start(), m.end()) for m in re.finditer(pattern, self._text)]


class TestSilFieldHover(unittest.TestCase):
    def setUp(self):
        sil_field_hover.CACHE_HEADERS.clear()

    def test_get_header_fields_caches_with_point_and_invalidates_on_change(self):
        text = (
            "@CREATE(TBL1)\n"
            "CREATE VIEW TBL1 AS SELECT ID, NAME, AMOUNT FROM DUAL VALUES\n"
            "(1, 'Alpha', 10.50),\n"
            "(2, 'Beta', 20.00);\n"
        )
        view = FakeView(text, file_name="test.sil", view_id=101)
        pt = text.index("(2,") + 4

        fields1 = sil_field_hover.get_header_fields(view, point=pt)
        self.assertEqual(fields1, ["ID", "NAME", "AMOUNT"])
        self.assertEqual(view.find_all_calls, 1)

        # Second call with point should hit cache without scanning again
        fields2 = sil_field_hover.get_header_fields(view, point=pt + 5)
        self.assertEqual(fields2, ["ID", "NAME", "AMOUNT"])
        self.assertEqual(view.find_all_calls, 1)

        # Modifying the buffer invalidates via change_count
        view.bump_change_count()
        fields3 = sil_field_hover.get_header_fields(view, point=pt)
        self.assertEqual(fields3, ["ID", "NAME", "AMOUNT"])
        self.assertEqual(view.find_all_calls, 2)

    def test_get_header_fields_multi_table_selection_by_point(self):
        text = (
            "CREATE VIEW T1 AS SELECT A, B FROM DUAL VALUES\n"
            "(1, 'x');\n"
            "CREATE VIEW T2 AS SELECT C, D, E FROM DUAL VALUES\n"
            "(2, 'y', 'z');\n"
        )
        view = FakeView(text, file_name="multi.sil", view_id=102)
        pt1 = text.index("(1,")
        pt2 = text.index("(2,")

        self.assertEqual(sil_field_hover.get_header_fields(view, point=pt1), ["A", "B"])
        self.assertEqual(sil_field_hover.get_header_fields(view, point=pt2), ["C", "D", "E"])
        self.assertEqual(view.find_all_calls, 1)

    def test_get_header_fields_skips_find_all_on_large_files(self):
        text = "CREATE VIEW BIG AS SELECT COL1, COL2 FROM DUAL VALUES\n(1, 'ok');\n"
        view = FakeView(text, file_name="big.sql", view_id=103, virtual_size=5 * 1024 * 1024)

        fields = sil_field_hover.get_header_fields(view, point=len(text) - 5)
        self.assertEqual(fields, ["COL1", "COL2"])
        self.assertEqual(view.find_all_calls, 0)

    def test_parse_row_at_point_quotes_and_commas(self):
        text = (
            "CREATE VIEW T AS SELECT ID, DESC, QTY FROM DUAL VALUES\n"
            "(42, 'Apples, Red', 7);\n"
        )
        view = FakeView(text, file_name="row.sil", view_id=104)
        pt = text.index("Red")
        col_idx, field_name, token = sil_field_hover.parse_row_at_point(view, pt)
        self.assertEqual(col_idx, 1)
        self.assertEqual(field_name, "DESC")
        self.assertEqual(token[2].strip(), "'Apples, Red'")


class TestSilSqliteQuery(unittest.TestCase):
    def test_parse_sil_tuples_handles_escapes_commas_and_nulls(self):
        chunk = "(1, 'O''Reilly, Inc.', , NULL, 3.14),\n(2, 'Plain', 'x', 'y', '');\n"
        rows = list(sil_sqlite_query.parse_sil_tuples(chunk, 5))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ["1", "O'Reilly, Inc.", None, None, "3.14"])
        self.assertEqual(rows[1], ["2", "Plain", "x", "y", ""])

    def test_ingest_view_data_sil_in_memory(self):
        text = (
            "@CREATE(ITEMS)\n"
            "CREATE VIEW ITEMS AS SELECT ID, NAME, PRICE FROM DUAL VALUES\n"
            "(1, 'Milk', 3.50),\n"
            "(2, 'Bread', 2.25),\n"
            "(3, '', NULL);\n"
        )
        view = FakeView(text, file_name="items.sil", syntax="SIL (Rainbow)", view_id=201)
        settings = {"type_inference_sample_size": 100, "ingestion_batch_size": 2, "multi_table_behavior": "prompt"}
        conn, tables, is_sil = sil_sqlite_query.ingest_view_data(view, settings)
        self.assertTrue(is_sil)
        self.assertEqual(tables, {"ITEMS": ["ID", "NAME", "PRICE"]})

        rows = conn.execute('SELECT ID, NAME, PRICE FROM "ITEMS" ORDER BY ID').fetchall()
        self.assertEqual(rows, [(1, "Milk", 3.5), (2, "Bread", 2.25), (3, None, None)])
        conn.close()

    def test_ingest_view_data_csv(self):
        text = "id,label,amount\n10,Alpha,1.5\n20,Beta,2.5\n"
        view = FakeView(text, file_name="data.csv", syntax="CSV", view_id=202)
        settings = {"type_inference_sample_size": 100, "ingestion_batch_size": 5000}
        conn, tables, is_sil = sil_sqlite_query.ingest_view_data(view, settings)
        self.assertFalse(is_sil)
        self.assertEqual(tables, {"DATA": ["ID", "LABEL", "AMOUNT"]})

        rows = conn.execute('SELECT ID, LABEL, AMOUNT FROM "DATA" ORDER BY ID').fetchall()
        self.assertEqual(rows, [(10, "Alpha", 1.5), (20, "Beta", 2.5)])
        conn.close()

    def test_ingest_view_data_streams_large_clean_file_from_disk(self):
        with tempfile.NamedTemporaryFile("w", suffix=".sil", delete=False, encoding="utf-8") as tmp:
            tmp.write("@CREATE(BIG)\nCREATE VIEW BIG AS SELECT ID, VAL FROM DUAL VALUES\n")
            for i in range(1, 201):
                sep = ";" if i == 200 else ","
                tmp.write(f"({i}, 'row_{i}'){sep}\n")
            tmp_path = tmp.name

        try:
            # virtual_size > 5 MB triggers disk-streaming path while view._text only has the header sample
            sample_only = "@CREATE(BIG)\nCREATE VIEW BIG AS SELECT ID, VAL FROM DUAL VALUES\n"
            view = FakeView(
                sample_only,
                file_name=tmp_path,
                syntax="SIL (Rainbow)",
                view_id=203,
                dirty=False,
                virtual_size=6 * 1024 * 1024,
            )
            settings = {"type_inference_sample_size": 50, "ingestion_batch_size": 60, "multi_table_behavior": "prompt"}
            conn, tables, is_sil = sil_sqlite_query.ingest_view_data(view, settings)
            self.assertTrue(is_sil)
            self.assertEqual(tables, {"BIG": ["ID", "VAL"]})
            count = conn.execute('SELECT COUNT(*) FROM "BIG"').fetchone()[0]
            self.assertEqual(count, 200)
            conn.close()
        finally:
            os.remove(tmp_path)

    def test_extract_headers_fast_sil_and_csv(self):
        sil_text = "@CREATE(HUGE)\nCREATE VIEW HUGE AS SELECT \"ID\", [NAME], PRICE FROM DUAL VALUES\n(1, 'A', 2.0);\n"
        sil_view = FakeView(sil_text, file_name="huge.sil", syntax="SIL (Rainbow)", view_id=204, virtual_size=90 * 1024 * 1024)
        self.assertEqual(sil_sqlite_query.extract_headers_fast(sil_view), {"HUGE": ["ID", "NAME", "PRICE"]})

        csv_view = FakeView("col a,col b\n1,2\n", file_name="huge.csv", syntax="CSV", view_id=205)
        self.assertEqual(sil_sqlite_query.extract_headers_fast(csv_view), {"DATA": ["COL_A", "COL_B"]})

    def test_parse_sil_tuples_double_quotes_and_unterminated(self):
        chunk = '(1, "say ""hi""", \'plain\');\n'
        rows = list(sil_sqlite_query.parse_sil_tuples(chunk, 3))
        self.assertEqual(rows, [["1", 'say "hi"', "plain"]])

    def test_format_sql_identifier(self):
        self.assertEqual(sil_sqlite_query.format_sql_identifier("Rpt_Fin_Load"), "Rpt_Fin_Load")
        self.assertEqual(sil_sqlite_query.format_sql_identifier("My Table"), '"My Table"')
        self.assertEqual(sil_sqlite_query.format_sql_identifier('Weird"Name'), '"Weird""Name"')


if __name__ == "__main__":
    unittest.main()
