import unittest

from xpcalc.bittypes import (
    FORMAT_DEFINITIONS,
    InputError,
    calculator_input,
    find_format,
    format_bits,
    interpretations,
    parse_input,
    swap_bytes,
    to_signed,
)


def values_for(value, width):
    return {item.name: item.value for item in interpretations(value, width)}


class InputTests(unittest.TestCase):
    def test_prefixed_integer_inputs(self):
        self.assertEqual(parse_input("0xDE_AD_BE_EF", "auto", 32), 0xDEADBEEF)
        self.assertEqual(parse_input("0b1010", "auto", 8), 10)
        self.assertEqual(parse_input("0o377", "auto", 8), 255)

    def test_explicit_bare_hex(self):
        self.assertEqual(parse_input("DEADBEEF", "hex", 32), 0xDEADBEEF)

    def test_auto_bare_hex_does_not_confuse_e_with_exponent(self):
        self.assertEqual(parse_input("DEADBEEF", "auto", 32), 0xDEADBEEF)

    def test_auto_scientific_decimal_stays_float(self):
        self.assertEqual(parse_input("1E3", "auto", 32), 0x447A0000)

    def test_signed_input_is_twos_complement(self):
        self.assertEqual(parse_input("-1", "signed", 16), 0xFFFF)
        self.assertEqual(parse_input("-32768", "signed", 16), 0x8000)

    def test_signed_overflow_is_rejected(self):
        with self.assertRaises(InputError):
            parse_input("128", "signed", 8)
        with self.assertRaises(InputError):
            parse_input("-129", "signed", 8)

    def test_unsigned_overflow_is_rejected(self):
        with self.assertRaises(InputError):
            parse_input("256", "decimal", 8)

    def test_float_input_is_reinterpreted_not_converted_to_integer(self):
        self.assertEqual(parse_input("1.0", "float", 32), 0x3F800000)
        self.assertEqual(parse_input("-0", "float", 32), 0x00000000)
        self.assertEqual(parse_input("-0.0", "float", 32), 0x80000000)
        self.assertEqual(parse_input("inf", "float", 16), 0x7C00)

    def test_float_expression_input(self):
        self.assertEqual(parse_input("sqrt(4)", "float", 32), 0x40000000)
        result = parse_input("sin(pi/2)", "float", 64)
        self.assertEqual(result, 0x3FF0000000000000)

    def test_decimal_comma_float_input(self):
        self.assertEqual(parse_input("1,5", "float", 32), 0x3FC00000)
        self.assertEqual(parse_input("1,5", "auto", 32), 0x3FC00000)

    def test_float_expression_is_not_python_eval(self):
        with self.assertRaises(InputError):
            parse_input("__import__('os').system('true')", "float", 64)
        with self.assertRaises(InputError):
            parse_input("(1).__class__", "float", 64)

    def test_auto_detects_float_expression(self):
        self.assertEqual(parse_input("1/2", "auto", 32), 0x3F000000)

    def test_xpcalc_integer_trailing_dot_stays_integer(self):
        self.assertEqual(calculator_input("5.", 10), ("5", "decimal"))
        self.assertEqual(calculator_input("-5.", 10), ("-5", "signed"))

    def test_xpcalc_real_decimal_stays_float(self):
        self.assertEqual(calculator_input("0.5", 10), ("0.5", "float"))
        self.assertEqual(calculator_input("1.e+3", 10), ("1.e+3", "float"))

    def test_format_bits(self):
        self.assertEqual(format_bits(0x2A, 8, 16), "2A")
        self.assertEqual(format_bits(5, 8, 2), "00000101")
        self.assertEqual(format_bits(8, 8, 8), "10")
        self.assertEqual(format_bits(42, 8, 10), "42")


class PrimitiveConversionTests(unittest.TestCase):
    def test_byte_swap(self):
        self.assertEqual(swap_bytes(0x12345678, 32), 0x78563412)

    def test_twos_complement(self):
        self.assertEqual(to_signed(0xFF, 8), -1)
        self.assertEqual(to_signed(0x7F, 8), 127)

    def test_integer_endianness(self):
        values = values_for(0x1234, 16)
        self.assertEqual(values["Word"], "4660")
        self.assertEqual(values["Word BE"], "13330")

    def test_integer_arrays_follow_bitbench_little_endian_chunk_order(self):
        values = values_for(0x0201, 16)
        self.assertEqual(values["Byte"], "[ 1, 2 ]")

    def test_gray_and_zigzag(self):
        values = values_for(0b0110, 8)
        self.assertEqual(values["Gray8"], "4")
        self.assertEqual(values_for(1, 8)["Zigzag8"], "-1")
        self.assertEqual(values_for(2, 8)["Zigzag8"], "1")


class FloatInterpretationTests(unittest.TestCase):
    def test_ieee_float32(self):
        values = values_for(0x3F800000, 32)
        self.assertEqual(values["Float32"], "1")
        self.assertNotEqual(values["Float32 BE"], "1")

    def test_ieee_float64(self):
        values = values_for(0x3FF0000000000000, 64)
        self.assertEqual(values["Float64"], "1")

    def test_ieee_half(self):
        values = values_for(0x3C00, 16)
        self.assertEqual(values["Float16"], "1")

    def test_nan_and_negative_zero(self):
        self.assertEqual(values_for(0x7FC00000, 32)["Float32"], "NaN")
        self.assertEqual(values_for(0x80000000, 32)["Float32"], "-0")

    def test_bfloat16(self):
        self.assertEqual(values_for(0x3F80, 16)["BFloat16"], "1")

    def test_fp8_e5m2_infinity(self):
        self.assertEqual(values_for(0x7C, 8)["FP8-E5M2"], "Infinity")


class FormatInterpretationTests(unittest.TestCase):
    def test_fixed_point(self):
        values = values_for(0x0180, 16)
        self.assertEqual(values["Q7.8"], "1.5")
        self.assertEqual(values["UQ8.8"], "1.5")

    def test_negative_fixed_point(self):
        values = values_for(0xFF80, 16)
        self.assertEqual(values["Q7.8"], "-0.5")

    def test_bcd(self):
        self.assertEqual(values_for(0x1234, 16)["BCD16"], "1234")
        self.assertEqual(values_for(0x1A, 8)["BCD8"], "Invalid BCD")

    def test_characters(self):
        values = values_for(0x4241, 16)
        self.assertEqual(values["ASCII"], "[ 'A', 'B' ]")
        self.assertEqual(values["ASCII16"], '"AB"')

    def test_unicode_scalar(self):
        self.assertIn("'A' U+0041", values_for(0x41, 32)["UTF-32"])

    def test_utf8_unit_classification(self):
        self.assertEqual(values_for(0xC2, 8)["UTF-8"], "(2-byte lead)")
        self.assertEqual(values_for(0x80, 8)["UTF-8"], "(cont)")

    def test_utf16_surrogate_classification(self):
        self.assertEqual(values_for(0xD800, 16)["UTF-16"],
                         "U+D800 (high surrogate)")

    def test_rgb565(self):
        self.assertEqual(values_for(0xF800, 16)["RGB565"], "rgb(255,0,0)")

    def test_rgba(self):
        self.assertEqual(values_for(0x80FF0000, 32)["RGBA"],
                         "rgba(255,0,0,0.50)")

    def test_unix_epoch(self):
        self.assertEqual(values_for(0, 32)["Unix32"],
                         "1970-01-01T00:00:00Z")

    def test_filetime_epoch(self):
        self.assertEqual(values_for(0, 64)["FILETIME"],
                         "1601-01-01T00:00:00Z")

    def test_ntp_epoch(self):
        self.assertEqual(values_for(0, 64)["NTP"],
                         "1900-01-01T00:00:00Z")

    def test_ole_date_epoch(self):
        self.assertEqual(values_for(0, 64)["OLE Date"],
                         "1899-12-30T00:00:00Z")

    def test_dos_datetime(self):
        date = ((2026 - 1980) << 9) | (8 << 5) | 31
        time = 10 << 11
        values = values_for((date << 16) | time, 32)
        self.assertEqual(values["DOS DateTime"], "2026-08-31T10:00:00")

    def test_ipv4(self):
        self.assertEqual(values_for(0xC0A80101, 32)["IPv4"], "192.168.1.1")

    def test_ipv4_and_ports_array_at_qword_width(self):
        value = (0x7F000001 << 32) | 0xC0A80101
        values = values_for(value, 64)
        self.assertEqual(values["IPv4"],
                         "[ 192.168.1.1, 127.0.0.1 ]")
        self.assertIn("Port", values)

    def test_fourcc_uses_file_byte_order(self):
        self.assertEqual(values_for(0x46464952, 32)["FourCC"], '"RIFF"')

    def test_mac48(self):
        values = values_for(0x001122334455, 64)
        self.assertEqual(values["MAC"], "00:11:22:33:44:55")

    def test_currency(self):
        self.assertEqual(values_for(123456, 64)["Currency"], "$12.3456")

    def test_g711_silence_codes(self):
        values = values_for(0xFF, 8)
        self.assertEqual(values["μ-law"], "PCM: 0")
        self.assertEqual(values_for(0xD5, 8)["A-law"], "PCM: -8")

    def test_midi_a4(self):
        self.assertTrue(values_for(69, 8)["MIDI Note"].startswith("A4 (440.000 Hz)"))

    def test_decimal_and_unpacked_bcd(self):
        values = values_for(0x12, 8)
        self.assertIn("Decimal8", values)
        self.assertEqual(values_for(0x0201, 16)["Unpacked BCD"], "[ 1, 2 ]")

    def test_argb4444(self):
        self.assertEqual(values_for(0xFF00, 16)["ARGB4444"],
                         "rgba(255,0,0,1.00)")

    def test_tf32_one(self):
        self.assertEqual(values_for(0x3F800000, 32)["TF32"], "1")

    def test_vax_f_is_exposed(self):
        self.assertIn("VAX F", values_for(0, 32))


class BitBenchCatalogTests(unittest.TestCase):
    EXPECTED_IDS = {
        "uint8", "int8", "uint16_le", "uint16_be", "int16_le", "int16_be",
        "uint32_le", "uint32_be", "int32_le", "int32_be", "uint64_le",
        "uint64_be", "int64_le", "int64_be",
        "float16_le", "float16_be", "float32_le", "float32_be", "float64_le",
        "float64_be", "minifloat8",
        "bfloat8", "bfloat16_le", "bfloat16_be", "bfloat32_le", "bfloat32_be",
        "bfloat64_le", "bfloat64_be", "fp8e4m3", "fp8e5m2", "tf32",
        "ibm_float32", "vax_f", "mbf32", "mbf64", "decimal8", "decimal16_le",
        "decimal16_be", "decimal32", "decimal64", "posit8", "posit16", "posit32",
        "q7_8", "q15_16", "q31_32", "uq8_8", "uq16_16", "uq32_32",
        "bcd8", "bcd16", "bcd32", "bcd64", "ubcd",
        "currency64", "filetime", "unix32", "unix64", "dosdate",
        "rgb24", "rgba32", "fourcc",
        "ascii8", "ascii16", "ascii32", "ascii64", "ebcdic8", "utf8", "utf16",
        "utf32", "ipv4", "mac48", "ipv6low", "port16",
        "rgb565", "rgb555", "argb1555", "argb4444", "bgr24", "bgra32",
        "abgr32", "hsv24", "ntp64", "oledate", "hfsplus", "gpstime",
        "webkit", "dotnet",
        "gray8", "gray16", "gray32", "gray64", "zigzag8", "zigzag16",
        "zigzag32", "zigzag64", "mulaw8", "alaw8", "midi8",
    }

    def test_registry_matches_bitbench_format_ids(self):
        self.assertEqual({definition.id for definition in FORMAT_DEFINITIONS},
                         self.EXPECTED_IDS)
        self.assertEqual(len(FORMAT_DEFINITIONS), 99)

    def test_every_width_exposes_all_applicable_formats(self):
        self.assertEqual(len(interpretations(0, 8)), 18)
        self.assertEqual(len(interpretations(0, 16)), 41)
        self.assertEqual(len(interpretations(0, 32)), 74)
        self.assertEqual(len(interpretations(0, 64)), 99)

    def test_alias_lookup_matches_bitbench_names(self):
        self.assertEqual(find_format("DWORD").id, "uint32_le")
        self.assertEqual(find_format("F_floating").id, "vax_f")
        self.assertEqual(find_format("COLORREF").id, "bgr24")
        self.assertEqual(find_format("DateTime.Ticks").id, "dotnet")
        self.assertEqual(find_format("G.711μ").id, "mulaw8")

    def test_wider_words_array_all_smaller_gray_and_zigzag_types(self):
        values = values_for(0x0201, 16)
        self.assertEqual(values["Gray8"], "[ 1, 3 ]")
        self.assertEqual(values["Zigzag8"], "[ -1, 1 ]")
        self.assertIn("Gray16", values)
        self.assertIn("Zigzag16", values)

    def test_missing_family_regressions_are_present(self):
        values16 = values_for(0, 16)
        self.assertIn("Decimal16 BE", values16)
        self.assertIn("BFloat16 BE", values16)
        values64 = values_for(0, 64)
        self.assertIn("BFloat64 BE", values64)
        self.assertIn("IPv6 (low)", values64)
        self.assertIn("WebKit", values64)
        self.assertIn(".NET Ticks", values64)


if __name__ == "__main__":
    unittest.main()
