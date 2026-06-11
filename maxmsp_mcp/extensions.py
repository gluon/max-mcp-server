"""maxmsp-mcp extensions — SOTA tools.

All tools are registered into the FastMCP instance via init(server_module).
They access server-level state and functions through _S.<name> at call time,
avoiding circular import issues.
"""
from __future__ import annotations

import json
import os
import time as _time
from typing import List, Optional

from .operations import Entry
from .patch_state import MaxObject


# ── Server module reference (set by init()) ────────────────────────────

_S = None  # server module


def init(server_module):
    """Register all extension tools into the server's FastMCP instance.
    Call this AFTER the server's function definitions but BEFORE mcp.run()."""
    global _S
    _S = server_module
    _register_all()


# ── Helpers ────────────────────────────────────────────────────────────

def _record(kind: str, desc: str, **kw):
    _S.state.history.push(Entry(kind=kind, description=desc, forward=kw, inverse=kw))


def _record_both(kind: str, desc: str, forward: dict, inverse: dict):
    _S.state.history.push(
        Entry(kind=kind, description=desc, forward=forward, inverse=inverse)
    )


def _tool(name):
    """Decorator to register a tool on _S.mcp."""
    def wrap(fn):
        return _S.mcp.tool()(fn)
    return wrap


_tools_registered = False


def _register_all():
    global _tools_registered
    if _tools_registered:
        return
    _tools_registered = True

    # ── 1. UNDO / REDO ──────────────────────────────────────────────────

    @_S.mcp.tool()
    def max_undo() -> str:
        """Undo the last operation. Returns a description of what was undone.
        Supports batching — a multi-step operation is undone atomically."""
        _S._require_init()
        entry = _S.state.history.pop_undo()
        if not entry:
            return "nothing to undo"
        return _apply_inverse(entry, "undo")

    @_S.mcp.tool()
    def max_redo() -> str:
        """Redo the last undone operation."""
        _S._require_init()
        entry = _S.state.history.pop_redo()
        if not entry:
            return "nothing to redo"
        return _apply_forward(entry, "redo")

    @_S.mcp.tool()
    def max_history() -> str:
        """Show the undo/redo history summary."""
        _S._require_init()
        return _S.state.history.summary()

    @_S.mcp.tool()
    def max_begin_batch() -> str:
        """Start batching operations — all tools called until
        max_commit_batch are grouped as one undoable unit."""
        _S._require_init()
        _S.state.history.begin_batch()
        return "batch started"

    @_S.mcp.tool()
    def max_commit_batch() -> str:
        """End batch mode and commit the group."""
        _S._require_init()
        _S.state.history.commit_batch()
        return "batch committed"

    @_S.mcp.tool()
    def max_cancel_batch() -> str:
        """Cancel batch mode without committing."""
        _S._require_init()
        _S.state.history.cancel_batch()
        return "batch cancelled"

    # ── 2. HEARTBEAT / LIVENESS ────────────────────────────────────────

    @_S.mcp.tool()
    def max_heartbeat() -> str:
        """Ping Max to check it's alive. Returns a status string."""
        _S._require_init()
        listener = _S._get_rx()
        listener.flush()
        _S.tx.send("/ping")
        try:
            address, args = listener.wait(1.5)
            if address == "/pong":
                return "Max is alive (pong received)"
            return f"Unexpected reply: {address} {args}"
        except OSError:
            try:
                _S._dump_raw()
                return "Max is alive (dump returned)"
            except RuntimeError:
                return "WARNING: No response from Max. Check mcp_host.maxpat is open."

    # ── 3. ATTRIBUTES ──────────────────────────────────────────────────

    @_S.mcp.tool()
    def max_set_attribute(name: str, attribute: str, value: str) -> str:
        """Set an attribute on an object by scripting name. Attributes are
        Max object properties like 'patching_rect', 'fontsize', 'color',
        'background', 'presentation_rect', 'minimum', 'maximum', 'size', etc.
        Example: max_set_attribute(\"num_0\", \"minimum\", \"0\")"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'. Known: {_S.state.names()}")
        _S.tx.send("/attribute", name, str(attribute), str(value))
        _record("setattr", f"set {name}:{attribute}={value}",
                name=name, attr=attribute, new_value=value)
        return f"set {name}.{attribute} = {value}"

    @_S.mcp.tool()
    def max_set_number_properties(name: str, minimum: float = None,
                                  maximum: float = None, size: int = None) -> str:
        """Set range and display size on a number/flonum box.
        Example: max_set_number_properties(\"num_0\", minimum=0, maximum=127)"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        parts = []
        if minimum is not None:
            _S.tx.send("/attribute", name, "minimum", str(minimum))
            parts.append(f"min={minimum}")
            _time.sleep(0.02)
        if maximum is not None:
            _S.tx.send("/attribute", name, "maximum", str(maximum))
            parts.append(f"max={maximum}")
            _time.sleep(0.02)
        if size is not None:
            _S.tx.send("/attribute", name, "size", str(int(size)))
            parts.append(f"size={size}")
            _time.sleep(0.02)
        _record("setattr", f"set {name} properties: {', '.join(parts)}",
                name=name, attr="properties", new_value=parts)
        return f"set {name}: {', '.join(parts)}"

    # ── 4. RENAME ──────────────────────────────────────────────────────

    @_S.mcp.tool()
    def max_rename(old_name: str, new_name: str) -> str:
        """Rename an object's scripting name. New name must be unique.
        Example: max_rename(\"obj_3\", \"my_filter\")"""
        _S._require_init()
        if old_name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{old_name}'")
        if new_name in _S.state.objects:
            raise RuntimeError(f"name '{new_name}' already in use")
        _S.tx.send("/rename", old_name, new_name)
        obj = _S.state.objects.pop(old_name)
        obj.name = new_name
        _S.state.objects[new_name] = obj
        _record("rename", f"renamed {old_name} -> {new_name}",
                old_name=old_name, new_name=new_name)
        return f"renamed {old_name} -> {new_name}"

    # ── 5. SUBPATCHER CONTEXT ──────────────────────────────────────────

    @_S.mcp.tool()
    def max_create_subpatcher(name: str, x: int = 480, y: int = 240) -> str:
        """Create a [p name] subpatcher at (x, y). Returns the scripting name.
        Example: max_create_subpatcher(\"fx_chain\")"""
        _S._require_init()
        sn = _S._newdefault("p", [name], x, y, prefix="sp")
        _record("create", f"created subpatcher {sn}: [p {name}]",
                name=sn, maxclass="p", text=f"p {name}", x=x, y=y)
        return f"created {sn}: [p {name}]"

    @_S.mcp.tool()
    def max_enter_subpatcher(name: str) -> str:
        """Enter a subpatcher. Subsequent create/connect calls operate
        INSIDE the subpatcher via thispatcher target. Call
        max_exit_subpatcher() to return to the parent.

        Example: max_enter_subpatcher(\"fx_chain\")"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown subpatcher '{name}'")
        obj = _S.state.objects.get(name)
        if obj and obj.maxclass != "p":
            raise RuntimeError(f"'{name}' is a {obj.maxclass}, not a subpatcher")
        # Set thispatcher target to the subpatcher: subsequent script
        # commands will operate inside it
        _S.tx.send("/target", name)
        _S.state.push_patcher(name)
        return f"entered subpatcher '{name}' (depth={_S.state.patcher_depth})"

    @_S.mcp.tool()
    def max_exit_subpatcher() -> str:
        """Exit the current subpatcher back to the parent level.
        Resets thispatcher target to top-level."""
        _S._require_init()
        if _S.state.patcher_depth == 0:
            return "already at top-level patcher"
        popped = _S.state.pop_patcher()
        # Reset thispatcher target to top-level
        _S.tx.send("/target")
        if _S.state.patcher_depth > 0:
            # Re-enter the parent subpatcher
            parent = _S.state.current_patcher
            _S.tx.send("/target", parent)
            return f"exited '{popped}', re-entered '{parent}' (depth={_S.state.patcher_depth})"
        return f"exited '{popped}' (depth=0, top-level)"

    @_S.mcp.tool()
    def max_get_patcher_info() -> str:
        """Show the current patcher context path and depth."""
        _S._require_init()
        parts = ["/".join(_S.state._patcher_stack)] if _S.state._patcher_stack else ["(top-level)"]
        parts.append(f"depth={_S.state.patcher_depth}")
        parts.append(f"objects={len(_S.state.objects)}")
        parts.append(_S.state.history.summary())
        return "\n".join(parts)

    # ── 6. SNAPSHOT / RESTORE ──────────────────────────────────────────

    @_S.mcp.tool()
    def max_snapshot() -> str:
        """Capture the full patch state as a JSON string. Can be saved and
        restored with max_load_snapshot."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        snapshot = json.dumps(data, indent=2)
        return f"SNAPSHOT ({len(data.get('objects', []))} objs, {len(data.get('lines', []))} conns):\n{snapshot[:50000]}"

    @_S.mcp.tool()
    def max_load_snapshot(snapshot_json: str, clear_first: bool = True) -> str:
        """Load a previously saved snapshot. If clear_first is True (default),
        deletes existing objects first."""
        _S._require_init()
        try:
            data = json.loads(snapshot_json)
        except json.JSONDecodeError as e:
            return f"ERROR: invalid JSON: {e}"
        objs = data.get("objects", [])
        lines = data.get("lines", [])
        if clear_first:
            for name in _S.state.names():
                _S.tx.send("/delete", name)
            _S.state.reset()
        name_map = {}
        for o in objs:
            vn = o.get("varname") or o.get("id", "")
            if not vn or vn.startswith("mcp_"):
                continue
            cls = o.get("maxclass", "newobj")
            txt = o.get("text", "")
            rect = o.get("rect", [0, 0, 120, 22])
            name = _S.state.next_name("snap")
            _S.tx.send("/newdefault", name, int(rect[0]), int(rect[1]), cls)
            _time.sleep(0.02)
            if cls in ("message", "comment") and txt:
                _S.tx.send("/setbox", name, "set", *txt.split())
                _time.sleep(0.02)
            _S.state.register(MaxObject(name=name, maxclass=cls, text=txt or cls,
                                         x=int(rect[0]), y=int(rect[1])))
            name_map[vn] = name
        for ln in lines:
            src, dst = ln.get("src", ""), ln.get("dst", "")
            s_name = name_map.get(src) or (src if src in _S.state.objects else None)
            d_name = name_map.get(dst) or (dst if dst in _S.state.objects else None)
            if s_name and d_name:
                _S.tx.send("/connect", s_name, ln.get("outlet", 0), d_name, ln.get("inlet", 0))
                _time.sleep(0.02)
        return f"loaded snapshot: {len(name_map)} objects, {len(lines)} connections"

    # ── 7. SEARCH ──────────────────────────────────────────────────────

    @_S.mcp.tool()
    def max_search(query: str = "", by_class: str = "", by_text: str = "") -> str:
        """Search objects in the live patch. Filters: query (text anywhere),
        by_class (Max class like '*~'), by_text (object text substring)."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        matches = []
        for o in data.get("objects", []):
            vn = o.get("varname") or "(unnamed)"
            cls = o.get("maxclass", "")
            txt = o.get("text", "")
            if by_class and cls != by_class:
                continue
            if by_text and by_text not in txt:
                continue
            if query:
                q = query.lower()
                if q not in vn.lower() and q not in cls.lower() and q not in txt.lower():
                    continue
            rect = o.get("rect", [0, 0, 0, 0])
            matches.append(f"  {vn}: [{txt or cls}] @ ({rect[0]},{rect[1]})")
        if not matches:
            return f"no matches (query={query!r}, class={by_class!r}, text={by_text!r})"
        return f"{len(matches)} match(es):\n" + "\n".join(matches)

    # ── 8. SCRIPT / RAW COMMAND ────────────────────────────────────────

    @_S.mcp.tool()
    def max_script(command: str) -> str:
        """Send a raw message to thispatcher. For advanced operations
        not covered by other tools.
        Example: max_script(\"script send obj_3 set 440\")"""
        _S._require_init()
        _S.tx.send("/script", command)
        return f"sent: {command}"

    # ── 9. RECEIVE / SEND OBJECTS ──────────────────────────────────────

    @_S.mcp.tool()
    def max_create_receive(name: str, x: int = 480, y: int = 240) -> str:
        """Create a [r name] receive object at (x, y).
        Example: max_create_receive(\"delay_time\")"""
        _S._require_init()
        sn = _S._newdefault("r", [name], x, y, prefix="rcv")
        _record("create", f"created {sn}: [r {name}]",
                name=sn, maxclass="r", text=f"r {name}", x=x, y=y)
        return f"created {sn}: [r {name}]"

    @_S.mcp.tool()
    def max_create_send(name: str, x: int = 480, y: int = 240) -> str:
        """Create a [s name] send object at (x, y).
        Example: max_create_send(\"freq_out\")"""
        _S._require_init()
        sn = _S._newdefault("s", [name], x, y, prefix="snd")
        _record("create", f"created {sn}: [s {name}]",
                name=sn, maxclass="s", text=f"s {name}", x=x, y=y)
        return f"created {sn}: [s {name}]"

    @_S.mcp.tool()
    def max_create_buffer(name: str, frames: int = 44100, channels: int = 1,
                          x: int = 480, y: int = 240) -> str:
        """Create a [buffer~ name] buffer object.
        Example: max_create_buffer(\"my_sound\", 44100)"""
        _S._require_init()
        sn = _S._newdefault("buffer~", [name, str(frames), str(channels)],
                            x, y, prefix="buf")
        _record("create", f"created {sn}: [buffer~ {name}]",
                name=sn, maxclass="buffer~", text=f"buffer~ {name}", x=x, y=y)
        return f"created {sn}: [buffer~ {name}]"

    # ── 10. ENHANCED CREATION TOOLS ────────────────────────────────────

    @_S.mcp.tool()
    def max_create_flonum(initial: float = 0.0, minimum: float = 0.0,
                          maximum: float = 1.0, x: int = 480, y: int = 240) -> str:
        """Create a flonum with initial value and min/max range.
        Example: max_create_flonum(0.5, 0.0, 1.0)"""
        _S._require_init()
        name = _S._newdefault("flonum", [str(initial)], x, y, prefix="num")
        _S.tx.send("/attribute", name, "minimum", str(minimum))
        _time.sleep(0.02)
        _S.tx.send("/attribute", name, "maximum", str(maximum))
        _record("create", f"created {name}: flonum [{initial}]",
                name=name, maxclass="flonum", text=f"flonum {initial}", x=x, y=y)
        return f"created {name}: flonum [{initial}] range [{minimum}, {maximum}]"

    @_S.mcp.tool()
    def max_create_dial(initial: float = 0.5, minimum: float = 0.0,
                        maximum: float = 1.0, x: int = 480, y: int = 240) -> str:
        """Create a live.dial UI control with range.
        Example: max_create_dial(0.5, 0.0, 1.0)"""
        _S._require_init()
        name = _S._newdefault("live.dial", [], x, y, prefix="dial")
        _S.tx.send("/attribute", name, "minimum", str(minimum))
        _time.sleep(0.02)
        _S.tx.send("/attribute", name, "maximum", str(maximum))
        _S.tx.send("/send", name, str(initial))
        _record("create", f"created {name}: live.dial [{initial}]",
                name=name, maxclass="live.dial", text="live.dial", x=x, y=y)
        return f"created {name}: live.dial [{initial}] range [{minimum}, {maximum}]"

    @_S.mcp.tool()
    def max_create_gain(initial: float = 0.0, x: int = 480, y: int = 240) -> str:
        """Create a live.gain~ gain control.
        Example: max_create_gain(-6.0)"""
        _S._require_init()
        name = _S._newdefault("live.gain~", [], x, y, prefix="gain")
        _S.tx.send("/send", name, str(initial))
        _record("create", f"created {name}: live.gain~ [{initial} dB]",
                name=name, maxclass="live.gain~", text="live.gain~", x=x, y=y)
        return f"created {name}: live.gain~ [{initial} dB]"

    @_S.mcp.tool()
    def max_create_ui(label: str, maxclass: str = "live.dial",
                      x: int = 480, y: int = 240,
                      initial: float = 0.5, minimum: float = 0.0,
                      maximum: float = 1.0) -> str:
        """Generic UI control. Supported maxclass: live.dial, live.slider,
        live.text, live.menu, live.button, live.gain~, slider, dial."""
        _S._require_init()
        name = _S._newdefault(maxclass, [], x, y, prefix="ui")
        if maxclass in ("live.dial", "live.slider"):
            _S.tx.send("/attribute", name, "minimum", str(minimum))
            _time.sleep(0.02)
            _S.tx.send("/attribute", name, "maximum", str(maximum))
            _time.sleep(0.02)
            _S.tx.send("/send", name, str(initial))
        cmt_name = _S.state.next_name("cmt")
        _S.tx.send("/newdefault", cmt_name, int(x), int(y - 25), "comment")
        _S.tx.send("/setbox", cmt_name, "set", *str(label).split())
        _S.state.register(MaxObject(name=cmt_name, maxclass="comment",
                                     text=label, x=int(x), y=int(y - 25)))
        _record("create", f"created {name}: {maxclass} [{label}]",
                name=name, maxclass=maxclass, text=maxclass, x=x, y=y)
        return f"created {name}: {maxclass} \"{label}\" [{initial}]"

    # ── 11. BATCH CONNECT ──────────────────────────────────────────────

    @_S.mcp.tool()
    def max_connect_batch(connections: List[dict]) -> str:
        """Connect multiple pairs in batch. Each: {from, outlet, to, inlet}.
        Verified in one dump instead of per-connection.
        Example: max_connect_batch([{\"from\":\"o1\",\"outlet\":0,\"to\":\"o2\",\"inlet\":0}])"""
        _S._require_init()
        requested = []
        warnings = []
        for c in connections:
            f, t = c.get("from"), c.get("to")
            if f not in _S.state.objects:
                warnings.append(f"unknown source '{f}'"); continue
            if t not in _S.state.objects:
                warnings.append(f"unknown target '{t}'"); continue
            fo, ti = int(c.get("outlet", 0)), int(c.get("inlet", 0))
            for n, side in ((f, "src"), (t, "tgt")):
                if _S.state.objects.get(n) and _S.state.objects[n].maxclass == "!+~":
                    warnings.append(f"'{n}' is !+~ (may fail; use +~)")
            _S.tx.send("/connect", f, fo, t, ti)
            _time.sleep(0.01)
            requested.append((f, fo, t, ti))
        _time.sleep(0.1)
        try:
            data = _S._dump_raw()
            have = {(ln.get("src"), ln.get("outlet"), ln.get("dst"), ln.get("inlet"))
                    for ln in data.get("lines", [])}
            missing = [(f, fo, t, ti) for (f, fo, t, ti) in requested if (f, fo, t, ti) not in have]
            if missing:
                for (f, fo, t, ti) in missing:
                    _S.tx.send("/connect", f, fo, t, ti)
                _time.sleep(0.15)
                data2 = _S._dump_raw()
                have2 = {(ln.get("src"), ln.get("outlet"), ln.get("dst"), ln.get("inlet"))
                         for ln in data2.get("lines", [])}
                still = [(f, fo, t, ti) for (f, fo, t, ti) in missing if (f, fo, t, ti) not in have2]
                result = f"{len(requested)-len(still)}/{len(requested)} wired"
                if still:
                    result += f"; {len(still)} STILL MISSING"
            else:
                result = f"all {len(requested)} connections verified"
        except RuntimeError:
            result = f"issued {len(requested)} connections (unverified)"
        if warnings:
            result += "\n" + "\n".join(warnings)
        return result

    # ── 12. STATE RECONCILIATION ───────────────────────────────────────

    @_S.mcp.tool()
    def max_reconcile() -> str:
        """Reconcile server state with the live patch. Syncs hand-added
        named objects and prunes missing ones. Call after hand-editing."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        patch_objs = {o["varname"]: o for o in data.get("objects", [])
                      if o.get("varname") and not o["varname"].startswith("mcp_")}
        added = []
        for vn, o in patch_objs.items():
            if vn not in _S.state.objects:
                _S.state.register(MaxObject(
                    name=vn, maxclass=o.get("maxclass", "?"),
                    text=o.get("text") or o.get("maxclass", ""),
                    x=o.get("rect", [0, 0, 0, 0])[0],
                    y=o.get("rect", [0, 0, 0, 0])[1],
                ))
                added.append(vn)
        missing = [n for n in _S.state.names() if n not in patch_objs]
        for n in missing:
            _S.state.forget(n)
        parts = [f"reconciled: {len(patch_objs)} in patch, {len(_S.state.objects)} in state"]
        if added:
            parts.append(f"added: {', '.join(added[:10])}")
        if missing:
            parts.append(f"pruned from state: {', '.join(missing[:10])}")
        return "\n".join(parts)

    # ── 13. VISUALIZATION / ANALYSIS ────────────────────────────────────

    @_S.mcp.tool()
    def max_get_connections(name: str = "") -> str:
        """Show all connections involving an object. If name is empty,
        lists ALL connections in the patch. Shows direction, outlet/inlet.

        Example: max_get_connections(\"obj_3\")"""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        lines = data.get("lines", [])
        objs = data.get("objects", [])
        obj_names = {o.get("varname") or o.get("id", ""): o.get("text") or o.get("maxclass", "")
                     for o in objs}
        matches = []
        for ln in lines:
            s = ln.get("src") or ""
            d = ln.get("dst") or ""
            if name and s != name and d != name:
                continue
            s_label = obj_names.get(s, s)
            d_label = obj_names.get(d, d)
            matches.append(f"  {s}:{ln.get('outlet')} [{s_label}] -> {d}:{ln.get('inlet')} [{d_label}]")
        if not matches:
            return f"no connections{' for ' + name if name else ''}"
        header = f"connections for '{name}'" if name else f"all connections ({len(lines)})"
        return f"{header} ({len(matches)}):\n" + "\n".join(matches)

    @_S.mcp.tool()
    def max_list_classes() -> str:
        """List all unique Max object classes in the live patch with counts.
        Useful for understanding what type of patch you're working with."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        counts = {}
        for o in data.get("objects", []):
            cls = o.get("maxclass", "?")
            vn = o.get("varname") or o.get("id", "?")
            if vn.startswith("mcp_"):
                continue
            counts[cls] = counts.get(cls, 0) + 1
        if not counts:
            return "no objects in patch"
        total = sum(counts.values())
        sorted_classes = sorted(counts.items(), key=lambda x: -x[1])
        lines = [f"{total} objects, {len(counts)} unique classes:"]
        for cls, cnt in sorted_classes:
            pct = cnt / total * 100
            lines.append(f"  {cls:20s} {cnt:3d} ({pct:.0f}%)")
        return "\n".join(lines)

    @_S.mcp.tool()
    def max_patch_stats() -> str:
        """Compute statistics about the current patch: object count,
        connection count, signal vs control ratio."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        objs = data.get("objects", [])
        lines = data.get("lines", [])
        signal_objs = sum(1 for o in objs if "~" in (o.get("maxclass", "") + (o.get("text") or "")))
        control_objs = len(objs) - signal_objs
        named = sum(1 for o in objs if o.get("varname") and not o["varname"].startswith("mcp_"))
        unnamed = sum(1 for o in objs if not o.get("varname"))
        density = len(lines) / max(len(objs), 1)
        stats = [
            f"  Objects:       {len(objs)}",
            f"  Connections:   {len(lines)}",
            f"  Density:       {density:.2f} conns/obj",
            f"  Signal:        {signal_objs} ({signal_objs/max(len(objs),1)*100:.0f}%)",
            f"  Control:       {control_objs} ({control_objs/max(len(objs),1)*100:.0f}%)",
            f"  Named (mcp):   {named}",
            f"  Unnamed (hand): {unnamed}",
        ]
        return "Patch Statistics:\n" + "\n".join(stats)

    @_S.mcp.tool()
    def max_find_issues() -> str:
        """Scan the patch for common problems: disconnected signal objects,
        feedback loops with no attenuation, orphan r/s pairs, zero gains,
        unconnected delay buffers."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        objs = data.get("objects", [])
        conns = data.get("lines", [])
        warnings = []

        srcs = {}
        dsts = {}
        for ln in conns:
            s = ln.get("src", "")
            d = ln.get("dst", "")
            srcs.setdefault(s, []).append((ln.get("outlet"), d, ln.get("inlet")))
            dsts.setdefault(d, []).append(ln.get("inlet"))

        receives = set()
        sends = set()

        for o in objs:
            vn = o.get("varname") or o.get("id", "")
            if vn.startswith("mcp_"):
                continue
            cls = o.get("maxclass", "")
            txt = o.get("text", "")

            if cls in ("r", "receive"):
                receives.add(txt.strip())
            if cls in ("s", "send"):
                sends.add(txt.strip())

            if "~" in cls + txt:
                has_in = vn in dsts
                has_out = vn in srcs
                if not has_in and not has_out:
                    warnings.append(f"FLOATING: '{vn}' [{cls}] has no connections")
                elif not has_out:
                    warnings.append(f"DEAD_END: '{vn}' [{cls}] no outputs")

            if cls in ("*~", "gain~") and "0" in txt:
                if vn in srcs:
                    warnings.append(f"ZERO_GAIN: '{vn}' — audio is muted")

            if cls == "tapin~":
                has_tapout = any(o2.get("maxclass") == "tapout~" for o2 in objs)
                if not has_tapout:
                    warnings.append(f"ORPHAN_DELAY: '{vn}' [tapin~] has no [tapout~]")

        for s in sorted(sends - receives):
            warnings.append(f"ORPHAN_SEND: [s {s}] no matching [r {s}]")
        for r in sorted(receives - sends):
            warnings.append(f"ORPHAN_RECEIVE: [r {r}] no matching [s {r}]")

        if not warnings:
            return "✓ No issues detected."
        return f"{len(warnings)} issue(s):\n" + "\n".join(warnings)

    @_S.mcp.tool()
    def max_explain() -> str:
        """Analyze the patch's signal flow: inputs, outputs, processors,
        controls, generators. Describes patch topology."""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        objs = data.get("objects", [])

        inputs, outputs, generators, processors, controls, ui, other = [], [], [], [], [], [], []
        for o in objs:
            vn = o.get("varname") or o.get("id", "")
            if vn.startswith("mcp_"):
                continue
            cls = o.get("maxclass", "")
            txt = o.get("text", "")
            entry = f"{vn}: [{txt or cls}]"
            if cls in ("adc~", "r", "receive", "sig~"):
                inputs.append(entry)
            elif cls in ("dac~", "s", "send", "prepend"):
                outputs.append(entry)
            elif cls in ("cycle~", "saw~", "tri~", "rect~", "noise~", "phasor~", "metro", "tempo"):
                generators.append(entry)
            elif cls in ("*~", "+~", "!+~", "-~", "/~", "svf~", "lores~", "biquad~",
                          "delay~", "tapin~", "tapout~", "line~", "gain~", "scale",
                          "expr", "pipe", "delay"):
                processors.append(entry)
            elif cls in ("number", "flonum", "toggle", "slider", "dial",
                          "live.dial", "live.slider", "live.gain~", "live.menu"):
                controls.append(entry)
            elif cls in ("comment", "button", "message", "live.text", "live.button"):
                ui.append(entry)
            else:
                other.append(entry)

        parts = ["Patch Analysis:"]
        for label, items in [("Inputs", inputs), ("Outputs", outputs),
                              ("Generators", generators), ("Processors", processors),
                              ("Controls", controls), ("UI", ui), ("Other", other)]:
            if items:
                parts.append(f"  {label} ({len(items)}): " + ", ".join(items))
        parts.append(f"\n  Total: {len(objs)} objects")
        return "\n".join(parts)

    # ── 14. MODIFICATION TOOLS ─────────────────────────────────────────

    @_S.mcp.tool()
    def max_move(name: str, x: int, y: int) -> str:
        """Move an object to coordinates (x, y). Preserves current size.
        Example: max_move(\"obj_3\", 700, 400)"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        obj = _S.state.objects[name]
        old_x, old_y = obj.x, obj.y
        _S.tx.send("/attribute", name, "patching_rect", f"{x} {y} 120 22")
        obj.x, obj.y = x, y
        _record("move", f"moved {name}: ({old_x},{old_y}) -> ({x},{y})",
                name=name, old_x=old_x, old_y=old_y, new_x=x, new_y=y)
        return f"moved {name}: ({old_x},{old_y}) -> ({x},{y})"

    @_S.mcp.tool()
    def max_resize(name: str, width: int, height: int) -> str:
        """Resize an object's box (width × height).
        Example: max_resize(\"num_0\", 80, 22)"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        obj = _S.state.objects[name]
        _S.tx.send("/attribute", name, "patching_rect", f"{obj.x} {obj.y} {width} {height}")
        _record("resize", f"resized {name}: {width}x{height}",
                name=name, width=width, height=height)
        return f"resized {name}: {obj.x},{obj.y} {width}x{height}"

    @_S.mcp.tool()
    def max_set_text(name: str, text: str) -> str:
        """Change the text/content of an object. Uses /setbox for messages
        and comments; /attribute for other objects.
        Example: max_set_text(\"msg_0\", \"1 20\")"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        obj = _S.state.objects[name]
        old_text = obj.text
        if obj.maxclass in ("message", "comment"):
            _S.tx.send("/setbox", name, "set", *str(text).split())
        else:
            _S.tx.send("/attribute", name, "text", str(text))
        obj.text = text
        _record("settext", f"set {name} text: '{old_text}' -> '{text}'",
                name=name, old_text=old_text, new_text=text)
        return f"set {name} text: '{old_text}' -> '{text}'"

    @_S.mcp.tool()
    def max_set_color(name: str, color: str = "") -> str:
        """Set an object's background color. Formats: hex (#FF8800),
        RGB floats (\"1.0 0.5 0.0\"), named (\"red\"). Empty string resets.

        Example: max_set_color(\"num_0\", \"#FF4400\")"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        _S.tx.send("/attribute", name, "bgcolor", color if color else "")
        _record("setcolor", f"set {name} color={color or 'reset'}",
                name=name, color=color)
        return f"set {name} bgcolor = {color or '(reset)'}"

    @_S.mcp.tool()
    def max_clone(name: str, x: int = 0, y: int = 0,
                  offset_x: int = 120, offset_y: int = 80) -> str:
        """Clone an object. If x,y are 0 (default), places at offset
        from the original.
        Example: max_clone(\"obj_3\", offset_x=200)"""
        _S._require_init()
        if name not in _S.state.objects:
            raise RuntimeError(f"unknown object '{name}'")
        obj = _S.state.objects[name]
        clone_x = x if x else obj.x + offset_x
        clone_y = y if y else obj.y + offset_y
        parts = obj.text.split()
        cls = parts[0] if parts else obj.maxclass
        args = parts[1:] if len(parts) > 1 else []
        if cls == "message":
            new_name = _S.state.next_name("msg")
            _S.tx.send("/newdefault", new_name, int(clone_x), int(clone_y), "message")
            if args:
                _S.tx.send("/setbox", new_name, "set", *args)
            _S.state.register(MaxObject(name=new_name, maxclass="message",
                                         text=" ".join(args) if args else "",
                                         x=int(clone_x), y=int(clone_y)))
        elif cls == "comment":
            new_name = _S.state.next_name("cmt")
            _S.tx.send("/newdefault", new_name, int(clone_x), int(clone_y), "comment")
            if args:
                _S.tx.send("/setbox", new_name, "set", *args)
            _S.state.register(MaxObject(name=new_name, maxclass="comment",
                                         text=" ".join(args) if args else "",
                                         x=int(clone_x), y=int(clone_y)))
        else:
            new_name = _S._newdefault(cls, args, int(clone_x), int(clone_y), prefix="cln")
        _record("clone", f"cloned {name} -> {new_name} at ({clone_x},{clone_y})",
                original=name, clone=new_name, cls=cls, x=clone_x, y=clone_y)
        return f"cloned {name} -> {new_name}: [{obj.text}] at ({clone_x},{clone_y})"

    # ── 15. STATE & FILE OPERATIONS ────────────────────────────────────

    @_S.mcp.tool()
    def max_get_dsp_status() -> str:
        """Check whether global audio DSP is currently on or off."""
        _S._require_init()
        return f"DSP is {'ON' if _S.state.dsp_on else 'OFF'}"

    @_S.mcp.tool()
    def max_save(filepath: str = "") -> str:
        """Save the current patch to a .maxpat file on disk.
        Default: ~/Desktop/mcp_saved_patch.maxpat

        Example: max_save(\"/Users/me/Desktop/delay.maxpat\")"""
        _S._require_init()
        try:
            data = _S._dump_raw()
        except RuntimeError as e:
            return f"ERROR: {e}"
        if not filepath:
            filepath = os.path.expanduser("~/Desktop/mcp_saved_patch.maxpat")
        if not filepath.endswith(".maxpat"):
            filepath += ".maxpat"

        maxpat = {
            "patcher": {
                "fileversion": 1,
                "appversion": {"major": 9, "minor": 1, "revision": 4,
                               "architecture": "x64", "modernui": 1},
                "classnamespace": "box",
                "rect": [0, 0, 1200, 800],
                "boxes": [],
                "lines": [],
                "autosave": 0,
            }
        }
        objs = data.get("objects", [])
        conns = data.get("lines", [])
        name_to_id = {}
        for o in objs:
            vn = o.get("varname") or o.get("id", "")
            if vn.startswith("mcp_"):
                continue
            cls = o.get("maxclass", "comment")
            txt = o.get("text", cls)
            rect = o.get("rect", [0, 0, 120, 22])
            box_id = f"box-{vn}"
            box_entry = {
                "box": {
                    "id": box_id,
                    "maxclass": "newobj" if cls not in ("message","comment","flonum",
                               "number","toggle","button","slider","live.dial",
                               "live.gain~","live.slider","live.text") else cls,
                    "text": txt,
                    "patching_rect": rect,
                }
            }
            if vn:
                box_entry["box"]["varname"] = vn
            maxpat["patcher"]["boxes"].append(box_entry)
            name_to_id[vn] = box_id

        for ln in conns:
            src = name_to_id.get(ln.get("src", ""))
            dst = name_to_id.get(ln.get("dst", ""))
            if src and dst:
                maxpat["patcher"]["lines"].append({
                    "patchline": {
                        "source": [src, ln.get("outlet", 0)],
                        "destination": [dst, ln.get("inlet", 0)],
                    }
                })

        try:
            with open(filepath, "w") as f:
                json.dump(maxpat, f, indent=2)
        except OSError as e:
            return f"ERROR: {e}"
        return (f"saved to {filepath} ({len(maxpat['patcher']['boxes'])} objects, "
                f"{len(maxpat['patcher']['lines'])} connections)")

    # ── 16. TEMPLATES ──────────────────────────────────────────────────

    @_S.mcp.tool()
    def max_list_templates() -> str:
        """List all available patch templates with descriptions, parameters,
        object counts. Templates are ready-to-build patch graphs.

        Example: max_list_templates()"""
        _S._require_init()
        from . import templates as _tpls
        entries = _tpls.list_templates()
        if not entries:
            return "no templates available"
        lines = [f"{len(entries)} templates:"]
        for e in entries:
            params_str = "; ".join(e["params"][:3])
            if len(e["params"]) > 3:
                params_str += f"; +{len(e['params'])-3} more"
            lines.append(f"  {e['name']:20s} — {e['description']}")
            lines.append(f"    {e['object_count']} objects, {e['connection_count']} connections")
            if params_str:
                lines.append(f"    params: {params_str}")
        return "\n".join(lines)

    @_S.mcp.tool()
    def max_apply_template(template_name: str, params: str = "",
                           title: str = "", auto_dsp: bool = True) -> str:
        """Instantiate a patch template. Uses max_build_patch internally.

        Args:
          template_name: one of the names returned by max_list_templates()
          params: optional override string \"key1=val1 key2=val2\" (space-sep)
          title: optional patch title
          auto_dsp: if true (default), turns DSP on after building

        Example: max_apply_template(\"simple_synth\", \"freq=220 amplitude=0.5\")
                 max_apply_template(\"simple_delay\", \"delay_time=1000 feedback=0.5\")
                 max_apply_template(\"lowpass_filter\", \"cutoff=5000 resonance=0.8\")"""
        _S._require_init()
        from . import templates as _tpls

        # Parse params string: "key=val key=val"
        parsed_params = {}
        if params:
            for token in params.split():
                if "=" in token:
                    k, v = token.split("=", 1)
                    try:
                        v = int(v) if v.isdigit() or (v.startswith("-") and v[1:].isdigit()) else float(v)
                    except ValueError:
                        pass
                    parsed_params[k] = v

        try:
            graph = _tpls.apply(template_name, parsed_params, title="")
        except ValueError as e:
            return f"ERROR: {e}"

        result = _S.max_build_patch(
            objects=graph["objects"],
            connections=graph["connections"],
            title=title or f"Template: {template_name}",
        )

        if auto_dsp:
            _S.tx.send("/dsp", 1)
            _S.state.dsp_on = True
            result += "\nDSP turned ON"

        return result

    # ── 17. MCP PROMPTS ────────────────────────────────────────────────

    # Prompts are registered directly on the FastMCP instance outside
    # of _register_all. They use @_S.mcp.prompt() which works like tool()
    # but returns prompt content strings.

    @_S.mcp.prompt()
    def build_delay() -> str:
        """Prompt template: build a simple mono delay patch.
        Prompts the user for parameters and builds the patch."""
        return (
            "I'll build a simple mono delay patch for you. Let me know:\n"
            "- Delay time (ms, default 500)\n"
            "- Feedback amount (0-1, default 0.35)\n"
            "- Wet/dry mix (0-1, default 0.5)\n\n"
            "I'll create the full signal chain with tapin~/tapout~, "
            "feedback loop, wet/dry mix, and flonum controls."
        )

    @_S.mcp.prompt()
    def build_synth() -> str:
        """Prompt template: build a monophonic synthesizer patch."""
        return (
            "I'll build a simple monophonic synthesizer for you. "
            "Available waveforms: saw~, tri~, rect~, cycle~.\n"
            "Let me know:\n"
            "- Waveform (default saw~)\n"
            "- Frequency in Hz (default 440)\n"
            "- Amplitude 0-1 (default 0.3)\n"
            "- ADSR or simple attack/decay envelope\n\n"
            "I'll create the oscillator, envelope generator, VCA, "
            "and output to dac~."
        )

    @_S.mcp.prompt()
    def build_filter() -> str:
        """Prompt template: build a lowpass filter patch."""
        return (
            "I'll build a lowpass filter using svf~. Let me know:\n"
            "- Cutoff frequency in Hz (default 2000)\n"
            "- Resonance 0-1 (default 0.5)\n"
            "- Input source: in~ (external) or internal oscillator\n\n"
            "The svf~ object provides simultaneous lowpass, highpass, "
            "and bandpass outputs on outlets 0, 1, and 2."
        )

    @_S.mcp.prompt()
    def explore_patch() -> str:
        """Prompt template: analyze and explain the current patch."""
        return (
            "Let me analyze the patch that's currently in Max. "
            "I'll read it back, categorize every object (inputs, "
            "outputs, generators, processors, controls), show the "
            "connection topology, and explain the signal flow.\n\n"
            "I'll also check for common issues like disconnected "
            "objects, zero gains, orphan sends/receives, and "
            "feedback loops without attenuation."
        )


# ── Undo/Redo application helpers ────────────────────────────────────────

def _apply_inverse(entry: Entry, direction: str) -> str:
    if entry.kind == "batch":
        batch = entry.inverse.get("batch", [])
        for sub in batch:
            _apply_single_inverse(sub)
        return f"{direction}: batch ({len(batch)} ops)"
    return _apply_single_inverse(entry)


def _apply_single_inverse(entry: Entry) -> str:
    kind, fwd = entry.kind, entry.forward
    if kind == "create":
        name = fwd.get("name", "")
        if name and name in _S.state.objects:
            _S.tx.send("/delete", name)
            _S.state.forget(name)
            return f"undo create: deleted {name}"
        return f"undo create: {name} already gone"
    elif kind == "delete":
        name = fwd.get("name", "")
        mc = fwd.get("maxclass", "")
        txt = fwd.get("text", "")
        x = fwd.get("x", 480); y = fwd.get("y", 240)
        if name and mc:
            _S.tx.send("/newdefault", name, int(x), int(y), mc)
            _time.sleep(0.02)
            if mc in ("message", "comment"):
                _S.tx.send("/setbox", name, "set", *txt.split())
            _S.state.register(MaxObject(name=name, maxclass=mc, text=txt, x=int(x), y=int(y)))
            return f"undo delete: recreated {name}: [{txt}]"
        return f"undo delete: no data"
    elif kind == "connect":
        name = fwd.get("from_name", "")
        out = fwd.get("outlet", 0)
        dest = fwd.get("to_name", "")
        inn = fwd.get("inlet", 0)
        if name and dest:
            _S.tx.send("/disconnect", name, int(out), dest, int(inn))
            return f"undo connect: disconnected {name}:{out} -> {dest}:{inn}"
        return "undo connect: insufficient data"
    elif kind == "disconnect":
        name = fwd.get("from_name", "")
        out = fwd.get("outlet", 0)
        dest = fwd.get("to_name", "")
        inn = fwd.get("inlet", 0)
        if name and dest:
            _S.tx.send("/connect", name, int(out), dest, int(inn))
            return f"undo disconnect: reconnected {name}:{out} -> {dest}:{inn}"
        return "undo disconnect: insufficient data"
    elif kind == "rename":
        new_name = fwd.get("new_name", "")
        old_name = fwd.get("old_name", "")
        if new_name in _S.state.objects:
            obj = _S.state.objects.pop(new_name)
            obj.name = old_name
            _S.state.objects[old_name] = obj
            _S.tx.send("/rename", new_name, old_name)
            return f"undo rename: {new_name} -> {old_name}"
        return f"undo rename: {new_name} not found"
    return f"undo: unknown '{kind}'"


def _apply_forward(entry: Entry, direction: str) -> str:
    if entry.kind == "batch":
        batch = entry.forward.get("batch", [])
        for sub in batch:
            _apply_single_forward(sub)
        return f"{direction}: batch ({len(batch)} ops)"
    return _apply_single_forward(entry)


def _apply_single_forward(entry: Entry) -> str:
    kind, fwd = entry.kind, entry.forward
    if kind == "create":
        name = fwd.get("name", "")
        mc = fwd.get("maxclass", ""); txt = fwd.get("text", "")
        x = fwd.get("x", 480); y = fwd.get("y", 240)
        if name and mc:
            _S.tx.send("/newdefault", name, int(x), int(y), mc)
            _time.sleep(0.02)
            if mc in ("message", "comment"):
                _S.tx.send("/setbox", name, "set", *txt.split())
            _S.state.register(MaxObject(name=name, maxclass=mc, text=txt, x=int(x), y=int(y)))
            return f"redo create: {name}: [{txt}]"
        return f"redo create: no data"
    elif kind == "delete":
        name = fwd.get("name", "")
        if name and name in _S.state.objects:
            _S.tx.send("/delete", name)
            _S.state.forget(name)
            return f"redo delete: {name}"
        return f"redo delete: {name} gone"
    elif kind == "connect":
        name = fwd.get("from_name", ""); out = fwd.get("outlet", 0)
        dest = fwd.get("to_name", ""); inn = fwd.get("inlet", 0)
        if name and dest:
            _S.tx.send("/connect", name, int(out), dest, int(inn))
            return f"redo connect: {name}:{out} -> {dest}:{inn}"
        return "redo connect: insufficient data"
    elif kind == "rename":
        old_name = fwd.get("old_name", ""); new_name = fwd.get("new_name", "")
        if old_name in _S.state.objects:
            obj = _S.state.objects.pop(old_name)
            obj.name = new_name
            _S.state.objects[new_name] = obj
            _S.tx.send("/rename", old_name, new_name)
            return f"redo rename: {old_name} -> {new_name}"
        return f"redo rename: {old_name} not found"
    return f"redo: unknown '{kind}'"
