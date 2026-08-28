import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from xpcalc.engine import Engine


def run(engine, seq):
    """Feed a compact key sequence: digits, ops, '=' etc."""
    for tok in seq.split():
        if tok.isdigit() or (len(tok) == 1 and tok.upper() in "ABCDEF"):
            for ch in tok:
                engine.digit(ch)
        elif tok == ".":
            engine.point()
        elif tok == "=":
            engine.equals()
        elif tok == "(":
            engine.open_paren()
        elif tok == ")":
            engine.close_paren()
        elif tok == "+/-":
            engine.sign()
        else:
            engine.operator(tok)
    return engine.display


class TestArithmetic(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_add(self):
        self.assertEqual(run(self.e, "2 + 3 ="), "5.")

    def test_precedence_scientific(self):
        self.assertEqual(run(self.e, "2 + 3 * 4 ="), "14.")

    def test_no_precedence_standard(self):
        self.e.set_mode("standard")
        self.assertEqual(run(self.e, "2 + 3 * 4 ="), "20.")

    def test_parens(self):
        self.assertEqual(run(self.e, "2 * ( 3 + 4 ) ="), "14.")

    def test_nested_parens(self):
        self.assertEqual(run(self.e, "2 * ( 3 + ( 4 - 1 ) ) ="), "12.")

    def test_divide_by_zero(self):
        self.assertEqual(run(self.e, "5 / 0 ="), "Cannot divide by zero")

    def test_decimal_exact(self):
        self.assertEqual(run(self.e, "0 . 1 + 0 . 2 ="), "0.3")

    def test_repeat_equals(self):
        run(self.e, "2 + 3 =")
        self.e.equals()
        self.assertEqual(self.e.display, "8.")

    def test_operator_replace(self):
        self.assertEqual(run(self.e, "8 + - 3 ="), "5.")

    def test_chained(self):
        self.assertEqual(run(self.e, "1 + 2 + 3 + 4 ="), "10.")

    def test_sign(self):
        self.assertEqual(run(self.e, "5 +/- + 2 ="), "-3.")


class TestFunctions(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_sqrt(self):
        run(self.e, "9")
        self.e.unary("sqrt")
        self.assertEqual(self.e.display, "3.")

    def test_factorial(self):
        run(self.e, "10")
        self.e.unary("n!")
        self.assertEqual(self.e.display, "3628800.")

    def test_sin_degrees(self):
        run(self.e, "30")
        self.e.unary("sin")
        self.assertTrue(self.e.display.startswith("0.5"))

    def test_sin_radians(self):
        self.e.set_angle("rad")
        run(self.e, "0")
        self.e.unary("sin")
        self.assertEqual(self.e.display, "0.")

    def test_asin(self):
        run(self.e, "1")
        self.e.unary("sin", inv=True)
        self.assertTrue(self.e.display.startswith("90"))

    def test_hyp(self):
        self.e.set_angle("rad")
        run(self.e, "0")
        self.e.unary("cos", hyp=True)
        self.assertEqual(self.e.display, "1.")

    def test_ln_exp_roundtrip(self):
        run(self.e, "1")
        self.e.unary("ln", inv=True)
        self.e.unary("ln")
        self.assertTrue(self.e.display.startswith("1"))

    def test_power(self):
        self.assertEqual(run(self.e, "2 ^ 10 ="), "1024.")

    def test_reciprocal_zero(self):
        run(self.e, "0")
        self.e.unary("1/x")
        self.assertEqual(self.e.display, "Cannot divide by zero")

    def test_percent(self):
        run(self.e, "200 +")
        run(self.e, "10")
        self.e.percent()
        self.e.equals()
        self.assertEqual(self.e.display, "220.")

    def test_int_and_frac(self):
        run(self.e, "3 . 75")
        self.e.unary("Int")
        self.assertEqual(self.e.display, "3.")
        run(self.e, "3 . 75")
        self.e.unary("Int", inv=True)
        self.assertEqual(self.e.display, "0.75")

    def test_dms(self):
        run(self.e, "1 . 5")
        self.e.unary("dms")
        self.assertEqual(self.e.display, "1.3")
        self.e.unary("dms", inv=True)
        self.assertEqual(self.e.display, "1.5")

    def test_pi(self):
        self.e.unary("pi")
        self.assertTrue(self.e.display.startswith("3.14159265358979"))


class TestBases(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_hex_display(self):
        run(self.e, "255")
        self.e.set_base(16)
        self.assertEqual(self.e.display, "FF")

    def test_hex_entry(self):
        self.e.set_base(16)
        run(self.e, "F F")
        self.e.set_base(10)
        self.assertEqual(self.e.display, "255.")

    def test_bin(self):
        run(self.e, "5")
        self.e.set_base(2)
        self.assertEqual(self.e.display, "101")

    def test_and(self):
        self.e.set_base(16)
        self.assertEqual(run(self.e, "F 0 And 3 F ="), "30")

    def test_lsh(self):
        self.e.set_base(10)
        self.e.set_base(16)
        self.assertEqual(run(self.e, "1 Lsh 4 ="), "10")

    def test_not_dword(self):
        self.e.set_base(16)
        self.e.set_word("dword")
        run(self.e, "1")
        self.e.unary("Not")
        self.assertEqual(self.e.display, "FFFFFFFE")
        self.e.set_base(10)
        self.assertEqual(self.e.display, "-2.")

    def test_byte_wrap(self):
        self.e.set_base(16)
        self.e.set_word("byte")
        self.assertEqual(run(self.e, "F F + 2 ="), "1")

    def test_mod(self):
        self.assertEqual(run(self.e, "17 Mod 5 ="), "2.")

    def test_truncate_on_base_switch(self):
        run(self.e, "3 . 9")
        self.e.set_base(16)
        self.assertEqual(self.e.display, "3")


class TestMemoryStats(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_memory(self):
        run(self.e, "7")
        self.e.memory_op("MS")
        run(self.e, "3")
        self.e.memory_op("M+")
        self.e.clear_all()
        self.e.memory_op("MR")
        self.assertEqual(self.e.display, "10.")
        self.assertTrue(self.e.memory_set)
        self.e.memory_op("MC")
        self.assertFalse(self.e.memory_set)

    def test_stats(self):
        for v in ("2", "4", "4", "4", "5", "5", "7", "9"):
            run(self.e, v)
            self.e.stat_add()
        self.e.stat_result("Ave")
        self.assertEqual(self.e.display, "5.")
        self.e.stat_result("Sum")
        self.assertEqual(self.e.display, "40.")
        self.e.stat_result("s", inv=True)      # population sigma
        self.assertEqual(self.e.display, "2.")


class TestDisplay(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_backspace(self):
        run(self.e, "123")
        self.e.backspace()
        self.assertEqual(self.e.display, "12")

    def test_clear_entry_keeps_pending(self):
        run(self.e, "5 + 9")
        self.e.clear_entry()
        run(self.e, "3 =")
        self.assertEqual(self.e.display, "8.")

    def test_grouping(self):
        self.e.grouping = True
        self.assertEqual(run(self.e, "1234567 ="), "1,234,567.")

    def test_fe_notation(self):
        run(self.e, "1234 =")
        self.e.toggle_fe()
        self.assertEqual(self.e.display, "1.234e+3")

    def test_big_number_auto_sci(self):
        run(self.e, "9 ^ 99 =")
        self.assertIn("e+", self.e.display)

    def test_exp_entry(self):
        run(self.e, "5")
        self.e.exp_entry()
        run(self.e, "3")
        self.e.equals()
        self.assertEqual(self.e.display, "5000.")

    def test_error_locks_then_clears(self):
        run(self.e, "1 / 0 =")
        self.e.digit("5")
        self.assertEqual(self.e.display, "Cannot divide by zero")
        self.e.clear_all()
        self.assertEqual(self.e.display, "0.")

    def test_paste(self):
        self.e.paste_text("-1,234.5")
        self.assertEqual(self.e.display, "-1234.5")


if __name__ == "__main__":
    unittest.main(verbosity=1)


class TestInverseOperators(unittest.TestCase):
    def setUp(self):
        self.e = Engine()

    def test_root(self):
        self.assertEqual(run(self.e, "27 root 3 ="), "3.")

    def test_root_negative_odd(self):
        self.assertEqual(run(self.e, "8 +/- root 3 ="), "-2.")

    def test_rsh(self):
        self.e.set_base(16)
        self.assertEqual(run(self.e, "10 Rsh 4 ="), "1")

    def test_cube_root(self):
        run(self.e, "125")
        self.e.unary("x^3", inv=True)
        self.assertEqual(self.e.display, "5.")

    def test_ten_to_the_x(self):
        run(self.e, "3")
        self.e.unary("log", inv=True)
        self.assertEqual(self.e.display, "1000.")


class TestExpression(unittest.TestCase):
    """The running task shown above the display until '=' is pressed."""

    def setUp(self):
        self.e = Engine()

    def test_builds_while_typing(self):
        run(self.e, "12 + 34 *")
        self.assertEqual(self.e.expression, "12 + 34 *")

    def test_typed_operand_is_not_shown_twice(self):
        run(self.e, "12 + 34")
        self.assertEqual(self.e.expression, "12 +")

    def test_cleared_by_equals(self):
        run(self.e, "2 + 3 =")
        self.assertEqual(self.e.expression, "")

    def test_cleared_by_clear_all(self):
        run(self.e, "2 + 3")
        self.e.clear_all()
        self.assertEqual(self.e.expression, "")

    def test_survives_clear_entry(self):
        run(self.e, "2 + 3")
        self.e.clear_entry()
        self.assertEqual(self.e.expression, "2 +")

    def test_parens(self):
        run(self.e, "2 * ( 3 + 4 )")
        self.assertEqual(self.e.expression, "2 * (3 + 4)")

    def test_nested_parens(self):
        run(self.e, "2 * ( 3 + ( 4 - 1 ) )")
        self.assertEqual(self.e.expression, "2 * (3 + (4 - 1))")

    def test_unary_shown_immediately(self):
        run(self.e, "9")
        self.e.unary("sqrt")
        self.assertEqual(self.e.expression, "sqrt(9)")

    def test_unary_nests(self):
        run(self.e, "9")
        self.e.unary("sqrt")
        self.e.unary("x^2")
        self.assertEqual(self.e.expression, "sqr(sqrt(9))")

    def test_unary_reuses_group_brackets(self):
        run(self.e, "( 2 + 3 )")
        self.e.unary("sqrt")
        self.assertEqual(self.e.expression, "sqrt(2 + 3)")

    def test_inverse_and_hyperbolic_labels(self):
        run(self.e, "1")
        self.e.unary("sin", inv=True)
        self.assertEqual(self.e.expression, "asin(1)")
        self.e.clear_all()
        run(self.e, "1")
        self.e.unary("sin", inv=True, hyp=True)
        self.assertEqual(self.e.expression, "asinh(1)")

    def test_pi_is_a_constant_not_a_call(self):
        self.e.unary("pi")
        self.assertEqual(self.e.expression, "pi")

    def test_operator_replacement_replaces_token(self):
        run(self.e, "8 + -")
        self.assertEqual(self.e.expression, "8 -")

    def test_no_trailing_point_on_operands(self):
        run(self.e, "5 =")
        run(self.e, "+")
        self.assertEqual(self.e.expression, "5 +")

    def test_decimals_kept(self):
        run(self.e, "1 . 5 +")
        self.assertEqual(self.e.expression, "1.5 +")

    def test_follows_digit_grouping(self):
        self.e.grouping = True
        run(self.e, "1234567 +")
        self.assertEqual(self.e.expression, "1,234,567 +")

    def test_hex_operands(self):
        self.e.set_base(16)
        run(self.e, "F F")
        self.e.operator("And")
        self.assertEqual(self.e.expression, "FF And")

    def test_memory_recall_is_a_plain_operand(self):
        run(self.e, "7")
        self.e.memory_op("MS")
        self.e.clear_all()
        self.e.memory_op("MR")
        self.e.operator("+")
        self.assertEqual(self.e.expression, "7 +")

    def test_standard_mode_too(self):
        self.e.set_mode("standard")
        run(self.e, "2 + 3 *")
        self.assertEqual(self.e.expression, "2 + 3 *")


class TestAnglePrecision(unittest.TestCase):
    """Angle conversion must not cost digits (asin(1) is exactly 90 degrees)."""

    def test_asin_one_is_ninety(self):
        e = Engine()
        run(e, "1")
        e.unary("sin", inv=True)
        self.assertEqual(e.display, "90.")

    def test_acos_zero_is_ninety(self):
        e = Engine()
        run(e, "0")
        e.unary("cos", inv=True)
        self.assertEqual(e.display, "90.")

    def test_atan_one_is_fortyfive(self):
        e = Engine()
        run(e, "1")
        e.unary("tan", inv=True)
        self.assertEqual(e.display, "45.")

    def test_asin_one_in_grads(self):
        e = Engine()
        e.set_angle("grad")
        run(e, "1")
        e.unary("sin", inv=True)
        self.assertEqual(e.display, "100.")
