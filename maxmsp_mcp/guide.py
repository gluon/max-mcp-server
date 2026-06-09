"""Orientation guide returned by max_init: one server-authored source of truth
so the agent does not infer conventions from individual docstrings.
"""

GUIDE = """\
MAX/MSP MCP — ORIENTATION

You drive a running Max patch through [thispatcher] scripting messages, sent as
OSC over UDP into a vanilla [udpreceive] in the host patch (max/mcp_host.maxpat).
Open that patch in Max before doing anything.

ID CONTRACT
- Every object you create gets a stable scripting NAME (obj_0, obj_1, ...).
- You wire, disconnect and delete BY NAME, never by index. Names never drift,
  even if the user edits the patch by hand.

WIRE MODEL
- max_connect(from_name, outlet, to_name, inlet). Outlets/inlets are 0-indexed,
  left to right, exactly as Max counts them.
- Signal and control connections use the same call; Max infers the cord type.

OBJECT BASICS (Max class names)
- Audio: cycle~ (sine), saw~, tri~, rect~, noise~, *~ (gain), +~, dac~, adc~,
  gain~, line~, sig~, phasor~, svf~, lores~, biquad~, delay~, tapin~ / tapout~.
- Control: metro, toggle, button (bang), number (int), flonum (float),
  slider, message, comment, loadbang, t (trigger), sel, route, pack, line.
- A message box is class "message"; its content is the rest of the text.

COOKBOOK — 440 Hz sine to the DAC
  max_create_object("cycle~", ["440"], 40, 40)   -> obj_0
  max_create_object("*~", ["0.2"], 40, 90)       -> obj_1
  max_create_object("dac~", [], 40, 140)         -> obj_2
  max_connect("obj_0", 0, "obj_1", 0)
  max_connect("obj_1", 0, "obj_2", 0)            # left
  max_connect("obj_1", 0, "obj_2", 1)            # right
  max_set_dsp(True)

DRIVING A LIVE PATCH
- max_send(name, [args...]) forwards a message to a [receive <name>] / [r <name>]
  already present in the patch (via [forward] in the host patch).

SEEING THE PATCH (read-back, closed loop)
- max_dump_patch() returns every object and connection currently in the patch,
  INCLUDING objects the user added by hand. Use it before extending or editing
  an existing patch so you build on what is really there, not a guess.
- max_verify() dumps and checks that everything you created is actually present;
  recreate anything it reports as MISSING.
- Objects related by NAME (e.g. [buffer~ micbuf] and [record~ micbuf]) are linked
  by that shared name in their text, not by a patch cord. Read the object text,
  not just the connections, to understand such relationships.

SAFETY / NOTES
- max_clear_canvas deletes every object THIS server created (one script delete
  per name). Objects the user made by hand are untouched.
- Prefer small, named, readable graphs. Lay objects out on a grid (x steps of
  ~160, y steps of ~50) so the result is legible to a human in Max.
- Do not suggest mxj-based objects.
"""
