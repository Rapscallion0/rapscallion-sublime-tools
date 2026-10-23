import sublime
import sublime_plugin

class JumpToFirstMatchCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return

        # Ensure main view is focused
        self.window.focus_view(view)

        # Move cursor to point 0 (top of document) and clear selections
        view.sel().clear()
        view.sel().add(sublime.Region(0, 0))

        # Search forward from position 0
        view.run_command("find_next")