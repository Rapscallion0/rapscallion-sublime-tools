import sublime
import sublime_plugin
from datetime import datetime, timezone

class InsertTimestampCommand(sublime_plugin.TextCommand):
    def run(self, edit, format="%Y-%m-%d %H:%M:%S", utc=False):
        try:
            now = datetime.now(timezone.utc) if (utc or format.endswith("Z")) else datetime.now()
            stamp = now.strftime(format)
        except ValueError as e:
            sublime.status_message(f"[RapscallionTools] Invalid timestamp format: {e}")
            return
        for region in self.view.sel():
            if region.empty():
                self.view.insert(edit, region.b, stamp)
            else:
                self.view.replace(edit, region, stamp)