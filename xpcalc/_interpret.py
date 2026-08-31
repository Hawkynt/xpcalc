"""BitBench-compatible type interpretation registry.

The catalog mirrors the FORMAT definitions from Hawkynt BitBench.  Definitions
are data-driven so the UI, alias lookup and regression tests all use the same
completeness list.
"""

import ipaddress
from dataclasses import dataclass

from ._bitfloat import (
    _bfloat_to_number, _bits_to_float, _decimal8, _decimal16, _decimal32,
    _decimal64, _fixed, _format_float, _fp8_e4m3, _fp8_e5m2, _ibm_hfp32,
    _mbf32, _mbf64, _posit, _tf32, _vax_f,
)
from ._bitformats import (
    _abgr, _alaw, _argb1555, _argb4444, _ascii_byte, _ascii_string, _bcd,
    _bgr, _bgra, _dos_datetime, _dotnet_ticks, _ebcdic_byte, _filetime, _gps,
    _hfs, _hsv, _midi, _mulaw, _ntp, _ole_date, _rgb, _rgb555, _rgb565,
    _rgba, _unpacked_bcd, _unix32, _unix64, _utf8_byte, _utf16_unit, _utf32,
    _webkit,
)


@dataclass(frozen=True)
class Interpretation:
    category: str
    name: str
    value: str


@dataclass(frozen=True)
class FormatDefinition:
    id: str
    category: str
    bits: int
    names: tuple
    formatter: object

    @property
    def name(self):
        return self.names[0]


CATEGORY_NAMES = {
    "integers": "Integers",
    "floats": "IEEE 754 Floats",
    "ai_floats": "AI/ML Floats",
    "exotic_floats": "Exotic Floats",
    "fixed": "Fixed Point",
    "decimal": "Decimal/BCD",
    "colors": "Colors",
    "datetime": "Date/Time",
    "audio": "Audio",
    "special": "Special",
    "characters": "Characters",
}


def _mask(width):
    return (1 << width) - 1


def _require_width(width):
    if width not in (8, 16, 32, 64):
        raise ValueError("width must be one of 8, 16, 32 or 64")


def swap_bytes(value, width):
    _require_width(width)
    return int.from_bytes(
        (value & _mask(width)).to_bytes(width // 8, "little"), "big")


def to_signed(value, width):
    value &= _mask(width)
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def gray_decode(value):
    result = value
    while value:
        value >>= 1
        result ^= value
    return result


def zigzag_decode(value):
    return (value >> 1) ^ -(value & 1)


def _chunks(value, bits, width):
    mask = _mask(bits)
    return [(value >> shift) & mask for shift in range(0, width, bits)]


def _array(value, bits, width, formatter):
    values = _chunks(value, bits, width)
    rendered = [str(formatter(item)) for item in values]
    return rendered[0] if len(rendered) == 1 else "[ {} ]".format(", ".join(rendered))


def _fmt_int(bits, signed=False, big_endian=False):
    def formatter(value, width):
        def one(item):
            if big_endian and bits > 8:
                item = swap_bytes(item, bits)
            return to_signed(item, bits) if signed else item
        return _array(value, bits, width, one)
    return formatter


def _fmt_float(bits, big_endian=False):
    def formatter(value, width):
        return _array(
            value, bits, width,
            lambda item: _format_float(_bits_to_float(
                swap_bytes(item, bits) if big_endian else item, bits)))
    return formatter


def _fmt_bfloat(bits, big_endian=False):
    def formatter(value, width):
        return _array(
            value, bits, width,
            lambda item: _format_float(_bfloat_to_number(
                swap_bytes(item, bits) if big_endian and bits > 8 else item,
                bits)))
    return formatter


def _fmt_number(bits, converter, big_endian=False):
    def formatter(value, width):
        return _array(
            value, bits, width,
            lambda item: _format_float(converter(
                swap_bytes(item, bits) if big_endian and bits > 8 else item)))
    return formatter


def _fmt_plain(bits, formatter):
    return lambda value, width: _array(value, bits, width, formatter)


def _fmt_fixed(bits, fraction_bits, signed):
    return _fmt_plain(
        bits,
        lambda item: format(_fixed(item, bits, fraction_bits, signed), ".17g"))


def _fmt_bcd(bits):
    return _fmt_plain(bits, lambda item: _bcd(item, bits))


def _fmt_ascii(bits):
    return _fmt_plain(bits, lambda item: _ascii_string(item, bits))


def _fmt_ipv4(value):
    return str(ipaddress.IPv4Address(value & 0xFFFFFFFF))


def _fmt_mac48(value):
    value &= (1 << 48) - 1
    return ":".join(
        "{:02X}".format((value >> shift) & 0xFF)
        for shift in range(40, -1, -8))


def _fmt_ipv6low(value):
    return "::" + ":".join(
        "{:x}".format((value >> shift) & 0xFFFF)
        for shift in (48, 32, 16, 0))


_WELL_KNOWN_PORTS = {
    20: "FTP-data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS",
    993: "IMAPS", 995: "POP3S", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 6379: "Redis", 6443: "K8s API",
    8080: "HTTP-alt", 11211: "Memcached", 27017: "MongoDB",
}


def _fmt_port(value):
    name = _WELL_KNOWN_PORTS.get(value)
    return "{} ({})".format(value, name) if name else str(value)


def _fmt_fourcc(value):
    chars = []
    for shift in (0, 8, 16, 24):
        byte = (value >> shift) & 0xFF
        chars.append(chr(byte) if 32 <= byte < 127 else ".")
    return '"{}"'.format("".join(chars))


def _fmt_currency(value):
    signed = to_signed(value, 64)
    negative = signed < 0
    absolute = -signed if negative else signed
    integer, fraction = divmod(absolute, 10000)
    frac = str(fraction).rjust(4, "0").rstrip("0") or "0"
    return "${}{}.{}".format("-" if negative else "", integer, frac)


def _definition(identifier, category, bits, names, formatter):
    return FormatDefinition(identifier, category, bits, tuple(names), formatter)


# This list mirrors BitBench's FORMAT registry one entry for one entry.
FORMAT_DEFINITIONS = (
    _definition("uint8", "integers", 8,
                ("Byte", "UInt8", "byte", "u8", "unsigned char", "BYTE"),
                _fmt_int(8)),
    _definition("int8", "integers", 8,
                ("SByte", "Int8", "sbyte", "i8", "signed char", "char"),
                _fmt_int(8, True)),
    _definition("uint16_le", "integers", 16,
                ("Word", "UInt16", "ushort", "u16", "word", "WORD",
                 "unsigned short"), _fmt_int(16)),
    _definition("uint16_be", "integers", 16,
                ("Word BE", "UInt16 BE", "u16be"), _fmt_int(16, False, True)),
    _definition("int16_le", "integers", 16,
                ("Short", "Int16", "short", "i16", "signed short"),
                _fmt_int(16, True)),
    _definition("int16_be", "integers", 16,
                ("Short BE", "Int16 BE", "i16be"), _fmt_int(16, True, True)),
    _definition("uint32_le", "integers", 32,
                ("DWord", "UInt32", "uint", "u32", "dword", "DWORD",
                 "unsigned int", "unsigned long"), _fmt_int(32)),
    _definition("uint32_be", "integers", 32,
                ("DWord BE", "UInt32 BE", "u32be"), _fmt_int(32, False, True)),
    _definition("int32_le", "integers", 32,
                ("Int", "Int32", "int", "i32", "signed int", "long"),
                _fmt_int(32, True)),
    _definition("int32_be", "integers", 32,
                ("Int BE", "Int32 BE", "i32be"), _fmt_int(32, True, True)),
    _definition("uint64_le", "integers", 64,
                ("QWord", "UInt64", "ulong", "u64", "qword", "QWORD",
                 "unsigned long long"), _fmt_int(64)),
    _definition("uint64_be", "integers", 64,
                ("QWord BE", "UInt64 BE", "u64be"), _fmt_int(64, False, True)),
    _definition("int64_le", "integers", 64,
                ("Long", "Int64", "long long", "i64", "signed long long"),
                _fmt_int(64, True)),
    _definition("int64_be", "integers", 64,
                ("Long BE", "Int64 BE", "i64be"), _fmt_int(64, True, True)),
    _definition("float16_le", "floats", 16,
                ("Float16", "half", "f16", "binary16", "__fp16"),
                _fmt_float(16)),
    _definition("float16_be", "floats", 16,
                ("Float16 BE", "f16be"), _fmt_float(16, True)),
    _definition("float32_le", "floats", 32,
                ("Float32", "float", "f32", "single", "binary32", "Single"),
                _fmt_float(32)),
    _definition("float32_be", "floats", 32,
                ("Float32 BE", "f32be"), _fmt_float(32, True)),
    _definition("float64_le", "floats", 64,
                ("Float64", "double", "f64", "binary64", "Double"),
                _fmt_float(64)),
    _definition("float64_be", "floats", 64,
                ("Float64 BE", "f64be"), _fmt_float(64, True)),
    _definition("minifloat8", "floats", 8,
                ("Minifloat8", "fp8", "float8"), _fmt_float(8)),
    _definition("bfloat8", "ai_floats", 8,
                ("BFloat8", "bf8", "brain float 8"), _fmt_bfloat(8)),
    _definition("bfloat16_le", "ai_floats", 16,
                ("BFloat16", "bf16", "brain float"), _fmt_bfloat(16)),
    _definition("bfloat16_be", "ai_floats", 16,
                ("BFloat16 BE", "bf16be"), _fmt_bfloat(16, True)),
    _definition("bfloat32_le", "ai_floats", 32,
                ("BFloat32", "bf32", "brain float 32"), _fmt_bfloat(32)),
    _definition("bfloat32_be", "ai_floats", 32,
                ("BFloat32 BE", "bf32be"), _fmt_bfloat(32, True)),
    _definition("bfloat64_le", "ai_floats", 64,
                ("BFloat64", "bf64", "brain float 64"), _fmt_bfloat(64)),
    _definition("bfloat64_be", "ai_floats", 64,
                ("BFloat64 BE", "bf64be"), _fmt_bfloat(64, True)),
    _definition("fp8e4m3", "ai_floats", 8,
                ("FP8-E4M3", "E4M3"), _fmt_number(8, _fp8_e4m3)),
    _definition("fp8e5m2", "ai_floats", 8,
                ("FP8-E5M2", "E5M2"), _fmt_number(8, _fp8_e5m2)),
    _definition("tf32", "ai_floats", 32,
                ("TF32", "TensorFloat-32", "TensorFloat32"),
                _fmt_number(32, _tf32)),
    _definition("ibm_float32", "exotic_floats", 32,
                ("IBM Float", "IBM HFP", "hex float"),
                _fmt_number(32, _ibm_hfp32)),
    _definition("vax_f", "exotic_floats", 32,
                ("VAX F", "F_floating", "VAX float"), _fmt_number(32, _vax_f)),
    _definition("mbf32", "exotic_floats", 32,
                ("MBF32", "MS Binary", "BASIC float"), _fmt_number(32, _mbf32)),
    _definition("mbf64", "exotic_floats", 64,
                ("MBF64", "MS Binary 64", "BASIC double"), _fmt_number(64, _mbf64)),
    _definition("decimal8", "exotic_floats", 8,
                ("Decimal8", "decimal8"), _fmt_number(8, _decimal8)),
    _definition("decimal16_le", "exotic_floats", 16,
                ("Decimal16", "decimal16"), _fmt_number(16, _decimal16)),
    _definition("decimal16_be", "exotic_floats", 16,
                ("Decimal16 BE", "decimal16be"), _fmt_number(16, _decimal16, True)),
    _definition("decimal32", "exotic_floats", 32,
                ("Decimal32", "decimal32", "_Decimal32"), _fmt_number(32, _decimal32)),
    _definition("decimal64", "exotic_floats", 64,
                ("Decimal64", "decimal64", "_Decimal64"), _fmt_number(64, _decimal64)),
    _definition("posit8", "exotic_floats", 8,
                ("Posit8", "posit<8,0>"), _fmt_number(8, lambda x: _posit(x, 8, 0))),
    _definition("posit16", "exotic_floats", 16,
                ("Posit16", "posit<16,1>"), _fmt_number(16, lambda x: _posit(x, 16, 1))),
    _definition("posit32", "exotic_floats", 32,
                ("Posit32", "posit<32,2>"), _fmt_number(32, lambda x: _posit(x, 32, 2))),
    _definition("q7_8", "fixed", 16, ("Q7.8", "fixed8.8"), _fmt_fixed(16, 8, True)),
    _definition("q15_16", "fixed", 32, ("Q15.16", "fixed16.16"), _fmt_fixed(32, 16, True)),
    _definition("q31_32", "fixed", 64, ("Q31.32", "fixed32.32"), _fmt_fixed(64, 32, True)),
    _definition("uq8_8", "fixed", 16, ("UQ8.8", "ufixed8.8"), _fmt_fixed(16, 8, False)),
    _definition("uq16_16", "fixed", 32, ("UQ16.16", "ufixed16.16"), _fmt_fixed(32, 16, False)),
    _definition("uq32_32", "fixed", 64, ("UQ32.32", "ufixed32.32"), _fmt_fixed(64, 32, False)),
    _definition("bcd8", "decimal", 8, ("BCD8", "packed BCD 8"), _fmt_bcd(8)),
    _definition("bcd16", "decimal", 16, ("BCD16", "packed BCD 16"), _fmt_bcd(16)),
    _definition("bcd32", "decimal", 32, ("BCD32", "packed BCD 32"), _fmt_bcd(32)),
    _definition("bcd64", "decimal", 64, ("BCD64", "packed BCD 64"), _fmt_bcd(64)),
    _definition("ubcd", "decimal", 8,
                ("Unpacked BCD", "UBCD", "zoned decimal"),
                _fmt_plain(8, lambda value: _unpacked_bcd(value, 8))),
    _definition("currency64", "special", 64,
                ("Currency", "OLE Currency", "money", "CY", "CURRENCY"),
                lambda value, width: _fmt_currency(value)),
    _definition("filetime", "datetime", 64,
                ("FILETIME", "Windows FILETIME"), lambda value, width: _filetime(value)),
    _definition("unix32", "datetime", 32,
                ("Unix32", "time_t", "Unix timestamp"), _fmt_plain(32, _unix32)),
    _definition("unix64", "datetime", 64,
                ("Unix64", "time64_t"), lambda value, width: _unix64(value)),
    _definition("dosdate", "datetime", 32,
                ("DOS DateTime", "FAT timestamp"), _fmt_plain(32, _dos_datetime)),
    _definition("rgb24", "colors", 32,
                ("RGB", "RGB24", "color"), _fmt_plain(32, _rgb)),
    _definition("rgba32", "colors", 32,
                ("RGBA", "RGBA32", "ARGB"), _fmt_plain(32, _rgba)),
    _definition("fourcc", "special", 32,
                ("FourCC", "FOURCC", "magic"), _fmt_plain(32, _fmt_fourcc)),
    _definition("ascii8", "characters", 8,
                ("ASCII", "Char", "char"), _fmt_plain(8, _ascii_byte)),
    _definition("ascii16", "characters", 16,
                ("ASCII16", "Chars16"), _fmt_ascii(16)),
    _definition("ascii32", "characters", 32,
                ("ASCII32", "Chars32"), _fmt_ascii(32)),
    _definition("ascii64", "characters", 64,
                ("ASCII64", "Chars64"), _fmt_ascii(64)),
    _definition("ebcdic8", "characters", 8,
                ("EBCDIC",), _fmt_plain(8, _ebcdic_byte)),
    _definition("utf8", "characters", 8,
                ("UTF-8",), _fmt_plain(8, _utf8_byte)),
    _definition("utf16", "characters", 16,
                ("UTF-16", "wchar_t", "WCHAR"), _fmt_plain(16, _utf16_unit)),
    _definition("utf32", "characters", 32,
                ("UTF-32", "Unicode", "UCS-4"), _fmt_plain(32, _utf32)),
    _definition("ipv4", "special", 32,
                ("IPv4", "IP Address", "ipaddr", "in_addr"), _fmt_plain(32, _fmt_ipv4)),
    _definition("mac48", "special", 64,
                ("MAC", "MAC-48", "EUI-48"), lambda value, width: _fmt_mac48(value)),
    _definition("ipv6low", "special", 64,
                ("IPv6 (low)", "IPv6-L"), lambda value, width: _fmt_ipv6low(value)),
    _definition("port16", "special", 16,
                ("Port", "TCP Port", "UDP Port"), _fmt_plain(16, _fmt_port)),
    _definition("rgb565", "colors", 16,
                ("RGB565", "16-bit Color", "rgb16"), _fmt_plain(16, _rgb565)),
    _definition("rgb555", "colors", 16,
                ("RGB555", "15-bit Color", "rgb15"), _fmt_plain(16, _rgb555)),
    _definition("argb1555", "colors", 16,
                ("ARGB1555", "16-bit ARGB"), _fmt_plain(16, _argb1555)),
    _definition("argb4444", "colors", 16,
                ("ARGB4444", "16-bit ARGB4444", "4444"), _fmt_plain(16, _argb4444)),
    _definition("bgr24", "colors", 32,
                ("BGR24", "BGR", "COLORREF"), _fmt_plain(32, _bgr)),
    _definition("bgra32", "colors", 32,
                ("BGRA32", "BGRA"), _fmt_plain(32, _bgra)),
    _definition("abgr32", "colors", 32,
                ("ABGR32", "ABGR"), _fmt_plain(32, _abgr)),
    _definition("hsv24", "colors", 32,
                ("HSV", "HSB"), _fmt_plain(32, _hsv)),
    _definition("ntp64", "datetime", 64,
                ("NTP", "NTP Timestamp"), lambda value, width: _ntp(value)),
    _definition("oledate", "datetime", 64,
                ("OLE Date", "Automation Date", "DATE"), lambda value, width: _ole_date(value)),
    _definition("hfsplus", "datetime", 32,
                ("HFS+", "Mac Time", "HFSPlusDate"), _fmt_plain(32, _hfs)),
    _definition("gpstime", "datetime", 32,
                ("GPS Time", "GPS"), _fmt_plain(32, _gps)),
    _definition("webkit", "datetime", 64,
                ("WebKit", "Chrome Time"), lambda value, width: _webkit(value)),
    _definition("dotnet", "datetime", 64,
                (".NET Ticks", "DateTime.Ticks"), lambda value, width: _dotnet_ticks(value)),
    _definition("gray8", "integers", 8,
                ("Gray8", "Gray Code 8"), _fmt_plain(8, gray_decode)),
    _definition("gray16", "integers", 16,
                ("Gray16", "Gray Code 16"), _fmt_plain(16, gray_decode)),
    _definition("gray32", "integers", 32,
                ("Gray32", "Gray Code 32"), _fmt_plain(32, gray_decode)),
    _definition("gray64", "integers", 64,
                ("Gray64", "Gray Code 64"), lambda value, width: gray_decode(value)),
    _definition("zigzag8", "integers", 8,
                ("Zigzag8", "sint8"), _fmt_plain(8, zigzag_decode)),
    _definition("zigzag16", "integers", 16,
                ("Zigzag16", "sint16"), _fmt_plain(16, zigzag_decode)),
    _definition("zigzag32", "integers", 32,
                ("Zigzag32", "Varint32", "sint32"), _fmt_plain(32, zigzag_decode)),
    _definition("zigzag64", "integers", 64,
                ("Zigzag64", "Varint64", "sint64"), lambda value, width: zigzag_decode(value)),
    _definition("mulaw8", "audio", 8,
                ("μ-law", "mu-law", "ulaw", "G.711μ"),
                _fmt_plain(8, lambda value: "PCM: {}".format(_mulaw(value)))),
    _definition("alaw8", "audio", 8,
                ("A-law", "alaw", "G.711A"),
                _fmt_plain(8, lambda value: "PCM: {}".format(_alaw(value)))),
    _definition("midi8", "audio", 8,
                ("MIDI Note", "MIDI", "note"), _fmt_plain(8, _midi)),
)


_FORMAT_BY_ALIAS = {
    alias.casefold(): definition
    for definition in FORMAT_DEFINITIONS
    for alias in (definition.id,) + definition.names
}


def find_format(name):
    """Resolve a BitBench format id or alias, case-insensitively."""

    return _FORMAT_BY_ALIAS.get(name.casefold())


def interpretations(value, width):
    """Return every BitBench format applicable to ``width``."""

    _require_width(width)
    value &= _mask(width)
    result = []
    for definition in FORMAT_DEFINITIONS:
        if definition.bits > width or width % definition.bits:
            continue
        result.append(Interpretation(
            CATEGORY_NAMES[definition.category],
            definition.name,
            str(definition.formatter(value, width)),
        ))
    return result
