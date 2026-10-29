import re
import sublime
import sublime_plugin

# Regex pattern pairs: (Group of contiguous hex tokens, Single hex token extractor)
HEX_PATTERNS = {
    "brace": (
        re.compile(r"((?:\{[0-9a-fA-F]{2}\})+)"),
        re.compile(r"\{([0-9a-fA-F]{2})\}")
    ),
    "percent": (
        re.compile(r"((?:%[0-9a-fA-F]{2})+)"),
        re.compile(r"%([0-9a-fA-F]{2})")
    ),
    "escaped": (
        re.compile(r"((?:\\x[0-9a-fA-F]{2})+)"),
        re.compile(r"\\x([0-9a-fA-F]{2})")
    ),
}


def decode_hex_text(text, pattern_mode="brace"):
    """
    Decodes hex-encoded byte representations within text.
    Handles multi-byte UTF-8 sequences by decoding consecutive tokens together.
    Falls back to Latin-1 if a byte sequence is not valid UTF-8.

    :param text: String containing hex escape sequences.
    :param pattern_mode: 'brace' ({HH}), 'percent' (%HH), 'escaped' (\\xHH), or 'all'.
    :return: Tuple of (decoded_string, total_hex_tokens_replaced).
    """
    if not text:
        return text, 0

    modes = ["brace", "percent", "escaped"] if pattern_mode == "all" else [pattern_mode]
    total_count = 0
    current_text = text

    for mode in modes:
        if mode not in HEX_PATTERNS:
            continue
        group_re, byte_re = HEX_PATTERNS[mode]

        def replace_group(match):
            nonlocal total_count
            raw_group = match.group(1)
            hex_tokens = byte_re.findall(raw_group)
            if not hex_tokens:
                return raw_group
            total_count += len(hex_tokens)
            try:
                byte_data = bytes(int(h, 16) for h in hex_tokens)
                try:
                    return byte_data.decode("utf-8")
                except UnicodeDecodeError:
                    return byte_data.decode("latin-1")
            except Exception:
                return raw_group

        current_text = group_re.sub(replace_group, current_text)

    return current_text, total_count


class RapscallionDecodeHexCommand(sublime_plugin.TextCommand):
    """
    Decodes hex-escaped characters in the active buffer.
    - If regions are selected, decodes only selected regions.
    - If no regions are selected, decodes the entire buffer.
    - If to_new_tab is True, outputs the decoded text into an unsaved scratch tab.
    - If to_new_tab is False, replaces text in-place with a single undo step.
    """

    def run(self, edit, to_new_tab=False, pattern="brace"):
        # Load user configuration override if available
        settings = sublime.load_settings("RapscallionTools.sublime-settings")
        configured_mode = settings.get("hex_decode_default_pattern", pattern)
        active_pattern = pattern if pattern != "brace" else configured_mode

        entire_view_region = sublime.Region(0, self.view.size())
        selections = [r for r in self.view.sel() if not r.empty()]

        if to_new_tab:
            # Generate decoded content
            if selections:
                # Concatenate selected regions or decode entire view
                parts = [self.view.substr(r) for r in selections]
                source_text = "\n".join(parts)
            else:
                source_text = self.view.substr(entire_view_region)

            decoded_text, count = decode_hex_text(source_text, pattern_mode=active_pattern)

            # Open a new scratch buffer tab
            window = self.view.window() or sublime.active_window()
            new_view = window.new_file()
            orig_name = self.view.file_name() or self.view.name() or "Buffer"
            new_view.set_name(f"Decoded - {orig_name}")
            new_view.set_scratch(True)

            # Inherit syntax if available
            orig_syntax = self.view.settings().get("syntax")
            if orig_syntax:
                new_view.assign_syntax(orig_syntax)

            new_view.run_command("append", {"characters": decoded_text})
            sublime.status_message(f"Rapscallion: Decoded {count} hex character(s) to new tab")
        else:
            # In-place replacement
            total_replaced = 0
            if selections:
                # Replace selections in reverse order to preserve region offsets
                for region in reversed(selections):
                    original = self.view.substr(region)
                    decoded, count = decode_hex_text(original, pattern_mode=active_pattern)
                    total_replaced += count
                    self.view.replace(edit, region, decoded)
            else:
                original = self.view.substr(entire_view_region)
                decoded, count = decode_hex_text(original, pattern_mode=active_pattern)
                total_replaced += count
                self.view.replace(edit, entire_view_region, decoded)

            sublime.status_message(f"Rapscallion: Decoded {total_replaced} hex character(s)")

    def is_enabled(self):
        return self.view.size() > 0

