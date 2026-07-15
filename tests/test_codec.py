"""Tests for the codec (encode/decode) functions."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

import dbckit
from dbckit.codec.decoder import decode_signal
from dbckit.codec.encoder import encode_signal
from dbckit.model.signal import ByteOrder, Signal

FIXTURES = Path(__file__).parent / "fixtures"


def _sig(
    name="S",
    start_bit=0,
    length=8,
    byte_order=ByteOrder.little_endian,
    is_signed=False,
    factor=1.0,
    offset=0.0,
    signal_type=None,
) -> Signal:
    return Signal(
        name=name,
        start_bit=start_bit,
        length=length,
        byte_order=byte_order,
        is_signed=is_signed,
        factor=factor,
        offset=offset,
        signal_type=signal_type,
    )


class TestLittleEndianDecode:
    def test_simple_byte(self):
        assert decode_signal(b"\x42" + b"\x00" * 7, _sig()) == pytest.approx(0x42)

    def test_factor_offset(self):
        assert decode_signal(bytes([100]) + b"\x00" * 7, _sig(factor=0.5, offset=10)) == pytest.approx(60.0)

    def test_signed_negative(self):
        assert decode_signal(b"\xff" + b"\x00" * 7, _sig(is_signed=True)) == pytest.approx(-1.0)

    def test_16bit_spanning_bytes(self):
        data = bytes([0x64, 0x00])
        assert decode_signal(data + b"\x00" * 6, _sig(length=16, factor=0.1)) == pytest.approx(10.0)

    def test_mid_byte_start(self):
        assert decode_signal(b"\xa0" + b"\x00" * 7, _sig(start_bit=4, length=4)) == pytest.approx(10.0)

    def test_two_signals_no_overlap(self):
        data = bytes([0x01, 0x02]) + b"\x00" * 6
        assert decode_signal(data, _sig("lo", 0, 8)) == pytest.approx(1.0)
        assert decode_signal(data, _sig("hi", 8, 8)) == pytest.approx(2.0)


class TestBigEndianDecode:
    def test_simple_byte(self):
        sig = _sig(start_bit=7, length=8, byte_order=ByteOrder.big_endian)
        assert decode_signal(b"\x42" + b"\x00" * 7, sig) == pytest.approx(0x42)

    def test_10bit_cross_boundary(self):
        sig = _sig(start_bit=39, length=10, byte_order=ByteOrder.big_endian, factor=0.1)
        data = bytearray(8)
        encode_signal(data, sig, 51.0)
        assert decode_signal(bytes(data), sig) == pytest.approx(51.0, abs=0.01)


class TestFloatSignals:
    @pytest.mark.parametrize(
        ("signal_type", "length", "fmt", "physical"),
        [(1, 32, "f", 1.5), (2, 64, "d", -123.25)],
    )
    @pytest.mark.parametrize("byte_order", list(ByteOrder))
    def test_ieee754_decode_and_encode(
        self,
        signal_type: int,
        length: int,
        fmt: str,
        physical: float,
        byte_order: ByteOrder,
    ):
        start_bit = 0 if byte_order == ByteOrder.little_endian else 7
        byte_prefix = "<" if byte_order == ByteOrder.little_endian else ">"
        expected = struct.pack(f"{byte_prefix}{fmt}", physical)
        sig = _sig(
            start_bit=start_bit,
            length=length,
            byte_order=byte_order,
            signal_type=signal_type,
        )

        assert decode_signal(expected, sig) == pytest.approx(physical)

        data = bytearray(length // 8)
        encode_signal(data, sig, physical)
        assert bytes(data) == expected

    def test_float_applies_factor_and_offset(self):
        sig = _sig(length=32, factor=2.0, offset=10.0, signal_type=1)
        data = bytearray(4)
        encode_signal(data, sig, 13.0)

        assert bytes(data) == struct.pack("<f", 1.5)
        assert decode_signal(bytes(data), sig) == pytest.approx(13.0)

    def test_frame_codec_uses_parsed_signal_type(self):
        db = dbckit.parse("""\
VERSION ""
NS_ :
BS_ :
BU_ : ECU
BO_ 100 FloatFrame: 4 ECU
 SG_ Value : 0|32@1+ (1,0) [0|0] "" ECU
SIG_VALTYPE_ 100 Value : 1;
""")

        payload = dbckit.encode_frame(db, 100, {"Value": 1.5})

        assert payload == struct.pack("<f", 1.5)
        assert dbckit.decode_frame(db, 100, payload)["Value"] == pytest.approx(1.5)

    def test_signal_type_zero_uses_integer_codec(self):
        sig = _sig(signal_type=0)
        data = bytearray(1)

        encode_signal(data, sig, 42.0)

        assert data == b"\x2a"
        assert decode_signal(bytes(data), sig) == pytest.approx(42.0)

    def test_float_overflow_raises_clear_error(self):
        sig = _sig(length=32, signal_type=1)
        with pytest.raises(ValueError, match="cannot be represented as an IEEE-754 float"):
            encode_signal(bytearray(4), sig, 1e100)

    @pytest.mark.parametrize("operation", ["decode", "encode"])
    def test_float_requires_32_bits(self, operation: str):
        sig = _sig(length=16, signal_type=1)
        with pytest.raises(ValueError, match="requires length 32, got 16"):
            if operation == "decode":
                decode_signal(b"\x00\x00", sig)
            else:
                encode_signal(bytearray(2), sig, 1.5)

    @pytest.mark.parametrize("operation", ["decode", "encode"])
    def test_unknown_signal_type_raises(self, operation: str):
        sig = _sig(length=32, signal_type=3)
        with pytest.raises(ValueError, match="unsupported SIG_VALTYPE_ value 3"):
            if operation == "decode":
                decode_signal(b"\x00" * 4, sig)
            else:
                encode_signal(bytearray(4), sig, 1.5)


class TestEncode:
    def test_simple_encode(self):
        data = bytearray(8)
        encode_signal(data, _sig(), 42.0)
        assert data[0] == 42

    def test_factor_offset_encode(self):
        data = bytearray(8)
        encode_signal(data, _sig(factor=0.5, offset=10), 60.0)
        assert data[0] == 100

    def test_signed_negative_encode(self):
        data = bytearray(8)
        encode_signal(data, _sig(is_signed=True), -1.0)
        assert data[0] == 0xFF

    def test_clamping_max(self):
        data = bytearray(8)
        encode_signal(data, _sig(), 1000.0)
        assert data[0] == 255

    def test_clamping_min_signed(self):
        data = bytearray(8)
        encode_signal(data, _sig(is_signed=True), -1000.0)
        assert data[0] == 0x80


class TestRoundTrip:
    @pytest.mark.parametrize("physical", [0.0, 1.0, 127.5, 255.0, 100.0])
    def test_little_endian(self, physical: float):
        sig = _sig(length=16, factor=0.1)
        data = bytearray(8)
        encode_signal(data, sig, physical)
        assert decode_signal(bytes(data), sig) == pytest.approx(physical, abs=0.01)

    @pytest.mark.parametrize("physical", [0.0, -5.0, 5.0, 50.0, -50.0])
    def test_signed(self, physical: float):
        sig = _sig(length=16, is_signed=True, factor=0.1)
        data = bytearray(8)
        encode_signal(data, sig, physical)
        assert decode_signal(bytes(data), sig) == pytest.approx(physical, abs=0.01)

    @pytest.mark.parametrize("physical", [0.0, 10.0, 51.0, 100.0])
    def test_big_endian(self, physical: float):
        sig = _sig(start_bit=7, length=8, byte_order=ByteOrder.big_endian, factor=0.5)
        data = bytearray(8)
        encode_signal(data, sig, physical)
        assert decode_signal(bytes(data), sig) == pytest.approx(physical, abs=0.01)


class TestSignedBoundaries:
    """Signed signals encode and decode correctly at the exact min/max raw value."""

    @pytest.mark.parametrize("length", [8, 16, 32])
    def test_signed_max(self, length: int):
        sig = _sig(length=length, is_signed=True)
        max_phys = float((1 << (length - 1)) - 1)
        data = bytearray(length // 8 + 1)
        encode_signal(data, sig, max_phys)
        assert decode_signal(bytes(data), sig) == pytest.approx(max_phys)

    @pytest.mark.parametrize("length", [8, 16, 32])
    def test_signed_min(self, length: int):
        sig = _sig(length=length, is_signed=True)
        min_phys = float(-(1 << (length - 1)))
        data = bytearray(length // 8 + 1)
        encode_signal(data, sig, min_phys)
        assert decode_signal(bytes(data), sig) == pytest.approx(min_phys)

    def test_signed_minus_one(self):
        sig = _sig(length=8, is_signed=True)
        data = bytearray(1)
        encode_signal(data, sig, -1.0)
        assert decode_signal(bytes(data), sig) == pytest.approx(-1.0)


class TestOverflowClamping:
    """Out-of-range physical values are clamped by default and raise in strict mode."""

    def test_clamp_unsigned_max(self):
        sig = _sig(length=8)
        data = bytearray(1)
        encode_signal(data, sig, 999.0)  # max is 255
        assert decode_signal(bytes(data), sig) == pytest.approx(255.0)

    def test_clamp_unsigned_negative(self):
        sig = _sig(length=8)
        data = bytearray(1)
        encode_signal(data, sig, -1.0)  # min is 0
        assert decode_signal(bytes(data), sig) == pytest.approx(0.0)

    def test_clamp_signed_max(self):
        sig = _sig(length=8, is_signed=True)
        data = bytearray(1)
        encode_signal(data, sig, 200.0)  # max is 127
        assert decode_signal(bytes(data), sig) == pytest.approx(127.0)

    def test_clamp_signed_min(self):
        sig = _sig(length=8, is_signed=True)
        data = bytearray(1)
        encode_signal(data, sig, -999.0)  # min is -128
        assert decode_signal(bytes(data), sig) == pytest.approx(-128.0)

    def test_strict_raises_unsigned_overflow(self):
        sig = _sig(length=8)
        data = bytearray(1)
        with pytest.raises(ValueError, match="outside"):
            encode_signal(data, sig, 999.0, strict=True)

    def test_strict_raises_signed_underflow(self):
        sig = _sig(length=8, is_signed=True)
        data = bytearray(1)
        with pytest.raises(ValueError, match="outside"):
            encode_signal(data, sig, -999.0, strict=True)

    def test_strict_does_not_raise_at_boundary(self):
        sig = _sig(length=8, is_signed=True)
        data = bytearray(1)
        encode_signal(data, sig, 127.0, strict=True)   # exactly max
        encode_signal(data, sig, -128.0, strict=True)  # exactly min

    def test_encode_frame_strict(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        with pytest.raises(ValueError, match="outside"):
            dbckit.encode_frame(db, 500, {"EngineSpeed": 99999.0}, strict=True)


class TestPayloadLength:
    """Behaviour with short (incomplete) and long (overlong) payloads."""

    def test_decode_short_payload_treats_missing_as_zero(self):
        # Signal at bits 8-15 (byte 1); omit byte 1 → raw should be 0.
        sig = _sig(start_bit=8, length=8)
        assert decode_signal(b"\xFF", sig) == pytest.approx(0.0)

    def test_decode_empty_payload(self):
        sig = _sig(start_bit=0, length=8)
        assert decode_signal(b"", sig) == pytest.approx(0.0)

    def test_decode_empty_payload_big_endian(self):
        sig = _sig(start_bit=7, length=8, byte_order=ByteOrder.big_endian)
        assert decode_signal(b"", sig) == pytest.approx(0.0)

    def test_decode_short_payload_big_endian_treats_missing_as_zero(self):
        sig = _sig(start_bit=7, length=16, byte_order=ByteOrder.big_endian)
        assert decode_signal(b"\x12", sig) == pytest.approx(0x1200)

    def test_decode_overlong_payload_reads_correct_bits(self):
        # Signal at bits 0-7 only; extra bytes must not affect the result.
        sig = _sig(start_bit=0, length=8)
        assert decode_signal(b"\x42\xFF\xFF\xFF", sig) == pytest.approx(0x42)

    def test_decode_frame_short_payload(self):
        # EngineSpeed lives at bits 0-15; passing only 1 byte → raw 0 for byte 1.
        db = dbckit.load(FIXTURES / "simple.dbc")
        vals = dbckit.decode_frame(db, 500, b"\xE8")  # only low byte present
        # raw = 0x00E8 = 232; factor=0.1 → 23.2
        assert vals["EngineSpeed"] == pytest.approx(23.2, abs=0.01)

    def test_decode_frame_overlong_payload_ignored(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        normal = dbckit.decode_frame(db, 500, b"\xE8\x03" + b"\x00" * 6)
        extra  = dbckit.decode_frame(db, 500, b"\xE8\x03" + b"\x00" * 6 + b"\xFF" * 4)
        assert normal["EngineSpeed"] == pytest.approx(extra["EngineSpeed"])


class TestDecodeFrame:
    def test_decode_frame_simple(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        data = bytes([0xE8, 0x03]) + b"\x00" * 6  # EngineSpeed raw=1000 → 100.0 rpm
        vals = dbckit.decode_frame(db, 500, data)
        assert vals["EngineSpeed"] == pytest.approx(100.0)

    def test_decode_frame_missing_id(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        with pytest.raises(KeyError):
            dbckit.decode_frame(db, 0xDEAD, b"\x00" * 8)

    def test_encode_decode_roundtrip(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        values = {"EngineSpeed": 825.0, "EngineTemp": 90.0}
        raw = dbckit.encode_frame(db, 500, values)
        decoded = dbckit.decode_frame(db, 500, raw)
        assert decoded["EngineSpeed"] == pytest.approx(825.0, abs=0.1)
        assert decoded["EngineTemp"] == pytest.approx(90.0, abs=1.0)

    def test_decode_frame_value_table_resolution(self):
        db = dbckit.load(FIXTURES / "simple.dbc")
        # IgnitionStatus=1 → "On"
        data = b"\x00\x00\x00\x01" + b"\x00" * 4
        vals = dbckit.decode_frame(db, 500, data)
        assert vals["IgnitionStatus"] == "On"


class TestMultiplexedDecode:
    # complex.dbc message 200 "BodyStatus" (4 bytes):
    #   MuxSelector M  : bits 0-3   (selector)
    #   LightStatus m0 : bits 4-11  (active when selector == 0)
    #   DoorStatus  m1 : bits 4-11  (active when selector == 1)
    #   WindowStatus m2: bits 4-11  (active when selector == 2)

    def test_decode_returns_selector_signal(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        raw = dbckit.encode_frame(db, 200, {"MuxSelector": 1.0, "DoorStatus": 42.0})
        vals = dbckit.decode_frame(db, 200, raw)
        assert "MuxSelector" in vals
        assert vals["MuxSelector"] == pytest.approx(1.0)

    def test_decode_returns_active_mux_signal(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        raw = dbckit.encode_frame(db, 200, {"MuxSelector": 1.0, "DoorStatus": 42.0})
        vals = dbckit.decode_frame(db, 200, raw)
        assert "DoorStatus" in vals
        assert vals["DoorStatus"] == pytest.approx(42.0)

    def test_decode_excludes_inactive_mux_signals(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        # selector=1: only DoorStatus should appear, not LightStatus or WindowStatus
        raw = dbckit.encode_frame(db, 200, {"MuxSelector": 1.0, "DoorStatus": 10.0})
        vals = dbckit.decode_frame(db, 200, raw)
        assert "LightStatus" not in vals
        assert "WindowStatus" not in vals

    def test_decode_selector_zero(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        raw = dbckit.encode_frame(db, 200, {"MuxSelector": 0.0, "LightStatus": 99.0})
        vals = dbckit.decode_frame(db, 200, raw)
        assert "LightStatus" in vals
        assert vals["LightStatus"] == pytest.approx(99.0)
        assert "DoorStatus" not in vals


class TestMultiplexedEncode:
    def test_encode_explicit_selector(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        raw = dbckit.encode_frame(db, 200, {"MuxSelector": 1.0, "DoorStatus": 0x42})
        vals = dbckit.decode_frame(db, 200, raw)
        assert vals["MuxSelector"] == pytest.approx(1.0)
        assert vals["DoorStatus"] == pytest.approx(0x42)

    def test_encode_infers_selector_from_mx_signal(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        # Provide only the mX signal — M should be auto-encoded
        raw = dbckit.encode_frame(db, 200, {"LightStatus": 0xFF})
        vals = dbckit.decode_frame(db, 200, raw)
        assert vals["MuxSelector"] == pytest.approx(0.0)
        assert vals["LightStatus"] == pytest.approx(0xFF)

    def test_encode_roundtrip_all_variants(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        for selector, signal_name, value in [
            (0.0, "LightStatus", 10.0),
            (1.0, "DoorStatus", 20.0),
            (2.0, "WindowStatus", 30.0),
        ]:
            raw = dbckit.encode_frame(
                db, 200, {"MuxSelector": selector, signal_name: value}
            )
            decoded = dbckit.decode_frame(db, 200, raw)
            assert decoded["MuxSelector"] == pytest.approx(selector)
            assert decoded[signal_name] == pytest.approx(value)

    def test_encode_rejects_wrong_mux_signal(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        # selector=0 (LightStatus active) but DoorStatus (m1) provided
        with pytest.raises(ValueError, match="not active"):
            dbckit.encode_frame(db, 200, {"MuxSelector": 0.0, "DoorStatus": 5.0})

    def test_encode_rejects_contradictory_mx_signals(self):
        db = dbckit.load(FIXTURES / "complex.dbc")
        with pytest.raises(ValueError, match="[Cc]onflicting"):
            dbckit.encode_frame(db, 200, {"LightStatus": 1.0, "DoorStatus": 2.0})
