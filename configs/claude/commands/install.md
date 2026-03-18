Run a Costa OS smart package install for: $ARGUMENTS

Follow these steps to install the requested package:

1. Check if the package is already installed:
   ```
   pacman -Qi $ARGUMENTS
   ```
   If it is already installed, report the installed version and stop.

2. Search official Arch repos:
   ```
   pacman -Ss $ARGUMENTS
   ```

3. If found in official repos, install it:
   ```
   sudo pacman -S --noconfirm <exact-package-name>
   ```
   Report success and stop.

4. If not found in official repos, search the AUR:
   ```
   yay -Ss $ARGUMENTS
   ```

5. If found in the AUR, install it:
   ```
   yay -S --noconfirm <exact-package-name>
   ```
   Report success and stop.

6. If not found anywhere, tell the user the package was not found and suggest similar package names from the search results if any were close matches.

Always use the exact package name from search results when installing, not the user's search term (which may be a partial match).

Use the costa-system MCP tools where available.
