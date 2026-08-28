"""Calculation engine for xpcalc.

Deliberately UI independent: it owns the display value, the digit entry
buffer, the operator stacks, memory and the statistics list.  ``ui.py`` only
turns button presses into method calls here and reads :attr:`Engine.display`.

Behaviour follows the Windows XP calculator:

* standard mode evaluates strictly left to right, scientific mode honours
  operator precedence and parentheses,
* Hex/Oct/Bin work on two's complement integers of the selected word size,
* the display keeps 32 significant digits.
"""

import math
from . import dmath
from decimal import (Decimal, DivisionByZero, InvalidOperation, Overflow,
                     getcontext, localcontext)

PRECISION = 32
getcontext().prec = PRECISION

WORD_BITS = {"byte": 8, "word": 16, "dword": 32, "qword": 64}
BASE_DIGITS = "0123456789ABCDEF"
ANGLES = ("deg", "rad", "grad")

# Scientific mode precedence, lowest binds loosest.
PREC = {"Or": 0, "Xor": 1, "And": 2, "Lsh": 3, "Rsh": 3,
        "+": 4, "-": 4, "*": 5, "/": 5, "Mod": 5, "^": 6, "root": 6}

INTEGER_OPS = {"And", "Or", "Xor", "Lsh", "Rsh", "Mod"}

DIVIDE_BY_ZERO = "Cannot divide by zero"
INVALID_INPUT = "Invalid input for function"
OVERFLOW = "Result is too large"
UNDEFINED = "Result of function is undefined"


class CalcError(Exception):
    """Raised for the error banners the XP calculator shows in its display."""


class Entry:
    """The digits the user is currently typing."""

    def __init__(self, base=10):
        self.base = base
        self.neg = False
        self.digits = "0"
        self.point = False
        self.frac = ""
        self.exp = None          # None until Exp is pressed
        self.exp_neg = False
        self.touched = False     # False while still showing a bare "0"

    # -- construction -------------------------------------------------
    @property
    def max_digits(self):
        return 32 if self.base == 10 else 64

    def add_digit(self, ch):
        ch = ch.upper()
        if BASE_DIGITS.index(ch) >= self.base:
            return
        if self.exp is not None:
            if len(self.exp) < 4:
                self.exp = (self.exp + ch).lstrip("0") or "0"
            return
        if self.point:
            if len(self.digits) + len(self.frac) < self.max_digits:
                self.frac += ch
        else:
            if self.digits == "0":
                self.digits = ch
            elif len(self.digits) < self.max_digits:
                self.digits += ch
        self.touched = True

    def add_point(self):
        if self.base != 10 or self.exp is not None:
            return
        self.point = True
        self.touched = True

    def start_exp(self):
        if self.base != 10 or self.exp is not None:
            return
        self.exp = "0"
        self.touched = True

    def negate(self):
        if self.exp is not None:
            self.exp_neg = not self.exp_neg
        else:
            self.neg = not self.neg
        self.touched = True

    def backspace(self):
        if self.exp is not None:
            self.exp = self.exp[:-1]
            if not self.exp:
                self.exp = None
                self.exp_neg = False
        elif self.frac:
            self.frac = self.frac[:-1]
        elif self.point:
            self.point = False
        elif len(self.digits) > 1:
            self.digits = self.digits[:-1]
        else:
            self.digits = "0"
            self.neg = False
            self.touched = False

    # -- readout ------------------------------------------------------
    def text(self):
        s = self.digits
        if self.point:
            s += "." + self.frac
        if self.neg:
            s = "-" + s
        if self.exp is not None:
            s += "e" + ("-" if self.exp_neg else "+") + self.exp
        return s

    def value(self):
        if self.base == 10:
            mant = Decimal(self.digits + ("." + self.frac if self.frac else ""))
            if self.neg:
                mant = -mant
            if self.exp is not None:
                e = int(self.exp) * (-1 if self.exp_neg else 1)
                try:
                    mant = mant.scaleb(e)
                except (Overflow, InvalidOperation):
                    raise CalcError(OVERFLOW)
            return mant
        n = int(self.digits, self.base)
        return Decimal(-n if self.neg else n)


class Engine:
    def __init__(self):
        self.mode = "scientific"
        self.base = 10
        self.angle = "deg"
        self.word = "qword"
        self.sci_notation = False   # F-E
        self.grouping = False
        self.memory = Decimal(0)
        self.stats = []
        self.error = None
        self._reset_calc()

    def _reset_calc(self):
        self._acc = Decimal(0)
        self._entry = Entry(self.base)
        self._typing = False
        self._stack = []            # [value, op] pairs at the current paren level
        self._frames = []           # saved stacks, one per open parenthesis
        self._last_op = None        # for repeating on '='
        self._last_operand = None
        self._fresh_op = False      # last thing pressed was a binary operator
        self._tokens = []           # the running expression, as shown to the user
        self._operand_repr = None   # e.g. "sqrt(9)" instead of "3"
        self._pending_operand = False

    # ================================================================
    # display
    # ================================================================
    @property
    def display(self):
        if self.error:
            return self.error
        if self._typing:
            return self._group(self._entry.text())
        return self._group(self.format(self._acc))

    @property
    def expression(self):
        """The task entered so far, e.g. ``2 + sqrt(9) *``.

        Emptied by ``=`` and by ``C``, so it always shows the calculation
        still in progress.
        """
        tokens = list(self._tokens)
        if self._pending_operand and self._operand_repr is not None:
            # a function has been applied but not yet consumed by an
            # operator - show sqrt(9) as soon as the key is pressed
            tokens.append(self._operand_repr)
        return self.expression_of(tokens)

    @property
    def paren_depth(self):
        return len(self._frames)

    def format(self, value):
        if self.base != 10:
            return self._format_int(value)
        return self._format_dec(value)

    def _format_int(self, value):
        n = self._to_int(value)
        if n < 0:
            n += 1 << WORD_BITS[self.word]
        if self.base == 16:
            return format(n, "X")
        if self.base == 8:
            return format(n, "o")
        return format(n, "b")

    def _format_dec(self, value):
        if value == 0:
            return "0."
        exp = value.adjusted()
        if self.sci_notation or exp >= PRECISION or exp < -PRECISION:
            with localcontext() as ctx:
                ctx.prec = PRECISION
                s = f"{value:.{PRECISION - 1}e}"
            mant, _, e = s.partition("e")
            if "." in mant:
                mant = mant.rstrip("0").rstrip(".")
            if "." not in mant:
                mant += "."
            return f"{mant}e{'+' if int(e) >= 0 else '-'}{abs(int(e))}"
        with localcontext() as ctx:
            ctx.prec = PRECISION
            s = format(+value, "f")
        if "." in s:
            s = s.rstrip("0")
        else:
            s += "."
        return s

    def _group(self, s):
        """Insert the thousands separators of View -> Digit grouping."""
        if not self.grouping:
            return s
        neg = s.startswith("-")
        body = s[1:] if neg else s
        head, sep, tail = body.partition("." if self.base == 10 else "\0")
        size = {10: 3, 16: 4, 8: 3, 2: 4}[self.base]
        if head.isalnum():
            chunks = []
            while len(head) > size:
                chunks.append(head[-size:])
                head = head[:-size]
            chunks.append(head)
            head = ",".join(reversed(chunks))
        return ("-" if neg else "") + head + sep + tail

    # ================================================================
    # helpers
    # ================================================================
    def _mask(self, n):
        bits = WORD_BITS[self.word]
        n &= (1 << bits) - 1
        if n >> (bits - 1):
            n -= 1 << bits
        return n

    def _to_int(self, value):
        try:
            n = int(value.to_integral_value(rounding="ROUND_DOWN"))
        except (InvalidOperation, Overflow, ValueError):
            raise CalcError(OVERFLOW)
        return self._mask(n)

    def _check(self, value):
        if value.is_nan():
            raise CalcError(UNDEFINED)
        if value.is_infinite():
            raise CalcError(OVERFLOW)
        if self.base != 10:
            return Decimal(self._to_int(value))
        return +value

    def _from_float(self, x):
        if isinstance(x, complex) or x != x:
            raise CalcError(UNDEFINED)
        if math.isinf(x):
            raise CalcError(OVERFLOW)
        return self._check(Decimal(repr(x)))

    def _operand_token(self):
        if self._operand_repr is not None:
            return self._operand_repr
        # the display shows a trailing "0." like XP, the expression line
        # reads better as plain "0"
        text = self._group(self.format(self._acc))
        return text[:-1] if text.endswith(".") else text

    def _needs_operand(self):
        """True when the expression so far cannot stand without an operand."""
        return not self._tokens or self._tokens[-1] == "(" or \
            self._tokens[-1] in PREC

    def _emit_operand(self):
        # after "=" or "C" the shown result becomes the left operand of
        # whatever the user types next, so emit it even though nothing
        # was typed
        if self._pending_operand or self._needs_operand():
            self._tokens.append(self._operand_token())
        self._pending_operand = False
        self._operand_repr = None

    def _wrap_last_group(self, label):
        """Turn a trailing ``( ... )`` into ``label( ... )`` for unary keys."""
        if not self._tokens or self._tokens[-1] != ")":
            return False
        depth = 0
        for index in range(len(self._tokens) - 1, -1, -1):
            token = self._tokens[index]
            if token == ")":
                depth += 1
            elif token == "(":
                depth -= 1
                if depth == 0:
                    # reuse the group's own brackets: sqrt(2 + 3), not
                    # sqrt((2 + 3))
                    group = self.expression_of(self._tokens[index + 1:-1])
                    del self._tokens[index:]
                    self._operand_repr = "%s(%s)" % (label, group)
                    self._pending_operand = True
                    return True
        return False

    @staticmethod
    def expression_of(tokens):
        out = ""
        for token in tokens:
            if not out or token == ")" or out.endswith("("):
                out += token
            else:
                out += " " + token
        return out

    @staticmethod
    def _unary_label(name, inv, hyp):
        if name in ("sin", "cos", "tan"):
            return ("a" if inv else "") + name + ("h" if hyp else "")
        return {"ln": "e^" if inv else "ln",
                "log": "10^" if inv else "log",
                "x^2": "sqrt" if inv else "sqr",
                "x^3": "cbrt" if inv else "cube",
                "1/x": "1/",
                "n!": "fact",
                "Int": "frac" if inv else "int",
                "dms": "deg" if inv else "dms",
                "Not": "not"}.get(name, name)

    def _commit(self):
        """Fold whatever is being typed into the accumulator."""
        if self._typing:
            self._acc = self._check(self._entry.value())
            self._typing = False
        return self._acc

    def _new_entry(self):
        self._entry = Entry(self.base)
        self._typing = True
        self._operand_repr = None
        self._pending_operand = True

    def _guard(fn):
        def wrapper(self, *args, **kwargs):
            if self.error and fn.__name__ not in ("clear_all", "clear_entry"):
                return
            try:
                return fn(self, *args, **kwargs)
            except CalcError as exc:
                self.error = str(exc)
            except (DivisionByZero, ZeroDivisionError):
                self.error = DIVIDE_BY_ZERO
            except (Overflow, OverflowError):
                self.error = OVERFLOW
            except (InvalidOperation, ValueError, ArithmeticError):
                self.error = INVALID_INPUT
        wrapper.__name__ = fn.__name__
        return wrapper

    # ================================================================
    # entry
    # ================================================================
    @_guard
    def digit(self, ch):
        if not self._typing:
            self._new_entry()
        self._entry.add_digit(ch)
        self._fresh_op = False

    @_guard
    def point(self):
        if not self._typing:
            self._new_entry()
        self._entry.add_point()
        self._fresh_op = False

    @_guard
    def exp_entry(self):
        if not self._typing:
            self._new_entry()
            self._entry.digits = self.format(self._acc).rstrip(".") or "0"
            self._entry.touched = True
        self._entry.start_exp()
        self._fresh_op = False

    @_guard
    def sign(self):
        if self._typing:
            self._entry.negate()
        else:
            self._acc = self._check(-self._acc)
            self._operand_repr = None
            self._pending_operand = True

    @_guard
    def backspace(self):
        if self._typing:
            self._entry.backspace()
        else:
            # XP truncates the shown result one digit at a time
            s = self.format(self._acc).rstrip(".")
            s = s[:-1] if len(s.lstrip("-")) > 1 else "0"
            self._new_entry()
            for ch in s.lstrip("-"):
                if ch == ".":
                    self._entry.add_point()
                else:
                    self._entry.add_digit(ch)
            self._entry.neg = s.startswith("-")

    @_guard
    def clear_entry(self):
        self.error = None
        self._new_entry()

    @_guard
    def clear_all(self):
        self.error = None
        self._reset_calc()

    # ================================================================
    # binary operators
    # ================================================================
    def _apply(self, op, a, b):
        if op in INTEGER_OPS and (self.base != 10 or op in
                                  {"And", "Or", "Xor", "Lsh", "Rsh"}):
            x, y = self._to_int(a), self._to_int(b)
            if op == "And":
                return Decimal(self._mask(x & y))
            if op == "Or":
                return Decimal(self._mask(x | y))
            if op == "Xor":
                return Decimal(self._mask(x ^ y))
            if op == "Lsh":
                return Decimal(self._mask(x << max(0, min(y, 512))))
            if op == "Rsh":
                return Decimal(self._mask(x >> max(0, min(y, 512))))
            if op == "Mod":
                if y == 0:
                    raise CalcError(DIVIDE_BY_ZERO)
                return Decimal(self._mask(int(math.fmod(x, y))))
        if op == "+":
            return self._check(a + b)
        if op == "-":
            return self._check(a - b)
        if op == "*":
            return self._check(a * b)
        if op == "/":
            if b == 0:
                raise CalcError(DIVIDE_BY_ZERO)
            return self._check(a / b)
        if op == "Mod":
            if b == 0:
                raise CalcError(DIVIDE_BY_ZERO)
            return self._check(a - b * (a / b).to_integral_value(rounding="ROUND_DOWN"))
        if op == "^":
            return self._power(a, b)
        if op == "root":
            try:
                return self._check(dmath.root(a, b))
            except (ZeroDivisionError, DivisionByZero):
                raise CalcError(DIVIDE_BY_ZERO)
            except ValueError:
                raise CalcError(INVALID_INPUT)
        raise CalcError(INVALID_INPUT)

    def _power(self, a, b):
        if a == 0 and b < 0:
            raise CalcError(DIVIDE_BY_ZERO)
        if a < 0 and b != b.to_integral_value():
            raise CalcError(INVALID_INPUT)
        try:
            return self._check(dmath.power(a, b))
        except (InvalidOperation, Overflow, OverflowError):
            raise CalcError(OVERFLOW)
        except ValueError:
            raise CalcError(INVALID_INPUT)

    def _reduce(self, limit):
        while self._stack and PREC[self._stack[-1][1]] >= limit:
            value, op = self._stack.pop()
            self._acc = self._apply(op, value, self._acc)

    @_guard
    def operator(self, op):
        if op not in PREC:
            raise CalcError(INVALID_INPUT)
        if self._fresh_op and self._stack:
            self._stack[-1][1] = op          # user changed their mind
            if self._tokens:
                self._tokens[-1] = op
            return
        self._commit()
        self._emit_operand()
        self._tokens.append(op)
        self._reduce(PREC[op] if self.mode == "scientific" else -1)
        self._stack.append([self._acc, op])
        self._fresh_op = True
        self._last_op = None

    @_guard
    def equals(self):
        if self._fresh_op and self._stack:
            self._stack.pop()
        if not self._stack and not self._frames and self._last_op and not self._typing:
            self._acc = self._apply(self._last_op, self._acc, self._last_operand)
            return
        operand = self._commit()
        if self._stack:
            self._last_op = self._stack[0][1] if self.mode == "standard" else self._stack[-1][1]
            self._last_operand = operand
        while True:
            self._reduce(-1)
            if not self._frames:
                break
            self._stack = self._frames.pop()
        self._fresh_op = False
        self._tokens = []
        self._operand_repr = None
        self._pending_operand = False

    @_guard
    def open_paren(self):
        if len(self._frames) >= 25:
            return
        self._frames.append(self._stack)
        self._stack = []
        self._fresh_op = False
        self._tokens.append("(")
        self._operand_repr = None
        self._pending_operand = False
        if not self._typing:
            self._acc = Decimal(0)

    @_guard
    def close_paren(self):
        if not self._frames:
            return
        self._commit()
        self._emit_operand()
        self._reduce(-1)
        self._stack = self._frames.pop()
        self._fresh_op = False
        self._tokens.append(")")

    @_guard
    def percent(self):
        value = self._commit()
        left = self._stack[-1][0] if self._stack else Decimal(0)
        self._acc = self._check(left * value / 100)
        self._fresh_op = False

    # ================================================================
    # unary functions
    # ================================================================
    @_guard
    def unary(self, name, inv=False, hyp=False):
        x = self._commit()
        label = self._unary_label(name, inv, hyp)
        if name == "pi":
            inner = None
        elif self._pending_operand:
            inner = self._operand_token()
        else:
            inner = None if self._wrap_last_group(label) else self._operand_token()
        self._acc = self._unary(name, x, inv, hyp)
        if name == "pi":
            self._operand_repr = "2pi" if inv else "pi"
            self._pending_operand = True
        elif inner is not None:
            self._operand_repr = "%s(%s)" % (label, inner)
            self._pending_operand = True
        self._fresh_op = False

    def _unary(self, name, x, inv, hyp):
        if name == "sqrt":
            if x < 0:
                raise CalcError(INVALID_INPUT)
            return self._check(x.sqrt())
        if name == "1/x":
            if x == 0:
                raise CalcError(DIVIDE_BY_ZERO)
            return self._check(1 / x)
        if name == "x^2":
            if inv:
                return self._unary("sqrt", x, False, False)
            return self._check(x * x)
        if name == "x^3":
            if inv:
                return self._check(dmath.root(x, Decimal(3)))
            return self._check(x * x * x)
        if name == "n!":
            return self._factorial(x)
        if name == "ln":
            if inv:
                return self._check(dmath.exp(x))
            if x <= 0:
                raise CalcError(INVALID_INPUT)
            return self._check(dmath.ln(x))
        if name == "log":
            if inv:
                return self._check(dmath.power(Decimal(10), x))
            if x <= 0:
                raise CalcError(INVALID_INPUT)
            return self._check(dmath.log10(x))
        if name in ("sin", "cos", "tan"):
            return self._trig(name, x, inv, hyp)
        if name == "Int":
            i = x.to_integral_value(rounding="ROUND_DOWN")
            return self._check(x - i if inv else i)
        if name == "Not":
            return Decimal(self._mask(~self._to_int(x)))
        if name == "dms":
            return self._dms(x, inv)
        if name == "pi":
            return self._check(+(dmath.PI * 2) if inv else +dmath.PI)
        raise CalcError(INVALID_INPUT)

    def _factorial(self, x):
        if x < 0 and x == x.to_integral_value():
            raise CalcError(UNDEFINED)
        if x == x.to_integral_value():
            n = int(x)
            if n > 3248:
                raise CalcError(OVERFLOW)
            return self._check(Decimal(math.factorial(n)))
        return self._from_float(math.gamma(float(x) + 1))

    def _trig(self, name, x, inv, hyp):
        try:
            if hyp:
                fn = {"sin": (dmath.sinh, dmath.asinh),
                      "cos": (dmath.cosh, dmath.acosh),
                      "tan": (dmath.tanh, dmath.atanh)}[name][1 if inv else 0]
                return self._check(fn(x))
            if inv:
                return self._check(dmath.inverse_trig(name, x, self.angle))
            return self._check(dmath.trig(name, x, self.angle))
        except ValueError:
            raise CalcError(INVALID_INPUT)
        except (ZeroDivisionError, DivisionByZero):
            raise CalcError(UNDEFINED)
        except (InvalidOperation, Overflow, OverflowError):
            raise CalcError(OVERFLOW)

    def _dms(self, x, inv):
        neg = x < 0
        x = abs(x)
        if inv:                                   # d.ms -> decimal degrees
            deg = x.to_integral_value(rounding="ROUND_DOWN")
            rest = (x - deg) * 100
            mins = rest.to_integral_value(rounding="ROUND_DOWN")
            secs = (rest - mins) * 100
            out = deg + mins / 60 + secs / 3600
        else:                                     # decimal degrees -> d.ms
            deg = x.to_integral_value(rounding="ROUND_DOWN")
            rest = (x - deg) * 60
            mins = rest.to_integral_value(rounding="ROUND_DOWN")
            secs = (rest - mins) * 60
            out = deg + mins / 100 + secs / 10000
        return self._check(-out if neg else out)

    # ================================================================
    # memory
    # ================================================================
    @_guard
    def memory_op(self, op):
        value = self._commit()
        if op == "MC":
            self.memory = Decimal(0)
        elif op == "MR":
            self._acc = self._check(self.memory)
            self._typing = False
            self._operand_repr = None
            self._pending_operand = True
        elif op == "MS":
            self.memory = value
        elif op == "M+":
            self.memory = self._check(self.memory + value)
        elif op == "M-":
            self.memory = self._check(self.memory - value)
        self._fresh_op = False

    @property
    def memory_set(self):
        return self.memory != 0

    # ================================================================
    # statistics
    # ================================================================
    @_guard
    def stat_add(self):
        self.stats.append(self._commit())

    @_guard
    def stat_clear(self):
        self.stats = []

    @_guard
    def stat_result(self, kind, inv=False):
        data = self.stats
        if not data:
            raise CalcError(INVALID_INPUT)
        n = len(data)
        if kind == "Sum":
            total = sum((d * d for d in data), Decimal(0)) if inv else sum(data, Decimal(0))
            self._acc = self._check(total)
        elif kind == "Ave":
            total = sum((d * d for d in data), Decimal(0)) if inv else sum(data, Decimal(0))
            self._acc = self._check(total / n)
        elif kind == "s":
            if n < 2 and not inv:
                raise CalcError(INVALID_INPUT)
            mean = sum(data, Decimal(0)) / n
            var = sum(((d - mean) ** 2 for d in data), Decimal(0)) / (n if inv else n - 1)
            self._acc = self._check(var.sqrt())
        self._typing = False
        self._fresh_op = False

    # ================================================================
    # modes
    # ================================================================
    @_guard
    def set_base(self, base):
        if base == self.base:
            return
        self._commit()
        self.base = base
        if base != 10:
            self._acc = Decimal(self._to_int(self._acc))
            self.sci_notation = False
        self._entry = Entry(base)
        self._typing = False

    def set_angle(self, angle):
        if angle in ANGLES:
            self.angle = angle

    @_guard
    def set_word(self, word):
        if word not in WORD_BITS:
            return
        self._commit()
        self.word = word
        if self.base != 10:
            self._acc = Decimal(self._to_int(self._acc))

    def set_mode(self, mode):
        self.mode = mode
        if mode == "standard":
            self.set_base(10)
            self.sci_notation = False
            self._frames = []
            self._stack = self._stack[:1]

    @_guard
    def toggle_fe(self):
        if self.base == 10:
            self.sci_notation = not self.sci_notation
            self._commit()

    # ================================================================
    # clipboard
    # ================================================================
    def copy_text(self):
        return self.display

    @_guard
    def paste_text(self, text):
        text = text.strip().replace(",", "").replace(" ", "")
        if not text:
            return
        self.error = None
        self._new_entry()
        neg = text.startswith("-")
        if neg or text.startswith("+"):
            text = text[1:]
        for ch in text:
            if ch == ".":
                self._entry.add_point()
            elif ch in "eE" and self.base == 10:
                self._entry.start_exp()
            elif ch == "-" and self._entry.exp is not None:
                self._entry.exp_neg = True
            elif ch.upper() in BASE_DIGITS:
                self._entry.add_digit(ch)
        self._entry.neg = neg
