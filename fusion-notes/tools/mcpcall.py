"""Call a tool on the local Fusion MCP bridge directly: mcpcall.py <tool> '<json args>'"""
import json, re, sys, urllib.request
URL = "http://127.0.0.1:8765/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
def post(body, sid=None):
    h = dict(H)
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(URL, json.dumps(body).encode(), h, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.headers.get("Mcp-Session-Id"), r.read().decode()
sid, _ = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "0"}}})
post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
_, out = post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")}}, sid)
m = re.search(r"\{.*\}", out, re.S); d = json.loads(m.group(0))
res = d.get("result", d)
for c in res.get("content", []):
    print(c.get("text", "[%s]" % c.get("type")))
if res.get("isError"): print("isError: true")
