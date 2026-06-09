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

- **NEVER place an object on top of, or overlapping, another object.** Before
  choosing a position, account for each object's width and height and leave a
  clear gap. Overlapping boxes are the worst possible output.
- **Keep clear of the machinery.** The top-left area holds `[p mcp_server]`,
  `[thispatcher]`, the chat panel (`jweb`) and comments. Build your patch in the
  open area to the **right** of the chat panel: start at **x >= 480**, and do
  not place anything in the top band where the machinery sits.
- Use a **regular grid**: a vertical step of **~45 px** between objects chained
  in series, and a horizontal step of **~150 px** between parallel columns
  (e.g. the voices of a sequencer side by side). Align to multiples of 15 px.
- Keep the signal/data flow vertical: source at top, `[dac~]` at the bottom.
- Comment a section with a `[comment]` placed **beside or above** the block it
  labels, never overlapping an object.

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
