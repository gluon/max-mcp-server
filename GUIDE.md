# maxmsp-mcp — patching guide

You build and drive a Max/MSP patch through tools. This guide is your single
source of truth: the wire model, the house patching style, an object
cheat-sheet, and a cookbook. Follow it over anything you might infer.

## How it works

- Every object you create gets a stable scripting **name** (`obj_0`, `obj_1`,
  ...), returned by the create call. You wire, set, and delete **by name**.
- Outlets and inlets are **0-indexed, left to right**, exactly as Max counts.
- Before extending or editing an existing patch, **read it back first** so you
  build on what is really there, including objects the user added by hand.
- **To build a patch from scratch, use `build_patch`.** Describe the whole
  graph — every object (with a short `id`, its `type` = the Max class itself
  such as `cycle~` or `*~`, never the literal word `object`; its `args`; and an
  optional `comment`) and every connection (by `id`). The code places everything
  automatically with no overlaps, wires it, verifies by reading back, and
  **reissues any missing connection itself** before reporting. You never compute
  coordinates. If the report still says "STILL MISSING", reissue only those
  specific connections with `connect` — **do NOT call `clear_canvas` and rebuild,
  and do not run `build_patch` again**, or you will create duplicate objects and
  lose any comments. Use the unitary tools only to edit a patch that already
  exists.
- **Name your objects.** When you create an object, pass a short meaningful
  `name` label (e.g. `freq`, `pack_main`, `carrier`) and connect using those
  labels. Do not try to track auto-generated `obj_N` names across many creates;
  that is where wiring goes wrong. A `connect` to an unknown name returns an
  error listing the names you have created — read it and correct the call.
- **No comma messages.** A message box created by these tools stores plain
  text; a comma becomes a literal character, not a Max message separator, and
  must never be escaped with a backslash. Do not build messages like
  `0, 1 20, 0 500`. For a `[line~]` envelope, use SEPARATE messages — e.g.
  `[1 20(` (ramp to 1 in 20 ms, the attack) and `[0 500(` (ramp to 0 in 500 ms,
  the release) — triggered in turn (the release after the attack, via a
  `[delay]` or on note-off).
- **Comments have no inlets or outlets.** Never connect anything to or from a
  comment. Do not create bare `set` messages that go nowhere.
- **When unsure of an object's signature** (inlet/outlet order, argument types,
  attribute names), **look it up** in the object reference rather than guessing.
  In particular, before connecting to an inlet other than 0, confirm the target
  actually has that inlet: a `[*~]` or `[dac~]` has only inlets 0 and 1, so
  connecting to inlet 2 silently fails.
- **Verify by reading back, as your final step.** A failed `connect` only logs
  to the Max console; the patch may be left incomplete. So after wiring any
  non-trivial patch, call `read_patch`, check that every connection you intended
  is present, and reissue any that are missing. Only then tell the user it is
  done.

## Max execution model (get this right)

- **Outlets fire right-to-left, depth-first.** When a single event must drive
  several actions in a defined order, do not rely on parallel cords. Use
  `[trigger]` (`t`) and remember its outlets fire right-to-left.
- **Hot vs cold inlets.** The leftmost inlet is usually *hot* (it triggers
  output); other inlets are *cold* (they store a value). Set cold inlets first,
  then send the hot (left) inlet last. This applies to `[+]`, `[*]`, `[pack]`,
  and most objects.

## House patching style (follow these)

1. **Decouple value from trigger.** For an adjustable parameter, use a
   `number` box (int) or `flonum` (float) for the VALUE and a separate
   `button`/bang for the TRIGGER. Do not use one message box that both stores
   and fires when the two should be independent. Example: a count lives in a
   `number`; a `button` fires the action.

2. **Load a message without firing it via its RIGHT inlet.** Connecting into a
   message box's right inlet (inlet 1) stores the content (like `set`) without
   output; the left inlet is what outputs. Prefer wiring into the right inlet
   over inserting a `[prepend set]` when you only need to store or display.

3. **Use `[trigger]`/`[t]` for ordering and fan-out**, not hopeful parallel
   cords. One bang into `[t b b b]` drives three things in a guaranteed order.

4. **Build lists** with `[pack]` (fixed arity, e.g. `pack i i i`) or
   `[zl group]` / `[zl.group]` (variable count). Display a list in a message via
   `[prepend set]` into the message, or by wiring into the message's right inlet.

5. **Signal vs control.** Tilde objects (`~`) carry audio signal; connect signal
   outlets to signal inlets. Output through `[dac~]`; for stereo, connect a gain
   `[*~]` to BOTH `[dac~]` inlets. Always start/stop global audio (DSP)
   explicitly, never assume it is running.

6. **Extrapolate musical intent.** "An arbitrary *number of* integers" means a
   variable count. "Arbitrary / random integers" means varied values, so reach
   for `[random]`, not `1..N`. Choose the musically useful reading.

7. **Arithmetic discipline.** `[+]`, `[*]`, `[scale]`, etc. compute when the
   left inlet receives input, using the value stored in the right inlet. Set the
   right inlet before banging the left.

## Layout (strict)

- **NEVER place an object on top of, or overlapping, another object or its
  comment.** You place objects blind (you cannot see the rendered canvas), so be
  generous: a typical object box is ~120 px wide and ~22 px tall, and a comment
  is ~150 px wide. Leave room for those widths.
- **Reserved zone — do not build here.** The machinery (`[p mcp_server]`,
  `[thispatcher]`), the header comment and the chat panel (`jweb`) occupy the
  top band and the whole left column. Build only in the open area: **x >= 480
  AND y >= 230**. Never place anything above y = 230 or left of x = 480.
- **Comments go ABOVE the object they label, never to its right.** Put the
  comment at the same x as the object and ~25 px above it (y_object - 25). A
  comment placed to the right collides with the next column. Keep comments to a
  few words.
- **Vertical chain:** objects wired in series share one x and step down by
  ~70 px (enough to fit each object's comment above it).
- **Parallel columns** (e.g. sequencer voices, a hot/cold pair) step across by
  **>= 220 px** so neither the objects nor their comments touch the next column.
- **Separate sections:** leave a >= 90 px vertical gap between independent
  blocks; if two blocks sit side by side, separate them by >= 320 px.
- Keep the signal/data flow vertical: source at top, `[dac~]` at the bottom.

## Object cheat-sheet

- Audio: `cycle~` (sine), `saw~`, `tri~`, `rect~`, `noise~`, `phasor~`, `*~`,
  `+~`, `sig~`, `line~`, `gain~`, `svf~`, `lores~`, `biquad~`, `delay~`,
  `tapin~`/`tapout~`, `dac~`, `adc~`, `buffer~`, `groove~`, `play~`, `record~`.
- Control: `metro`, `tempo`, `counter`, `uzi`, `trigger` (`t`), `sel`, `route`,
  `gate`, `switch`, `pack`, `unpack`, `zl` (`zl.group`, `zl.join`, `zl.rev`...),
  `pipe`, `delay`, `line`, `scale`, `expr`, `random`, `drunk`.
- UI: `number`, `flonum`, `toggle`, `button` (bang), `message`, `comment`,
  `slider`, `dial`, `live.dial`, `live.gain~`.

## Cookbook

- **Sine to the DAC:** `cycle~ 440` -> `*~ 0.2` -> `dac~` (wire the gain to both
  dac~ inlets), then start DSP.
- **N random ints on one bang:** `button` -> `t b b b` -> three `random 100` ->
  `pack i i i` -> `prepend set` -> `message`. The trigger fans out in order; pack
  collects right-to-left into a list.
- **Adjustable count, then fire:** a `number` (the count) wired into the RIGHT
  inlet of `uzi`; a `button` into the LEFT inlet of `uzi`; `uzi` -> `zl.group`
  -> `prepend set` -> `message`. Setting the count never fires; only the button
  does.
- **Two-operator FM:** the modulator's output is SCALED by depth and ADDED to
  the carrier frequency; it never replaces it. Chain:
  `cycle~` (modulator) -> `*~ <depth>` -> `+~ <carrier_freq>` -> `cycle~`
  (carrier) -> `*~ <amp>` -> `dac~`. The modulator frequency is
  `carrier_freq * ratio` (compute it and set the modulator's frequency). Use
  `number`/`flonum` boxes for carrier freq, ratio and depth.

## Reading the patch

- Reading the patch returns every object (name, class, text) and connection,
  including hand-added ones.
- Objects linked by **name** (e.g. `buffer~ snd`, `record~ snd`, `groove~ snd`)
  share that name in their *text*, not via a patch cord. Read the object text,
  not only the cords, to understand such relationships.
