# Installation & Setup

## Prerequisites
- **Sublime Text 4** (Build 4100+ recommended for `HtmlSheet` and Python 3.8 plugin host support).
- **Windows PowerShell** (for `install.ps1` automated linking).

---

## Method 1: Automated Installer (`install.ps1`) — Recommended

From the repository root:

```powershell
# Interactive selection menu
.\install.ps1

# Install all packages using live NTFS directory junctions (edits reflect immediately)
.\install.ps1 -All

# Install specific packages only
.\install.ps1 -Packages RapscallionBookmarks,RapscallionMarkdown

# Install via standalone copy (independent of the git repo)
.\install.ps1 -All -Mode Copy

# Uninstall all packages
.\install.ps1 -All -Uninstall
```

> [!NOTE]
> `install.ps1` discovers packages by scanning for `Rapscallion*` directories containing a `README.md`.

---

## Method 2: Manual Installation

1. In Sublime Text 4, open **Preferences > Browse Packages...** (typically `%APPDATA%\Sublime Text\Packages`).
2. Copy any `Rapscallion*` folder from this repository directly into `Packages`.
3. Sublime Text loads the package automatically.

---

## Method 3: Pre-built `.sublime-package` Archives

1. Download the desired `<PackageName>.sublime-package` from [GitHub Releases](https://github.com/Rapscallion0/rapscallion-sublime-tools/releases).
2. Place the file into `%APPDATA%\Sublime Text\Installed Packages`.

---

## Verifying the Python 3.8 Host

All Python-based `Rapscallion*` packages include a `.python-version` file containing `3.8`. If a package ever fails to load on first install, restart Sublime Text 4 once so the plugin host initializes it in Python 3.8 rather than the legacy Python 3.3 host.
