"""GTK 3 dialog for BitBench-style type interpretations."""

from gi.repository import Gdk, Gtk

from .bittypes import (
    BIT_WIDTHS,
    FORMAT_DEFINITIONS,
    INPUT_MODES,
    InputError,
    calculator_input,
    format_bits,
    interpretations,
    parse_input,
    to_signed,
)

_MODE_LABELS = {
    "auto": "Auto",
    "hex": "Hex",
    "decimal": "Decimal",
    "signed": "Signed",
    "binary": "Binary",
    "octal": "Octal",
    "float": "Float / expression",
}


class BitTypesWindow(Gtk.Window):
    """Interactive bit-pattern input/conversion window."""

    def __init__(self, parent, engine, on_change):
        super().__init__(title="Type Interpretations")
        self.engine = engine
        self.on_change = on_change
        self.value = 0

        self.set_transient_for(parent)
        self.set_default_size(760, 560)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.connect("delete-event", self._hide)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(8)
        self.add(outer)

        controls = Gtk.Grid(row_spacing=6, column_spacing=8)
        outer.pack_start(controls, False, False, 0)

        controls.attach(Gtk.Label(label="Width", xalign=0.0), 0, 0, 1, 1)
        self.width_combo = Gtk.ComboBoxText()
        for width in BIT_WIDTHS:
            self.width_combo.append(str(width), "{} bit".format(width))
        self.width_combo.set_active_id("64")
        self.width_combo.connect("changed", self._on_changed)
        controls.attach(self.width_combo, 1, 0, 1, 1)

        controls.attach(Gtk.Label(label="Input", xalign=0.0), 2, 0, 1, 1)
        self.mode_combo = Gtk.ComboBoxText()
        for mode in INPUT_MODES:
            self.mode_combo.append(mode, _MODE_LABELS[mode])
        self.mode_combo.set_active_id("auto")
        self.mode_combo.connect("changed", self._on_changed)
        controls.attach(self.mode_combo, 3, 0, 1, 1)

        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        self.entry.set_activates_default(True)
        self.entry.connect("activate", self._evaluate)
        controls.attach(self.entry, 0, 1, 4, 1)

        evaluate = Gtk.Button(label="Interpret")
        evaluate.connect("clicked", self._evaluate)
        evaluate.set_can_default(True)
        evaluate.grab_default()
        controls.attach(evaluate, 4, 1, 1, 1)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        from_display = Gtk.Button(label="From calculator")
        from_display.connect("clicked", self._from_calculator)
        buttons.pack_start(from_display, False, False, 0)

        to_display = Gtk.Button(label="Send bits to calculator")
        to_display.connect("clicked", self._to_calculator)
        buttons.pack_start(to_display, False, False, 0)

        outer.pack_start(buttons, False, False, 0)

        self.summary = Gtk.Label(xalign=0.0, selectable=True)
        self.summary.set_line_wrap(True)
        outer.pack_start(self.summary, False, False, 0)

        self.error = Gtk.Label(xalign=0.0)
        self.error.get_style_context().add_class("error")
        outer.pack_start(self.error, False, False, 0)

        self.store = Gtk.TreeStore(str, str, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.set_headers_visible(True)
        self.tree.append_column(
            Gtk.TreeViewColumn("Type", Gtk.CellRendererText(), text=0))
        aliases_column = Gtk.TreeViewColumn(
            "Aliases", Gtk.CellRendererText(), text=2)
        self.tree.append_column(aliases_column)
        value_column = Gtk.TreeViewColumn(
            "Value", Gtk.CellRendererText(), text=1)
        value_column.set_expand(True)
        self.tree.append_column(value_column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)

        self._from_calculator()

    def _hide(self, *_args):
        self.hide()
        return True

    @property
    def width(self):
        return int(self.width_combo.get_active_id() or "64")

    @property
    def mode(self):
        return self.mode_combo.get_active_id() or "auto"

    def _on_changed(self, *_args):
        if self.entry.get_text().strip():
            self._evaluate()

    def sync_from_calculator(self):
        self._from_calculator()

    def _from_calculator(self, *_args):
        width = 64
        if self.engine.base != 10:
            width = {
                "byte": 8, "word": 16, "dword": 32, "qword": 64
            }.get(self.engine.word, 64)
        self.width_combo.set_active_id(str(width))

        text, mode = calculator_input(
            self.engine.copy_text(), self.engine.base)
        self.mode_combo.set_active_id(mode)
        self.entry.set_text(text)
        self._evaluate()

    def _evaluate(self, *_args):
        try:
            self.value = parse_input(
                self.entry.get_text(), self.mode, self.width)
        except InputError as exc:
            self.error.set_text(str(exc))
            self.store.clear()
            self.summary.set_text("")
            return
        self.error.set_text("")
        self._render()

    def _render(self):
        width = self.width
        value = self.value
        self.summary.set_text(
            "Hex 0x{}    Unsigned {}    Signed {}    Oct 0o{}    Bin 0b{}"
            .format(
                format_bits(value, width, 16),
                value,
                to_signed(value, width),
                format_bits(value, width, 8),
                format_bits(value, width, 2),
            )
        )

        self.store.clear()
        parents = {}
        aliases = {definition.name: ", ".join(definition.names[1:])
                   for definition in FORMAT_DEFINITIONS}
        items = interpretations(value, width)
        for item in items:
            parent = parents.get(item.category)
            if parent is None:
                parent = self.store.append(None, [item.category, "", ""])
                parents[item.category] = parent
            self.store.append(parent, [item.name, item.value, aliases[item.name]])
        self.tree.expand_all()
        self.set_title("Type Interpretations - {} formats".format(len(items)))

    def _to_calculator(self, *_args):
        base = self.engine.base
        self.engine.paste_text(format_bits(self.value, self.width, base))
        self.on_change()


def install():
    """Attach the BitBench workbench to xpcalc's existing Tools surface."""

    from .ui import Calculator

    if getattr(Calculator, "_bittypes_installed", False):
        return

    original_build_menu = Calculator._build_menu

    def show_bittypes(self, *_args):
        window = getattr(self, "bittypes_window", None)
        if window is None:
            window = self.bittypes_window = BitTypesWindow(
                self, self.engine, self.refresh)
        else:
            window.sync_from_calculator()
        window.show_all()
        window.present()

    def build_menu(self):
        bar = original_build_menu(self)

        tools = Gtk.MenuItem(label="Tools")
        menu = Gtk.Menu()
        bittypes = Gtk.MenuItem(label="Type interpretations...")
        bittypes.connect("activate", self._show_bittypes)
        menu.append(bittypes)
        tools.set_submenu(menu)

        children = bar.get_children()
        help_item = children[-1] if children else None
        if help_item is not None and help_item.get_label() == "Help":
            bar.remove(help_item)
            bar.append(tools)
            bar.append(help_item)
        else:
            bar.append(tools)

        return bar

    Calculator._show_bittypes = show_bittypes
    Calculator._build_menu = build_menu
    Calculator._bittypes_installed = True
