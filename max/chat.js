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
    max_tokens: 1500,
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

// ---------------------------------------------------------------------------
// Patch state (stable scripting names, mirrors the Python server)
// ---------------------------------------------------------------------------
let counter = 0;
const created = new Set();
function nextName(prefix) { const n = prefix + "_" + counter; counter++; created.add(n); return n; }

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
    { name: "create_object", description: "Create a Max object box [maxclass args...] at (x,y). Returns its scripting name (e.g. obj_3).",
      input_schema: { type: "object", properties: {
          maxclass: { type: "string", description: "e.g. cycle~, *~, dac~, metro" },
          args: { type: "array", items: { type: "string" }, description: "typed-in arguments" },
          x: { type: "integer" }, y: { type: "integer" } }, required: ["maxclass"] } },
    { name: "create_message", description: "Create a message box with the given content at (x,y).",
      input_schema: { type: "object", properties: {
          text: { type: "string" }, x: { type: "integer" }, y: { type: "integer" } }, required: ["text"] } },
    { name: "connect", description: "Wire from_name:outlet -> to_name:inlet (0-indexed, left to right).",
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
];

async function execTool(name, input) {
    input = input || {};
    const x = (input.x != null) ? input.x : 40;
    const y = (input.y != null) ? input.y : 40;
    switch (name) {
        case "create_object": {
            const nm = nextName("obj");
            const args = (input.args || []).map(String);
            Max.outlet("/newdefault", nm, x, y, input.maxclass, ...args);
            return "created " + nm + ": [" + [input.maxclass].concat(args).join(" ") + "]";
        }
        case "create_message": {
            const nm = nextName("msg");
            Max.outlet("/newdefault", nm, x, y, "message");
            Max.outlet("/setbox", nm, "set", ...String(input.text).split(" "));
            return "created " + nm + ": message [" + input.text + "]";
        }
        case "connect":
            Max.outlet("/connect", input.from_name, input.outlet, input.to_name, input.inlet);
            return "connected " + input.from_name + ":" + input.outlet + " -> " + input.to_name + ":" + input.inlet;
        case "disconnect":
            Max.outlet("/disconnect", input.from_name, input.outlet, input.to_name, input.inlet);
            return "disconnected";
        case "delete_object":
            Max.outlet("/delete", input.name); created.delete(input.name);
            return "deleted " + input.name;
        case "set_dsp":
            Max.outlet("/dsp", input.on ? 1 : 0);
            return "dsp " + (input.on ? "on" : "off");
        case "read_patch": {
            const json = await readPatch(1500);
            return json;
        }
        case "clear_canvas": {
            let n = 0;
            created.forEach((nm) => { Max.outlet("/delete", nm); n++; });
            created.clear(); counter = 0;
            return "cleared " + n + " object(s)";
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
    while (guard++ < 12) {
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
        if (resp.stop_reason !== "tool_use" || toolUses.length === 0) return;

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
    res.writeHead(404); res.end();
});

server.listen(CONFIG.port, "127.0.0.1", () => {
    Max.post("chat.js: serving on http://127.0.0.1:" + CONFIG.port +
             (CONFIG.anthropic_api_key ? "" : "  (WARNING: no API key in chat.config.json)"));
});

Max.addHandler("reset", () => { history = []; counter = 0; created.clear(); Max.post("chat.js: conversation reset"); });
