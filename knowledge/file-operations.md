---
l0: "File operations: finding files (fd, rg, fzf), opening, copying, bulk operations, project paths"
l1_sections: ["CRITICAL RULES", "Finding Files", "Opening Files", "File Management", "Bulk Operations", "Project-Specific Paths", "Tools Available"]
tags: [file, find, search, locate, open, copy, move, delete, rename, fd, ripgrep, fzf, disk-usage]
---

# File Operations

## CRITICAL RULES
- **NEVER create files when the user asks to FIND a file.** "Find", "where is", "locate", "search for" = use search commands below.
- **NEVER create files when the user asks to OPEN a file.** Find it first, then open it.
- Only create a file if the user explicitly says "create", "make", "write", or "new file".

## Finding Files
- By name: `fd filename` (fast, respects .gitignore) or `find / -name "filename" 2>/dev/null`
- By extension: `fd -e css`, `fd -e py ~/projects`
- By content: `rg "search term"` (ripgrep — fast recursive content search)
- By content in specific dir: `rg "search term" ~/projects/myproject`
- By content with file type: `rg -t py "import torch"`, `rg -t css "animation"`
- Fuzzy find: `fzf` (interactive), `fd | fzf` (find + fuzzy filter)
- Locate (if installed): `locate filename` (uses database, run `sudo updatedb` first)
- Recently modified: `fd --changed-within 1h`, `find . -mmin -60`
- Large files: `dust` (visual disk usage), `du -sh * | sort -rh | head -20`

## Opening Files
- Text editor: `code filename` (VS Code), `$EDITOR filename`
- File manager: `thunar /path/to/dir`
- Open with default app: `xdg-open filename`
- Images: `imv filename` or `xdg-open filename`

## File Management
- Copy: `cp src dst`, recursive: `cp -r src/ dst/`
- Move/rename: `mv old new`
- Delete: `rm file`, directory: `rm -r dir/` (USE WITH CAUTION)
- Create directory: `mkdir -p path/to/dir`
- Symlink: `ln -s target linkname`
- Permissions: `chmod 755 file`, ownership: `chown user:group file`
- Disk usage of directory: `dust /path` or `du -sh /path`
- Tree view: `eza --tree --level=3`

## Bulk Operations
- Rename multiple: `rename 's/old/new/' *.ext` (perl-rename)
- Find and delete: `fd -e tmp -x rm {}`
- Find and move: `fd -e log -x mv {} /tmp/logs/`
- Batch content replace: `sd 'old' 'new' file` or `rg -l "old" | xargs sd 'old' 'new'`

## Project-Specific Paths
- User projects: `~/projects/`
- Config files: `~/.config/`
- Costa OS configs: `~/.config/costa/`, `~/.config/hypr/`, `~/.config/waybar/`
- Screenshots: `~/Pictures/Screenshots/`
- Downloads: `~/Downloads/`

## Tools Available
- `fd` — fast find alternative (respects .gitignore, regex support)
- `rg` (ripgrep) — fast content search
- `fzf` — fuzzy finder
- `eza` — modern ls with tree view
- `dust` — visual disk usage
- `bat` — cat with syntax highlighting
- `sd` — sed alternative for find-and-replace
- `tokei` — code statistics
