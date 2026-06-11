// dump.js — patch reader for maxmsp-mcp (load in a [v8 dump.js] object).
// On bang (or "dump"), walks the TOP-LEVEL patcher and emits one or more
// OSC messages carrying the full patch state as JSON.
//
// SMALL patches (≤ MAX_CHUNK bytes): single /patch <json> message.
// LARGE patches: /patch_chunk <index> <total> <partial_json> messages,
//   where total ≥ 2, indices 0..total-1, payloads concatenated reassemble
//   the full JSON string.
//
// Wiring in mcp_host.maxpat:
//   [v8 dump.js] -> [udpsend 127.0.0.1 7401]
//
// Uses the v8 JS API (docs.cycling74.com/apiref/js):
//   Maxobj.boxtext, Maxobj.patchcords ({inputs, outputs}), MaxobjConnection,
//   Patcher.parentpatcher.
//
// Plumbing carries varnames starting with "mcp_" and is filtered out.

inlets = 1;
outlets = 1;

var DEBUG = 0;       // set to 1 to post JSON to Max Console on each dump
var MAX_CHUNK = 56000;  // safe UDP payload — 56 KB leaves room for OSC framing

function bang() { dump(); }
function msg_int() { dump(); }

function dump() {
    var p = this.patcher;
    if (!p) { post("dump.js: no patcher\n"); return; }
    while (p.parentpatcher) { p = p.parentpatcher; }  // climb to top-level

    var objects = [];
    var connections = [];
    var idx = 0;

    var o = p.firstobject;
    while (o) {
        var vn = varnameOf(o);
        var txt = boxText(o);
        if (isPlumbing(o, vn, txt)) { o = o.nextobject; continue; }

        var myId = vn || ("#" + idx);
        objects.push({ id: myId, varname: vn, maxclass: String(o.maxclass), text: txt, rect: rectOf(o) });

        try {
            var pc = o.patchcords;
            if (pc && pc.outputs) {
                for (var k = 0; k < pc.outputs.length; k++) {
                    var c = pc.outputs[k];
                    var dvn = varnameOf(c.dstobject);
                    if (isPlumbing(c.dstobject, dvn, "")) continue;
                    connections.push({ src: myId, outlet: c.srcoutlet, dst: dvn || boxHint(c.dstobject), inlet: c.dstinlet });
                }
            }
        } catch (e) {}

        idx++;
        o = o.nextobject;
    }

    var payload = JSON.stringify({ patcher: "top", objects: objects, lines: connections });

    if (payload.length <= MAX_CHUNK) {
        if (DEBUG) post("dump:", payload.length, "bytes (single)\n");
        outlet(0, "/patch", payload);
    } else {
        var total = Math.ceil(payload.length / MAX_CHUNK);
        if (DEBUG) post("dump:", payload.length, "bytes,", total, "chunks\n");
        for (var i = 0; i < total; i++) {
            var chunk = payload.substring(i * MAX_CHUNK, (i + 1) * MAX_CHUNK);
            outlet(0, "/patch_chunk", i, total, chunk);
        }
    }
}

// Filter machinery: anything named mcp_*, and the [p mcp-server] subpatcher box.
function isPlumbing(o, vn, txt) {
    if (vn && vn.indexOf("mcp_") === 0) return true;
    try {
        if (String(o.maxclass) === "newobj") {
            var t = txt || boxText(o);
            if (t.indexOf("p mcp-server") === 0 || t.indexOf("p mcp") === 0) return true;
        }
    } catch (e) {}
    return false;
}

function boxText(o) {
    try { var t = o.boxtext; if (t !== null && t !== undefined) return String(t); } catch (e) {}
    return "";
}
function boxHint(o) { var t = boxText(o); return t ? ("?" + t) : "?"; }
function varnameOf(o) { try { return (o && o.varname) ? String(o.varname) : ""; } catch (e) { return ""; } }
function rectOf(o) {
    try { var r = o.rect; if (r instanceof Array) return [Math.round(r[0]), Math.round(r[1]), Math.round(r[2]), Math.round(r[3])]; }
    catch (e) {}
    return [0, 0, 0, 0];
}
