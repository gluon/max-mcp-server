---
name: maxmsp
description: >
  Build, wire, modify, read back, and play Max/MSP patches through the
  maxmsp-mcp server. Use when the user wants to create or edit a Max patch —
  synthesis (sine, FM, AM, subtractive, granular), audio routing, sequencing,
  control logic, MIDI, signal processing — or mentions Max, MSP, a .maxpat,
  thispatcher, or specific objects (cycle~, dac~, metro, groove~, ...). The host
  patch max/mcp_host.maxpat must be open in Max. Do NOT invoke for purely
  conceptual questions ("what is Max?", "Max vs Pd") — answer those directly.
---

# Max/MSP via maxmsp-mcp

You drive a running Max patch through the maxmsp-mcp tools. Objects you create
appear live on the canvas in `max/mcp_host.maxpat`, which the user keeps open.

## The one rule

**Call `max_init` before any other tool.** Every other tool refuses until you
do. `max_init` returns the orientation guide — wire model, naming contract,
object cheat sheet, cookbook, and the layout and style rules. That guide is the
authoritative source on conventions; this file only tells you *when* to reach
for the MCP and how to stay out of trouble.

## Prerequisites the user must satisfy

- **The host patch is open.** `max/mcp_host.maxpat` must be open in Max, and the
  `max/` folder on the Max search path (Options > File Preferences) so
  `[v8 dump.js]` resolves. If nothing appears in Max, this is almost always why.
- **Object reference (optional but recommended).** `max_doc` needs a local
  database built once from Max's own `.maxref.xml` files:
  `python tools/build_maxref_db.py /Applications/Max.app -o maxmsp_mcp/objects.json`.
  Without it, `max_doc` reports that no database is loaded; every other tool
  still works.

## Working rules

- **Address objects by their scripting name** (`obj_0`, `obj_1`, ...), returned
  by every create call. Wire, disconnect and delete by that name. Track the
  names you create; do not invent them.
- **When unsure of an object's signature** — inlet/outlet order, argument types,
  attribute names — call `max_doc <object>` instead of guessing. In particular,
  before connecting to an inlet other than 0, confirm the object has that inlet
  (`[*~]` and `[dac~]` have only inlets 0 and 1).
- **Build incrementally**, then **verify**: after wiring a non-trivial patch,
  call `max_dump_patch` (or `max_verify`) to confirm every connection took, and
  reissue any that are missing. A failed `connect` only logs to the Max Console;
  it does not come back as an error, so reading back is how you catch it.
- **Before extending an existing patch, read it back first** with
  `max_dump_patch` so you build on what is really there, including objects the
  user added by hand.
- **Lay out per the guide**, not by habit: build clear of the machinery (to the
  right of, and below, the chat panel and `[thispatcher]`), keep the signal flow
  vertical, and never overlap boxes. Follow the exact spacing in the guide
  returned by `max_init`.
- **Do not propose `mxj`-based solutions**, and do not write malicious or
  unsafe-loud audio (see below).

## Audio safety

Audio is loud and immediate. Never call `max_set_dsp(True)` until the signal
path is complete AND there is a gain stage (`[*~ 0.1]`–`[*~ 0.2]`) before
`[dac~]`. Connect the gain to BOTH `[dac~]` inlets for stereo. Never run an
open-ended source (`[noise~]`, a high-feedback loop) straight into `[dac~]`.

## Cookbook (full version in `max_init`)

- **Tone:** `[cycle~ 440]` -> `[*~ 0.2]` -> `[dac~]` (both inlets), then DSP on.
- **Two-operator FM:** modulator `[cycle~]` -> `[*~ depth]` -> `[+~ carrier_freq]`
  -> carrier `[cycle~]` -> `[*~ amp]` -> `[dac~]`. The modulator is ADDED to the
  carrier frequency, never substituted.
- **Sequencer:** `[metro ms]` -> `[counter 0 0 N]` -> `[sel 0 1 2 3]` ->
  message boxes of pitches -> `[cycle~]`.
- For fixed presets (pitches), prefer message boxes over number boxes: a number
  box loses its value on patch reload unless `loadbang`-ed.

## When something is off

- **Nothing appears in Max:** confirm `mcp_host.maxpat` is open and that the
  `[udpreceive]` port matches `MAX_PORT` (default 7400).
- **`max_doc` says no database:** the user has not built `objects.json` yet (see
  Prerequisites). Proceed without lookups, or ask them to build it.
- **A connection is missing after building:** you targeted an inlet that does not
  exist, or the object was not created. Read back with `max_dump_patch`, confirm
  the objects and inlet indices, and reissue.

## What this skill does NOT cover

- `mxj` / Java externals.
- Live message delivery to a named `[receive]` — `max_send` is currently a stub
  that prints to the Console.
- Parsing or editing `.maxpat` files on disk (the server talks only to the live
  open patch).
- Generating RNBO C++ or gen~ codegen.

For any of those, fall back to general knowledge and say it is out of scope.
