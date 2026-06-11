"""Patch templates for maxmsp-mcp.

Each template is a pre-built patch graph (objects + connections) that
can be instantiated via max_apply_template(). Templates use the same
format as max_build_patch's objects/connections lists.
"""
from __future__ import annotations

import time as _time
from copy import deepcopy
from typing import Any, Dict, List, Optional


# ── Template type ──────────────────────────────────────────────────────

PatchTemplate = Dict[str, Any]  # {objects: [...], connections: [...], params: {...}}


def _param(val, desc: str):
    """Declare a template parameter with default value and description."""
    return {"default": val, "description": desc}


# ── Built-in Templates ─────────────────────────────────────────────────

TEMPLATES: dict[str, dict] = {}
"""Registry: name -> {objects, connections, params, description}"""


def register(name: str, objects: list, connections: list,
             params: dict = None, description: str = ""):
    """Register a template."""
    TEMPLATES[name] = {
        "objects": objects,
        "connections": connections,
        "params": params or {},
        "description": description,
    }


# ── Individual Templates ───────────────────────────────────────────────

register(
    name="simple_synth",
    description="A simple monophonic synthesizer: oscillator → envelope → VCA → output",
    params={
        "freq": _param(440, "Carrier frequency in Hz"),
        "waveform": _param("saw", "Oscillator waveform: saw, tri, rect, noise"),
        "amplitude": _param(0.3, "Output amplitude 0-1"),
    },
    objects=[
        {"id": "osc", "type": "saw~", "args": [440], "comment": "oscillator"},
        {"id": "vca", "type": "*~",   "args": [],    "comment": "amplitude VCA"},
        {"id": "gain","type": "*~",   "args": [],    "comment": "output gain (cold)"},
        {"id": "env", "type": "line~","args": [],    "comment": "amplitude envelope"},
        {"id": "trig","type": "button","args": [],   "comment": "trigger note on"},
        {"id": "rel", "type": "button","args": [],   "comment": "trigger note off"},
        {"id": "att", "type": "flonum","args": [50], "comment": "attack ms"},
        {"id": "dec", "type": "flonum","args": [200],"comment": "decay ms"},
        {"id": "amp", "type": "flonum","args": [0.3],"comment": "amplitude 0-1"},
        {"id": "dac", "type": "dac~",  "args": [1, 2],"comment": "output"},
        {"id": "msg_on", "type": "message","text": "1 50",     "comment": "note on envelope"},
        {"id": "msg_off","type": "message","text": "0 500",    "comment": "note off envelope"},
    ],
    connections=[
        {"from": "osc",   "outlet": 0, "to": "vca",   "inlet": 0},
        {"from": "vca",   "outlet": 0, "to": "gain",  "inlet": 0},
        {"from": "gain",  "outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "gain",  "outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "env",   "outlet": 0, "to": "vca",   "inlet": 1},
        {"from": "amp",   "outlet": 0, "to": "gain",  "inlet": 1},
        {"from": "trig",  "outlet": 0, "to": "msg_on","inlet": 0},
        {"from": "rel",   "outlet": 0, "to": "msg_off","inlet": 0},
        {"from": "msg_on","outlet": 0, "to": "env",   "inlet": 0},
        {"from": "msg_off","outlet":0, "to": "env",   "inlet": 0},
    ],
)


register(
    name="simple_delay",
    description="Mono delay: input → delay buffer → mix dry/wet → output",
    params={
        "delay_time": _param(500, "Delay time in ms"),
        "feedback": _param(0.35, "Feedback amount 0-1"),
        "wet_level": _param(0.5, "Wet level 0-1"),
    },
    objects=[
        {"id": "adc",    "type": "adc~",  "args": [1],      "comment": "audio input"},
        {"id": "in_gn",  "type": "*~",    "args": [],       "comment": "input gain"},
        {"id": "mix",    "type": "+~",    "args": [],       "comment": "dry + feedback"},
        {"id": "tapin",  "type": "tapin~","args": [],       "comment": "delay write"},
        {"id": "tapout", "type": "tapout~","args": [],      "comment": "delay read"},
        {"id": "fb_gn",  "type": "*~",    "args": [],       "comment": "feedback (cold)"},
        {"id": "wet_gn", "type": "*~",    "args": [],       "comment": "wet level (cold)"},
        {"id": "dry_gn", "type": "*~",    "args": [],       "comment": "dry level (cold)"},
        {"id": "sum",    "type": "+~",    "args": [],       "comment": "dry + wet"},
        {"id": "out_gn", "type": "*~",    "args": [],       "comment": "output gain"},
        {"id": "dac",    "type": "dac~",  "args": [1, 2],   "comment": "stereo out"},
        {"id": "dly_t",  "type": "flonum","args": [500],    "comment": "delay ms"},
        {"id": "fb_a",   "type": "flonum","args": [0.35],   "comment": "feedback"},
        {"id": "wet",    "type": "flonum","args": [0.5],    "comment": "wet"},
        {"id": "dry",    "type": "flonum","args": [0.5],    "comment": "dry"},
        {"id": "in_l",   "type": "flonum","args": [0.8],    "comment": "input gain"},
        {"id": "out_l",  "type": "flonum","args": [0.75],   "comment": "output gain"},
    ],
    connections=[
        {"from": "adc",   "outlet": 0, "to": "in_gn", "inlet": 0},
        {"from": "adc",   "outlet": 0, "to": "dry_gn","inlet": 0},
        {"from": "in_gn", "outlet": 0, "to": "mix",   "inlet": 0},
        {"from": "mix",   "outlet": 0, "to": "tapin", "inlet": 0},
        {"from": "tapout","outlet": 0, "to": "fb_gn", "inlet": 0},
        {"from": "fb_gn", "outlet": 0, "to": "mix",   "inlet": 1},
        {"from": "tapout","outlet": 0, "to": "wet_gn","inlet": 0},
        {"from": "wet_gn","outlet": 0, "to": "sum",   "inlet": 1},
        {"from": "dry_gn","outlet": 0, "to": "sum",   "inlet": 0},
        {"from": "sum",   "outlet": 0, "to": "out_gn","inlet": 0},
        {"from": "out_gn","outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "out_gn","outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "dly_t", "outlet": 0, "to": "tapout","inlet": 0},
        {"from": "fb_a",  "outlet": 0, "to": "fb_gn", "inlet": 1},
        {"from": "wet",   "outlet": 0, "to": "wet_gn","inlet": 1},
        {"from": "dry",   "outlet": 0, "to": "dry_gn","inlet": 1},
        {"from": "in_l",  "outlet": 0, "to": "in_gn", "inlet": 1},
        {"from": "out_l", "outlet": 0, "to": "out_gn","inlet": 1},
    ],
)


register(
    name="lowpass_filter",
    description="State-variable lowpass filter: input → svf~ → output with cutoff + resonance",
    params={
        "cutoff": _param(2000, "Cutoff frequency in Hz"),
        "resonance": _param(0.5, "Resonance 0-1"),
    },
    objects=[
        {"id": "in",    "type": "in~",   "args": [],        "comment": "signal input"},
        {"id": "svf",   "type": "svf~",  "args": [],        "comment": "multimode filter"},
        {"id": "gain",  "type": "*~",    "args": [],        "comment": "output gain"},
        {"id": "dac",   "type": "dac~",  "args": [1, 2],    "comment": "output"},
        {"id": "freq",  "type": "flonum","args": [2000],    "comment": "cutoff Hz"},
        {"id": "res",   "type": "flonum","args": [0.5],     "comment": "resonance"},
        {"id": "out_l", "type": "flonum","args": [0.7],     "comment": "output level"},
    ],
    connections=[
        {"from": "in",   "outlet": 0, "to": "svf",   "inlet": 0},
        {"from": "svf",  "outlet": 0, "to": "gain",  "inlet": 0},  # outlet 0 = lowpass
        {"from": "gain", "outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "gain", "outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "freq", "outlet": 0, "to": "svf",   "inlet": 1},
        {"from": "res",  "outlet": 0, "to": "svf",   "inlet": 2},
        {"from": "out_l","outlet": 0, "to": "gain",  "inlet": 1},
    ],
)


register(
    name="tremolo",
    description="Amplitude modulation: slow LFO → VCA for rhythmic volume changes",
    params={
        "rate": _param(5, "Tremolo rate in Hz"),
        "depth": _param(0.7, "Modulation depth 0-1"),
    },
    objects=[
        {"id": "lfo",   "type": "cycle~","args": [5],      "comment": "LFO oscillator"},
        {"id": "dc",    "type": "+~",    "args": [],        "comment": "bias + depth"},
        {"id": "amt",   "type": "*~",    "args": [],        "comment": "depth (cold)"},
        {"id": "vca",   "type": "*~",    "args": [],        "comment": "VCA: signal * mod"},
        {"id": "sig",   "type": "in~",   "args": [],        "comment": "audio input"},
        {"id": "out",   "type": "*~",    "args": [],        "comment": "output gain"},
        {"id": "dac",   "type": "dac~",  "args": [1, 2],    "comment": "output"},
        {"id": "rt",    "type": "flonum","args": [5],       "comment": "rate Hz"},
        {"id": "dp",    "type": "flonum","args": [0.7],     "comment": "depth"},
        {"id": "lv",    "type": "flonum","args": [0.8],     "comment": "output level"},
        {"id": "bias",  "type": "flonum","args": [0.5],     "comment": "DC bias 0.5"},
    ],
    connections=[
        {"from": "sig",  "outlet": 0, "to": "vca",   "inlet": 0},
        {"from": "lfo",  "outlet": 0, "to": "amt",   "inlet": 0},
        {"from": "amt",  "outlet": 0, "to": "dc",    "inlet": 0},
        {"from": "bias", "outlet": 0, "to": "dc",    "inlet": 1},
        {"from": "dc",   "outlet": 0, "to": "vca",   "inlet": 1},
        {"from": "vca",  "outlet": 0, "to": "out",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "rt",   "outlet": 0, "to": "lfo",   "inlet": 0},
        {"from": "dp",   "outlet": 0, "to": "amt",   "inlet": 1},
        {"from": "lv",   "outlet": 0, "to": "out",   "inlet": 1},
    ],
)


register(
    name="noise_gate",
    description="Noise gate: input → compare with threshold → gate → output",
    params={
        "threshold": _param(0.05, "Gate threshold 0-1"),
        "attack": _param(5, "Attack time in ms"),
        "release": _param(100, "Release time in ms"),
    },
    objects=[
        {"id": "in",    "type": "in~",   "args": [],        "comment": "audio input"},
        {"id": "abs",   "type": "+~",    "args": [],        "comment": "abs value"},
        {"id": "comp",  "type": ">~",    "args": [],        "comment": "compare > threshold"},
        {"id": "smt",   "type": "line~", "args": [],        "comment": "smooth transitions"},
        {"id": "vca",   "type": "*~",    "args": [],        "comment": "gate VCA"},
        {"id": "out",   "type": "*~",    "args": [],        "comment": "output gain"},
        {"id": "dac",   "type": "dac~",  "args": [1, 2],    "comment": "output"},
        {"id": "thr",   "type": "flonum","args": [0.05],    "comment": "threshold"},
        {"id": "atk",   "type": "flonum","args": [5],       "comment": "attack ms"},
        {"id": "rel",   "type": "flonum","args": [100],     "comment": "release ms"},
        {"id": "lv",    "type": "flonum","args": [0.8],     "comment": "output level"},
    ],
    connections=[
        {"from": "in",   "outlet": 0, "to": "abs",   "inlet": 0},
        {"from": "in",   "outlet": 0, "to": "vca",   "inlet": 0},
        {"from": "abs",  "outlet": 0, "to": "comp",  "inlet": 0},
        {"from": "thr",  "outlet": 0, "to": "comp",  "inlet": 1},
        {"from": "comp", "outlet": 0, "to": "smt",   "inlet": 0},
        {"from": "smt",  "outlet": 0, "to": "vca",   "inlet": 1},
        {"from": "vca",  "outlet": 0, "to": "out",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "lv",   "outlet": 0, "to": "out",   "inlet": 1},
    ],
)


register(
    name="ring_modulator",
    description="Ring modulation: audio * carrier = sum & difference frequencies",
    params={
        "carrier_freq": _param(440, "Carrier oscillator frequency in Hz"),
        "mix": _param(0.5, "Dry/wet mix 0-1"),
    },
    objects=[
        {"id": "car",   "type": "cycle~","args": [440],    "comment": "carrier osc"},
        {"id": "rm",    "type": "*~",    "args": [],        "comment": "ring mod *~"},
        {"id": "dry_g", "type": "*~",    "args": [],        "comment": "dry level (cold)"},
        {"id": "sum",   "type": "+~",    "args": [],        "comment": "dry + wet"},
        {"id": "out",   "type": "*~",    "args": [],        "comment": "output gain"},
        {"id": "in",    "type": "in~",   "args": [],        "comment": "audio input"},
        {"id": "dac",   "type": "dac~",  "args": [1, 2],    "comment": "output"},
        {"id": "freq",  "type": "flonum","args": [440],     "comment": "carrier freq"},
        {"id": "mix",   "type": "flonum","args": [0.5],     "comment": "dry/wet mix"},
        {"id": "lv",    "type": "flonum","args": [0.7],     "comment": "output level"},
    ],
    connections=[
        {"from": "in",   "outlet": 0, "to": "rm",    "inlet": 0},
        {"from": "in",   "outlet": 0, "to": "dry_g", "inlet": 0},
        {"from": "car",  "outlet": 0, "to": "rm",    "inlet": 1},
        {"from": "rm",   "outlet": 0, "to": "sum",   "inlet": 1},
        {"from": "dry_g","outlet": 0, "to": "sum",   "inlet": 0},
        {"from": "sum",  "outlet": 0, "to": "out",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 0},
        {"from": "out",  "outlet": 0, "to": "dac",   "inlet": 1},
        {"from": "freq", "outlet": 0, "to": "car",   "inlet": 0},
        {"from": "mix",  "outlet": 0, "to": "dry_g", "inlet": 1},
        {"from": "lv",   "outlet": 0, "to": "out",   "inlet": 1},
    ],
)


# ── Apply a template ───────────────────────────────────────────────────

def apply(template_name: str, params: dict = None,
          x: int = 480, y: int = 240,
          title: str = "") -> dict:
    """Resolve a template with given params and return {objects, connections}.

    - template_name: registered template name (e.g. 'simple_delay')
    - params: overrides for template parameters {name: value}
    - x, y: starting position for auto-layout
    - title: optional patch title

    Returns a dict ready for max_build_patch(objects=..., connections=...).
    """
    tmpl = TEMPLATES.get(template_name)
    if not tmpl:
        raise ValueError(f"Unknown template '{template_name}'. "
                         f"Available: {sorted(TEMPLATES.keys())}")

    objects = deepcopy(tmpl["objects"])
    connections = deepcopy(tmpl["connections"])
    merged_params = {}
    for k, v in tmpl.get("params", {}).items():
        merged_params[k] = v["default"] if isinstance(v, dict) else v
    if params:
        merged_params.update(params)

    # Apply parameter overrides to flonum args
    for obj in objects:
        oid = obj.get("id", "")
        if oid in merged_params:
            param_val = merged_params[oid]
            if obj.get("type") in ("flonum", "number", "cycle~",
                                    "saw~", "tri~", "rect~"):
                obj["args"] = [param_val]

    result = {
        "objects": objects,
        "connections": connections,
    }
    if title:
        result["title"] = title
    return result


def list_templates() -> list:
    """Return list of {name, description, params} for all templates."""
    result = []
    for name, tmpl in sorted(TEMPLATES.items()):
        params_list = []
        for pname, pinfo in tmpl.get("params", {}).items():
            params_list.append(f"{pname}={pinfo.get('default', '?')} ({pinfo.get('description', '')})")
        result.append({
            "name": name,
            "description": tmpl.get("description", ""),
            "params": params_list,
            "object_count": len(tmpl.get("objects", [])),
            "connection_count": len(tmpl.get("connections", [])),
        })
    return result
