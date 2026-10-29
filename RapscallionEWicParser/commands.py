"""Sublime Text 4 Command Implementations for RapscallionEWicParser.

Commands:
- ewic_analyze_transaction_by_id: Audit specific transaction by Invoice # / Sequence # / Auth ID
- ewic_audit_log: Audit all E-WIC transactions in active log buffer
- ewic_parse_selection: Quick-decode cursor line or highlighted TLV string (ctrl+alt+w)
- ewic_load_apl_file: Explicitly browse and cache an APL catalog file
- ewic_clear_apl_cache: Reset window session-cached APL data
"""

import os
import sys
import subprocess
from typing import List, Optional, Tuple, Callable

import sublime
import sublime_plugin

from .apl_parser import (
    APLDatabase,
    get_cached_apl,
    set_cached_apl,
    clear_apl_cache,
    discover_candidate_apls,
)
from .ewic_core import (
    parse_tlv_string,
    LogAuditScanner,
    render_markdown_report,
)
from .usda_fallback import resolve_category, format_balance
from .report_renderer import (
    markdown_to_standalone_html,
    open_in_browser,
)

SETTINGS_FILE = "RapscallionEWicParser.sublime-settings"


def get_plugin_setting(key: str, default=None):
    """Retrieve user setting with fallback."""
    settings = sublime.load_settings(SETTINGS_FILE)
    return settings.get(key, default)


def get_report_destination() -> str:
    """Resolve active destination: 'markdown', 'browser', or 'both'."""
    settings = sublime.load_settings(SETTINGS_FILE)
    dest = settings.get("report_destination", None)
    if dest in ("markdown", "browser", "both"):
        return dest
    # Fallback to legacy boolean if present
    if settings.get("auto_open_in_browser", False):
        return "both"
    # Fallback to deprecated report_view_mode if present
    legacy_mode = settings.get("report_view_mode", None)
    if legacy_mode in ("markdown", "browser", "both"):
        return legacy_mode
    return "markdown"


def browse_for_apl_file() -> Optional[str]:
    """Open a native OS file dialog to select an APL file."""
    # 1. Try tkinter if available
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select WIC APL File",
            filetypes=[("APL Files", "*.apl;*apl*.txt"), ("All Files", "*.*")]
        )
        root.destroy()
        if path and os.path.isfile(path):
            return os.path.normpath(path)
    except Exception:
        pass

    # 2. On Windows, use PowerShell OpenFileDialog
    if sys.platform == "win32":
        try:
            ps_script = (
                "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
                "$d = New-Object System.Windows.Forms.OpenFileDialog; "
                "$d.Title = 'Select WIC APL File'; "
                "$d.Filter = 'APL Files (*.apl;*apl*.txt)|*.apl;*apl*.txt|All Files (*.*)|*.*'; "
                "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.FileName }"
            )
            res = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_script],
                universal_newlines=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ).strip()
            if res and os.path.isfile(res):
                return os.path.normpath(res)
        except Exception:
            pass

    return None


class EwicAnalyzeTransactionByIdCommand(sublime_plugin.TextCommand):
    """Filter and audit a single E-WIC transaction by F1032 / PAYINVOICE number."""

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window:
            return

        # Pre-populate if numbers are highlighted in view
        initial_val = ""
        sels = view.sel()
        if sels and not sels[0].empty():
            selected_text = view.substr(sels[0]).strip()
            if selected_text.isdigit():
                initial_val = selected_text

        def on_invoice_entered(inv_str: str):
            inv_str = inv_str.strip()
            if not inv_str:
                return
            # Normalize invoice ID away from leading zeros
            norm_inv = str(int(inv_str)) if inv_str.isdigit() else inv_str
            self._prompt_apl_and_execute(norm_inv)

        window.show_input_panel("Enter Invoice # / Sequence # / Auth ID:", initial_val, on_invoice_entered, None, None)

    def _prompt_apl_and_execute(self, target_invoice: str):
        prompt_apl_selection(self.view, lambda apl_db: self._execute_audit(target_invoice, apl_db))

    def _execute_audit(self, target_invoice: str, apl_db: Optional[APLDatabase]):
        view = self.view
        window = view.window()
        if not window:
            return

        lines = [view.substr(r) for r in view.lines(sublime.Region(0, view.size()))]
        def_state = get_plugin_setting("default_state", "NZ")
        pfx_map = get_plugin_setting("state_prefix_map", {})
        lookback = get_plugin_setting("correlation_lookback_lines", 1500)
        show_zeros = get_plugin_setting("show_zero_balance_items", True)
        highlight_ded = get_plugin_setting("highlight_deductions_in_markdown", True)

        scanner = LogAuditScanner(lines, default_state=def_state, state_prefix_map=pfx_map, lookback_limit=lookback)
        cycles = scanner.scan(target_invoice=target_invoice)

        if not cycles:
            sublime.error_message(f"E-WIC Transaction matching '{target_invoice}' was not found in the active log buffer.")
            return

        for c in cycles:
            c.reconcile(apl_db, show_zeros=show_zeros)

        apl_name = apl_db.file_name if apl_db else None
        bank_name = scanner.bank_name
        report_md, clip_table = render_markdown_report(
            cycles,
            log_path=view.file_name() or "Active Buffer",
            apl_name=apl_name,
            show_zeros=show_zeros,
            highlight_deductions=highlight_ded,
            bank_name=bank_name
        )

        display_audit_results(window, f"WIC Audit - Inv {target_invoice}", report_md, clip_table)


class EwicAuditLogCommand(sublime_plugin.TextCommand):
    """Audit all E-WIC transactions in the active log buffer."""

    def run(self, edit):
        view = self.view
        prompt_apl_selection(view, lambda apl_db: self._execute_audit(apl_db))

    def _execute_audit(self, apl_db: Optional[APLDatabase]):
        view = self.view
        window = view.window()
        if not window:
            return

        lines = [view.substr(r) for r in view.lines(sublime.Region(0, view.size()))]
        def_state = get_plugin_setting("default_state", "NZ")
        pfx_map = get_plugin_setting("state_prefix_map", {})
        lookback = get_plugin_setting("correlation_lookback_lines", 1500)
        show_zeros = get_plugin_setting("show_zero_balance_items", True)
        highlight_ded = get_plugin_setting("highlight_deductions_in_markdown", True)

        scanner = LogAuditScanner(lines, default_state=def_state, state_prefix_map=pfx_map, lookback_limit=lookback)
        cycles = scanner.scan()

        if not cycles:
            sublime.message_dialog("No E-WIC transactions discovered in the active log buffer.")
            return

        for c in cycles:
            c.reconcile(apl_db, show_zeros=show_zeros)

        apl_name = apl_db.file_name if apl_db else None
        bank_name = scanner.bank_name
        file_name = os.path.basename(view.file_name()) if view.file_name() else "Buffer"
        report_md, clip_table = render_markdown_report(
            cycles,
            log_path=view.file_name() or "Active Buffer",
            apl_name=apl_name,
            show_zeros=show_zeros,
            highlight_deductions=highlight_ded,
            bank_name=bank_name
        )

        display_audit_results(window, f"WIC Audit - All ({file_name})", report_md, clip_table)


class EwicParseSelectionCommand(sublime_plugin.TextCommand):
    """Quick-decode cursor line or highlighted TLV string (ctrl+alt+w / super+alt+w)."""

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window:
            return

        text_to_parse = ""
        sels = view.sel()
        if sels and not sels[0].empty():
            text_to_parse = view.substr(sels[0])
        elif sels:
            text_to_parse = view.substr(view.line(sels[0]))

        if not text_to_parse or "EA" not in text_to_parse:
            sublime.status_message("No EA TLV balance tag found in selection or current line.")
            return

        def_state = get_plugin_setting("default_state", "NZ")
        pfx_map = get_plugin_setting("state_prefix_map", {})
        cached_apl = get_cached_apl(window.id())

        balances, exp_date, state = parse_tlv_string(text_to_parse, default_state=def_state, state_prefix_map=pfx_map)
        if not balances:
            sublime.status_message("Could not extract any EA benefit balance tags.")
            return

        # Build quick breakdown
        lines = []
        lines.append(f"# Quick TLV Benefit Balance Breakdown")
        lines.append("")
        lines.append(f"- **State / Schema**: `{state}`")
        lines.append(f"- **Benefit Expiration**: `{exp_date or 'N/A'}`")
        lines.append(f"- **APL Reference**: `{cached_apl.file_name if cached_apl else 'Standard USDA Fallback'}`")
        lines.append("")
        lines.append("| Cat/Sub | Description | Balance | UOM |")
        lines.append("| :---: | :--- | :---: | :---: |")

        clip_rows = ["| Cat/Sub | Description | Balance | UOM |", "| :---: | :--- | :---: | :---: |"]

        for (cat, subcat) in sorted(balances.keys()):
            amount = balances[(cat, subcat)]
            if cached_apl:
                info = cached_apl.lookup_category(cat, subcat)
            else:
                info = resolve_category(cat, subcat)

            desc = info.get("description", f"Category {cat}")
            uom = info.get("uom", "EA")
            is_curr = info.get("is_currency", False) or uom == "$$$"
            bal_str = format_balance(amount, is_curr, uom)

            row_str = f"| {cat}/{subcat} | {desc} | {bal_str} | {uom} |"
            lines.append(row_str)
            clip_rows.append(row_str)

        full_md = "\n".join(lines)
        clip_table = "\n".join(clip_rows) + "\n"

        display_audit_results(window, "WIC Quick TLV Breakdown", full_md, clip_table)


class EwicClearAplCacheCommand(sublime_plugin.WindowCommand):
    """Reset window session-cached APL data."""

    def run(self):
        clear_apl_cache(self.window.id())
        sublime.status_message("Rapscallion WIC: Active APL cache cleared.")


class EwicLoadAplFileCommand(sublime_plugin.WindowCommand):
    """Explicitly select and load an APL catalog file into the window cache."""

    def run(self):
        view = self.window.active_view()
        if not view:
            return

        def on_loaded(apl_db: Optional[APLDatabase]):
            if apl_db:
                sublime.message_dialog(
                    f"Successfully loaded APL catalog:\n\n"
                    f"File: {apl_db.file_name}\n"
                    f"Items: {len(apl_db.upc_map):,} UPC entries\n"
                    f"Categories: {len(apl_db.cat_map)} categories"
                )

        prompt_apl_selection(view, on_loaded)


def _is_valid_report_view(view: Optional[sublime.View]) -> bool:
    """Determine whether the given view is a valid Markdown file or WIC audit report."""
    if not view:
        return False
    syntax = str(view.settings().get("syntax", "")).lower()
    if "markdown" in syntax:
        return True
    fname = view.file_name()
    if fname and fname.lower().endswith((".md", ".markdown", ".mdown")):
        return True
    vname = view.name()
    if vname and ("WIC Audit" in vname or "WIC Quick" in vname or "TLV Breakdown" in vname):
        return True
    header = view.substr(sublime.Region(0, min(view.size(), 500)))
    if any(k in header for k in (
        "E-WIC Transaction Audit Report",
        "# Quick TLV Benefit Balance Breakdown",
        "## Scanned Basket Items",
        "## Balance Reconciliation Table",
    )):
        return True
    return False


class EwicViewReportInBrowserCommand(sublime_plugin.TextCommand):
    """Render the active Markdown report in the system default web browser."""

    def is_visible(self) -> bool:
        """Only visible in context menus of Markdown files or generated WIC reports."""
        return _is_valid_report_view(self.view)

    def is_enabled(self) -> bool:
        return self.is_visible()

    def run(self, edit):
        view = self.view
        content = view.substr(sublime.Region(0, view.size()))
        if not content.strip():
            sublime.status_message("Buffer is empty.")
            return

        title = view.name() or "WIC Audit Report"
        path = open_in_browser(content, title=title)
        sublime.status_message(f"Opened report in browser: {os.path.basename(path)}")


DESTINATION_OPTIONS = [
    {
        "id": "markdown",
        "title": "Markdown Only (Sublime Tab)",
        "desc": "Open report as a Markdown scratch view in Sublime Text (Default)"
    },
    {
        "id": "browser",
        "title": "Web Browser Only (External HTML)",
        "desc": "Launch the report in your system default web browser (no Sublime tab created)"
    },
    {
        "id": "both",
        "title": "Both (Sublime Tab & Web Browser)",
        "desc": "Open in a Sublime Text Markdown tab AND launch in your default web browser"
    }
]


class EwicSetReportDestinationCommand(sublime_plugin.WindowCommand):
    """Interactive Quick Panel to set report output destination."""

    def run(self):
        current_dest = get_report_destination()
        items = []
        selected_idx = 0
        for idx, opt in enumerate(DESTINATION_OPTIONS):
            is_cur = (opt["id"] == current_dest)
            if is_cur:
                selected_idx = idx
            prefix = "✓ " if is_cur else "   "
            items.append([f"{prefix}{opt['title']}", opt["desc"]])

        def on_select(idx: int):
            if idx < 0:
                return
            chosen = DESTINATION_OPTIONS[idx]["id"]
            settings = sublime.load_settings(SETTINGS_FILE)
            settings.set("report_destination", chosen)
            sublime.save_settings(SETTINGS_FILE)
            sublime.status_message(f"WIC Report Destination set to: {DESTINATION_OPTIONS[idx]['title']}")

        self.window.show_quick_panel(items, on_select, selected_index=selected_idx)


# ==============================================================================
# Helper Dialogs & Presentation Logic
# ==============================================================================

def prompt_apl_selection(view: sublime.View, on_selected: Callable[[Optional[APLDatabase]], None]):
    """Interactive APL file selection panel with local discovery, browsing, and fallback."""
    window = view.window()
    if not window:
        on_selected(None)
        return

    cached_apl = get_cached_apl(window.id())
    active_path = view.file_name()
    project_folders = window.folders()

    candidates = discover_candidate_apls(active_path, project_folders)

    # Build options list
    # Format: [ [Title, Subtitle], action_callback ]
    menu_items: List[Tuple[List[str], Callable[[], None]]] = []

    # 1. Use active APL if cached
    if cached_apl:
        menu_items.append((
            [f"Use Active APL ({cached_apl.file_name})", f"Currently loaded session catalog ({len(cached_apl.upc_map)} items)"],
            lambda: on_selected(cached_apl)
        ))

    # 2. Local candidate files
    for c_path in candidates:
        fname = os.path.basename(c_path)
        menu_items.append((
            [f"Load {fname}", c_path],
            lambda p=c_path: _load_and_proceed(window, p, on_selected)
        ))

    # 3. Browse option
    menu_items.append((
        ["Browse for file...", "Open native OS file browser to locate an APL catalog (*.apl, *.txt)"],
        lambda: _browse_and_proceed(window, on_selected)
    ))

    # 4. USDA fallback option
    menu_items.append((
        ["Proceed without APL (Use Standard USDA Fallback)", "Resolve standard categories (01 Formula, 02 Cheese, 05 Cereal, 19 Produce...)"],
        lambda: on_selected(None)
    ))

    quick_panel_items = [item[0] for item in menu_items]

    def on_done(idx: int):
        if idx == -1:
            return  # Cancelled by user
        callback = menu_items[idx][1]
        callback()

    window.show_quick_panel(quick_panel_items, on_done)


def _load_and_proceed(window: sublime.Window, file_path: str, callback: Callable[[Optional[APLDatabase]], None]):
    """Load an APL file into window cache and proceed with audit."""
    sublime.status_message(f"Loading APL catalog: {os.path.basename(file_path)}...")
    try:
        db = APLDatabase(file_path)
        set_cached_apl(window.id(), db)
        sublime.status_message(f"APL loaded: {len(db.upc_map)} items indexed.")
        callback(db)
    except Exception as e:
        sublime.error_message(f"Failed to parse APL file: {e}")
        callback(None)


def _browse_and_proceed(window: sublime.Window, callback: Callable[[Optional[APLDatabase]], None]):
    """Open file browser and load selected APL."""
    selected_path = browse_for_apl_file()
    if selected_path:
        _load_and_proceed(window, selected_path, callback)
    else:
        # User canceled browse, re-prompt or fallback
        prompt_apl_selection(window.active_view(), callback)


def _create_markdown_view(
    window: sublime.Window,
    tab_title: str,
    markdown_content: str,
    group: int = -1
) -> sublime.View:
    """Helper to create and populate a clean Markdown scratch view tab."""
    report_view = window.new_file()
    report_view.set_scratch(True)
    report_view.set_name(tab_title)
    report_view.assign_syntax("Packages/Markdown/Markdown.sublime-syntax")
    report_view.run_command("append", {"characters": markdown_content})
    if group >= 0 and group < window.num_groups():
        window.set_view_index(report_view, group, 0)
    return report_view


def display_audit_results(
    window: sublime.Window,
    tab_title: str,
    markdown_content: str,
    clipboard_table: str
) -> None:
    """Render markdown report according to report_destination & manage clipboard export."""
    dest = get_report_destination()

    # 1. Create Sublime Text Markdown view if requested
    if dest in ("markdown", "both"):
        _create_markdown_view(window, tab_title, markdown_content)

    # 2. Open in web browser if requested
    if dest in ("browser", "both"):
        try:
            open_in_browser(markdown_content, title=tab_title)
        except Exception as e:
            sublime.error_message(f"Failed to open report in browser: {e}")

    # 3. Clipboard management
    auto_copy = get_plugin_setting("auto_copy_to_clipboard", True)
    if auto_copy and clipboard_table:
        sublime.set_clipboard(clipboard_table)

    # 4. Status bar feedback
    if dest == "browser":
        status_msg = "WIC audit report opened in browser"
    elif dest == "both":
        status_msg = "WIC audit report opened in editor and browser"
    else:
        status_msg = "WIC audit report generated in editor"

    if auto_copy and clipboard_table:
        status_msg += " (balance table copied to clipboard)"
    sublime.status_message(status_msg)

