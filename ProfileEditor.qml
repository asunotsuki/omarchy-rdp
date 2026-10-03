import QtQuick
import QtQuick.Controls as C
import QtQuick.Layouts
import qs.Commons

Item {
    id: editor
    property bool editingExisting: false
    property bool busy: false
    property string error: ""
    property bool credentialSaved: false
    property bool credentialBusy: false
    property string savedHost: ""
    property string savedUsername: ""
    readonly property var resolutionValues: ["auto", "1280x720", "1920x1080", "1920x1200", "2560x1440", "3440x1440", "3840x2160", "custom"]
    property alias resolutionControl: resolutionChoice
    signal credentialRequested()
    readonly property int bodySize: Math.max(16, Style.font.body)
    signal saveRequested(var fields)
    signal cancelled()

    function load(profile) {
        error = ""
        nameField.text = profile ? profile.name : ""
        customerField.text = profile ? profile.customer : "Egna maskiner"
        hostField.text = profile ? profile.host : ""
        userField.text = profile ? profile.username : ""
        vpnField.text = profile ? profile.vpn : ""
        notesField.text = profile ? profile.notes : ""
        savedHost = profile ? profile.host : ""
        savedUsername = profile ? profile.username : ""
        var resolution = profile && profile.resolution ? profile.resolution : "auto"
        var index = resolutionValues.indexOf(resolution)
        resolutionChoice.currentIndex = index >= 0 ? index : resolutionValues.length - 1
        customResolution.text = index < 0 ? resolution : "2560x1600"
        scroll.contentItem.contentY = 0
    }
    function focusFirst() { nameField.input.forceActiveFocus() }
    function values() {
        return {name: nameField.text, customer: customerField.text, host: hostField.text,
            username: userField.text, vpn: vpnField.text, notes: notesField.text,
            resolution: resolutionChoice.currentIndex === resolutionValues.length - 1 ? customResolution.text : resolutionValues[resolutionChoice.currentIndex]}
    }
    function submit() {
        if (busy) return
        if (!nameField.text.trim() || !hostField.text.trim() || !userField.text.trim()) {
            error = "Fyll i datornamn, adress och användarnamn."
            return
        }
        saveRequested(values())
    }

    component Label: Text {
        color: Color.menu.text
        font.family: Style.font.menuFamily
        font.pixelSize: editor.bodySize
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }
    component Field: GridLayout {
        id: field
        property string label: ""
        property alias text: input.text
        property alias hint: input.placeholderText
        property alias input: input
        Layout.fillWidth: true
        columns: width >= Style.space(440) ? 2 : 1
        columnSpacing: Style.space(16)
        rowSpacing: Style.space(7)
        Label {
            text: field.label
            Layout.preferredWidth: field.columns === 2 ? Style.space(140) : -1
            Layout.fillWidth: field.columns === 1
        }
        C.TextField {
            id: input
            Layout.fillWidth: true
            Layout.preferredHeight: Style.space(46)
            font.family: Style.font.menuFamily
            font.pixelSize: editor.bodySize + 1
            color: Color.menu.text
            placeholderTextColor: Qt.rgba(color.r, color.g, color.b, 0.5)
            selectByMouse: true
            maximumLength: 500
            leftPadding: Style.space(12)
            rightPadding: Style.space(12)
            activeFocusOnTab: true
            Accessible.name: field.label
            background: Rectangle {
                color: Color.menu.background
                border.color: input.activeFocus ? Color.accent : Color.menu.border
                border.width: input.activeFocus ? 2 : 1
                radius: Style.cornerRadius
            }
            onAccepted: editor.submit()
            onActiveFocusChanged: {
                if (!activeFocus) return
                var point = input.mapToItem(form, 0, 0)
                var flick = scroll.contentItem
                if (point.y < flick.contentY) flick.contentY = Math.max(0, point.y - Style.space(30))
                else if (point.y + height > flick.contentY + scroll.availableHeight)
                    flick.contentY = point.y + height - scroll.availableHeight + Style.space(10)
            }
        }
    }
    component Button: C.Button {
        id: button
        implicitHeight: Style.space(44)
        implicitWidth: Math.max(Style.space(110), implicitContentWidth + Style.space(32))
        contentItem: Label {
            text: button.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: button.enabled ? 1 : 0.5
        }
        background: Rectangle {
            radius: Style.cornerRadius
            color: button.hovered || button.down ? Color.menu.selectedBackground : "transparent"
            border.color: button.activeFocus ? Color.accent : Color.menu.border
            border.width: 1
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Style.space(24)
        spacing: Style.space(16)
        Label {
            text: editor.editingExisting ? "Redigera anslutning" : "Ny anslutning"
            font.pixelSize: editor.bodySize + 7
            Layout.fillWidth: true
        }
        Label {
            text: "Datornamn, adress och användarnamn behövs. Lösenord kan sparas separat i nyckelringen."
            opacity: 0.7
            Layout.fillWidth: true
        }
        C.ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff
            C.ScrollBar.vertical.policy: contentHeight > availableHeight ? C.ScrollBar.AlwaysOn : C.ScrollBar.AsNeeded
            ColumnLayout {
                id: form
                width: scroll.availableWidth
                spacing: Style.space(16)
                enabled: !editor.busy
                Field { id: nameField; label: "Datornamn"; hint: "Till exempel Acer Revo" }
                Field { id: customerField; label: "Kund / grupp"; hint: "Till exempel Egna maskiner" }
                Field { id: hostField; label: "Adress"; hint: "Tailscale-IP eller DNS-namn, eventuellt :port" }
                Field { id: userField; label: "Windows-användare"; hint: "Användarnamn, e-post eller DOMÄN\\namn" }
                GridLayout {
                    Layout.fillWidth: true
                    columns: width >= Style.space(440) ? 2 : 1
                    columnSpacing: Style.space(16)
                    rowSpacing: Style.space(7)
                    Label { text: "Upplösning"; Layout.preferredWidth: parent.columns === 2 ? Style.space(140) : -1 }
                    C.ComboBox {
                        id: resolutionChoice
                        Layout.fillWidth: true
                        Layout.preferredHeight: Style.space(46)
                        model: ["Automatisk", "1280 × 720", "1920 × 1080", "1920 × 1200", "2560 × 1440", "3440 × 1440", "3840 × 2160", "Egen upplösning…"]
                        Accessible.name: "Upplösning"
                        contentItem: Label {
                            text: resolutionChoice.displayText
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: Style.space(12)
                            rightPadding: Style.space(28)
                        }
                        indicator: Label { text: "▾"; anchors.right: parent.right; anchors.rightMargin: Style.space(12); anchors.verticalCenter: parent.verticalCenter }
                        background: Rectangle { color: Color.menu.background; border.color: resolutionChoice.activeFocus ? Color.accent : Color.menu.border; radius: Style.cornerRadius }
                        delegate: C.ItemDelegate {
                            required property string modelData
                            required property int index
                            width: resolutionChoice.width
                            implicitHeight: Style.space(40)
                            contentItem: Label { text: modelData; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { color: parent.highlighted ? Color.menu.selectedBackground : Color.menu.background }
                            highlighted: resolutionChoice.highlightedIndex === index
                        }
                        popup: C.Popup {
                            y: resolutionChoice.height
                            width: resolutionChoice.width
                            implicitHeight: Math.min(contentItem.implicitHeight + 2, Style.space(320))
                            padding: 1
                            contentItem: ListView {
                                clip: true
                                implicitHeight: contentHeight
                                model: resolutionChoice.popup.visible ? resolutionChoice.delegateModel : null
                                currentIndex: resolutionChoice.highlightedIndex
                                C.ScrollBar.vertical: C.ScrollBar {}
                            }
                            background: Rectangle { color: Color.menu.background; border.color: Color.menu.border }
                        }
                    }
                }
                Field { id: customResolution; visible: resolutionChoice.currentIndex === editor.resolutionValues.length - 1; label: "Bredd × höjd"; hint: "Till exempel 2560x1600" }
                Label { Layout.fillWidth: true; opacity: 0.7; text: resolutionChoice.currentIndex === 0 ? "Anpassas när fönstrets storlek ändras." : "Fast upplösning på fjärrdatorn. Bilden skalas till fönstret. Gäller nästa anslutning." }
                Field { id: vpnField; label: "VPN (valfritt)"; hint: "Till exempel Tailscale" }
                Field { id: notesField; label: "VPN-anteckning (valfritt)"; hint: "Information att ha till hands före anslutning" }
                Label {
                    Layout.fillWidth: true
                    text: !editor.editingExisting ? "Spara profilen först. Lösenordet kan du sedan spara vid anslutning." :
                        (hostField.text !== editor.savedHost || userField.text !== editor.savedUsername ?
                         "Spara ändrad adress/användare innan du hanterar lösenordet." :
                         (editor.credentialSaved ? "Lösenord sparat i nyckelringen." : "Inget sparat lösenord."))
                    opacity: 0.7
                }
                Button {
                    visible: editor.editingExisting
                    text: editor.credentialSaved ? "Byt / ta bort lösenord…" : "Spara lösenord…"
                    enabled: !editor.credentialBusy && hostField.text === editor.savedHost && userField.text === editor.savedUsername
                    onClicked: editor.credentialRequested()
                }
                Item { Layout.preferredHeight: Style.space(8) }
            }
        }
        Label { visible: editor.error !== ""; text: editor.error; color: Color.urgent; Layout.fillWidth: true }
        Rectangle { color: Color.menu.border; Layout.fillWidth: true; height: 1 }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Enter sparar · Esc avbryter"; opacity: 0.7; font.pixelSize: editor.bodySize - 2; Layout.fillWidth: true }
            Button { text: "Avbryt"; enabled: !editor.busy; onClicked: editor.cancelled() }
            Button { text: editor.busy ? "Sparar…" : "Spara"; enabled: !editor.busy; onClicked: editor.submit() }
        }
    }
}
