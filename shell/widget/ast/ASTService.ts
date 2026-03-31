import Gio from "gi://Gio"
import GLib from "gi://GLib"
import { createState } from "gnim"

// D-Bus proxy for org.costa.AST
// Provides tree-sitter code intelligence to AGS widgets.
// Mirrors AirPodsService.ts pattern: bus watching, property sync, reactive state.

const BUS_NAME = "org.costa.AST"
const OBJECT_PATH = "/org/costa/AST"
const IFACE_NAME = "org.costa.AST"

export interface ASTState {
  available: boolean
  parsedFiles: number
  watchedDirs: string[]
  supportedLanguages: string[]
}

const DEFAULT_STATE: ASTState = {
  available: false,
  parsedFiles: 0,
  watchedDirs: [],
  supportedLanguages: [],
}

const [getState, setState] = createState<ASTState>({ ...DEFAULT_STATE })
export { getState }

let proxy: Gio.DBusProxy | null = null

function unpackVariant(v: GLib.Variant): any {
  if (!v) return null
  return v.deepUnpack()
}

function getProperty(name: string): any {
  if (!proxy) return null
  const v = proxy.get_cached_property(name)
  return v ? unpackVariant(v) : null
}

function readAllProperties(): Partial<ASTState> {
  return {
    parsedFiles: getProperty("ParsedFiles") ?? 0,
    watchedDirs: getProperty("WatchedDirs") ?? [],
    supportedLanguages: getProperty("SupportedLanguages") ?? [],
  }
}

function syncState() {
  if (!proxy) {
    setState({ ...DEFAULT_STATE })
    return
  }
  const props = readAllProperties()
  setState({ ...DEFAULT_STATE, available: true, ...props })
}

// Signal listeners
const signalHandlers: number[] = []

// Callbacks for file change events (set by consumers)
let onFileChanged: (path: string, changeType: string) => void = () => {}
let onSymbolsUpdated: (path: string) => void = () => {}

export function setChangeCallbacks(
  onFile: (path: string, changeType: string) => void,
  onSymbols: (path: string) => void,
) {
  onFileChanged = onFile
  onSymbolsUpdated = onSymbols
}

function connectProxy() {
  if (proxy) {
    signalHandlers.forEach((id) => proxy!.disconnect(id))
    signalHandlers.length = 0
  }

  try {
    proxy = Gio.DBusProxy.new_for_bus_sync(
      Gio.BusType.SESSION,
      Gio.DBusProxyFlags.NONE,
      null,
      BUS_NAME,
      OBJECT_PATH,
      IFACE_NAME,
      null,
    )

    // Listen for property changes
    const propId = proxy.connect(
      "g-properties-changed",
      (_proxy: Gio.DBusProxy, _changed: GLib.Variant, _invalidated: string[]) => {
        syncState()
      },
    )
    signalHandlers.push(propId)

    // Listen for custom signals
    const sigId = proxy.connect(
      "g-signal",
      (_proxy: Gio.DBusProxy, _sender: string | null, signalName: string, params: GLib.Variant) => {
        const unpacked = params.deepUnpack<unknown[]>()
        if (signalName === "FileChanged") {
          const path = Array.isArray(unpacked) && typeof unpacked[0] === "string" ? unpacked[0] : ""
          const changeType = Array.isArray(unpacked) && typeof unpacked[1] === "string" ? unpacked[1] : ""
          onFileChanged(path, changeType)
        } else if (signalName === "SymbolsUpdated") {
          const path = Array.isArray(unpacked) && typeof unpacked[0] === "string" ? unpacked[0] : ""
          onSymbolsUpdated(path)
        }
      },
    )
    signalHandlers.push(sigId)

    syncState()
  } catch (e) {
    proxy = null
    setState({ ...DEFAULT_STATE })
  }
}

// ── D-Bus Method Calls ─────────────────────────────────────────

function callMethod(method: string, argSignature: string | null, args: any[]): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!proxy) {
      reject(new Error("AST daemon not available"))
      return
    }
    const variant = argSignature ? new GLib.Variant(argSignature, args) : null
    proxy.call(
      method,
      variant,
      Gio.DBusCallFlags.NONE,
      10000,
      null,
      (_proxy, result) => {
        try {
          const reply = proxy!.call_finish(result)
          if (reply) {
            const unpacked = reply.deepUnpack<string[]>()
            resolve(Array.isArray(unpacked) ? unpacked[0] : String(unpacked))
          } else {
            resolve("{}")
          }
        } catch (e) {
          reject(e)
        }
      },
    )
  })
}

export async function getSymbols(path: string): Promise<any[]> {
  const json = await callMethod("GetSymbols", "(s)", [path])
  return JSON.parse(json)
}

export async function getScope(path: string, line: number, col: number = 0): Promise<any> {
  const json = await callMethod("GetScope", "(suu)", [path, line, col])
  return JSON.parse(json)
}

export async function getComplexity(path: string): Promise<any> {
  const json = await callMethod("GetComplexity", "(s)", [path])
  return JSON.parse(json)
}

export async function getDependents(
  path: string, symbol: string, searchDirs: string[] = [],
): Promise<any[]> {
  const json = await callMethod("GetDependents", "(ssas)", [path, symbol, searchDirs])
  return JSON.parse(json)
}

export async function getFileSummary(path: string): Promise<any> {
  const json = await callMethod("GetFileSummary", "(s)", [path])
  return JSON.parse(json)
}

export async function watchDirectory(path: string, recursive: boolean = true): Promise<boolean> {
  const json = await callMethod("WatchDirectory", "(sb)", [path, recursive])
  return json === "true"
}

export async function unwatchDirectory(path: string): Promise<boolean> {
  const json = await callMethod("UnwatchDirectory", "(s)", [path])
  return json === "true"
}

export async function getStatus(): Promise<any> {
  const json = await callMethod("GetStatus", null, [])
  return JSON.parse(json)
}

// Watch for daemon appearing/disappearing on the bus
function watchBus() {
  Gio.bus_watch_name(
    Gio.BusType.SESSION,
    BUS_NAME,
    Gio.BusNameWatcherFlags.NONE,
    () => {
      // Name appeared
      connectProxy()
    },
    () => {
      // Name vanished
      proxy = null
      setState({ ...DEFAULT_STATE })
    },
  )
}

// Initialize
watchBus()
connectProxy()
