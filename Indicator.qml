import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "david.rdp"
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "\uf108"
        tooltipText: "Anslutningar · Super + R"
        onPressed: Quickshell.execDetached(["omarchy-shell", "shell", "toggle", "david.rdp"])
    }
}
