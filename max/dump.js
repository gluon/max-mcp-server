// dump.js — patch reader for maxmsp-mcp (load in a [v8 dump.js] object).
// On bang (or "dump"), walks the host patcher and emits one OSC message:
//   /patch <json>
// wired to [udpsend 127.0.0.1 7401] so the Python server can read patch state.
//
// Uses the v8 JS API (confirmed against docs.cycling74.com/apiref/js):
//   - Maxobj.boxtext        -> the object box text (v8-only property)
//   - Maxobj.patchcords     -> { inputs, outputs } of MaxobjConnection
//   - MaxobjConnection      -> srcoutlet, dstobject, dstinlet
//
// Plumbing objects carry varnames starting with "mcp_" and are filtered out.

inlets = 1;
outlets = 1;

var DEBUG = 0; // set to 1 to post the JSON to the Max Console on each dump

function bang() { dump(); }
function msg_int() { dump(); }

function dump() {
    var p = this.patcher;
    if (!p) { post("dump.js: no patcher\n"); return; }

    var objects = [];
    var connections = [];
    var idx = 0;

    var o = p.firstobject;
    while (o) {
        var vn = varnameOf(o);
        if (vn.indexOf("mcp_") === 0) { o = o.nextobject; continue; }

        var myId = vn || ("#" + idx);
        objects.push({
            id: myId,
            varname: vn,
            maxclass: String(o.maxclass),
            text: boxText(o),
            rect: rectOf(o)
        });

        // outgoing cords from this object (each cord listed once, at its source)
        try {
            var pc = o.patchcords;
            if (pc && pc.outputs) {
                for (var k = 0; k < pc.outputs.length; k++) {
                    var c = pc.outputs[k];
                    var dvn = varnameOf(c.dstobject);
                    if (dvn.indexOf("mcp_") === 0) continue;
                    connections.push({
                        src: myId,
                        outlet: c.srcoutlet,
                        dst: dvn || boxHint(c.dstobject),
                        inlet: c.dstinlet
                    });
                }
            }
        } catch (e) {}

        idx++;
        o = o.nextobject;
    }

    var payload = JSON.stringify({ patcher: "top", objects: objects, lines: connections });
    if (DEBUG) post("dump:", payload, "\n");
    outlet(0, "/patch", payload);
}

function boxText(o) {
    try {
        var t = o.boxtext;          // correct v8 accessor
        if (t !== null && t !== undefined) return String(t);
    } catch (e) {}
    return "";
}

function boxHint(o) {
    var t = boxText(o);
    return t ? ("?" + t) : "?";
}

function varnameOf(o) {
    try { return (o && o.varname) ? String(o.varname) : ""; }
    catch (e) { return ""; }
}

function rectOf(o) {
    try {
        var r = o.rect;
        if (r instanceof Array) {
            return [Math.round(r[0]), Math.round(r[1]), Math.round(r[2]), Math.round(r[3])];
        }
    } catch (e) {}
    return [0, 0, 0, 0];
}
