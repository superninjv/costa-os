import { execAsync } from "ags/process"

export default function Claude() {
  return (
    <button
      class="claude"
      onClicked={() =>
        execAsync("ghostty -e zsh -lc 'cd ~ && claude'").catch(() => {})
      }
      tooltipText="Open Claude Code"
    >
      <label label="🤖" />
    </button>
  )
}
