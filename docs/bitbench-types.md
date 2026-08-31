# BitBench type interpretations

xpcalc includes a BitBench-style binary/type workbench under **Tools → Type interpretations…**.

The integration is intentionally separate from the calculator arithmetic engine. It accepts a bit pattern, interprets it in multiple formats, and can send the raw bits back to the calculator in its current number base.

## Input

The workbench accepts 8, 16, 32, and 64-bit values in:

- automatic mode;
- hexadecimal;
- unsigned decimal;
- signed decimal (two's complement);
- binary;
- octal;
- floating point.

Float input is reinterpreted as IEEE bits rather than converted to an integer. It also accepts a restricted mathematical expression syntax (`sqrt(2)`, `sin(pi/4)`, `2^10`, etc.). The expression evaluator uses a whitelisted AST and never calls Python `eval`.

## BitBench registry parity

`xpcalc._interpret.FORMAT_DEFINITIONS` mirrors the 99 entries in BitBench's `FORMATS` registry. Smaller formats automatically appear as little-endian arrays when the selected word is wider, matching BitBench behavior.

The registry includes:

- signed and unsigned 8/16/32/64-bit integers, including LE/BE variants;
- Gray8/16/32/64 and Zigzag8/16/32/64;
- Minifloat8 and IEEE Float16/32/64 LE/BE;
- BFloat8/16/32/64, including all BitBench BE variants;
- FP8 E4M3/E5M2 and TensorFloat-32;
- IBM HFP32, VAX F, MBF32/64;
- Decimal8/16/32/64, including Decimal16 BE;
- Posit8/16/32;
- signed and unsigned Q-format fixed point;
- packed BCD8/16/32/64 and unpacked BCD;
- RGB/RGBA, RGB565/555, ARGB1555/4444, BGR/BGRA/ABGR and HSV;
- Unix32/64, DOS/FAT, FILETIME, NTP, OLE Date, HFS+, GPS, WebKit and .NET ticks;
- μ-law, A-law and MIDI notes;
- ASCII8/16/32/64, EBCDIC and UTF-8/16/32;
- IPv4, lower IPv6, MAC-48, TCP/UDP ports, FourCC and OLE Currency.

Aliases from BitBench are retained in the registry and can be resolved with `find_format()`. Tests assert the complete ID set and the applicable format counts for every supported word width, so losing a format is a regression rather than a silent simplification.

## Source

This implementation is adapted from [Hawkynt BitBench](https://github.com/Hawkynt/Hawkynt.github.io/tree/main/BitBench) with explicit permission from its author for this integration.
