import sublime
import sublime_plugin
import subprocess
import os
import sys
import datetime
import urllib.parse
import shutil
import html

SETTINGS_FILE = "RapscallionTools.sublime-settings"

ACTIVE_MEDIA_VIEWS = {}      # norm_path -> view.id()
PERSISTENT_PHANTOMS = {}     # view.id() -> PhantomSet
APP_NAME_CACHE = {}          # ext -> app_name

def get_setting(key, default=None):
    settings = sublime.load_settings(SETTINGS_FILE)
    return settings.get(key, default)

def get_windows_app_name(ext):
    try:
        import winreg
        user_choice_path = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{ext}\UserChoice"
        prog_id = None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_choice_path) as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        except OSError:
            pass

        if not prog_id:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
                    prog_id, _ = winreg.QueryValue(key, "")
            except OSError:
                pass

        if not prog_id:
            return None

        shell_open_path = rf"{prog_id}\shell\open\command"
        raw_cmd = None
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, shell_open_path) as key:
                raw_cmd, _ = winreg.QueryValue(key, "")
        except OSError:
            pass

        if raw_cmd:
            raw_cmd = raw_cmd.strip()
            exe = raw_cmd[1:].split('"', 1)[0] if raw_cmd.startswith('"') else raw_cmd.split()[0]
            base_exe = os.path.splitext(os.path.basename(exe))[0]
            if base_exe.lower() not in ("openwith", "cmd", "explorer", "rundll32"):
                return base_exe.capitalize()

        if "AppX" in prog_id or "Microsoft." in prog_id:
            for part in prog_id.split("."):
                if part.lower() not in ("appx", "microsoft", "windows", "default"):
                    return part.capitalize()
    except Exception:
        pass
    return None

def detect_default_app(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    # Check manual configuration override first
    overrides = get_setting("external_app_overrides", {})
    if ext in overrides and overrides[ext]:
        override_exe = overrides[ext]
        return os.path.splitext(os.path.basename(override_exe))[0].capitalize()

    if ext in APP_NAME_CACHE:
        return APP_NAME_CACHE[ext]

    detected = None
    try:
        if sys.platform.startswith("win"):
            detected = get_windows_app_name(ext)
            if detected and detected.lower() in ("windows", "system", "unknown"):
                detected = None
        elif sys.platform.startswith("darwin"):
            script = f'tell application "Finder" to set app_path to application file id (default application of (POSIX file "{file_path}" as alias)) as text\nPOSIX path of app_path'
            out = subprocess.check_output(["osascript", "-e", script], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore').strip()
            if out:
                app_name = os.path.basename(out.rstrip('/')).replace('.app', '')
                if app_name.lower() not in ("finder", "system"):
                    detected = app_name
        else:
            mime = subprocess.check_output(["xdg-mime", "query", "filetype", file_path], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore').strip()
            if mime:
                desktop = subprocess.check_output(["xdg-mime", "query", "default", mime], stderr=subprocess.DEVNULL).decode('utf-8', 'ignore').strip()
                if desktop:
                    detected = desktop.replace('.desktop', '').capitalize()
    except Exception:
        pass

    APP_NAME_CACHE[ext] = detected
    return detected

def launch_external(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    overrides = get_setting("external_app_overrides", {})

    if ext in overrides and overrides[ext]:
        custom_bin = overrides[ext]
        try:
            subprocess.Popen([custom_bin, file_path])
            return
        except Exception as exc:
            print(f"[RapscallionTools] Custom override launch failed: {exc}")

    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", file_path], shell=True)
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", file_path])
        else:
            subprocess.Popen(["xdg-open", file_path])
    except Exception as exc:
        print(f"[RapscallionTools] Launch failed: {exc}")

def format_file_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def on_phantom_click(href):
    if href.startswith("action:reopen?path="):
        encoded_path = href.split("?path=", 1)[1]
        target_path = urllib.parse.unquote(encoded_path)
        if os.path.exists(target_path):
            launch_external(target_path)
    elif href.startswith("action:reveal?path="):
        encoded_path = href.split("?path=", 1)[1]
        target_path = urllib.parse.unquote(encoded_path)
        folder = os.path.dirname(target_path)
        if os.path.isdir(folder):
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"/select,{target_path}"])
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", "-R", target_path])
            else:
                subprocess.Popen(["xdg-open", folder])
    elif href.startswith("action:copy?path="):
        encoded_path = href.split("?path=", 1)[1]
        target_path = urllib.parse.unquote(encoded_path)
        sublime.set_clipboard(target_path)
        sublime.status_message(f"[RapscallionTools] Copied path to clipboard")

def build_card_html(file_path, app_name):
    file_size = "Unknown"
    modified_time = "Unknown"
    if os.path.exists(file_path):
        try:
            stat = os.stat(file_path)
            file_size = format_file_size(stat.st_size)
            modified_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %I:%M %p')
        except OSError:
            pass

    launched_time = datetime.datetime.now().strftime('%I:%M:%S %p')
    file_name_only = os.path.basename(file_path)
    ext = os.path.splitext(file_name_only)[1].upper().replace('.', '')
    encoded_path = urllib.parse.quote(file_path)

    safe_app_name = html.escape(app_name) if app_name else ""
    safe_file_name = html.escape(file_name_only)
    safe_file_path = html.escape(file_path)
    safe_ext = html.escape(ext)
    safe_size = html.escape(file_size)
    safe_modified = html.escape(modified_time)
    safe_launched = html.escape(launched_time)

    if app_name:
        subtitle_text = f"Opened in <b>{safe_app_name}</b>"
        app_row = f"""
            <div class="meta-row">
                <div class="meta-label">External App</div>
                <div class="meta-value"><b>{safe_app_name}</b></div>
            </div>
        """
        button_text = f"Re-open in {safe_app_name}"
    else:
        subtitle_text = "Opened in external viewer"
        app_row = ""
        button_text = "Re-open in External App"

    return f"""
    <body id="rapscallion-media-preview">
        <style>
            body {{
                background-color: var(--background);
                color: var(--foreground);
                font-family: system-ui, -apple-system, blinkmacsystemfont, "Segoe UI", roboto, sans-serif;
                padding: 30px;
            }}
            .card {{
                background-color: color-mix(in srgb, var(--foreground) 5%, var(--background));
                border: 1px solid color-mix(in srgb, var(--foreground) 14%, var(--background));
                border-radius: 6px;
                padding: 24px;
                max-width: 650px;
            }}
            .badge {{
                background-color: var(--accent);
                color: #ffffff;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            .title {{
                font-size: 18px;
                font-weight: bold;
                margin-top: 10px;
                margin-bottom: 2px;
                color: var(--foreground);
            }}
            .subtitle {{
                font-size: 12px;
                color: color-mix(in srgb, var(--foreground) 60%, var(--background));
                margin-bottom: 16px;
            }}
            .meta-list {{
                margin-top: 10px;
                margin-bottom: 20px;
                border-top: 1px solid color-mix(in srgb, var(--foreground) 10%, var(--background));
            }}
            .meta-row {{
                padding: 8px 0;
                border-bottom: 1px solid color-mix(in srgb, var(--foreground) 8%, var(--background));
            }}
            .meta-label {{
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                color: color-mix(in srgb, var(--foreground) 55%, var(--background));
                margin-bottom: 2px;
            }}
            .meta-value {{
                font-size: 13px;
                color: var(--foreground);
                word-break: break-all;
            }}
            .actions {{
                margin-top: 18px;
            }}
            .btn {{
                display: inline-block;
                padding: 8px 16px;
                background-color: var(--accent);
                color: #ffffff;
                text-decoration: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                margin-right: 8px;
            }}
            .btn-secondary {{
                display: inline-block;
                padding: 8px 14px;
                background-color: color-mix(in srgb, var(--foreground) 10%, var(--background));
                color: var(--foreground);
                text-decoration: none;
                border-radius: 4px;
                font-size: 12px;
                margin-right: 8px;
            }}
        </style>

        <div class="card">
            <div><span class="badge">{safe_ext} MEDIA</span></div>
            <div class="title">{safe_file_name}</div>
            <div class="subtitle">{subtitle_text}</div>

            <div class="meta-list">
                {app_row}
                <div class="meta-row">
                    <div class="meta-label">File Size</div>
                    <div class="meta-value">{safe_size}</div>
                </div>
                <div class="meta-row">
                    <div class="meta-label">Last Modified</div>
                    <div class="meta-value">{safe_modified}</div>
                </div>
                <div class="meta-row">
                    <div class="meta-label">Launched At</div>
                    <div class="meta-value">{safe_launched}</div>
                </div>
                <div class="meta-row">
                    <div class="meta-label">Full Path</div>
                    <div class="meta-value">{safe_file_path}</div>
                </div>
            </div>

            <div class="actions">
                <a class="btn" href="action:reopen?path={encoded_path}">{button_text}</a>
                <a class="btn-secondary" href="action:reveal?path={encoded_path}">Open Folder</a>
                <a class="btn-secondary" href="action:copy?path={encoded_path}">Copy Path</a>
            </div>
        </div>
    </body>
    """

def spawn_preview_tab(window, file_path):
    file_name_only = os.path.basename(file_path)
    norm_path = os.path.abspath(file_path)
    app_name = detect_default_app(file_path)

    scratch = window.new_file()
    scratch.set_name(f"Preview: {file_name_only}")
    scratch.set_scratch(True)
    scratch.set_read_only(True)
    scratch.settings().set("gutter", False)
    scratch.settings().set("line_numbers", False)
    scratch.settings().set("word_wrap", False)
    scratch.settings().set("rapscallion_bound_path", norm_path)

    ACTIVE_MEDIA_VIEWS[norm_path] = scratch.id()

    html = build_card_html(file_path, app_name)
    p_set = sublime.PhantomSet(scratch, "rapscallion_media_phantom")
    phantom = sublime.Phantom(
        sublime.Region(0, 0),
        html,
        sublime.LAYOUT_BLOCK,
        on_phantom_click
    )
    p_set.update([phantom])
    PERSISTENT_PHANTOMS[scratch.id()] = p_set
    window.focus_view(scratch)

class RapscallionOpenExternalMediaListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        try:
            if not get_setting("open_external_media_enabled", True):
                return

            file_path = view.file_name()
            if not file_path:
                return

            if view.settings().get("rapscallion_bound_path"):
                return

            extensions = get_setting("external_media_extensions", [])
            lower_name = file_path.lower()
            if not any(lower_name.endswith(ext.lower()) for ext in extensions):
                return

            window = view.window() or sublime.active_window()
            if not window:
                return
            norm_path = os.path.abspath(file_path)

            if norm_path in ACTIVE_MEDIA_VIEWS:
                target_id = ACTIVE_MEDIA_VIEWS[norm_path]
                for v in window.views():
                    if v.id() == target_id and v.is_valid():
                        view.set_scratch(True)
                        view.close()
                        window.focus_view(v)
                        if get_setting("relaunch_if_already_open", False):
                            sublime.set_timeout_async(lambda: launch_external(norm_path), 0)
                        return
                del ACTIVE_MEDIA_VIEWS[norm_path]

            view.set_scratch(True)
            view.close()

            sublime.set_timeout_async(lambda: launch_external(file_path), 0)
            sublime.set_timeout(lambda: spawn_preview_tab(window, file_path), 20)
        except Exception as e:
            print(f"[RapscallionTools] Error in media preview on_activated: {e}")

    def on_pre_close(self, view):
        try:
            vid = view.id()
            if vid in PERSISTENT_PHANTOMS:
                del PERSISTENT_PHANTOMS[vid]

            bound_path = view.settings().get("rapscallion_bound_path")
            if bound_path and bound_path in ACTIVE_MEDIA_VIEWS:
                del ACTIVE_MEDIA_VIEWS[bound_path]
            else:
                for path, registered_vid in list(ACTIVE_MEDIA_VIEWS.items()):
                    if registered_vid == vid:
                        del ACTIVE_MEDIA_VIEWS[path]
                        break
        except Exception as e:
            print(f"[RapscallionTools] Error in media preview on_pre_close: {e}")