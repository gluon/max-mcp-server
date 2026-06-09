// dump.js — patch reader for maxmsp-mcp (load in a [v8 dump.js] object).
// On bang (or "dump"), walks the TOP-LEVEL patcher and emits one OSC message:
//   /patch <json>
// wired to [udpsend 127.0.0.1 7401] so the server can read patch state.
//
// The [v8] may live inside the [p mcp-server] machinery subpatcher; we walk up
// to the top-level patcher, which is the workspace where objects are built
// (the top-level [thispatcher] creates them there).
//
// Uses the v8 JS API (docs.cycling74.com/apiref/js):
//   Maxobj.boxtext, Maxobj.patchcords ({inputs, outputs}), MaxobjConnection,
//   Patcher.parentpatcher.
//
// Plumbing carries varnames starting with "mcp_" and is filtered out.

inlets = 1;
outlets = 1;

var DEBUG = 0; // set to 1 to post the JSON to the Max Console on each dump

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
    if (DEBUG) post("dump:", payload, "\n");
    outlet(0, "/patch", payload);
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
