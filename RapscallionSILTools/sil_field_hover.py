import sublime
import sublime_plugin
import re
import html
import csv

COLUMN_SCOPES = [
    "markup.rainbow1.sil",
    "markup.rainbow2.sil",
    "markup.rainbow3.sil",
    "markup.rainbow4.sil",
    "markup.rainbow5.sil",
    "markup.rainbow6.sil",
    "markup.rainbow7.sil",
    "markup.rainbow8.sil",
    "markup.rainbow9.sil",
    "markup.rainbow10.sil",
]

FALLBACK_COLORS = [
    "#FF5370",  # 1: Coral Red
    "#FFD700",  # 2: Bright Gold / Yellow
    "#50FA7B",  # 3: Emerald Green
    "#38BDF8",  # 4: Sky Blue
    "#BD93F9",  # 5: Electric Purple
    "#FF9800",  # 6: Tangerine Orange
    "#00E5FF",  # 7: Bright Cyan
    "#FF79C6",  # 8: Hot Pink / Magenta
    "#A3E635",  # 9: Lime Green
    "#E2E8F0",  # 10: Platinum Silver
]

CACHE_HEADERS = {}


def is_sil_or_csv_view(view):
    """Returns True only if view contains SIL data, .sil/.csv file, or SIL/CSV results tab."""
    if not view or not view.is_valid():
        return False
    if view.settings().get("is_rapscallion_zip_view", False):
        return False

    # 1. Scope check (fastest)
    if view.score_selector(0, "text.rainbow.sil") > 0:
        return True

    # 2. Syntax path check
    syntax = view.settings().get("syntax", "")
    if "SIL" in syntax or "CSV" in syntax:
        return True

    # 3. File name check
    file_name = view.file_name() or ""
    if file_name.lower().endswith((".sil", ".csv")):
        return True

    # 4. Tab name check
    tab_name = view.name() or ""
    if "Results.csv" in tab_name or "Frequency.csv" in tab_name:
        return True

    # 5. Sample text check
    sample = view.substr(sublime.Region(0, min(view.size(), 256))).lstrip()
    if sample.upper().startswith("@CREATE(") or "CREATE VIEW" in sample.upper():
        return True

    return False


def get_column_color(view, col_index):
    cycle_idx = col_index % 10
    settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
    custom_colors = settings.get("rainbow_column_colors")
    if custom_colors and len(custom_colors) > cycle_idx:
        return custom_colors[cycle_idx]

    scope = COLUMN_SCOPES[cycle_idx]
    style = view.style_for_scope(scope)
    fg_color = style.get("foreground")
    return fg_color if fg_color else FALLBACK_COLORS[cycle_idx]


def _extract_select_fields(raw_select_cols):
    raw_cols = raw_select_cols.split(',')
    fields = [re.sub(r'["\'\[\]\s]', '', f) for f in raw_cols if f.strip()]
    return fields if fields else None


def get_header_fields(view, point=None):
    view_id = view.id()
    change_count = view.change_count()
    cached = CACHE_HEADERS.get(view_id)

    if cached and cached[0] == change_count:
        headers_list = cached[1]
    else:
        headers_list = []
        pattern = r'(?is)SELECT\s+([^;]+?)\s+FROM\b'
        if view.size() <= 2 * 1024 * 1024:
            for region in view.find_all(pattern):
                full_match = view.substr(region)
                match = re.search(r'(?is)SELECT\s+(.*?)\s+FROM\b', full_match)
                if match:
                    fields = _extract_select_fields(match.group(1))
                    if fields:
                        headers_list.append((region.begin(), fields))
        else:
            # Avoid scanning multi-megabyte buffers on the UI/plugin_host thread
            head_text = view.substr(sublime.Region(0, min(view.size(), 256 * 1024)))
            for match in re.finditer(pattern, head_text):
                fields = _extract_select_fields(match.group(1))
                if fields:
                    headers_list.append((match.start(), fields))

        CACHE_HEADERS[view_id] = (change_count, headers_list)

    if not headers_list:
        return None

    chosen_fields = headers_list[0][1]
    if point is not None:
        for begin, fields in headers_list:
            if begin <= point:
                chosen_fields = fields
            else:
                break
    return chosen_fields


def parse_row_at_point(view, point):
    line = view.line(point)
    line_str = view.substr(line).strip()

    if not line_str.startswith('('):
        return None, None, None

    fields = get_header_fields(view, point=point)
    if not fields:
        return None, None, None

    line_full = view.substr(line)
    open_paren_idx = line_full.find('(')
    close_paren_idx = line_full.rfind(')')

    rel_point = point - line.begin()
    if rel_point < open_paren_idx or (close_paren_idx != -1 and rel_point > close_paren_idx):
        return None, None, None

    row_content_start = open_paren_idx + 1
    row_content_end = close_paren_idx if close_paren_idx != -1 else len(line_full)
    inside_row = line_full[row_content_start:row_content_end]
    rel_point_inside = rel_point - row_content_start

    tokens = []
    token_start = 0
    in_squote = False
    in_dquote = False

    for idx, char in enumerate(inside_row):
        if char == "'" and not in_dquote:
            in_squote = not in_squote
        elif char == '"' and not in_squote:
            in_dquote = not in_dquote
        elif char == ',' and not in_squote and not in_dquote:
            tokens.append((token_start, idx, inside_row[token_start:idx]))
            token_start = idx + 1

    tokens.append((token_start, len(inside_row), inside_row[token_start:]))

    col_index = 0
    matched_token = None
    for i, token in enumerate(tokens):
        t_start, t_end, _ = token
        if t_start <= rel_point_inside <= t_end:
            col_index = i
            matched_token = token
            break
    else:
        col_index = len(tokens) - 1
        matched_token = tokens[-1] if tokens else (0, 0, "")

    field_name = fields[col_index] if col_index < len(fields) else ("Col " + str(col_index + 1))
    return col_index, field_name, matched_token


def parse_csv_column_at_point(view, point):
    """Detects (col_index, field_name) at point in a CSV view."""
    try:
        line = view.line(point)
        line_str = view.substr(line)
        header_line = view.substr(view.line(0))
        reader = csv.reader([header_line])
        headers = next(reader, None)
        if not headers:
            return None, None

        if line.begin() == 0:
            rel_pt = point
        else:
            rel_pt = point - line.begin()

        in_quote = False
        col_idx = 0
        for i, ch in enumerate(line_str):
            if i >= rel_pt:
                break
            if ch == '"':
                in_quote = not in_quote
            elif ch == ',' and not in_quote:
                col_idx += 1

        field_name = headers[col_idx] if col_idx < len(headers) else f"Col {col_idx + 1}"
        return col_idx, field_name
    except Exception:
        return None, None


def show_field_popup(view, point, col_index, field_name, raw_val):
    """Renders the styled field context card tooltip at the specified point."""
    try:
        val_trimmed = raw_val.strip() if raw_val else ""

        has_quotes = (
            (val_trimmed.startswith("'") and val_trimmed.endswith("'") and len(val_trimmed) >= 2) or
            (val_trimmed.startswith('"') and val_trimmed.endswith('"') and len(val_trimmed) >= 2)
        )
        clean_val = val_trimmed[1:-1] if has_quotes else val_trimmed

        safe_col = str(col_index + 1)
        safe_field = html.escape(field_name)
        column_color = get_column_color(view, col_index)

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        show_val = settings.get("hover_show_value", True)
        max_len = settings.get("hover_max_value_length", 80)

        if show_val:
            display_val = clean_val if clean_val else "(empty)"
            if max_len > 0 and len(display_val) > max_len:
                display_val = display_val[:max_len] + "..."
            val_style = f"color: {column_color};" if clean_val else "color: #7f848e; font-style: italic;"
            val_html = f'<div class="val" style="{val_style}">{html.escape(display_val)}</div>'
        else:
            val_html = ""

        popup_html = f"""
        <body id="sil-hover">
            <style>
                div.card {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
                    padding: 5px 9px;
                    background-color: color-mix(in srgb, var(--background) 94%, var(--foreground));
                    border: 1px solid color-mix(in srgb, var(--foreground) 22%, transparent);
                    border-radius: 4px;
                    font-size: 11px;
                }}
                .header {{
                    margin-bottom: 2px;
                }}
                b.col-title {{
                    color: {column_color};
                    margin-right: 4px;
                }}
                span.field-name {{
                    color: var(--foreground);
                    font-weight: 500;
                }}
                div.val {{
                    font-weight: bold;
                    margin-top: 3px;
                }}
            </style>
            <div class="card">
                <div class="header">
                    <b class="col-title">Col {safe_col}:</b><span class="field-name">{safe_field}</span>
                </div>
                {val_html}
            </div>
        </body>
        """

        view.show_popup(
            popup_html,
            location=point,
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            max_width=450
        )
    except Exception as e:
        print(f"[Rapscallion Tools: SIL] Error in show_field_popup: {e}")


class SilFieldHoverListener(sublime_plugin.EventListener):
    def on_close(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_post_save(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_modified(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_selection_modified_async(self, view):
        if not is_sil_or_csv_view(view):
            view.erase_status("sil_col_indicator")
            return

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        if not settings.get("status_bar_column_info", True):
            view.erase_status("sil_col_indicator")
            return

        sel = view.sel()
        if not sel or len(sel) == 0:
            view.erase_status("sil_col_indicator")
            return

        try:
            pt = sel[0].b
            col_idx, field_name, _ = parse_row_at_point(view, pt)
            if col_idx is not None:
                view.set_status("sil_col_indicator", f"Col {col_idx + 1}: {field_name}")
            else:
                tab_name = view.name() or ""
                file_name = view.file_name() or ""
                if "Results.csv" in tab_name or file_name.lower().endswith(".csv"):
                    c_idx, c_name = parse_csv_column_at_point(view, pt)
                    if c_idx is not None:
                        view.set_status("sil_col_indicator", f"Col {c_idx + 1}: {c_name}")
                        return
                view.erase_status("sil_col_indicator")
        except (IndexError, Exception):
            view.erase_status("sil_col_indicator")

    def on_hover(self, view, point, hover_zone):
        try:
            if hover_zone != sublime.HOVER_TEXT:
                return

            if not is_sil_or_csv_view(view):
                return

            settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
            if not settings.get("hover_enabled", True):
                return

            col_index, field_name, matched_token = parse_row_at_point(view, point)
            if col_index is None:
                return

            _, _, raw_val = matched_token
            show_field_popup(view, point, col_index, field_name, raw_val)
        except Exception as e:
            print(f"[Rapscallion Tools: SIL] Error in on_hover: {e}")


class SilToggleHoverCommand(sublime_plugin.TextCommand):
    """Toggles hover tooltip display on or off"""
    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view)

    def run(self, edit):
        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        current_state = settings.get("hover_enabled", True)
        new_state = not current_state
        settings.set("hover_enabled", new_state)
        sublime.save_settings("RapscallionSILTools.sublime-settings")
        status = "enabled" if new_state else "disabled"
        sublime.status_message(f"Rapscallion Tools: SIL - Field hover {status}.")