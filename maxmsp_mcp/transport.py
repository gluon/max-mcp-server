"""OSC-over-UDP transport to a vanilla [udpreceive] in Max.

No third-party dependency: a tiny, correct OSC 1.0 encoder (4-byte aligned,
type tags s/i/f). Max's [udpreceive] parses incoming OSC and outputs the
address as the leading symbol followed by the arguments, which we then
[route] to [thispatcher] in the host patch.
"""

from __future__ import annotations

import os
import socket
import struct
from typing import Sequence, Union

Atom = Union[str, int, float]

MAX_HOST = os.environ.get("MAX_HOST", "127.0.0.1")
MAX_PORT = int(os.environ.get("MAX_PORT", "7400"))
RETURN_PORT = int(os.environ.get("MAX_RETURN_PORT", "7401"))


def _pad(b: bytes) -> bytes:
    """OSC strings/blobs are null-terminated and padded to 4 bytes."""
    return b + b"\x00" * (4 - (len(b) % 4) if len(b) % 4 else 4)


def encode_osc(address: str, args: Sequence[Atom]) -> bytes:
    """Encode a single OSC message. Supports string, int (i), float (f)."""
    if not address.startswith("/"):
        address = "/" + address
    out = _pad(address.encode("utf-8"))
    tags = ","
    payload = b""
    for a in args:
        if isinstance(a, bool):
            # treat as int 0/1
            tags += "i"
            payload += struct.pack(">i", 1 if a else 0)
        elif isinstance(a, int):
            tags += "i"
            payload += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            payload += struct.pack(">f", a)
        else:
            tags += "s"
            payload += _pad(str(a).encode("utf-8"))
    out += _pad(tags.encode("utf-8"))
    out += payload
    return out


class MaxTransport:
    """Fire-and-forget UDP sender. Max [udpreceive] is the listener."""

    def __init__(self, host: str = MAX_HOST, port: int = MAX_PORT) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address: str, *args: Atom) -> None:
        self._sock.sendto(encode_osc(address, args), (self.host, self.port))

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _read_osc_string(data: bytes, i: int):
    """Read a null-terminated, 4-byte-padded OSC string starting at i.
    Returns (string, next_index)."""
    end = data.index(b"\x00", i)
    s = data[i:end].decode("utf-8", "replace")
    total = (end - i) + 1  # content + null
    pad = (4 - (total % 4)) % 4
    return s, i + total + pad


def decode_osc(data: bytes):
    """Decode one OSC message. Returns (address, [args]). Handles s/i/f."""
    address, i = _read_osc_string(data, 0)
    if i >= len(data) or data[i : i + 1] != b",":
        return address, []
    tags, i = _read_osc_string(data, i)
    args: list = []
    for t in tags[1:]:
        if t == "s":
            s, i = _read_osc_string(data, i)
            args.append(s)
        elif t == "i":
            args.append(struct.unpack(">i", data[i : i + 4])[0])
            i += 4
        elif t == "f":
            args.append(struct.unpack(">f", data[i : i + 4])[0])
            i += 4
        else:
            break
    return address, args


class MaxReturn:
    """Listens for OSC replies from Max (the [udpsend] in the host patch).

    Lazy-bound: a busy port raises an actionable error from the calling tool
    instead of crashing the whole server at import time.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = RETURN_PORT) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))

    def flush(self) -> None:
        """Drop any stale datagrams so we read a fresh reply."""
        self._sock.setblocking(False)
        try:
            while True:
                self._sock.recvfrom(65535)
        except (BlockingIOError, OSError):
            pass
        finally:
            self._sock.setblocking(True)

    def wait(self, timeout: float = 2.0):
        """Block for one reply. Returns (address, [args]). Raises on timeout."""
        self._sock.settimeout(timeout)
        data, _ = self._sock.recvfrom(65535)
        return decode_osc(data)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass
