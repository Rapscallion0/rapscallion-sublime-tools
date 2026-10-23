import sublime
import sublime_plugin

SIL_SYNTAX = "Packages/RapscallionSILTools/SIL (Rainbow).sublime-syntax"
LEGACY_SYNTAX = "Packages/SILTools/SIL (Rainbow).sublime-syntax"


def plugin_loaded():
    """Migrates any open buffers still pointing to the legacy SILTools syntax path."""
    for window in sublime.windows():
        for view in window.views():
            cur_syntax = view.settings().get("syntax")
            if cur_syntax == LEGACY_SYNTAX:
                view.assign_syntax(SIL_SYNTAX)
            elif cur_syntax != SIL_SYNTAX:
                try:
                    sample = view.substr(sublime.Region(0, min(view.size(), 256))).lstrip()
                    if sample.upper().startswith("@CREATE("):
                        view.assign_syntax(SIL_SYNTAX)
                except Exception:
                    pass


class AutoSilSyntaxDetector(sublime_plugin.EventListener):
    """Automatically assigns SIL (Rainbow) syntax for .sil files or buffers starting with @CREATE("""

    def on_load(self, view):
        self.check_and_assign(view)

    def on_post_save(self, view):
        self.check_and_assign(view)

    def on_activated(self, view):
        self.check_and_assign(view)

    def check_and_assign(self, view):
        if not view or not view.is_valid():
            return

        try:
            cur_syntax = view.settings().get("syntax")

            # Immediately migrate any legacy package path
            if cur_syntax == LEGACY_SYNTAX:
                view.assign_syntax(SIL_SYNTAX)
                return

            # Check if buffer is already SIL
            if cur_syntax == SIL_SYNTAX:
                return

            fname = view.file_name()
            if fname and fname.lower().endswith(".sil"):
                view.assign_syntax(SIL_SYNTAX)
                return

            sample = view.substr(sublime.Region(0, min(view.size(), 256))).lstrip()
            if sample.upper().startswith("@CREATE("):
                view.assign_syntax(SIL_SYNTAX)
        except Exception as e:
            print(f"[Rapscallion Tools: SIL] Error in AutoSilSyntaxDetector: {e}")


class SilShowDocsCommand(sublime_plugin.WindowCommand):
    """Opens the package README directly inside Sublime Text."""

    def run(self):
        self.window.run_command("open_file", {
            "file": "${packages}/RapscallionSILTools/README.md"
        })
