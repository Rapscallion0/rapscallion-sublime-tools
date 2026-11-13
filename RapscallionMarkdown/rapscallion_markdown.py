# -*- coding: utf-8 -*-
"""RapscallionMarkdown — Live Markdown viewer & editor for Sublime Text 4.

Provides:
  - Theme-aware minihtml side-panel preview (HtmlSheet)
  - Zero-dependency localhost SSE live browser preview
  - Interactive checkbox toggling, heading jump, and relative link navigation
"""

import os
import re
import threading
import webbrowser
from typing import Dict, Optional

import sublime
import sublime_plugin

from .md_parser import render_browser_fragment, render_minihtml
from .md_server import MarkdownPreviewServer


SETTINGS_FILE = "RapscallionMarkdown.sublime-settings"
PANEL_SHEET_ID_KEY = "rapscallion_markdown_sheet_id"
SAVED_LAYOUT_KEY = "rapscallion_markdown_saved_layout"
SOURCE_VIEW_ID_KEY = "rapscallion_markdown_source_view_id"
STATUS_KEY = "rapscallion_markdown_server"

_TASK_LINE_RE = re.compile(r"^(\s*(?:[-*+]|\d+\.)\s+\[)([ xX])(\]\s+.*)$")

_SERVER = MarkdownPreviewServer()
_DEBOUNCE_LOCK = threading.Lock()
_DEBOUNCE_TIMERS: Dict[int, threading.Timer] = {}
_WATCHED_WINDOWS = set()


def get_setting(key: str, default=None):
    s = sublime.load_settings(SETTINGS_FILE)
    return s.get(key, default)


def is_markdown_view(view: Optional[sublime.View]) -> bool:
    if view is None or not view.is_valid():
        return False
    if view.settings().get("is_widget"):
        return False
    if not view.sel():
        return False
    pt = view.sel()[0].begin()
    return view.match_selector(pt, "text.html.markdown")


def get_view_title(view: sublime.View) -> str:
    fname = view.file_name()
    if fname:
        return os.path.basename(fname)
    return view.name() or "Untitled.md"


def get_cursor_line(view: sublime.View) -> int:
    if not view.sel():
        return 1
    row, _ = view.rowcol(view.sel()[0].begin())
    return row + 1


def find_preview_sheet(window: Optional[sublime.Window]) -> Optional[sublime.HtmlSheet]:
    if not window:
        return None
    sheet_id = window.settings().get(PANEL_SHEET_ID_KEY)
    if not sheet_id:
        return None
    for sheet in window.sheets():
        if isinstance(sheet, sublime.HtmlSheet) and sheet.id() == sheet_id:
            return sheet
    return None


def _get_panel_groups() -> tuple:
    side = get_setting("preview_panel_side", "right")
    if side == "left":
        return 0, 1
    return 1, 0


def _restore_layout(window: sublime.Window) -> None:
    saved = window.settings().get(SAVED_LAYOUT_KEY)
    if saved and isinstance(saved, dict) and "cols" in saved:
        window.set_layout(saved)
        window.settings().erase(SAVED_LAYOUT_KEY)
    else:
        window.set_layout({
            "cols": [0.0, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1]],
        })
    window.settings().erase(PANEL_SHEET_ID_KEY)
    window.settings().erase(SOURCE_VIEW_ID_KEY)


def _check_and_restore_layout(window: Optional[sublime.Window]) -> None:
    if not window or not window.is_valid():
        return
    if window.settings().get(PANEL_SHEET_ID_KEY) and find_preview_sheet(window) is None:
        _restore_layout(window)


def _start_panel_watchdog(window: sublime.Window) -> None:
    wid = window.id()
    if wid in _WATCHED_WINDOWS:
        return
    _WATCHED_WINDOWS.add(wid)

    def _tick():
        if not window.is_valid():
            _WATCHED_WINDOWS.discard(wid)
            return
        if not window.settings().get(PANEL_SHEET_ID_KEY):
            _WATCHED_WINDOWS.discard(wid)
            return
        if find_preview_sheet(window) is None:
            _WATCHED_WINDOWS.discard(wid)
            _restore_layout(window)
            return
        sublime.set_timeout(_tick, 250)

    sublime.set_timeout(_tick, 250)


def _find_source_view_for_window(window: sublime.Window) -> Optional[sublime.View]:
    active = window.active_view()
    if is_markdown_view(active):
        return active
    src_id = window.settings().get(SOURCE_VIEW_ID_KEY)
    if src_id:
        for v in window.views():
            if v.id() == src_id and is_markdown_view(v):
                return v
    return None


def _refresh_previews_for_view(view: sublime.View) -> None:
    """Read buffer text and update any active HtmlSheet and/or Browser Server."""
    if not view or not view.is_valid():
        return
    window = view.window()
    text = view.substr(sublime.Region(0, view.size()))
    title = get_view_title(view)
    source_path = view.file_name() or ""
    cursor_line = get_cursor_line(view)
    highlight_line = cursor_line if get_setting("highlight_cursor_line", True) else None

    # 1. Update in-editor HtmlSheet if open in this window
    if window:
        sheet = find_preview_sheet(window)
        if sheet:
            mini_html = render_minihtml(
                text,
                source_path=source_path,
                title=title,
                cursor_line=highlight_line,
            )
            window.settings().set(SOURCE_VIEW_ID_KEY, view.id())
            sublime.set_timeout(lambda: _apply_sheet_html(sheet, mini_html), 0)

    # 2. Update localhost SSE browser server if running
    if _SERVER.is_running():
        roots = list(window.folders()) if window else []
        frag = render_browser_fragment(text, source_path=source_path)
        _SERVER.publish(
            html_fragment=frag,
            title=title,
            source_path=source_path,
            cursor_line=cursor_line,
            allowed_roots=roots,
        )


def _apply_sheet_html(sheet: sublime.HtmlSheet, html_content: str) -> None:
    try:
        if sheet and sheet.window():
            sheet.set_contents(html_content)
    except Exception as exc:
        print(f"[RapscallionMarkdown] Failed updating HtmlSheet: {exc}")


def _schedule_debounced_refresh(view: sublime.View) -> None:
    vid = view.id()
    delay_s = float(get_setting("live_preview_debounce_ms", 150)) / 1000.0

    with _DEBOUNCE_LOCK:
        old = _DEBOUNCE_TIMERS.pop(vid, None)
        if old is not None:
            old.cancel()

        def _fire():
            with _DEBOUNCE_LOCK:
                _DEBOUNCE_TIMERS.pop(vid, None)
            sublime.set_timeout_async(lambda: _refresh_previews_for_view(view), 0)

        t = threading.Timer(delay_s, _fire)
        t.daemon = True
        _DEBOUNCE_TIMERS[vid] = t
        t.start()


def _handle_browser_toggle_task(line: int, source_path: str) -> None:
    """Callback invoked from HTTP server thread when browser checkbox is clicked."""
    def _on_ui():
        target_view: Optional[sublime.View] = None
        for win in sublime.windows():
            for v in win.views():
                if source_path and v.file_name() == source_path:
                    target_view = v
                    break
            if target_view:
                break
        if target_view is None:
            win = sublime.active_window()
            if win:
                target_view = _find_source_view_for_window(win)
        if target_view and target_view.is_valid():
            target_view.run_command("rapscallion_markdown_toggle_task", {"line": line})

    sublime.set_timeout(_on_ui, 0)


_SERVER.set_toggle_task_callback(_handle_browser_toggle_task)


# ==============================================================================
# Commands
# ==============================================================================

class RapscallionMarkdownTogglePreviewCommand(sublime_plugin.WindowCommand):
    """Toggle the side-by-side minihtml Markdown preview sheet."""

    def run(self):
        sheet = find_preview_sheet(self.window)
        if sheet:
            sheet.close()
            _restore_layout(self.window)
            return

        view = _find_source_view_for_window(self.window)
        if not view:
            sublime.status_message("RapscallionMarkdown: Open a Markdown file to preview.")
            return

        width = float(get_setting("preview_panel_width", 0.45))
        width = max(0.2, min(0.75, width))
        side = get_setting("preview_panel_side", "right")
        panel_group, editor_group = _get_panel_groups()

        prev_layout = self.window.layout()
        self.window.settings().set(SAVED_LAYOUT_KEY, prev_layout)

        if side == "left":
            layout = {
                "cols": [0.0, width, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
            }
        else:
            layout = {
                "cols": [0.0, 1.0 - width, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
            }

        self.window.set_layout(layout)
        text = view.substr(sublime.Region(0, view.size()))
        highlight_line = get_cursor_line(view) if get_setting("highlight_cursor_line", True) else None
        html_content = render_minihtml(
            text,
            source_path=view.file_name() or "",
            title=get_view_title(view),
            cursor_line=highlight_line,
        )
        new_sheet = self.window.new_html_sheet("Markdown Preview", html_content, group=panel_group)
        self.window.settings().set(PANEL_SHEET_ID_KEY, new_sheet.id())
        self.window.settings().set(SOURCE_VIEW_ID_KEY, view.id())
        _start_panel_watchdog(self.window)
        self.window.focus_group(editor_group)
        self.window.focus_view(view)


class RapscallionMarkdownBrowserPreviewCommand(sublime_plugin.WindowCommand):
    """Start the zero-dep SSE preview server (if needed) and open in browser."""

    def run(self):
        url = _SERVER.start()
        view = _find_source_view_for_window(self.window)
        if view:
            _refresh_previews_for_view(view)
            view.set_status(STATUS_KEY, f"MD Live: {url}")
        webbrowser.open(url)
        sublime.status_message(f"RapscallionMarkdown: Live browser preview at {url}")


class RapscallionMarkdownStopBrowserServerCommand(sublime_plugin.WindowCommand):
    """Stop the background localhost SSE preview server."""

    def run(self):
        if _SERVER.is_running():
            _SERVER.stop()
            for win in sublime.windows():
                for v in win.views():
                    v.erase_status(STATUS_KEY)
            sublime.status_message("RapscallionMarkdown: Browser preview server stopped.")
        else:
            sublime.status_message("RapscallionMarkdown: Browser preview server is not running.")


class RapscallionMarkdownToggleTaskCommand(sublime_plugin.TextCommand):
    """Toggle a Markdown task checkbox (- [ ] <-> - [x]) at the given 1-based line."""

    def run(self, edit, line=0):
        if not line or line < 1:
            return
        pt = self.view.text_point(line - 1, 0)
        line_region = self.view.line(pt)
        line_text = self.view.substr(line_region)
        m = _TASK_LINE_RE.match(line_text)
        if not m:
            return
        new_mark = " " if m.group(2).lower() == "x" else "x"
        replacement = f"{m.group(1)}{new_mark}{m.group(3)}"
        self.view.replace(edit, line_region, replacement)
        _schedule_debounced_refresh(self.view)


class RapscallionMarkdownToggleTaskFromSheetCommand(sublime_plugin.WindowCommand):
    """Dispatch task checkbox toggle from HtmlSheet to the source Markdown view."""

    def run(self, line=0):
        view = _find_source_view_for_window(self.window)
        if view and view.is_valid():
            view.run_command("rapscallion_markdown_toggle_task", {"line": line})


class RapscallionMarkdownJumpLineCommand(sublime_plugin.WindowCommand):
    """Jump the source Markdown view to a specific 1-based line."""

    def run(self, line=1):
        view = _find_source_view_for_window(self.window)
        if not view or not view.is_valid():
            return
        group, _ = self.window.get_view_index(view)
        if group >= 0:
            self.window.focus_group(group)
        self.window.focus_view(view)
        pt = view.text_point(max(0, int(line) - 1), 0)
        view.sel().clear()
        view.sel().add(sublime.Region(pt))
        view.show_at_center(pt)


class RapscallionMarkdownOpenLinkCommand(sublime_plugin.WindowCommand):
    """Open an external URL in browser or a relative Markdown/project file in Sublime."""

    def run(self, href="", source_path=""):
        if not href:
            return
        if href.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(href)
            return

        if href.startswith("#"):
            # Anchor jump handled gracefully if needed later
            return

        base_dir = os.path.dirname(source_path) if source_path else ""
        if not base_dir:
            folders = self.window.folders()
            base_dir = folders[0] if folders else ""

        if base_dir:
            clean_href = href.split("#")[0]
            target = os.path.normpath(os.path.join(base_dir, clean_href))
            if os.path.isfile(target):
                self.window.open_file(target)
                return

        sublime.status_message(f"RapscallionMarkdown: Target not found ({href})")


# ==============================================================================
# Event Listener & Lifecycle
# ==============================================================================

class RapscallionMarkdownListener(sublime_plugin.EventListener):
    """Handles live preview updates and side-panel layout guarding."""

    def on_activated_async(self, view):
        try:
            window = view.window()
            if not window:
                return

            # Panel Guard: collapse layout if preview sheet was closed, or keep views out of panel group
            if window.settings().get(PANEL_SHEET_ID_KEY):
                sheet = find_preview_sheet(window)
                if sheet is None:
                    sublime.set_timeout(lambda: _check_and_restore_layout(window), 0)
                elif window.num_groups() > 1:
                    panel_group, editor_group = _get_panel_groups()
                    view_group, _ = window.get_view_index(view)
                    if view_group == panel_group:
                        def _move_view():
                            if view.is_valid() and window.num_groups() > 1:
                                window.set_view_index(
                                    view,
                                    editor_group,
                                    len(window.views_in_group(editor_group)),
                                )
                                window.focus_group(editor_group)
                                window.focus_view(view)
                        sublime.set_timeout(_move_view, 0)

            if is_markdown_view(view):
                if _SERVER.is_running():
                    url = _SERVER.get_url()
                    if url:
                        sublime.set_timeout(
                            lambda: view.set_status(STATUS_KEY, f"MD Live: {url}") if view.is_valid() else None,
                            0,
                        )
                _refresh_previews_for_view(view)
        except Exception as exc:
            print(f"[RapscallionMarkdown] Error in on_activated_async: {exc}")

    def on_modified_async(self, view):
        try:
            if not is_markdown_view(view):
                return
            window = view.window()
            has_sheet = bool(window and find_preview_sheet(window))
            if has_sheet or _SERVER.is_running():
                _schedule_debounced_refresh(view)
        except Exception as exc:
            print(f"[RapscallionMarkdown] Error in on_modified_async: {exc}")

    def on_selection_modified_async(self, view):
        try:
            if not is_markdown_view(view):
                return
            window = view.window()
            has_sheet = bool(window and find_preview_sheet(window))
            should_sync_browser = _SERVER.is_running() and (
                get_setting("browser_sync_scroll", True) or get_setting("highlight_cursor_line", True)
            )
            should_sync_sheet = has_sheet and get_setting("highlight_cursor_line", True)
            if should_sync_browser or should_sync_sheet:
                _schedule_debounced_refresh(view)
        except Exception as exc:
            print(f"[RapscallionMarkdown] Error in on_selection_modified_async: {exc}")

    def on_window_command(self, window, command_name, args):
        try:
            if command_name in ("close", "close_by_index", "close_sheet", "close_file"):
                if window.settings().get(PANEL_SHEET_ID_KEY):
                    sublime.set_timeout(lambda: _check_and_restore_layout(window), 50)
        except Exception as exc:
            print(f"[RapscallionMarkdown] Error in on_window_command: {exc}")
        return None


def plugin_unloaded():
    """Ensure background HTTP server and debounce timers are cleaned up."""
    with _DEBOUNCE_LOCK:
        for t in _DEBOUNCE_TIMERS.values():
            t.cancel()
        _DEBOUNCE_TIMERS.clear()
    _SERVER.stop()
