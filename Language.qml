import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: languageState
    property string language: "sv"
    property var catalog: ({})
    property string profilesPath: Quickshell.env("HOME") + "/.config/omarchy-rdp/connections.json"
    property string helper: Quickshell.env("HOME") + "/.config/omarchy/plugins/david.rdp/rdp.py"
    readonly property string settingsPath: profilesPath.slice(0, profilesPath.lastIndexOf("/") + 1) + "settings.json"
    readonly property bool busy: saveProcess.running
    signal failed(string message)

    function tr(source, values) {
        var text = language === "en" && catalog[source] !== undefined ? catalog[source] : source
        return text.replace(/\{([a-z]+)\}/g, function(match, key) {
            return values && values[key] !== undefined ? String(values[key]) : match
        })
    }
    function choose(value) {
        if (busy || value === language || (value !== "sv" && value !== "en")) return
        saveProcess.command = ["python3", helper, "language", value, "--profiles", profilesPath]
        saveProcess.running = true
    }
    FileView {
        path: Qt.resolvedUrl("translations.json")
        onLoaded: {
            try { languageState.catalog = JSON.parse(text()) }
            catch (error) { languageState.catalog = ({}) }
        }
    }
    FileView {
        id: preferences
        path: languageState.settingsPath
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                var value = JSON.parse(text()).language
                languageState.language = value === "en" ? "en" : "sv"
            } catch (error) { languageState.language = "sv" }
        }
        onLoadFailed: languageState.language = "sv"
    }
    Process {
        id: saveProcess
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    if (!result.ok) throw new Error()
                    languageState.language = result.language
                    preferences.reload()
                } catch (error) { languageState.failed(languageState.tr("Kunde inte spara språkvalet.")) }
            }
        }
    }
}
