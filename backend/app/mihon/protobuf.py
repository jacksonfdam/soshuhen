"""The protobuf wire format, as much of it as a Mihon backup uses.

A dependency on `protobuf` would want a compiled schema, and the schema lives in
Kotlin annotations (kotlinx.serialization's @ProtoNumber) rather than in a
.proto file. Four wire types and a varint are all a backup needs.
"""

import struct
from collections.abc import Iterator

VARINT = 0
FIXED64 = 1
BYTES = 2
FIXED32 = 5

Field = tuple[int, int, int | bytes]


def _varint(data: bytes, at: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if at >= len(data):
            raise ValueError("truncated varint")
        byte = data[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > 63:
            raise ValueError("varint longer than 64 bits")


def fields(data: bytes) -> Iterator[Field]:
    """Each (number, wire type, value) in a message, in the order written."""
    at = 0
    while at < len(data):
        key, at = _varint(data, at)
        number, wire = key >> 3, key & 7
        if wire == VARINT:
            value, at = _varint(data, at)
            yield number, wire, value
        elif wire == BYTES:
            length, at = _varint(data, at)
            if at + length > len(data):
                raise ValueError("truncated field")
            yield number, wire, data[at : at + length]
            at += length
        elif wire == FIXED32:
            yield number, wire, data[at : at + 4]
            at += 4
        elif wire == FIXED64:
            yield number, wire, data[at : at + 8]
            at += 8
        else:
            raise ValueError(f"unsupported wire type {wire}")


def signed64(value: int) -> int:
    """A varint read back as the int64 Kotlin wrote. Negative numbers take ten bytes."""
    return value - (1 << 64) if value >= 1 << 63 else value


def float32(raw: bytes) -> float:
    return struct.unpack("<f", raw)[0]


def packed_varints(raw: bytes) -> list[int]:
    """A packed repeated varint field. kotlinx writes them unpacked; protoc packs them."""
    values, at = [], 0
    while at < len(raw):
        value, at = _varint(raw, at)
        values.append(value)
    return values


def _encode_varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def varint(number: int, value: int | bool) -> bytes:
    return _encode_varint(number << 3 | VARINT) + _encode_varint(int(value))


def string(number: int, value: str | bytes) -> bytes:
    raw = value.encode() if isinstance(value, str) else value
    return _encode_varint(number << 3 | BYTES) + _encode_varint(len(raw)) + raw


def float_(number: int, value: float) -> bytes:
    return _encode_varint(number << 3 | FIXED32) + struct.pack("<f", value)
