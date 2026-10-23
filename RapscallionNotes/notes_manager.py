import sublime
import sublime_plugin
import os
import getpass
import platform
from string import Template
from datetime import datetime

SETTINGS_FILE = "RapscallionNotes.sublime-settings"

def get_settings():
    return sublime.load_settings(SETTINGS_FILE)

def normalize_path(path):
    if not path:
        return ""
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    return os.path.normcase(os.path.abspath(os.path.realpath(expanded)))

def find_matching_rule(folder_path):
    settings = get_settings()
    rules = settings.get("notes_path_rules", [])
    norm_folder = normalize_path(folder_path)

    for rule in rules:
        raw_prefix = rule.get("path_prefix", "")
        if not raw_prefix:
            continue
        norm_prefix = normalize_path(raw_prefix)

        # Match exact prefix folder or any subfolder under it
        if norm_folder == norm_prefix or norm_folder.startswith(norm_prefix + os.sep):
            return rule

    return None

def build_token_dict(root_folder):
    now = datetime.now()
    norm_folder = os.path.normpath(root_folder)
    folder_name = os.path.basename(norm_folder)

    settings = get_settings()
    configured_tac = settings.get("default_tac_name", "").strip()
    tac_name = configured_tac if configured_tac else getpass.getuser()

    return {
        "folder_name": folder_name,
        "ticket_number": folder_name,
        "folder_path": root_folder,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "year": str(now.year),
        "month": now.strftime("%m"),
        "day": now.strftime("%d"),
        "tac_name": tac_name,
        "user": getpass.getuser(),
        "workstation": platform.node(),
    }

def render_template_safely(raw_template, tokens):
    try:
        tmpl = Template(raw_template)
        return tmpl.safe_substitute(tokens)
    except Exception as e:
        print(f"[Rapscallion Tools: Notes] Template substitution error: {e}")
        return raw_template

def ensure_notes_file(window, orig_view=None, force_open=False):
    folders = window.folders()
    if not folders:
        return

    root_folder = folders[0]
    rule = find_matching_rule(root_folder)
    if not rule:
        return

    settings = get_settings()
    subfolder_name = settings.get("notes_subfolder", ".sublime").strip()
    filename = rule.get("filename") or settings.get("notes_default_filename", ".notes.md")

    # Target path: root/.sublime/.notes.md
    target_dir = os.path.join(root_folder, subfolder_name) if subfolder_name else root_folder
    notes_path = os.path.join(target_dir, filename)

    # Non-destructive creation: write only if file does not exist
    if not os.path.exists(notes_path):
        raw_tmpl = rule.get("template") or settings.get(
            "notes_default_template",
            "Ticket#: ${ticket_number}\nDate Created:${date} ${time}\nAssigned TAC:${tac_name}\n\nNotes:\n"
        )
        tokens = build_token_dict(root_folder)
        rendered_content = render_template_safely(raw_tmpl, tokens)

        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(rendered_content)
        except Exception as e:
            print(f"[Rapscallion Tools: Notes] Failed to create note at {notes_path}: {e}")
            return

    # Check auto-open setting (manual Command Palette invocation bypasses this)
    auto_open = settings.get("notes_auto_open", True)
    if not auto_open and not force_open:
        return

    norm_notes_path = normalize_path(notes_path)
    existing_view = None
    for v in window.views():
        if v.file_name() and normalize_path(v.file_name()) == norm_notes_path:
            existing_view = v
            break

    target_view = existing_view or window.open_file(notes_path)

    def position_and_restore_focus(retries=15):
        if not target_view or not target_view.is_valid():
            return

        group, current_idx = window.get_view_index(target_view)
        # View may still be registering inside the window group
        if group == -1:
            if retries > 0:
                sublime.set_timeout(lambda: position_and_restore_focus(retries - 1), 30)
            return

        # Move note view to the first tab position
        if current_idx != 0:
            window.set_view_index(target_view, group, 0)

        # Restore focus to the originally opened file if this was an automated background load
        if not force_open and orig_view and orig_view.is_valid() and orig_view != target_view:
            window.focus_view(orig_view)

    sublime.set_timeout(position_and_restore_focus, 30)

class TicketNotesEventListener(sublime_plugin.EventListener):
    def on_load(self, view):
        window = view.window()
        if not window:
            return

        file_path = view.file_name() or ""

        # Ignore archives to prevent conflicts with custom tree renderers
        ignored_extensions = (".zip", ".jar", ".war", ".nupkg", ".tar", ".gz")
        if file_path.lower().endswith(ignored_extensions):
            return

        # Ignore the notes file itself
        if os.path.basename(file_path).lower() in (".notes.md", "notes.md"):
            return

        # Ensure project folders exist
        if not window.folders():
            return

        try:
            if window.settings().get("rapscallion_notes_initialized", False):
                return
            window.settings().set("rapscallion_notes_initialized", True)

            sublime.set_timeout(lambda: ensure_notes_file(window, orig_view=view, force_open=False), 200)
        except Exception as e:
            print(f"[Rapscallion Tools: Notes] Failed to initialize notes listener: {e}")

class CreateTicketNoteCommand(sublime_plugin.WindowCommand):
    """Command to trigger note creation/opening manually via Command Palette"""
    def run(self):
        ensure_notes_file(self.window, force_open=True)