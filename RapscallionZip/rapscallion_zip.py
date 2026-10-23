import sublime
import sublime_plugin
import zipfile
import os
import datetime
import tempfile
import fnmatch

SETTINGS_FILE = "RapscallionZip.sublime-settings"

ACTIVE_ZIP_VIEWS = {}

def get_setting(key, default=None):
    return sublime.load_settings(SETTINGS_FILE).get(key, default)

def normalize_path(path):
    if not path:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    return os.path.normcase(os.path.abspath(os.path.realpath(expanded)))

def format_size(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return "{0:.1f} {1}".format(bytes_val, unit) if unit != 'B' else "{0} B".format(bytes_val)
        bytes_val /= 1024.0
    return "{0:.1f} TB".format(bytes_val)

def is_ignored(filename, patterns):
    for pattern in patterns:
        if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(os.path.basename(filename), pattern):
            return True
    return False

class TreeNode:
    def __init__(self, name, is_dir=False, info=None, full_path=""):
        self.name = name
        self.is_dir = is_dir
        self.info = info
        self.full_path = full_path
        self.children = {}

    def add_child(self, parts, info, full_path=""):
        if not parts:
            return
        part = parts[0]
        is_leaf = len(parts) == 1
        is_directory = not is_leaf or info.filename.endswith('/')

        if part not in self.children:
            self.children[part] = TreeNode(
                name=part,
                is_dir=is_directory,
                info=info if is_leaf else None,
                full_path=full_path if is_leaf else ""
            )

        if not is_leaf:
            self.children[part].add_child(parts[1:], info, full_path)

    def matches_filter(self, query):
        if not query:
            return True
        if query.lower() in self.name.lower():
            return True
        return any(child.matches_filter(query) for child in self.children.values())

def update_row_highlight(view, row):
    pt = view.text_point(row, 0)
    line_region = view.line(pt)
    view.add_regions(
        "rapscallion_zip_active_row",
        [line_region],
        "region.bluish",
        "",
        sublime.DRAW_SOLID_UNDERLINE | sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE
    )

class RapscallionRenderZipTreeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        path = view.settings().get("zip_archive_path")
        if not path or not zipfile.is_zipfile(path):
            return

        expanded = set(view.settings().get("zip_expanded_dirs", []))
        filter_query = view.settings().get("zip_filter_query", "").strip()
        ignored_patterns = get_setting("archive_ignored_patterns", [])

        try:
            stat_info = os.stat(path)
            archive_size_str = format_size(stat_info.st_size)
            mod_time_str = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            with zipfile.ZipFile(path, 'r') as zf:
                root = TreeNode(os.path.basename(path), is_dir=True)
                items = zf.infolist()

                total_files = 0
                all_dirs = set()
                total_uncomp = 0

                for info in items:
                    if is_ignored(info.filename, ignored_patterns):
                        continue

                    clean_path = info.filename.rstrip('/')
                    parts = clean_path.split('/')
                    root.add_child(parts, info, full_path=info.filename)

                    if info.filename.endswith('/'):
                        all_dirs.add(clean_path)
                    else:
                        total_files += 1
                        total_uncomp += info.file_size
                        for i in range(1, len(parts)):
                            all_dirs.add('/'.join(parts[:i]))

                total_folders = len(all_dirs)
                uncomp_size_str = format_size(total_uncomp)
                parent_dir = os.path.dirname(path).rstrip('\\/') + '\\'

                NAME_WIDTH = 56
                SIZE_WIDTH = 12
                COMP_WIDTH = 12
                DATE_WIDTH = 16

                header_line = "{0:<{1}} {2:>{3}}   {4:>{5}}   {6:<{7}}".format(
                    'Name', NAME_WIDTH, 'Size', SIZE_WIDTH, 'Compressed', COMP_WIDTH, 'Date', DATE_WIDTH
                )
                divider = "-" * len(header_line)
                double_divider = "=" * len(header_line)

                lines = [
                    "ARCHIVE:       {0}".format(os.path.basename(path)),
                    "PATH:          {0}".format(parent_dir),
                    "ARCHIVE SIZE:  {0} ({1:,} bytes) [Uncompressed: {2} ({3:,} bytes)]".format(
                        archive_size_str, stat_info.st_size, uncomp_size_str, total_uncomp
                    ),
                    "DATE MODIFIED: {0}".format(mod_time_str),
                    "CONTENTS:      {0} files, {1} folders{2}".format(
                        total_files, total_folders, (" (Filtered: '{0}')".format(filter_query) if filter_query else "")
                    ),
                    double_divider,
                    "ℹ Click ▸ / ▾ to toggle folder, double-click item or press Enter to open",
                    header_line,
                    divider,
                ]

                header_map = {"0": "archive", "1": "path"}
                line_map = {}
                dir_line_map = {}

                def render_node(node, depth=0, current_path=""):
                    sorted_children = sorted(
                        node.children.values(),
                        key=lambda x: (not x.is_dir, x.name.lower())
                    )

                    indent = "    " * depth

                    for child in sorted_children:
                        if filter_query and not child.matches_filter(filter_query):
                            continue

                        child_path = "{0}{1}/".format(current_path, child.name) if child.is_dir else child.full_path

                        if child.is_dir:
                            is_open = child_path in expanded or bool(filter_query)
                            icon = "▾" if is_open else "▸"
                            display_str = "{0}{1} 📁 {2}/".format(indent, icon, child.name)

                            line_idx = len(lines)
                            dir_line_map[str(line_idx)] = child_path
                            lines.append(display_str)

                            if is_open:
                                render_node(child, depth + 1, child_path)
                        else:
                            info = child.info
                            sz_str = format_size(info.file_size)
                            comp_str = format_size(info.compress_size)
                            dt_str = "%d-%02d-%02d %02d:%02d" % info.date_time[:5]

                            raw_name_col = "{0}  📄 {1}".format(indent, child.name)
                            visual_name_len = len(raw_name_col) + 1
                            padding = max(1, NAME_WIDTH - visual_name_len)
                            padded_name = raw_name_col + (" " * padding)

                            line_idx = len(lines)
                            line_map[str(line_idx)] = child.full_path
                            lines.append("{0} {1:>{2}}   {3:>{4}}   {5:<{6}}".format(
                                padded_name, sz_str, SIZE_WIDTH, comp_str, COMP_WIDTH, dt_str, DATE_WIDTH
                            ))

                render_node(root)
                lines.append(double_divider)

            viewport = view.viewport_position()
            
            view.set_read_only(False)
            view.replace(edit, sublime.Region(0, view.size()), "\n".join(lines))
            view.set_read_only(True)
            view.set_scratch(True)

            view.settings().set("zip_header_map", header_map)
            view.settings().set("zip_line_map", line_map)
            view.settings().set("zip_dir_line_map", dir_line_map)

            active_row = view.settings().get("zip_active_row")
            if active_row is not None:
                update_row_highlight(view, active_row)
            
            view.set_viewport_position(viewport, False)

        except Exception as e:
            sublime.error_message("[Rapscallion Tools: Zip] Render failed:\n{0}".format(str(e)))


class RapscallionZipOpenInterceptor(sublime_plugin.EventListener):
    def on_load(self, view):
        try:
            file_path = view.file_name()
            if not file_path:
                return

            ext = os.path.splitext(file_path)[1].lower()
            if ext not in (".zip", ".jar", ".war", ".nupkg"):
                return

            if not zipfile.is_zipfile(file_path):
                return

            norm_path = normalize_path(file_path)
            window = view.window() or sublime.active_window()

            if norm_path in ACTIVE_ZIP_VIEWS:
                target_id = ACTIVE_ZIP_VIEWS[norm_path]
                if window:
                    for v in window.views():
                        if v.id() == target_id and v.is_valid():
                            window.focus_view(v)
                            view.set_scratch(True)
                            view.close()
                            return

            ACTIVE_ZIP_VIEWS[norm_path] = view.id()

            view.settings().set("is_rapscallion_zip_view", True)
            view.settings().set("zip_archive_path", file_path)
            view.settings().set("zip_expanded_dirs", [])
            view.settings().set("zip_filter_query", "")
            view.settings().set("fold_buttons", False)
            view.settings().set("show_folding_indicators", False)
            syntax_path = "Packages/RapscallionZip/RapscallionZip.sublime-syntax"
            if sublime.find_resources("RapscallionZip.sublime-syntax"):
                view.assign_syntax(syntax_path)
            else:
                syntax = sublime.find_syntax_by_name("Plain Text")
                if syntax:
                    view.assign_syntax(syntax[0])

            view.run_command("rapscallion_render_zip_tree")
        except Exception as e:
            print(f"[Rapscallion Tools: Zip] Error in zip open interceptor: {e}")

    def on_close(self, view):
        try:
            vid = view.id()
            for path, tracked_id in list(ACTIVE_ZIP_VIEWS.items()):
                if tracked_id == vid:
                    del ACTIVE_ZIP_VIEWS[path]
        except Exception as e:
            print(f"[Rapscallion Tools: Zip] Error in zip on_close: {e}")


class RapscallionHandleZipClickCommand(sublime_plugin.TextCommand):
    """Unified handler: single-click arrow toggle, double-click row toggle/open."""
    def run(self, edit, event=None, count=1):
        view = self.view
        if not view.settings().get("is_rapscallion_zip_view"):
            return

        if event:
            pt = view.window_to_text((event["x"], event["y"]))
            row, col = view.rowcol(pt)
        else:
            sels = view.sel()
            if not sels:
                return
            pt = sels[0].b
            row, col = view.rowcol(pt)

        view.settings().set("zip_active_row", row)
        update_row_highlight(view, row)

        row_str = str(row)
        header_map = view.settings().get("zip_header_map", {})
        dir_line_map = view.settings().get("zip_dir_line_map", {})
        line_map = view.settings().get("zip_line_map", {})
        zip_path = view.settings().get("zip_archive_path")

        # Double-click header items
        if count == 2 and row_str in header_map and zip_path:
            header_type = header_map[row_str]
            if header_type == "archive":
                try:
                    os.startfile(zip_path)
                except Exception as e:
                    sublime.error_message("[Rapscallion Tools: Zip] Could not open archive:\n{0}".format(str(e)))
            elif header_type == "path":
                parent_dir = os.path.dirname(zip_path)
                if os.path.isdir(parent_dir):
                    try:
                        os.startfile(parent_dir)
                    except Exception as e:
                        sublime.error_message("[Rapscallion Tools: Zip] Could not open folder:\n{0}".format(str(e)))
            return

        # Folder toggle handling
        if row_str in dir_line_map:
            dir_path = dir_line_map[row_str]
            line_str = view.substr(view.line(pt))

            arrow_idx = -1
            for symbol in ("▸", "▾", "▶", "▼"):
                idx = line_str.find(symbol)
                if idx != -1:
                    arrow_idx = idx
                    break

            clicked_arrow = (arrow_idx != -1 and abs(col - arrow_idx) <= 4)

            # Single click on arrow OR double click on the row
            if (count == 1 and clicked_arrow) or count == 2:
                expanded = set(view.settings().get("zip_expanded_dirs", []))
                if dir_path in expanded:
                    expanded.remove(dir_path)
                else:
                    expanded.add(dir_path)

                view.settings().set("zip_expanded_dirs", list(expanded))
                view.run_command("rapscallion_render_zip_tree")
            return

        # Double-click file opens it
        if count == 2 and row_str in line_map:
            inner_file_path = line_map[row_str]
            safe_extract_and_open(self.view.window() or sublime.active_window(), zip_path, inner_file_path)

    def want_event(self):
        return True


def safe_extract_and_open(window, zip_path, file_path):
    if not zip_path or not os.path.exists(zip_path) or not file_path:
        return

    temp_dir = os.path.abspath(os.path.join(tempfile.gettempdir(), "RapscallionTools_ZipCache"))
    target_abs = os.path.abspath(os.path.join(temp_dir, file_path))
    if not target_abs.startswith(temp_dir + os.sep):
        sublime.error_message(f"[Rapscallion Tools: Zip] Path traversal detected in archive entry:\n{file_path}")
        return

    os.makedirs(temp_dir, exist_ok=True)

    def _worker():
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                extracted_path = zf.extract(file_path, path=temp_dir)

            def _open():
                if window and window.is_valid():
                    window.open_file(extracted_path)

            sublime.set_timeout(_open, 0)
        except Exception as e:
            sublime.set_timeout(lambda: sublime.error_message(f"[Rapscallion Tools: Zip] Failed to extract item:\n{e}"), 0)

    sublime.set_timeout_async(_worker, 0)


class RapscallionActivateZipItemCommand(sublime_plugin.TextCommand):
    """Enter key handler: toggles folder or opens file."""
    def run(self, edit):
        view = self.view
        if not view.settings().get("is_rapscallion_zip_view"):
            return

        row = view.settings().get("zip_active_row")
        if row is None:
            sels = view.sel()
            if sels:
                row, _ = view.rowcol(sels[0].b)
            else:
                return

        update_row_highlight(view, row)

        dir_map = view.settings().get("zip_dir_line_map", {})
        line_map = view.settings().get("zip_line_map", {})
        zip_path = view.settings().get("zip_archive_path")

        target_dir = dir_map.get(str(row))
        target_file = line_map.get(str(row))

        if target_dir:
            expanded = set(view.settings().get("zip_expanded_dirs", []))
            if target_dir in expanded:
                expanded.remove(target_dir)
            else:
                expanded.add(target_dir)
            view.settings().set("zip_expanded_dirs", list(expanded))
            view.run_command("rapscallion_render_zip_tree")
        elif target_file and zip_path:
            window = view.window() or sublime.active_window()
            safe_extract_and_open(window, zip_path, target_file)