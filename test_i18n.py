import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import i18n
import rdp


class LanguageTest(unittest.TestCase):
    def tearDown(self):
        i18n.LANGUAGE = 'sv'

    def test_saved_language_survives_and_preserves_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            self.assertEqual(i18n.configure(path), 'sv')
            path.write_text('{"other":42}')
            self.assertEqual(i18n.save_language(path, 'en'), 'en')
            self.assertEqual(i18n.tr('Språk'), 'Language')
            self.assertEqual(json.loads(path.read_text())['other'], 42)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                i18n.save_language(path, 'unsupported')
            self.assertEqual(path.read_bytes(), before)
            i18n.save_language(path, 'sv')
            self.assertEqual(i18n.tr('Språk'), 'Språk')

    def test_invalid_preferences_fall_back_to_swedish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            for data in ['broken', '[]', '{"language":"xx"}']:
                path.write_text(data)
                self.assertEqual(i18n.configure(path), 'sv')

    def test_english_validation_does_not_translate_profile_data(self):
        profile = dict(id='example', name='Datornamn', customer='Egna maskiner',
                       username='david', host='192.0.2.10', notes='Anslutningar')
        original = rdp.validate(profile)
        i18n.LANGUAGE = 'en'
        self.assertEqual(rdp.validate(profile), original)
        with self.assertRaisesRegex(ValueError, 'Computer name is required'):
            rdp.validate(dict(profile, name=''))
        with self.assertRaisesRegex(ValueError, 'Enter a resolution'):
            rdp.validate_resolution('invalid')
        from credentials import check_password
        with self.assertRaisesRegex(ValueError, 'Enter a password'):
            check_password('')

    def test_helper_loads_language_and_does_not_touch_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            profiles = Path(tmp) / 'connections.json'
            profiles.write_text('{"version":1,"connections":[]}')
            before = profiles.read_bytes()
            command = [sys.executable, str(Path(rdp.__file__)), 'language', 'en', '--profiles', str(profiles)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), dict(ok=True, language='en'))
            result = subprocess.run([sys.executable, str(Path(rdp.__file__)), 'save', '--profiles', str(profiles)],
                                    input='{"fields":{}}\n', capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['error'], 'Computer name is required.')
            self.assertEqual(profiles.read_bytes(), before)

    def test_catalog_placeholders_and_literal_calls_are_complete(self):
        for source, translated in i18n.CATALOG.items():
            self.assertTrue(translated)
            self.assertEqual(set(re.findall(r'\{\w+\}', source)), set(re.findall(r'\{\w+\}', translated)), source)
        directory = Path(__file__).parent
        for name in ['rdp.py', 'credentials.py']:
            for node in ast.walk(ast.parse((directory / name).read_text())):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr':
                    self.assertIn(node.args[0].value, i18n.CATALOG)
        for name in ['PickerWindow.qml', 'ProfileEditor.qml', 'TransferPanel.qml', 'Indicator.qml', 'Language.qml']:
            for value in re.findall(r'\.tr\(("(?:[^"\\]|\\.)*")', (directory / name).read_text()):
                self.assertIn(json.loads(value), i18n.CATALOG)
        i18n.LANGUAGE = 'en'
        self.assertEqual(i18n.tr('{label} måste fyllas i.', label='{untouched}'), '{untouched} is required.')
        self.assertEqual(i18n.tr(r'Användarnamn, e-post eller DOMÄN\namn'), r'Username, email or DOMAIN\name')


if __name__ == '__main__':
    unittest.main()
