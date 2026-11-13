# Troubleshooting & FAQ

### A `Ctrl+Alt+<Key>` chord types a character instead of running the command
- **Cause**: Another binding in `Packages/User/Default (Windows).sublime-keymap` uses that same prefix as a single-key shortcut (User bindings always override package keymaps).
- **Fix**: Open **Preferences > Key Bindings** and remove or remap the conflicting single-key binding.

### A newly installed package's commands or shortcuts don't work
- **Cause**: Sublime Text 4 may have initially loaded the package in the legacy Python 3.3 host if `.python-version` wasn't read yet.
- **Fix**: Restart Sublime Text 4 once so it initializes the package in the Python 3.8 host.

### `RapscallionMarkdown` side-panel preview doesn't scroll-sync
- **Cause**: Sublime Text 4's `HtmlSheet` API does not expose scroll positions or `scrollIntoView` JavaScript.
- **Fix**: Use the **Live Browser Preview (`Ctrl+Alt+M, B`)**, which supports smooth cursor-line sync scrolling and two-way checkbox toggling.

### Windows `install.ps1` fails to create directory junctions
- **Cause**: Destination folder already exists as a real directory, or Sublime Text has a lock on a file.
- **Fix**: Run `.\install.ps1 -All -Uninstall` first (or remove the conflicting folder in `%APPDATA%\Sublime Text\Packages`), then re-run `.\install.ps1 -All`.

### Checking for Plugin Errors
Open the Sublime Text console (**``Ctrl+` ``**) and look for prefixed log lines such as `[RapscallionMarkdown] ...` or `[RapscallionBookmarks] ...`.
