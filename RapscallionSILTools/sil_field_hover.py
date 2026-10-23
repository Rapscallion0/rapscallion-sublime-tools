import sublime
import sublime_plugin
import re
import html
import csv

COLUMN_SCOPES = [
    "markup.deleted.sil",
    "constant.numeric.sil",
    "entity.name.class.sil",
    "string.quoted.single.sil",
    "support.type.sil",
    "entity.name.function.sil",
    "keyword.control.sil",
    "variable.parameter.sil",
    "comment.line.sil",
    "storage.type.sil",
]

FALLBACK_COLORS = [
    "#E06C75", "#D19A66", "#E5C07B", "#98C379", "#56B6C2",
    "#61AFEF", "#C678DD", "#BE5046", "#7F848E", "#4EC9B0",
]

CACHE_HEADERS = {}


def get_column_color(view, col_index):
    cycle_idx = col_index % 10
    scope = COLUMN_SCOPES[cycle_idx]
    style = view.style_for_scope(scope)
    fg_color = style.get("foreground")
    return fg_color if fg_color else FALLBACK_COLORS[cycle_idx]


def get_header_fields(view, point=None):
    view_id = view.id()
    if point is None and view_id in CACHE_HEADERS:
        return CACHE_HEADERS[view_id]

    all_headers = view.find_all(r'(?is)SELECT\s+([^;]+?)\s+FROM\b')
    if not all_headers:
        return None

    chosen_region = all_headers[0]
    if point is not None:
        preceding = [r for r in all_headers if r.begin() <= point]
        if preceding:
            chosen_region = preceding[-1]

    full_match = view.substr(chosen_region)
    match = re.search(r'(?is)SELECT\s+(.*?)\s+FROM\b', full_match)
    if not match:
        return None

    raw_cols = match.group(1).split(',')
    fields = [re.sub(r'["\'\[\]\s]', '', f) for f in raw_cols if f.strip()]
    if fields:
        if len(all_headers) == 1:
            CACHE_HEADERS[view_id] = fields
        return fields
    return None


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


class SilFieldHoverListener(sublime_plugin.EventListener):
    def on_close(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_post_save(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_modified(self, view):
        CACHE_HEADERS.pop(view.id(), None)

    def on_selection_modified_async(self, view):
        if view.settings().get("is_rapscallion_zip_view", False):
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
                # Check if in a CSV view
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

            if view.settings().get("is_rapscallion_zip_view", False):
                return

            settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
            if not settings.get("hover_enabled", True):
                return

            col_index, field_name, matched_token = parse_row_at_point(view, point)
            if col_index is None:
                return

            _, _, raw_val = matched_token
            val_trimmed = raw_val.strip()

            has_quotes = (
                (val_trimmed.startswith("'") and val_trimmed.endswith("'") and len(val_trimmed) >= 2) or
                (val_trimmed.startswith('"') and val_trimmed.endswith('"') and len(val_trimmed) >= 2)
            )
            clean_val = val_trimmed[1:-1] if has_quotes else val_trimmed

            safe_col = str(col_index + 1)
            safe_field = html.escape(field_name)
            column_color = get_column_color(view, col_index)

            show_val = settings.get("hover_show_value", True)
            max_len = settings.get("hover_max_value_length", 80)

            if show_val:
                display_val = clean_val
                if max_len > 0 and len(display_val) > max_len:
                    display_val = display_val[:max_len] + "..."
                val_html = f'<div class="val" style="color: {column_color};">{html.escape(display_val)}</div>'
            else:
                val_html = ""

            popup_html = f"""
            <body id="sil-hover">
                <style>
                    div.card {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
                        padding: 5px 9px;
                        background-color: #21252b;
                        border: 1px solid #3b4048;
                        border-radius: 4px;
                        font-size: 11px;
                    }}
                    .header {{
                        margin-bottom: 2px;
                    }}
                    b.col-title {{
                        color: #61afef;
                        margin-right: 4px;
                    }}
                    span.field-name {{
                        color: #c8ccd4;
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
            print(f"[Rapscallion Tools: SIL] Error in on_hover: {e}")


class SilToggleHoverCommand(sublime_plugin.ApplicationCommand):
    """Toggles hover tooltip display on or off"""
    def run(self):
        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        current_state = settings.get("hover_enabled", True)
        new_state = not current_state
        settings.set("hover_enabled", new_state)
        sublime.save_settings("RapscallionSILTools.sublime-settings")
        status = "enabled" if new_state else "disabled"
        sublime.status_message(f"Rapscallion Tools: SIL - Field hover {status}.")