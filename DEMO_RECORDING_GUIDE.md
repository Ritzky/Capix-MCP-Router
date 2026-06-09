# CapIX Router MCP Demo Recording Guide

Use this when recording the Google Rapid Agent / MongoDB MCP submission. Keep the video under three minutes.

## Demo Thesis

CapIX turns a workload into a routed compute plan. MongoDB MCP provides the live route book, Gemini/Agent Builder plans the split, and the private CapIX app takes the wallet deposit before unlocking the router.

## One-Minute Local Proof

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m agent_builder.demo
```

What to point out:

- The route book is read through MongoDB MCP, direct MongoDB, or the offline catalog with the source reported.
- The agent returns CPU/GPU allocation, not just a chat answer.
- The quote compares highest-required-route cost against the optimized split.
- Controlled execution proof is explicit: only the private app can call Oracle Node Agents.

## Hosted Router Proof

```bash
CAPIX_ROUTER_PORT=8788 python http_server.py
```

In a second terminal:

```bash
curl http://127.0.0.1:8788/health
curl http://127.0.0.1:8788/nodes | python -m json.tool | head -80
```

Then route a demo workload:

```bash
curl -s http://127.0.0.1:8788/smart-route \
  -H "content-type: application/json" \
  -d '{
    "track": "compute",
    "language": "python",
    "code_content": "import numpy as np\nrows=[1,2,3]\nclean=[x for x in rows if x>1]\na=np.random.rand(1024,1024)\nb=np.random.rand(1024,1024)\nprint(np.dot(a,b).mean(), len(clean))",
    "setup_script": "numpy==2.1.3",
    "bundle_file_name": "demo.py"
  }' | python -m json.tool
```

What to point out:

- MongoDB stores many compute and inference routes; the UI should not depend on two hard-coded nodes.
- The router shows which segments go to CPU lanes and which segments go to GPU lanes.
- The savings are grounded in the active route book.

## Private CapIX App Proof

Open:

```text
https://www.capix.network/buy?track=compute
```

Recording steps:

1. Connect the funded Phantom wallet.
2. Open `Smart Route`.
3. Load `Basic real Oracle run` for the real CPU-lane demo, or `Complex mock demo` for a richer route split.
4. Pay the 0.01 CPX anti-abuse deposit.
5. Show the route allocation table and savings card.
6. Run delivery. The basic demo can execute on the Oracle CPU lane; richer demos return controlled `output.txt` proof after routing.

Say this clearly:

> CapIX does not route before payment. The public MCP repo is a safe skeleton; the private app mints a short-lived route key after CPX deposit, injects the private policy, and then calls the router.

## EasyA Add-On Beat

After Smart Route, switch to:

```text
https://www.capix.network/sell
https://www.capix.network/buy
```

Show that sellers list capacity against visible demand, buyers buy compute or inference from live asks, and CPX settlement is the receipt for SSH or stream delivery.

## Avoid In The Video

- Do not dwell on the full Exchange page. It is for price discovery, not the demo core.
- Do not show env files, Vercel secrets, Atlas passwords, Oracle credentials, private policy tokens, or treasury keys.
- Do not claim arbitrary uploaded code executes on public hosts. Only the marked basic demo is allowed to run for real.
