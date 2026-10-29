#!/usr/bin/env python3
"""
Standalone Hex Character Decoding Utility
Decodes hex-escaped byte sequences ({HH}, %HH, \\xHH) in text files, piped streams,
or the Windows clipboard.
"""

import sys
import os
import re
import argparse
import subprocess

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


def decode_hex_text(text: str, pattern_mode: str = "brace"):
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


def get_clipboard() -> str:
    """Retrieves UTF-8 text from the system clipboard."""
    if sys.platform.startswith("win"):
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )
            return res.stdout
        except Exception as e:
            sys.stderr.write(f"Error reading clipboard: {e}\n")
            return ""
    else:
        # Fallback for Linux/macOS
        for cmd in [["pbpaste"], ["xclip", "-selection", "clipboard", "-o"]]:
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8")
                return res.stdout
            except FileNotFoundError:
                continue
    return ""


def set_clipboard(text: str):
    """Copies UTF-8 text to the system clipboard."""
    if sys.platform.startswith("win"):
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text,
                text=True,
                encoding="utf-8",
                check=True
            )
        except Exception as e:
            sys.stderr.write(f"Error setting clipboard: {e}\n")
    else:
        for cmd in [["pbcopy"], ["xclip", "-selection", "clipboard"]]:
            try:
                subprocess.run(cmd, input=text, text=True, encoding="utf-8", check=True)
                break
            except FileNotFoundError:
                continue


def main():
    parser = argparse.ArgumentParser(
        description="Decode hex-encoded characters (e.g. {3A} -> :, %20 -> space, \\x2E -> .)"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Input file path(s). If omitted and not reading from clipboard, reads from stdin."
    )
    parser.add_argument(
        "-p", "--pattern",
        choices=["brace", "percent", "escaped", "all"],
        default="brace",
        help="Pattern to decode: 'brace' ({HH}), 'percent' (%%HH), 'escaped' (\\xHH), or 'all' (default: brace)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "-i", "--in-place",
        action="store_true",
        help="Modify input files in-place"
    )
    parser.add_argument(
        "-c", "--clipboard",
        action="store_true",
        help="Read input from the system clipboard"
    )
    parser.add_argument(
        "--clipboard-out",
        action="store_true",
        help="Copy decoded result back to the system clipboard"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print operation summary to stderr"
    )

    args = parser.parse_args()

    # Case 1: Clipboard Input
    if args.clipboard:
        content = get_clipboard()
        if not content:
            sys.stderr.write("Clipboard is empty or could not be read.\n")
            sys.exit(1)
        decoded, count = decode_hex_text(content, pattern_mode=args.pattern)
        if args.verbose:
            sys.stderr.write(f"Decoded {count} hex character(s) from clipboard.\n")

        if args.clipboard_out or (not args.output and not sys.stdout.isatty()):
            # If requested or piped
            pass

        if args.clipboard_out:
            set_clipboard(decoded)
            if args.verbose:
                sys.stderr.write("Copied decoded result to clipboard.\n")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(decoded)
        else:
            sys.stdout.write(decoded)
        return

    # Case 2: File Inputs
    if args.files:
        total_files = len(args.files)
        total_replaced = 0

        for file_path in args.files:
            if not os.path.exists(file_path):
                sys.stderr.write(f"Error: File not found: {file_path}\n")
                continue

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            decoded, count = decode_hex_text(content, pattern_mode=args.pattern)
            total_replaced += count

            if args.in_place:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(decoded)
                if args.verbose:
                    sys.stderr.write(f"[{file_path}] Decoded {count} hex tokens in-place.\n")
            elif args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(decoded)
                if args.verbose:
                    sys.stderr.write(f"Saved decoded content to {args.output} ({count} tokens).\n")
            else:
                sys.stdout.write(decoded)

        if args.clipboard_out and 'decoded' in locals():
            set_clipboard(decoded)

        if args.verbose:
            sys.stderr.write(f"Total: Processed {total_files} file(s), decoded {total_replaced} hex tokens.\n")
        return

    # Case 3: Stdin Stream Input
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        decoded, count = decode_hex_text(content, pattern_mode=args.pattern)
        if args.verbose:
            sys.stderr.write(f"Decoded {count} hex tokens from stdin.\n")

        if args.clipboard_out:
            set_clipboard(decoded)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(decoded)
        else:
            sys.stdout.write(decoded)
        return

    # No input provided: print help
    parser.print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

