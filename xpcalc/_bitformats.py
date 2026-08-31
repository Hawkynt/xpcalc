"""Character, colour, time, audio and special-format helpers."""

import math
import struct
from datetime import datetime, timedelta, timezone

_EPOCH_UNIX = datetime(1970, 1, 1, tzinfo=timezone.utc)
_EPOCH_FILETIME = datetime(1601, 1, 1, tzinfo=timezone.utc)
_EPOCH_NTP = datetime(1900, 1, 1, tzinfo=timezone.utc)
_EPOCH_HFS = datetime(1904, 1, 1, tzinfo=timezone.utc)
_EPOCH_GPS = datetime(1980, 1, 6, tzinfo=timezone.utc)
_EPOCH_OLE = datetime(1899, 12, 30, tzinfo=timezone.utc)
_EPOCH_DOTNET = datetime(1, 1, 1, tzinfo=timezone.utc)

_ASCII_CONTROL = (
    "NUL", "SOH", "STX", "ETX", "EOT", "ENQ", "ACK", "BEL",
    "BS", "HT", "LF", "VT", "FF", "CR", "SO", "SI",
    "DLE", "DC1", "DC2", "DC3", "DC4", "NAK", "SYN", "ETB",
    "CAN", "EM", "SUB", "ESC", "FS", "GS", "RS", "US",
)


def _mask(width):
    return (1 << width) - 1


def _to_signed(value, width):
    value &= _mask(width)
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def _bits_to_float(bits, width):
    bits &= _mask(width)
    if width == 64:
        return struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    raise ValueError("unsupported float width")


def _format_float(value):
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "-Infinity" if value < 0 else "Infinity"
    return format(value, ".17g")


def _unpacked_bcd(bits, width):
    result = 0
    multiplier = 1
    for shift in range(0, width, 8):
        digit = (bits >> shift) & 0xF
        if digit > 9:
            return "Invalid BCD"
        result += digit * multiplier
        multiplier *= 10
    return str(result)


def _bcd(bits, width):
    digits = []
    valid = True
    for shift in range(width - 4, -1, -4):
        digit = (bits >> shift) & 0xF
        if digit > 9:
            valid = False
        digits.append(str(digit) if digit <= 9 else "?")
    return "".join(digits) if valid else "Invalid BCD"


def _rgb565(value):
    r = (value >> 11) & 0x1F
    g = (value >> 5) & 0x3F
    b = value & 0x1F
    return "#{:02X}{:02X}{:02X}".format(round(r * 255 / 31),
                                        round(g * 255 / 63),
                                        round(b * 255 / 31))


def _rgb555(value):
    r = (value >> 10) & 0x1F
    g = (value >> 5) & 0x1F
    b = value & 0x1F
    return "#{:02X}{:02X}{:02X}".format(round(r * 255 / 31),
                                        round(g * 255 / 31),
                                        round(b * 255 / 31))


def _argb1555(value):
    return "A={} {}".format((value >> 15) & 1, _rgb555(value))


def _argb4444(value):
    a = ((value >> 12) & 0xF) * 17
    r = ((value >> 8) & 0xF) * 17
    g = ((value >> 4) & 0xF) * 17
    b = (value & 0xF) * 17
    return "#{:02X}{:02X}{:02X}{:02X}".format(r, g, b, a)


def _rgb(value):
    return "#{:06X}".format(value & 0xFFFFFF)


def _rgba(value):
    return "#{:08X}".format(value & 0xFFFFFFFF)


def _bgr(value):
    b = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    r = value & 0xFF
    return "#{:02X}{:02X}{:02X}".format(r, g, b)


def _bgra(value):
    a = (value >> 24) & 0xFF
    b = (value >> 16) & 0xFF
    g = (value >> 8) & 0xFF
    r = value & 0xFF
    return "#{:02X}{:02X}{:02X}{:02X}".format(r, g, b, a)


def _abgr(value):
    r = (value >> 24) & 0xFF
    g = (value >> 16) & 0xFF
    b = (value >> 8) & 0xFF
    a = value & 0xFF
    return "#{:02X}{:02X}{:02X}{:02X}".format(r, g, b, a)


def _hsv(value):
    r = ((value >> 16) & 0xFF) / 255.0
    g = ((value >> 8) & 0xFF) / 255.0
    b = (value & 0xFF) / 255.0
    maximum = max(r, g, b)
    minimum = min(r, g, b)
    delta = maximum - minimum
    if delta == 0:
        hue = 0
    elif maximum == r:
        hue = (60 * ((g - b) / delta) + 360) % 360
    elif maximum == g:
        hue = 60 * ((b - r) / delta + 2)
    else:
        hue = 60 * ((r - g) / delta + 4)
    saturation = 0 if maximum == 0 else delta / maximum
    return "H={} S={}% V={}%".format(
        round(hue), round(saturation * 100), round(maximum * 100))


def _safe_datetime(epoch, **delta):
    try:
        return (epoch + timedelta(**delta)).isoformat().replace("+00:00", "Z")
    except (OverflowError, ValueError):
        return "<out of range>"


def _unix32(value):
    return _safe_datetime(_EPOCH_UNIX, seconds=_to_signed(value, 32))


def _unix64(value):
    return _safe_datetime(_EPOCH_UNIX, seconds=_to_signed(value, 64))


def _filetime(value):
    return _safe_datetime(_EPOCH_FILETIME, microseconds=value // 10)


def _ntp(value):
    seconds = (value >> 32) & 0xFFFFFFFF
    fraction = value & 0xFFFFFFFF
    return _safe_datetime(_EPOCH_NTP,
                          seconds=seconds + fraction / 2 ** 32)


def _hfs(value):
    return _safe_datetime(_EPOCH_HFS, seconds=value & 0xFFFFFFFF)


def _gps(value):
    return _safe_datetime(_EPOCH_GPS, seconds=value & 0xFFFFFFFF)


def _dotnet_ticks(value):
    return _safe_datetime(_EPOCH_DOTNET, microseconds=value // 10)


def _webkit(value):
    return _safe_datetime(_EPOCH_FILETIME, microseconds=value)


def _ole_date(bits):
    days = _bits_to_float(bits, 64)
    if not math.isfinite(days):
        return _format_float(days)
    return _safe_datetime(_EPOCH_OLE, days=days)


def _dos_datetime(value):
    date = (value >> 16) & 0xFFFF
    time = value & 0xFFFF
    year = 1980 + ((date >> 9) & 0x7F)
    month = (date >> 5) & 0x0F
    day = date & 0x1F
    hour = (time >> 11) & 0x1F
    minute = (time >> 5) & 0x3F
    second = (time & 0x1F) * 2
    try:
        return datetime(year, month, day, hour, minute, second).isoformat()
    except ValueError:
        return "Invalid DOS DateTime"


def _mulaw(value):
    sample = (~value) & 0xFF
    sign = sample & 0x80
    exponent = (sample >> 4) & 0x07
    mantissa = sample & 0x0F
    pcm = ((mantissa << 3) + 0x84) << exponent
    pcm -= 0x84
    return -pcm if sign else pcm


def _alaw(value):
    sample = value ^ 0x55
    sign = sample & 0x80
    exponent = (sample >> 4) & 0x07
    mantissa = sample & 0x0F
    pcm = (mantissa << 4) + 8
    if exponent:
        pcm += 0x100
        pcm <<= exponent - 1
    return -pcm if sign else pcm


def _midi(value):
    note = value & 0x7F
    names = ("C", "C#", "D", "D#", "E", "F",
             "F#", "G", "G#", "A", "A#", "B")
    octave = note // 12 - 1
    frequency = 440.0 * 2 ** ((note - 69) / 12)
    return "{}{} ({:.3f} Hz)".format(names[note % 12], octave, frequency)


def _ascii_byte(value):
    value &= 0xFF
    if value < 32:
        return "'{}'".format(_ASCII_CONTROL[value])
    if value == 32:
        return "'SP'"
    if value == 127:
        return "'DEL'"
    if value > 127:
        return "'\\x{:02x}'".format(value)
    return repr(chr(value))


def _ascii_string(value, bits):
    chars = []
    for shift in range(0, bits, 8):
        byte = (value >> shift) & 0xFF
        chars.append(chr(byte) if 32 <= byte < 127 else ".")
    return '"{}"'.format("".join(chars))


def _utf8_byte(value):
    value &= 0xFF
    if value < 0x80:
        return _ascii_byte(value)
    if value < 0xC0:
        return "(cont)"
    if value < 0xE0:
        return "(2-byte lead)"
    if value < 0xF0:
        return "(3-byte lead)"
    if value < 0xF8:
        return "(4-byte lead)"
    return "(invalid)"


def _utf16_unit(value):
    value &= 0xFFFF
    if 0xD800 <= value <= 0xDBFF:
        return "U+{:04X} (high surrogate)".format(value)
    if 0xDC00 <= value <= 0xDFFF:
        return "U+{:04X} (low surrogate)".format(value)
    if value < 32:
        return "U+{:04X} '{}'".format(value, _ASCII_CONTROL[value])
    try:
        return "U+{:04X} {}".format(value, repr(chr(value)))
    except ValueError:
        return "U+{:04X} (invalid)".format(value)


def _ebcdic_byte(value):
    char = bytes([value & 0xFF]).decode("cp037")
    return repr(char) if char.isprintable() else "U+{:04X}".format(ord(char))


def _utf32(value):
    if 0 <= value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF:
        char = chr(value)
        return "{} U+{:04X}".format(repr(char), value)
    return "Invalid Unicode scalar"
