#!/usr/bin/env python3
"""Local RDP launcher. Passwords persist only in the system Secret Service."""
import argparse
import contextlib
import fcntl
import html
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import unquote, urlsplit

# Omarchy watches every file in the plugin directory. Import caches would
# trigger a plugin reload just as the first keyring status request opens it.
sys.dont_write_bytecode = True
import i18n
from i18n import tr

CONFIG = Path.home() / '.config/omarchy-rdp'
PROFILES = CONFIG / 'connections.json'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'omarchy-rdp'
HERE = Path(__file__).resolve().parent


class AuthenticationRejected(RuntimeError):
    pass


def keyring():
    from credentials import Keyring
    return Keyring(PROFILES)


def ask_password(profile, **options):
    from credentials import prompt_password
    return prompt_password(profile, **options)


def manage_password(ident):
    profile = profile_by_id(ident)
    vault = keyring()
    answer = ask_password(profile, manage=True, saved=vault.statuses([profile])[ident])
    if answer is None:
        return
    action, password, _remember = answer
    if action == 'clear':
        vault.clear(profile)
        notify(tr('Det sparade lösenordet har tagits bort.'))
    else:
        vault.store(profile, password)
        notify(tr('Lösenordet är sparat i nyckelringen.'))


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, **kwargs)


def dialog(kind, title, text='', extra=()):
    args = ['zenity', '--' + kind, '--title=' + title, '--width=560']
    if text:
        args.append('--text=' + html.escape(text))
    return run(args + list(extra))


def notify(text):
    run(['notify-send', tr('Anslutningar'), text])


def text_value(value, label, required=False, limit=500):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value) or len(value) > limit:
        raise ValueError(tr('{label} innehåller ogiltiga tecken eller är för långt.', label=label))
    value = value.strip()
    if required and not value:
        raise ValueError(tr('{label} måste fyllas i.', label=label))
    return value


def validate(profile):
    if not isinstance(profile, dict):
        raise ValueError(tr('En profil måste vara ett objekt.'))
    ident = profile.get('id', '')
    if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', ident):
        raise ValueError(tr('Ogiltigt profil-id.'))
    result = {'id': ident}
    for key, label in [('name', tr('Datornamn')), ('customer', tr('Kund')), ('host', tr('Adress')), ('username', tr('Användare')), ('vpn', 'VPN'), ('notes', tr('Anteckningar'))]:
        result[key] = text_value(profile.get(key, ''), label, key in ('name', 'host', 'username'))
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*(?::[0-9]{1,5})?', result['host']):
        raise ValueError(tr('Ange IPv4 eller DNS-namn, eventuellt med :port. IPv6 kommer senare.'))
    if ':' in result['host'] and not 1 <= int(result['host'].rsplit(':', 1)[1]) <= 65535:
        raise ValueError(tr('Porten måste vara mellan 1 och 65535.'))
    result['customer'] = result['customer'] or 'Egna maskiner'
    if not isinstance(profile.get('favorite', False), bool):
        raise ValueError(tr('favorite ska vara true eller false.'))
    result['favorite'] = profile.get('favorite', False)
    result['resolution'] = validate_resolution(profile.get('resolution', 'auto'))
    if profile.get('gateway'):
        raise ValueError(tr('Gateway stöds inte i denna första version.'))
    return result


def validate_resolution(value):
    value = text_value(value, tr('Upplösning'), required=True, limit=32).lower().replace('×', 'x').replace(' ', '')
    if value == 'auto':
        return value
    match = re.fullmatch(r'([0-9]{3,4})x([0-9]{3,4})', value)
    if not match or not all(200 <= int(n) <= 8192 for n in match.groups()):
        raise ValueError(tr('Ange upplösning som bredd x höjd, till exempel 1920x1080. Varje mått måste vara 200–8192 pixlar.'))
    return 'x'.join(str(int(n)) for n in match.groups())


def parse_profiles(obj):
    if not isinstance(obj, dict) or type(obj.get('version')) is not int or obj['version'] != 1 or not isinstance(obj.get('connections'), list):
        raise ValueError(tr('Ogiltigt profilformat.'))
    profiles = [validate(p) for p in obj['connections']]
    if len({p['id'] for p in profiles}) != len(profiles):
        raise ValueError(tr('Profil-id får inte förekomma flera gånger.'))
    return profiles


def load_profiles():
    if not PROFILES.exists():
        return []
    return parse_profiles(json.loads(PROFILES.read_text()))


@contextlib.contextmanager
def config_lock():
    CONFIG.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (CONFIG / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save_profiles(profiles):
    write_profile_document(PROFILES, profiles)


def write_profile_document(path, profiles):
    profiles = [validate(p) for p in profiles]
    fd, name = tempfile.mkstemp(prefix='.connections-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump({'version': 1, 'connections': profiles}, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transfer_path(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError(tr('Välj en fil.'))
    if value.startswith('file:'):
        url = urlsplit(value)
        if url.netloc not in ('', 'localhost') or url.query or url.fragment:
            raise ValueError(tr('Välj en lokal fil.'))
        value = unquote(url.path)
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(tr('Välj en lokal fil med fullständig sökväg.'))
    return path


def selected_profiles(profiles, ids):
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
        raise ValueError(tr('Välj minst en anslutning.'))
    if len(set(ids)) != len(ids) or not set(ids) <= {p['id'] for p in profiles}:
        raise ValueError(tr('Urvalet har ändrats. Öppna exporten eller importen igen.'))
    return [p for p in profiles if p['id'] in set(ids)]


def transfer_profiles(payload):
    """Versioned, allowlisted profile transfer. Never contacts the keyring."""
    if not isinstance(payload, dict):
        raise ValueError(tr('Ogiltiga uppgifter.'))
    operation = payload.get('operation')
    if operation == 'preview':
        path = transfer_path(payload.get('path'))
        with path.open('rb') as source:
            data = source.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError(tr('Filen är för stor. Högst 4 MB stöds.'))
        profiles = parse_profiles(json.loads(data))
        if not profiles:
            raise ValueError(tr('Filen innehåller inga anslutningar.'))
        return {'profiles': profiles}
    if operation == 'export':
        path = transfer_path(payload.get('path'))
        if path.resolve() == PROFILES.resolve():
            raise ValueError(tr('Välj en annan fil än appens aktiva anslutningsfil.'))
        profiles = selected_profiles(load_profiles(), payload.get('ids'))
        write_profile_document(path, profiles)
        return {'count': len(profiles)}
    if operation == 'import':
        incoming = parse_profiles(payload.get('document'))
        incoming = selected_profiles(incoming, payload.get('ids'))
        policy = payload.get('conflicts')
        if policy not in ('keep', 'replace'):
            raise ValueError(tr('Välj om befintliga anslutningar ska behållas eller ersättas.'))
        with config_lock():
            current = load_profiles()
            merged = {p['id']: p for p in current}
            added = replaced = skipped = 0
            for profile in incoming:
                ident = profile['id']
                if ident not in merged:
                    added += 1
                elif policy == 'keep':
                    skipped += 1
                    continue
                else:
                    replaced += 1
                merged[ident] = profile
            if added or replaced:
                # Preserve an undo copy before importing; unrelated rows survive.
                backup = CONFIG / 'backups' / ('import-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
                backup.mkdir(parents=True, mode=0o700)
                write_profile_document(backup / 'connections.json', current)
                save_profiles(list(merged.values()))
        return {'added': added, 'replaced': replaced, 'skipped': skipped}
    raise ValueError(tr('Okänd import- eller exportåtgärd.'))


def profile_by_id(ident):
    return next(p for p in load_profiles() if p['id'] == ident)


def save_profile(payload):
    """Create or update one profile, preserving concurrent changes to other rows."""
    if not isinstance(payload, dict) or not isinstance(payload.get('fields'), dict):
        raise ValueError(tr('Ogiltiga profiluppgifter.'))
    ident = payload.get('id', '')
    fields = {key: payload['fields'].get(key, '') for key in
              ('name', 'customer', 'host', 'username', 'vpn', 'notes')}
    if 'resolution' in payload['fields']:
        fields['resolution'] = payload['fields']['resolution']
    with config_lock():
        profiles = load_profiles()
        if ident:
            original = next((p for p in profiles if p['id'] == ident), None)
            if original is None:
                raise ValueError(tr('Profilen finns inte längre. Öppna listan igen.'))
            updated = validate(dict(original, **fields))
            profiles = [updated if p['id'] == ident else p for p in profiles]
        else:
            updated = validate(dict(fields, id=uuid.uuid4().hex[:12], favorite=True))
            profiles.append(updated)
        save_profiles(profiles)
    return updated


def hypr_json(what):
    proc = run(['hyprctl', '-j', what], timeout=4)
    if proc.returncode:
        raise RuntimeError(tr('Kunde inte kontakta Hyprland.'))
    return json.loads(proc.stdout)


def dispatch(expression):
    proc = run(['hyprctl', 'dispatch', expression], timeout=4)
    if proc.returncode or 'error' in proc.stdout.lower():
        raise RuntimeError(tr('Hyprland kunde inte placera RDP-fönstret: ') + proc.stdout.strip())


def window_for(ident):
    return next((w for w in hypr_json('clients') if w.get('class') == 'omarchy-rdp-' + ident or w.get('initialClass') == 'omarchy-rdp-' + ident), None)


def focus_window(window):
    address = window['address']
    if not re.fullmatch(r'0x[0-9a-fA-F]+', address):
        raise ValueError(tr('Ogiltig fönsteradress.'))
    dispatch('hl.dsp.focus({window = ' + json.dumps('address:' + address) + '})')


def place_window(window):
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    with (RUNTIME / 'workspaces.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        used = {w['id'] for w in hypr_json('workspaces')}
        target = next(i for i in range(11, 1000) if i not in used)
        address = window['address']
        if not re.fullmatch(r'0x[0-9a-fA-F]+', address):
            raise ValueError(tr('Ogiltig fönsteradress.'))
        selector = json.dumps('address:' + address)
        dispatch('hl.dsp.window.move({window = ' + selector + ', workspace = "' + str(target) + '", follow = true})')
        dispatch('hl.dsp.window.fullscreen({window = ' + selector + ', mode = "fullscreen"})')
        return target


def build_options(profile, password):
    # FreeRDP's args-from format has exactly one argument per line.
    if any(c in password for c in ('\n', '\r', '\0')):
        raise ValueError(tr('Radbrytningar stöds inte i lösenord i denna version.'))
    username = profile['username']
    domain = ''
    if '\\' in username:
        domain, username = username.split('\\', 1)
    resolution = validate_resolution(profile.get('resolution', 'auto'))
    display_options = ['/dynamic-resolution'] if resolution == 'auto' else [
        '-dynamic-resolution', '/size:' + resolution, '/smart-sizing']
    return [
        '/v:' + profile['host'], '/u:' + username, '/d:' + domain,
        '/p:' + password, '/wm-class:omarchy-rdp-' + profile['id'],
        '/t:' + profile['name'] + ' — ' + profile['customer'],
        '-grab-keyboard', '+clipboard', '/sound',
        '/gfx:AVC420', '/network:auto', '/log-level:WARN',
        '+force-console-callbacks', '/timeout:15000',
    ] + display_options


def certificate_summary(transcript):
    """Extract the CLI certificate block, never the surrounding diagnostic log."""
    transcript = transcript.replace('\r', '')
    headers = list(re.finditer(r'^(?:New Certificate details:|Certificate details(?: for [^\n]+)?:)$', transcript, re.M))
    if not headers:
        raise ValueError(tr('Certifikatuppgifterna kunde inte läsas. Anslutningen avbröts.'))
    header = headers[-1]
    changed = header.group().startswith('New ')
    blocks = transcript[header.end():].split('Old Certificate details:', 1)

    def field(block, key, limit=120):
        match = re.search(r'^\t' + re.escape(key) + r':[ \t]*([^\n]*)$', block, re.M)
        value = match.group(1).strip() if match else ''
        if len(value) > limit or any(ord(c) < 32 for c in value):
            raise ValueError(tr('Certifikatuppgifterna har ett oväntat format. Anslutningen avbröts.'))
        return value

    def fingerprint(block):
        value = field(block, 'Thumbprint', 191)
        if not re.fullmatch(r'[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){19,63}', value):
            raise ValueError(tr('Certifikatets fingeravtryck kunde inte läsas. Anslutningen avbröts.'))
        octets = value.upper().split(':')
        return '\n'.join(':'.join(octets[i:i + 16]) for i in range(0, len(octets), 16))

    current = blocks[0]
    if changed:
        intro = tr('Datorns certifikat har ändrats sedan förra anslutningen. Kontrollera ändringen innan du litar på det nya certifikatet.')
    else:
        intro = tr('Datorns identitet kunde inte verifieras automatiskt. Kontrollera namn och fingeravtryck innan du litar på certifikatet.')
    name = field(current, 'Common Name') or field(current, 'Subject') or tr('(namn saknas)')
    lines = [intro, '', tr('Namn i certifikatet: ') + name]
    for key, label in [('Issuer', tr('Utfärdare')), ('Valid from', tr('Giltigt från')), ('Valid to', tr('Giltigt till'))]:
        value = field(current, key)
        if value:
            lines.append(label + ': ' + value)
    lines.extend(['', (tr('Nytt fingeravtryck:') if changed else tr('Fingeravtryck:')) + '\n' + fingerprint(current)])
    if changed:
        if len(blocks) != 2:
            raise ValueError(tr('Det tidigare certifikatet kunde inte läsas. Anslutningen avbröts.'))
        lines.extend(['', tr('Tidigare fingeravtryck:\n') + fingerprint(blocks[1])])
    return '\n'.join(lines)


def certificate_question(transcript, host=''):
    try:
        summary = certificate_summary(transcript)
    except ValueError as error:
        dialog('error', tr('Kunde inte kontrollera certifikatet'), str(error))
        return False
    if host:
        summary = tr('Ansluter till: ') + host + '\n\n' + summary
    answer = dialog('question', tr('Verifiera fjärrdatorns certifikat'),
                    summary,
                    ['--ok-label=' + tr('Lita på och spara'), '--cancel-label=' + tr('Avbryt'), '--default-cancel'])
    return answer.returncode == 0


def session_error(code, transcript):
    """FreeRDP 3.x X11 exit codes include ordinary disconnects (11/12).

    See client/X11/xf_client.c and xfreerdp.h. An unknown reason alone
    does not justify an error dialog; the picker will reopen either way.
    """
    errors = list(dict.fromkeys(re.findall(r'\b(?:ERRCONNECT|ERRINFO)_[A-Z0-9_]+\b', transcript)))
    user_ended = {'ERRINFO_RPC_INITIATED_DISCONNECT_BY_USER', 'ERRINFO_LOGOFF_BY_USER'}
    # These server reasons can be followed by secondary transport errors during
    # teardown. The explicit user action is the reason the session ended.
    if code in (0, 11, 12, 145) or user_ended.intersection(errors):
        return None
    errors = [error for error in errors if error not in
              {'ERRINFO_SUCCESS', 'ERRCONNECT_SUCCESS', 'ERRCONNECT_CONNECT_CANCELLED'}]
    if code < 0:
        return tr('RDP-klienten avslutades oväntat (signal {signal}).', signal=-code)
    if errors:
        return ', '.join(errors[:4])
    # Documented non-user server reasons, license/protocol and client failures.
    if code in range(1, 11) or code in range(16, 27) or code == 32 or code in range(128, 162):
        return tr('FreeRDP rapporterade ett anslutningsfel (kod {code}).', code=code)
    return None


def show_picker():
    # Reopen, never toggle: the user may already have the picker open.
    try:
        run(['omarchy-shell', 'shell', 'summon', 'david.rdp', '{}'], timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass  # Failure to open the picker must not become an RDP error.


def supervise(profile, password, on_connected=None):
    options = build_options(profile, password)
    read_fd, write_fd = os.pipe()
    master, slave = pty.openpty()
    env = os.environ.copy()
    env['LC_ALL'] = 'C.UTF-8'
    # Avoid the example ATHENA.MIT.EDU realm for local Windows accounts.
    env['KRB5_CONFIG'] = str(HERE / 'krb5.conf')
    proc = subprocess.Popen(['xfreerdp3', '/args-from:fd:' + str(read_fd)],
                            pass_fds=(read_fd,), stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(read_fd)
    os.close(slave)
    with os.fdopen(write_fd, 'wb') as pipe:
        pipe.write(('\n'.join(options) + '\n').encode())
    options.clear()
    transcript = ''
    pending = ''
    placed = False
    placement_failed = False
    declined = False
    connected = False
    began = time.monotonic()
    next_window_check = began
    try:
        # Drain the PTY even after the process exits: its last message often
        # contains the disconnect reason, which must not be lost in a race.
        while True:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 8192).decode('utf-8', errors='replace')
                except OSError:
                    break
                if not chunk:
                    break
                chunk = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', chunk)
                if password:
                    chunk = chunk.replace(password, '[redacted]')
                transcript = (transcript + chunk)[-16000:]
                pending = (pending + chunk)[-16000:]
                if 'Do you trust the above certificate?' in pending and proc.poll() is None:
                    trusted = certificate_question(pending, profile['host'])
                    os.write(master, b'y\n' if trusted else b'n\n')
                    declined = not trusted
                    pending = ''
                    began = time.monotonic()
                elif re.search(r'(Username:|Domain:|Password:|GatewayPassword:)\s*$', pending):
                    proc.terminate()
                    if not connected and re.search(r'(?<![A-Za-z])Password:\s*$', pending):
                        raise AuthenticationRejected(tr('Servern begärde ett nytt lösenord.'))
                    raise RuntimeError(tr('Servern begärde ytterligare inloggning. Kontrollera användarnamn och lösenord i profilen; gateway stöds ännu inte.'))
            elif proc.poll() is not None:
                break
            if proc.poll() is not None:
                continue
            if not placed and not placement_failed and time.monotonic() >= next_window_check:
                next_window_check = time.monotonic() + 0.5
                window = window_for(profile['id'])
                if window:
                    if not connected:
                        connected = True
                        if on_connected:
                            on_connected()
                    try:
                        place_window(window)
                        placed = True
                    except Exception as error:
                        placement_failed = True
                        notify(tr('RDP-fönstret öppnades, men arbetsytan kunde inte väljas: ') + str(error))
            if not placed and not placement_failed and time.monotonic() - began > 75:
                proc.terminate()
                raise RuntimeError(tr('Anslutningen tog för lång tid. Kontrollera Tailscale/VPN, adress och att Windows tillåter fjärrskrivbord.'))
        code = proc.wait(timeout=5)
        if not declined and not connected and (code in (132, 134, 154) or
                re.search(r'\bERRCONNECT_(?:AUTHENTICATION_FAILED|LOGON_FAILURE|WRONG_PASSWORD)\b', transcript)):
            raise AuthenticationRejected(tr('Windows godkände inte användarnamnet eller lösenordet.'))
        detail = session_error(code, transcript)
        if detail and not declined:
            dialog('error', tr('RDP-anslutningen avbröts'), profile['name'] + '\n\n' + detail)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def session(ident):
    profile = profile_by_id(ident)
    existing = window_for(ident)
    if existing:
        focus_window(existing)
        return
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    with (RUNTIME / (ident + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            existing = window_for(ident)
            if existing:
                focus_window(existing)
            else:
                notify(tr('Anslutningen håller redan på att startas.'))
            return
        try:
            connect_with_credentials(profile)
        finally:
            show_picker()


def connect_with_credentials(profile):
    vault = keyring()
    message = ''
    try:
        password = vault.lookup(profile)
    except RuntimeError:
        password = None
        message = tr('Nyckelringen kunde inte öppnas. Du kan ange lösenordet för denna anslutning.')
    was_saved = bool(password)
    for attempt in range(2):
        used_saved = bool(password) and attempt == 0
        remember = False
        if not used_saved:
            answer = ask_password(profile, saved=was_saved, message=message)
            if answer is None:
                return
            _action, password, remember = answer

        def remember_after_connect():
            if used_saved:
                return
            try:
                if remember:
                    vault.store(profile, password)
                elif was_saved:
                    vault.clear(profile)
            except RuntimeError:
                notify(tr('Ansluten, men lösenordet kunde inte uppdateras i nyckelringen. Försök via Lösenord… i väljaren.'))

        try:
            supervise(profile, password, on_connected=remember_after_connect)
            return
        except AuthenticationRejected:
            if not used_saved:
                dialog('error', tr('Inloggningen misslyckades'), tr('Windows godkände inte användarnamnet eller lösenordet.'))
                return
            password = None
            message = tr('Windows godkände inte det sparade lösenordet. Ange ett nytt eller avbryt och kontrollera användarnamnet i profilen.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['list', 'validate', 'save', 'favorite', 'launch', 'session', 'credential-status', 'credential', 'transfer', 'language'])
    parser.add_argument('id', nargs='?')
    parser.add_argument('--profiles', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    global CONFIG, PROFILES
    if args.profiles:
        PROFILES = args.profiles
        CONFIG = PROFILES.parent
    i18n.configure(CONFIG / 'settings.json')
    if args.action == 'language':
        try:
            with config_lock():
                language = i18n.save_language(CONFIG / 'settings.json', args.id)
            print(json.dumps({'ok': True, 'language': language}))
        except (ValueError, OSError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}))
            sys.exit(1)
    elif args.action == 'transfer':
        try:
            payload = json.loads(sys.stdin.readline(8 * 1024 * 1024))
            print(json.dumps(dict(ok=True, **transfer_profiles(payload)), ensure_ascii=False))
        except (ValueError, OSError, RecursionError) as error:
            message = str(error) if isinstance(error, (ValueError, OSError)) and not isinstance(error, (json.JSONDecodeError, UnicodeError)) else tr('Filen kunde inte läsas som en giltig anslutningsexport.')
            print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False))
            sys.exit(1)
    elif args.action == 'credential-status':
        try:
            print(json.dumps({'ok': True, 'saved': keyring().statuses(load_profiles())}))
        except (RuntimeError, ImportError, ValueError, OSError):
            print(json.dumps({'ok': False, 'saved': {}}))
    elif args.action == 'credential':
        manage_password(args.id)
    elif args.action in ('list', 'validate'):
        profiles = load_profiles()
        print(json.dumps(profiles, ensure_ascii=False) if args.action == 'list' else tr('{count} giltiga profiler', count=len(profiles)))
    elif args.action == 'save':
        try:
            profile = save_profile(json.loads(sys.stdin.readline(16384)))
            print(json.dumps({'ok': True, 'profile': profile}, ensure_ascii=False))
        except (ValueError, OSError) as error:
            print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
            sys.exit(1)
    elif args.action == 'favorite':
        with config_lock():
            profiles = load_profiles()
            profile = next(p for p in profiles if p['id'] == args.id)
            profile['favorite'] = not profile['favorite']
            save_profiles(profiles)
    elif args.action == 'launch':
        profile_by_id(args.id)
        proc = run(['systemd-run', '--user', '--collect', '--quiet', '--unit=omarchy-rdp-' + uuid.uuid4().hex[:12],
                    '--property=Type=exec', sys.executable, str(HERE / 'rdp.py'), 'session', args.id])
        if proc.returncode:
            raise RuntimeError(tr('Kunde inte starta RDP-sessionen: ') + proc.stderr.strip())
    else:
        session(args.id)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except (ValueError, RuntimeError, OSError, StopIteration, subprocess.TimeoutExpired) as error:
        dialog('error', tr('Anslutningar'), str(error) or tr('Profilen finns inte längre.'))
        sys.exit(1)
