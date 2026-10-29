import sublime
import sublime_plugin
import os
import json
import html
import re

CONFIG_DIR = ".sublime"
CONFIG_FILE = "RapscallionBooks.json"
GLOBAL_CONFIG_FILE = "RapscallionBookmarks.global.json"
SETTINGS_FILE = "RapscallionBookmarks.sublime-settings"
REGION_KEY_PREFIX = "rapscallion_bookmarks"
PANEL_ID_KEY = "rapscallion_bookmarks_sheet"
OUTPUT_PANEL_NAME = "rapscallion_bookmarks"

PENDING_HIGHLIGHTS = {}
COLLAPSED_FILES_BY_WINDOW = {}


# ==============================================================================
# Helper & Path Functions
# ==============================================================================

def get_setting(key, default=None):
    s = sublime.load_settings(SETTINGS_FILE)
    return s.get(key, default)


def get_collapsed_files(window):
    if not window or not window.is_valid():
        return set()
    wid = window.id()
    if wid not in COLLAPSED_FILES_BY_WINDOW:
        COLLAPSED_FILES_BY_WINDOW[wid] = set()
    return COLLAPSED_FILES_BY_WINDOW[wid]


def get_project_root(window):
    if not window or not window.is_valid():
        return None
    folders = window.folders()
    return folders[0] if folders else None


def safe_relpath(file_path, root):
    if not file_path:
        return ""
    if not root:
        return os.path.normpath(file_path)
    try:
        return os.path.relpath(file_path, root)
    except ValueError:
        return os.path.normpath(file_path)


def resolve_target_path(stored_path, root):
    if not stored_path:
        return ""
    if os.path.isabs(stored_path) or not root:
        return os.path.normpath(stored_path)
    return os.path.normpath(os.path.join(root, stored_path))


def get_storage_path(window):
    root = get_project_root(window)
    if root:
        sublime_dir = os.path.join(root, CONFIG_DIR)
        if not os.path.exists(sublime_dir):
            try:
                os.makedirs(sublime_dir, exist_ok=True)
            except Exception:
                pass
        return os.path.join(sublime_dir, CONFIG_FILE)
    # Global fallback for standalone files outside project folders
    user_dir = os.path.join(sublime.packages_path(), "User")
    if not os.path.exists(user_dir):
        os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, GLOBAL_CONFIG_FILE)


def get_category_config():
    categories = get_setting("categories", {})
    if not isinstance(categories, dict):
        categories = {}
    return categories


def get_category_info(category_key):
    categories = get_category_config()
    default_scope = get_setting("default_category_scope", "region.yellowish")
    default_icon = get_setting("default_category_icon", "bookmark")

    if category_key and category_key in categories:
        info = categories[category_key]
        scope = info.get("scope", default_scope)
        icon = info.get("icon", default_icon)
        label = info.get("label", category_key)
        return scope, icon, label
    elif category_key:
        return default_scope, default_icon, category_key
    return default_scope, default_icon, ""


def get_panel_group():
    side = get_setting("side", "right").lower()
    return 0 if side == "left" else 1


def get_editor_group():
    side = get_setting("side", "right").lower()
    return 1 if side == "left" else 0


def select_all_in_input(input_view):
    if input_view and input_view.is_valid():
        input_view.run_command("select_all")


def schedule_select_all(input_view):
    if not input_view:
        return
    select_all_in_input(input_view)
    sublime.set_timeout(lambda: select_all_in_input(input_view), 30)
    sublime.set_timeout(lambda: select_all_in_input(input_view), 100)


def find_bookmark_sheet(window):
    target_id = window.settings().get(PANEL_ID_KEY)
    if not target_id:
        return None
    for s in window.sheets():
        if s.id() == target_id:
            return s
    return None


def get_panel_ratio(window):
    side = get_setting("side", "right").lower()
    layout = window.layout()
    cols = layout.get("cols", [0.0, 1.0])
    if len(cols) == 3:
        return (cols[1] - cols[0]) if side == "left" else (cols[2] - cols[1])
    return float(get_setting("panel_width", 0.22))


def save_current_panel_width(window):
    if not get_setting("remember_panel_width", True):
        return

    layout = window.layout()
    cols = layout.get("cols", [0.0, 1.0])
    if len(cols) != 3:
        return

    side = get_setting("side", "right").lower()
    ratio = (cols[1] - cols[0]) if side == "left" else (cols[2] - cols[1])
    if 0.08 <= ratio <= 0.80:
        s = sublime.load_settings(SETTINGS_FILE)
        s.set("panel_width", round(ratio, 4))
        sublime.save_settings(SETTINGS_FILE)


def get_dynamic_max_chars(window):
    side = get_setting("side", "right").lower()
    layout = window.layout()
    cols = layout.get("cols", [0.0, 1.0])

    if len(cols) == 3:
        panel_ratio = (cols[1] - cols[0]) if side == "left" else (cols[2] - cols[1])
        editor_ratio = (cols[2] - cols[1]) if side == "left" else (cols[1] - cols[0])
    else:
        panel_ratio = float(get_setting("panel_width", 0.22))
        editor_ratio = 1.0 - panel_ratio

    editor_views = window.views_in_group(get_editor_group())
    view_candidate = editor_views[0] if editor_views else window.active_view()

    total_window_px = 1400.0
    if view_candidate and hasattr(view_candidate, "viewport_extent"):
        extent = view_candidate.viewport_extent()[0]
        if extent > 150 and editor_ratio > 0.05:
            total_window_px = extent / editor_ratio

    panel_px = max(total_window_px * panel_ratio, 80.0)
    usable_px = max(panel_px - 96.0, 30.0)
    return max(int(usable_px / 6.2), 8)


# ==============================================================================
# Flash Highlighting & Centering Engine
# ==============================================================================

def flash_and_center_bookmark(view, line, col=1, length=0):
    if not view or not view.is_valid():
        return

    pt_start = view.text_point(line - 1, col - 1)
    pt_end = pt_start + length if length > 0 else pt_start

    view.sel().clear()
    view.sel().add(sublime.Region(pt_start, pt_end))
    view.show_at_center(pt_start)

    if get_setting("flash_jump", True):
        flash_scope = get_setting("flash_scope", "region.yellowish")
        flash_duration = int(get_setting("flash_duration_ms", 700))
        flash_key = "rapscallion_flash_jump"
        line_reg = view.line(pt_start)

        view.add_regions(
            flash_key,
            [line_reg],
            flash_scope,
            flags=sublime.DRAW_NO_OUTLINE
        )
        sublime.set_timeout(
            lambda: view.is_valid() and view.erase_regions(flash_key),
            flash_duration
        )


# ==============================================================================
# Storage Management
# ==============================================================================

class BookmarkStorage:
    @staticmethod
    def load(window):
        path = get_storage_path(window)
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            sublime.status_message(f"RapscallionBookmarks: Error loading ({e})")
            return {}

    @staticmethod
    def save(window, data):
        path = get_storage_path(window)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            sublime.status_message(f"RapscallionBookmarks: Error saving ({e})")


def refresh_all_bookmark_views(window):
    """Refreshes all visible UI elements: decorations, output panel, and side sheet."""
    if not window or not window.is_valid():
        return

    # 1. Update side sheet if open
    sheet = find_bookmark_sheet(window)
    if sheet:
        sheet.set_contents(build_panel_html(window))

    # 2. Update bottom output panel if currently active
    if window.active_panel() == f"output.{OUTPUT_PANEL_NAME}":
        render_output_panel(window)

    # 3. Refresh in-editor gutter decorations
    for v in window.views():
        v.run_command("rapscallion_refresh_decorations")


# ==============================================================================
# Feature 1: Floating Quick Panel with Smooth Live Preview (Alt + B)
# ==============================================================================

class RapscallionQuickBookmarksCommand(sublime_plugin.WindowCommand):
    """Opens a fuzzy-searchable Quick Panel with smooth scrolling preview."""

    def run(self):
        window = self.window
        data = BookmarkStorage.load(window)
        if not data:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks found.")
            return

        items = []
        entries = []  # (stored_file, line, col, length, category)

        root = get_project_root(window)
        initial_view = window.active_view()
        initial_file = safe_relpath(initial_view.file_name(), root) if initial_view and initial_view.file_name() else None
        current_cursor_line = (initial_view.rowcol(initial_view.sel()[0].begin())[0] + 1) if initial_view and initial_view.sel() else 1

        closest_idx = 0
        min_distance = float("inf")

        for stored_file in sorted(data.keys()):
            full_path = resolve_target_path(stored_file, root)
            is_missing = not os.path.exists(full_path)

            file_bookmarks = sorted(data[stored_file], key=lambda x: (x.get("line", 0), x.get("col", 0)))
            for b in file_bookmarks:
                b_name = b.get("name", "Bookmark")
                b_line = b.get("line", 1)
                b_col = b.get("col", 1)
                b_len = b.get("len", 0)
                b_cat = b.get("category", "")
                b_prev = b.get("preview", "").strip()

                tag_badge = f"[{b_cat}] " if b_cat else ""
                trigger = f"{tag_badge}{b_name}"
                display_details = b_prev if b_prev else f"Line {b_line}"
                if is_missing:
                    display_annotation = f"[MISSING] {stored_file}:{b_line}"
                else:
                    display_annotation = f"{stored_file}:{b_line}"

                item = sublime.QuickPanelItem(
                    trigger=trigger,
                    details=display_details,
                    annotation=display_annotation,
                    kind=(sublime.KIND_ID_MARKUP, "B", "Bookmark")
                )
                items.append(item)
                entries.append((stored_file, b_line, b_col, b_len, b_cat))

                # Track closest bookmark in current file
                if initial_file and stored_file == initial_file:
                    dist = abs(b_line - current_cursor_line)
                    if dist < min_distance:
                        min_distance = dist
                        closest_idx = len(entries) - 1

        if not items:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks found.")
            return

        initial_sel = [s for s in initial_view.sel()] if initial_view else []
        initial_viewport = initial_view.viewport_position() if initial_view else None
        live_preview = get_setting("quick_panel_preview", True)
        preview_on_open = get_setting("quick_panel_preview_on_open", False)

        is_initial_call = [True]

        def on_highlight(idx):
            if not live_preview or idx < 0 or idx >= len(entries):
                return

            # Suppress jarring auto-preview on initial panel open
            if is_initial_call[0]:
                is_initial_call[0] = False
                if not preview_on_open:
                    return

            s_file, line, col, length, _ = entries[idx]
            target_path = resolve_target_path(s_file, root)
            if not os.path.exists(target_path):
                return

            target_view = window.open_file(
                f"{target_path}:{line}:{col}",
                sublime.TRANSIENT | sublime.ENCODED_POSITION
            )
            if target_view and not target_view.is_loading():
                pt = target_view.text_point(line - 1, col - 1)
                target_view.show_at_center(pt)

        def on_select(idx):
            if idx == -1:
                # Cancelled (Esc): restore initial view and position
                if initial_view and initial_view.is_valid():
                    window.focus_view(initial_view)
                    initial_view.sel().clear()
                    for r in initial_sel:
                        initial_view.sel().add(r)
                    if initial_viewport:
                        initial_view.set_viewport_position(initial_viewport)
                return

            s_file, line, col, length, _ = entries[idx]
            window.run_command("rapscallion_jump_bookmark", {
                "stored_file": s_file,
                "line": line,
                "col": col,
                "length": length
            })

        window.show_quick_panel(
            items,
            on_select,
            flags=sublime.MONOSPACE_FONT,
            selected_index=closest_idx,
            on_highlight=on_highlight
        )


# ==============================================================================
# Feature 2: Dedicated Bottom Dock Output Panel (Alt + Shift + B)
# ==============================================================================

def render_output_panel(window):
    """Builds and writes the structured bookmark content into the output panel."""
    panel = window.create_output_panel(OUTPUT_PANEL_NAME)
    root = get_project_root(window)
    data = BookmarkStorage.load(window)

    all_files = sorted(data.keys())
    total_bookmarks = sum(len(b_list) for b_list in data.values())

    lines = [
        "=" * 80,
        f"RAPSCALLION BOOKMARKS ({total_bookmarks} bookmark{'s' if total_bookmarks != 1 else ''} across {len(all_files)} file{'s' if len(all_files) != 1 else ''})",
        "[Enter] Jump  |  [r] Rename  |  [t] Tag  |  [Del] Delete  |  [F5] Refresh  |  [Esc] Close",
        "=" * 80,
        ""
    ]

    if not all_files:
        lines.append("  No bookmarks found. Use Ctrl+F2 to toggle a bookmark at cursor.")
    else:
        for stored_file in all_files:
            target_path = resolve_target_path(stored_file, root)
            is_missing = not os.path.exists(target_path)
            file_header = f"{stored_file}:" if not is_missing else f"{stored_file}:  [MISSING]"

            lines.append(file_header)
            file_bookmarks = sorted(data[stored_file], key=lambda x: (x.get("line", 0), x.get("col", 0)))
            for b in file_bookmarks:
                b_name = b.get("name", "Bookmark")
                b_line = b.get("line", 1)
                b_col = b.get("col", 1)
                b_cat = b.get("category", "")
                b_prev = b.get("preview", "").strip()

                loc_tag = f"{b_line}:{b_col}"
                cat_badge = f"[{b_cat}] " if b_cat else ""
                lines.append(f"  {loc_tag:<10}  {cat_badge}{b_name}")
                if b_prev:
                    clean_prev = b_prev[:120] + ("..." if len(b_prev) > 120 else "")
                    lines.append(f"        {clean_prev}")
            lines.append("")

    panel_text = "\n".join(lines)

    panel.set_read_only(False)
    panel.run_command("select_all")
    panel.run_command("left_delete")
    panel.run_command("append", {"characters": panel_text, "force": True, "scroll_to_end": False})
    panel.set_read_only(True)

    panel.settings().set("word_wrap", False)
    panel.settings().set("gutter", False)
    panel.settings().set("line_numbers", False)
    panel.settings().set("scroll_past_end", False)
    panel.settings().set("rapscallion_bookmarks_panel", True)

    panel.settings().set("result_file_regex", r"^([^\s\t].*?)(?:\s+\[MISSING\])?:$")
    panel.settings().set("result_line_regex", r"^\s+(\d+):?(\d+)?")
    if root:
        panel.settings().set("result_base_dir", root)

    panel.assign_syntax("Packages/RapscallionBookmarks/RapscallionBookmarksPanel.sublime-syntax")
    return panel


class RapscallionTogglePanelCommand(sublime_plugin.WindowCommand):
    """Toggles the bookmarks panel according to configured panel_mode ('bottom_panel' or 'side_dock')."""

    def run(self):
        window = self.window
        mode = get_setting("panel_mode", "bottom_panel").lower()

        if mode == "side_dock":
            window.run_command("rapscallion_toggle_side_panel")
            return

        active = window.active_panel()
        if active == f"output.{OUTPUT_PANEL_NAME}":
            window.run_command("hide_panel")
        else:
            render_output_panel(window)
            window.run_command("show_panel", {"panel": f"output.{OUTPUT_PANEL_NAME}"})


class RapscallionRefreshPanelCommand(sublime_plugin.WindowCommand):
    """Refreshes the bottom dock bookmarks panel content."""

    def run(self):
        window = self.window
        render_output_panel(window)
        sublime.status_message("Rapscallion Bookmarks: Panel refreshed.")


# ==============================================================================
# Panel Interaction Commands (Jump, Rename, Tag, Delete under cursor)
# ==============================================================================

def get_bookmark_from_panel_cursor(view):
    """Parses (stored_file, line_num, col_num, bookmark_dict) at current panel cursor."""
    if not view.settings().get("rapscallion_bookmarks_panel"):
        return None

    sel = view.sel()
    if not sel:
        return None

    cursor_pt = sel[0].begin()
    cursor_line_region = view.line(cursor_pt)
    cursor_line = view.substr(cursor_line_region)

    target_line = cursor_line
    line_pt = cursor_pt

    # If cursor is on preview row (indented with 8 spaces), look at row directly above
    if target_line.startswith("        "):
        prev_row = view.rowcol(cursor_pt)[0] - 1
        if prev_row >= 0:
            line_pt = view.text_point(prev_row, 0)
            target_line = view.substr(view.line(line_pt))

    # Match bookmark row: "  11819:308   [bug] JavaScript ERROR"
    m_row = re.match(r"^\s{2,4}(\d+)(?::(\d+))?\s{2,}(?:\[([a-zA-Z0-9_\-]+)\]\s+)?(.*?)$", target_line)
    if not m_row:
        return None

    b_line = int(m_row.group(1))
    b_col = int(m_row.group(2)) if m_row.group(2) else 1

    # Search backwards for file header: "path/to/file.ext:"
    cur_row = view.rowcol(line_pt)[0]
    stored_file = None
    for r in range(cur_row, -1, -1):
        test_line = view.substr(view.line(view.text_point(r, 0))).strip()
        m_file = re.match(r"^([^\s\t].*?)(?:\s+\[MISSING\])?:$", test_line)
        if m_file:
            stored_file = m_file.group(1)
            break

    if not stored_file:
        return None

    window = view.window()
    data = BookmarkStorage.load(window)
    if stored_file in data:
        for b in data[stored_file]:
            if b.get("line") == b_line and b.get("col", 1) == b_col:
                return stored_file, b_line, b_col, b

    return stored_file, b_line, b_col, None


class RapscallionPanelJumpCommand(sublime_plugin.TextCommand):
    """Jumps to the bookmark currently under cursor in the output panel."""

    def run(self, edit):
        result = get_bookmark_from_panel_cursor(self.view)
        if not result:
            return

        stored_file, b_line, b_col, b_dict = result
        window = self.view.window()
        if not window:
            return

        b_len = b_dict.get("len", 0) if b_dict else 0
        window.run_command("rapscallion_jump_bookmark", {
            "stored_file": stored_file,
            "line": b_line,
            "col": b_col,
            "length": b_len
        })


class RapscallionPanelRenameCommand(sublime_plugin.TextCommand):
    """Renames the bookmark currently under cursor in the output panel."""

    def run(self, edit):
        result = get_bookmark_from_panel_cursor(self.view)
        if not result:
            return

        stored_file, b_line, b_col, b_dict = result
        current_name = b_dict.get("name", "") if b_dict else ""
        window = self.view.window()
        if not window:
            return

        def on_done(new_name):
            new_name = new_name.strip()
            if not new_name or new_name == current_name:
                return

            data = BookmarkStorage.load(window)
            if stored_file in data:
                for b in data[stored_file]:
                    if b.get("line") == b_line and b.get("col", 1) == b_col:
                        b["name"] = new_name
                        break
                BookmarkStorage.save(window, data)
                refresh_all_bookmark_views(window)
                sublime.status_message(f"Bookmark renamed to '{new_name}'.")

        input_view = window.show_input_panel("Rename Bookmark:", current_name, on_done, None, None)
        schedule_select_all(input_view)


class RapscallionPanelSetTagCommand(sublime_plugin.TextCommand):
    """Sets or edits the category/tag for the bookmark currently under cursor in the output panel."""

    def run(self, edit):
        result = get_bookmark_from_panel_cursor(self.view)
        if not result:
            return

        stored_file, b_line, b_col, b_dict = result
        current_cat = b_dict.get("category", "") if b_dict else ""
        window = self.view.window()
        if not window:
            return

        categories = get_category_config()
        cat_keys = sorted(list(categories.keys()))
        options = ["(No Category / Clear Tag)"] + [f"{k} — {categories[k].get('label', k)}" for k in cat_keys] + ["[Custom Tag...]"]

        def on_select(idx):
            if idx == -1:
                return

            if idx == 0:
                # Clear tag
                _apply_tag("")
            elif idx == len(options) - 1:
                # Prompt for custom freeform tag
                window.show_input_panel("Custom Tag / Category:", current_cat, _apply_tag, None, None)
            else:
                chosen_key = cat_keys[idx - 1]
                _apply_tag(chosen_key)

        def _apply_tag(new_tag):
            new_tag = new_tag.strip().lstrip("#")
            data = BookmarkStorage.load(window)
            if stored_file in data:
                for b in data[stored_file]:
                    if b.get("line") == b_line and b.get("col", 1) == b_col:
                        b["category"] = new_tag
                        break
                BookmarkStorage.save(window, data)
                refresh_all_bookmark_views(window)
                sublime.status_message(f"Tag set to '{new_tag}'." if new_tag else "Tag cleared.")

        window.show_quick_panel(options, on_select)


class RapscallionPanelDeleteCommand(sublime_plugin.TextCommand):
    """Deletes the bookmark currently under cursor in the output panel."""

    def run(self, edit):
        result = get_bookmark_from_panel_cursor(self.view)
        if not result:
            return

        stored_file, b_line, b_col, b_dict = result
        b_name = b_dict.get("name", f"Line {b_line}") if b_dict else f"Line {b_line}"
        window = self.view.window()
        if not window:
            return

        if sublime.ok_cancel_dialog(f"Delete bookmark '{b_name}'?", "Delete"):
            data = BookmarkStorage.load(window)
            if stored_file in data:
                data[stored_file] = [b for b in data[stored_file] if not (b.get("line") == b_line and b.get("col", 1) == b_col)]
                if not data[stored_file]:
                    del data[stored_file]
                BookmarkStorage.save(window, data)
                refresh_all_bookmark_views(window)
                sublime.status_message(f"Bookmark '{b_name}' deleted.")


# ==============================================================================
# In-Editor Commands (Toggle, Prompt Named, Cycling, Jump, Decorations)
# ==============================================================================

class RapscallionToggleBookmarkCommand(sublime_plugin.TextCommand):
    """Instantly toggles a bookmark at the cursor without prompting."""

    def is_enabled(self):
        return not self.view.settings().get("is_rapscallion_zip_view", False)

    def is_visible(self):
        return not self.view.settings().get("is_rapscallion_zip_view", False)

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window or not view.file_name():
            sublime.status_message("Rapscallion Bookmarks: Save file before bookmarking.")
            return

        file_path = view.file_name()
        if file_path.lower().endswith((".zip", ".jar", ".war", ".nupkg")):
            sublime.status_message("Rapscallion Bookmarks: Cannot bookmark inside zip archives.")
            return

        root = get_project_root(window)
        stored_path = safe_relpath(file_path, root)

        sel = view.sel()[0]
        line_region = view.line(sel)
        row, col = view.rowcol(sel.begin())
        line_num = row + 1
        col_num = col + 1
        sel_length = len(sel)
        line_text = view.substr(line_region).strip()

        data = BookmarkStorage.load(window)
        existing = None
        if stored_path in data:
            for b in data[stored_path]:
                if b.get("line") == line_num:
                    existing = b
                    break

        if existing:
            # Remove existing bookmark on line
            data[stored_path] = [b for b in data[stored_path] if b.get("line") != line_num]
            if not data[stored_path]:
                del data[stored_path]
            BookmarkStorage.save(window, data)
            sublime.status_message(f"Bookmark removed from line {line_num}.")
            refresh_all_bookmark_views(window)
        else:
            # Create new bookmark
            suggested = view.substr(sel).strip() if not sel.empty() else (line_text[:40] or f"Line {line_num}")
            if stored_path not in data:
                data[stored_path] = []

            data[stored_path].append({
                "name": suggested,
                "line": line_num,
                "col": col_num,
                "len": sel_length,
                "preview": line_text,
                "category": ""
            })
            BookmarkStorage.save(window, data)
            sublime.status_message(f"Bookmark '{suggested}' added.")
            refresh_all_bookmark_views(window)
            flash_and_center_bookmark(view, line_num, col_num, sel_length)


class RapscallionSetNamedBookmarkCommand(sublime_plugin.TextCommand):
    """Prompts for a custom bookmark name and optional category."""

    def is_enabled(self):
        return not self.view.settings().get("is_rapscallion_zip_view", False)

    def is_visible(self):
        return not self.view.settings().get("is_rapscallion_zip_view", False)

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window or not view.file_name():
            sublime.status_message("Rapscallion Bookmarks: Save file before bookmarking.")
            return

        file_path = view.file_name()
        if file_path.lower().endswith((".zip", ".jar", ".war", ".nupkg")):
            sublime.status_message("Rapscallion Bookmarks: Cannot bookmark inside zip archives.")
            return

        root = get_project_root(window)
        stored_path = safe_relpath(file_path, root)

        sel = view.sel()[0]
        line_region = view.line(sel)
        row, col = view.rowcol(sel.begin())
        line_num = row + 1
        col_num = col + 1
        sel_length = len(sel)
        line_text = view.substr(line_region).strip()

        # Check existing
        data = BookmarkStorage.load(window)
        existing_name = ""
        existing_cat = ""
        if stored_path in data:
            for b in data[stored_path]:
                if b.get("line") == line_num:
                    existing_name = b.get("name", "")
                    existing_cat = b.get("category", "")
                    break

        suggested = existing_name or (view.substr(sel).strip() if not sel.empty() else (line_text[:40] or f"Line {line_num}"))

        def on_done(name):
            final_name = name.strip() or suggested
            # Check for inline category prefix like "[bug] Fix it" or "#bug Fix it"
            detected_cat = existing_cat
            m_bracket = re.match(r"^\[([a-zA-Z0-9_\-]+)\]\s*(.*)$", final_name)
            m_hash = re.match(r"^#([a-zA-Z0-9_\-]+)\s+(.*)$", final_name)

            if m_bracket:
                detected_cat = m_bracket.group(1)
                final_name = m_bracket.group(2) or final_name
            elif m_hash:
                detected_cat = m_hash.group(1)
                final_name = m_hash.group(2) or final_name

            if stored_path not in data:
                data[stored_path] = []

            data[stored_path] = [b for b in data[stored_path] if b.get("line") != line_num]
            data[stored_path].append({
                "name": final_name,
                "line": line_num,
                "col": col_num,
                "len": sel_length,
                "preview": line_text,
                "category": detected_cat
            })
            BookmarkStorage.save(window, data)
            sublime.status_message(f"Bookmark '{final_name}' saved.")
            refresh_all_bookmark_views(window)
            flash_and_center_bookmark(view, line_num, col_num, sel_length)

        input_view = window.show_input_panel("Bookmark Name (use #tag or [tag] to categorize):", suggested, on_done, None, None)
        schedule_select_all(input_view)


class RapscallionSetBookmarkCommand(RapscallionSetNamedBookmarkCommand):
    """Backwards compatibility alias for rapscallion_set_named_bookmark."""
    pass


class RapscallionNextBookmarkCommand(sublime_plugin.TextCommand):
    """Jumps to the next bookmark in the active file (wrapping around)."""

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window or not view.file_name():
            return

        root = get_project_root(window)
        stored_path = safe_relpath(view.file_name(), root)
        data = BookmarkStorage.load(window)

        if stored_path not in data or not data[stored_path]:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks in this file.")
            return

        bookmarks = sorted(data[stored_path], key=lambda x: (x.get("line", 1), x.get("col", 1)))
        curr_line = view.rowcol(view.sel()[0].begin())[0] + 1

        next_b = next((b for b in bookmarks if b.get("line", 1) > curr_line), None)
        if not next_b:
            next_b = bookmarks[0]  # Wrap around

        line = next_b.get("line", 1)
        col = next_b.get("col", 1)
        length = next_b.get("len", 0)
        flash_and_center_bookmark(view, line, col, length)
        sublime.status_message(f"Bookmark: {next_b.get('name', 'Bookmark')} (Line {line})")


class RapscallionPrevBookmarkCommand(sublime_plugin.TextCommand):
    """Jumps to the previous bookmark in the active file (wrapping around)."""

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window or not view.file_name():
            return

        root = get_project_root(window)
        stored_path = safe_relpath(view.file_name(), root)
        data = BookmarkStorage.load(window)

        if stored_path not in data or not data[stored_path]:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks in this file.")
            return

        bookmarks = sorted(data[stored_path], key=lambda x: (x.get("line", 1), x.get("col", 1)))
        curr_line = view.rowcol(view.sel()[0].begin())[0] + 1

        prev_b = next((b for b in reversed(bookmarks) if b.get("line", 1) < curr_line), None)
        if not prev_b:
            prev_b = bookmarks[-1]  # Wrap around

        line = prev_b.get("line", 1)
        col = prev_b.get("col", 1)
        length = prev_b.get("len", 0)
        flash_and_center_bookmark(view, line, col, length)
        sublime.status_message(f"Bookmark: {prev_b.get('name', 'Bookmark')} (Line {line})")


class RapscallionNextProjectBookmarkCommand(sublime_plugin.WindowCommand):
    """Steps to the next bookmark across all project files."""

    def run(self):
        window = self.window
        data = BookmarkStorage.load(window)
        if not data:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks found.")
            return

        root = get_project_root(window)
        all_bookmarks = []
        for s_file in sorted(data.keys()):
            for b in sorted(data[s_file], key=lambda x: (x.get("line", 1), x.get("col", 1))):
                all_bookmarks.append((s_file, b))

        if not all_bookmarks:
            return

        active_view = window.active_view()
        curr_file = safe_relpath(active_view.file_name(), root) if active_view and active_view.file_name() else ""
        curr_line = (active_view.rowcol(active_view.sel()[0].begin())[0] + 1) if active_view and active_view.sel() else 0

        target_entry = None
        for i, (s_file, b) in enumerate(all_bookmarks):
            if s_file == curr_file and b.get("line", 1) > curr_line:
                target_entry = (s_file, b)
                break
            elif s_file > curr_file:
                target_entry = (s_file, b)
                break

        if not target_entry:
            target_entry = all_bookmarks[0]  # Wrap around

        s_file, b = target_entry
        window.run_command("rapscallion_jump_bookmark", {
            "stored_file": s_file,
            "line": b.get("line", 1),
            "col": b.get("col", 1),
            "length": b.get("len", 0)
        })


class RapscallionPrevProjectBookmarkCommand(sublime_plugin.WindowCommand):
    """Steps to the previous bookmark across all project files."""

    def run(self):
        window = self.window
        data = BookmarkStorage.load(window)
        if not data:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks found.")
            return

        root = get_project_root(window)
        all_bookmarks = []
        for s_file in sorted(data.keys()):
            for b in sorted(data[s_file], key=lambda x: (x.get("line", 1), x.get("col", 1))):
                all_bookmarks.append((s_file, b))

        if not all_bookmarks:
            return

        active_view = window.active_view()
        curr_file = safe_relpath(active_view.file_name(), root) if active_view and active_view.file_name() else ""
        curr_line = (active_view.rowcol(active_view.sel()[0].begin())[0] + 1) if active_view and active_view.sel() else 0

        target_entry = None
        for i, (s_file, b) in enumerate(reversed(all_bookmarks)):
            if s_file == curr_file and b.get("line", 1) < curr_line:
                target_entry = (s_file, b)
                break
            elif s_file < curr_file:
                target_entry = (s_file, b)
                break

        if not target_entry:
            target_entry = all_bookmarks[-1]  # Wrap around

        s_file, b = target_entry
        window.run_command("rapscallion_jump_bookmark", {
            "stored_file": s_file,
            "line": b.get("line", 1),
            "col": b.get("col", 1),
            "length": b.get("len", 0)
        })


class RapscallionClearFileBookmarksCommand(sublime_plugin.TextCommand):
    """Clears all bookmarks in the current active file."""

    def run(self, edit):
        view = self.view
        window = view.window()
        if not window or not view.file_name():
            return

        root = get_project_root(window)
        stored_path = safe_relpath(view.file_name(), root)
        data = BookmarkStorage.load(window)

        if stored_path in data:
            del data[stored_path]
            BookmarkStorage.save(window, data)
            refresh_all_bookmark_views(window)
            sublime.status_message("Rapscallion Bookmarks: Cleared all bookmarks in current file.")


class RapscallionClearAllBookmarksCommand(sublime_plugin.WindowCommand):
    """Clears all bookmarks in the entire project after confirmation."""

    def run(self):
        window = self.window
        data = BookmarkStorage.load(window)
        total = sum(len(b_list) for b_list in data.values())
        if total == 0:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks to clear.")
            return

        if sublime.ok_cancel_dialog(f"Are you sure you want to delete all {total} bookmarks in this project?", "Clear All"):
            BookmarkStorage.save(window, {})
            refresh_all_bookmark_views(window)
            sublime.status_message("Rapscallion Bookmarks: All bookmarks cleared.")


class RapscallionCleanDeadBookmarksCommand(sublime_plugin.WindowCommand):
    """Prunes bookmarks pointing to files that no longer exist on disk."""

    def run(self):
        window = self.window
        root = get_project_root(window)
        data = BookmarkStorage.load(window)
        dead_files = []

        for s_file in list(data.keys()):
            full_path = resolve_target_path(s_file, root)
            if not os.path.exists(full_path):
                dead_files.append(s_file)

        if not dead_files:
            sublime.status_message("Rapscallion Bookmarks: No dead/missing bookmarks found.")
            return

        if sublime.ok_cancel_dialog(f"Remove bookmarks for {len(dead_files)} missing file(s)?\n" + "\n".join(dead_files[:5]), "Prune"):
            for df in dead_files:
                del data[df]
            BookmarkStorage.save(window, data)
            refresh_all_bookmark_views(window)
            sublime.status_message(f"Rapscallion Bookmarks: Pruned bookmarks for {len(dead_files)} file(s).")


class RapscallionExportMarkdownCommand(sublime_plugin.WindowCommand):
    """Generates a GitHub-flavored Markdown checklist of all project bookmarks."""

    def run(self):
        window = self.window
        data = BookmarkStorage.load(window)
        if not data:
            sublime.status_message("Rapscallion Bookmarks: No bookmarks to export.")
            return

        lines = [
            "# Project Bookmarks",
            "",
            "> Exported via Rapscallion Bookmarks",
            ""
        ]

        for s_file in sorted(data.keys()):
            lines.append(f"### `{s_file}`")
            lines.append("")
            file_bookmarks = sorted(data[s_file], key=lambda x: (x.get("line", 1), x.get("col", 1)))
            for b in file_bookmarks:
                b_name = b.get("name", "Bookmark")
                b_line = b.get("line", 1)
                b_cat = b.get("category", "")
                b_prev = b.get("preview", "").strip()

                cat_prefix = f"**[{b_cat}]** " if b_cat else ""
                lines.append(f"- [ ] `Line {b_line}`: {cat_prefix}{b_name}")
                if b_prev:
                    lines.append(f"  > `{b_prev}`")
            lines.append("")

        md_content = "\n".join(lines)
        sublime.set_clipboard(md_content)

        # Open in a new scratch buffer
        scratch = window.new_file()
        scratch.set_name("Project Bookmarks Export.md")
        scratch.set_scratch(True)
        scratch.assign_syntax("Packages/Markdown/Markdown.sublime-syntax")
        scratch.run_command("append", {"characters": md_content})
        sublime.status_message("Rapscallion Bookmarks: Markdown checklist copied to clipboard and opened.")


class RapscallionJumpBookmarkCommand(sublime_plugin.WindowCommand):
    """Navigates to a bookmark, ensuring centering, focus, and prominent flash highlight."""

    def run(self, stored_file, line=1, col=1, length=0):
        window = self.window
        root = get_project_root(window)
        target_path = resolve_target_path(stored_file, root)

        if not os.path.exists(target_path):
            sublime.status_message(f"Rapscallion Bookmarks: File not found ({stored_file})")
            return

        if window.num_groups() > 1 and find_bookmark_sheet(window):
            editor_group = get_editor_group()
            window.focus_group(editor_group)

        PENDING_HIGHLIGHTS[target_path] = (int(line), int(col), int(length))
        target_view = window.open_file(f"{target_path}:{line}:{col}", sublime.ENCODED_POSITION)
        if target_view and not target_view.is_loading():
            flash_and_center_bookmark(target_view, int(line), int(col), int(length))


class RapscallionRefreshDecorationsCommand(sublime_plugin.TextCommand):
    """Refreshes gutter badges in the view, grouped by custom category scopes with persistent tracking."""

    def run(self, edit):
        view = self.view

        if view.settings().get("is_rapscallion_zip_view", False):
            self._erase_all_regions(view)
            return

        window = view.window()
        file_path = view.file_name()
        if not window or not file_path:
            return

        if file_path.lower().endswith((".zip", ".jar", ".war", ".nupkg")):
            self._erase_all_regions(view)
            return

        root = get_project_root(window)
        stored_path = safe_relpath(file_path, root)
        data = BookmarkStorage.load(window)

        self._erase_all_regions(view)

        if stored_path not in data:
            return

        # Group bookmark regions by category
        regions_by_category = {}
        for b in data[stored_path]:
            cat = b.get("category", "")
            if cat not in regions_by_category:
                regions_by_category[cat] = []
            pt = view.text_point(b.get("line", 1) - 1, b.get("col", 1) - 1)
            regions_by_category[cat].append(sublime.Region(pt, pt))

        # Register persistent regions per category
        for cat, regions in regions_by_category.items():
            scope, icon, _ = get_category_info(cat)
            key = f"{REGION_KEY_PREFIX}_{cat}" if cat else REGION_KEY_PREFIX
            view.add_regions(
                key,
                regions,
                scope,
                icon,
                sublime.PERSISTENT | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
            )

    def _erase_all_regions(self, view):
        categories = get_category_config()
        view.erase_regions(REGION_KEY_PREFIX)
        for cat in categories.keys():
            view.erase_regions(f"{REGION_KEY_PREFIX}_{cat}")


# ==============================================================================
# Optional Side Dock HTML Sheet (Legacy Compatible, Layout Preserving)
# ==============================================================================

def build_panel_html(window):
    data = BookmarkStorage.load(window)
    all_files = sorted(data.keys())
    total_files = len(all_files)
    total_bookmarks = sum(len(b_list) for b_list in data.values())

    collapsed = get_collapsed_files(window)
    all_collapsed = (total_files > 0 and len(collapsed.intersection(set(all_files))) == total_files)
    toggle_label = "Expand All" if all_collapsed else "Collapse All"
    toggle_cmd = "rapscallion_expand_all_bookmarks" if all_collapsed else "rapscallion_collapse_all_bookmarks"

    max_label_chars = get_dynamic_max_chars(window)

    css = """
    <style>
        body {
            background-color: var(--background);
            color: var(--foreground);
            font-family: monospace;
            margin: 0;
            padding: 8px 10px;
            font-size: 11px;
            white-space: nowrap;
        }
        a { text-decoration: none; color: inherit; }
        .header-box { margin-bottom: 4px; line-height: 1.4; white-space: nowrap; overflow: hidden; }
        .meta-line { color: var(--foreground); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .meta-label { color: color-mix(in srgb, var(--foreground) 45%, var(--background)); display: inline-block; width: 76px; }
        .double-divider { border-bottom: 2px solid color-mix(in srgb, var(--foreground) 25%, var(--background)); margin: 6px 0; }
        .tree-toolbar { margin: 4px 0 6px 0; white-space: nowrap; }
        .tool-btn { color: #61afef; padding: 2px 5px; }
        .file-banner { margin-top: 8px; margin-bottom: 2px; font-weight: bold; color: var(--foreground); }
        .bookmark-row { margin: 2px 0; padding-left: 8px; line-height: 1.3; }
        .tree-stem { color: color-mix(in srgb, var(--foreground) 30%, var(--background)); }
        .line-pill { color: #e5c07b; font-size: 10px; }
        .tag-pill { color: #c678dd; font-size: 10px; margin-right: 4px; }
        .bookmark-link { color: #98c379; }
        .edit-badge { color: #61afef; font-size: 10px; padding: 0 3px; }
        .del-badge { color: #e06c75; font-size: 10px; padding: 0 3px; }
    </style>
    """

    content = [
        '<div class="header-box">',
        f'<div class="meta-line"><span class="meta-label">Files:</span>{total_files}</div>',
        f'<div class="meta-line"><span class="meta-label">Bookmarks:</span>{total_bookmarks}</div>',
        '</div>',
        '<div class="double-divider"></div>',
        f'<div class="tree-toolbar"><a class="tool-btn" href="subl:{toggle_cmd}">{toggle_label}</a></div>'
    ]

    for stored_file in all_files:
        is_collapsed = stored_file in collapsed
        arrow = "+" if is_collapsed else "-"
        disp_file = html.escape(stored_file)
        toggle_args = html.escape(json.dumps({"stored_file": stored_file}))
        toggle_href = f"subl:rapscallion_toggle_file_branch {toggle_args}"

        content.append(f'<div class="file-banner"><a href="{toggle_href}">{arrow} {disp_file}</a></div>')

        if not is_collapsed:
            bookmarks = sorted(data[stored_file], key=lambda x: (x.get("line", 0), x.get("col", 0)))
            for i, b in enumerate(bookmarks):
                is_last = (i == len(bookmarks) - 1)
                branch = "`--" if is_last else "|--"
                raw_name = b.get("name", "Bookmark")
                b_line = b.get("line", 1)
                b_col = b.get("col", 1)
                b_len = b.get("len", 0)
                b_cat = b.get("category", "")

                tag_html = f'<span class="tag-pill">[{html.escape(b_cat)}]</span>' if b_cat else ""

                disp_name = raw_name if len(raw_name) <= max_label_chars else raw_name[:max_label_chars - 1] + "..."
                b_name = html.escape(disp_name)
                tooltip_name = html.escape(f"{raw_name} (Line {b_line})")

                jump_args = html.escape(json.dumps({"stored_file": stored_file, "line": b_line, "col": b_col, "length": b_len}))
                rename_args = html.escape(json.dumps({"stored_file": stored_file, "line": b_line, "col": b_col}))
                delete_args = html.escape(json.dumps({"stored_file": stored_file, "line": b_line, "col": b_col}))

                jump_href = f"subl:rapscallion_jump_bookmark {jump_args}"
                rename_href = f"subl:rapscallion_rename_from_sheet {rename_args}"
                delete_href = f"subl:rapscallion_delete_from_sheet {delete_args}"

                content.append(f"""
                <div class="bookmark-row">
                    <span class="tree-stem">{branch} </span><span class="line-pill">L:{b_line}</span> {tag_html}<a class="bookmark-link" href="{jump_href}" title="{tooltip_name}">{b_name}</a> <a href="{rename_href}" title="Rename"><span class="edit-badge">edit</span></a> <a href="{delete_href}" title="Delete"><span class="del-badge">x</span></a>
                </div>
                """)

    return f"<html><head>{css}</head><body>{''.join(content)}</body></html>"


class RapscallionToggleFileBranchCommand(sublime_plugin.WindowCommand):
    def run(self, stored_file):
        collapsed = get_collapsed_files(self.window)
        if stored_file in collapsed:
            collapsed.remove(stored_file)
        else:
            collapsed.add(stored_file)
        refresh_all_bookmark_views(self.window)


class RapscallionExpandAllBookmarksCommand(sublime_plugin.WindowCommand):
    def run(self):
        collapsed = get_collapsed_files(self.window)
        collapsed.clear()
        refresh_all_bookmark_views(self.window)


class RapscallionCollapseAllBookmarksCommand(sublime_plugin.WindowCommand):
    def run(self):
        collapsed = get_collapsed_files(self.window)
        data = BookmarkStorage.load(self.window)
        for key in data.keys():
            collapsed.add(key)
        refresh_all_bookmark_views(self.window)


class RapscallionRenameFromSheetCommand(sublime_plugin.WindowCommand):
    def run(self, stored_file, line=1, col=1):
        window = self.window
        line = int(line)
        col = int(col)
        data = BookmarkStorage.load(window)
        current_name = ""

        if stored_file in data:
            for b in data[stored_file]:
                if b.get("line") == line and b.get("col", 1) == col:
                    current_name = b.get("name", "")
                    break

        def on_done(new_name):
            new_name = new_name.strip()
            if not new_name or new_name == current_name:
                return
            for b in data[stored_file]:
                if b.get("line") == line and b.get("col", 1) == col:
                    b["name"] = new_name
                    break
            BookmarkStorage.save(window, data)
            refresh_all_bookmark_views(window)

        input_view = window.show_input_panel("Rename Bookmark:", current_name, on_done, None, None)
        schedule_select_all(input_view)


class RapscallionDeleteFromSheetCommand(sublime_plugin.WindowCommand):
    def run(self, stored_file, line=1, col=1):
        window = self.window
        line = int(line)
        col = int(col)
        data = BookmarkStorage.load(window)

        if stored_file in data:
            target_b = next((b for b in data[stored_file] if b.get("line") == line and b.get("col", 1) == col), None)
            b_name = target_b.get("name", "Bookmark") if target_b else "Bookmark"

            if sublime.ok_cancel_dialog(f"Delete '{b_name}'?", "Delete"):
                data[stored_file] = [b for b in data[stored_file] if not (b.get("line") == line and b.get("col", 1) == col)]
                if not data[stored_file]:
                    del data[stored_file]
                BookmarkStorage.save(window, data)
                refresh_all_bookmark_views(window)


class RapscallionToggleSidePanelCommand(sublime_plugin.WindowCommand):
    """Optional side column HTML view with layout preservation."""

    def run(self, side=None):
        window = self.window
        side = side or get_setting("side", "right").lower()
        width = float(get_setting("panel_width", 0.22))

        panel_sheet = find_bookmark_sheet(window)

        if panel_sheet:
            save_current_panel_width(window)
            panel_sheet.close()
            window.settings().erase(PANEL_ID_KEY)
            self._restore_layout()
            return

        # Save previous layout before splitting
        prev_layout = window.layout()
        window.settings().set("rapscallion_saved_layout", prev_layout)

        panel_group = 0 if side == "left" else 1
        editor_group = 1 if side == "left" else 0

        if side == "left":
            layout = {
                "cols": [0.0, width, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            }
        else:
            layout = {
                "cols": [0.0, 1.0 - width, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            }

        window.set_layout(layout)
        html_content = build_panel_html(window)
        sheet = window.new_html_sheet("Bookmarks", html_content, group=panel_group)
        window.settings().set(PANEL_ID_KEY, sheet.id())
        window.focus_group(editor_group)

    def _restore_layout(self):
        saved = self.window.settings().get("rapscallion_saved_layout")
        if saved and isinstance(saved, dict) and "cols" in saved:
            self.window.set_layout(saved)
            self.window.settings().erase("rapscallion_saved_layout")
        else:
            self.window.set_layout({
                "cols": [0.0, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1]]
            })


# ==============================================================================
# Event Listeners (Drift Tracking, Status Bar, Hover Popup, Navigation Sync)
# ==============================================================================

class RapscallionBookmarksListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        try:
            window = view.window()
            if not window:
                return

            if window.num_groups() > 1:
                sheet = find_bookmark_sheet(window)
                if sheet:
                    panel_group = get_panel_group()
                    editor_group = get_editor_group()
                    view_group, _ = window.get_view_index(view)
                    if view_group == panel_group:
                        window.set_view_index(view, editor_group, len(window.views_in_group(editor_group)))
                        window.focus_group(editor_group)
                        window.focus_view(view)

            self._check_highlights(view)
            view.run_command("rapscallion_refresh_decorations")
        except Exception as e:
            print(f"[RapscallionBookmarks] Error in on_activated: {e}")

    def on_selection_modified(self, view):
        if not get_setting("status_bar_indicator", True):
            return

        window = view.window()
        file_path = view.file_name()
        if not window or not file_path or not view.sel():
            view.erase_status("rapscallion_bookmark")
            return

        root = get_project_root(window)
        stored_path = safe_relpath(file_path, root)
        data = BookmarkStorage.load(window)

        if stored_path not in data:
            view.erase_status("rapscallion_bookmark")
            return

        curr_line = view.rowcol(view.sel()[0].begin())[0] + 1
        found = next((b for b in data[stored_path] if b.get("line") == curr_line), None)
        if found:
            cat = found.get("category", "")
            cat_label = f" [{cat}]" if cat else ""
            view.set_status("rapscallion_bookmark", f"★ Bookmark: {found.get('name', 'Bookmark')}{cat_label}")
        else:
            view.erase_status("rapscallion_bookmark")

    def on_pre_save(self, view):
        """Dynamic Line-Drift Sync: Updates stored lines from active persistent regions."""
        try:
            window = view.window()
            file_path = view.file_name()
            if not window or not file_path:
                return

            root = get_project_root(window)
            stored_path = safe_relpath(file_path, root)
            data = BookmarkStorage.load(window)

            if stored_path not in data or not data[stored_path]:
                return

            # Collect all registered persistent bookmark regions from view
            all_regions = []
            categories = get_category_config()
            all_regions.extend(view.get_regions(REGION_KEY_PREFIX))
            for cat in categories.keys():
                all_regions.extend(view.get_regions(f"{REGION_KEY_PREFIX}_{cat}"))

            if not all_regions:
                return

            # Sort regions by point
            all_regions = sorted(all_regions, key=lambda r: r.begin())
            stored_bookmarks = sorted(data[stored_path], key=lambda b: (b.get("line", 1), b.get("col", 1)))

            # If count matches, map by sequence
            if len(all_regions) == len(stored_bookmarks):
                changed = False
                for r, b in zip(all_regions, stored_bookmarks):
                    new_line, new_col = view.rowcol(r.begin())[0] + 1, view.rowcol(r.begin())[1] + 1
                    line_region = view.line(r.begin())
                    new_prev = view.substr(line_region).strip()
                    if b.get("line") != new_line or b.get("col") != new_col:
                        b["line"] = new_line
                        b["col"] = new_col
                        b["preview"] = new_prev
                        changed = True

                if changed:
                    BookmarkStorage.save(window, data)
                    # Refresh panel without full reload
                    if window.active_panel() == f"output.{OUTPUT_PANEL_NAME}":
                        render_output_panel(window)
        except Exception as e:
            print(f"[RapscallionBookmarks] Error in on_pre_save drift sync: {e}")

    def on_hover(self, view, point, hover_zone):
        """Displays mini-HTML popup on gutter icon hover."""
        if hover_zone != sublime.HOVER_GUTTER or not get_setting("gutter_hover_popup", True):
            return

        window = view.window()
        file_path = view.file_name()
        if not window or not file_path:
            return

        root = get_project_root(window)
        stored_path = safe_relpath(file_path, root)
        data = BookmarkStorage.load(window)

        if stored_path not in data:
            return

        hover_line = view.rowcol(point)[0] + 1
        target_b = next((b for b in data[stored_path] if b.get("line") == hover_line), None)
        if not target_b:
            return

        b_name = html.escape(target_b.get("name", "Bookmark"))
        b_cat = target_b.get("category", "")
        b_line = target_b.get("line", hover_line)
        b_col = target_b.get("col", 1)
        b_len = target_b.get("len", 0)
        b_prev = html.escape(target_b.get("preview", ""))

        tag_badge = f'<span style="color: #c678dd; font-weight: bold;">[{html.escape(b_cat)}] </span>' if b_cat else ""

        jump_args = html.escape(json.dumps({"stored_file": stored_path, "line": b_line, "col": b_col, "length": b_len}))
        del_args = html.escape(json.dumps({"stored_file": stored_path, "line": b_line, "col": b_col}))
        rename_args = html.escape(json.dumps({"stored_file": stored_path, "line": b_line, "col": b_col}))

        popup_html = f"""
        <body id="rapscallion-hover-popup" style="margin: 0; padding: 6px 10px; font-family: sans-serif; font-size: 11px;">
            <div style="font-weight: bold; margin-bottom: 3px;">★ {tag_badge}{b_name} <span style="color: #7f848e; font-weight: normal;">(L:{b_line})</span></div>
            <div style="color: #98c379; font-family: monospace; margin-bottom: 6px;">{b_prev[:70]}</div>
            <div>
                <a style="color: #61afef; text-decoration: none;" href="subl:rapscallion_jump_bookmark {jump_args}">Jump</a> &nbsp;|&nbsp;
                <a style="color: #e5c07b; text-decoration: none;" href="subl:rapscallion_rename_from_sheet {rename_args}">Rename</a> &nbsp;|&nbsp;
                <a style="color: #e06c75; text-decoration: none;" href="subl:rapscallion_delete_from_sheet {del_args}">Delete</a>
            </div>
        </body>
        """

        view.show_popup(
            popup_html,
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            max_width=500
        )

    def on_pre_close(self, view):
        try:
            window = view.window()
            if not window:
                return
            save_current_panel_width(window)
            sublime.set_timeout(lambda: self._check_collapse(window), 50)
        except Exception as e:
            print(f"[RapscallionBookmarks] Error in on_pre_close: {e}")

    def _check_collapse(self, window):
        try:
            if not window.is_valid():
                return
            if not find_bookmark_sheet(window) and window.num_groups() > 1:
                saved = window.settings().get("rapscallion_saved_layout")
                window.settings().erase(PANEL_ID_KEY)
                if saved and isinstance(saved, dict) and "cols" in saved:
                    window.set_layout(saved)
                    window.settings().erase("rapscallion_saved_layout")
                else:
                    window.set_layout({
                        "cols": [0.0, 1.0],
                        "rows": [0.0, 1.0],
                        "cells": [[0, 0, 1, 1]]
                    })
        except Exception as e:
            print(f"[RapscallionBookmarks] Error collapsing panel layout: {e}")

    def on_load(self, view):
        try:
            self._check_highlights(view)
            view.run_command("rapscallion_refresh_decorations")
        except Exception as e:
            print(f"[RapscallionBookmarks] Error in on_load: {e}")

    def _check_highlights(self, view):
        file_path = view.file_name()
        if not file_path:
            return
        norm = os.path.normpath(file_path)
        if norm in PENDING_HIGHLIGHTS:
            line, col, length = PENDING_HIGHLIGHTS.pop(norm)
            flash_and_center_bookmark(view, line, col, length)
