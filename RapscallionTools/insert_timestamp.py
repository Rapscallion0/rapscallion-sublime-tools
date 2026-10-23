import sublime
import sublime_plugin
from datetime import datetime

class InsertTimestampCommand(sublime_plugin.TextCommand):
    def run(self, edit, format="%Y-%m-%d %H:%M:%S"):
        stamp = datetime.now().strftime(format)
        for region in self.view.sel():
            if region.empty():
                self.view.insert(edit, region.b, stamp)
            else:
                self.view.replace(edit, region, stamp)