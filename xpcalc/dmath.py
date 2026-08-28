"""32-digit transcendental functions on :class:`decimal.Decimal`.

Python's ``math`` module tops out at double precision, which would make
``sin(30)`` read ``0.49999999999999994``.  The XP calculator carries 32
significant digits through every function, so we do the same: exp/ln/log10/
sqrt come from Decimal itself, the rest are series expansions evaluated with
guard digits.
"""

from decimal import Decimal, localcontext

# pi to 60 digits - enough guard digits for the 32 we display.
PI = Decimal("3."
             "14159265358979323846264338327950288419716939937510582097494")
GUARD = 12


def _series_done(term, prec):
    return term == 0 or term.adjusted() < -(prec + 5)


def exp(x):
    return x.exp()


def ln(x):
    if x <= 0:
        raise ValueError("ln domain")
    return x.ln()


def log10(x):
    if x <= 0:
        raise ValueError("log10 domain")
    return x.log10()


def sqrt(x):
    if x < 0:
        raise ValueError("sqrt domain")
    return x.sqrt()


def _reduce_two_pi(x, ctx):
    two_pi = +PI * 2
    if abs(x) >= two_pi:
        x -= two_pi * (x / two_pi).to_integral_value(rounding="ROUND_FLOOR")
    return x


def sin(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        x = _reduce_two_pi(Decimal(x), ctx)
        total = term = x
        x2 = x * x
        n = 1
        while True:
            n += 2
            term = -term * x2 / (n * (n - 1))
            if _series_done(term, ctx.prec):
                break
            total += term
    return +total


def cos(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        x = _reduce_two_pi(Decimal(x), ctx)
        total = term = Decimal(1)
        x2 = x * x
        n = 0
        while True:
            n += 2
            term = -term * x2 / (n * (n - 1))
            if _series_done(term, ctx.prec):
                break
            total += term
    return +total


def tan(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        c = cos(x)
        if c == 0:
            raise ZeroDivisionError("tan pole")
        total = sin(x) / c
    return +total


def atan(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        x = Decimal(x)
        halvings = 0
        limit = Decimal("0.05")
        while abs(x) > limit:
            x = x / (1 + (1 + x * x).sqrt())
            halvings += 1
        total = term = x
        x2 = x * x
        n = 1
        while True:
            n += 2
            term = -term * x2
            piece = term / n
            if _series_done(piece, ctx.prec):
                break
            total += piece
        total *= 2 ** halvings
    return +total


def asin(x):
    x = Decimal(x)
    if abs(x) > 1:
        raise ValueError("asin domain")
    with localcontext() as ctx:
        ctx.prec += GUARD
        if abs(x) == 1:
            total = (PI / 2).copy_sign(x)
        else:
            total = atan(x / (1 - x * x).sqrt())
    return +total


def acos(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        total = PI / 2 - asin(x)
    return +total


def sinh(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        e = Decimal(x).exp()
        total = (e - 1 / e) / 2
    return +total


def cosh(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        e = Decimal(x).exp()
        total = (e + 1 / e) / 2
    return +total


def tanh(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        e = (Decimal(x) * 2).exp()
        total = (e - 1) / (e + 1)
    return +total


def asinh(x):
    with localcontext() as ctx:
        ctx.prec += GUARD
        x = Decimal(x)
        total = (x + (x * x + 1).sqrt()).ln()
    return +total


def acosh(x):
    x = Decimal(x)
    if x < 1:
        raise ValueError("acosh domain")
    with localcontext() as ctx:
        ctx.prec += GUARD
        total = (x + (x * x - 1).sqrt()).ln()
    return +total


def atanh(x):
    x = Decimal(x)
    if abs(x) >= 1:
        raise ValueError("atanh domain")
    with localcontext() as ctx:
        ctx.prec += GUARD
        total = ((1 + x) / (1 - x)).ln() / 2
    return +total


def power(a, b):
    """a ** b for Decimals, exact for integer exponents."""
    if b == b.to_integral_value() and abs(b) < 100000:
        return a ** int(b)
    if a < 0:
        raise ValueError("negative base, fractional exponent")
    if a == 0:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec += GUARD
        total = (b * a.ln()).exp()
    return +total


def trig(name, x, angle):
    """sin/cos/tan of an angle, converted and evaluated in one context.

    Rounding the radian value to display precision first would cost the last
    couple of digits, so the conversion and the series share guard digits.
    """
    with localcontext() as ctx:
        ctx.prec += GUARD
        total = {"sin": sin, "cos": cos, "tan": tan}[name](radians(x, angle))
    return +total


def inverse_trig(name, x, angle):
    """asin/acos/atan, returned in the current angle unit."""
    with localcontext() as ctx:
        ctx.prec += GUARD
        radian = {"sin": asin, "cos": acos, "tan": atan}[name](x)
        total = from_radians(radian, angle)
    return +total


def root(a, b):
    """The b-th root of a, kept accurate to the full display precision.

    Computing ``a ** (1 / b)`` would round 1/b first and lose the last few
    digits, so divide inside the logarithm instead.
    """
    if b == 0:
        raise ZeroDivisionError("zeroth root")
    if a == 0:
        return Decimal(0)
    negative = a < 0
    if negative:
        if b != b.to_integral_value() or int(b) % 2 == 0:
            raise ValueError("even root of a negative number")
        a = -a
    with localcontext() as ctx:
        ctx.prec += GUARD * 2
        total = (a.ln() / b).exp()
        if negative:
            total = -total
    return +total


def radians(x, angle):
    if angle == "deg":
        with localcontext() as ctx:
            ctx.prec += GUARD
            return +(Decimal(x) * PI / 180)
    if angle == "grad":
        with localcontext() as ctx:
            ctx.prec += GUARD
            return +(Decimal(x) * PI / 200)
    return Decimal(x)


def from_radians(x, angle):
    if angle == "deg":
        with localcontext() as ctx:
            ctx.prec += GUARD
            return +(Decimal(x) * 180 / PI)
    if angle == "grad":
        with localcontext() as ctx:
            ctx.prec += GUARD
            return +(Decimal(x) * 200 / PI)
    return Decimal(x)
