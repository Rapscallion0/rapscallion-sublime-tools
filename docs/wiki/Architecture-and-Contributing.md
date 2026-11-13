# Architecture & Contributing

All packages in this repository follow the strict architectural standards defined in [`.agents/rules.md`](https://github.com/Rapscallion0/rapscallion-sublime-tools/blob/main/.agents/rules.md).

## Core Engineering Rules
1. **Python 3.8 Only**: Every Python package declares `3.8` in `.python-version`. Do not use Python 3.9+ syntax (`str.removeprefix`, `dict1 | dict2`, `list[str]` annotations, `match/case`).
2. **Zero External Dependencies**: Use only Python 3.8's standard library and `sublime` / `sublime_plugin`. Never require `pip` or PyPI packages.
3. **Strict Edit Token Rule**: Never store `edit` tokens or pass them to `sublime.set_timeout` or background threads. Asynchronous mutations must invoke a `TextCommand`.
4. **Non-Blocking I/O**: Operations taking >10ms run on daemon `threading.Thread` workers and marshal UI updates back via `sublime.set_timeout(..., 0)`.
5. **Package Isolation**: Never import Python modules across `Rapscallion*` packages; coordinate via `view.settings()`, `window.settings()`, or `run_command(...)`.
6. **HtmlSheet Lifecycle**: Side-panel `HtmlSheet` tabs use a lightweight `sublime.set_timeout` watchdog while open to collapse the split group when the user closes the tab.

## Testing & CI Pipeline

Before committing or tagging a release, run:

```powershell
# Syntax check all Python files
Get-ChildItem -Recurse -Filter "*.py" | ForEach-Object { python -m py_compile $_.FullName }

# Run unit test suites
python -m unittest discover -s RapscallionEWicParser\tests -v
python -m unittest discover -s RapscallionSILTools\tests -v
python -m unittest discover -s RapscallionMarkdown\tests -v
```

Pushing a `v*` tag (e.g. `v1.2.0`) triggers `.github/workflows/package.yml` to run all tests, build `.sublime-package` archives, and publish a GitHub Release.
