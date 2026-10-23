import sublime
import sublime_plugin

SETTINGS_FILE = "RapscallionNotes.sublime-settings"

class EditRapscallionTemplateCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings(SETTINGS_FILE)
        rules = settings.get("notes_path_rules", [])

        self.options = [
            {
                "action": "edit",
                "type": "default",
                "title": "Default Template",
                "desc": "Global fallback when no specific path rule matches",
                "template": settings.get("notes_default_template", "")
            },
            {
                "action": "create",
                "title": "[+] Add New Path Rule",
                "desc": "Bind a new directory path to a custom template"
            }
        ]

        for idx, rule in enumerate(rules):
            prefix = rule.get("path_prefix", f"Rule #{idx + 1}")
            self.options.append({
                "action": "edit",
                "type": "rule",
                "index": idx,
                "title": f"Rule: {prefix}",
                "desc": f"Matches any folder inside '{prefix}'",
                "template": rule.get("template", "")
            })

        panel_items = [[opt["title"], opt["desc"]] for opt in self.options]
        self.window.show_quick_panel(panel_items, self.on_select)

    def on_select(self, index):
        if index < 0:
            return

        selected = self.options[index]

        if selected["action"] == "create":
            self.prompt_for_new_path()
        else:
            self.open_template_buffer(selected)

    def prompt_for_new_path(self):
        self.window.show_input_panel(
            "Folder Path Prefix (e.g. D:\\_Calls):",
            "",
            self.on_path_entered,
            None,
            None
        )

    def on_path_entered(self, path):
        path = path.strip()
        if not path:
            return

        settings = sublime.load_settings(SETTINGS_FILE)
        rules = settings.get("notes_path_rules", [])

        new_rule = {
            "path_prefix": path,
            "filename": ".notes.md",
            "template": "Ticket#: ${ticket_number}\nDate Created:${date} ${time}\nAssigned TAC:${tac_name}\n\nNotes:\n\n"
        }
        rules.append(new_rule)
        settings.set("notes_path_rules", rules)
        sublime.save_settings(SETTINGS_FILE)

        new_index = len(rules) - 1
        self.open_template_buffer({
            "type": "rule",
            "index": new_index,
            "title": f"Rule: {path}",
            "template": new_rule["template"]
        })

    def open_template_buffer(self, selected):
        view = self.window.new_file()
        view.set_name(f"Edit Template: {selected['title']}")
        view.set_scratch(True)

        syntax = sublime.find_syntax_by_name("Markdown")
        if syntax:
            view.assign_syntax(syntax[0])

        view.settings().set("is_rapscallion_template_buffer", True)
        view.settings().set("template_target_type", selected["type"])
        if selected["type"] == "rule":
            view.settings().set("template_target_index", selected["index"])

        view.run_command("append", {"characters": selected["template"]})


class SaveRapscallionTemplateListener(sublime_plugin.EventListener):
    def commit_template(self, view):
        try:
            settings = sublime.load_settings(SETTINGS_FILE)
            content = view.substr(sublime.Region(0, view.size()))
            target_type = view.settings().get("template_target_type")

            if target_type == "default":
                settings.set("notes_default_template", content)
                sublime.save_settings(SETTINGS_FILE)
                sublime.status_message("Rapscallion Tools: Notes - Default template updated.")
                view.set_scratch(True)

            elif target_type == "rule":
                index = view.settings().get("template_target_index")
                rules = settings.get("notes_path_rules", [])
                if 0 <= index < len(rules):
                    rules[index]["template"] = content
                    settings.set("notes_path_rules", rules)
                    sublime.save_settings(SETTINGS_FILE)
                    sublime.status_message(f"Rapscallion Tools: Notes - Rule template updated.")
                    view.set_scratch(True)
        except Exception as e:
            print(f"[Rapscallion Tools: Notes] Failed to commit template: {e}")

    def on_text_command(self, view, command_name, args):
        try:
            if command_name == "save" and view.settings().get("is_rapscallion_template_buffer"):
                self.commit_template(view)
                return ("noop", None)
        except Exception as e:
            print(f"[Rapscallion Tools: Notes] Error in on_text_command: {e}")
        return None