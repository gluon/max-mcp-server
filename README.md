# maxmsp-mcp

A reliable [Model Context Protocol](https://modelcontextprotocol.io) server for
[Max/MSP](https://cycling74.com). It lets an MCP client (Claude Desktop, Claude
Code, etc.) build and drive Max patches in natural language: create objects,
wire them together, toggle audio, and drive a running patch.

Spiritual port of [jfboisvenue/pd-mcp-server](https://github.com/jfboisvenue/pd-mcp-server)
to the Max world. Same idea, native Max mechanisms.

## Why this design is reliable

It uses Max's own dynamic-patching object, **`thispatcher`** (`script
newdefault`, `script connect`, `script disconnect`, `script delete`), driven by
**OSC over UDP** into a vanilla **`[udpreceive]`**. That means:

- **No third-party externals** (no CNMAT odot, no sadam, no net libs).
- **No mxj.**
- **No intermediate daemon.** The MCP server talks straight to `[udpreceive]`.
- **Stable object addressing.** Every object gets a scripting *name*
  (`obj_0`, `obj_1`, ...). You wire and delete by name, so ids never drift on
  manual edits.

Two things this does *better* than the Pd version, by virtue of Max:

- **Single-object delete** (`script delete <name>`). Pd vanilla cannot delete
  one object; this can.
- **No index resync.** Names are stable, so there is no creation-index counter
  to realign after a hand edit.

## Architecture

```
Claude / MCP client
       |  (stdio, JSON-RPC)
       v
maxmsp_mcp.server  --OSC over UDP-->  [udpreceive 7400]   (max/mcp_host.maxpat)
                                            |
                                       [route /newdefault /connect /disconnect /delete /dsp /send]
                                            |
                                       [prepend script ...] -> [thispatcher]
```

Created objects land in the host patcher itself (`thispatcher` targets the
top-level patcher it lives in).

## Install (dev / local)

```
git clone https://github.com/gluon/max-mcp-server
cd max-mcp-server
uv run python -m maxmsp_mcp.server      # or: pip install -e . && maxmsp-mcp
```

Register it in `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or the Linux/Windows equivalent:

```json
{
  "mcpServers": {
    "maxmsp": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/max-mcp-server",
               "run", "python", "-m", "maxmsp_mcp.server"],
      "env": { "MAX_HOST": "127.0.0.1", "MAX_PORT": "7400" }
    }
  }
}
```

Use the **absolute** path to `uv` (`which uv`); GUI launchers do not inherit the
shell `PATH`.

**Then open `max/mcp_host.maxpat` in Max** and leave it open. The server needs
something to talk to.

## Requirements

- Max **8+** (uses `thispatcher` scripting + vanilla `udpreceive`).
- Python **3.10+** for the MCP server.
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`.

No external Max packages required.

## Tools

The agent must call **`max_init` first**; every other tool refuses until it
has. `max_init` returns the orientation guide (wire model, id contract, object
cheat sheet, cookbook), so the model has a single server-authored source of
truth.

| Tool                  | What it does |
| --------------------- | ------------ |
| `max_init`            | **Mandatory first call.** Returns the orientation guide and unlocks the rest |
| `max_create_object`   | Create `[maxclass args...]` at (x,y); returns its scripting name |
| `max_create_message`  | Create a message box |
| `max_create_comment`  | Create a text comment |
| `max_create_toggle`   | Create a `[toggle]` |
| `max_create_bang`     | Create a `[button]` |
| `max_create_number`   | Create a `[number]` or `[flonum]` |
| `max_create_slider`   | Create a `[slider]` |
| `max_connect`         | Wire `from:outlet -> to:inlet` (by name) |
| `max_disconnect`      | Remove a connection |
| `max_delete`          | Delete a single object by name |
| `max_set_dsp`         | Start/stop global audio DSP |
| `max_send`            | Forward a message to a named `[receive]` (v0.1 stub, see below) |
| `max_clear_canvas`    | Delete every object this server created |
| `max_get_state`       | List objects the server has created |
| `max_dump_patch`      | **Read the live patch back** (objects + connections, hand-added included) |
| `max_verify`          | Dump and check that everything the server created is actually present |

### Example: 440 Hz sine to the DAC

```
max_create_object  maxclass="cycle~"  args=["440"]  x=40 y=40   -> obj_0
max_create_object  maxclass="*~"      args=["0.2"]  x=40 y=90   -> obj_1
max_create_object  maxclass="dac~"                  x=40 y=140  -> obj_2
max_connect  obj_0 0 -> obj_1 0
max_connect  obj_1 0 -> obj_2 0      (left)
max_connect  obj_1 0 -> obj_2 1      (right)
max_set_dsp  on=true
```

## Testing (without Max)

The OSC wire format and the server bookkeeping are covered by tests that run
without Max, using a real loopback UDP socket and a fake transport:

```
pip install pytest
python -m pytest tests/ -v
```

## Patch read-back (v0.2, closed loop)

Earlier MCP-for-patcher tools (including the Pd one) are open-loop: the server
mirrors what it created but never reads the patch back, so the agent cannot see
hand edits or confirm its own work. This one closes the loop.

A `[v8 dump.js]` in the host patch walks the patcher and sends its full state
(objects + connections) as OSC to the server on **port 7401**. Two tools use it:

- `max_dump_patch` — see every object and connection in the patch, including
  ones the user added by hand.
- `max_verify` — check that everything the server created is actually present.

Plumbing objects carry `mcp_*` scripting names and are filtered out of dumps, so
the agent only sees the musical patch.

`dump.js` must sit where Max can find it (next to `mcp_host.maxpat`, or add its
folder in Options > File Preferences). If text comes back empty, set `DEBUG = 1`
at the top of `dump.js` and watch the Max Console on a bang.



- **`max_send` is a stub.** `/send` currently prints to the Max console. To
  actually drive a live `[receive <name>]`, wire `[forward]` off the `/send`
  outlet in `max/mcp_host.maxpat`. (Kept honest until validated.)
- **No read-back.** The server mirrors what it created; it does not query Max.
  A future v0.2 can use Node for Max (`node.script` + `max-api`) for bidirectional
  state and live introspection.
- Default transport is **UDP on 7400**. Change the `[udpreceive]` argument and
  `MAX_PORT` together to move it.

## License

MIT. Concept inspired by jfboisvenue/pd-mcp-server (MIT).
