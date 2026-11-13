import sublime
import sublime_plugin

class JumpXmlTagCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        sel = self.view.sel()
        if not sel:
            return False
        return self.view.match_selector(sel[0].b, "text.xml, embedding.xml")

    def run(self, edit):
        view = self.view
        sel = view.sel()
        if not sel:
            return

        orig_pt = sel[0].b
        if not view.match_selector(orig_pt, "text.xml, embedding.xml"):
            sublime.status_message("[RapscallionTools] Jump XML Tag only applies to XML buffers.")
            return

        # Expand selection to cover the surrounding tag/element
        view.run_command("expand_selection", {"to": "tag"})
        view.run_command("expand_selection", {"to": "tag"})

        if not view.sel():
            return
        region = view.sel()[0]
        sel.clear()

        text = view.substr(region).strip()

        # Check if selection is an empty/self-closing element (<item />)
        if text.endswith("/>"):
            target = region.begin() + 1
            sel.add(sublime.Region(target, target))
            view.show(target)
            return

        # Decide whether to jump forward to closing tag or back to opening tag
        if abs(orig_pt - region.begin()) <= abs(orig_pt - region.end()):
            slash_pos = view.substr(sublime.Region(region.begin(), region.end())).rfind("</")
            if slash_pos != -1:
                target = region.begin() + slash_pos + 2
            else:
                target = region.end()
        else:
            target = region.begin() + 1

        sel.add(sublime.Region(target, target))
        view.show(target)