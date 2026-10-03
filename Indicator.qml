import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "david.rdp"
    implicitWidth: button.implicitWidth
    Language { id: i18n }
    implicitHeight: button.implicitHeight
    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "\uf108"
        tooltipText: i18n.tr("Anslutningar · Super + R")
        onPressed: Quickshell.execDetached(["omarchy-shell", "shell", "toggle", "david.rdp"])
    }
}
