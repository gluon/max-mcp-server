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
- **When unsure of an object's signature** (inlet/outlet order, argument types,
  attribute names), **look it up** in the object reference rather than guessing.
  In particular, before connecting to an inlet other than 0, confirm the target
  actually has that inlet: a `[*~]` or `[dac~]` has only inlets 0 and 1, so
  connecting to inlet 2 silently fails.
- **Verify by reading back.** A failed `connect` (wrong inlet index, or a target
  whose creation failed) only logs to the Max console; the tool result does not
  report it. So after wiring a non-trivial patch, call `read_patch`, compare the
  connections present against what you intended, and reissue any that are
  missing. Do not assume a connection succeeded just because the call returned.

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
