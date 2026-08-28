import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from xpcalc import settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults_when_missing(self):
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_round_trip(self):
        settings.save({"mode": "standard", "digit_grouping": True,
                       "xp_colours": True})
        self.assertEqual(settings.load(), {"mode": "standard",
                                           "digit_grouping": True,
                                           "xp_colours": True})

    def test_path_follows_xdg(self):
        self.assertEqual(settings.config_file(),
                         os.path.join(self.tmp, "xpcalc", "settings.json"))

    def test_corrupt_file_falls_back(self):
        os.makedirs(settings.config_dir())
        with open(settings.config_file(), "w") as handle:
            handle.write("not json {{{")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_wrong_types_ignored(self):
        os.makedirs(settings.config_dir())
        with open(settings.config_file(), "w") as handle:
            json.dump({"mode": 42, "digit_grouping": "yes"}, handle)
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_unknown_mode_ignored(self):
        settings.save(dict(settings.DEFAULTS, mode="programmer"))
        self.assertEqual(settings.load()["mode"], "scientific")

    def test_partial_file_keeps_defaults(self):
        os.makedirs(settings.config_dir())
        with open(settings.config_file(), "w") as handle:
            json.dump({"xp_colours": True}, handle)
        loaded = settings.load()
        self.assertTrue(loaded["xp_colours"])
        self.assertEqual(loaded["mode"], "scientific")

    def test_unwritable_dir_is_silent(self):
        os.makedirs(settings.config_dir())
        os.chmod(settings.config_dir(), 0o500)
        try:
            settings.save(dict(settings.DEFAULTS, mode="standard"))
        finally:
            os.chmod(settings.config_dir(), 0o700)

    def test_no_temp_files_left_behind(self):
        settings.save(settings.DEFAULTS)
        self.assertEqual(os.listdir(settings.config_dir()), ["settings.json"])


if __name__ == "__main__":
    unittest.main()
