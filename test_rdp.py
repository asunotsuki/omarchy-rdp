import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('rdp', Path(__file__).with_name('rdp.py'))
rdp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rdp)


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.profile = dict(id='dev-1', name='Windows dev', customer='Eget', host='100.65.2.1', username='DOMÄN\\david', vpn='Tailscale', notes='', favorite=True)

    def test_untrusted_host_and_newline_options_rejected(self):
        for host in ['127.0.0.1\n/cert:ignore', '$(touch /tmp/pwned)', '-option', 'host:65536']:
            with self.subTest(host=host), self.assertRaises(ValueError):
                rdp.validate(dict(self.profile, host=host))
        with self.assertRaises(ValueError):
            rdp.validate(dict(self.profile, username='user\n/p:injected'))
        with self.assertRaises(ValueError):
            rdp.build_options(self.profile, 'password\n/cert:ignore')

    def test_secrets_and_domain_arguments(self):
        options = rdp.build_options(self.profile, 'secret$ ; value')
        self.assertIn('/d:DOMÄN', options)
        self.assertIn('/u:david', options)
        self.assertIn('/p:secret$ ; value', options)
        self.assertIn('-grab-keyboard', options)
        self.assertFalse(any(arg.startswith('/cert:') for arg in options))

    def test_atomic_profile_write_permissions_and_no_password(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rdp, 'CONFIG', Path(tmp)), patch.object(rdp, 'PROFILES', Path(tmp) / 'connections.json'):
            with rdp.config_lock():
                rdp.save_profiles([dict(self.profile, password='must not persist')])
            data = rdp.PROFILES.read_text()
            self.assertNotIn('must not persist', data)
            self.assertNotIn('password', data)
            self.assertEqual(rdp.PROFILES.stat().st_mode & 0o777, 0o600)
            self.assertEqual(rdp.load_profiles()[0]['username'], self.profile['username'])
            bad = json.loads(data)
            bad['connections'].append(bad['connections'][0])
            rdp.PROFILES.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                rdp.load_profiles()

    def test_workspace_allocation_uses_free_workspace(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rdp, 'RUNTIME', Path(tmp)), patch.object(rdp, 'hypr_json', return_value=[{'id': 1}, {'id': 11}, {'id': 13}]), patch.object(rdp, 'dispatch') as dispatch:
            self.assertEqual(rdp.place_window({'address': '0x123abc'}), 12)
            self.assertIn('workspace = "12"', dispatch.call_args_list[0].args[0])
            self.assertIn('fullscreen', dispatch.call_args_list[1].args[0])

    def test_form_create_and_edit_preserve_id_favorite_and_other_profiles(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rdp, 'CONFIG', Path(tmp)), patch.object(rdp, 'PROFILES', Path(tmp) / 'connections.json'):
            rdp.save_profiles([self.profile])
            created = rdp.save_profile({'fields': dict(self.profile, name='New PC')})
            self.assertNotEqual(created['id'], self.profile['id'])
            self.assertTrue(created['favorite'])
            created['favorite'] = False
            rdp.save_profiles([self.profile, created])
            edited = rdp.save_profile({'id': created['id'], 'fields': dict(created, name='Edited PC')})
            self.assertEqual(edited['id'], created['id'])
            self.assertFalse(edited['favorite'])
            self.assertEqual(rdp.load_profiles(), [rdp.validate(self.profile), edited])
            before = rdp.PROFILES.read_bytes()
            for payload in [{'id': 'missing', 'fields': self.profile},
                            {'id': edited['id'], 'fields': dict(edited, host='bad\n/cert:ignore')}]:
                with self.assertRaises(ValueError):
                    rdp.save_profile(payload)
                self.assertEqual(rdp.PROFILES.read_bytes(), before)

    def test_fd_transport_and_certificate_prompt(self):
        # A fake client exercises the real pipe, PTY and certificate handshake.
        # It never connects to a network or opens a remote desktop.
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'xfreerdp3'
            executable.write_text('''#!/usr/bin/env python3
import os,sys
assert len(sys.argv)==2 and sys.argv[1].startswith('/args-from:fd:')
with os.fdopen(int(sys.argv[1].rsplit(':',1)[1])) as stream: options=stream.read()
assert '/p:test-secret\\n' in options
assert '/cert:ignore' not in options
print('Fingerprint: FA:KE',flush=True)
print('Do you trust the above certificate? (Y/T/N) ',end='',flush=True)
answer=sys.stdin.readline().strip()
assert answer=='n'
sys.exit(1)
''')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'PATH': tmp + ':' + os.environ['PATH']}), patch.object(rdp, 'window_for', return_value=None), patch.object(rdp, 'certificate_question', return_value=False) as cert, patch.object(rdp, 'dialog') as dialog:
                rdp.supervise(self.profile, 'test-secret')
                self.assertEqual(cert.call_count, 1)
                self.assertIn('FA:KE', cert.call_args.args[0])
                self.assertNotIn('test-secret', cert.call_args.args[0])
                dialog.assert_not_called()


class ResolutionTest(unittest.TestCase):
    profile = dict(id='test', name='Test', customer='QA', host='127.0.0.1', username='test')

    def test_existing_profiles_remain_automatic(self):
        self.assertEqual(rdp.validate(self.profile)['resolution'], 'auto')
        options = rdp.build_options(self.profile, 'test-value')
        self.assertIn('/dynamic-resolution', options)
        self.assertNotIn('/smart-sizing', options)

    def test_fixed_resolution_disables_server_resizing_and_scales_locally(self):
        options = rdp.build_options(dict(self.profile, resolution='2560 × 1600'), 'test-value')
        self.assertIn('/size:2560x1600', options)
        self.assertIn('-dynamic-resolution', options)
        self.assertIn('/smart-sizing', options)
        self.assertNotIn('/dynamic-resolution', options)

    def test_invalid_dimensions_and_option_injection_are_rejected(self):
        for resolution in ['', None, 1920, '0x1080', '1920x99999', '1920x1080\n/cert:ignore', '/f', '100%x100%', '1920x1080junk']:
            with self.subTest(resolution=resolution), self.assertRaises(ValueError):
                rdp.build_options(dict(self.profile, resolution=resolution), 'test-value')

    def test_save_reload_and_old_editor_preserve_resolution_and_credentials_identity(self):
        from credentials import Keyring
        with tempfile.TemporaryDirectory() as tmp, patch.object(rdp, 'CONFIG', Path(tmp)), patch.object(rdp, 'PROFILES', Path(tmp) / 'connections.json'):
            created = rdp.save_profile({'fields': dict(self.profile, resolution='3440x1440')})
            self.assertEqual(rdp.load_profiles()[0]['resolution'], '3440x1440')
            fields = dict(created); fields.pop('resolution')
            edited = rdp.save_profile({'id': created['id'], 'fields': fields})
            self.assertEqual(edited['resolution'], '3440x1440')
            vault = Keyring(rdp.PROFILES)
            self.assertEqual(vault.attributes(created), vault.attributes(dict(created, resolution='auto')))


class CertificateTest(unittest.TestCase):
    fingerprint = ':'.join(f'{i:02X}' for i in range(32))
    fields = ('\tCommon Name: TEST-PC\n\tSubject: CN=TEST-PC\n'
              '\tIssuer: CN=TEST-PC\n\tValid from: Sep 1 2026 GMT\n'
              '\tValid to: Oct 1 2026 GMT\n\tThumbprint: ' + fingerprint + '\n')

    def test_noisy_log_becomes_bounded_summary_with_complete_fingerprint(self):
        log = ('[WARN] technical noise\n' * 500 +
               'Certificate details for 127.0.0.1:3389 (RDP-Server):\n' + self.fields +
               'The above X.509 certificate could not be verified\n'
               'Do you trust the above certificate? (Y/T/N) ')
        summary = rdp.certificate_summary(log.replace('\n', '\r\n'))
        self.assertLess(len(summary), 650)
        self.assertNotIn('[WARN]', summary)
        self.assertNotIn('X.509', summary)
        self.assertIn('TEST-PC', summary)
        self.assertIn('Oct 1 2026 GMT', summary)
        self.assertIn(self.fingerprint, summary.replace('\n', ':'))

    def test_changed_certificate_retains_warning_and_both_fingerprints(self):
        old = ':'.join(['AA'] * 32)
        log = ('!!!Certificate for 127.0.0.1:3389 (RDP-Server) has changed!!!\n'
               'New Certificate details:\n' + self.fields +
               'Old Certificate details:\n\tThumbprint: ' + old + '\n')
        summary = rdp.certificate_summary(log)
        self.assertIn('har ändrats', summary)
        self.assertIn('Nytt fingeravtryck', summary)
        self.assertIn('Tidigare fingeravtryck', summary)
        self.assertIn(self.fingerprint, summary.replace('\n', ':'))
        self.assertIn(old, summary.replace('\n', ':'))

    def test_unknown_or_truncated_certificate_is_never_approved(self):
        for log in ['unknown format', 'Certificate details:\n\tThumbprint: truncated\n',
                    'New Certificate details:\n' + self.fields]:
            with self.subTest(log=log), patch.object(rdp, 'dialog') as dialog:
                self.assertFalse(rdp.certificate_question(log))
                self.assertEqual(dialog.call_args.args[0], 'error')

    def test_cancel_or_close_declines_and_trust_requires_explicit_acceptance(self):
        log = 'Certificate details:\n' + self.fields
        for code in [0, 1, 5]:
            with self.subTest(code=code), patch.object(rdp, 'dialog') as dialog:
                dialog.return_value.returncode = code
                self.assertEqual(rdp.certificate_question(log, '127.0.0.1'), code == 0)
                self.assertIn('--default-cancel', dialog.call_args.args[3])
                self.assertIn('Ansluter till: 127.0.0.1', dialog.call_args.args[2])


class DisconnectTest(unittest.TestCase):
    def test_user_disconnect_logoff_and_unknown_reason_are_quiet(self):
        for code, log in [(0, ''), (11, ''), (12, ''), (145, ''), (255, ''),
                          (255, 'ERRINFO_RPC_INITIATED_DISCONNECT_BY_USER\nERRCONNECT_CONNECT_TRANSPORT_FAILED'),
                          (255, 'ERRINFO_LOGOFF_BY_USER')]:
            with self.subTest(code=code, log=log):
                self.assertIsNone(rdp.session_error(code, log))

    def test_unexpected_disconnects_and_login_failures_remain_errors(self):
        for code, log in [(147, 'ERRCONNECT_CONNECT_TRANSPORT_FAILED'),
                          (132, 'ERRCONNECT_AUTHENTICATION_FAILED'),
                          (5, 'ERRINFO_DISCONNECTED_BY_OTHER_CONNECTION'),
                          (1, 'ERRINFO_RPC_INITIATED_DISCONNECT'),
                          (2, 'ERRINFO_RPC_INITIATED_LOGOFF'),
                          (3, 'ERRINFO_IDLE_TIMEOUT'), (141, ''), (-11, '')]:
            with self.subTest(code=code, log=log):
                self.assertTrue(rdp.session_error(code, log))

    def test_final_pty_output_is_drained_before_classifying_exit(self):
        profile = dict(id='test', host='127.0.0.1', username='test', name='Test', customer='QA')
        for code, reason, expected_error in [(11, 'ERRINFO_RPC_INITIATED_DISCONNECT_BY_USER', False),
                                             (12, 'ERRINFO_LOGOFF_BY_USER', False),
                                             (147, 'ERRCONNECT_CONNECT_TRANSPORT_FAILED', True)]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                executable = Path(tmp) / 'xfreerdp3'
                executable.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                                      'with os.fdopen(int(sys.argv[1].rsplit(":",1)[1])) as stream: stream.read()\n'
                                      'sys.stdout.write("diagnostic noise\\n" * 2000 + ' + repr(reason) + ' + "\\n")\n'
                                      'sys.stdout.flush()\nsys.exit(' + str(code) + ')\n')
                executable.chmod(0o700)
                with patch.dict(os.environ, {'PATH': tmp + ':' + os.environ['PATH']}), \
                        patch.object(rdp, 'window_for', return_value=None), patch.object(rdp, 'dialog') as dialog:
                    rdp.supervise(profile, 'test-value')
                    self.assertEqual(dialog.call_count, int(expected_error))
                    if expected_error:
                        self.assertIn(reason, dialog.call_args.args[2])

    def test_picker_returns_after_session_or_password_cancel(self):
        profile = dict(id='test', name='Test', username='test', host='127.0.0.1')
        for cancelled in [False, True]:
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(rdp, 'RUNTIME', Path(tmp)), \
                    patch.object(rdp, 'profile_by_id', return_value=profile), \
                    patch.object(rdp, 'window_for', return_value=None), \
                    patch.object(rdp, 'keyring', return_value=MagicMock(lookup=lambda _: None)), \
                    patch.object(rdp, 'ask_password', return_value=None if cancelled else ('connect', 'test-value', False)), \
                    patch.object(rdp, 'supervise') as supervise, patch.object(rdp, 'show_picker') as picker:
                rdp.session('test')
                self.assertEqual(supervise.call_count, int(not cancelled))
                picker.assert_called_once_with()


class CredentialsTest(unittest.TestCase):
    profile = dict(id='test', name='Test', host='127.0.0.1', username='test')

    def test_saved_password_skips_prompt_and_is_not_rewritten(self):
        vault = MagicMock()
        vault.lookup.return_value = 'stored-test-value'
        with patch.object(rdp, 'keyring', return_value=vault), patch.object(rdp, 'ask_password') as prompt, \
                patch.object(rdp, 'supervise') as connect:
            rdp.connect_with_credentials(self.profile)
            prompt.assert_not_called()
            self.assertEqual(connect.call_args.args[1], 'stored-test-value')
            connect.call_args.kwargs['on_connected']()
            vault.store.assert_not_called()

    def test_remember_saves_only_after_connection_and_only_if_selected(self):
        for remember in [False, True]:
            vault = MagicMock()
            vault.lookup.return_value = None
            with self.subTest(remember=remember), patch.object(rdp, 'keyring', return_value=vault), \
                    patch.object(rdp, 'ask_password', return_value=('connect', 'new-test-value', remember)), \
                    patch.object(rdp, 'supervise') as connect:
                rdp.connect_with_credentials(self.profile)
                vault.store.assert_not_called()
                connect.call_args.kwargs['on_connected']()
                self.assertEqual(vault.store.call_count, int(remember))

    def test_rejected_saved_password_prompts_once_and_never_retries_automatically(self):
        vault = MagicMock()
        vault.lookup.return_value = 'old-test-value'
        with patch.object(rdp, 'keyring', return_value=vault), \
                patch.object(rdp, 'ask_password', return_value=('connect', 'new-test-value', True)) as prompt, \
                patch.object(rdp, 'supervise', side_effect=[rdp.AuthenticationRejected(), rdp.AuthenticationRejected()]) as connect, \
                patch.object(rdp, 'dialog') as dialog:
            rdp.connect_with_credentials(self.profile)
            self.assertEqual(connect.call_count, 2)
            prompt.assert_called_once()
            self.assertIn('sparade lösenordet', prompt.call_args.kwargs['message'])
            dialog.assert_called_once()
            vault.store.assert_not_called()

    def test_cancel_after_rejection_makes_no_second_attempt(self):
        vault = MagicMock()
        vault.lookup.return_value = 'old-test-value'
        with patch.object(rdp, 'keyring', return_value=vault), patch.object(rdp, 'ask_password', return_value=None), \
                patch.object(rdp, 'supervise', side_effect=rdp.AuthenticationRejected()) as connect:
            rdp.connect_with_credentials(self.profile)
            connect.assert_called_once()
            vault.store.assert_not_called()

    def test_unavailable_keyring_allows_manual_connection(self):
        vault = MagicMock()
        vault.lookup.side_effect = RuntimeError('locked')
        with patch.object(rdp, 'keyring', return_value=vault), \
                patch.object(rdp, 'ask_password', return_value=('connect', 'manual-test-value', False)) as prompt, \
                patch.object(rdp, 'supervise') as connect:
            rdp.connect_with_credentials(self.profile)
            self.assertIn('inte öppnas', prompt.call_args.kwargs['message'])
            connect.assert_called_once()

    def test_keyring_identity_includes_destination_and_user_without_password(self):
        from credentials import Keyring
        vault = Keyring(Path('/tmp/rdp-unit-profiles.json'))
        original = vault.attributes(self.profile)
        self.assertNotEqual(original, vault.attributes(dict(self.profile, host='other-host')))
        self.assertNotEqual(original, vault.attributes(dict(self.profile, username='other-user')))
        self.assertNotIn('password', original)

    def test_management_store_remove_and_cancel(self):
        for answer in [('store', 'test-value', True), ('clear', '', True), None]:
            vault = MagicMock()
            vault.statuses.return_value = {'test': True}
            with self.subTest(action=answer[0] if answer else 'cancel'), \
                    patch.object(rdp, 'profile_by_id', return_value=self.profile), \
                    patch.object(rdp, 'keyring', return_value=vault), \
                    patch.object(rdp, 'ask_password', return_value=answer), patch.object(rdp, 'notify'):
                rdp.manage_password('test')
                self.assertEqual(vault.store.call_count, int(answer is not None and answer[0] == 'store'))
                self.assertEqual(vault.clear.call_count, int(answer is not None and answer[0] == 'clear'))
                vault.lookup.assert_not_called()

    def test_client_password_retry_becomes_controlled_authentication_rejection(self):
        profile = dict(self.profile, customer='QA')
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / 'xfreerdp3'
            executable.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                                  'with os.fdopen(int(sys.argv[1].rsplit(":",1)[1])) as stream: stream.read()\n'
                                  'print("Password: ",end="",flush=True)\nsys.stdin.readline()\n')
            executable.chmod(0o700)
            with patch.dict(os.environ, {'PATH': tmp + ':' + os.environ['PATH']}), \
                    patch.object(rdp, 'window_for', return_value=None), \
                    self.assertRaises(rdp.AuthenticationRejected):
                rdp.supervise(profile, 'test-value')


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = self.directory / 'config'
        self.config.mkdir()
        self.profiles = self.config / 'connections.json'
        for name, value in [('CONFIG', self.config), ('PROFILES', self.profiles)]:
            patcher = patch.object(rdp, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        vault = patch.object(rdp, 'keyring', side_effect=AssertionError('Transfer must not access secrets'))
        vault.start()
        self.addCleanup(vault.stop)
        self.first = rdp.validate(dict(id='one', name='Dator ett', host='100.65.2.1', username='david',
                                       customer='Eget', favorite=True, resolution='2560x1440'))
        self.second = dict(self.first, id='two', name='Dator två', host='100.65.2.2')
        rdp.save_profiles([self.first, self.second])

    def test_selected_export_roundtrip_and_permissions(self):
        target = self.directory / 'Mina anslutningar åäö.json'
        before = self.profiles.read_bytes()
        result = rdp.transfer_profiles(dict(operation='export', path=target.as_uri(), ids=['two']))
        self.assertEqual(result, {'count': 1})
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(target.read_text()), {'version': 1, 'connections': [self.second]})
        self.assertEqual(self.profiles.read_bytes(), before)
        preview = rdp.transfer_profiles(dict(operation='preview', path=str(target)))
        self.assertEqual(preview['profiles'], [self.second])
        self.profiles.unlink()
        result = rdp.transfer_profiles(dict(operation='import', document=json.loads(target.read_text()),
                                             ids=['two'], conflicts='keep'))
        self.assertEqual(result, dict(added=1, replaced=0, skipped=0))
        self.assertEqual(rdp.load_profiles(), [self.second])

    def test_import_keep_replace_backup_and_unrelated_profiles(self):
        changed = dict(self.first, name='Nytt namn', resolution='1920x1080')
        third = dict(self.second, id='three', name='Dator tre')
        doc = dict(version=1, connections=[changed, third])
        kept = rdp.transfer_profiles(dict(operation='import', document=doc, ids=['one', 'three'], conflicts='keep'))
        self.assertEqual(kept, dict(added=1, replaced=0, skipped=1))
        self.assertEqual(rdp.load_profiles(), [self.first, self.second, third])
        replaced = rdp.transfer_profiles(dict(operation='import', document=doc, ids=['one'], conflicts='replace'))
        self.assertEqual(replaced, dict(added=0, replaced=1, skipped=0))
        self.assertEqual(rdp.load_profiles(), [changed, self.second, third])
        backups = list((self.config / 'backups').glob('import-*/connections.json'))
        self.assertEqual(len(backups), 2)
        self.assertTrue(any(json.loads(p.read_text())['connections'] == [self.first, self.second] for p in backups))
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in backups))

    def test_invalid_import_never_partially_writes(self):
        before = self.profiles.read_bytes()
        for doc in [[], {'version': True, 'connections': []}, {'version': 2, 'connections': []},
                    {'version': 1, 'connections': [self.first, self.first]},
                    {'version': 1, 'connections': [dict(self.first, name='Changed'), dict(self.second, host='bad\n/p:secret')]}]:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                rdp.transfer_profiles(dict(operation='import', document=doc, ids=['one'], conflicts='replace'))
            self.assertEqual(self.profiles.read_bytes(), before)
        self.assertFalse((self.config / 'backups').exists())

    def test_secrets_are_discarded_on_preview_import_and_export(self):
        dirty = dict(self.first, password='DO-NOT-COPY', secret='DO-NOT-COPY', credentials={'token': 'DO-NOT-COPY'})
        source = self.directory / 'input.json'
        source.write_text(json.dumps(dict(version=1, connections=[dirty], passwords='DO-NOT-COPY')))
        preview = rdp.transfer_profiles(dict(operation='preview', path=str(source)))
        self.assertNotIn('DO-NOT-COPY', json.dumps(preview))
        rdp.transfer_profiles(dict(operation='import', document=dict(version=1, connections=[dirty]), ids=['one'], conflicts='replace'))
        self.assertNotIn('DO-NOT-COPY', self.profiles.read_text())
        self.profiles.write_text(json.dumps(dict(version=1, connections=[dirty])))
        target = self.directory / 'output.json'
        rdp.transfer_profiles(dict(operation='export', path=str(target), ids=['one']))
        self.assertNotIn('DO-NOT-COPY', target.read_text())

    def test_export_invalid_selection_and_active_file_are_protected(self):
        before = self.profiles.read_bytes()
        alias = self.directory / 'alias.json'
        alias.symlink_to(self.profiles)
        for path, ids in [(self.profiles, ['one']), (alias, ['one']),
                          (self.directory / 'out.json', []), (self.directory / 'out.json', ['missing'])]:
            with self.subTest(path=path, ids=ids), self.assertRaises(ValueError):
                rdp.transfer_profiles(dict(operation='export', path=str(path), ids=ids))
        self.assertEqual(self.profiles.read_bytes(), before)
        self.assertFalse((self.directory / 'out.json').exists())


if __name__ == '__main__':
    unittest.main()
