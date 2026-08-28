#!/bin/sh
# Install (or remove) xpcalc as a proper desktop application.
#
#   ./install.sh                 install into ~/.local
#   sudo ./install.sh            install into /usr/local
#   PREFIX=/opt ./install.sh     install into /opt
#   ./install.sh --uninstall     remove it again
#
# Installs the package, an `xpcalc` launcher, a freedesktop .desktop entry
# with Standard/Scientific launcher actions, and the hicolor icons every
# desktop environment reads (GNOME, KDE, Xfce, Cinnamon, MATE, LXQt, ...).
set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -n "${PREFIX:-}" ]; then
    :
elif [ "$(id -u)" = 0 ]; then
    PREFIX=/usr/local
else
    PREFIX="$HOME/.local"
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/share/xpcalc"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor"
LAUNCHER="$BIN_DIR/xpcalc"
DESKTOP_FILE="$DESKTOP_DIR/xpcalc.desktop"
ICON_SIZES="16 22 24 32 48 64 128 256"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

refresh_caches() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi
    # gtk-update-icon-cache needs an index.theme; without one the loose files
    # are still found, so a failure here is not fatal.
    if command -v gtk-update-icon-cache >/dev/null 2>&1 &&
       [ -f "$ICON_DIR/index.theme" ]; then
        gtk-update-icon-cache -q -f -t "$ICON_DIR" 2>/dev/null || true
    fi
    if command -v xdg-desktop-menu >/dev/null 2>&1; then
        xdg-desktop-menu forceupdate 2>/dev/null || true
    fi
}

uninstall() {
    rm -rf "$LIB_DIR"
    rm -f "$LAUNCHER" "$DESKTOP_FILE"
    for size in $ICON_SIZES; do
        rm -f "$ICON_DIR/${size}x${size}/apps/xpcalc.png"
    done
    rm -f "$ICON_DIR/scalable/apps/xpcalc.svg"
    refresh_caches
    printf 'Removed xpcalc from %s\n' "$PREFIX"
    exit 0
}

case "${1:-}" in
    --uninstall|-u) uninstall ;;
    "") ;;
    *) die "unknown option: $1 (use --uninstall)" ;;
esac

# ---------------------------------------------------------------- checks
command -v python3 >/dev/null 2>&1 || die "python3 is not installed"

if ! python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk
PY
then
    printf 'error: PyGObject with GTK 3 is missing.\n\n' >&2
    printf 'Install it with one of:\n' >&2
    printf '  Arch          sudo pacman -S python-gobject gtk3\n' >&2
    printf '  Debian/Ubuntu sudo apt install python3-gi gir1.2-gtk-3.0\n' >&2
    printf '  Fedora        sudo dnf install python3-gobject gtk3\n' >&2
    printf '  openSUSE      sudo zypper install python3-gobject gtk3\n' >&2
    exit 1
fi

# ---------------------------------------------------------------- program
mkdir -p "$BIN_DIR" "$LIB_DIR" "$DESKTOP_DIR"

rm -rf "$LIB_DIR/xpcalc"
cp -R "$SOURCE_DIR/xpcalc" "$LIB_DIR/xpcalc"
find "$LIB_DIR/xpcalc" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$LAUNCHER" <<LAUNCHEOF
#!/bin/sh
PYTHONPATH="$LIB_DIR\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m xpcalc "\$@"
LAUNCHEOF
chmod 755 "$LAUNCHER"

# ---------------------------------------------------------------- icons
for size in $ICON_SIZES; do
    source_icon="$SOURCE_DIR/data/icons/${size}x${size}/xpcalc.png"
    [ -f "$source_icon" ] || continue
    mkdir -p "$ICON_DIR/${size}x${size}/apps"
    cp "$source_icon" "$ICON_DIR/${size}x${size}/apps/xpcalc.png"
done
mkdir -p "$ICON_DIR/scalable/apps"
cp "$SOURCE_DIR/data/xpcalc.svg" "$ICON_DIR/scalable/apps/xpcalc.svg"

# ---------------------------------------------------------------- desktop
# Point every Exec line (the main one and both launcher actions) at the
# installed launcher, so the entry works whatever the prefix is.
sed "s|^Exec=xpcalc|Exec=$LAUNCHER|" \
    "$SOURCE_DIR/data/xpcalc.desktop" > "$DESKTOP_FILE"
chmod 644 "$DESKTOP_FILE"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_FILE" ||
        printf 'warning: desktop entry validation reported issues\n' >&2
fi

refresh_caches

printf 'Installed xpcalc to %s\n' "$PREFIX"
printf '  launcher   %s\n' "$LAUNCHER"
printf '  package    %s/xpcalc\n' "$LIB_DIR"
printf '  menu entry %s\n' "$DESKTOP_FILE"
printf '  icons      %s/{16x16..256x256,scalable}/apps/xpcalc.*\n' "$ICON_DIR"

case ":$PATH:" in
    *":$BIN_DIR:"*) printf '\nRun it with: xpcalc\n' ;;
    *) printf '\n%s is not on your PATH.\nRun it with: %s\n' "$BIN_DIR" "$LAUNCHER" ;;
esac

case "$PREFIX" in
    "$HOME"/*)
        printf 'It will appear in your application menu (may need a re-login).\n' ;;
esac
