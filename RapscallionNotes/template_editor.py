import os
import sublime
import sublime_plugin

SETTINGS_FILE = "RapscallionNotes.sublime-settings"
DEFAULT_FALLBACK_TEMPLATE = (
    "# ${folder_name}\n"
    "Date Created: ${date} ${time}\n"
    "Author: ${user}\n\n"
    "Notes:\n\n"
)


class EditRapscallionTemplateCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings(SETTINGS_FILE)
        rules = settings.get("notes_path_rules", [])
        default_sub = (settings.get("notes_subfolder", ".sublime") or "").strip()
        default_fn = (settings.get("notes_default_filename", ".notes.md") or ".notes.md").strip()
        default_tmpl = settings.get("notes_default_template") or DEFAULT_FALLBACK_TEMPLATE

        self.options = [
            {
                "action": "edit",
                "type": "default",
                "title": "Default Template",
                "desc": f"Global fallback ({os.path.join(default_sub, default_fn) if default_sub else default_fn})",
                "template": default_tmpl
            },
            {
                "action": "create",
                "title": "[+] Add New Path Rule",
                "desc": "Bind a directory path to a custom filename, subfolder, and template"
            }
        ]

        for idx, rule in enumerate(rules):
            prefix = rule.get("path_prefix", f"Rule #{idx + 1}")
            fn = (rule.get("filename") or default_fn).strip()
            sub = (rule.get("subfolder") if "subfolder" in rule else default_sub) or ""
            sub = sub.strip()
            rel_path = f"{sub}/{fn}" if sub else fn
            self.options.append({
                "action": "edit",
                "type": "rule",
                "index": idx,
                "title": f"Rule: {prefix}",
                "desc": f"Note target: {rel_path}",
                "template": rule.get("template") or default_tmpl
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
        folders = self.window.folders()
        initial_path = folders[0] if folders else ""
        self.window.show_input_panel(
            "Folder Path Prefix (e.g. D:\\_Calls or D:\\Projects):",
            initial_path,
            self.on_path_entered,
            None,
            None
        )

    def on_path_entered(self, path):
        path = path.strip()
        if not path:
            return

        self._new_rule_path = path
        settings = sublime.load_settings(SETTINGS_FILE)
        default_fn = (settings.get("notes_default_filename", ".notes.md") or ".notes.md").strip()

        self.window.show_input_panel(
            "Note Filename (e.g. .notes.md, NOTES.md):",
            default_fn,
            self.on_filename_entered,
            None,
            None
        )

    def on_filename_entered(self, filename):
        settings = sublime.load_settings(SETTINGS_FILE)
        default_fn = (settings.get("notes_default_filename", ".notes.md") or ".notes.md").strip()
        self._new_rule_filename = filename.strip() or default_fn

        default_sub = (settings.get("notes_subfolder", ".sublime") or "").strip()
        self.window.show_input_panel(
            "Note Subfolder (e.g. .sublime, docs, or leave blank for folder root):",
            default_sub,
            self.on_subfolder_entered,
            None,
            None
        )

    def on_subfolder_entered(self, subfolder):
        settings = sublime.load_settings(SETTINGS_FILE)
        rules = settings.get("notes_path_rules", [])
        default_tmpl = settings.get("notes_default_template") or DEFAULT_FALLBACK_TEMPLATE

        new_rule = {
            "path_prefix": self._new_rule_path,
            "filename": self._new_rule_filename,
            "subfolder": subfolder.strip(),
            "template": default_tmpl
        }
        rules.append(new_rule)
        settings.set("notes_path_rules", rules)
        sublime.save_settings(SETTINGS_FILE)

        new_index = len(rules) - 1
        self.open_template_buffer({
            "type": "rule",
            "index": new_index,
            "title": f"Rule: {self._new_rule_path}",
            "template": new_rule["template"]
        })

    def open_template_buffer(self, selected):
        target_name = f"Edit Template: {selected['title']}"
        for v in self.window.views():
            if v.settings().get("is_rapscallion_template_buffer") and v.name() == target_name:
                self.window.focus_view(v)
                return

        view = self.window.new_file()
        view.set_name(target_name)
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
                if isinstance(index, int) and 0 <= index < len(rules):
                    rules[index]["template"] = content
                    settings.set("notes_path_rules", rules)
                    sublime.save_settings(SETTINGS_FILE)
                    sublime.status_message("Rapscallion Tools: Notes - Rule template updated.")
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
