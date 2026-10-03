#!/usr/bin/env python3
"""Set up an Omarchy checkout or install a downloaded release as the user."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
PLUGIN_ID = 'david.rdp'
# Keep legacy markers so existing installations update the same block.
BEGIN = '-- BEGIN Anslutningar (david.rdp)'
END = '-- END Anslutningar (david.rdp)'
FILES = ('manifest.json', 'ProfileEditor.qml', 'TransferPanel.qml', 'PickerWindow.qml',
         'Indicator.qml', 'Language.qml', 'i18n.py', 'translations.json',
         'rdp.py', 'credentials.py', 'krb5.conf', 'rdp-bindings.lua',
         'README.md', 'LICENSE', 'CHANGELOG.md', 'install.py')
BLOCK = (BEGIN + '\n'
         'o.bind("SUPER + R", "DeskQuest", "omarchy-shell shell toggle david.rdp")\n'
         'dofile(os.getenv("HOME") .. "/.config/omarchy/plugins/david.rdp/rdp-bindings.lua")\n'
         + END)
DESKTOP = ('[Desktop Entry]\nType=Application\nName=DeskQuest\n'
           'Comment=RDP till dina datorer\nExec=omarchy-shell shell toggle david.rdp\n'
           'Icon=preferences-desktop-remote-desktop\nTerminal=false\nCategories=Network;RemoteAccess;\n')


def integration_text(text, remove=False):
    counts = text.count(BEGIN), text.count(END)
    if counts not in ((0, 0), (1, 1)):
        raise ValueError('The DeskQuest shortcut block is malformed; nothing was changed.')
    if counts == (1, 1):
        start, end = text.index(BEGIN), text.index(END)
        if end < start:
            raise ValueError('The DeskQuest shortcut block is malformed; nothing was changed.')
        return text[:start] + ('' if remove else BLOCK) + text[end + len(END):]
    return text if remove else text.rstrip() + '\n\n' + BLOCK + '\n'


def check_dependencies(home):
    missing = [name for name in ('python3', 'omarchy', 'omarchy-shell', 'hyprctl',
                                 'xfreerdp3', 'Xwayland', 'systemd-run', 'zenity', 'notify-send')
               if shutil.which(name) is None]
    result = subprocess.run([sys.executable, '-c',
        'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Secret", "1"); '
        'from gi.repository import Gtk, Secret'], capture_output=True, text=True)
    if result.returncode:
        missing.append('Python GObject + GTK 4 + libsecret (python-gobject gtk4 libsecret)')
    if not (home / '.config/hypr/bindings.lua').is_file():
        missing.append('Omarchy user configuration with Hyprland Lua bindings')
    if missing:
        raise ValueError('Missing requirements:\n- ' + '\n- '.join(missing) +
                         '\nSee README.md for the package installation command.')


def backup_config(home, destination):
    config = home / '.config/omarchy-rdp'
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    backup = config / 'backups' / ('setup-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    config.chmod(0o700)
    for p in (home / '.config/hypr/bindings.lua', home / '.config/omarchy/shell.json'):
        if p.exists():
            shutil.copy2(p, backup / p.name)
    for name in FILES:
        if (destination / name).is_file():
            (backup / 'plugin').mkdir(exist_ok=True)
            shutil.copy2(destination / name, backup / 'plugin' / name)
    return backup


def install(source, home):
    destination = home / '.config/omarchy/plugins' / PLUGIN_ID
    bindings = home / '.config/hypr/bindings.lua'
    text = bindings.read_text()
    new_text = integration_text(text)
    for name in FILES:
        if not (source / name).is_file():
            raise ValueError('Incomplete package: missing ' + name)
    in_place = source.resolve() == destination.resolve()
    if not in_place and (destination / '.git').exists():
        raise ValueError('This plugin is Git-managed. Update with omarchy plugin update david.rdp, '
                         'then run install.py from the installed plugin directory.')
    if BEGIN not in text:
        current = json.loads(subprocess.check_output(['hyprctl', '-j', 'binds'], text=True))
        if any(b.get('modmask') == 64 and str(b.get('key', '')).upper() == 'R' for b in current):
            raise ValueError('Super+R is already bound. Resolve that shortcut conflict before installation.')
    backup = backup_config(home, destination)
    destination.mkdir(parents=True, exist_ok=True)
    if not in_place:
        for name in FILES:
            shutil.copy2(source / name, destination / name)
    config = home / '.config/omarchy-rdp'
    profiles = config / 'connections.json'
    if not profiles.exists():
        fd = os.open(profiles, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write('{"version": 1, "connections": []}\n')
    if new_text != text:
        bindings.write_text(new_text)
    apps = home / '.local/share/applications'
    apps.mkdir(parents=True, exist_ok=True)
    (apps / 'omarchy-rdp.desktop').write_text(DESKTOP)
    return destination, backup


def remove_integration(home):
    bindings = home / '.config/hypr/bindings.lua'
    text = bindings.read_text()
    new_text = integration_text(text, remove=True)
    backup = backup_config(home, home / '.config/omarchy/plugins' / PLUGIN_ID)
    if new_text != text:
        bindings.write_text(new_text)
    desktop = home / '.local/share/applications/omarchy-rdp.desktop'
    if desktop.exists() and desktop.read_text() == DESKTOP:
        desktop.unlink()
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='check dependencies without changing files')
    modes.add_argument('--remove-integration', action='store_true', help='remove our shortcuts and launcher, preserving profiles and plugin')
    args = parser.parse_args()
    home = Path.home()
    if os.getuid() == 0 and not args.check:
        raise ValueError('Run this as your desktop user, without sudo.')
    if args.remove_integration:
        print('Integration removed. Backup:', remove_integration(home))
        print('Run hyprctl reload, then hyprctl configerrors.')
        return
    check_dependencies(home)
    if args.check:
        print('Required programs and libraries are available. A running desktop session is needed for setup.')
        print('Password storage also needs an unlocked Secret Service keyring in that session.')
        return
    destination, backup = install(Path(__file__).resolve().parent, home)
    print('Ready:', destination)
    print('Backup:', backup)
    print('Profiles and passwords preserved. Super+R opens the picker; Alt+Tab is contextual in RDP.')
    print('Next: omarchy-shell shell rescanPlugins')
    print('      omarchy plugin enable david.rdp')
    print('      hyprctl reload')
    print('      hyprctl configerrors')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
