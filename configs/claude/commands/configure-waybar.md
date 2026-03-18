Run a Costa OS Waybar configuration helper.

Follow these steps:

1. Read the customization knowledge file via MCP resource `costa://knowledge/customization` to understand the Waybar template system and available modules.

2. Read the current Waybar configuration:
   - `~/.config/waybar/config.jsonc` — module layout and settings
   - `~/.config/waybar/style.css` — module styling

3. Also check for any Waybar templates in `~/.config/waybar/templates/` that define reusable module configurations.

4. Present the current module layout to the user (which modules are on which bar, left/center/right positioning).

5. Ask the user what they want to change:
   - Add a new module (suggest available ones)
   - Remove an existing module
   - Modify a module's settings or appearance
   - Rearrange module positions
   - Change bar-level settings (height, position, output monitor)

6. Apply the requested changes to the config and style files.

7. Restart Waybar to apply:
   ```
   killall waybar; waybar &disown
   ```

8. Ask the user to confirm the changes look correct. If not, iterate.

Use the costa-system MCP tools where available. Read relevant knowledge files via MCP resources before making changes.
