---
name: maxmsp
description: Build and drive Max/MSP patches programmatically through the maxmsp-mcp server. Use when the user wants to create, wire, modify, or play a Max patch - synthesis, audio routing, MIDI, control logic, signal processing - or mentions Max, MSP, cycle~, thispatcher, or a .maxpat. Requires max/mcp_host.maxpat open in Max.
---

# Max/MSP via maxmsp-mcp

Drive a running Max patch through the maxmsp-mcp tools. The host patch
(`max/mcp_host.maxpat`) must be open in Max.

## Always start here

Call `max_init` before anything else. It returns the orientation guide (wire
model, naming contract, object cheat sheet, cookbook) and unlocks the other
tools. Treat that guide as authoritative.

## Working rules

- Objects are addressed by stable scripting **names** (`obj_0`, `obj_1`, ...),
  returned by every create call. Wire, disconnect and delete by name.
- Lay objects on a grid (x ~160 apart, y ~50 apart) so the patch stays readable
  to a human in Max.
- Build incrementally: create, wire, then `max_set_dsp(True)` only when the
  signal path reaches a `[dac~]`.
- Do not propose mxj-based solutions.

## Common signal path

`cycle~ 440` -> `*~ 0.2` -> `dac~` (connect the gain to both `dac~` inlets for
stereo), then `max_set_dsp(True)`.

## When something is off

If nothing appears in Max, confirm `mcp_host.maxpat` is open and that the
`[udpreceive]` port matches `MAX_PORT` (default 7400).
