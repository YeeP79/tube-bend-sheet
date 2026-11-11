"""Direct bridge client: import call(tool, **args) -> (parsed_or_text, is_error)."""
import json, re, urllib.request
URL = "http://127.0.0.1:8765/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
def _post(body, sid=None):
    h = dict(H)
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(URL, json.dumps(body).encode(), h, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.headers.get("Mcp-Session-Id"), r.read().decode()
_sid, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "0"}}})
_post({"jsonrpc": "2.0", "method": "notifications/initialized"}, _sid)
def call(tool, **args):
    _, out = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}, _sid)
    d = json.loads(re.search(r"\{.*\}", out, re.S).group(0)); res = d.get("result", d)
    text = "\n".join(c.get("text", "") for c in res.get("content", []))
    try: text = json.loads(text)
    except Exception: pass
    return text, bool(res.get("isError"))
