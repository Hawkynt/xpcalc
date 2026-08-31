"""Bit-pattern input, conversion and type interpretations.

Adapted from Hawkynt's BitBench with the author's explicit permission for this
integration. The module stays UI-independent so xpcalc's arithmetic state
machine remains untouched.
"""

import ast
import math
import re

from ._bitfloat import _float_to_bits
from ._interpret import (CATEGORY_NAMES, FORMAT_DEFINITIONS, Interpretation,
                         find_format, interpretations)

BIT_WIDTHS = (8, 16, 32, 64)
INPUT_MODES = ("auto", "hex", "decimal", "signed", "binary", "octal", "float")


class InputError(ValueError):
    """Raised when a BitBench-style input cannot be interpreted."""


def _mask(width):
    return (1 << width) - 1


def _require_width(width):
    if width not in BIT_WIDTHS:
        raise ValueError("width must be one of 8, 16, 32 or 64")


def swap_bytes(value, width):
    _require_width(width)
    size = width // 8
    return int.from_bytes((value & _mask(width)).to_bytes(size, "little"), "big")


def to_signed(value, width):
    value &= _mask(width)
    sign = 1 << (width - 1)
    return value - (1 << width) if value & sign else value


def gray_decode(value):
    value = int(value)
    result = value
    while value:
        value >>= 1
        result ^= value
    return result


def zigzag_decode(value, width):
    value &= _mask(width)
    result = (value >> 1) ^ -(value & 1)
    return to_signed(result, width)


def _safe_eval_float(text):
    functions = {
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "cot": lambda x: 1 / math.tan(x),
        "sec": lambda x: 1 / math.cos(x),
        "csc": lambda x: 1 / math.sin(x),
        "asin": math.asin, "acos": math.acos, "atan": math.atan,
        "acot": lambda x: math.atan(1 / x),
        "asec": lambda x: math.acos(1 / x),
        "acsc": lambda x: math.asin(1 / x),
        "atan2": math.atan2,
        "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        "coth": lambda x: 1 / math.tanh(x),
        "sech": lambda x: 1 / math.cosh(x),
        "csch": lambda x: 1 / math.sinh(x),
        "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
        "acoth": lambda x: math.atanh(1 / x),
        "asech": lambda x: math.acosh(1 / x),
        "acsch": lambda x: math.asinh(1 / x),
        "arsinh": math.asinh, "arcosh": math.acosh, "artanh": math.atanh,
        "log": math.log, "ln": math.log, "log10": math.log10,
        "log2": math.log2, "exp": math.exp, "pow": math.pow,
        "sqrt": math.sqrt,
        "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
        "abs": abs, "ceil": math.ceil, "floor": math.floor,
        "round": round, "trunc": math.trunc,
        "sign": lambda x: -1 if x < 0 else 1 if x > 0 else 0,
        "min": min, "max": max, "hypot": math.hypot,
        "frac": lambda x: x - math.trunc(x),
        "deg": math.degrees, "rad": math.radians,
    }
    constants = {
        "pi": math.pi, "e": math.e, "tau": math.tau,
        "phi": (1 + math.sqrt(5)) / 2,
        "inf": math.inf, "nan": math.nan,
    }
    operators = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }
    unary = {
        ast.UAdd: lambda a: a,
        ast.USub: lambda a: -a,
    }

    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise InputError("invalid float expression") from exc

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name) and node.id in constants:
            return constants[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary:
            return unary[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = functions.get(node.func.id)
            if function is None or node.keywords:
                raise InputError("unknown or unsupported function")
            return function(*(evaluate(arg) for arg in node.args))
        raise InputError("unsupported expression syntax")

    try:
        return float(evaluate(tree))
    except InputError:
        raise
    except (ArithmeticError, OverflowError, ValueError, TypeError) as exc:
        raise InputError(str(exc)) from exc


def parse_input(text, mode="auto", width=64):
    """Parse a BitBench-style input into an unsigned bit pattern."""

    _require_width(width)
    mode = mode.lower()
    if mode not in INPUT_MODES:
        raise ValueError("unknown input mode")

    text = text.strip().replace("_", "").replace(" ", "")
    if not text:
        raise InputError("empty input")

    if mode == "auto":
        lowered = text.lower()
        if lowered.startswith(("0x", "+0x", "-0x")):
            mode = "hex"
        elif lowered.startswith(("0b", "+0b", "-0b")):
            mode = "binary"
        elif lowered.startswith(("0o", "+0o", "-0o")):
            mode = "octal"
        elif lowered in {
                "nan", "inf", "+inf", "-inf", "infinity",
                "+infinity", "-infinity", "pi", "e", "tau", "phi"}:
            mode = "float"
        elif re.match(r"^[+-]?(?:\d+[.,]\d*|[.,]\d+|\d+[eE][+-]?\d+"
                      r"|\d+[.,]\d*[eE][+-]?\d+"
                      r"|[.,]\d+[eE][+-]?\d+)$", text):
            mode = "float"
        elif re.match(r"^[0-9A-Fa-f]+$", text) and re.search(r"[A-Fa-f]", text):
            mode = "hex"
        elif any(ch in text for ch in "()*/^") or re.search(r"[A-Za-z_]", text):
            mode = "float"
        else:
            mode = "decimal"

    if mode == "float":
        if ("," in text and "(" not in text and ")" not in text and
                "." not in text and text.count(",") == 1):
            text = text.replace(",", ".")
        normalized = text.lower()
        special = {
            "inf": math.inf, "+inf": math.inf, "infinity": math.inf,
            "+infinity": math.inf, "-inf": -math.inf,
            "-infinity": -math.inf, "nan": math.nan,
        }
        value = special.get(normalized)
        if value is None:
            value = _safe_eval_float(text)
        return _float_to_bits(value, width)

    base = {
        "hex": 16, "decimal": 10, "signed": 10,
        "binary": 2, "octal": 8,
    }[mode]
    raw = text
    negative = raw.startswith("-")
    sign = ""
    if raw[:1] in "+-":
        sign, raw = raw[0], raw[1:]
    prefixes = {16: "0x", 2: "0b", 8: "0o"}
    prefix = prefixes.get(base)
    if prefix and raw.lower().startswith(prefix):
        raw = raw[2:]
    if not raw:
        raise InputError("missing digits")
    try:
        number = int(sign + raw, base)
    except ValueError as exc:
        raise InputError("invalid {} input".format(mode)) from exc

    if mode == "signed":
        minimum = -(1 << (width - 1))
        maximum = (1 << (width - 1)) - 1
        if not minimum <= number <= maximum:
            raise InputError("signed value does not fit {} bits".format(width))
    elif negative:
        minimum = -(1 << (width - 1))
        if number < minimum:
            raise InputError("negative value does not fit {} bits".format(width))
    elif number > _mask(width):
        raise InputError("value does not fit {} bits".format(width))

    return number & _mask(width)


def calculator_input(text, base):
    """Return normalized text and input mode for an xpcalc display value."""

    text = text.replace(",", "").strip()
    mode = {
        16: "hex", 10: "decimal", 8: "octal", 2: "binary"
    }.get(base, "auto")
    if base == 10:
        lowered = text.lower()
        if text.endswith(".") and "e" not in lowered:
            text = text[:-1]
        if "." in text or "e" in lowered:
            mode = "float"
        elif text.startswith("-"):
            mode = "signed"
    return text, mode


def format_bits(value, width, base=16):
    _require_width(width)
    value &= _mask(width)
    if base == 16:
        return format(value, "0{}X".format(width // 4))
    if base == 10:
        return str(value)
    if base == 8:
        return format(value, "o")
    if base == 2:
        return format(value, "0{}b".format(width))
    raise ValueError("base must be 2, 8, 10 or 16")
