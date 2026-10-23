# Rapscallion Tools - Bookmarks

Dedicated panel and quick-navigation bookmark manager for Sublime Text 4.

---

## Features

* **Floating Quick Panel (`Alt + B`):** Instant fuzzy-searchable bookmark palette with real-time scrolling preview as you navigate items before pressing `Enter`.
* **Dedicated Bottom Panel (`Alt + Shift + B`):** Slide-up dock panel integrated with Sublime Text's native output tray. Zero extra tab groups, zero window layout disruption, and closes immediately with `Esc`.
* **Native Jump Navigation:** Double-click or press `Enter` on any bookmark in the panel to jump directly to file, line, and column.
* **Inline Panel Actions:** Press `r` to rename, `Del` to delete, or `F5` to refresh directly from the bottom panel.
* **In-Editor Gutter Badges:** Bookmarked lines display visual bookmark indicators in the gutter.
* **Project-Level Persistence:** Bookmarks are saved automatically under your project root at `.sublime/RapscallionBooks.json`.
* **Optional Side Panel:** Preserves multi-column editor layouts when toggled, restoring your exact workspace upon close.

---

## Key Bindings

| Shortcut | Context | Command | Description |
|---|---|---|---|
| `Alt + B` | Global | `rapscallion_quick_bookmarks` | Open Quick Panel with live preview |
| `Alt + Shift + B` | Global | `rapscallion_toggle_panel` | Toggle dedicated bottom dock panel |
| `Ctrl + F2` | Text View | `rapscallion_set_bookmark` | Add or edit bookmark at cursor |
| `Enter` | Bottom Panel | `rapscallion_panel_jump` | Jump to bookmark under cursor |
| `r` | Bottom Panel | `rapscallion_panel_rename` | Rename bookmark under cursor |
| `Del` | Bottom Panel | `rapscallion_panel_delete` | Delete bookmark under cursor |
| `F5` | Bottom Panel | `rapscallion_refresh_panel` | Refresh bookmark panel |
| `Esc` | Bottom Panel | Native | Close bottom panel |

---

## Configuration

Settings can be customized via **Preferences > Package Settings > Rapscallion Tools > Bookmarks > Settings** or by editing `Packages/User/RapscallionBookmarks.sublime-settings`:

```json
{
    // Live scrolling preview in Quick Panel (Alt+B)
    "quick_panel_preview": true,

    // Default panel display mode: "bottom_panel" or "side_dock"
    "panel_mode": "bottom_panel",

    // Side dock preferences (if using optional side panel)
    "side": "right",
    "panel_width": 0.22,
    "remember_panel_width": true,
    "min_panel_ratio": 0.12
}
```
