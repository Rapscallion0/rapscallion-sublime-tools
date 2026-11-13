# RapscallionMarkdown

Zero-dependency live Markdown viewer and editor for Sublime Text 4, offering both an in-editor `minihtml` side panel and a real-time localhost SSE browser preview.

## Key Features
- **In-Editor Side-Panel Preview (`HtmlSheet`)**: Theme-aware rendering using ST4 CSS variables (`var(--background)`, `var(--foreground)`, `color-mix`), clickable `[ ]` / `[x]` task checkboxes that mutate the `.md` buffer, clickable headings that jump the editor cursor, and active-block cursor highlighting.
- **Live Browser Preview (`ThreadingHTTPServer` + SSE)**: Spins up a zero-dependency server on `127.0.0.1:0` pushing live DOM updates via Server-Sent Events (`/events`) with no page reloads.
  - Auto / Light / Dark theme toggle
  - Smooth cursor-line **Sync Scroll** & active-line highlight
  - Copy-code buttons & two-way task checkbox toggling
  - Safe local relative asset serving (`/asset`) scoped to the document/project root
- **Auto Layout Cleanup**: Closing the side-panel preview tab (via `Ctrl+W` or mouse `×`) automatically collapses the split group.

## Commands & Shortcuts

| Action | Command Palette (`Ctrl+Shift+P`) | Chord |
| :--- | :--- | :--- |
| Toggle Side Panel Preview | `Raps: Markdown - Toggle Side Panel Preview` | `Ctrl+Alt+M, P` |
| Open Live Browser Preview | `Raps: Markdown - Open Live Browser Preview` | `Ctrl+Alt+M, B` |
| Stop Live Browser Server | `Raps: Markdown - Stop Live Browser Server` | `Ctrl+Alt+M, X` |

## Settings (`RapscallionMarkdown.sublime-settings`)

```json
{
    "preview_panel_side": "right",
    "preview_panel_width": 0.45,
    "live_preview_debounce_ms": 150,
    "browser_sync_scroll": true,
    "highlight_cursor_line": true
}
```
