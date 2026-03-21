import { createState } from "gnim"
import { execAsync } from "ags/process"
import GLib from "gi://GLib"

interface SystemIssues {
  count: number
  details: string[]
}

const [getIssues, setIssues] = createState<SystemIssues>({ count: 0, details: [] })

function checkIssues() {
  const details: string[] = []
  let pending = 3

  function done() {
    pending--
    if (pending === 0) {
      setIssues({ count: details.length, details })
    }
  }

  execAsync("bash -c 'systemctl --user --failed --no-legend | wc -l'")
    .then((out) => {
      const n = parseInt(out.trim())
      if (n > 0) details.push(`${n} failed service(s)`)
    })
    .catch(() => {})
    .finally(done)

  try {
    const [ok, contents] = GLib.file_get_contents("/proc/loadavg")
    if (ok && contents) {
      const load = parseFloat(new TextDecoder().decode(contents).split(" ")[0])
      if (load > 8) details.push(`Load: ${load.toFixed(1)}`)
    }
  } catch {}

  execAsync("bash -c \"df / --output=pcent | tail -1 | tr -d ' %'\"")
    .then((out) => {
      const pct = parseInt(out.trim())
      if (pct > 90) details.push(`Disk: ${pct}%`)
    })
    .catch(() => {})
    .finally(done)

  // Account for the sync load check
  done()
}

checkIssues()
GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60000, () => {
  checkIssues()
  return GLib.SOURCE_CONTINUE
})

export default function Troubleshoot() {
  return (
    <box
      class="troubleshoot"
      visible={getIssues.as(i => i.count > 0)}
    >
      <label
        label="⚠"
        class="trouble-icon"
        tooltipText={getIssues.as(i => i.details.join("\n"))}
      />
    </box>
  )
}
