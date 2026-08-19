"""Framing tests: round-trip, chunking, the newline guard, and malformed input."""

from __future__ import annotations

import json
import unittest

from .. import protocol


def _round_trip(message: dict) -> list[dict]:
    writer = protocol.MessageWriter()
    reader = protocol.MessageReader()
    received: list[dict] = []
    for frame in writer.frames(message):
        received.extend(reader.feed(frame))
    return received


class TestFraming(unittest.TestCase):
    def test_small_message_is_one_frame(self) -> None:
        message = protocol.check_message(542000000)
        frames = protocol.MessageWriter().frames(message)
        self.assertEqual(len(frames), 1)
        self.assertTrue(frames[0].endswith(b"\n"))
        self.assertEqual(_round_trip(message), [message])

    def test_every_frame_ends_in_exactly_one_newline(self) -> None:
        big = protocol.items_message([(index, index + 1) for index in range(5000)])
        for frame in protocol.MessageWriter().frames(big):
            self.assertTrue(frame.endswith(b"\n"))
            self.assertEqual(frame.count(b"\n"), 1)
            self.assertLessEqual(len(frame), protocol.MAX_FRAME_BYTES)

    def test_config_message_round_trip(self) -> None:
        message = protocol.config_message(
            {"542100000": 9010}, {"9035": 542000000, "9036": 542000001},
            {"542100050": ["cash", 5000], "542100051": ["weapon"]},
            {"9377": 1, "9378": 0},
            {"9075": [479.6, -1718.5, 15.6], "9076": [708.4, -498.2, 12.3]},
            [[393.9, -60.2, 11.5, 15, 366, 0], [-228.4, -1318.2, 9.1, 15, 274, 34]],
            [{"global": 9032, "label": "Prawn Island Bridge",
              "needs_global": 0, "needs_label": ""},
             {"global": 9035, "label": "Starfish Island Causeway",
              "needs_global": 9031, "needs_label": "Starfish Island Access"}],
        )
        self.assertEqual(_round_trip(message), [message])

    def test_large_message_chunks_and_reassembles(self) -> None:
        big = protocol.items_message([(index, index * 7) for index in range(5000)])
        frames = protocol.MessageWriter().frames(big)
        self.assertGreater(len(frames), 1)
        self.assertEqual(_round_trip(big), [big])

    def test_reader_handles_split_and_merged_frames(self) -> None:
        writer = protocol.MessageWriter()
        blob = b"".join(
            frame for location in range(3)
            for frame in writer.frames(protocol.check_message(location))
        )
        reader = protocol.MessageReader()
        received: list[dict] = []
        # Feed one byte at a time to prove the reader reassembles across reads.
        for index in range(len(blob)):
            received.extend(reader.feed(blob[index:index + 1]))
        self.assertEqual([message["location"] for message in received], [0, 1, 2])

    def test_malformed_frame_raises(self) -> None:
        reader = protocol.MessageReader()
        with self.assertRaises(protocol.ProtocolError):
            reader.feed(b"this is not json\n")

    def test_non_object_frame_raises(self) -> None:
        reader = protocol.MessageReader()
        with self.assertRaises(protocol.ProtocolError):
            reader.feed(json.dumps([1, 2, 3]).encode("utf-8") + b"\n")

    def test_malformed_chunk_envelope_raises(self) -> None:
        reader = protocol.MessageReader()
        bad = json.dumps({"chunk": 0, "seq": 0}).encode("utf-8") + b"\n"  # missing "of"/"data"
        with self.assertRaises(protocol.ProtocolError):
            reader.feed(bad)

    def test_out_of_range_chunk_sequence_raises(self) -> None:
        reader = protocol.MessageReader()
        bad = json.dumps({"chunk": 0, "seq": 5, "of": 2, "data": "AA"}).encode("utf-8") + b"\n"
        with self.assertRaises(protocol.ProtocolError):
            reader.feed(bad)

    def test_seed_hash_is_stable_and_slot_specific(self) -> None:
        self.assertEqual(protocol.seed_hash("SEED", "Player1"), protocol.seed_hash("SEED", "Player1"))
        self.assertNotEqual(protocol.seed_hash("SEED", "Player1"), protocol.seed_hash("SEED", "Player2"))
        self.assertNotEqual(protocol.seed_hash("A", "Player1"), protocol.seed_hash("B", "Player1"))


if __name__ == "__main__":
    unittest.main()
