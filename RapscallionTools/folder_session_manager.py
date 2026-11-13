import sublime
import sublime_plugin
import os
import json

SESSION_DIR_NAME = ".sublime"
STATE_FILE_NAME = "folder-session.json"
CLOSING_WINDOWS = set()

def get_session_file(window):
    folders = window.folders()
    if not folders:
        return None
    session_dir = os.path.join(folders[0], SESSION_DIR_NAME)
    return session_dir, os.path.join(session_dir, STATE_FILE_NAME)

def save_window_state(window):
    paths = get_session_file(window)
    if not paths:
        return
    session_dir, session_file = paths

    data = {"files": []}
    for view in window.views():
        file_path = view.file_name()
        if file_path and os.path.exists(file_path):
            sels = [[s.a, s.b] for s in view.sel()]
            viewport_pos = view.viewport_position()
            data["files"].append({
                "path": file_path,
                "selections": sels,
                "viewport": viewport_pos
            })

    try:
        if not os.path.exists(session_dir):
            os.makedirs(session_dir, exist_ok=True)
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[RapscallionTools] Failed to write session file: {e}")

def restore_window_state(window):
    paths = get_session_file(window)
    if not paths:
        return
    _, session_file = paths
    if not os.path.exists(session_file):
        return

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[RapscallionTools] Failed to read session file: {e}")
        return

    existing_files = {v.file_name() for v in window.views() if v.file_name()}

    for item in data.get("files", []):
        file_path = item.get("path")
        if file_path and os.path.exists(file_path) and file_path not in existing_files:
            view = window.open_file(file_path)

            def apply_view_state(v=view, selections=item.get("selections", []), vp=item.get("viewport"), retries=30):
                if not v or not v.is_valid():
                    return
                if v.is_loading():
                    if retries > 0:
                        sublime.set_timeout(lambda: apply_view_state(v, selections, vp, retries - 1), 50)
                    return
                if selections:
                    v.sel().clear()
                    for sel in selections:
                        if isinstance(sel, (list, tuple)) and len(sel) == 2:
                            v.sel().add(sublime.Region(int(sel[0]), int(sel[1])))
                if vp:
                    v.set_viewport_position(tuple(vp), animate=False)

            sublime.set_timeout(apply_view_state, 50)

class FolderSessionListener(sublime_plugin.EventListener):
    def on_pre_close_window(self, window):
        try:
            CLOSING_WINDOWS.add(window.id())
            save_window_state(window)
            wid = window.id()
            sublime.set_timeout(lambda: CLOSING_WINDOWS.discard(wid), 2000)
        except Exception as e:
            print(f"[RapscallionTools] Failed to save session on pre_close_window: {e}")

    def on_close(self, view):
        try:
            window = view.window() or sublime.active_window()
            if window and window.id() not in CLOSING_WINDOWS:
                save_window_state(window)
        except Exception as e:
            print(f"[RapscallionTools] Failed to save session on view close: {e}")

    def _check_restore(self, window):
        if window and window.is_valid() and not window.settings().get("folder_session_checked", False):
            window.settings().set("folder_session_checked", True)
            restore_window_state(window)

    def on_load(self, view):
        try:
            self._check_restore(view.window())
        except Exception as e:
            print(f"[RapscallionTools] Failed to restore folder session: {e}")

    def on_new_window(self, window):
        try:
            sublime.set_timeout(lambda: self._check_restore(window), 250)
        except Exception as e:
            print(f"[RapscallionTools] Failed to schedule folder session restore: {e}")

class RestoreFolderSessionCommand(sublime_plugin.WindowCommand):
    def run(self):
        restore_window_state(self.window)