# -*- coding: utf-8 -*-
"""Unit tests for RapscallionMarkdown parser and localhost SSE server."""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PKG_DIR not in sys.path:
    sys.path.insert(0, PKG_DIR)

from md_parser import extract_headings, render_browser_fragment, render_minihtml
from md_server import MarkdownPreviewServer


class TestMarkdownParser(unittest.TestCase):
    def test_headings_and_slugs(self):
        md = "# Hello World\n```python\n# not a heading\n```\n## Sub Section!\n"
        headings = extract_headings(md)
        self.assertEqual(
            headings,
            [
                (1, "Hello World", 1, "hello-world"),
                (2, "Sub Section!", 5, "sub-section"),
            ],
        )

    def test_minihtml_escapes_html_and_renders_tasks(self):
        md = "# Title <script>alert(1)</script>\n\n- [ ] Open task\n- [x] Done task\n"
        out = render_minihtml(md, source_path="notes.md", title="notes.md")
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertIn("subl:rapscallion_markdown_toggle_task", out)
        self.assertIn("[ ]", out)
        self.assertIn("[x]", out)

    def test_browser_fragment_tables_callouts_and_code(self):
        md = (
            "> [!WARNING]\n"
            "> Watch out for **bold** and `inline`.\n\n"
            "| Name | Score |\n"
            "| :--- | ---: |\n"
            "| Alice | 100 |\n\n"
            "```py\nprint('hi')\n```\n"
        )
        frag = render_browser_fragment(md)
        self.assertIn("callout-warning", frag)
        self.assertIn("<strong>bold</strong>", frag)
        self.assertIn("<code>inline</code>", frag)
        self.assertIn('<table data-line="4">', frag)
        self.assertIn('style="text-align:right"', frag)
        self.assertIn("copy-btn", frag)
        self.assertIn("language-py", frag)


class TestMarkdownServer(unittest.TestCase):
    def test_server_serves_index_publish_toggle_and_blocks_traversal(self):
        srv = MarkdownPreviewServer()
        toggled = []
        srv.set_toggle_task_callback(lambda line, path: toggled.append((line, path)))

        with tempfile.TemporaryDirectory() as tmpdir:
            img_path = os.path.join(tmpdir, "pic.txt")
            with open(img_path, "wb") as f:
                f.write(b"hello-asset")

            md_path = os.path.join(tmpdir, "doc.md")
            url = srv.start()
            try:
                srv.publish(
                    html_fragment="<h1>Live</h1>",
                    title="doc.md",
                    source_path=md_path,
                    cursor_line=3,
                    allowed_roots=[tmpdir],
                )

                with urllib.request.urlopen(url, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    body = resp.read().decode("utf-8")
                    self.assertIn("<h1>Live</h1>", body)
                    self.assertIn("doc.md", body)

                # Valid relative asset
                with urllib.request.urlopen(url + "asset?path=pic.txt", timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(resp.read(), b"hello-asset")

                # Path traversal must be rejected
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(url + "asset?path=../../Windows/win.ini", timeout=3)
                self.assertEqual(ctx.exception.code, 404)

                # Checkbox toggle POST
                req = urllib.request.Request(
                    url + "action/toggle_task",
                    data=json.dumps({"line": 7}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(resp.status, 200)
                self.assertEqual(toggled, [(7, md_path)])
            finally:
                srv.stop()


if __name__ == "__main__":
    unittest.main()
