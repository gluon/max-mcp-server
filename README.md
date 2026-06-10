# maxmsp-mcp


> **Early experiment — v0.4, a first public test, not a finished product.**
> It works and ships with a test suite, but it has had very little real-world use:
> expect rough edges, and expect things to change. It has been exercised mostly
> through the in-Max chat; the external MCP server runs the same engine and passes
> the tests but has seen little live use. Bug reports and feedback are very welcome.

Build and drive [Max/MSP](https://cycling74.com) patches in natural language,
from an MCP client (Claude Desktop, Claude Code, the MCP Inspector, ...) **or
from a chat window that lives inside Max itself**. The agent creates objects,
wires them, sets message content, toggles audio, **reads the live patch back**
to see what is actually there before it edits, and **grounds itself on the
official object reference** so it stops guessing object signatures.

Pure Max mechanisms — no third-party externals, no `mxj`, no relay daemon:

- **Writing** the patch uses `[thispatcher]` scripting (`script newdefault`,
  `script connect`, `script disconnect`, `script delete`, `script send`).
- **Reading** the patch uses a `[v8]` JavaScript object that walks the patcher
  via the official Max JS API (`boxtext`, `patchcords`) and returns it as JSON.
- **Transport** to the external server is OSC over UDP between the Python server
  and a stock `[udpreceive]` / `[udpsend]` pair in the host patch. The in-Max
  chat drives the same plumbing directly from `[node.script]`.

## Two ways to use it

| Facade | What it is | Runs the LLM via |
| ------ | ---------- | ---------------- |
| **External MCP server** | `maxmsp_mcp.server`, spoken to by Claude Desktop / Claude Code / the Inspector over stdio | your Claude plan / MCP client |
| **In-Max chat** | a chat window *inside* the patch (`[node.script chat.js]` + `[jweb]`), no external client | the Anthropic API (or a local model) |

Both facades share the same command vocabulary, the same host patch, and the
same patching guide. Build with one, inspect or extend with the other.

## Design notes

- **Stable addressing.** Every object the agent creates gets a scripting *name*.
  You wire, set and delete by name, so the mapping never drifts when the user
  edits the patch by hand. In the in-Max chat the model assigns its own readable
  labels (`carrier`, `pack_main`, ...) and wires by those.
- **Single-object delete.** `script delete <name>` removes exactly one object.
- **Closed loop.** The agent dumps the live patch to confirm its own work and to
  discover objects the user added by hand, instead of building blind.
- **Machinery stays hidden.** Plumbing objects carry `mcp_*` scripting names and
  are filtered out of every dump, so the agent only ever sees the musical patch.
- **Grounded on the docs.** A parsed reference database lets the agent look up an
  object's real inlets, outlets, arguments and attributes instead of inventing
  them.

## Architecture

```
 MCP client (stdio, JSON-RPC)                 In-Max chat ([jweb] UI)
        |                                            |
        v                                            v
 maxmsp_mcp.server                          [node.script chat.js]
        |  write: OSC/UDP -> [udpreceive 7400] ----.    |
        |  read:  [v8 dump.js] -> [udpsend 7401] <--|    | write/read
        v                                           v    v
                       Max patch (max/mcp_host.maxpat)
                  [route] -> [thispatcher]      [v8 dump.js]
```

Objects land in the host patcher's top level (`[thispatcher]` targets the
patcher it lives in); all plumbing is encapsulated in a `[p mcp_server]`
subpatcher and filtered from every read-back.

## Requirements

- Max **8 or 9** (`thispatcher`, stock `udpreceive`/`udpsend`, the `[v8]`
  engine; `[node.script]` for the in-Max chat).
- Python **3.10+** for the external MCP server.
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`.

No external Max packages required.

## Install

```bash
git clone https://github.com/gluon/max-mcp-server
cd max-mcp-server
uv venv && source .venv/bin/activate
uv pip install -e .
```

**Open `max/mcp_host.maxpat` in Max and leave it open.** Add the `max/` folder to
the Max search path (Options > File Preferences) so `[v8 dump.js]` and
`[node.script chat.js]` resolve. The server talks to this patch; with it closed,
messages go nowhere.

### Register the external server with an MCP client

For Claude Desktop, add to its config (use the **absolute** path to `uv`, from
`which uv`; GUI launchers do not inherit your shell `PATH`):

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

### Try it without a chat client

The [MCP Inspector](https://modelcontextprotocol.io) drives the tools by hand:

```bash
npx @modelcontextprotocol/inspector \
  uv --directory /absolute/path/to/max-mcp-server run python -m maxmsp_mcp.server
```

## Object reference (grounding)

So the agent reasons from real object signatures instead of guessing, build a
local reference database from the `.maxref.xml` files that Max ships for every
object. The parser handles both the standard Max/MSP schema and the RNBO schema,
de-duplicates across packages (preferring core Max/MSP), and writes a single
JSON file.

```bash
# point it at your Max app and, optionally, your packages
uv run python tools/build_maxref_db.py \
  /Applications/Max.app \
  ~/Documents/Max\ 9/Packages \
  -o maxmsp_mcp/objects.json

# core Max/MSP/Jitter only, for a clean and portable database:
uv run python tools/build_maxref_db.py \
  /Applications/Max.app --core-only -o maxmsp_mcp/objects.json
```

`objects.json` is git-ignored: it is built from your own Max install (so it can
include private or third-party objects) and belongs on your machine, not in the
repository. Each user runs the parser once.

With the database present, the agent can call **`max_doc`** (external server) or
**`lookup_object`** (in-Max chat) to fetch an object's digest, arguments,
inlets, outlets, attributes and messages — with a fuzzy fallback that suggests
close names. Without it, those tools simply report that no database is loaded;
everything else still works.

## Tools (external server)

Call **`max_init` first**; every other tool refuses until it has. `max_init`
returns the orientation guide (wire model, naming contract, object cheat sheet,
cookbook, layout and style rules) so the model has one server-authored source of
truth.

| Tool                  | What it does |
| --------------------- | ------------ |
| `max_init`            | **Mandatory first call.** Returns the orientation guide and unlocks the rest |
| `max_build_patch`     | **Build a whole patch from a graph** (objects + connections by id): auto-layout, by-id wiring, self-healing read-back verification. Preferred for building from scratch |
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
| `max_doc`             | Look up an object's reference (needs the object database) |

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

## In-Max chat

A chat window lives inside Max, with no external client. `[node.script chat.js]`
runs a small local HTTP server, `[jweb]` displays the chat UI pointed at it, and
the backend talks to an LLM, executes its tool calls through the same
`[thispatcher]` plumbing, and reads the patch back via `[v8 dump.js]`.

Setup:

1. Copy the config and add your key (kept out of git):
   ```bash
   cp max/chat.config.example.json max/chat.config.json
   # edit max/chat.config.json -> anthropic_api_key
   ```
2. Open `max/mcp_host.maxpat`. `[node.script chat.js]` autostarts and prints
   `serving on http://127.0.0.1:5173` in the Max Console.
3. Type into the `[jweb]` chat, e.g. *"build a two-operator FM voice with
   carrier, ratio and depth controls"*, and watch the patch appear.
4. The **New** button starts a fresh conversation without touching the patch.

### Building reliably: `build_patch`

For building from scratch the in-Max chat exposes a declarative **`build_patch`**
tool: the model describes the whole graph — every object (id, type, args, an
optional one-line comment) and every connection (by id) — and the code does the
rest. It lays the patch out automatically from its topology (flow top to bottom,
parallel nodes side by side, comments in a side lane so cords never cross them),
wires everything by id, then **reads the patch back and reports any connection
that did not take**, so nothing fails silently. The model computes no
coordinates and tracks no auto-generated names. The unitary tools
(`create_object`, `connect`, ...) remain for editing a patch that already
exists.

### Running on a local model

The LLM backend is one function, `callLLM()` in `chat.js`. To run on a local
model (e.g. Gemma via `mlx_lm.server`, LM Studio or Ollama) instead of the
Anthropic API, point `api_url` at a local OpenAI-compatible endpoint and adjust
the request/response shape in that one function. The tool layer is unchanged.

The in-Max chat uses Anthropic API credits; external MCP clients use your Claude
plan.

## Patch read-back

`[v8 dump.js]` walks the top-level patcher and sends its full state (objects +
connections) to the agent.

- The dump returns every object (`varname`, `maxclass`, `text`, `rect`) and
  every connection, including objects the user added by hand.
- `max_verify` reports any server-created object missing from the patch, so the
  agent can rebuild it.

Objects related by **name** (e.g. `[buffer~ snd]` and `[record~ snd]`) are
linked by that shared name in their text, not by a patch cord — read the object
text, not just the connections, to see such relationships.

If text comes back empty, set `DEBUG = 1` at the top of `max/dump.js`, save, and
watch the Max Console on a bang.

## Patching conventions

The patch the agent builds follows a house style documented in
[`GUIDE.md`](GUIDE.md): decouple a parameter's value (a `number`/`flonum`) from
its trigger (a `button`), load a message through its right inlet rather than
`[prepend set]`, use `[trigger]` for ordering and fan-out, keep the signal path
vertical with `[dac~]` always connected, name objects and verify by reading
back, and respect a strict no-overlap layout. That same file is the single
source of truth fed to the model: `max_init` returns it on the MCP side, and the
in-Max chat uses it as its system prompt. Edit `GUIDE.md` to change how the agent
patches, on both facades at once.

## Configuration

### External server (environment variables)

| Variable          | Default     | Meaning |
| ----------------- | ----------- | ------- |
| `MAX_HOST`        | `127.0.0.1` | Where Max listens |
| `MAX_PORT`        | `7400`      | `[udpreceive]` port (writing) |
| `MAX_RETURN_PORT` | `7401`      | `[udpsend]` port (reading) |

Change a port in both the env var and the matching object in the host patch.

### In-Max chat (`max/chat.config.json`)

| Key                 | Default                | Meaning |
| ------------------- | ---------------------- | ------- |
| `anthropic_api_key` | —                      | your API key (file is git-ignored) |
| `model`             | `claude-sonnet-4-6`    | model id used by the chat |
| `api_url`           | Anthropic messages API | point at a local endpoint to use a local model |
| `max_tokens`        | `4096`                 | response budget per turn |
| `port`              | `5173`                 | local HTTP port the `[jweb]` UI connects to |

Copy `max/chat.config.example.json` to `max/chat.config.json` and edit. The real
config and the generated `maxmsp_mcp/objects.json` are both git-ignored.

## Testing

The OSC wire format, the read-back decoding, and the server bookkeeping are
covered by tests that run without Max (loopback UDP + a fake transport):

```bash
uv pip install pytest
uv run pytest -q
```

## Limitations

- **`max_send` is a stub.** `/send` currently prints to the Max Console. To drive
  a live `[receive <name>]`, wire `[forward]` off the `/send` outlet in
  `max/mcp_host.maxpat`.
- **Dumps are single-datagram.** Very large patches may exceed one UDP packet;
  chunking is planned.
- **The object database is local.** It is built from your Max install and not
  shipped; run `tools/build_maxref_db.py` once to enable `max_doc` /
  `lookup_object`.
- Objects created by hand have no scripting name, so they appear in dumps with a
  `#index` id and their text rather than a stable name.

## Author

Created by **Julien Bayle** — artist, **Ableton Certified Trainer** and **Max
Certified Trainer**.

- Art and audiovisual work: [julienbayle.net](http://julienbayle.net)
- **Structure Void** — Max/MSP, Ableton Live and creative-coding tools, tutorials
  and teaching: [structure-void.com](https://structure-void.com)

This project grows out of that teaching practice: it encodes a working trainer's
patching habits and the reflexes Max users are taught — name your objects, build
the value and its trigger separately, mind hot and cold inlets, read the patch
back — so an LLM builds patches the way a Max instructor would.

## License

MIT — see `LICENSE`. Copyright (c) Julien Bayle.
