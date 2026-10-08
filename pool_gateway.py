# Pool gateway: OpenAI-compatible server over harvested vani_ keys.
# Rotates keys; on concurrency_limit/429 switches to next healthy key.
# Run: python pool_gateway.py   (env: PORT, KEYS_FILE)
import json, os, time, uuid, threading
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

PORT = int(os.environ.get("PORT", "3300"))
KEYS_FILE = os.environ.get("KEYS_FILE", os.path.join(os.path.dirname(__file__), "vani_accounts.jsonl"))
UPSTREAM = "https://api.vani.ai/v1"

_lock = threading.Lock()

def load_keys():
    keys, seen = [], set()
    with open(KEYS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = r.get("api_key")
            if k and r.get("status") == "registered" and k not in seen:
                seen.add(k)
                keys.append({"key": k, "alias": r.get("alias"), "cooldown_until": 0.0, "fails": 0})
    return keys

KEYS = load_keys()
app = FastAPI(title="vani-pool-gateway", version="1.0.0")
_client = httpx.Client(timeout=httpx.Timeout(300, connect=20), trust_env=False)

def pick_key(min_cooldown=0):
    now = time.time()
    with _lock:
        cands = [k for k in KEYS if k["cooldown_until"] <= now]
        if not cands:
            return None
        cands.sort(key=lambda k: k["fails"])
        return cands[0]

def cooldown(k, secs, why=""):
    with _lock:
        k["cooldown_until"] = time.time() + secs
        k["fails"] += 1
    print(f"[pool] cooldown {k['alias']} {secs}s ({why})")

@app.get("/health")
def health():
    now = time.time()
    return {"status": "ok", "keys": len(KEYS),
            "available": sum(1 for k in KEYS if k["cooldown_until"] <= now)}

@app.get("/v1/models")
def models():
    k = pick_key()
    if not k:
        return JSONResponse({"error": {"message": "all keys cooling down"}}, status_code=503)
    r = _client.get(f"{UPSTREAM}/models", headers={"Authorization": "Bea"+"rer " + k["key"]})
    return r.json()

@app.post("/v1/chat/completions")
def chat(body: dict):
    stream = bool(body.get("stream"))
    for attempt in range(len(KEYS) + 1):
        k = pick_key()
        if not k:
            return JSONResponse({"error": {"message": "no keys available (all cooling)"}}, status_code=503)
        hdr = {"Authorization": "Bea"+"rer " + k["key"], "Content-Type": "application/json"}
        try:
            r = _client.post(f"{UPSTREAM}/chat/completions", json=body, headers=hdr)
        except Exception as e:
            cooldown(k, 30, f"net {e}")
            continue
        if r.status_code == 429:
            code = ""
            try:
                code = r.json().get("error", {}).get("code", "")
            except Exception:
                pass
            cooldown(k, 90 if code == "concurrency_limit" else 300, code or "429")
            continue
        if r.status_code == 402:
            cooldown(k, 3600, "usage_limit_exceeded")
            continue
        if r.status_code == 401:
            cooldown(k, 86400, "invalid key")
            continue
        if stream:
            return StreamingResponse(r.iter_lines(), media_type="text/event-stream")
        return JSONResponse(r.json(), status_code=r.status_code)
    return JSONResponse({"error": {"message": "all keys exhausted"}}, status_code=503)

if __name__ == "__main__":
    import uvicorn
    print(f"pool loaded: {len(KEYS)} keys")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
