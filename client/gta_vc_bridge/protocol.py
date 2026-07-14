"""The frozen mod-to-client protocol: framing plus message schema.

This module is the single source of truth for the boundary between the Python
bridge client and the C++ ASI mod. Both sides encode and decode with it. It has
no Archipelago dependency, so it and the bridge that uses it test headless.

Roles
-----
The client HOSTS a localhost TCP listener. The ASI connects to it with
retry and backoff. The client is the server; the ASI is the client of that
socket.

Framing
-------
Newline-delimited JSON, one message per line, UTF-8. json.dumps never emits a
raw newline (it escapes them inside strings), so a compact JSON object is
always a single safe line; the encoder guards this. A message whose line would
exceed MAX_FRAME_BYTES is split into chunk frames so no single line can
overflow the mod's read buffer and swallow the next message. Each chunk frame
is itself a small JSON line carrying a base64 slice of the original payload;
the reader reassembles them. Every frame, chunked or not, ends in exactly one
newline.

Seed handshake
--------------
On connect the ASI sends HELLO with the seed hash it has stamped into its
reserved SCM global, or an empty string on a game that has not started one. The
client replies WELCOME carrying the expected hash (the ASI stamps it on a new
game and presents it forever after), or REFUSED when a non-empty presented hash
does not match: that is a save from a different multiworld, and mixing them
would corrupt progress.

Message types
-------------
Client to ASI:
    welcome  {seed_hash}      accept; carries the expected seed hash to stamp
    refused  {reason}         reject this connection, with a player-facing reason
    config   {item_globals,   how the ASI maps play to the SCM: item id -> the
              completion_watch} unlock global it counts toward, and completion
                              global index -> location id to poll and report.
                              Sent once per connection, before the resync.
    items    {items}          the full cumulative received-items list, as
                              [index, item_id] pairs. The ASI re-derives all
                              unlock globals from this every time and re-applies
                              one-shot grants only past its saved applied-index.
    checked  {locations}      AP location ids already checked (resync), so the
                              ASI does not re-send them
    toast    {text}           a player-facing message for the in-game toast queue

ASI to client:
    hello        {seed_hash}  first frame after connect
    check        {location}   a location was completed in game
    goal_reached {}           the goal completion signal
    applied      {index}      an item index was durably applied (for logging)
"""

from __future__ import annotations

import base64
import hashlib
import json

PROTOCOL_VERSION = 1

# A single frame, including its trailing newline, never exceeds this many bytes.
MAX_FRAME_BYTES = 4096
# Reassembly and buffer guards, so a malformed or hostile peer cannot exhaust
# memory.
MAX_PENDING_BUFFER_BYTES = 1 << 20
MAX_CHUNKS_IN_FLIGHT = 64
# The most chunks one message may split into. Bounds parts accumulated under a
# single chunk id, so a peer cannot grow one reassembly buffer without limit.
MAX_CHUNK_PARTS = 4096

# Message type values.
WELCOME = "welcome"
REFUSED = "refused"
CONFIG = "config"
ITEMS = "items"
CHECKED = "checked"
TOAST = "toast"
HELLO = "hello"
CHECK = "check"
GOAL_REACHED = "goal_reached"
APPLIED = "applied"

# The chunk-envelope key. Distinct from the "type" key of a logical message so
# the two never collide.
_CHUNK = "chunk"


class ProtocolError(Exception):
    """A frame or message that violates the protocol."""


def seed_hash(seed_name: str, slot_name: str) -> str:
    """The seed identity both sides compare. A short hex digest of the
    multiworld seed and this slot, stable across a session."""
    digest = hashlib.sha256(f"{seed_name}\x1f{slot_name}".encode())
    return digest.hexdigest()[:16]


def welcome_message(expected_seed_hash: str) -> dict:
    return {"type": WELCOME, "protocol_version": PROTOCOL_VERSION,
            "seed_hash": expected_seed_hash}


def refused_message(reason: str) -> dict:
    return {"type": REFUSED, "protocol_version": PROTOCOL_VERSION, "reason": reason}


def config_message(item_globals: dict, completion_watch: dict) -> dict:
    return {"type": CONFIG, "item_globals": item_globals, "completion_watch": completion_watch}


def items_message(items: list[tuple[int, int]]) -> dict:
    return {"type": ITEMS, "items": [[index, item_id] for index, item_id in items]}


def checked_message(locations: list[int]) -> dict:
    return {"type": CHECKED, "locations": list(locations)}


def toast_message(text: str) -> dict:
    return {"type": TOAST, "text": text}


def hello_message(presented_seed_hash: str) -> dict:
    return {"type": HELLO, "protocol_version": PROTOCOL_VERSION,
            "seed_hash": presented_seed_hash}


def check_message(location: int) -> dict:
    return {"type": CHECK, "location": location}


def goal_reached_message() -> dict:
    return {"type": GOAL_REACHED}


class MessageWriter:
    """Turns a message dict into one or more newline-terminated frames,
    chunking anything too large for a single frame."""

    def __init__(self) -> None:
        self._next_chunk_id = 0

    def frames(self, message: dict) -> list[bytes]:
        payload = json.dumps(message, separators=(",", ":"))
        if "\n" in payload:
            raise ProtocolError("a serialized message must not contain a newline")
        raw = payload.encode("utf-8")
        if len(raw) + 1 <= MAX_FRAME_BYTES:
            return [raw + b"\n"]
        return self._chunk_frames(raw)

    def _chunk_frames(self, raw: bytes) -> list[bytes]:
        encoded = base64.b64encode(raw).decode("ascii")
        chunk_id = self._next_chunk_id
        self._next_chunk_id += 1
        # Leave generous headroom for the envelope keys around the base64 slice.
        slice_size = MAX_FRAME_BYTES - 256
        pieces = [encoded[start:start + slice_size]
                  for start in range(0, len(encoded), slice_size)]
        frames: list[bytes] = []
        for sequence, piece in enumerate(pieces):
            envelope = {_CHUNK: chunk_id, "seq": sequence, "of": len(pieces), "data": piece}
            frames.append(json.dumps(envelope, separators=(",", ":")).encode("utf-8") + b"\n")
        return frames


class MessageReader:
    """Feeds received bytes and yields complete message dicts, reassembling
    chunked frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._chunks: dict[int, dict] = {}

    def feed(self, data: bytes) -> list[dict]:
        self._buffer.extend(data)
        if len(self._buffer) > MAX_PENDING_BUFFER_BYTES:
            raise ProtocolError("inbound buffer exceeded the frame size limit")
        messages: list[dict] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._buffer[:newline])
            del self._buffer[:newline + 1]
            if not line.strip():
                continue
            message = self._decode_line(line)
            if message is not None:
                messages.append(message)
        return messages

    def _decode_line(self, line: bytes) -> dict | None:
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError) as error:
            raise ProtocolError(f"invalid frame: {error}") from error
        if not isinstance(obj, dict):
            raise ProtocolError("a frame must be a JSON object")
        if _CHUNK in obj:
            return self._accept_chunk(obj)
        return obj

    def _accept_chunk(self, envelope: dict) -> dict | None:
        try:
            chunk_id = envelope[_CHUNK]
            total = envelope["of"]
            sequence = envelope["seq"]
            data = envelope["data"]
        except KeyError as error:
            raise ProtocolError(f"malformed chunk envelope: missing {error}") from error
        if not isinstance(total, int) or not 1 <= total <= MAX_CHUNK_PARTS:
            raise ProtocolError("invalid chunk count")
        if not isinstance(sequence, int) or not 0 <= sequence < total:
            raise ProtocolError("invalid chunk sequence")
        entry = self._chunks.setdefault(chunk_id, {"of": total, "parts": {}})
        if entry["of"] != total:
            raise ProtocolError("inconsistent chunk count across a message")
        entry["parts"][sequence] = data
        if len(self._chunks) > MAX_CHUNKS_IN_FLIGHT:
            raise ProtocolError("too many chunked messages in flight")
        if len(entry["parts"]) < total:
            return None
        # Sequences were each validated in range, so a full count means every
        # index is present with no gaps.
        del self._chunks[chunk_id]
        try:
            encoded = "".join(entry["parts"][index] for index in range(total))
            raw = base64.b64decode(encoded)
            return json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as error:
            raise ProtocolError(f"invalid reassembled message: {error}") from error
