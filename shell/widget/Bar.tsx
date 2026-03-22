import app from "ags/gtk4/app"
import { Astal, Gtk, Gdk } from "ags/gtk4"
import { getBarRevealed, revealBar, hideBar, setBarWindow } from "../lib/state"

import Workspaces from "./Workspaces"
import Git from "./Git"
import NowPlaying from "./NowPlaying"
import CostaWave from "./CostaWave"
import Headless from "./Headless"
import PTT from "./PTT"
import Audio from "./Audio"
import BatteryWidget from "./BatteryWidget"
import Troubleshoot from "./Troubleshoot"
import Clock from "./Clock"
import Claude from "./Claude"
import Power from "./Power"

const { TOP } = Astal.WindowAnchor

export default function Bar(gdkmonitor: Gdk.Monitor) {
  return (
    <window
      visible={false}
      name="costa-bar"
      class="Bar"
      gdkmonitor={gdkmonitor}
      layer={Astal.Layer.OVERLAY}
      anchor={TOP}
      exclusivity={Astal.Exclusivity.IGNORE}
      namespace="costa-bar"
      application={app}
      $={(self: Gtk.Window) => {
        setBarWindow(self)
        const motion = new Gtk.EventControllerMotion()
        motion.connect("enter", () => revealBar())
        motion.connect("leave", () => hideBar(1200))
        self.add_controller(motion)
      }}
    >
      <revealer
        revealChild={getBarRevealed}
        transitionType={Gtk.RevealerTransitionType.SLIDE_DOWN}
        transitionDuration={300}
      >
        <centerbox class="bar-panel" widthRequest={1100}>
          <box $type="start" class="bar-left" spacing={2}>
            <Workspaces />
            <Git />
            <NowPlaying />
          </box>
          <box $type="center" class="bar-center">
            <CostaWave />
          </box>
          <box $type="end" class="bar-right" spacing={2}>
            <Headless />
            <PTT />
            <Audio />
            <BatteryWidget />
            <Troubleshoot />
            <Clock />
            <Claude />
            <Power />
          </box>
        </centerbox>
      </revealer>
    </window>
  )
}
