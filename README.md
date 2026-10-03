# Anslutningar — Omarchy RDP

A small Swedish/English connection picker for Omarchy, powered by FreeRDP. Search by
customer or computer, mark favorites, and open each Windows session fullscreen
on its own workspace. The picker is a normal tiled window.

This is an **Omarchy shell plugin** for Quickshell, not a Hyprland C++ plugin.
The plugin ID is `david.rdp` regardless of who installs it.

## Requirements

- Omarchy with shell plugin support and Hyprland's **Lua configuration**.
- FreeRDP 3 with the `xfreerdp3` X11 client and XWayland.
- Python 3, Python GObject bindings, GTK 4, libsecret, Zenity and libnotify.
- A running systemd user session. Optional password storage needs a working
  Secret Service keyring, such as GNOME Keyring, unlocked in that session.

Tested with Omarchy 4.0.4, Hyprland 0.56.2, Quickshell 0.3.1 and FreeRDP 3.31.1.
Older Omarchy installations using `.conf` rather than Lua bindings are not
supported by the setup script. Other version combinations need testing.

On Omarchy, install the runtime packages with:

```bash
omarchy pkg add freerdp xorg-xwayland python python-gobject gtk4 libsecret zenity libnotify qt6-declarative
```

If your session has no Secret Service provider, GNOME Keyring is one option:

```bash
omarchy pkg add gnome-keyring
```

Installing a keyring package alone does not configure automatic unlocking.
The plugin does not change login/PAM settings or automatically install packages.
FreeRDP comes from the system package manager; it is not bundled here.

## Install from GitHub

Omarchy supports installing and updating
plugins directly from Git repositories; see the
[Omarchy plugin guide](https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md).

```bash
omarchy plugin add https://github.com/asunotsuki/omarchy-rdp.git
cd ~/.config/omarchy/plugins/david.rdp
python install.py --check
python install.py
omarchy-shell shell rescanPlugins
omarchy plugin enable david.rdp
hyprctl reload
hyprctl configerrors
```

Run setup as your desktop user, **without sudo**. Setup creates an empty profile
file only if none exists, adds the launcher, and backs up the files it changes.
It works directly inside Omarchy's Git checkout and does not copy files onto
themselves or modify the checkout's Git metadata.

Setup claims **Super+R** and stops if that shortcut is already assigned on a
first installation. It replaces Omarchy's local **Alt+Tab / Alt+Shift+Tab**
bindings with contextual versions: they go to Windows while one of this
plugin's RDP windows is focused, and cycle local windows otherwise.
**Super+Tab / Super+Shift+Tab** remain the normal local workspace shortcuts.

## Install a ZIP release

Extract `omarchy-rdp-VERSION.zip`, open a terminal in the extracted directory,
and run the same commands starting with `python install.py --check` above.
The installer copies the plugin to `~/.config/omarchy/plugins/david.rdp/`.
This method does not create a Git checkout; update it by extracting the next
release and running its installer again.

## Update

For a Git-managed installation:

```bash
omarchy plugin update david.rdp
python ~/.config/omarchy/plugins/david.rdp/install.py
hyprctl reload
hyprctl configerrors
```

If QML changes are not visible after updating, run `omarchy restart shell`.
Restarting the shell does not terminate separately launched RDP sessions.
Profiles and passwords are kept outside the plugin directory.

An existing manually installed copy cannot be updated with `plugin update`.
To switch it to Git, export your connections, remove its shortcut integration
as described below, remove the old plugin with `omarchy plugin remove david.rdp`,
then install from GitHub. The separate profiles and keyring entries remain.
For an older copy without `--remove-integration`, remove the marked
`BEGIN Anslutningar (david.rdp)` through `END Anslutningar (david.rdp)` block
from `~/.config/hypr/bindings.lua` and the `omarchy-rdp.desktop` launcher first.

## Use

- Choose **Svenska** or **English** in the bottom-right language menu. The
  interface updates immediately and the choice is saved for future launches.
  Swedish remains the default for existing installations. Profile names,
  customers, notes, credentials and exported connection data are not translated.
  Password/certificate dialogs and helper messages use the saved language when
  they open; already running dialogs retain their original language. Standard
  toolkit file-picker controls may follow the desktop language.
- Open with **Super+R**, the monitor icon in the bar, or **Anslutningar** in
  the application launcher. Search, use ↑/↓ and Enter, or double-click a row.
- **Lägg till** and **Redigera profil** share the same inline editor. Choose a
  resolution preset, a custom size, or **Automatisk** for dynamic resizing.
  Fixed resolutions scale to fit the window and apply on the next connection.
- Connect VPN/Tailscale separately. VPN notes are reminders, not automatic checks.
- Each session opens on a free workspace numbered 11 or higher. Selecting an
  already running session focuses it instead of launching a duplicate.
- **Alt+Tab** switches Windows applications; keep Alt held to continue cycling.
  **Super+Tab** switches local workspaces. Add Shift to reverse either direction.
- **Lösenord…** manages optional keyring storage. Credentials are requested in
  a separate GTK window; the QML picker only reads saved/not-saved metadata.
- An unknown or changed certificate requires explicit confirmation. No automatic
  certificate acceptance is enabled. Normal disconnect/sign-out returns to the
  picker quietly; recognized connection failures show a short error.

## Move to another computer

1. Choose **Exportera…**, select some or all connections and save the JSON file.
2. Install the plugin and its dependencies on the new computer.
3. Choose **Importera…**, preview the file and import the selected connections.
4. Enter and optionally save passwords again on the new computer.

Exports include names, customers, addresses, usernames, resolutions, VPN notes
and favorites. Passwords and keyring entries are not exported or imported.
Existing profiles are recognized by their stable ID and kept by default.
Check **Ersätt befintliga med uppgifterna från filen** to replace matching
selected profiles. Unrelated profiles stay unchanged. Imports that change data
first make a backup. Export and profile files have owner-only permissions.

## Data and limitations

| Data | Location |
| --- | --- |
| Plugin | `~/.config/omarchy/plugins/david.rdp/` |
| Profiles | `~/.config/omarchy-rdp/connections.json` |
| Language preference | `~/.config/omarchy-rdp/settings.json` |
| Setup/import backups | `~/.config/omarchy-rdp/backups/` |
| Passwords | System Secret Service keyring |
| Session locks | `$XDG_RUNTIME_DIR/omarchy-rdp/` |

The supplied `connections.example.json` is fictional documentation data and is
not installed as a working connection. Keep actual profile exports outside the
repository. Passwords are passed to FreeRDP through an anonymous pipe, not
command arguments or temporary files. Saved credentials are scoped to profile
path, ID, host and username. Changing the host/user does not reuse the previous
secret; old entries remain associated with their original identity.

Direct RDP over LAN, Tailscale or VPN is supported, with IPv4/DNS and an optional
port, `DOMAIN\user` or UPN usernames. Gateways, MFA, Citrix, IPv6, multi-monitor
sessions and automatic VPN handling are not implemented. No custom Kerberos
realm is configured.

Clipboard and remote audio are enabled. No local drive, microphone or printer
is shared automatically. Copying files between two RDP sessions still needs
verification against the actual hosts and their clipboard policies. Keep the
source connected and leave the clipboard unchanged until a copy finishes.

## Remove

Remove the shortcut integration before deleting its Lua file:

```bash
python ~/.config/omarchy/plugins/david.rdp/install.py --remove-integration
hyprctl reload
hyprctl configerrors
omarchy plugin remove david.rdp
```

This restores Omarchy's default Alt+Tab behavior. The profile directory and
keyring entries are retained. To temporarily hide the picker, use
`omarchy plugin disable david.rdp`; this does not remove its keyboard integration.

## Development and packaging

```bash
python -m unittest -v test_rdp.py test_install.py test_i18n.py
python package.py
```

Tests use temporary profiles, mocked credentials and a fake FreeRDP process;
they do not log in to remote machines. Installation tests use temporary home
directories. The packaging command uses an explicit file list and creates a
ZIP plus SHA-256 checksum in `dist/`, excluding local QA data, caches, profiles
and passwords. The ZIP can be uploaded as an asset on a GitHub release.
For a source clone, `manifest.json` remains at the repository root, as Omarchy
requires. The local `.qa/` development harness is deliberately not published.

Before releasing, run the tests, inspect the ZIP contents, and validate an
extracted copy with `omarchy plugin validate /path/to/extracted/plugin`.
Set the version in `manifest.json`, update `CHANGELOG.md`, and use the same
version for the Git tag/release. See [PUBLISHING.md](PUBLISHING.md).

UI and Python messages share `translations.json`, with Swedish source strings
and English translations. Named placeholders must match in both languages.
`test_i18n.py` checks catalog coverage, placeholder consistency, persistence,
translated helper errors and preservation of profile data.

## License

MIT; see [LICENSE](LICENSE). FreeRDP and the other external dependencies have
their own licenses and are distributed separately.
