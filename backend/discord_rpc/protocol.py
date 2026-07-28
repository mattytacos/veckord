"""
Discord IPC Binary Protocol Framing and Parsing Module.

Implements binary framing (8-byte little-endian header: opcode + payload length)
and strict UTF-8 / JSON payload parsing for Discord RPC over Unix domain sockets.
"""

import json
import struct
from enum import IntEnum
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union


class Opcode(IntEnum):
    HANDSHAKE = 0
    FRAME = 1
    CLOSE = 2
    PING = 3
    PONG = 4

    @classmethod
    def is_valid(cls, value: int) -> bool:
        return value in cls._value2member_map_


HEADER_STRUCT = struct.Struct("<II")  # Opcode (uint32 LE), Payload Length (uint32 LE)
HEADER_SIZE = HEADER_STRUCT.size  # 8 bytes

# 16 MB maximum payload size ceiling to prevent memory exhaustion attacks
MAX_PAYLOAD_SIZE = 16 * 1024 * 1024


class ProtocolError(Exception):
    """Base exception for Discord RPC framing and parsing errors."""
    pass


class MalformedHeaderError(ProtocolError):
    """Raised when header bytes cannot be unpacked or header structure is invalid."""
    pass


class UnsupportedOpcodeError(ProtocolError):
    """Raised when an unknown or invalid opcode integer is received."""
    def __init__(self, opcode: int):
        super().__init__(f"Unsupported or unknown Discord RPC opcode: {opcode}")
        self.opcode = opcode


class OversizedPayloadError(ProtocolError):
    """Raised when declared payload length exceeds MAX_PAYLOAD_SIZE."""
    def __init__(self, length: int, max_limit: int = MAX_PAYLOAD_SIZE):
        super().__init__(f"Declared payload size {length} bytes exceeds limit of {max_limit} bytes")
        self.length = length
        self.max_limit = max_limit


class InvalidUTF8Error(ProtocolError):
    """Raised when payload bytes cannot be decoded as UTF-8."""
    pass


class InvalidJSONError(ProtocolError):
    """Raised when payload string cannot be parsed as valid JSON."""
    pass


@dataclass
class ParsedFrame:
    opcode: Opcode
    payload: Any  # Decoded JSON data (dict, list, str, int, bool, None)

    def __repr__(self) -> str:
        return f"ParsedFrame(opcode={self.opcode.name}, payload={self.payload!r})"


def encode_frame(opcode: Union[Opcode, int], payload: Any = None) -> bytes:
    """
    Encode an opcode and JSON-compatible payload into a Discord RPC binary frame.

    Header: 4-byte uint32 LE opcode + 4-byte uint32 LE payload length
    Payload: UTF-8 encoded JSON string
    """
    if isinstance(opcode, int) and not isinstance(opcode, Opcode):
        if not Opcode.is_valid(opcode):
            raise UnsupportedOpcodeError(opcode)
        opcode = Opcode(opcode)

    if payload is None:
        payload_bytes = b""
    elif isinstance(payload, bytes):
        payload_bytes = payload
    else:
        try:
            payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            payload_bytes = payload_str.encode("utf-8")
        except (TypeError, ValueError) as e:
            raise InvalidJSONError(f"Failed to serialize payload to JSON: {e}") from e

    length = len(payload_bytes)
    if length > MAX_PAYLOAD_SIZE:
        raise OversizedPayloadError(length, MAX_PAYLOAD_SIZE)

    header = HEADER_STRUCT.pack(int(opcode), length)
    return header + payload_bytes


class FrameParser:
    """
    Stream parser for Discord IPC binary frames.
    
    Buffers incoming bytes, extracts complete frames, handles partial/fragmented reads,
    and defends against oversized or malformed inputs.
    """

    def __init__(self, max_payload_size: int = MAX_PAYLOAD_SIZE):
        self._buffer = bytearray()
        self.max_payload_size = max_payload_size

    @property
    def buffer_size(self) -> int:
        """Return the current unparsed buffer size in bytes."""
        return len(self._buffer)

    def feed(self, chunk: bytes) -> List[ParsedFrame]:
        """
        Append incoming socket bytes to internal buffer and return all complete frames.
        """
        if chunk:
            self._buffer.extend(chunk)
        return self.pop_all_frames()

    def pop_frame(self) -> Optional[ParsedFrame]:
        """
        Attempt to extract a single complete ParsedFrame from the buffer.
        
        Returns None if buffer has insufficient bytes for a complete frame.
        Raises ProtocolError subclasses on malformed headers, opcodes, or payloads.
        """
        if len(self._buffer) < HEADER_SIZE:
            return None

        # Peek at header without consuming buffer yet
        opcode_raw, length = HEADER_STRUCT.unpack(self._buffer[:HEADER_SIZE])

        if not Opcode.is_valid(opcode_raw):
            # Consume header to prevent infinite loops on error
            del self._buffer[:HEADER_SIZE]
            raise UnsupportedOpcodeError(opcode_raw)

        if length > self.max_payload_size:
            del self._buffer[:HEADER_SIZE]
            raise OversizedPayloadError(length, self.max_payload_size)

        total_frame_length = HEADER_SIZE + length
        if len(self._buffer) < total_frame_length:
            # Payload incomplete - wait for more data
            return None

        # Consume full frame bytes from buffer
        frame_bytes = bytes(self._buffer[HEADER_SIZE:total_frame_length])
        del self._buffer[:total_frame_length]

        opcode = Opcode(opcode_raw)

        if not frame_bytes:
            # Empty payload (e.g. PING / PONG / empty HANDSHAKE)
            return ParsedFrame(opcode=opcode, payload=None)

        try:
            payload_str = frame_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as e:
            raise InvalidUTF8Error(f"Payload contains invalid UTF-8: {e}") from e

        try:
            payload_json = json.loads(payload_str)
        except json.JSONDecodeError as e:
            raise InvalidJSONError(f"Payload is not valid JSON: {e}") from e

        return ParsedFrame(opcode=opcode, payload=payload_json)

    def pop_all_frames(self) -> List[ParsedFrame]:
        """
        Extract all currently available complete frames from internal buffer.
        """
        frames: List[ParsedFrame] = []
        while True:
            frame = self.pop_frame()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def clear(self) -> None:
        """Clear internal buffer."""
        self._buffer.clear()
