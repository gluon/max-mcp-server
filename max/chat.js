// chat.js — in-Max chat backend for maxmsp-mcp (load in [node.script chat.js]).
//
// Runs entirely inside Max via Node for Max. It:
//   1. serves a small chat UI over local HTTP (jweb points at it),
//   2. talks to an LLM backend (Anthropic by default; swap the URL/headers in
//      callLLM() for a local Gemma OpenAI-compatible endpoint),
//   3. executes the model's tool calls by emitting commands out its Max outlet,
//      wired to the same [route] -> [thispatcher] plumbing the patch already has,
//   4. can read the live patch back by triggering [v8 dump.js] and awaiting the
//      /patch reply on its inlet.
//
// The API key lives in chat.config.json (gitignored), never in the repo.

const Max = require("max-api");
const http = require("http");
const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const DEFAULTS = {
    port: 5173,
    model: "claude-sonnet-4-20250514",
    max_tokens: 4096,
    anthropic_api_key: "",
    api_url: "https://api.anthropic.com/v1/messages",
    anthropic_version: "2023-06-01",
};

function loadConfig() {
    const p = path.join(__dirname, "chat.config.json");
    try {
        const cfg = JSON.parse(fs.readFileSync(p, "utf8"));
        return Object.assign({}, DEFAULTS, cfg);
    } catch (e) {
        Max.post("chat.js: no chat.config.json found next to the script. " +
                 "Copy chat.config.example.json to chat.config.json and add your API key.");
        return Object.assign({}, DEFAULTS);
    }
}
const CONFIG = loadConfig();

// Object reference database (built by tools/build_maxref_db.py). Optional.
let OBJ_DB = null;
function objDb() {
    if (OBJ_DB === null) {
        const candidates = [
            path.join(__dirname, "..", "maxmsp_mcp", "objects.json"),
            path.join(__dirname, "objects.json"),
        ];
        OBJ_DB = {};
        for (const c of candidates) {
            try { OBJ_DB = JSON.parse(fs.readFileSync(c, "utf8")); break; } catch (e) {}
        }
    }
    return OBJ_DB;
}
function formatDoc(o) {
    const out = [(o.name + " - " + (o.digest || "")).replace(/ -\s*$/, "")];
    const block = (title, items) => {
        if (!items || !items.length) return;
        out.push(title + ":");
        items.forEach((it, i) => {
            const t = it.type ? " [" + it.type + "]" : "";
            const d = it.digest ? " - " + it.digest : "";
            out.push("  " + i + ": " + (it.name || i) + t + d);
        });
    };
    block("args", o.args); block("inlets", o.inlets); block("outlets", o.outlets);
    block("attributes", o.attributes); block("messages", o.messages);
    return out.join("\n");
}

// ---------------------------------------------------------------------------
// Patch state (stable scripting names, mirrors the Python server)
// ---------------------------------------------------------------------------
let counter = 0;
// Registry of objects created this session. Keyed by BOTH the model's chosen
// label (if any) and the scripting name, so connect/delete resolve either.
// Value: { name: <scripting name>, maxclass }.
const nodes = new Map();
function nextName(prefix) { return prefix + "_" + (counter++); }
function register(scriptName, maxclass, label) {
    const rec = { name: scriptName, maxclass: maxclass };
    if (label && label !== scriptName) nodes.set(label, rec);
    nodes.set(scriptName, rec);
    return rec;
}
function resolve(key) { return nodes.get(String(key)); }
function knownLabels() {
    const seen = new Set(), out = [];
    for (const [k, v] of nodes) { if (!seen.has(v.name)) { seen.add(v.name); out.push(k); } }
    return out;
}

// ---------------------------------------------------------------------------
// Reading the patch: trigger [v8 dump.js], await the /patch reply
// ---------------------------------------------------------------------------
let pendingDump = null;
Max.addHandler("/patch", (jsonStr) => {
    if (pendingDump) { const r = pendingDump; pendingDump = null; r(jsonStr); }
});
function readPatch(timeoutMs) {
    return new Promise((resolve) => {
        let done = false;
        pendingDump = (s) => { if (!done) { done = true; resolve(s); } };
        Max.outlet("/dump");
        setTimeout(() => { if (!done) { done = true; pendingDump = null; resolve('{"objects":[],"lines":[]}'); } }, timeoutMs || 1500);
    });
}

// ---------------------------------------------------------------------------
// Tools exposed to the model (mirror the build tools; executed via Max.outlet)
// ---------------------------------------------------------------------------
const TOOLS = [
    { name: "build_patch", description: "Build a whole patch at once from a graph. The CODE lays everything out automatically (no overlaps, flow top-to-bottom) and wires it, then verifies and reports any connection that did not take. PREFER this to build a patch from scratch; you supply no coordinates. Use the unitary tools only to edit an already-existing patch.",
      input_schema: { type: "object", properties: {
          objects: { type: "array", description: "every box to create", items: { type: "object", properties: {
              id: { type: "string", description: "your label, referenced in connections" },
              type: { type: "string", description: "maxclass: cycle~, *~, +~, dac~, metro, counter, sel, number, flonum, message, button, toggle, ..." },
              args: { type: "array", items: { type: "string" }, description: "typed-in arguments (for object boxes)" },
              text: { type: "string", description: "content (for type 'message' or 'comment')" },
              comment: { type: "string", description: "optional short annotation, shown in a side lane" } },
              required: ["id", "type"] } },
          connections: { type: "array", description: "wires, by id", items: { type: "object", properties: {
              from: { type: "string" }, outlet: { type: "integer" }, to: { type: "string" }, inlet: { type: "integer" } },
              required: ["from", "to"] } },
          title: { type: "string", description: "optional title comment at the top" } },
          required: ["objects"] } },
    { name: "create_object", description: "Create a Max object box [maxclass args...] at (x,y). Pass a short label in `name` (e.g. 'freq', 'pack_main') and use that same label when connecting. Returns the label.",
      input_schema: { type: "object", properties: {
          maxclass: { type: "string", description: "e.g. cycle~, *~, dac~, metro" },
          args: { type: "array", items: { type: "string" }, description: "typed-in arguments" },
          name: { type: "string", description: "your label to refer to this object later" },
          x: { type: "integer" }, y: { type: "integer" } }, required: ["maxclass"] } },
    { name: "create_message", description: "Create a message box with the given content at (x,y). Pass a label in `name` to refer to it later.",
      input_schema: { type: "object", properties: {
          text: { type: "string" }, name: { type: "string", description: "your label" },
          x: { type: "integer" }, y: { type: "integer" } }, required: ["text"] } },
    { name: "create_comment", description: "Create a comment (label text) at (x,y). A comment has NO inlets or outlets; never connect anything to or from it. Place it ABOVE the object it labels.",
      input_schema: { type: "object", properties: {
          text: { type: "string" }, name: { type: "string", description: "your label" },
          x: { type: "integer" }, y: { type: "integer" } }, required: ["text"] } },
    { name: "connect", description: "Wire from_name:outlet -> to_name:inlet (0-indexed, left to right). Use the labels you gave when creating the objects.",
      input_schema: { type: "object", properties: {
          from_name: { type: "string" }, outlet: { type: "integer" },
          to_name: { type: "string" }, inlet: { type: "integer" } },
          required: ["from_name", "outlet", "to_name", "inlet"] } },
    { name: "disconnect", description: "Remove a connection from_name:outlet -> to_name:inlet.",
      input_schema: { type: "object", properties: {
          from_name: { type: "string" }, outlet: { type: "integer" },
          to_name: { type: "string" }, inlet: { type: "integer" } },
          required: ["from_name", "outlet", "to_name", "inlet"] } },
    { name: "delete_object", description: "Delete a single object by name.",
      input_schema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] } },
    { name: "set_dsp", description: "Start or stop global audio DSP.",
      input_schema: { type: "object", properties: { on: { type: "boolean" } }, required: ["on"] } },
    { name: "read_patch", description: "Read the live patch: every object (name, class, text) and connection, including hand-added objects. Use before extending an existing patch.",
      input_schema: { type: "object", properties: {} } },
    { name: "clear_canvas", description: "Delete every object this session created.",
      input_schema: { type: "object", properties: {} } },
    { name: "lookup_object", description: "Look up an object's official reference (arguments, inlets, outlets, attributes, messages). Call this whenever unsure of a signature instead of guessing.",
      input_schema: { type: "object", properties: { name: { type: "string", description: "the Max object name, e.g. groove~" } }, required: ["name"] } },
];

// Numeric tokens must reach Max as ints/floats, not quoted symbols, or a
// message like [262] becomes ["262"] and won't drive a [cycle~].
function atomize(tokens) {
    return tokens.map((t) => {
        if (typeof t !== "string") return t;
        if (/^-?\d+$/.test(t)) return parseInt(t, 10);
        if (/^-?\d*\.\d+$/.test(t)) return parseFloat(t);
        return t;
    });
}

// Deterministic layout: lay objects out by graph topology so signal/data flows
// top-to-bottom, parallel nodes sit side by side, and nothing overlaps. The
// model no longer computes any coordinate. Per-object comments go in a side
// lane to the right so cords never cross them.
function layoutGraph(objects, connections, opts) {
    const X0 = (opts && opts.x0) || 480;
    const Y0 = (opts && opts.y0) || 240;
    const COL = 200, ROW = 80;
    const ids = objects.map((o) => o.id);
    const idset = new Set(ids);
    const indeg = new Map(ids.map((i) => [i, 0]));
    const adj = new Map(ids.map((i) => [i, []]));
    connections.forEach((c) => {
        if (idset.has(c.from) && idset.has(c.to) && c.from !== c.to) {
            adj.get(c.from).push(c.to);
            indeg.set(c.to, indeg.get(c.to) + 1);
        }
    });
    // longest-path layering (Kahn); cycle-safe for feedback patches.
    const depth = new Map(ids.map((i) => [i, 0]));
    const work = new Map(indeg);
    const q = ids.filter((i) => work.get(i) === 0);
    let processed = 0;
    while (q.length) {
        const u = q.shift(); processed++;
        adj.get(u).forEach((v) => {
            if (depth.get(v) < depth.get(u) + 1) depth.set(v, depth.get(u) + 1);
            work.set(v, work.get(v) - 1);
            if (work.get(v) === 0) q.push(v);
        });
    }
    if (processed < ids.length) { // nodes left in a cycle: stack them below
        let d = Math.max(0, ...depth.values()) + 1;
        ids.forEach((i) => { if (work.get(i) > 0) depth.set(i, d++); });
    }
    const byRow = new Map();
    ids.forEach((i) => { const r = depth.get(i); if (!byRow.has(r)) byRow.set(r, []); byRow.get(r).push(i); });
    const pos = new Map(); let maxCol = 0;
    byRow.forEach((arr, r) => arr.forEach((id, col) => {
        pos.set(id, { x: X0 + col * COL, y: Y0 + r * ROW });
        if (col > maxCol) maxCol = col;
    }));
    return { pos: pos, commentX: X0 + (maxCol + 1) * COL + 20 };
}

async function execTool(name, input) {
    input = input || {};
    const x = (input.x != null) ? input.x : 40;
    const y = (input.y != null) ? input.y : 40;
    switch (name) {
        case "create_object": {
            const nm = nextName("obj");
            const args = atomize((input.args || []).map(String));
            Max.outlet("/newdefault", nm, x, y, input.maxclass, ...args);
            if (input.maxclass === "comment" && args.length) {
                Max.outlet("/setbox", nm, "set", ...args);
            }
            register(nm, input.maxclass, input.name);
            const label = input.name || nm;
            return "created '" + label + "' (" + nm + "): [" + [input.maxclass].concat(args).join(" ") + "]";
        }
        case "create_message": {
            const nm = nextName("msg");
            Max.outlet("/newdefault", nm, x, y, "message");
            Max.outlet("/setbox", nm, "set", ...atomize(String(input.text).split(" ")));
            register(nm, "message", input.name);
            const label = input.name || nm;
            return "created '" + label + "' (" + nm + "): message [" + input.text + "]";
        }
        case "create_comment": {
            const nm = nextName("obj");
            Max.outlet("/newdefault", nm, x, y, "comment");
            Max.outlet("/setbox", nm, "set", ...String(input.text).split(" "));
            register(nm, "comment", input.name);
            const label = input.name || nm;
            return "created '" + label + "' (" + nm + "): comment [" + input.text + "]";
        }
        case "connect": {
            const src = resolve(input.from_name), dst = resolve(input.to_name);
            if (!src) return "ERROR: no object named '" + input.from_name + "'. Known: " + knownLabels().join(", ");
            if (!dst) return "ERROR: no object named '" + input.to_name + "'. Known: " + knownLabels().join(", ");
            if (src.maxclass === "comment") return "ERROR: '" + input.from_name + "' is a comment and has no outlet; comments cannot be connected.";
            if (dst.maxclass === "comment") return "ERROR: '" + input.to_name + "' is a comment and has no inlet; comments cannot be connected.";
            Max.outlet("/connect", src.name, input.outlet, dst.name, input.inlet);
            return "connected " + input.from_name + ":" + input.outlet + " -> " + input.to_name + ":" + input.inlet;
        }
        case "disconnect": {
            const src = resolve(input.from_name), dst = resolve(input.to_name);
            if (!src || !dst) return "ERROR: unknown object. Known: " + knownLabels().join(", ");
            Max.outlet("/disconnect", src.name, input.outlet, dst.name, input.inlet);
            return "disconnected";
        }
        case "delete_object": {
            const rec = resolve(input.name);
            if (!rec) return "ERROR: no object named '" + input.name + "'.";
            Max.outlet("/delete", rec.name);
            for (const [k, v] of [...nodes]) if (v.name === rec.name) nodes.delete(k);
            return "deleted " + input.name;
        }
        case "set_dsp":
            Max.outlet("/dsp", input.on ? 1 : 0);
            return "dsp " + (input.on ? "on" : "off");
        case "read_patch": {
            const json = await readPatch(1500);
            return json;
        }
        case "clear_canvas": {
            const names = new Set([...nodes.values()].map(v => v.name));
            names.forEach((nm) => Max.outlet("/delete", nm));
            nodes.clear(); counter = 0;
            return "cleared " + names.size + " object(s)";
        }
        case "build_patch": {
            const objs = input.objects || [];
            const conns = input.connections || [];
            if (!objs.length) return "ERROR: build_patch needs a non-empty 'objects' array.";
            const Y0 = input.title ? 288 : 240;
            const { pos, commentX } = layoutGraph(objs, conns, { y0: Y0 });
            const laneY = []; // track used comment-lane rows to avoid overlap
            function placeComment(text, y) {
                let cy = y;
                while (laneY.some((yy) => Math.abs(yy - cy) < 24)) cy += 24;
                laneY.push(cy);
                const cn = nextName("obj");
                Max.outlet("/newdefault", cn, commentX, cy, "comment");
                Max.outlet("/setbox", cn, "set", ...String(text).split(" ").filter(Boolean));
            }
            if (input.title) {
                const tn = nextName("obj");
                Max.outlet("/newdefault", tn, 480, 244, "comment");
                Max.outlet("/setbox", tn, "set", ...String(input.title).split(" ").filter(Boolean));
            }
            // 1) create every object at its computed position
            for (const ob of objs) {
                const p = pos.get(ob.id) || { x: 480, y: Y0 };
                const type = ob.type || ob.maxclass;
                let nm, mc;
                if (type === "message") {
                    nm = nextName("msg"); mc = "message";
                    Max.outlet("/newdefault", nm, p.x, p.y, "message");
                    Max.outlet("/setbox", nm, "set", ...atomize(String(ob.text || "").split(" ").filter(Boolean)));
                } else if (type === "comment") {
                    nm = nextName("obj"); mc = "comment";
                    Max.outlet("/newdefault", nm, p.x, p.y, "comment");
                    Max.outlet("/setbox", nm, "set", ...String(ob.text || "").split(" ").filter(Boolean));
                } else {
                    nm = nextName("obj"); mc = type;
                    const args = atomize((ob.args || []).map(String));
                    Max.outlet("/newdefault", nm, p.x, p.y, type, ...args);
                }
                register(nm, mc, ob.id);
                if (ob.comment) placeComment(ob.comment, p.y);
            }
            // 2) wire every connection by id
            const requested = [], skipped = [];
            for (const c of conns) {
                const src = resolve(c.from), dst = resolve(c.to);
                if (!src || !dst) { skipped.push(c.from + "->" + c.to + " (unknown id)"); continue; }
                if (src.maxclass === "comment" || dst.maxclass === "comment") { skipped.push(c.from + "->" + c.to + " (comment)"); continue; }
                const ou = c.outlet || 0, il = c.inlet || 0;
                Max.outlet("/connect", src.name, ou, dst.name, il);
                requested.push({ src: src.name, ou, dst: dst.name, il, from: c.from, to: c.to });
            }
            // 3) let thispatcher flush, then read back and verify
            await new Promise((r) => setTimeout(r, 400));
            const json = await readPatch(1800);
            let present = 0; const missing = [];
            try {
                const patch = JSON.parse(json);
                const have = new Set((patch.lines || []).map((l) => l.src + "|" + l.outlet + "|" + l.dst + "|" + l.inlet));
                requested.forEach((r) => {
                    if (have.has(r.src + "|" + r.ou + "|" + r.dst + "|" + r.il)) present++;
                    else missing.push(r.from + ":" + r.ou + " -> " + r.to + ":" + r.il);
                });
            } catch (e) {
                return "built " + objs.length + " objects, issued " + requested.length + " connections (verify failed: " + e.message + ")";
            }
            let rep = "built " + objs.length + " objects; " + present + "/" + requested.length + " connections verified";
            if (missing.length) rep += ". MISSING (reissue with connect): " + missing.join("; ");
            if (skipped.length) rep += ". skipped: " + skipped.join("; ");
            return rep;
        }
        case "lookup_object": {
            const db = objDb();
            if (!db || !Object.keys(db).length) return "No object database; build it with tools/build_maxref_db.py.";
            const o = db[input.name];
            if (o) return formatDoc(o);
            const keys = Object.keys(db);
            const close = keys.filter(k => k.indexOf(input.name) !== -1).slice(0, 6);
            return "'" + input.name + "' not found." + (close.length ? " Similar: " + close.join(", ") : "");
        }
        default:
            return "unknown tool: " + name;
    }
}

// ---------------------------------------------------------------------------
// LLM backend. Swap this one function to point at a local Gemma server
// (OpenAI-compatible) instead of Anthropic.
// ---------------------------------------------------------------------------
const FALLBACK_SYSTEM = [
    "You build and drive a Max/MSP patch through tools. Rules:",
    "- Objects are addressed by stable scripting names returned by create_object.",
    "- Wire, disconnect and delete by name. Outlets/inlets are 0-indexed, left to right.",
    "- Audio output is [dac~]; connect a gain (*~) to both dac~ inlets for stereo, then set_dsp(true).",
    "- Decouple value (number/flonum) from trigger (button); load a message via its right inlet, not [prepend set].",
    "- Use [trigger] for ordering and fan-out. Place objects right of the chat panel (x>=460) so they are visible.",
    "- Before extending an existing patch, call read_patch to see what is really there.",
    "- Keep replies short; describe what you built in one or two sentences.",
].join("\n");

function loadGuide() {
    const candidates = [
        path.join(__dirname, "..", "GUIDE.md"),
        path.join(__dirname, "GUIDE.md"),
    ];
    for (const c of candidates) {
        try { const t = fs.readFileSync(c, "utf8"); if (t) return t; } catch (e) {}
    }
    return FALLBACK_SYSTEM;
}
const SYSTEM = loadGuide();

let history = [];

async function callLLM(messages) {
    const res = await fetch(CONFIG.api_url, {
        method: "POST",
        headers: {
            "content-type": "application/json",
            "x-api-key": CONFIG.anthropic_api_key,
            "anthropic-version": CONFIG.anthropic_version,
        },
        body: JSON.stringify({
            model: CONFIG.model,
            max_tokens: CONFIG.max_tokens,
            system: SYSTEM,
            tools: TOOLS,
            messages: messages,
        }),
    });
    if (!res.ok) {
        const t = await res.text();
        throw new Error("LLM HTTP " + res.status + ": " + t.slice(0, 300));
    }
    return await res.json();
}

async function runAgent(userText) {
    history.push({ role: "user", content: userText });
    let guard = 0;
    while (guard++ < 16) {
        let resp;
        try {
            resp = await callLLM(history);
        } catch (e) {
            sendToUI("Error: " + e.message);
            Max.post("chat.js LLM error: " + e.message);
            return;
        }
        history.push({ role: "assistant", content: resp.content });

        const text = (resp.content || []).filter(b => b.type === "text").map(b => b.text).join("\n");
        if (text) sendToUI(text);

        const toolUses = (resp.content || []).filter(b => b.type === "tool_use");
        // Branch on tool_use presence, NOT stop_reason: if the model emitted any
        // tool calls we MUST answer every one with a tool_result, or the next
        // request 400s ("tool_use without tool_result"). Only finish when there
        // are no tool calls left.
        if (toolUses.length === 0) return;

        const results = [];
        for (const tu of toolUses) {
            let out;
            try { out = await execTool(tu.name, tu.input); }
            catch (e) { out = "tool error: " + e.message; }
            results.push({ type: "tool_result", tool_use_id: tu.id, content: String(out) });
        }
        history.push({ role: "user", content: results });
    }
    sendToUI("(stopped: too many steps)");
}

// ---------------------------------------------------------------------------
// HTTP server + SSE. jweb points at http://127.0.0.1:<port>
// ---------------------------------------------------------------------------
let sseClients = [];
function sendToUI(text) {
    const payload = "data: " + JSON.stringify({ role: "assistant", text: text }) + "\n\n";
    sseClients.forEach((res) => { try { res.write(payload); } catch (e) {} });
}

const INDEX = (() => {
    try { return fs.readFileSync(path.join(__dirname, "index.html"), "utf8"); }
    catch (e) { return "<html><body>index.html missing</body></html>"; }
})();

const server = http.createServer((req, res) => {
    if (req.method === "GET" && (req.url === "/" || req.url === "/index.html")) {
        res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
        res.end(INDEX);
        return;
    }
    if (req.method === "GET" && req.url === "/events") {
        res.writeHead(200, {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            "connection": "keep-alive",
        });
        res.write("retry: 1000\n\n");
        sseClients.push(res);
        req.on("close", () => { sseClients = sseClients.filter(c => c !== res); });
        return;
    }
    if (req.method === "POST" && req.url === "/send") {
        let body = "";
        req.on("data", (c) => { body += c; });
        req.on("end", () => {
            res.writeHead(202, { "content-type": "application/json" });
            res.end("{}");
            try {
                const { text } = JSON.parse(body || "{}");
                if (text && text.trim()) runAgent(text.trim());
            } catch (e) { Max.post("chat.js bad /send body: " + e.message); }
        });
        return;
    }
    if (req.method === "POST" && req.url === "/reset") {
        history = [];
        res.writeHead(200, { "content-type": "application/json" });
        res.end("{}");
        Max.post("chat.js: conversation reset");
        return;
    }
    res.writeHead(404); res.end();
});

server.listen(CONFIG.port, "127.0.0.1", () => {
    Max.post("chat.js: serving on http://127.0.0.1:" + CONFIG.port +
             (CONFIG.anthropic_api_key ? "" : "  (WARNING: no API key in chat.config.json)"));
});

Max.addHandler("reset", () => { history = []; counter = 0; nodes.clear(); Max.post("chat.js: conversation reset"); });
