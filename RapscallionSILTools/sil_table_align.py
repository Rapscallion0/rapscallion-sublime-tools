import sublime
import sublime_plugin
import csv
import io

try:
    from .sil_field_hover import is_sil_or_csv_view
except Exception:
    is_sil_or_csv_view = lambda view: False


def tokenize_sil_tuple(line):
    """
    Parses a single SIL tuple line e.g. "  ('A', 12, 'B', ),"
    Returns (indent, tokens, suffix) or None if not a valid tuple line.
    """
    raw = line.rstrip('\r\n')
    lstripped = raw.lstrip()
    indent = raw[:len(raw) - len(lstripped)]

    if not lstripped.startswith('('):
        return None

    rstripped = lstripped.rstrip()
    if not (rstripped.endswith(')') or rstripped.endswith('),') or rstripped.endswith(');')):
        return None

    last_paren = rstripped.rfind(')')
    if last_paren == -1:
        return None

    inside = rstripped[1:last_paren]
    suffix = rstripped[last_paren:]

    tokens = []
    current = []
    in_squote = False
    in_dquote = False
    i = 0
    length = len(inside)

    while i < length:
        ch = inside[i]
        if in_squote:
            if ch == "'":
                if i + 1 < length and inside[i + 1] == "'":
                    current.append("''")
                    i += 2
                    continue
                else:
                    in_squote = False
                    current.append("'")
                    i += 1
                    continue
            else:
                current.append(ch)
                i += 1
                continue

        if in_dquote:
            if ch == '"':
                if i + 1 < length and inside[i + 1] == '"':
                    current.append('""')
                    i += 2
                    continue
                else:
                    in_dquote = False
                    current.append('"')
                    i += 1
                    continue
            else:
                current.append(ch)
                i += 1
                continue

        if ch == "'":
            in_squote = True
            current.append("'")
            i += 1
        elif ch == '"':
            in_dquote = True
            current.append('"')
            i += 1
        elif ch == ',':
            tokens.append("".join(current).strip())
            current = []
            i += 1
        else:
            current.append(ch)
            i += 1

    tokens.append("".join(current).strip())
    return (indent, tokens, suffix)


def tokenize_csv_line(line):
    """Parses a CSV line, preserving leading indentation and trailing newline."""
    raw = line.rstrip('\r\n')
    lstripped = raw.lstrip()
    indent = raw[:len(raw) - len(lstripped)]
    if not lstripped:
        return None

    try:
        reader = csv.reader([lstripped])
        row = next(reader)
        return (indent, [c.strip() for c in row], "")
    except Exception:
        return None


class SilAlignColumnsCommand(sublime_plugin.TextCommand):
    """
    Vertically aligns table columns in SIL data row tuples or CSV lines.
    Reversible in one step with standard Undo (Ctrl+Z).
    """

    def is_visible(self):
        return is_sil_or_csv_view(self.view)

    def is_enabled(self):
        return is_sil_or_csv_view(self.view) and self.view.size() > 0

    def run(self, edit):
        view = self.view
        sel = view.sel()
        if not sel:
            return

        settings = sublime.load_settings("RapscallionSILTools.sublime-settings")
        max_col_limit = settings.get("align_max_col_width", 120)

        # 1. Determine lines to process
        has_selection = any(not s.empty() for s in sel)

        if has_selection:
            # Process all lines covered by current selections
            line_regions = []
            for s in sel:
                for line_reg in view.lines(s):
                    if line_reg not in line_regions:
                        line_regions.append(line_reg)
        else:
            # Caret is at a single point: automatically discover contiguous block
            pt = sel[0].b
            cur_line = view.line(pt)
            cur_text = view.substr(cur_line)

            is_sil_candidate = cur_text.lstrip().startswith('(')

            # Expand upwards and downwards to find contiguous block
            start_row, _ = view.rowcol(cur_line.begin())
            total_lines = view.rowcol(view.size())[0] + 1

            up_row = start_row
            while up_row > 0:
                prev_line = view.line(view.text_point(up_row - 1, 0))
                prev_text = view.substr(prev_line)
                if is_sil_candidate:
                    if not prev_text.lstrip().startswith('('):
                        break
                else:
                    if not prev_text.strip():
                        break
                up_row -= 1

            down_row = start_row
            while down_row < total_lines - 1:
                next_line = view.line(view.text_point(down_row + 1, 0))
                next_text = view.substr(next_line)
                if is_sil_candidate:
                    if not next_text.lstrip().startswith('('):
                        break
                else:
                    if not next_text.strip():
                        break
                down_row += 1

            line_regions = [
                view.line(view.text_point(r, 0))
                for r in range(up_row, down_row + 1)
            ]

        if not line_regions:
            sublime.status_message("Rapscallion Tools: SIL - No lines to align.")
            return

        lines_text = [view.substr(lr) for lr in line_regions]

        # 2. Try parsing as SIL tuples
        parsed_rows = []
        is_sil = True
        for lt in lines_text:
            toks = tokenize_sil_tuple(lt)
            if toks is None:
                is_sil = False
                break
            parsed_rows.append(toks)

        # 3. If not all valid SIL tuples, try CSV
        if not is_sil:
            parsed_rows = []
            for lt in lines_text:
                c_toks = tokenize_csv_line(lt)
                if c_toks is None:
                    continue
                parsed_rows.append(c_toks)

        if not parsed_rows:
            sublime.status_message("Rapscallion Tools: SIL - Could not parse table columns on selected lines.")
            return

        # 4. Compute maximum width for each column
        max_cols = max(len(p[1]) for p in parsed_rows)
        col_widths = [0] * max_cols
        for p in parsed_rows:
            tokens = p[1]
            for c_idx, tok in enumerate(tokens):
                w = len(tok)
                if max_col_limit > 0:
                    w = min(w, max_col_limit)
                col_widths[c_idx] = max(col_widths[c_idx], w)

        # 5. Format aligned rows
        aligned_lines = []
        for indent, tokens, suffix in parsed_rows:
            formatted_tokens = []
            for c_idx in range(max_cols):
                tok = tokens[c_idx] if c_idx < len(tokens) else ""
                w = col_widths[c_idx]
                formatted_tokens.append(tok.ljust(w))

            if is_sil:
                row_str = f"{indent}({', '.join(formatted_tokens)}{suffix}"
            else:
                row_str = f"{indent}{', '.join(formatted_tokens)}"
            aligned_lines.append(row_str)

        # 6. Apply replacement in one atomic undo step
        full_region = sublime.Region(line_regions[0].begin(), line_regions[-1].end())
        replacement_text = "\n".join(aligned_lines)
        view.replace(edit, full_region, replacement_text)

        sublime.status_message(f"Rapscallion Tools: SIL - Aligned {len(aligned_lines)} rows across {max_cols} columns.")
