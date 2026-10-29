# Rapscallion Tools - Bookmarks

Dedicated panel, rapid-cycling navigation, and persistent bookmark manager for Sublime Text 4.

---

## Features

* **Instant One-Key Toggle (`Ctrl + F2`):** Instantly add or remove a bookmark at the cursor without modal input interruptions. Uses selected text or line preview as default label.
* **Named & Categorized Bookmarks (`Ctrl + Shift + F2`):** Prompt dialog to set a custom title or tag (e.g. `#bug`, `[todo]`, or custom categories).
* **Rapid Next / Previous Cycling (`F2` / `Shift + F2`):** Step sequentially through bookmarks in the current file with automatic wrap-around. Use `Alt + F2` / `Alt + Shift + F2` to cycle across the entire project.
* **Smooth, Non-Jarring Quick Palette (`Alt + B`):** Instant fuzzy-searchable palette. Automatically selects the bookmark nearest to your cursor and suppresses synthetic jumping on launch, while supporting live scrolling preview as you navigate items.
* **Visual Flash Highlighting & Centered Focus:** Jumping to any bookmark briefly flashes the bookmarked line with a distinct highlight and ensures it is centered cleanly in view, even across asynchronously loaded files.
* **Right-Click Context Menu:** Full editor context menu with submenus (`Rapscallion Bookmarks ▶`) for toggling, named creation, cycling, palette/dock access, bulk clearing, and markdown export.
* **Dynamic Line-Drift Tracking:** Automatically tracks bookmarks using persistent regions during edits and syncs updated line/column positions back to storage upon save (`Ctrl + S`).
* **Custom Categories & Scopes:** Built-in and user-definable categories (`todo`, `bug`, `review`, `note`, or freeform tags) with custom gutter icons and Sublime color scopes (`region.redish`, `region.yellowish`, `region.bluish`, `region.purplish`).
* **Dedicated Bottom Dock Panel (`Alt + Shift + B`):** Slide-up output panel integrated with Sublime Text's native output tray. Press `Enter` to jump, `r` to rename, `t` to assign categories/tags, `Del` to delete, and `F5` to refresh. Closes immediately with `Esc`.
* **Optional Right Side Dock Panel (`rapscallion_toggle_side_panel`):** Dedicated split-column HTML panel preserving multi-column layouts when toggled, restoring your exact workspace on close. Set `"panel_mode": "side_dock"` in settings to make `Alt + Shift + B` toggle the side dock by default.
* **Gutter Hover Popup:** Hovering your mouse over any gutter bookmark badge shows a mini-HTML popup with line preview and one-click `[Jump]`, `[Rename]`, and `[Delete]` links.
* **Status Bar Indicator:** Displays the bookmark title and category badge in the bottom status bar whenever your cursor rests on a bookmarked line.
* **Project & Global Persistence:** Bookmarks are saved under your project root at `.sublime/RapscallionBooks.json`. Standalone files outside projects automatically fall back to `Packages/User/RapscallionBookmarks.global.json`.
* **Export to Markdown:** Export project bookmarks to a clean GitHub-flavored checklist copied to clipboard and opened in a scratch buffer.

---

## Key Bindings

| Shortcut | Context | Command | Description |
|---|---|---|---|
| `Ctrl + F2` | Text View | `rapscallion_toggle_bookmark` | Instant bookmark toggle (add/remove) |
| `Ctrl + Shift + F2` | Text View | `rapscallion_set_named_bookmark` | Add or edit bookmark with custom name/tag |
| `F2` | Text View | `rapscallion_next_bookmark` | Jump to next bookmark in active file |
| `Shift + F2` | Text View | `rapscallion_prev_bookmark` | Jump to previous bookmark in active file |
| `Alt + F2` | Global | `rapscallion_next_project_bookmark` | Jump to next bookmark across project |
| `Alt + Shift + F2` | Global | `rapscallion_prev_project_bookmark` | Jump to previous bookmark across project |
| `Alt + B` | Global | `rapscallion_quick_bookmarks` | Open Quick Palette with smooth live preview |
| `Alt + Shift + B` | Global | `rapscallion_toggle_panel` | Toggle panel (respects `panel_mode` setting) |
| `Enter` | Bottom Panel | `rapscallion_panel_jump` | Jump to bookmark under cursor |
| `r` | Bottom Panel | `rapscallion_panel_rename` | Rename bookmark under cursor |
| `t` | Bottom Panel | `rapscallion_panel_set_tag` | Set or change category/tag under cursor |
| `Del` | Bottom Panel | `rapscallion_panel_delete` | Delete bookmark under cursor |
| `F5` | Bottom Panel | `rapscallion_refresh_panel` | Refresh bookmark panel |
| `Esc` | Bottom Panel | Native | Close bottom dock panel |

---

## Editor Context Menu

Right-click anywhere inside the editor view to access the **Rapscallion Bookmarks** submenu:

```text
Rapscallion Bookmarks ▶
    Toggle Bookmark
    Add Named Bookmark…
    ------------------------------
    Next Bookmark
    Previous Bookmark
    ------------------------------
    Quick Search Palette…
    Toggle Bottom Dock Panel
    Toggle Right Side Panel
    ------------------------------
    Clear Bookmarks in This File
    Clear All Bookmarks in Project…
    ------------------------------
    Export Bookmarks to Markdown
```

---

## Configuration

Settings can be customized via **Preferences > Package Settings > Rapscallion Tools > Bookmarks > Settings** or by editing `Packages/User/RapscallionBookmarks.sublime-settings`:

```json
{
  // Live scrolling preview in Quick Panel (Alt+B)
  "quick_panel_preview": true,

  // Prevents jarring jump to the first bookmark upon opening Quick Panel
  "quick_panel_preview_on_open": false,

  // Flash highlight line when navigating to a bookmark
  "flash_jump": true,
  "flash_scope": "region.yellowish",
  "flash_duration_ms": 700,

  // Show bookmark title in Sublime status bar when cursor is on a bookmarked line
  "status_bar_indicator": true,

  // Show hover popup when hovering over gutter icons
  "gutter_hover_popup": true,

  // Custom categories and visual scopes for bookmarks
  "categories": {
    "todo": {
      "scope": "region.yellowish",
      "icon": "bookmark",
      "label": "TODO"
    },
    "bug": {
      "scope": "region.redish",
      "icon": "dot",
      "label": "Bug / Issue"
    },
    "review": {
      "scope": "region.purplish",
      "icon": "bookmark",
      "label": "Review"
    },
    "note": {
      "scope": "region.bluish",
      "icon": "circle",
      "label": "Note"
    }
  },
  "default_category_scope": "region.yellowish",
  "default_category_icon": "bookmark",

  // Default panel mode: "bottom_panel" (native dock) or "side_dock" (split column)
  "panel_mode": "bottom_panel",

  // Side dock preferences (if using side panel)
  "side": "right",
  "panel_width": 0.22,
  "remember_panel_width": true,
  "min_panel_ratio": 0.12
}
```

---

## Installation

### Automated (PowerShell)
From the repository root, run:
```powershell
.\install.ps1 -Packages RapscallionBookmarks
```

### Manual
Copy this `RapscallionBookmarks` folder into your Sublime Text Packages directory (accessible via **Preferences > Browse Packages...**).
