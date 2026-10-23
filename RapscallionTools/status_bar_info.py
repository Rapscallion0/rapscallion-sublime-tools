import sublime
import sublime_plugin
import os
import stat
import datetime

SETTINGS_FILE = "RapscallionTools.sublime-settings"

def get_setting(key, default=None):
    return sublime.load_settings(SETTINGS_FILE).get(key, default)

def is_item_enabled(item_name):
    items = get_setting("status_bar_items", {})
    return items.get(item_name, False)

def plugin_loaded():
    s = sublime.load_settings(SETTINGS_FILE)
    s.clear_on_change("rapscallion_status_bar_reload")
    s.add_on_change("rapscallion_status_bar_reload", on_settings_changed)

def on_settings_changed():
    enabled = get_setting("show_status_bar_info", True)
    for window in sublime.windows():
        for view in window.views():
            if enabled:
                StatusBarInfoListener().update_status(view)
            else:
                view.erase_status("sb_info")

def collect_file_metrics(view):
    data = []
    file_path = view.file_name()
    stats = None
    if file_path and os.path.exists(file_path):
        try:
            stats = os.stat(file_path)
        except OSError:
            stats = None

    # Read-only
    if is_item_enabled("read_only"):
        is_ro = view.is_read_only() or (stats and not os.access(file_path, os.W_OK))
        if is_ro:
            data.append({"key": "Status", "label": "Status", "val": "[RO]", "desc": "File is Read-Only on disk or locked in editor"})

    # Encoding
    if is_item_enabled("encoding"):
        enc = view.encoding()
        if enc == "Undefined":
            enc = view.settings().get("default_encoding", "UTF-8")
        data.append({"key": "Enc", "label": "Encoding", "val": enc, "desc": "Character encoding used to read/save the buffer"})

    # Line endings
    if is_item_enabled("line_endings"):
        eol = view.line_endings().upper()
        desc = "Windows (CRLF)" if eol == "CRLF" else ("Unix (LF)" if eol == "LF" else "Classic Mac (CR)")
        data.append({"key": "EOL", "label": "Line Endings", "val": eol, "desc": desc})

    # Total lines
    if is_item_enabled("total_lines"):
        total_lines = f"{view.rowcol(view.size())[0] + 1:,}L"
        data.append({"key": "Lines", "label": "Total Lines", "val": total_lines, "desc": "Total number of lines in this file"})

    # File size
    if is_item_enabled("size") and stats:
        sz = stats.st_size
        size_str = f"{sz} B" if sz < 1024 else (f"{sz/1024:.1f} KB" if sz < 1048576 else f"{sz/1048576:.2f} MB")
        data.append({"key": "Size", "label": "File Size", "val": size_str, "desc": f"Physical size on disk ({sz:,} bytes)"})

    # Permissions
    if is_item_enabled("permissions") and stats:
        perms = stat.filemode(stats.st_mode)
        data.append({"key": "Perms", "label": "Permissions", "val": perms, "desc": "POSIX file permissions (Owner/Group/Others)"})

    # Date modified
    if is_item_enabled("modified") and stats:
        fmt = get_setting("status_bar_date_format", "%Y-%m-%d %H:%M")
        mod_time = datetime.datetime.fromtimestamp(stats.st_mtime).strftime(fmt)
        data.append({"key": "Mod", "label": "Modified", "val": mod_time, "desc": "Last modified timestamp on disk"})

    return data

class RapscallionShowStatusDetailsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        metrics = collect_file_metrics(self.view)
        if not metrics:
            sublime.status_message("No status bar metrics available.")
            return

        rows = "".join(
            f"<tr><td style='padding: 2px 10px; font-weight: bold; color: var(--yellowish);'>{m['label']}</td>"
            f"<td style='padding: 2px 10px; font-family: monospace; color: var(--foreground);'>{m['val']}</td>"
            f"<td style='padding: 2px 10px; color: var(--bluish); font-size: 0.9em;'>{m['desc']}</td></tr>"
            for m in metrics
        )

        html = f"""
        <body id="rapscallion-status-popup" style="padding: 8px; margin: 0; font-family: sans-serif;">
            <div style="font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid color(var(--foreground) alpha(0.2)); padding-bottom: 4px;">
                File Status Details
            </div>
            <table style="border-collapse: collapse;">
                {rows}
            </table>
        </body>
        """
        self.view.show_popup(html, max_width=650, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY)

class RapscallionToggleStatusBarCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        s = sublime.load_settings(SETTINGS_FILE)
        new_val = not s.get("show_status_bar_info", True)
        s.set("show_status_bar_info", new_val)
        sublime.save_settings(SETTINGS_FILE)

        for window in sublime.windows():
            for view in window.views():
                if new_val:
                    StatusBarInfoListener().update_status(view)
                else:
                    view.erase_status("sb_info")

        state = "Enabled" if new_val else "Disabled"
        sublime.status_message(f"RapscallionTools: Status Bar Info {state}")

    def is_checked(self):
        return get_setting("show_status_bar_info", True)

class StatusBarInfoListener(sublime_plugin.EventListener):
    def on_activated_async(self, view):
        try:
            self.update_status(view)
        except Exception as e:
            print(f"[RapscallionTools] Error in status bar on_activated_async: {e}")

    def on_post_save_async(self, view):
        try:
            self.update_status(view)
        except Exception as e:
            print(f"[RapscallionTools] Error in status bar on_post_save_async: {e}")

    def update_status(self, view):
        try:
            if not get_setting("show_status_bar_info", True):
                view.erase_status("sb_info")
                return

            use_labels = get_setting("status_bar_use_labels", True)
            metrics = collect_file_metrics(view)

            parts = []
            for m in metrics:
                if use_labels and m["key"] != "Status":
                    parts.append(f"{m['key']}: {m['val']}")
                else:
                    parts.append(m["val"])

            if parts:
                view.set_status("sb_info", " | ".join(parts))
            else:
                view.erase_status("sb_info")
        except Exception as e:
            print(f"[RapscallionTools] Error updating status bar: {e}")