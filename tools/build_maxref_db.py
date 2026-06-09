#!/usr/bin/env python3
"""Build a curated object database from Max's .maxref.xml reference files.

Max ships a structured doc file for every object. This parser walks one or more
root folders, extracts each object's signature (arguments, inlets, outlets,
attributes, messages) and writes maxmsp_mcp/objects.json, which the max_doc tool
serves so the model looks up signatures instead of guessing.

Handles both the standard Max/MSP schema (<inletlist>, <outletlist>,
<attributelist>, <methodlist>, <objarglist>) and the RNBO schema
(<rnboinletlist>, <rnbooutletlist>, <rnboattributelist>).

Usage:
    python tools/build_maxref_db.py ROOT [ROOT ...] [-o OUT] [--core-only]

Example (core Max objects only, clean for publishing):
    python tools/build_maxref_db.py \
        "/Applications/Max.app/Contents/Resources/C74/docs/refpages" \
        --core-only -o maxmsp_mcp/objects.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

CORE_MODULES = {"Max", "MSP", "Jitter", "max", "msp", "jitter"}


def _text(elem) -> str:
    if elem is None:
        return ""
    s = "".join(elem.itertext())
    return re.sub(r"\s+", " ", s).strip()


def _find(parent, *tags):
    """First child matching any of the given tag names (schema variants)."""
    for t in tags:
        e = parent.find(t)
        if e is not None:
            return e
    return None


def _entries(parent, list_tags, item_tag):
    container = _find(parent, *list_tags)
    if container is None:
        return []
    out = []
    for item in container.findall(item_tag):
        name = item.get("name") or item.get("id") or ""
        entry = {"name": name, "type": item.get("type", "")}
        if item.get("optional"):
            entry["optional"] = item.get("optional") == "1"
        digest = item.find("digest")
        entry["digest"] = _text(digest) if digest is not None else ""
        out.append(entry)
    return out


def parse_file(path: str):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    if root.tag != "c74object":
        return None
    name = root.get("name") or os.path.basename(path).replace(".maxref.xml", "")
    name = re.sub(r"^rnbo_", "", name)
    digest = root.find("digest")
    desc = root.find("description")
    return {
        "name": name,
        "module": root.get("module", ""),
        "category": root.get("category", ""),
        "kind": root.get("kind", ""),
        "digest": _text(digest) if digest is not None else "",
        "description": _text(desc) if desc is not None else "",
        "args": _entries(root, ["objarglist"], "objarg"),
        "inlets": _entries(root, ["inletlist", "rnboinletlist"], "inlet"),
        "outlets": _entries(root, ["outletlist", "rnbooutletlist"], "outlet"),
        "attributes": _entries(root, ["attributelist", "rnboattributelist"], "attribute"),
        "messages": _entries(root, ["methodlist"], "method"),
        "_path": path,
    }


def _score(obj) -> int:
    """Higher wins when the same object name appears in several files."""
    s = 0
    if obj.get("module") in CORE_MODULES:
        s += 10
    if obj.get("kind") != "rnboobject":
        s += 3
    if "/refpages/max-ref/" in obj["_path"] or "/refpages/msp-ref/" in obj["_path"]:
        s += 5
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build objects.json from .maxref.xml files")
    ap.add_argument("roots", nargs="+", help="folders to scan recursively")
    ap.add_argument("-o", "--out", default="maxmsp_mcp/objects.json")
    ap.add_argument("--core-only", action="store_true",
                    help="keep only Max/MSP/Jitter modules (clean for publishing)")
    args = ap.parse_args(argv)

    best = {}
    files = 0
    for r in args.roots:
        for dirpath, _, filenames in os.walk(r):
            for fn in filenames:
                if fn.endswith(".maxref.xml"):
                    files += 1
                    obj = parse_file(os.path.join(dirpath, fn))
                    if not obj or not obj["name"]:
                        continue
                    if args.core_only and obj.get("module") not in CORE_MODULES:
                        continue
                    cur = best.get(obj["name"])
                    if cur is None or _score(obj) > _score(cur):
                        best[obj["name"]] = obj

    for o in best.values():
        o.pop("_path", None)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(best, f, ensure_ascii=False, indent=0, sort_keys=True)

    print(f"scanned {files} files -> {len(best)} unique objects -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
