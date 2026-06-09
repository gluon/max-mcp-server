# maxmsp-mcp

Build and drive [Max/MSP](https://cycling74.com) patches from an MCP client
(Claude Desktop, Claude Code, the MCP Inspector, ...) in natural language. The
agent creates objects, wires them, toggles audio, sets message content, and
**reads the live patch back** to see what is actually there before it edits.

Pure Max mechanisms, no third-party externals, no `mxj`:
- **Writing** the patch uses `[thispatcher]` scripting (`script newdefault`,
  `script connect`, `script delete`, `script send`).
- **Reading** the patch uses a `[v8]` JavaScript object that walks the patcher
  via the official Max JS API (`boxtext`, `patchcords`) and returns it as JSON.
- **Transport** is OSC over UDP between the Python server and a vanilla
  `[udpreceive]` / `[udpsend]` pair in the host patch.

## Design notes

- **Stable addressing.** Every object the server creates gets a scripting
  *name* (`obj_0`, `obj_1`, ...). You wire, set and delete by name, so the
  mapping never drifts when the user edits the patch by hand.
- **Single-object delete.** `script delete <name>` removes exactly one object.
- **Closed loop.** `max_dump_patch` and `max_verify` let the agent confirm its
  own work and discover objects the user added by hand, instead of building
  blind.
- **Machinery stays hidden.** Plumbing objects carry `mcp_*` scripting names and
  are filtered out of every dump, so the agent only ever sees the musical patch.

## Architecture

```
MCP client (stdio, JSON-RPC)
      |
      v
maxmsp_mcp.server
      |  write: OSC/UDP -> [udpreceive 7400] -> [route ...] -> [thispatcher]
      |  read:  [v8 dump.js] -> [udpsend 127.0.0.1 7401] -> OSC/UDP
      v
   Max patch (max/mcp_host.maxpat)
```

Objects land in the host patcher itself (`thispatcher` targets the patcher it
lives in).

## Requirements

- Max **8+** (`thispatcher`, vanilla `udpreceive`/`udpsend`, the `[v8]` engine).
- Python **3.10+** for the MCP server.
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`.

No external Max packages.

## Install

```bash
git clone https://github.com/gluon/max-mcp-server
cd max-mcp-server
uv venv && source .venv/bin/activate
uv pip install -e .
```

Register the server with your MCP client. For Claude Desktop, add to its config
(use the **absolute** path to `uv`, from `which uv`; GUI launchers do not inherit
your shell `PATH`):

```json
{
  "mcpServers": {
    "maxmsp": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/max-mcp-server",
               "run", "python", "-m", "maxmsp_mcp.server"],
      "env": { "MAX_HOST": "127.0.0.1", "MAX_PORT": "7400", "MAX_RETURN_PORT": "7401" }
    }
  }
}
```

**Then open `max/mcp_host.maxpat` in Max and leave it open.** Add the `max/`
folder to the Max search path (Options > File Preferences) so `[v8 dump.js]`
resolves. The server talks to this patch; with it closed, messages go nowhere.

### Try it without a chat client

The [MCP Inspector](https://modelcontextprotocol.io) drives the tools by hand:

```bash
npx @modelcontextprotocol/inspector \
  uv --directory /absolute/path/to/max-mcp-server run python -m maxmsp_mcp.server
```

## Tools

Call **`max_init` first**; every other tool refuses until it has. `max_init`
returns the orientation guide (wire model, naming contract, object cheat sheet,
cookbook) so the model has one server-authored source of truth.

| Tool                  | What it does |
| --------------------- | ------------ |
| `max_init`            | **Mandatory first call.** Returns the orientation guide and unlocks the rest |
| `max_create_object`   | Create `[maxclass args...]` at (x,y); returns its scripting name |
| `max_create_message`  | Create a message box and set its content |
| `max_create_comment`  | Create a text comment |
| `max_create_toggle`   | Create a `[toggle]` |
| `max_create_bang`     | Create a `[button]` |
| `max_create_number`   | Create a `[number]` or `[flonum]` |
| `max_create_slider`   | Create a `[slider]` |
| `max_connect`         | Wire `from:outlet -> to:inlet` (by name) |
| `max_disconnect`      | Remove a connection |
| `max_delete`          | Delete a single object by name |
| `max_set_dsp`         | Start/stop global audio DSP |
| `max_send`            | Forward a message to a named `[receive]` (see limitations) |
| `max_clear_canvas`    | Delete every object this server created |
| `max_get_state`       | List what the server has created |
| `max_dump_patch`      | Read the live patch back (objects + connections, hand-added included) |
| `max_verify`          | Dump and check that everything the server created is present |

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

## Patch read-back

`[v8 dump.js]` walks the patcher and sends its full state (objects +
connections) as OSC to the server on **port 7401**.

- `max_dump_patch` returns every object (`varname`, `maxclass`, `text`, `rect`)
  and every connection, including objects the user added by hand.
- `max_verify` dumps and reports any server-created object missing from the
  patch, so the agent can rebuild it.

Objects related by **name** (e.g. `[buffer~ snd]` and `[record~ snd]`) are
linked by that shared name in their text, not by a patch cord — read the object
text, not just the connections, to see such relationships.

If text comes back empty, set `DEBUG = 1` at the top of `max/dump.js`, save, and
watch the Max Console on a bang.

## Configuration

| Variable          | Default     | Meaning |
| ----------------- | ----------- | ------- |
| `MAX_HOST`        | `127.0.0.1` | Where Max listens |
| `MAX_PORT`        | `7400`      | `[udpreceive]` port (writing) |
| `MAX_RETURN_PORT` | `7401`      | `[udpsend]` port (reading) |

Change a port in both the env var and the matching object in the host patch.

## Testing

The OSC wire format, the read-back decoding, and the server bookkeeping are
covered by tests that run without Max (loopback UDP + a fake transport):

```bash
uv pip install pytest
uv run pytest -q
```

## Limitations

- **`max_send` is a stub.** `/send` currently prints to the Max Console. To
  drive a live `[receive <name>]`, wire `[forward]` off the `/send` outlet in
  `max/mcp_host.maxpat`.
- **Dumps are single-datagram.** Very large patches may exceed one UDP packet;
  chunking is planned.
- Objects created by hand have no scripting name, so they appear in dumps with a
  `#index` id and their text rather than a stable name.

## License

MIT — see `LICENSE`.
