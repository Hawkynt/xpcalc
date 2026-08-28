"""GTK 3 front end laid out like the Windows XP calculator.

GTK 3 is what Thunar/Xfce 4.20 uses, so the widgets pick up the same GTK
theme.  Nothing here hardcodes colours unless View -> XP button colours is
switched on.
"""

import argparse
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from . import __version__, settings  # noqa: E402
from .engine import Engine  # noqa: E402

APP_NAME = "Calculator"
APP_ID = "xpcalc"

CSS = b"""
#display {
    font-family: monospace;
    font-size: 14pt;
    padding: 2px 6px;
}
#expression {
    font-size: 8pt;
    min-height: 15px;
    padding: 0 6px;
}
#indicator {
    font-size: 8pt;
    min-width: 26px;
    min-height: 16px;
    padding: 0 2px;
}
button {
    padding: 0;
    font-size: 9pt;
}
"""

XP_COLOURS = b"""
button.digit  { color: #0000c0; }
button.op     { color: #c00000; }
button.mem    { color: #c00000; }
button.edit   { color: #c00000; }
button.func   { color: #000080; }
"""


class Button(Gtk.Button):
    def __init__(self, label, css=None, width=32, height=26, tooltip=None):
        super().__init__(label=label)
        self.set_can_focus(False)
        self.set_size_request(width, height)
        if css:
            self.get_style_context().add_class(css)
        if tooltip:
            self.set_tooltip_text(tooltip)


class StatisticsBox(Gtk.Window):
    """The little data window the Sta button opens."""

    def __init__(self, parent, engine, on_change):
        super().__init__(title="Statistics Box")
        self.engine = engine
        self.on_change = on_change
        self.set_transient_for(parent)
        self.set_default_size(200, 190)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(4)
        self.add(box)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        self.store = Gtk.ListStore(str)
        self.view = Gtk.TreeView(model=self.store, headers_visible=False)
        column = Gtk.TreeViewColumn("", Gtk.CellRendererText(), text=0)
        self.view.append_column(column)
        scroll.add(self.view)
        box.pack_start(scroll, True, True, 0)

        self.count = Gtk.Label(label="n=0", xalign=0.0)
        box.pack_start(self.count, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3,
                      homogeneous=True)
        for label, handler in (("RET", self._ret), ("LOAD", self._load),
                               ("CD", self._cd), ("CAD", self._cad)):
            button = Button(label, height=24)
            button.connect("clicked", handler)
            row.pack_start(button, True, True, 0)
        box.pack_start(row, False, False, 0)

        self.connect("delete-event", self._hide)
        self.refresh()

    def _hide(self, *_a):
        self.hide()
        return True

    def refresh(self):
        self.store.clear()
        for value in self.engine.stats:
            self.store.append([self.engine.format(value)])
        self.count.set_text("n=%d" % len(self.engine.stats))

    def _selected(self):
        model, treeiter = self.view.get_selection().get_selected()
        if treeiter is None:
            return None
        return int(model.get_path(treeiter)[0])

    def _ret(self, *_a):
        self.get_transient_for().present()

    def _load(self, *_a):
        index = self._selected()
        if index is not None:
            self.engine.paste_text(self.engine.format(self.engine.stats[index]))
            self.on_change()

    def _cd(self, *_a):
        index = self._selected()
        if index is not None:
            del self.engine.stats[index]
            self.refresh()

    def _cad(self, *_a):
        self.engine.stat_clear()
        self.refresh()


class Calculator(Gtk.Window):
    def __init__(self, mode=None):
        super().__init__(title=APP_NAME)
        self.engine = Engine()
        self.stat_window = None
        self.stat_buttons = []
        self.buttons = {}
        self._colour_provider = None
        self.settings = settings.load()
        if mode is not None:
            self.settings["mode"] = mode
        self._applying = True     # suppress saving while restoring

        self.set_resizable(False)
        theme = Gtk.IconTheme.get_default()
        for name in (APP_ID, "accessories-calculator"):
            if theme.has_icon(name):
                self.set_icon_name(name)
                break

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        outer.pack_start(self._build_menu(), False, False, 0)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.body.set_border_width(5)
        outer.pack_start(self.body, True, True, 0)

        # the running calculation, above the result like a paper tape
        self.expression = Gtk.Label(label="", xalign=1.0)
        self.expression.set_name("expression")
        self.expression.get_style_context().add_class("dim-label")
        self.expression.set_ellipsize(Pango.EllipsizeMode.START)
        self.expression.set_max_width_chars(1)   # ellipsize instead of growing
        self.expression.set_selectable(True)
        self.expression.set_can_focus(False)
        self.body.pack_start(self.expression, False, False, 0)

        self.display = Gtk.Entry()
        self.display.set_name("display")
        self.display.set_alignment(1.0)
        self.display.set_editable(False)
        self.display.set_can_focus(False)
        self.display.set_width_chars(24)
        self.body.pack_start(self.display, False, False, 0)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.body.pack_start(self.panel, True, True, 0)

        self.connect("key-press-event", self._on_key)
        self.connect("destroy", Gtk.main_quit)

        self.set_mode(self.settings["mode"])
        self.grouping_item.set_active(self.settings["digit_grouping"])
        self.colours_item.set_active(self.settings["xp_colours"])
        self._applying = False

    # ================================================================
    # menu
    # ================================================================
    def _build_menu(self):
        bar = Gtk.MenuBar()

        edit = Gtk.MenuItem(label="Edit")
        menu = Gtk.Menu()
        for label, accel, handler in (
                ("Copy", "<Control>c", lambda *_a: self._copy()),
                ("Paste", "<Control>v", lambda *_a: self._paste())):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", handler)
            menu.append(item)
        edit.set_submenu(menu)
        bar.append(edit)

        view = Gtk.MenuItem(label="View")
        menu = Gtk.Menu()
        self.mode_items = {}
        group = None
        for label, mode in (("Standard", "standard"), ("Scientific", "scientific")):
            item = Gtk.RadioMenuItem(label=label, group=group)
            group = item
            item.connect("toggled", self._on_mode_item, mode)
            menu.append(item)
            self.mode_items[mode] = item
        menu.append(Gtk.SeparatorMenuItem())

        self.grouping_item = Gtk.CheckMenuItem(label="Digit grouping")
        self.grouping_item.connect("toggled", self._on_grouping)
        menu.append(self.grouping_item)

        self.colours_item = Gtk.CheckMenuItem(label="XP button colours")
        self.colours_item.connect("toggled", self._on_colours)
        menu.append(self.colours_item)
        view.set_submenu(menu)
        bar.append(view)

        help_item = Gtk.MenuItem(label="Help")
        menu = Gtk.Menu()
        about = Gtk.MenuItem(label="About Calculator")
        about.connect("activate", self._on_about)
        menu.append(about)
        help_item.set_submenu(menu)
        bar.append(help_item)
        return bar

    def _on_mode_item(self, item, mode):
        if item.get_active() and mode != self.engine.mode:
            self.set_mode(mode)

    def _on_grouping(self, item):
        self.engine.grouping = item.get_active()
        self.refresh()
        self._save()

    def _on_colours(self, item):
        screen = Gdk.Screen.get_default()
        if item.get_active():
            self._colour_provider = Gtk.CssProvider()
            self._colour_provider.load_from_data(XP_COLOURS)
            Gtk.StyleContext.add_provider_for_screen(
                screen, self._colour_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        elif self._colour_provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(
                screen, self._colour_provider)
            self._colour_provider = None
        self._save()

    def _on_about(self, *_a):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_comments("A Windows XP style calculator for GTK 3.\n"
                            "32 significant digits, scientific and "
                            "programmer modes.")
        dialog.set_version(__version__)
        dialog.set_logo_icon_name(self.get_icon_name() or APP_ID)
        dialog.run()
        dialog.destroy()

    # ================================================================
    # layout
    # ================================================================
    def set_mode(self, mode):
        self.engine.set_mode(mode)
        self.mode_items[mode].set_active(True)
        for child in self.panel.get_children():
            self.panel.remove(child)
        self.stat_buttons = []
        self.buttons = {}
        if mode == "standard":
            self._build_standard()
        else:
            self._build_scientific()
        self.panel.show_all()
        self.resize(1, 1)
        self.refresh()
        self._save()

    def _save(self):
        """Remember the View menu across sessions."""
        if self._applying:
            return
        settings.save({
            "mode": self.engine.mode,
            "digit_grouping": self.grouping_item.get_active(),
            "xp_colours": self.colours_item.get_active(),
        })

    def _indicator(self):
        label = Gtk.Label(label="")
        label.set_name("indicator")
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        frame.add(label)
        return frame, label

    def _edit_buttons(self, width=64):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, handler, tip in (
                ("Backspace", self.engine.backspace, "Remove the last digit"),
                ("CE", self.engine.clear_entry, "Clear the displayed value"),
                ("C", self.engine.clear_all, "Clear the calculation")):
            button = Button(label, "edit", width=width, height=26, tooltip=tip)
            button.connect("clicked", self._run, handler)
            box.pack_start(button, label == "Backspace", True, 0)
        return box

    def _grid(self, rows, spacing=3):
        grid = Gtk.Grid(row_spacing=spacing, column_spacing=spacing)
        for row, items in enumerate(rows):
            for col, spec in enumerate(items):
                if spec is None:
                    continue
                grid.attach(self._make(spec), col, row, 1, 1)
        return grid

    def _make(self, spec):
        label, css, action = spec
        button = Button(label, css)
        button.connect("clicked", self._run, action)
        self.buttons[label] = button
        if label in ("Ave", "Sum", "s", "Dat"):
            button.set_sensitive(bool(self.stat_window))
            self.stat_buttons.append(button)
        return button

    # -- standard -----------------------------------------------------
    def _build_standard(self):
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        frame, self.mem_label = self._indicator()
        top.pack_start(frame, False, False, 0)
        top.pack_end(self._edit_buttons(width=72), False, False, 0)
        self.panel.pack_start(top, False, False, 0)
        self.paren_label = None

        E = self.engine
        digit = lambda d: (lambda: E.digit(d))
        rows = [
            [("MC", "mem", lambda: E.memory_op("MC"))] + self._numrow("789") +
            [("/", "op", lambda: E.operator("/")),
             ("sqrt", "func", lambda: E.unary("sqrt"))],
            [("MR", "mem", lambda: E.memory_op("MR"))] + self._numrow("456") +
            [("*", "op", lambda: E.operator("*")),
             ("%", "func", E.percent)],
            [("MS", "mem", lambda: E.memory_op("MS"))] + self._numrow("123") +
            [("-", "op", lambda: E.operator("-")),
             ("1/x", "func", lambda: E.unary("1/x"))],
            [("M+", "mem", lambda: E.memory_op("M+")),
             ("0", "digit", digit("0")),
             ("+/-", "digit", E.sign),
             (".", "digit", E.point),
             ("+", "op", lambda: E.operator("+")),
             ("=", "op", E.equals)],
        ]
        grid = Gtk.Grid(row_spacing=3, column_spacing=3)
        for r, items in enumerate(rows):
            for c, spec in enumerate(items):
                button = self._make(spec)
                button.set_size_request(40, 30)
                grid.attach(button, c, r, 1, 1)
        self.panel.pack_start(grid, True, True, 0)

    def _numrow(self, digits):
        E = self.engine
        return [(d, "digit", (lambda d=d: E.digit(d))) for d in digits]

    # -- scientific ---------------------------------------------------
    def _build_scientific(self):
        E = self.engine

        # radio row: number base | angle unit (or word size in non-decimal)
        bases = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        group = None
        self.base_radios = {}
        for label, base in (("Hex", 16), ("Dec", 10), ("Oct", 8), ("Bin", 2)):
            radio = Gtk.RadioButton.new_with_label_from_widget(group, label)
            radio.set_can_focus(False)
            group = group or radio
            radio.connect("toggled", self._on_base, base)
            bases.pack_start(radio, False, False, 0)
            self.base_radios[base] = radio

        self.angle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        group = None
        self.angle_radios = {}
        for label, angle in (("Degrees", "deg"), ("Radians", "rad"),
                             ("Grads", "grad")):
            radio = Gtk.RadioButton.new_with_label_from_widget(group, label)
            radio.set_can_focus(False)
            group = group or radio
            radio.connect("toggled", self._on_angle, angle)
            self.angle_box.pack_start(radio, False, False, 0)
            self.angle_radios[angle] = radio

        self.word_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        group = None
        self.word_radios = {}
        for label, word in (("Qword", "qword"), ("Dword", "dword"),
                            ("Word", "word"), ("Byte", "byte")):
            radio = Gtk.RadioButton.new_with_label_from_widget(group, label)
            radio.set_can_focus(False)
            group = group or radio
            radio.connect("toggled", self._on_word, word)
            self.word_box.pack_start(radio, False, False, 0)
            self.word_radios[word] = radio

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row1.pack_start(bases, False, False, 0)
        row1.pack_end(self.word_box, False, False, 0)
        row1.pack_end(self.angle_box, False, False, 0)
        self.panel.pack_start(row1, False, False, 0)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.inv = Gtk.CheckButton(label="Inv")
        self.hyp = Gtk.CheckButton(label="Hyp")
        for check in (self.inv, self.hyp):
            check.set_can_focus(False)
            row2.pack_start(check, False, False, 0)

        indicators = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        frame, self.paren_label = self._indicator()
        indicators.pack_start(frame, False, False, 0)
        frame, self.mem_label = self._indicator()
        indicators.pack_start(frame, False, False, 0)
        row2.pack_start(indicators, False, False, 12)
        row2.pack_end(self._edit_buttons(width=64), False, False, 0)
        self.panel.pack_start(row2, False, False, 0)

        digit = lambda d: (lambda: E.digit(d))
        unary = lambda name: (lambda: E.unary(name, self._take_inv(),
                                              self.hyp.get_active()))
        stat = lambda kind: (lambda: E.stat_result(kind, self._take_inv()))

        rows = [
            [("Sta", "func", self._toggle_stats),
             ("F-E", "func", E.toggle_fe),
             ("(", "func", E.open_paren),
             (")", "func", E.close_paren),
             ("MC", "mem", lambda: E.memory_op("MC")),
             ("7", "digit", digit("7")), ("8", "digit", digit("8")),
             ("9", "digit", digit("9")),
             ("/", "op", lambda: E.operator("/")),
             ("Mod", "op", lambda: E.operator("Mod")),
             ("And", "op", lambda: E.operator("And"))],
            [("Ave", "func", stat("Ave")),
             ("dms", "func", unary("dms")),
             ("Exp", "func", E.exp_entry),
             ("ln", "func", unary("ln")),
             ("MR", "mem", lambda: E.memory_op("MR")),
             ("4", "digit", digit("4")), ("5", "digit", digit("5")),
             ("6", "digit", digit("6")),
             ("*", "op", lambda: E.operator("*")),
             ("Or", "op", lambda: E.operator("Or")),
             ("Xor", "op", lambda: E.operator("Xor"))],
            [("Sum", "func", stat("Sum")),
             ("sin", "func", unary("sin")),
             ("x^y", "func",
              lambda: E.operator("root" if self._take_inv() else "^")),
             ("log", "func", unary("log")),
             ("MS", "mem", lambda: E.memory_op("MS")),
             ("1", "digit", digit("1")), ("2", "digit", digit("2")),
             ("3", "digit", digit("3")),
             ("-", "op", lambda: E.operator("-")),
             ("Lsh", "op",
              lambda: E.operator("Rsh" if self._take_inv() else "Lsh")),
             ("Not", "op", lambda: E.unary("Not"))],
            [("s", "func", stat("s")),
             ("cos", "func", unary("cos")),
             ("x^3", "func", unary("x^3")),
             ("n!", "func", unary("n!")),
             ("M+", "mem", lambda: E.memory_op("M+")),
             ("0", "digit", digit("0")),
             ("+/-", "digit", E.sign),
             (".", "digit", E.point),
             ("+", "op", lambda: E.operator("+")),
             ("=", "op", E.equals),
             ("Int", "op", unary("Int"))],
            [("Dat", "func", self._stat_add),
             ("tan", "func", unary("tan")),
             ("x^2", "func", unary("x^2")),
             ("1/x", "func", unary("1/x")),
             ("pi", "func", unary("pi"))] +
            [(d, "digit", digit(d)) for d in "ABCDEF"],
        ]
        self.panel.pack_start(self._grid(rows), True, True, 0)
        self.base_radios[self.engine.base].set_active(True)
        self._sync_radios()

    # ================================================================
    # actions
    # ================================================================
    def _run(self, _widget, action):
        action()
        self.refresh()

    def _take_inv(self):
        """Read the Inv checkbox; like XP it unticks itself once used."""
        active = self.inv.get_active()
        if active:
            self.inv.set_active(False)
        return active

    def _stat_add(self):
        self.engine.stat_add()
        if self.stat_window:
            self.stat_window.refresh()

    def _toggle_stats(self):
        if self.stat_window is None:
            self.stat_window = StatisticsBox(self, self.engine, self.refresh)
            for button in self.stat_buttons:
                button.set_sensitive(True)
        self.stat_window.show_all()
        self.stat_window.present()

    def _on_base(self, radio, base):
        if not radio.get_active():
            return
        self.engine.set_base(base)
        self._sync_radios()
        self.refresh()

    def _on_angle(self, radio, angle):
        if radio.get_active():
            self.engine.set_angle(angle)

    def _on_word(self, radio, word):
        if radio.get_active():
            self.engine.set_word(word)
            self.refresh()

    #: functions the XP calculator greys out outside base 10
    DECIMAL_ONLY = (".", "Exp", "F-E", "dms", "sin", "cos", "tan", "ln",
                    "log", "pi")

    def _sync_radios(self):
        """Dec shows Degrees/Radians/Grads, the other bases show word sizes."""
        if self.engine.mode != "scientific":
            return
        base = self.engine.base
        decimal = base == 10
        self.angle_box.set_visible(decimal)
        self.angle_box.set_no_show_all(not decimal)
        self.word_box.set_visible(not decimal)
        self.word_box.set_no_show_all(decimal)
        for label in self.DECIMAL_ONLY:
            if label in self.buttons:
                self.buttons[label].set_sensitive(decimal)
        for check in (self.inv, self.hyp):
            check.set_sensitive(decimal)
        for digit, button in self.buttons.items():
            if len(digit) == 1 and digit in "0123456789ABCDEF":
                button.set_sensitive("0123456789ABCDEF".index(digit) < base)

    def _copy(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.engine.copy_text(), -1)

    def _paste(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text()
        if text:
            self.engine.paste_text(text)
            self.refresh()

    def refresh(self):
        self.display.set_text(self.engine.display)
        self.expression.set_text(self.engine.expression)
        if self.mem_label is not None:
            self.mem_label.set_text("M" if self.engine.memory_set else "")
        if self.paren_label is not None:
            depth = self.engine.paren_depth
            self.paren_label.set_text("(" * min(depth, 3) if depth else "")
        if self.stat_window is not None:
            self.stat_window.refresh()

    # ================================================================
    # keyboard
    # ================================================================
    def _on_key(self, _widget, event):
        E = self.engine
        name = Gdk.keyval_name(event.keyval)
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl:
            if name in ("c", "C"):
                self._copy()
                return True
            if name in ("v", "V"):
                self._paste()
                return True
            return False

        char = event.string
        scientific = E.mode == "scientific"
        handled = True

        if char and char.isdigit() and int(char) < max(E.base, 10):
            E.digit(char)
        elif char and char.upper() in "ABCDEF" and E.base == 16:
            E.digit(char.upper())
        elif char in (".", ","):
            E.point()
        elif char in ("+", "-", "*", "/"):
            E.operator(char)
        elif char == "%":
            E.percent()
        elif name in ("Return", "KP_Enter") or char == "=":
            E.equals()
        elif name == "BackSpace":
            E.backspace()
        elif name == "Escape":
            E.clear_all()
        elif name == "Delete":
            E.clear_entry()
        elif char == "@":
            E.unary("sqrt")
        elif char == "!":
            E.unary("n!")
        elif char == "(" and scientific:
            E.open_paren()
        elif char == ")" and scientific:
            E.close_paren()
        elif char == "r":
            E.unary("1/x")
        elif char in ("n", "l", "s", "o", "t", "y", "x", "i", "h") and scientific:
            if char == "i":
                self.inv.set_active(not self.inv.get_active())
            elif char == "h":
                self.hyp.set_active(not self.hyp.get_active())
            elif char == "y":
                E.operator("root" if self._take_inv() else "^")
            else:
                inv, hyp = self._take_inv(), self.hyp.get_active()
                E.unary({"n": "ln", "l": "log", "s": "sin", "o": "cos",
                         "t": "tan", "x": "x^2"}[char], inv, hyp)
        elif name in ("F5", "F6", "F7", "F8") and scientific:
            self.base_radios[{"F5": 16, "F6": 10, "F7": 8, "F8": 2}[name]] \
                .set_active(True)
        elif name in ("F2", "F3", "F4", "F12") and scientific:
            if E.base == 10:
                mapping = {"F2": "deg", "F3": "rad", "F4": "grad"}
                if name in mapping:
                    self.angle_radios[mapping[name]].set_active(True)
            else:
                mapping = {"F12": "qword", "F2": "dword", "F3": "word",
                           "F4": "byte"}
                self.word_radios[mapping[name]].set_active(True)
        else:
            handled = False

        if handled:
            self.refresh()
        return handled


def main(argv=None):
    argv = sys.argv if argv is None else argv
    parser = argparse.ArgumentParser(
        prog=APP_ID, description="A Windows XP style calculator for GTK 3.")
    parser.add_argument("--standard", dest="mode", action="store_const",
                        const="standard",
                        help="start in standard mode")
    parser.add_argument("--scientific", dest="mode", action="store_const",
                        const="scientific",
                        help="start in scientific mode")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv[1:])

    # Sets WM_CLASS on X11 and the app_id on Wayland, so window managers can
    # match the window to the .desktop file (StartupWMClass=xpcalc).
    GLib.set_prgname(APP_ID)
    GLib.set_application_name(APP_NAME)
    Gdk.set_program_class("Xpcalc")

    win = Calculator(mode=args.mode)
    win.show_all()
    win._sync_radios()
    win.refresh()
    Gtk.main()
    return 0
