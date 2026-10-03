import QtQuick
import QtQuick.Window
import QtQuick.Controls as C
import QtQuick.Layouts
import QtQuick.Dialogs as D
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property bool editing: false
    property bool transferring: false
    property alias transferEditor: transferPanel
    property string status: ""
    property string editId: ""
    property string savedId: ""
    property var savedPasswords: ({})
    property bool keyringAvailable: true
    property alias editor: profileEditor
    property alias languageState: i18n
    property var profiles: []
    property var filtered: []
    property int current: 0
    property string problem: ""
    property alias query: search.text
    readonly property var selected: filtered.length ? filtered[Math.min(current, filtered.length - 1)] : null
    property string helper: Quickshell.env("HOME") + "/.config/omarchy/plugins/david.rdp/rdp.py"
    property string configPath: Quickshell.env("HOME") + "/.config/omarchy-rdp/connections.json"
    readonly property int bodySize: Math.max(16, Style.font.body)
    readonly property color bg: Color.menu.background
    readonly property color fg: Color.menu.text
    readonly property color dim: Qt.rgba(fg.r, fg.g, fg.b, 0.75)
    readonly property color line: Color.menu.border

    Language {
        id: i18n
        profilesPath: root.configPath
        helper: root.helper
        onFailed: function(message) { root.problem = message }
        onLanguageChanged: {
            root.status = ""
            root.problem = ""
            profileEditor.error = ""
            transferPanel.error = ""
        }
    }

    function open(payload) {
        opened = true
        panel.visible = true
        search.text = ""
        dataFile.reload()
        Qt.callLater(function() { search.forceActiveFocus() })
    }
    function close() { opened = false; panel.visible = false }
    function dismiss() {
        close()
        if (shell && typeof shell.hide === "function") shell.hide("david.rdp")
    }
    function toggle() { if (opened) dismiss(); else open("{}") }
    function refresh() {
        var query = search.text.toLowerCase().trim()
        filtered = profiles.filter(function(p) {
            return (p.name + " " + p.customer + " " + p.host).toLowerCase().indexOf(query) >= 0
        }).sort(function(a,b) {
            return Number(!!b.favorite) - Number(!!a.favorite) || a.customer.localeCompare(b.customer) || a.name.localeCompare(b.name)
        })
        current = 0
    }
    function move(delta) {
        if (!filtered.length) return
        current = (current + delta + filtered.length) % filtered.length
        computers.positionViewAtIndex(current, ListView.Contain)
    }
    function launch() {
        if (!selected) return
        var id = selected.id
        dismiss()
        Quickshell.execDetached(["python3", helper, "launch", id])
    }
    function editProfile(add) {
        if (!add && !selected) return
        editId = add ? "" : selected.id
        profileEditor.load(add ? null : selected)
        editing = true
        Qt.callLater(function() { profileEditor.focusFirst() })
    }
    function exportProfiles() {
        if (transferProcess.running || !profiles.length) return
        transferPanel.load(profiles, false, [])
        transferring = true
        status = ""
        Qt.callLater(function() { transferPanel.focusFirst() })
    }
    function importProfiles(path) {
        if (transferProcess.running) return
        status = ""
        runTransfer({operation: "preview", path: path})
    }
    function chooseImport() { importDialog.open() }
    function cancelTransfer() {
        if (transferProcess.running) return
        transferring = false
        search.forceActiveFocus()
    }
    function runTransfer(payload) {
        if (transferProcess.running) return
        problem = ""
        transferPanel.error = ""
        transferProcess.operation = payload.operation
        transferProcess.payload = JSON.stringify(payload)
        transferProcess.command = ["python3", helper, "transfer", "--profiles", configPath]
        transferProcess.running = true
    }
    function saveExport(path) {
        runTransfer({operation: "export", path: path, ids: transferPanel.selectedIds})
    }
    function finishImport() {
        runTransfer({operation: "import", document: {version: 1, connections: transferPanel.profiles},
            ids: transferPanel.selectedIds, conflicts: transferPanel.replaceExisting ? "replace" : "keep"})
    }
    function cancelEdit() {
        if (saveProcess.running) return
        editing = false
        search.forceActiveFocus()
    }
    function saveEdit(fields) {
        if (saveProcess.running) return
        profileEditor.error = ""
        saveProcess.payload = JSON.stringify({id: editId, fields: fields})
        saveProcess.command = ["python3", helper, "save", "--profiles", configPath]
        saveProcess.running = true
    }
    function favorite(id) {
        if (mutation.running) return
        mutation.command = ["python3", helper, "favorite", id, "--profiles", configPath]
        mutation.running = true
    }
    function refreshCredentials() {
        if (credentialStatus.running) { credentialStatus.again = true; return }
        credentialStatus.command = ["python3", helper, "credential-status", "--profiles", configPath]
        credentialStatus.running = true
    }
    function manageCredentials(id) {
        if (!id || credentialProcess.running) return
        credentialProcess.command = ["python3", helper, "credential", id, "--profiles", configPath]
        credentialProcess.running = true
    }

    FileView {
        id: dataFile
        path: root.configPath
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                var parsed = JSON.parse(text())
                if (!Array.isArray(parsed.connections)) throw new Error(i18n.tr("Fältet connections ska vara en lista."))
                root.profiles = parsed.connections
                root.refreshCredentials()
                root.problem = ""
                root.refresh()
                if (root.savedId) {
                    var index = root.filtered.findIndex(function(p) { return p.id === root.savedId })
                    if (index >= 0) root.current = index
                    root.savedId = ""
                }
            } catch (error) { root.problem = i18n.tr("Kunde inte läsa profilerna: ") + error.message }
        }
        onLoadFailed: { root.problem = i18n.tr("Kunde inte läsa ") + root.configPath }
    }
    Process {
        id: credentialStatus
        property bool again: false
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    root.savedPasswords = result.saved || ({})
                    root.keyringAvailable = result.ok === true
                } catch (error) { root.keyringAvailable = false }
            }
        }
        onExited: {
            if (again) { again = false; Qt.callLater(root.refreshCredentials) }
        }
    }
    Process {
        id: credentialProcess
        onExited: root.refreshCredentials()
    }
    Process {
        id: mutation
        onExited: function(code) {
            if (code === 0) dataFile.reload()
            else root.problem = i18n.tr("Kunde inte spara favoritmarkeringen.")
        }
    }

    Process {
        id: transferProcess
        property string operation: ""
        property string payload: ""
        stdinEnabled: true
        onStarted: { write(payload + "\n"); payload = "" }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    if (!result.ok) {
                        if (root.transferring) transferPanel.error = result.error
                        else root.problem = result.error
                        return
                    }
                    if (transferProcess.operation === "preview") {
                        transferPanel.load(result.profiles, true, root.profiles.map(function(p) { return p.id }))
                        root.transferring = true
                        Qt.callLater(function() { transferPanel.focusFirst() })
                    } else {
                        root.transferring = false
                        root.status = transferProcess.operation === "export" ? i18n.tr("{count} anslutningar exporterade utan lösenord.", {count: result.count})
                            : i18n.tr("Import klar: {added} tillagda, {replaced} ersatta, {skipped} behållna.", {added: result.added, replaced: result.replaced, skipped: result.skipped})
                        if (transferProcess.operation === "import") { search.text = ""; dataFile.reload() }
                        search.forceActiveFocus()
                    }
                } catch (error) {
                    if (root.transferring) transferPanel.error = i18n.tr("Kunde inte slutföra åtgärden. Försök igen.")
                    else root.problem = i18n.tr("Kunde inte läsa importfilen.")
                }
            }
        }
    }
    Process {
        id: saveProcess
        property string payload: ""
        stdinEnabled: true
        onStarted: { write(payload + "\n"); payload = "" }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    if (!result.ok) { profileEditor.error = result.error; return }
                    root.savedId = result.profile.id
                    root.editing = false
                    search.text = ""
                    dataFile.reload()
                    search.forceActiveFocus()
                } catch (error) { profileEditor.error = i18n.tr("Kunde inte spara profilen. Försök igen.") }
            }
        }
    }

    component Label: Text {
        color: root.fg
        font.family: Style.font.menuFamily
        font.pixelSize: root.bodySize
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }
    component Action: C.Button {
        id: control
        implicitHeight: Style.space(38)
        implicitWidth: Math.max(Style.space(80), implicitContentWidth + Style.space(24))
        padding: Style.space(10)
        contentItem: Label { text: control.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; opacity: control.enabled ? 1 : 0.45 }
        background: Rectangle {
            color: control.down || control.hovered ? Color.menu.selectedBackground : "transparent"
            radius: Style.cornerRadius
            border.width: 1
            border.color: control.activeFocus ? Color.accent : root.line
        }
    }

    FloatingWindow {
        id: panel
        visible: false
        title: i18n.tr("Anslutningar")
        color: root.bg
        implicitWidth: Style.space(1000)
        implicitHeight: Style.space(720)
        minimumSize: Qt.size(Style.space(480), Style.space(440))
        onVisibleChanged: { if (!visible && root.opened) root.dismiss() }
        D.FileDialog {
            id: exportDialog
            parentWindow: card.Window.window
            options: D.FileDialog.DontUseNativeDialog
            title: i18n.tr("Exportera anslutningar")
            fileMode: D.FileDialog.SaveFile
            nameFilters: [i18n.tr("Anslutningar (*.json)")]
            defaultSuffix: "json"
            selectedFile: "file://" + Quickshell.env("HOME") + "/anslutningar.json"
            acceptLabel: i18n.tr("Spara")
            rejectLabel: i18n.tr("Avbryt")
            onAccepted: root.saveExport(selectedFile.toString())
        }
        D.FileDialog {
            id: importDialog
            parentWindow: card.Window.window
            options: D.FileDialog.DontUseNativeDialog
            title: i18n.tr("Importera anslutningar")
            fileMode: D.FileDialog.OpenFile
            nameFilters: [i18n.tr("Anslutningar (*.json)"), i18n.tr("Alla filer (*)")]
            acceptLabel: i18n.tr("Öppna")
            rejectLabel: i18n.tr("Avbryt")
            onAccepted: root.importProfiles(selectedFile.toString())
        }
        Rectangle {
            id: card
            anchors.fill: parent
            color: root.bg
            Keys.onEscapePressed: { if (root.transferring) root.cancelTransfer(); else if (root.editing) root.cancelEdit(); else root.dismiss() }
            TransferPanel {
                id: transferPanel
                i18n: root.languageState
                anchors.fill: parent
                visible: root.transferring
                busy: transferProcess.running
                onCancelled: root.cancelTransfer()
                onSubmitted: {
                    if (importing) root.finishImport()
                    else exportDialog.open()
                }
            }
            ProfileEditor {
                id: profileEditor
                i18n: root.languageState
                anchors.fill: parent
                visible: root.editing
                editingExisting: root.editId !== ""
                busy: saveProcess.running
                credentialSaved: !!root.savedPasswords[root.editId]
                credentialBusy: credentialProcess.running
                onCredentialRequested: root.manageCredentials(root.editId)
                onSaveRequested: function(fields) { root.saveEdit(fields) }
                onCancelled: root.cancelEdit()
            }
            ColumnLayout {
                visible: !root.editing && !root.transferring
                anchors.fill: parent
                anchors.margins: Style.space(22)
                spacing: Style.space(15)
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: i18n.tr("Anslutningar"); font.pixelSize: root.bodySize + 7; Layout.fillWidth: true }
                    Action { text: i18n.tr("+ Lägg till"); onClicked: root.editProfile(true) }
                    Action { text: i18n.tr("Stäng"); onClicked: root.dismiss() }
                }
                C.TextField {
                    id: search
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.space(42)
                    placeholderText: i18n.tr("Sök kund eller dator…")
                    placeholderTextColor: root.dim
                    color: root.fg
                    font.family: Style.font.menuFamily
                    font.pixelSize: root.bodySize + 1
                    selectByMouse: true
                    leftPadding: Style.space(12)
                    background: Rectangle { color: root.bg; border.color: search.activeFocus ? Color.accent : root.line; border.width: 1; radius: Style.cornerRadius }
                    onTextChanged: root.refresh()
                    Keys.onDownPressed: root.move(1)
                    Keys.onUpPressed: root.move(-1)
                    Keys.onEscapePressed: { if (text) text = ""; else root.dismiss() }
                    onAccepted: root.launch()
                }
                Label { visible: root.problem !== ""; text: root.problem; color: Color.urgent; Layout.fillWidth: true; wrapMode: Text.Wrap; elide: Text.ElideNone }
                Label { visible: root.status !== ""; text: root.status; Layout.fillWidth: true; wrapMode: Text.Wrap; elide: Text.ElideNone }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: Style.space(20)
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            id: computers
                            anchors.fill: parent
                            clip: true
                            spacing: Style.space(5)
                            model: root.filtered
                            currentIndex: root.current
                            C.ScrollBar.vertical: C.ScrollBar {}
                            delegate: Column {
                                id: row
                                required property var modelData
                                required property int index
                                width: computers.width
                                property bool groupStart: index === 0 || !!root.filtered[index - 1].favorite !== !!modelData.favorite
                                Label {
                                    visible: row.groupStart
                                    text: row.modelData.favorite ? i18n.tr("FAVORITER") : i18n.tr("DATORER")
                                    color: root.dim
                                    font.pixelSize: root.bodySize - 2
                                    height: visible ? Style.space(30) : 0
                                }
                                Rectangle {
                                    width: parent.width
                                    height: Style.space(63)
                                    color: root.current === row.index ? Color.menu.selectedBackground : "transparent"
                                    radius: Style.cornerRadius
                                    C.Button {
                                        anchors.fill: parent
                                        anchors.rightMargin: Style.space(42)
                                        background: Item {}
                                        contentItem: Column {
                                            leftPadding: Style.space(10)
                                            spacing: Style.space(3)
                                            Label { width: parent.width - Style.space(12); text: row.modelData.name; color: root.current === row.index ? Color.menu.selectedText : root.fg }
                                            Label { width: parent.width - Style.space(12); text: row.modelData.customer + (row.modelData.vpn ? " · " + row.modelData.vpn : ""); font.pixelSize: root.bodySize - 2; color: root.current === row.index ? Color.menu.selectedText : root.dim }
                                        }
                                        onClicked: { root.current = row.index; search.forceActiveFocus() }
                                        onDoubleClicked: { root.current = row.index; root.launch() }
                                        Accessible.name: row.modelData.name + ", " + row.modelData.customer
                                    }
                                    C.Button {
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: Style.space(42)
                                        height: parent.height
                                        background: Item {}
                                        contentItem: Label { text: row.modelData.favorite ? "★" : "☆"; color: root.current === row.index ? Color.menu.selectedText : Color.accent; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        onClicked: root.favorite(row.modelData.id)
                                        Accessible.name: i18n.tr("Favoritmarkera ") + row.modelData.name
                                    }
                                }
                            }
                        }
                        Column {
                            visible: !root.filtered.length
                            anchors.centerIn: parent
                            width: parent.width
                            spacing: Style.space(12)
                            Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.profiles.length ? i18n.tr("Ingen dator matchar sökningen.") : i18n.tr("Din första anslutning"); font.pixelSize: root.bodySize + 2 }
                            Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: root.profiles.length ? i18n.tr("Prova ett annat namn.") : i18n.tr("Lägg till din Windows-dator med\nTailscale-IP och användarnamn."); wrapMode: Text.Wrap; color: root.dim }
                            Action { anchors.horizontalCenter: parent.horizontalCenter; visible: !root.profiles.length; text: i18n.tr("+ Lägg till dator"); onClicked: root.editProfile(true) }
                        }
                    }
                    Rectangle { visible: !!root.selected; Layout.fillHeight: true; width: 1; color: root.line }
                    C.ScrollView {
                        id: detailsScroll
                        visible: !!root.selected
                        Layout.minimumWidth: Style.space(200)
                        Layout.maximumWidth: Math.min(Style.space(310), card.width * 0.42)
                        Layout.preferredWidth: Math.min(Style.space(310), card.width * 0.42)
                        Layout.fillHeight: true
                        Layout.minimumHeight: 0
                        clip: true
                        contentWidth: availableWidth
                        C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff
                        ColumnLayout {
                            width: detailsScroll.availableWidth
                            height: Math.max(implicitHeight, detailsScroll.availableHeight)
                            spacing: Style.space(10)
                            C.ScrollView {
                                id: detailTextScroll
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                Layout.minimumHeight: Style.space(80)
                                clip: true
                                contentWidth: availableWidth
                                C.ScrollBar.horizontal.policy: C.ScrollBar.AlwaysOff
                                ColumnLayout {
                                    width: detailTextScroll.availableWidth
                                    spacing: Style.space(10)
                                    Label { text: root.selected ? root.selected.customer : ""; color: root.dim; Layout.fillWidth: true }
                                    Label { text: root.selected ? root.selected.name : ""; font.pixelSize: root.bodySize + 5; Layout.fillWidth: true }
                                    Label { text: i18n.tr("ADRESS"); color: root.dim; font.pixelSize: root.bodySize - 3; Layout.topMargin: Style.space(12) }
                                    Label { text: root.selected ? root.selected.host : ""; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone; Layout.fillWidth: true }
                                    Label { text: i18n.tr("ANVÄNDARE"); color: root.dim; font.pixelSize: root.bodySize - 3; Layout.topMargin: Style.space(8) }
                                    Label { text: root.selected ? root.selected.username : ""; wrapMode: Text.WrapAnywhere; elide: Text.ElideNone; Layout.fillWidth: true }
                                    Label { text: i18n.tr("Upplösning: ") + (root.selected && root.selected.resolution && root.selected.resolution !== "auto" ? root.selected.resolution.replace("x", " × ") : i18n.tr("Automatisk")); color: root.dim; Layout.fillWidth: true; wrapMode: Text.Wrap; elide: Text.ElideNone }
                                    Rectangle { Layout.fillWidth: true; height: 1; color: root.line; Layout.topMargin: Style.space(10); Layout.bottomMargin: Style.space(7) }
                                    Label { text: root.selected && root.selected.vpn ? root.selected.vpn : i18n.tr("Ingen VPN angiven"); Layout.fillWidth: true }
                                    Label { text: root.selected ? (root.selected.notes || (root.selected.vpn ? i18n.tr("Anslut separat innan du öppnar fjärrskrivbordet.") : i18n.tr("Direkt RDP-anslutning."))) : ""; color: root.dim; wrapMode: Text.Wrap; elide: Text.ElideNone; Layout.fillWidth: true }
                                }
                            }
                            Label { text: !root.keyringAvailable ? i18n.tr("Nyckelringen är inte tillgänglig.") : (root.selected && root.savedPasswords[root.selected.id] ? i18n.tr("Lösenord sparat i nyckelringen.") : i18n.tr("Lösenord anges vid anslutning.")); color: root.dim; font.pixelSize: root.bodySize - 2; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Action { text: i18n.tr("Lösenord…"); Layout.fillWidth: true; enabled: !credentialProcess.running; onClicked: root.manageCredentials(root.selected.id) }
                            Action { text: i18n.tr("Anslut  ↵"); Layout.fillWidth: true; onClicked: root.launch() }
                            Action { text: i18n.tr("Redigera profil"); Layout.fillWidth: true; onClicked: root.editProfile(false) }
                        }
                    }
                }
                Rectangle { height: 1; Layout.fillWidth: true; color: root.line }
                RowLayout {
                    Layout.fillWidth: true
                    Action { text: i18n.tr("Importera…"); enabled: !transferProcess.running; onClicked: root.chooseImport() }
                    Action { text: i18n.tr("Exportera…"); enabled: root.profiles.length > 0 && !transferProcess.running; onClicked: root.exportProfiles() }
                    Item { Layout.fillWidth: true }
                    C.ComboBox {
                        id: languageChoice
                        Layout.preferredWidth: Style.space(140)
                        Layout.preferredHeight: Style.space(38)
                        model: ["Svenska", "English"]
                        currentIndex: i18n.language === "en" ? 1 : 0
                        enabled: !i18n.busy && !transferProcess.running
                        Accessible.name: i18n.tr("Språk")
                        onActivated: i18n.choose(currentIndex === 1 ? "en" : "sv")
                        contentItem: Label { text: languageChoice.displayText; verticalAlignment: Text.AlignVCenter; leftPadding: Style.space(10); rightPadding: Style.space(25) }
                        indicator: Label { text: "▾"; anchors.right: parent.right; anchors.rightMargin: Style.space(9); anchors.verticalCenter: parent.verticalCenter }
                        background: Rectangle { color: root.bg; border.color: languageChoice.activeFocus ? Color.accent : root.line; radius: Style.cornerRadius }
                        delegate: C.ItemDelegate {
                            required property string modelData
                            required property int index
                            width: languageChoice.width
                            implicitHeight: Style.space(38)
                            contentItem: Label { text: modelData; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle { color: parent.highlighted ? Color.menu.selectedBackground : root.bg }
                            highlighted: languageChoice.highlightedIndex === index
                        }
                        popup: C.Popup {
                            y: -implicitHeight
                            width: languageChoice.width
                            implicitHeight: contentItem.implicitHeight + 2
                            padding: 1
                            contentItem: ListView {
                                implicitHeight: contentHeight
                                model: languageChoice.popup.visible ? languageChoice.delegateModel : null
                                currentIndex: languageChoice.highlightedIndex
                            }
                            background: Rectangle { color: root.bg; border.color: root.line }
                        }
                    }
                }
                Label { text: i18n.tr("↑ ↓ välj   Enter anslut   Esc stäng   ·   Super + Tab byter arbetsyta"); font.pixelSize: root.bodySize - 2; color: root.dim; Layout.fillWidth: true }
            }
        }
    }
}
