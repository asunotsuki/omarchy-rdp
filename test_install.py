import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch
import zipfile

import install
import package


class InstallationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / 'home'
        self.source = Path(__file__).resolve().parent
        self.bindings = self.home / '.config/hypr/bindings.lua'
        self.bindings.parent.mkdir(parents=True)
        self.original = '-- personal settings\no.bind("SUPER + X", "Test", "true")\n'
        self.bindings.write_text(self.original)
        check = patch.object(install.subprocess, 'check_output', return_value='[]')
        check.start()
        self.addCleanup(check.stop)

    def test_fresh_install_then_in_place_git_setup_preserves_profiles(self):
        destination, backup = install.install(self.source, self.home)
        profiles = self.home / '.config/omarchy-rdp/connections.json'
        self.assertEqual(json.loads(profiles.read_text()), dict(version=1, connections=[]))
        self.assertEqual(profiles.stat().st_mode & 0o777, 0o600)
        self.assertEqual((backup / 'bindings.lua').read_text(), self.original)
        content = '{"version":1,"connections":[{"id":"keep-my-profile"}]}\n'
        profiles.write_text(content)
        (destination / '.git').mkdir()
        (destination / '.git/config').write_text('local git metadata')
        before = self.bindings.read_text()
        install.install(destination, self.home)
        self.assertEqual(profiles.read_text(), content)
        self.assertEqual(self.bindings.read_text(), before)
        self.assertEqual(before.count(install.BEGIN), 1)
        self.assertEqual((destination / '.git/config').read_text(), 'local git metadata')
        self.assertFalse(any((self.home / '.config/omarchy-rdp/backups').rglob('.git')))

    def test_external_copy_cannot_overwrite_git_checkout(self):
        destination, _ = install.install(self.source, self.home)
        (destination / '.git').mkdir()
        before = self.bindings.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Git-managed'):
            install.install(self.source, self.home)
        self.assertEqual(self.bindings.read_bytes(), before)

    def test_shortcut_conflict_and_malformed_block_do_not_write(self):
        with patch.object(install.subprocess, 'check_output', return_value='[{"modmask":64,"key":"R"}]'):
            with self.assertRaisesRegex(ValueError, 'already bound'):
                install.install(self.source, self.home)
        self.assertEqual(self.bindings.read_text(), self.original)
        self.assertFalse((self.home / '.config/omarchy-rdp').exists())
        for text in [install.BEGIN, install.END + '\n' + install.BEGIN,
                     install.BLOCK + '\n' + install.BLOCK]:
            self.bindings.write_text(text)
            with self.assertRaisesRegex(ValueError, 'malformed'):
                install.install(self.source, self.home)
            self.assertEqual(self.bindings.read_text(), text)

    def test_remove_integration_preserves_other_settings_and_profiles(self):
        destination, _ = install.install(self.source, self.home)
        profiles = self.home / '.config/omarchy-rdp/connections.json'
        before = profiles.read_bytes()
        install.remove_integration(self.home)
        self.assertTrue(self.bindings.read_text().startswith(self.original.rstrip()))
        self.assertNotIn(install.BEGIN, self.bindings.read_text())
        self.assertEqual(profiles.read_bytes(), before)
        self.assertTrue((destination / 'rdp.py').exists())
        self.assertFalse((self.home / '.local/share/applications/omarchy-rdp.desktop').exists())

    def test_dependency_check_only_reports_and_does_not_write(self):
        with patch.object(install.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'xfreerdp3'):
                install.check_dependencies(self.home)
        self.assertFalse((self.home / '.config/omarchy-rdp').exists())

    def test_release_contains_only_allowlisted_files_and_installs(self):
        source = self.root / 'source'
        source.mkdir()
        for name in package.RELEASE_FILES:
            shutil.copy2(self.source / name, source / name)
        (source / 'connections.json').write_text('PRIVATE PROFILES')
        private_token = uuid.uuid4().hex
        (source / '.env').write_text(private_token)
        (source / '.qa').mkdir()
        (source / '.qa/private.json').write_text('PRIVATE TEST DATA')
        archive = package.build(source)
        with zipfile.ZipFile(archive) as zipped:
            self.assertEqual({Path(n).name for n in zipped.namelist()}, set(package.RELEASE_FILES))
            self.assertFalse(any(private_token.encode() in zipped.read(n) for n in zipped.namelist()))
            zipped.extractall(self.root / 'extracted')
        destination, _ = install.install(self.root / 'extracted' / archive.stem, self.home)
        self.assertTrue((destination / 'TransferPanel.qml').exists())


if __name__ == '__main__':
    unittest.main()
