"""Round-trip tests that run WITHOUT Max, using a mock UDP listener and a
fake transport.
"""

import socket
import struct

from maxmsp_mcp import server
from maxmsp_mcp.transport import encode_osc


# ---- OSC wire format -------------------------------------------------------

def _decode_address(packet: bytes) -> str:
    end = packet.index(b"\x00")
    return packet[:end].decode()


def test_osc_alignment_and_address():
    pkt = encode_osc("/connect", ["obj_0", 0, "obj_1", 1])
    assert len(pkt) % 4 == 0
    assert _decode_address(pkt) == "/connect"
    assert b",sisi" in pkt


def test_osc_adds_leading_slash():
    pkt = encode_osc("connect", ["a", 0, "b", 0])
    assert _decode_address(pkt) == "/connect"


def test_osc_reaches_a_real_udp_socket():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    port = rx.getsockname()[1]
    from maxmsp_mcp.transport import MaxTransport
    tx = MaxTransport("127.0.0.1", port)
    tx.send("/newdefault", "obj_0", 40, 40, "cycle~", "440")
    rx.settimeout(1.0)
    data, _ = rx.recvfrom(4096)
    assert _decode_address(data) == "/newdefault"
    rx.close()
    tx.close()


# ---- Server logic (fake transport) ----------------------------------------

class FakeTx:
    def __init__(self):
        self.calls = []

    def send(self, address, *args):
        self.calls.append((address, list(args)))

    def close(self):
        pass


def _fresh(monkeypatch=None):
    fake = FakeTx()
    server.tx = fake
    server.state.reset()
    server.state.initialized = False
    return fake


def test_init_gate_blocks_until_init():
    _fresh()
    try:
        server.max_create_object("cycle~", ["440"])
        assert False, "should have refused before init"
    except RuntimeError as e:
        assert "max_init" in str(e)


def test_create_assigns_stable_names():
    fake = _fresh()
    server.max_init()
    r0 = server.max_create_object("cycle~", ["440"])
    r1 = server.max_create_object("dac~", [])
    assert "obj_0" in r0 and "obj_1" in r1
    assert fake.calls[0] == ("/newdefault", ["obj_0", 40, 40, "cycle~", "440"])


def test_connect_validates_names():
    _fresh()
    server.max_init()
    server.max_create_object("cycle~", ["440"])
    try:
        server.max_connect("obj_0", 0, "ghost", 0)
        assert False
    except RuntimeError as e:
        assert "ghost" in str(e)


def test_create_message_sets_content():
    fake = _fresh()
    server.max_init()
    server.max_create_message("set 1 2 3", 40, 40)
    addrs = [c[0] for c in fake.calls]
    assert "/newdefault" in addrs and "/setbox" in addrs
    setbox = [c for c in fake.calls if c[0] == "/setbox"][0]
    # args: name, "set", "set", "1", "2", "3"  (content words after the leading 'set')
    assert setbox[1][1] == "set"
    assert setbox[1][2:] == ["set", "1", "2", "3"]


def test_clear_deletes_each_name():
    fake = _fresh()
    server.max_init()
    server.max_create_object("cycle~", ["440"])
    server.max_create_object("dac~", [])
    fake.calls.clear()
    out = server.max_clear_canvas()
    deletes = [c for c in fake.calls if c[0] == "/delete"]
    assert len(deletes) == 2
    assert "2" in out
    assert server.state.objects == {}


# ---- OSC decode + read-back ------------------------------------------------

def test_osc_decode_roundtrip():
    from maxmsp_mcp.transport import decode_osc
    addr, args = decode_osc(encode_osc("/patch", ["hello world", 7, 1.5]))
    assert addr == "/patch"
    assert args[0] == "hello world"
    assert args[1] == 7
    assert abs(args[2] - 1.5) < 1e-6


def test_osc_decode_long_string():
    from maxmsp_mcp.transport import decode_osc
    big = '{"objects":[{"varname":"obj_0","maxclass":"newobj","text":"cycle~ 440"}]}'
    addr, args = decode_osc(encode_osc("/patch", [big]))
    assert addr == "/patch"
    import json
    assert json.loads(args[0])["objects"][0]["text"] == "cycle~ 440"


class FakeRx:
    def __init__(self, payload):
        self.payload = payload
    def flush(self):
        pass
    def wait(self, timeout=2.0):
        import json
        return "/patch", [json.dumps(self.payload)]


def test_dump_patch_summarizes():
    _fresh()
    server.max_init()
    payload = {
        "objects": [
            {"varname": "obj_0", "maxclass": "newobj", "text": "cycle~ 440"},
            {"varname": "", "maxclass": "newobj", "text": "buffer~ micbuf 5000"},
        ],
        "lines": [{"src": "obj_0", "outlet": 0, "dst": "obj_1", "inlet": 0}],
    }
    server.rx = FakeRx(payload)
    out = server.max_dump_patch()
    assert "cycle~ 440" in out
    assert "buffer~ micbuf 5000" in out
    assert "obj_0:0 -> obj_1:0" in out


def test_verify_reports_missing():
    _fresh()
    server.max_init()
    server.max_create_object("cycle~", ["440"])   # obj_0
    server.max_create_object("dac~", [])           # obj_1
    # patch only has obj_0; obj_1 went missing
    server.rx = FakeRx({"objects": [{"varname": "obj_0", "maxclass": "newobj", "text": "cycle~ 440"}], "lines": []})
    out = server.max_verify()
    assert "MISSING" in out and "obj_1" in out
