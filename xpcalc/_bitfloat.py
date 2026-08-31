"""Floating-point and numeric bit-format helpers for xpcalc.bittypes."""

import math
import struct


def _mask(width):
    return (1 << width) - 1


def _to_signed(value, width):
    value &= _mask(width)
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value

def _format_float(value):
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "-Infinity" if value < 0 else "Infinity"
    if value == 0.0 and math.copysign(1.0, value) < 0:
        return "-0"
    return format(value, ".17g")


def _number_to_minifloat8(value):
    if math.isnan(value):
        return 0x7C
    if math.isinf(value):
        return 0x78 if value > 0 else 0xF8
    if value == 0:
        return 0x80 if math.copysign(1.0, value) < 0 else 0
    sign = 1 if value < 0 else 0
    absolute = abs(value)
    if absolute < 2 ** -9:
        return sign << 7
    if absolute >= 240:
        return (sign << 7) | 0x78
    if absolute < 2 ** -6:
        mantissa = round(absolute / (2 ** -6) * 8)
        return (sign << 7) | (mantissa & 0x7)
    exponent = math.floor(math.log2(absolute))
    mantissa = absolute / (2 ** exponent) - 1
    exponent += 7
    if exponent <= 0:
        exponent = 0
        mantissa = absolute / (2 ** -6)
    if exponent >= 15:
        return (sign << 7) | 0x78
    return ((sign << 7) | ((exponent & 0xF) << 3)
            | (round(mantissa * 8) & 0x7))


def _minifloat8_to_number(bits):
    sign = (bits >> 7) & 1
    exponent = (bits >> 3) & 0xF
    mantissa = bits & 0x7
    if exponent == 0:
        if mantissa == 0:
            return -0.0 if sign else 0.0
        value = mantissa / 8 * 2 ** -6
    elif exponent == 15:
        return math.nan if mantissa else (-math.inf if sign else math.inf)
    else:
        value = (1 + mantissa / 8) * 2 ** (exponent - 7)
    return -value if sign else value


def _float_to_bits(value, width):
    if width == 8:
        return _number_to_minifloat8(value)
    try:
        if width == 16:
            return int.from_bytes(struct.pack(">e", value), "big")
        if width == 32:
            return int.from_bytes(struct.pack(">f", value), "big")
        if width == 64:
            return int.from_bytes(struct.pack(">d", value), "big")
    except OverflowError:
        if width == 16:
            return 0xFC00 if value < 0 else 0x7C00
        if width == 32:
            return 0xFF800000 if value < 0 else 0x7F800000
        return 0xFFF0000000000000 if value < 0 else 0x7FF0000000000000
    raise ValueError("unsupported float width")


def _bits_to_float(bits, width):
    bits &= _mask(width)
    if width == 8:
        return _minifloat8_to_number(bits)
    if width == 16:
        return struct.unpack(">e", bits.to_bytes(2, "big"))[0]
    if width == 32:
        return struct.unpack(">f", bits.to_bytes(4, "big"))[0]
    if width == 64:
        return struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    raise ValueError("unsupported float width")


def _bfloat_to_number(bits, width):
    if width == 8:
        return _minifloat8_to_number(bits)
    if width == 16:
        return _bits_to_float((bits & 0xFFFF) << 16, 32)
    if width == 32:
        return _bits_to_float(bits, 32)
    if width == 64:
        sign = (bits >> 63) & 1
        exponent = (bits >> 55) & 0xFF
        mantissa = bits & ((1 << 55) - 1)
        if exponent == 0:
            if mantissa == 0:
                return -0.0 if sign else 0.0
            value = mantissa / (1 << 55) * 2 ** -126
        elif exponent == 255:
            return math.nan if mantissa else (-math.inf if sign else math.inf)
        else:
            value = (1 + mantissa / (1 << 55)) * 2 ** (exponent - 127)
        return -value if sign else value
    raise ValueError("unsupported bfloat width")


def _fp8_e4m3(bits):
    sign = (bits >> 7) & 1
    exponent = (bits >> 3) & 0xF
    mantissa = bits & 7
    if exponent == 15:
        return math.nan
    if exponent == 0:
        value = mantissa / 8 * 2 ** -6
    else:
        value = (1 + mantissa / 8) * 2 ** (exponent - 7)
    return -value if sign else value


def _fp8_e5m2(bits):
    sign = (bits >> 7) & 1
    exponent = (bits >> 2) & 0x1F
    mantissa = bits & 3
    if exponent == 31:
        return math.nan if mantissa else (-math.inf if sign else math.inf)
    if exponent == 0:
        value = mantissa / 4 * 2 ** -14
    else:
        value = (1 + mantissa / 4) * 2 ** (exponent - 15)
    return -value if sign else value


def _ibm_hfp32(bits):
    sign = (bits >> 31) & 1
    exponent = (bits >> 24) & 0x7F
    mantissa = bits & 0xFFFFFF
    if exponent == 0 and mantissa == 0:
        return -0.0 if sign else 0.0
    value = mantissa / 0x1000000 * 16 ** (exponent - 64)
    return -value if sign else value


def _vax_f(bits):
    # VAX F_floating stores 16-bit words in VAX order.
    swapped = ((bits & 0xFFFF) << 16) | ((bits >> 16) & 0xFFFF)
    sign = (swapped >> 15) & 1
    exponent = (swapped >> 7) & 0xFF
    mantissa = ((swapped & 0x7F) << 16) | ((bits >> 16) & 0xFFFF)
    if exponent == 0:
        return 0.0
    value = (0.5 + mantissa / 0x1000000) * 2 ** (exponent - 128)
    return -value if sign else value


def _tf32(bits):
    sign = (bits >> 31) & 1
    exponent = (bits >> 23) & 0xFF
    mantissa = (bits >> 13) & 0x3FF
    if exponent == 0:
        if mantissa == 0:
            return -0.0 if sign else 0.0
        value = mantissa / 1024 * 2 ** -126
    elif exponent == 255:
        return math.nan if mantissa else (-math.inf if sign else math.inf)
    else:
        value = (1 + mantissa / 1024) * 2 ** (exponent - 127)
    return -value if sign else value


def _decimal8(bits):
    sign = (bits >> 7) & 1
    exponent = (bits >> 4) & 0x7
    coefficient = bits & 0xF
    if exponent == 7 and coefficient >= 14:
        return math.nan if coefficient == 15 else (-math.inf if sign else math.inf)
    value = coefficient * 10 ** (exponent - 4)
    return -value if sign else value


def _decimal16(bits):
    sign = (bits >> 15) & 1
    exponent = (bits >> 10) & 0x1F
    coefficient = bits & 0x3FF
    if exponent == 31 and coefficient >= 1022:
        return math.nan if coefficient == 1023 else (-math.inf if sign else math.inf)
    value = coefficient * 10 ** (exponent - 16)
    return -value if sign else value


def _decimal32(bits):
    sign = (bits >> 31) & 1
    combo = (bits >> 23) & 0xFF
    trailing = bits & 0x7FFFFF
    if (combo >> 6) == 3:
        if (combo >> 5) == 0x1E:
            return -math.inf if sign else math.inf
        if (combo >> 5) == 0x1F:
            return math.nan
        exponent = ((combo & 0x3) << 6) | ((bits >> 21) & 0x3F)
        coefficient = (8 + ((combo >> 2) & 1)) * 1000000 + (trailing & 0x1FFFFF)
    else:
        exponent = (combo >> 1) & 0x7F
        lead_digit = (combo >> 3) & 0x7
        coefficient = lead_digit * 10000000 + trailing
    value = coefficient * 10 ** (exponent - 101)
    return -value if sign else value


def _decimal64(bits):
    sign = (bits >> 63) & 1
    combo = (bits >> 53) & 0x3FF
    trailing = bits & 0x1FFFFFFFFFFFFF
    if (combo >> 8) == 3:
        if (combo >> 7) == 0x1E:
            return -math.inf if sign else math.inf
        if (combo >> 7) == 0x1F:
            return math.nan
        exponent = ((combo & 0x3) << 8) | ((bits >> 51) & 0xFF)
        lead_digit = 8 + ((combo >> 2) & 1)
        coefficient = lead_digit * 10000000000000000 + (trailing & 0x7FFFFFFFFFFFF)
    else:
        exponent = (combo >> 2) & 0xFF
        lead_digit = combo & 0x7
        coefficient = lead_digit * 10000000000000000 + trailing
    try:
        value = float(coefficient) * 10.0 ** (exponent - 398)
    except OverflowError:
        value = math.inf
    return -value if sign else value


def _mbf32(bits):
    exponent = (bits >> 24) & 0xFF
    if exponent == 0:
        return 0.0
    sign = (bits >> 23) & 1
    mantissa = bits & 0x7FFFFF
    value = (0.5 + mantissa / 0x1000000) * 2 ** (exponent - 128)
    return -value if sign else value


def _mbf64(bits):
    exponent = (bits >> 56) & 0xFF
    if exponent == 0:
        return 0.0
    sign = (bits >> 55) & 1
    mantissa = bits & ((1 << 55) - 1)
    value = (0.5 + mantissa / (1 << 56)) * 2 ** (exponent - 128)
    return -value if sign else value


def _posit(bits, nbits, es):
    mask = (1 << nbits) - 1
    bits &= mask
    if bits == 0:
        return 0.0
    if bits == 1 << (nbits - 1):
        return math.nan
    sign = (bits >> (nbits - 1)) & 1
    payload = ((1 << nbits) - bits) & mask if sign else bits
    regime_bit = (payload >> (nbits - 2)) & 1
    regime_len = 1
    for index in range(nbits - 3, -1, -1):
        if ((payload >> index) & 1) == regime_bit:
            regime_len += 1
        else:
            break
    k = regime_len - 1 if regime_bit else -regime_len
    remaining = nbits - 1 - regime_len - 1
    exponent = 0
    fraction_bits = 0
    fraction = 0
    if remaining > 0:
        if es and remaining >= es:
            exponent = (payload >> (remaining - es)) & ((1 << es) - 1)
            fraction_bits = remaining - es
        elif es:
            exponent = (payload & ((1 << remaining) - 1)) << (es - remaining)
        else:
            fraction_bits = remaining
        if fraction_bits:
            fraction = payload & ((1 << fraction_bits) - 1)
    scale = k * (1 << es) + exponent
    value = (1 + fraction / (1 << fraction_bits) if fraction_bits else 1.0) * 2 ** scale
    return -value if sign else value


def _fixed(bits, total_bits, fraction_bits, signed):
    value = _to_signed(bits, total_bits) if signed else bits & _mask(total_bits)
    return value / (1 << fraction_bits)
