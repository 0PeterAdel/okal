import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons

// Original Okal panel. The interaction pattern is informed by omarchy-voice,
// but the state contract and implementation belong to Okal.
Item {
  id: root

  property string phase: "idle"
  property string label: ""
  property string language: "unknown"
  property real level: 0
  property real updatedAt: 0
  property real clock: Date.now() / 1000

  readonly property bool fresh: updatedAt > 0 && clock - updatedAt < 900
  readonly property bool visiblePhase: phase === "listening"
                                     || phase === "transcribing"
                                     || phase === "routing"
                                     || phase === "speaking"
                                     || phase === "blocked"
                                     || phase === "error"
  readonly property bool awake: fresh && visiblePhase
  readonly property real voiceLevel: phase === "listening" ? level : 0
  readonly property color tint: {
    if (phase === "error") return Color.urgent
    if (phase === "blocked") return "#f0ad4e"
    if (phase === "speaking") return Color.foreground
    return Color.accent
  }

  function rgba(c, alpha) {
    return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255)
         + "," + Math.round(c.b * 255) + "," + alpha + ")"
  }

  FileView {
    id: stateFile
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/okal/voice/state.json"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: {
      try {
        const state = JSON.parse(stateFile.text())
        root.phase = state.phase || "idle"
        root.label = state.text || ""
        root.language = state.language || "unknown"
        root.updatedAt = Number(state.updated_at) || 0
      } catch (error) {
        root.phase = "error"
        root.label = "Invalid Okal voice state"
        root.updatedAt = Date.now() / 1000
      }
    }
    onLoadFailed: {
      root.phase = "idle"
      root.label = ""
      root.updatedAt = 0
    }
  }

  FileView {
    id: levelFile
    path: Quickshell.env("XDG_RUNTIME_DIR") + "/okal/voice/level"
    onLoaded: {
      const parsed = parseFloat(levelFile.text())
      root.level = isFinite(parsed) ? Math.max(0, Math.min(1, parsed)) : 0
    }
    onLoadFailed: root.level = 0
  }

  Timer {
    running: true
    repeat: true
    interval: 30000
    onTriggered: root.clock = Date.now() / 1000
  }

  Timer {
    running: root.phase === "listening" && root.awake
    repeat: true
    interval: 60
    onTriggered: levelFile.reload()
    onRunningChanged: if (!running) root.level = 0
  }

  PanelWindow {
    visible: root.awake
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "okal-voice-orb"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    mask: Region {}

    Item {
      id: stage
      width: 230
      height: 190
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.bottom: parent.bottom
      anchors.bottomMargin: 64
      opacity: root.awake ? 1 : 0

      Behavior on opacity {
        NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
      }

      SequentialAnimation on scale {
        running: root.awake
        loops: Animation.Infinite
        NumberAnimation { from: 0.96; to: 1.04; duration: 1000; easing.type: Easing.InOutSine }
        NumberAnimation { from: 1.04; to: 0.96; duration: 1000; easing.type: Easing.InOutSine }
      }

      Canvas {
        id: halo
        anchors.centerIn: parent
        width: 190 + root.voiceLevel * 30
        height: width
        opacity: 0.9
        onPaint: {
          const context = getContext("2d")
          context.reset()
          const center = width / 2
          const gradient = context.createRadialGradient(center, center, 0, center, center, center)
          gradient.addColorStop(0.00, root.rgba(root.tint, 0.72))
          gradient.addColorStop(0.28, root.rgba(root.tint, 0.34))
          gradient.addColorStop(0.65, root.rgba(root.tint, 0.10))
          gradient.addColorStop(1.00, root.rgba(root.tint, 0.00))
          context.fillStyle = gradient
          context.fillRect(0, 0, width, height)
        }
        onWidthChanged: requestPaint()
        Connections {
          target: root
          function onTintChanged() { halo.requestPaint() }
        }
      }

      Rectangle {
        id: core
        anchors.centerIn: parent
        width: 58 + root.voiceLevel * 20
        height: width
        radius: width / 2
        color: root.tint
        border.color: root.rgba(Color.foreground, 0.75)
        border.width: 1
        Behavior on width { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }
      }

      Rectangle {
        anchors.centerIn: core
        width: core.width + 18
        height: width
        radius: width / 2
        color: "transparent"
        border.color: root.tint
        border.width: 2
        visible: root.phase === "transcribing" || root.phase === "routing"
        RotationAnimator on rotation {
          running: parent.visible
          loops: Animation.Infinite
          from: 0
          to: 360
          duration: 900
        }
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: core.bottom
        anchors.topMargin: 22
        width: 440
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
        text: root.label
        color: Color.foreground
        font.pixelSize: 14
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        text: "OKAL · " + root.phase.toUpperCase()
        color: root.tint
        font.pixelSize: 11
        font.letterSpacing: 2
      }
    }
  }
}
