"""Shared Swedish/English catalog and non-secret language preference."""
import json
import os
from pathlib import Path
import tempfile

CATALOG = json.loads(Path(__file__).with_name('translations.json').read_text())
LANGUAGE = 'sv'


def configure(path):
    global LANGUAGE
    try:
        settings = json.loads(path.read_text())
        value = settings.get('language') if isinstance(settings, dict) else None
    except (OSError, ValueError):
        value = None
    LANGUAGE = value if value in ('sv', 'en') else 'sv'
    return LANGUAGE


def tr(source, **values):
    text = CATALOG.get(source, source) if LANGUAGE == 'en' else source
    # Replace only placeholders from the template, never braces in user values.
    return text.format(**values) if values else text


def save_language(path, language):
    if language not in ('sv', 'en'):
        raise ValueError(tr('Ogiltigt språkval.'))
    try:
        settings = json.loads(path.read_text())
        if not isinstance(settings, dict):
            settings = {}
    except (OSError, ValueError):
        settings = {}
    settings.update(version=1, language=language)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.settings-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(settings, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return configure(path)
