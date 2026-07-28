"""
Unit tests for backend.discord_rpc.protocol framing and parsing layer.
"""

import struct
import unittest
from backend.discord_rpc.protocol import (
    Opcode,
    ParsedFrame,
    FrameParser,
    encode_frame,
    MAX_PAYLOAD_SIZE,
    ProtocolError,
    MalformedHeaderError,
    UnsupportedOpcodeError,
    OversizedPayloadError,
    InvalidUTF8Error,
    InvalidJSONError,
)


class TestProtocolFraming(unittest.TestCase):

    def test_encode_frame_header_little_endian(self):
        payload = {"v": 1}
        raw = encode_frame(Opcode.HANDSHAKE, payload)
        self.assertGreaterEqual(len(raw), 8)
        
        # Verify first 8 bytes unpack correctly as little-endian uint32
        opcode_val, length_val = struct.unpack("<II", raw[:8])
        self.assertEqual(opcode_val, 0)
        self.assertEqual(length_val, len(raw[8:]))

    def test_valid_frame_round_trip(self):
        payload = {"cmd": "DISPATCH", "data": {"user": "test_user"}}
        encoded = encode_frame(Opcode.FRAME, payload)
        
        parser = FrameParser()
        frames = parser.feed(encoded)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].opcode, Opcode.FRAME)
        self.assertEqual(frames[0].payload, payload)
        self.assertEqual(parser.buffer_size, 0)

    def test_empty_json_object_payload(self):
        payload = {}
        encoded = encode_frame(Opcode.FRAME, payload)
        parser = FrameParser()
        frames = parser.feed(encoded)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].opcode, Opcode.FRAME)
        self.assertEqual(frames[0].payload, {})

    def test_unicode_json_payload(self):
        payload = {"greeting": "Hello, 世界! 🚀 Gamer Deck #1"}
        encoded = encode_frame(Opcode.FRAME, payload)
        parser = FrameParser()
        frames = parser.feed(encoded)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, payload)

    def test_ping_and_pong_frames(self):
        ping_raw = encode_frame(Opcode.PING, None)
        pong_raw = encode_frame(Opcode.PONG, {"nonce": "12345"})

        parser = FrameParser()
        f1 = parser.feed(ping_raw)
        self.assertEqual(len(f1), 1)
        self.assertEqual(f1[0].opcode, Opcode.PING)
        self.assertIsNone(f1[0].payload)

        f2 = parser.feed(pong_raw)
        self.assertEqual(len(f2), 1)
        self.assertEqual(f2[0].opcode, Opcode.PONG)
        self.assertEqual(f2[0].payload, {"nonce": "12345"})

    def test_fragmented_header(self):
        payload = {"test": "fragmented_header"}
        encoded = encode_frame(Opcode.FRAME, payload)
        
        parser = FrameParser()
        # Feed first 3 bytes of header (incomplete header)
        f1 = parser.feed(encoded[:3])
        self.assertEqual(len(f1), 0)
        self.assertEqual(parser.buffer_size, 3)

        # Feed remaining bytes
        f2 = parser.feed(encoded[3:])
        self.assertEqual(len(f2), 1)
        self.assertEqual(f2[0].payload, payload)
        self.assertEqual(parser.buffer_size, 0)

    def test_fragmented_payload(self):
        payload = {"key": "very_long_payload_string_for_testing_fragmentation"}
        encoded = encode_frame(Opcode.FRAME, payload)
        
        parser = FrameParser()
        # Feed header + partial payload (first 12 bytes total)
        f1 = parser.feed(encoded[:12])
        self.assertEqual(len(f1), 0)
        self.assertEqual(parser.buffer_size, 12)

        # Feed rest of payload
        f2 = parser.feed(encoded[12:])
        self.assertEqual(len(f2), 1)
        self.assertEqual(f2[0].payload, payload)
        self.assertEqual(parser.buffer_size, 0)

    def test_one_byte_at_a_time_input(self):
        payload = {"data": [1, 2, 3, 4, 5]}
        encoded = encode_frame(Opcode.FRAME, payload)
        
        parser = FrameParser()
        discovered_frames = []
        for i in range(len(encoded)):
            frames = parser.feed(encoded[i:i+1])
            discovered_frames.extend(frames)

        self.assertEqual(len(discovered_frames), 1)
        self.assertEqual(discovered_frames[0].payload, payload)
        self.assertEqual(parser.buffer_size, 0)

    def test_multiple_frames_in_one_buffer(self):
        f1_bytes = encode_frame(Opcode.HANDSHAKE, {"v": 1, "client_id": "123"})
        f2_bytes = encode_frame(Opcode.FRAME, {"cmd": "PING"})
        f3_bytes = encode_frame(Opcode.CLOSE, {"code": 4000, "message": "Goodbye"})

        combined = f1_bytes + f2_bytes + f3_bytes
        parser = FrameParser()
        frames = parser.feed(combined)

        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[0].opcode, Opcode.HANDSHAKE)
        self.assertEqual(frames[1].opcode, Opcode.FRAME)
        self.assertEqual(frames[2].opcode, Opcode.CLOSE)
        self.assertEqual(parser.buffer_size, 0)

    def test_complete_frames_plus_incomplete_trailing_frame(self):
        f1_bytes = encode_frame(Opcode.FRAME, {"seq": 1})
        f2_bytes = encode_frame(Opcode.FRAME, {"seq": 2})

        # Send full f1 + first 4 bytes of f2 header
        combined = f1_bytes + f2_bytes[:4]
        parser = FrameParser()
        frames = parser.feed(combined)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, {"seq": 1})
        self.assertEqual(parser.buffer_size, 4)

        # Feed rest of f2
        frames2 = parser.feed(f2_bytes[4:])
        self.assertEqual(len(frames2), 1)
        self.assertEqual(frames2[0].payload, {"seq": 2})
        self.assertEqual(parser.buffer_size, 0)

    def test_invalid_opcode(self):
        # Opcode 99 is invalid
        header = struct.pack("<II", 99, 10)
        payload = b'{"a": 1234}'
        bad_frame = header + payload

        parser = FrameParser()
        with self.assertRaises(UnsupportedOpcodeError) as ctx:
            parser.feed(bad_frame)
        self.assertEqual(ctx.exception.opcode, 99)

    def test_encode_invalid_opcode(self):
        with self.assertRaises(UnsupportedOpcodeError):
            encode_frame(99, {"test": True})

    def test_oversized_declared_payload(self):
        # Declare 20 MB payload size (> 16 MB MAX_PAYLOAD_SIZE)
        oversized_len = 20 * 1024 * 1024
        header = struct.pack("<II", int(Opcode.FRAME), oversized_len)
        
        parser = FrameParser()
        with self.assertRaises(OversizedPayloadError) as ctx:
            parser.feed(header)
        self.assertEqual(ctx.exception.length, oversized_len)
        self.assertEqual(ctx.exception.max_limit, MAX_PAYLOAD_SIZE)

    def test_invalid_utf8_payload(self):
        invalid_utf8_bytes = b"\x80\x81\x82\x83"
        header = struct.pack("<II", int(Opcode.FRAME), len(invalid_utf8_bytes))
        bad_frame = header + invalid_utf8_bytes

        parser = FrameParser()
        with self.assertRaises(InvalidUTF8Error):
            parser.feed(bad_frame)

    def test_invalid_json_payload(self):
        invalid_json_bytes = b"{this is not valid json}"
        header = struct.pack("<II", int(Opcode.FRAME), len(invalid_json_bytes))
        bad_frame = header + invalid_json_bytes

        parser = FrameParser()
        with self.assertRaises(InvalidJSONError):
            parser.feed(bad_frame)

    def test_buffer_state_remains_correct_after_parsing(self):
        parser = FrameParser()
        self.assertEqual(parser.buffer_size, 0)

        # Push 3 complete frames sequentially
        for i in range(5):
            frame_bytes = encode_frame(Opcode.FRAME, {"i": i})
            res = parser.feed(frame_bytes)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0].payload, {"i": i})
            self.assertEqual(parser.buffer_size, 0)


if __name__ == "__main__":
    unittest.main()
