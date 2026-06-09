"""maxmsp-mcp — drive Max/MSP patches from an MCP client.

Architecture:

    MCP client (stdio, JSON-RPC)
          v
    maxmsp_mcp.server  --OSC over UDP-->  [udpreceive 7400]  (mcp_host.maxpat)
                                                v
                                          [route /newdefault /connect ...]
                                                v
                                          [prepend script] -> [thispatcher]

Max's [thispatcher] does the dynamic patching. Objects are addressed by stable
scripting names assigned here (obj_0, obj_1, ...).
"""

from __future__ import annotations

import json
import os
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from .guide import GUIDE
from .patch_state import MaxObject, PatchState
from .transport import MaxReturn, MaxTransport

mcp = FastMCP("maxmsp")
state = PatchState()
tx = MaxTransport()
rx: Optional[MaxReturn] = None

_NOT_INIT = (
    "Call max_init first. It returns the orientation guide and unlocks the "
    "other tools. Make sure max/mcp_host.maxpat is open in Max."
)


def _require_init() -> None:
    if not state.initialized:
        raise RuntimeError(_NOT_INIT)


def _newdefault(maxclass: str, args: List[str], x: int, y: int, prefix: str = "obj") -> str:
    """Common path: create [maxclass args...] at (x, y) with a fresh name."""
    name = state.next_name(prefix)
    # OSC: /newdefault name x y maxclass arg1 arg2 ...
    tx.send("/newdefault", name, int(x), int(y), maxclass, *[str(a) for a in args])
    text = " ".join([maxclass, *[str(a) for a in args]]).strip()
    state.register(MaxObject(name=name, maxclass=maxclass, text=text, x=int(x), y=int(y)))
    return name


@mcp.tool()
def max_init() -> str:
    """Mandatory first call. Returns the orientation guide and unlocks the
    other tools. Requires max/mcp_host.maxpat open in Max."""
    state.initialized = True
    return GUIDE


@mcp.tool()
def max_create_object(maxclass: str, args: List[str] = [], x: int = 40, y: int = 40) -> str:
    """Create a Max object box [maxclass args...] at (x, y). Returns its
    scripting name (e.g. obj_3). Example: max_create_object("cycle~", ["440"])."""
    _require_init()
    name = _newdefault(maxclass, args, x, y)
    return f"created {name}: [{state.objects[name].text}]"


@mcp.tool()
def max_create_message(text: str, x: int = 40, y: int = 40) -> str:
    """Create a message box containing `text` at (x, y). Returns its name."""
    _require_init()
    name = state.next_name("msg")
    tx.send("/newdefault", name, int(x), int(y), "message")
    # Reliably set the content: script send <name> set <atoms...>
    tx.send("/setbox", name, "set", *text.split())
    state.register(MaxObject(name=name, maxclass="message", text=text, x=int(x), y=int(y)))
    return f"created {name}: message [{text}]"


@mcp.tool()
def max_create_comment(text: str, x: int = 40, y: int = 40) -> str:
    """Create a text comment at (x, y). Returns its name. Place comments BESIDE
    the object they label, never on top of an object."""
    _require_init()
    name = state.next_name("cmt")
    tx.send("/newdefault", name, int(x), int(y), "comment")
    # A comment's text must be set explicitly, or the box shows up empty.
    tx.send("/setbox", name, "set", *text.split())
    state.register(MaxObject(name=name, maxclass="comment", text=text, x=int(x), y=int(y)))
    return f"created {name}: comment [{text}]"


@mcp.tool()
def max_create_toggle(x: int = 40, y: int = 40) -> str:
    """Create a [toggle] at (x, y). Returns its name."""
    _require_init()
    name = _newdefault("toggle", [], x, y, prefix="tgl")
    return f"created {name}: toggle"


@mcp.tool()
def max_create_bang(x: int = 40, y: int = 40) -> str:
    """Create a [button] (bang) at (x, y). Returns its name."""
    _require_init()
    name = _newdefault("button", [], x, y, prefix="bng")
    return f"created {name}: button"


@mcp.tool()
def max_create_number(x: int = 40, y: int = 40, float_box: bool = False) -> str:
    """Create a number box at (x, y). float_box=True gives a [flonum], else
    an integer [number]. Returns its name."""
    _require_init()
    cls = "flonum" if float_box else "number"
    name = _newdefault(cls, [], x, y, prefix="num")
    return f"created {name}: {cls}"


@mcp.tool()
def max_create_slider(x: int = 40, y: int = 40) -> str:
    """Create a [slider] at (x, y). Returns its name."""
    _require_init()
    name = _newdefault("slider", [], x, y, prefix="sld")
    return f"created {name}: slider"


@mcp.tool()
def max_connect(from_name: str, outlet: int, to_name: str, inlet: int) -> str:
    """Wire from_name:outlet -> to_name:inlet (0-indexed, left to right)."""
    _require_init()
    for n in (from_name, to_name):
        if n not in state.objects:
            raise RuntimeError(f"unknown object '{n}'. Known: {state.names()}")
    tx.send("/connect", from_name, int(outlet), to_name, int(inlet))
    return f"connected {from_name}:{outlet} -> {to_name}:{inlet}"


@mcp.tool()
def max_disconnect(from_name: str, outlet: int, to_name: str, inlet: int) -> str:
    """Remove the connection from_name:outlet -> to_name:inlet."""
    _require_init()
    tx.send("/disconnect", from_name, int(outlet), to_name, int(inlet))
    return f"disconnected {from_name}:{outlet} -> {to_name}:{inlet}"


@mcp.tool()
def max_delete(name: str) -> str:
    """Delete a single object by name."""
    _require_init()
    tx.send("/delete", name)
    state.forget(name)
    return f"deleted {name}"


@mcp.tool()
def max_set_dsp(on: bool) -> str:
    """Start or stop global audio DSP."""
    _require_init()
    tx.send("/dsp", 1 if on else 0)
    return f"dsp {'on' if on else 'off'}"


@mcp.tool()
def max_send(name: str, args: List[str]) -> str:
    """Forward a message (args...) to a [receive <name>] / [r <name>] already
    present in the patch. Used to drive a running patch."""
    _require_init()
    tx.send("/send", name, *[str(a) for a in args])
    return f"sent to [r {name}]: {' '.join(str(a) for a in args)}"


@mcp.tool()
def max_clear_canvas() -> str:
    """Delete every object this server created (one delete per name)."""
    _require_init()
    n = 0
    for name in state.names():
        tx.send("/delete", name)
        n += 1
    state.reset()
    return f"cleared {n} object(s)"


@mcp.tool()
def max_get_state() -> str:
    """List the objects this server has created."""
    _require_init()
    if not state.objects:
        return "no objects yet"
    return "\n".join(
        f"{o.name}: [{o.text}] @ ({o.x},{o.y})" for o in state.objects.values()
    )


def _get_rx() -> MaxReturn:
    global rx
    if rx is None:
        try:
            rx = MaxReturn()
        except OSError as e:
            raise RuntimeError(
                f"Cannot bind the return port for patch read-back ({e}). "
                "Another instance may already be listening, or set MAX_RETURN_PORT."
            )
    return rx


def _dump_raw() -> dict:
    """Ask Max to dump the patch and return the parsed structure."""
    listener = _get_rx()
    listener.flush()
    tx.send("/dump")
    try:
        address, args = listener.wait(2.0)
    except OSError:
        raise RuntimeError(
            "No reply from Max. Check that mcp_host.maxpat is open, that "
            "[v8 dump.js] loaded (dump.js next to the patch), and that "
            "[udpsend 127.0.0.1 7401] is wired to it."
        )
    if address != "/patch" or not args:
        raise RuntimeError(f"Unexpected reply from Max: {address} {args}")
    return json.loads(args[0])


@mcp.tool()
def max_dump_patch() -> str:
    """Read the live patch back from Max: every object (varname, class, text)
    and every connection. This is how you SEE what is actually in the patcher,
    including objects the user added by hand. Machinery is filtered out."""
    _require_init()
    data = _dump_raw()
    objs = data.get("objects", [])
    lines = data.get("lines", [])
    out = [f"{len(objs)} object(s), {len(lines)} connection(s):"]
    for o in objs:
        label = o.get("text") or o.get("maxclass")
        name = o.get("varname") or "(unnamed)"
        out.append(f"  {name}: [{label}]")
    if lines:
        out.append("connections:")
        for ln in lines:
            s = ln.get("src") or "(unnamed)"
            d = ln.get("dst") or "(unnamed)"
            out.append(f"  {s}:{ln.get('outlet')} -> {d}:{ln.get('inlet')}")
    return "\n".join(out)


@mcp.tool()
def max_verify() -> str:
    """Close the loop: dump the patch and compare it to what this server
    believes it created. Reports objects that are missing (creation may have
    failed) so you can rebuild them."""
    _require_init()
    data = _dump_raw()
    present = {o["varname"] for o in data.get("objects", []) if o.get("varname")}
    expected = set(state.names())
    missing = sorted(expected - present)
    also_present = sorted(present - expected)
    out = [f"expected {len(expected)} object(s) created by the server."]
    if missing:
        out.append("MISSING (not found in patch, recreate these): " + ", ".join(missing))
    else:
        out.append("all server-created objects are present.")
    if also_present:
        out.append("other named objects in the patch (hand-added): " + ", ".join(also_present))
    return "\n".join(out)


_OBJ_DB = None
_OBJ_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "objects.json")


def _obj_db() -> dict:
    global _OBJ_DB
    if _OBJ_DB is None:
        try:
            with open(_OBJ_DB_PATH, "r", encoding="utf-8") as f:
                _OBJ_DB = json.load(f)
        except OSError:
            _OBJ_DB = {}
    return _OBJ_DB


def _format_doc(o: dict) -> str:
    lines = [f"{o['name']} - {o.get('digest', '')}".rstrip(" -")]
    if o.get("module") or o.get("category"):
        lines.append(f"  module: {o.get('module', '?')}  category: {o.get('category', '?')}")

    def block(title, items, show_optional=False):
        if not items:
            return
        lines.append(title + ":")
        for i, it in enumerate(items):
            label = it.get("name") or str(i)
            opt = " (optional)" if show_optional and it.get("optional") else ""
            d = (" - " + it["digest"]) if it.get("digest") else ""
            t = f" [{it['type']}]" if it.get("type") else ""
            lines.append(f"  {i}: {label}{t}{opt}{d}")

    block("args", o.get("args"), show_optional=True)
    block("inlets", o.get("inlets"))
    block("outlets", o.get("outlets"))
    block("attributes", o.get("attributes"))
    block("messages", o.get("messages"))
    return "\n".join(lines)


@mcp.tool()
def max_doc(name: str) -> str:
    """Look up the official reference for a Max object: its arguments, inlets,
    outlets, attributes and messages. Call this whenever you are unsure of an
    object's signature (inlet/outlet order, argument types, attribute names)
    instead of guessing."""
    import difflib

    db = _obj_db()
    if not db:
        return ("No object database loaded. Build it with "
                "tools/build_maxref_db.py to enable signature lookups.")
    o = db.get(name)
    if o:
        return _format_doc(o)
    close = difflib.get_close_matches(name, list(db.keys()), n=6, cutoff=0.5)
    hint = f" Closest matches: {', '.join(close)}." if close else ""
    return f"'{name}' is not in the reference database.{hint}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
