# CapIX Router MCP

Open-source routing layer for CapIX Smart Route.

CapIX is the exchange. This repo is the public router skeleton that judges and developers can inspect: it reads a MongoDB-backed route book through MCP, uses Gemini to split compute jobs or inference prompts, and returns a priced allocation. Wallet settlement, treasury logic, private policy, Oracle host credentials, and production delivery stay inside the private CapIX protocol app.

## What This Proves

- **Compute routing:** uploaded scripts are split across CPU and GPU capacity instead of running everything on the most expensive required lane.
- **Inference routing:** complex prompts are stripped of transport wrapper text, decomposed into subtasks, and routed across model sellers by price, latency, and reliability.
- **MongoDB MCP integration:** the route book is loaded from MongoDB Atlas through a hosted MongoDB MCP server.
- **Gemini / Agent Builder integration:** Gemini plans the allocation when configured; deterministic fallbacks keep demos reliable.
- **Paid access boundary:** production Smart Route can require a short-lived paid route key issued by the private CapIX app after a CPX deposit.

## Repository Boundary

Included here:

- Router schemas, prompts, pricing math, fallbacks, and tests.
- Optional FastMCP tool server.
- JSON HTTP bridge used by the private CapIX app.
- Google Agent Builder / ADK agent definitions.
- Dockerfiles and Cloud Build configs for deployment.
- Demo route catalogs and sample workloads.

Not included here:

- CPX treasury keys or mint authority keys.
- Phantom wallet settlement code.
- CapIX private policy source.
- Oracle host agent credentials.
- Production SSH delivery and admin routes.
- Vercel private app environment values.

## Project Layout

```text
router/
  agent.py                 Compute job splitter and pricing estimator
  inference_agent.py       Prompt sanitizer, splitter, and inference route estimator
  mongodb_mcp_client.py    MongoDB MCP client with direct Mongo and offline fallbacks
  prompts.py               Strict JSON prompts for Gemini
  policy.py                Paid-route-key/private-policy boundary
  schemas.py               Route, allocation, and quote models

agent_builder/
  agents.py                Google ADK agents for compute and inference routing
  tools.py                 Agent tools backed by the router
  demo.py                  Local Agent Builder demo

server.py                  FastMCP tool server
http_server.py             JSON HTTP service for the private CapIX app
seed_nodes.py              Seeds compute and inference route catalogs into MongoDB
pull_capix_snapshot.py     One-shot private CapIX snapshot -> MongoDB sync
Dockerfile                 Router HTTP service container
Dockerfile.mongodb-mcp     Hosted MongoDB MCP service container
cloudbuild.*.yaml          Cloud Build image configs
examples/                  Demo workloads and local route snapshots
tests/                     Unit tests for routing, fallback, MCP, and agent tools
```

## Local Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m compileall .
pytest -q
```

Run a local JSON router:

```bash
CAPIX_ROUTER_PORT=8788 python http_server.py
```

In another terminal:

```bash
curl http://127.0.0.1:8788/health
curl http://127.0.0.1:8788/nodes | python -m json.tool | head -80
```

Run a local compute route:

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

Run a local inference route:

```bash
curl -s http://127.0.0.1:8788/smart-route \
  -H "content-type: application/json" \
  -d '{
    "track": "inference",
    "language": "prompt",
    "prompt_content": "Build an agent workflow for a support automation launch. Extract incident themes, plan API checks, draft escalation logic, and return a launch-review report."
  }' | python -m json.tool
```

## MCP And HTTP Entry Points

This repo has two server modes.

### FastMCP Tool Server

Use this when an MCP client wants tools directly:

```bash
python server.py
```

Tools exposed:

- `get_node_pricing`
- `get_inference_routes`
- `split_and_route_job_tool`
- `split_and_route_prompt_tool`

### JSON HTTP Router

Use this for the private CapIX app and Cloud Run:

```bash
python http_server.py
```

Routes exposed:

- `GET /health`
- `GET /nodes`
- `POST /smart-route`
- `POST /route`

`/smart-route` accepts either compute or inference payloads and returns the same route response shape the CapIX Buy page displays.

## Environment Variables

Start from `.env.example`. Keep real values out of Git.

Core router:

```text
CAPIX_ROUTER_TOKEN=shared-private-app-token
CAPIX_REQUIRE_PAID_ROUTE_KEY=true
CAPIX_PRIVATE_POLICY_URL=https://capix.network/api/router/private-policy
CAPIX_PRIVATE_POLICY_TOKEN=shared-private-policy-token
```

MongoDB MCP:

```text
MONGODB_MCP_URL=https://your-mongodb-mcp-service/mcp
MONGODB_MCP_TOKEN=optional-bearer-token
MONGODB_MCP_FIND_TOOL=find
MONGODB_MCP_DATABASE=capix_compute_db
MONGODB_MCP_NODES_COLLECTION=nodes
MONGODB_MCP_INFERENCE_COLLECTION=inference_routes
```

Gemini:

```text
CAPIX_USE_VERTEX_AI=true
GOOGLE_CLOUD_PROJECT=your-google-cloud-project
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-2.5-flash
```

Local-only fallback:

```text
GEMINI_API_KEY=your-local-gemini-api-key
MONGO_URI=mongodb://localhost:27017/
```

For the Google Cloud demo, prefer Vertex AI on Cloud Run and MongoDB MCP for route data. Do not set `MONGO_URI` on the router service if you want `/nodes` to report `mongodb-mcp`.

## MongoDB Atlas Setup

Create a database:

```text
capix_compute_db
```

Collections:

```text
nodes             compute routes
inference_routes  model-provider routes
```

Seed demo-safe route books:

```bash
export MONGO_URI="<mongodb-atlas-driver-connection-string>"
python3 seed_nodes.py --prune
```

Expected seed size:

```text
nodes             66 routes
inference_routes  60 routes
```

Smoke check:

```bash
python - <<'PY'
from router.mongodb_mcp_client import MongoDbMcpClient
client = MongoDbMcpClient()
compute = client.get_node_pricing()
inference = client.get_inference_routes()
print(compute.source, len(compute.nodes))
print(inference.source, len(inference.routes))
PY
```

Source meanings:

- `mongodb-mcp`: router is reading through hosted MongoDB MCP.
- `mongodb-direct`: router is using `MONGO_URI` directly.
- `market-seed`: router fell back to bundled demo catalogs.

## One-Shot CapIX Snapshot Sync

If the private CapIX app exposes a signed snapshot endpoint, use this once to pull visible compute routes into MongoDB:

```bash
export CAPIX_SNAPSHOT_URL="https://capix.network/api/router/compute-snapshot"
export CAPIX_ROUTER_SYNC_TOKEN="<private-sync-token>"
export MONGO_URI="<mongodb-atlas-driver-connection-string>"
python3 pull_capix_snapshot.py
```

For a dry run:

```bash
python3 pull_capix_snapshot.py --dry-run
```

This script is intentionally one-shot. The public repo does not contain private capacity ingestion, host credentials, or settlement state.

## Deploy To Google Cloud Run

Use two hosted services:

```text
Private CapIX app on Vercel
  -> hosted CapIX Router HTTP service
  -> hosted MongoDB MCP service
  -> MongoDB Atlas capix_compute_db
  -> Gemini through Vertex AI
```

### 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com
```

### 2. Create Artifact Registry

```bash
export PROJECT_ID="<google-cloud-project-id>"
export REGION="us-central1"
export REPOSITORY="capix"

gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="CapIX router images"
```

### 3. Create Secrets

```bash
printf '%s' "$MONGO_URI" | gcloud secrets create capix-mongo-uri --data-file=-
printf '%s' "$CAPIX_ROUTER_TOKEN" | gcloud secrets create capix-router-token --data-file=-
printf '%s' "$CAPIX_PRIVATE_POLICY_TOKEN" | gcloud secrets create capix-private-policy-token --data-file=-
```

If a secret already exists:

```bash
printf '%s' "$MONGO_URI" | gcloud secrets versions add capix-mongo-uri --data-file=-
```

### 4. Build And Deploy MongoDB MCP

```bash
gcloud builds submit \
  --config cloudbuild.mongodb-mcp.yaml \
  --substitutions _IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-mongodb-mcp:latest"
```

```bash
gcloud run deploy capix-mongodb-mcp \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-mongodb-mcp:latest" \
  --set-env-vars="MDB_MCP_TRANSPORT=http,MDB_MCP_READ_ONLY=true,MDB_MCP_HTTP_HOST=0.0.0.0,MDB_MCP_HTTP_BODY_RESPONSE_TYPE=json" \
  --set-secrets="MDB_MCP_CONNECTION_STRING=capix-mongo-uri:latest" \
  --allow-unauthenticated
```

The router should call:

```text
https://<mongodb-mcp-cloud-run-url>/mcp
```

For production, make the Atlas database user read-only and scope it to `capix_compute_db`. For stricter deployments, put Cloud Run IAM or an API gateway in front of the MCP service.

### 5. Build And Deploy CapIX Router

```bash
gcloud builds submit \
  --config cloudbuild.router.yaml \
  --substitutions _IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-router-mcp:latest"
```

```bash
export MONGODB_MCP_URL="https://<mongodb-mcp-cloud-run-url>/mcp"

gcloud run deploy capix-router-mcp \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-router-mcp:latest" \
  --set-env-vars="MONGODB_MCP_URL=$MONGODB_MCP_URL,MONGODB_MCP_FIND_TOOL=find,MONGODB_MCP_DATABASE=capix_compute_db,MONGODB_MCP_NODES_COLLECTION=nodes,MONGODB_MCP_INFERENCE_COLLECTION=inference_routes,CAPIX_REQUIRE_PAID_ROUTE_KEY=true,CAPIX_PRIVATE_POLICY_URL=https://capix.network/api/router/private-policy,CAPIX_USE_VERTEX_AI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-2.5-flash" \
  --set-secrets="CAPIX_ROUTER_TOKEN=capix-router-token:latest,CAPIX_PRIVATE_POLICY_TOKEN=capix-private-policy-token:latest" \
  --allow-unauthenticated
```

Smoke check:

```bash
export ROUTER_URL="https://<router-cloud-run-url>"
export CAPIX_ROUTER_TOKEN="<same-router-token>"

curl "$ROUTER_URL/health"
curl "$ROUTER_URL/nodes" \
  -H "authorization: Bearer $CAPIX_ROUTER_TOKEN" \
  | python -m json.tool | head -80
```

The `/nodes` response should include:

```json
{
  "source": "mongodb-mcp"
}
```

## Connect The Private CapIX App

Set these on the private Vercel project:

```text
CAPIX_USE_SMART_ROUTER=true
CAPIX_ROUTER_URL=https://<router-cloud-run-url>/smart-route
CAPIX_ROUTER_TOKEN=<same-token-as-router>
CAPIX_ROUTER_KEY_SECRET=<private-route-key-derivation-secret>
CAPIX_PRIVATE_POLICY_TOKEN=<same-private-policy-token-used-by-router>
```

Private app flow:

```text
Buyer opens Smart Route
  -> Phantom pays 0.01 CPX anti-abuse deposit
  -> private app mints a short-lived paid route key
  -> private app calls hosted CapIX Router
  -> router loads private policy and scans MongoDB MCP routes
  -> Gemini returns a CPU/GPU or model-provider split
  -> private app handles quote handoff and controlled delivery proof
```

The router should not run before the CPX deposit when `CAPIX_REQUIRE_PAID_ROUTE_KEY=true`.

## Response Shape

Compute and inference routes return:

```json
{
  "routing": {
    "analysis": "string",
    "allocation": [],
    "nodes": [],
    "source": "mongodb-mcp",
    "fallback_used": false,
    "warnings": []
  },
  "unoptimized_gpu_cost_usd": 0.45,
  "capix_optimized_cost_usd": 0.17,
  "percent_savings": "61%",
  "hold_cap_cpx": 1,
  "settled_cpx": 0.17,
  "released_cpx": 0.83
}
```

For compute, `allocation` uses line ranges:

```json
{
  "node_id": "node-id",
  "label": "Vast.ai verified NVIDIA L4",
  "line_start": 33,
  "line_end": 42,
  "task_label": "numeric_kernels_and_tensor_operations",
  "reason": "Routed to GPU because this block contains tensor and matrix work."
}
```

For inference, `allocation` uses prompt segments:

```json
{
  "node_id": "route-id",
  "label": "Foza provider pool / Mistral-Mixtral-8x22B",
  "line_start": 2,
  "line_end": 2,
  "task_label": "route_plan_decomposition",
  "segment_label": "Decompose the request into tool calls and ordering constraints.",
  "reason": "Planning-heavy prompts use a stronger reasoning lane."
}
```

## Google Agent Builder / ADK

Install optional dependencies:

```bash
pip install -r requirements-agent-builder.txt
```

Run the local agent demo:

```bash
python -m agent_builder.demo
```

Agent definitions live in `agent_builder/agents.py`:

- `CapIX_Compute_Router_Agent`
- `CapIX_Inference_Router_Agent`
- `CapIX_Router_Agent`

The agents use tools from `agent_builder/tools.py`, which call the same router code used by the HTTP service. This keeps the demo honest: Agent Builder orchestrates a multi-step tool workflow, while MongoDB MCP supplies the route registry and Gemini performs the planning.

## Demo Script

For a short recording, use [DEMO_RECORDING_GUIDE.md](DEMO_RECORDING_GUIDE.md).

Best sequence:

1. Show `GET /nodes` returning `source: mongodb-mcp`.
2. Open `https://www.capix.network/buy?track=compute`.
3. Choose `Smart Route`.
4. Pay the `0.01 CPX & Route` deposit.
5. Show CPU/GPU allocation, quote, and savings.
6. Switch to inference Smart Route and show prompt decomposition across model sellers.
7. Explain that the public repo is the inspectable MCP/router layer; private settlement and delivery remain in CapIX.

Suggested judging line:

> CapIX is the exchange. Smart Route is the routing edge: CPX payment unlocks a private route key, MongoDB MCP supplies the market depth, Gemini plans the split, and CapIX delivers compute or inference through the private app.

## Safety Notes

- Never commit `.env`, Atlas passwords, Google credentials, CPX treasury keys, or private policy tokens.
- Keep MongoDB Atlas demo users read-only where possible.
- Keep `CAPIX_REQUIRE_PAID_ROUTE_KEY=true` in hosted demos so routing only happens after CPX deposit.
- Treat arbitrary uploaded code as untrusted. This repo returns routing plans; production execution belongs in isolated private infrastructure.

## License

MIT. See [LICENSE](LICENSE).
