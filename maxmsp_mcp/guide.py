"""Orientation guide returned by max_init.

Single source of truth lives in GUIDE.md at the repo root (also read by the
in-Max chat and by humans). We load it at import; a short embedded fallback
keeps the server working if the file is not reachable (e.g. a minimal install).
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.join(_HERE, "..", "GUIDE.md"),   # repo checkout / editable install
    os.path.join(_HERE, "GUIDE.md"),         # packaged alongside the module
]

_FALLBACK = """\
MAX/MSP MCP — ORIENTATION (fallback; full guide in GUIDE.md)
- Objects are addressed by stable scripting names (obj_0, obj_1, ...).
- Wire, set and delete by name. Outlets/inlets are 0-indexed, left to right.
- Read the patch back before extending an existing one.
- Decouple value (number/flonum) from trigger (button); load a message via its
  right inlet rather than [prepend set]; use [trigger] for ordering and fan-out.
- Audio out is [dac~]; for stereo wire a gain [*~] to both inlets; start DSP.
- Place objects to the right of the chat panel (x >= ~460) so they are visible.
"""


def _load():
    for p in _CANDIDATES:
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return _FALLBACK


GUIDE = _load()
