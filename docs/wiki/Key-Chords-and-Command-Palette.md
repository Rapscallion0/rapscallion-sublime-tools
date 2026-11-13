# Key Chords & Command Palette

Every package registers commands in the Sublime Command Palette (`Ctrl+Shift+P`) using the format:

```text
Raps: <Tool> - <Descriptive Action>
```

Each package also uses a dedicated **`Ctrl+Alt+<Letter>`** two-key chord prefix so shortcuts stay memorable and conflict-free.

---

## Master Chord Prefix Map

| Prefix | Package | Actions |
| :--- | :--- | :--- |
| **`Ctrl+Alt+B`** | **RapscallionBookmarks** | `T` Toggle · `N` Named · `Q` Quick Panel · `P` Bottom Panel · `C` Clear File · `E` Export MD |
| **`Ctrl+Alt+H`** | **RapscallionTools (Hex)** | `B` Brace In-Place · `T` Brace to Tab · `A` All Formats In-Place · `N` All Formats to Tab |
| **`Ctrl+Alt+I`** | **RapscallionSILTools** | `Q` SQLite Query · `F` Frequency · `G` Go to Column · `A` Align · `S` Scratchpad · `P` Presets · `R` Format · `H` Hover · `D` Docs |
| **`Ctrl+Alt+M`** | **RapscallionMarkdown** | `P` Side Panel Preview · `B` Live Browser Preview · `X` Stop Browser Server |
| **`Ctrl+Alt+N`** | **RapscallionNotes** | `C` / `N` Create or Open Note · `T` Edit Template |
| **`Ctrl+Alt+U`** | **RapscallionTools (Utils)** | `T` Full Timestamp · `D` Date · `H` Time · `I` ISO UTC · `X` Jump XML Tag · `M` First Match · `S` Status Bar · `P` Status Details |
| **`Ctrl+Alt+W`** | **RapscallionEWicParser** | `S` Parse Selection · `I` Analyze ID · `A` Audit Log · `B` View in Browser · `D` Output Dest · `L` Load APL · `C` Clear APL Cache |
| **`Ctrl+Alt+Z`** | **RapscallionZip** | `F` Filter Archive Tree · `C` Clear Extracted Cache |

---

## Resolving `User` Keymap Conflicts

Sublime Text gives `Packages/User/Default (Windows).sublime-keymap` higher priority than package keymaps. If you have a single-key binding like `ctrl+alt+m` in your `User` keymap, it will fire immediately instead of waiting for the second key in a chord. Remove or remap the conflicting `User` binding, or customize any package shortcut via **Raps: &lt;Tool&gt; - Key Bindings**.
