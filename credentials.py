"""Secret Service storage and a private GTK password prompt.

Passwords never pass through QML, command arguments, files or stdout.
"""
import gi
from i18n import tr

gi.require_version('Secret', '1')
from gi.repository import Secret, GLib


class KeyringError(RuntimeError):
    pass


SCHEMA = Secret.Schema.new('local.david.omarchy-rdp.Password', Secret.SchemaFlags.NONE,
                          {key: Secret.SchemaAttributeType.STRING for key in
                           ('scope', 'profile', 'host', 'username')})


class Keyring:
    def __init__(self, profile_path):
        self.scope = str(profile_path.resolve())

    def attributes(self, profile):
        return dict(scope=self.scope, profile=profile['id'],
                    host=profile['host'], username=profile['username'])

    def call(self, function, *args):
        try:
            return function(*args)
        except GLib.Error:
            raise KeyringError(tr('Nyckelringen kunde inte öppnas. Lås upp den och försök igen.')) from None

    def statuses(self, profiles):
        # Metadata only: no unlocking and no secret values loaded by the picker.
        items = self.call(Secret.password_search_sync, SCHEMA, {'scope': self.scope},
                          Secret.SearchFlags.ALL, None)
        identities = {tuple(item.get_attributes().get(k, '') for k in ('profile', 'host', 'username'))
                      for item in items}
        return {p['id']: (p['id'], p['host'], p['username']) in identities for p in profiles}

    def lookup(self, profile):
        return self.call(Secret.password_lookup_sync, SCHEMA, self.attributes(profile), None)

    def store(self, profile, password):
        check_password(password)
        ok = self.call(Secret.password_store_sync, SCHEMA, self.attributes(profile),
                       Secret.COLLECTION_DEFAULT, 'DeskQuest · ' + profile['name'], password, None)
        if not ok:
            raise KeyringError(tr('Lösenordet sparades inte. Nyckelringen kan vara låst eller upplåsningen avbruten.'))

    def clear(self, profile):
        self.call(Secret.password_clear_sync, SCHEMA, self.attributes(profile), None)
        if self.statuses([profile])[profile['id']]:
            raise KeyringError(tr('Lösenordet kunde inte tas bort. Lås upp nyckelringen och försök igen.'))


def check_password(password):
    if not isinstance(password, str) or not password or any(c in password for c in ('\n', '\r', '\0')):
        raise ValueError(tr('Ange ett lösenord utan radbrytningar.'))


def prompt_password(profile, *, manage=False, saved=False, message=''):
    """Return (action, password, remember) in memory; cancel returns None."""
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, Gio

    answer = None
    app = Gtk.Application(application_id='local.david.rdp.credentials',
                          flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(application):
        nonlocal answer
        window = Gtk.ApplicationWindow(application=application)
        window.set_title((tr('Lösenord · ') if manage else tr('Anslut till ')) + profile['name'])
        window.set_default_size(580, -1)
        window.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + side)(24)
        window.set_child(box)

        def label(text):
            item = Gtk.Label(label=text, xalign=0, wrap=True)
            item.set_max_width_chars(65)
            box.append(item)
            return item

        label(profile['name']).add_css_class('title-2')
        label(profile['username'] + ' · ' + profile['host'])
        if message:
            label(message)
        if manage:
            label(tr('Lösenord sparat i nyckelringen. Ange ett nytt för att byta.') if saved
                  else tr('Spara ett lösenord i nyckelringen för att ansluta direkt.'))
        label(tr('Nytt lösenord') if manage and saved else tr('Lösenord'))
        entry = Gtk.PasswordEntry(show_peek_icon=True)
        entry.set_size_request(-1, 48)
        entry.set_hexpand(True)
        box.append(entry)
        remember = Gtk.CheckButton(label=tr('Kom ihåg lösenordet i nyckelringen'))
        remember.set_active(saved)
        if not manage:
            box.append(remember)
        error = label('')
        error.add_css_class('error')
        error.set_visible(False)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons.set_halign(Gtk.Align.END)
        box.append(buttons)

        def finish(action):
            nonlocal answer
            password = entry.get_text() if action != 'clear' else ''
            if action != 'clear':
                try:
                    check_password(password)
                except ValueError as exc:
                    error.set_label(str(exc)); error.set_visible(True)
                    return
            answer = (action, password, manage or remember.get_active())
            entry.set_text('')
            window.close()

        if manage and saved:
            remove = Gtk.Button(label=tr('Ta bort sparat lösenord'))
            remove.connect('clicked', lambda _: finish('clear'))
            buttons.append(remove)
        cancel = Gtk.Button(label=tr('Avbryt'))
        cancel.connect('clicked', lambda _: window.close())
        buttons.append(cancel)
        accept = Gtk.Button(label=tr('Spara lösenord') if manage else tr('Anslut'))
        accept.add_css_class('suggested-action')
        accept.connect('clicked', lambda _: finish('store' if manage else 'connect'))
        buttons.append(accept)
        entry.connect('activate', lambda _: finish('store' if manage else 'connect'))
        controller = Gtk.EventControllerKey()

        def key_pressed(_controller, keyval, _keycode, _state):
            if keyval == 0xff1b:  # Escape
                window.close()
                return True
            return False

        controller.connect('key-pressed', key_pressed)
        window.add_controller(controller)
        window.present()
        entry.grab_focus()

    app.connect('activate', activate)
    app.run([])
    return answer
