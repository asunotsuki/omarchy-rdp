import QtQuick
import QtQuick.Controls as C
import QtQuick.Layouts
import qs.Commons

Item {
    id: transfer
    required property var i18n
    property bool importing: false
    property bool busy: false
    property string error: ""
    property var profiles: []
    property var selectedIds: []
    property var existingIds: []
    property bool replaceExisting: false
    readonly property int bodySize: Math.max(16, Style.font.body)
    readonly property int conflicts: selectedIds.filter(function(id) { return existingIds.indexOf(id) >= 0 }).length
    signal cancelled()
    signal submitted()

    function load(rows, importing, existing) {
        transfer.importing = importing
        profiles = rows
        existingIds = existing || []
        selectedIds = rows.map(function(p) { return p.id })
        replaceExisting = false
        error = ""
        list.positionViewAtBeginning()
    }
    function toggleSelection(id) {
        var ids = selectedIds.slice()
        var index = ids.indexOf(id)
        if (index >= 0) ids.splice(index, 1)
        else ids.push(id)
        selectedIds = ids
    }
    function focusFirst() { selectAll.forceActiveFocus() }

    component Label: Text {
        color: Color.menu.text
        font.family: Style.font.menuFamily
        font.pixelSize: transfer.bodySize
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }
    component Action: C.Button {
        id: button
        implicitHeight: Style.space(42)
        implicitWidth: implicitContentWidth + Style.space(28)
        padding: Style.space(10)
        contentItem: Label {
            text: button.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: button.enabled ? 1 : 0.45
        }
        background: Rectangle {
            color: button.hovered || button.down ? Color.menu.selectedBackground : "transparent"
            border.color: button.activeFocus ? Color.accent : Color.menu.border
            radius: Style.cornerRadius
        }
    }
    component Choice: C.CheckBox {
        id: choice
        implicitHeight: Math.max(Style.space(38), implicitContentHeight + Style.space(12))
        padding: Style.space(6)
        spacing: Style.space(12)
        indicator: Rectangle {
            x: choice.leftPadding
            y: (choice.height - height) / 2
            width: Style.space(24)
            height: width
            radius: Style.cornerRadius
            color: choice.checked ? Color.accent : "transparent"
            border.color: choice.activeFocus ? Color.accent : Color.menu.border
            Label { anchors.centerIn: parent; text: choice.checked ? "✓" : ""; color: Color.menu.background }
        }
        contentItem: Label {
            text: choice.text
            leftPadding: Style.space(36)
            verticalAlignment: Text.AlignVCenter
            opacity: choice.enabled ? 1 : 0.45
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Style.space(22)
        spacing: Style.space(14)
        Label { text: transfer.importing ? i18n.tr("Importera anslutningar") : i18n.tr("Exportera anslutningar"); font.pixelSize: transfer.bodySize + 7; Layout.fillWidth: true }
        Label {
            text: transfer.importing ? i18n.tr("Välj vilka anslutningar du vill lägga till. Lösenord importeras inte.") : i18n.tr("Välj anslutningar att spara i en fil. Lösenord följer inte med.")
            opacity: 0.75
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            Action { id: selectAll; text: i18n.tr("Välj alla"); enabled: !transfer.busy; onClicked: transfer.selectedIds = transfer.profiles.map(function(p) { return p.id }) }
            Action { text: i18n.tr("Välj inga"); enabled: !transfer.busy; onClicked: transfer.selectedIds = [] }
            Label { text: i18n.tr("{selected} av {total} valda", {selected: transfer.selectedIds.length, total: transfer.profiles.length}); horizontalAlignment: Text.AlignRight; Layout.fillWidth: true }
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: Style.space(5)
            model: transfer.profiles
            C.ScrollBar.vertical: C.ScrollBar {}
            delegate: Rectangle {
                id: row
                required property var modelData
                width: list.width
                height: Style.space(78)
                color: checkbox.hovered ? Color.menu.selectedBackground : "transparent"
                radius: Style.cornerRadius
                Choice {
                    id: checkbox
                    anchors.fill: parent
                    enabled: !transfer.busy
                    checked: transfer.selectedIds.indexOf(row.modelData.id) >= 0
                    Accessible.name: row.modelData.name + ", " + row.modelData.customer
                    onClicked: transfer.toggleSelection(row.modelData.id)
                    contentItem: Column {
                        leftPadding: Style.space(36)
                        spacing: Style.space(3)
                        Label { width: parent.width - parent.leftPadding; text: row.modelData.name + (transfer.importing && transfer.existingIds.indexOf(row.modelData.id) >= 0 ? i18n.tr(" · Befintlig") : ""); wrapMode: Text.NoWrap; elide: Text.ElideRight }
                        Label { width: parent.width - parent.leftPadding; text: row.modelData.customer + " · " + row.modelData.host; opacity: 0.75; font.pixelSize: transfer.bodySize - 2; wrapMode: Text.NoWrap; elide: Text.ElideRight }
                    }
                }
            }
        }
        ColumnLayout {
            visible: transfer.importing && transfer.conflicts > 0
            Layout.fillWidth: true
            spacing: Style.space(4)
            Label { text: i18n.tr("{count} valda anslutningar finns redan och behålls som standard.", {count: transfer.conflicts}); Layout.fillWidth: true }
            Choice {
                text: i18n.tr("Ersätt befintliga med uppgifterna från filen")
                Layout.fillWidth: true
                enabled: !transfer.busy
                checked: transfer.replaceExisting
                onClicked: transfer.replaceExisting = checked
            }
        }
        Label { visible: transfer.error !== ""; text: transfer.error; color: Color.urgent; Layout.fillWidth: true }
        Rectangle { Layout.fillWidth: true; height: 1; color: Color.menu.border }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Action { text: i18n.tr("Avbryt"); enabled: !transfer.busy; onClicked: transfer.cancelled() }
            Action {
                text: transfer.busy ? i18n.tr("Arbetar…") : (transfer.importing ? i18n.tr("Importera") : i18n.tr("Spara fil…"))
                enabled: !transfer.busy && transfer.selectedIds.length > 0
                onClicked: transfer.submitted()
            }
        }
    }
}
