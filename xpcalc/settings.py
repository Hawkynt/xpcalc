"""Persistence for the View menu, stored under the XDG config directory.

Everything here fails quietly: a missing, unreadable or corrupt settings file
just means the defaults are used, which is better than refusing to start.
"""

import json
import os
import tempfile

DEFAULTS = {
    "mode": "scientific",
    "digit_grouping": False,
    "xp_colours": False,
}


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "xpcalc")


def config_file():
    return os.path.join(config_dir(), "settings.json")


def load():
    settings = dict(DEFAULTS)
    try:
        with open(config_file(), encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings
    for key, default in DEFAULTS.items():
        value = stored.get(key, default)
        if isinstance(value, type(default)):
            settings[key] = value
    if settings["mode"] not in ("standard", "scientific"):
        settings["mode"] = DEFAULTS["mode"]
    return settings


def save(settings):
    """Write the settings atomically so a crash cannot truncate the file."""
    path = config_file()
    try:
        os.makedirs(config_dir(), exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=config_dir(), prefix="settings-",
            suffix=".tmp", delete=False)
        try:
            with handle:
                json.dump({key: settings.get(key, default)
                           for key, default in DEFAULTS.items()},
                          handle, indent=2)
                handle.write("\n")
            os.replace(handle.name, path)
        except BaseException:
            try:
                os.unlink(handle.name)
            except OSError:
                pass
            raise
    except OSError:
        pass
